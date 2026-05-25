"""Keyword analysis of uncategorised sessions → suggested category rules.

Algorithm:
  1. Collect first_user_text of all sessions that don't match any existing rule.
  2. Tokenise (lowercase, strip stop words, min 3 chars).
  3. Build a keyword→session-index mapping.
  4. Greedy clustering: pick the highest-frequency keyword, pull in its
     top co-occurring keywords, form a rule, remove those sessions, repeat.
  5. Return up to MAX_SUGGESTIONS SuggestedRule objects.
"""
from __future__ import annotations

import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path

STOP_WORDS = {
    "the", "a", "an", "is", "are", "was", "were", "it", "this", "that",
    "i", "we", "can", "to", "for", "with", "in", "on", "at", "from",
    "and", "or", "but", "not", "be", "do", "have", "has", "had",
    "will", "would", "could", "should", "may", "might", "let", "get",
    "make", "use", "add", "need", "want", "look", "help", "how", "what",
    "when", "where", "why", "who", "which", "also", "just", "some",
    "more", "all", "any", "if", "so", "then", "my", "our", "your",
    "its", "into", "out", "up", "about", "as", "by", "of", "me",
    "im", "please", "update", "create", "file", "there", "they",
    "check", "work", "working", "change", "sure", "good", "go", "now",
    "run", "set", "like", "try", "see", "keep", "move", "show", "here",
    "put", "give", "take", "been", "being", "new", "code", "using",
    "you", "he", "she", "them", "us", "them", "those", "these", "few",
    "same", "own", "such", "too", "very", "just", "over", "after",
    "before", "other", "each", "only", "both", "through", "during",
    "following", "without", "within", "along", "across", "behind",
    "already", "still", "again", "once", "case", "number", "way",
    "day", "time", "current", "currently", "possible", "make", "made",
    "something", "anything", "everything", "nothing", "someone",
    "rather", "instead", "example", "examples", "based", "since",
    "while", "however", "therefore", "because", "although",
    # common dev words too generic to categorise
    "function", "method", "class", "module", "import", "variable",
    "value", "type", "string", "list", "dict", "object", "return",
    "line", "lines", "column", "columns", "row", "rows", "item",
    "items", "array", "index", "key", "keys", "name", "names",
    "path", "paths", "field", "fields", "version", "versions",
    "page", "pages", "section", "content", "data", "user", "users",
    "system", "process", "app", "application", "project", "error",
    "message", "messages", "text", "output", "input", "result",
    "results", "step", "steps", "start", "end", "top", "bottom",
    "right", "left", "side", "part", "parts", "point", "points",
    "read", "write", "open", "close", "save", "load", "call",
    "called", "calling", "pass", "passed", "find", "found",
    "handle", "handles", "handling", "include", "includes",
    "remove", "removed", "add", "added", "move", "moved",
}

MAX_SUGGESTIONS = 12
MIN_CLUSTER_SIZE = 2
CO_OCCUR_RATIO = 0.25  # keyword must appear in at least 25% of cluster sessions


@dataclass
class SuggestedRule:
    suggested_name: str
    match_any: list[str]
    session_count: int
    sample_texts: list[str] = field(default_factory=list)
    accepted: bool = True


def _tokenise(text: str) -> list[str]:
    words = re.findall(r"\b[a-z]{3,}\b", text.lower())
    return [w for w in words if w not in STOP_WORDS]


def get_uncategorised_texts(store, since: str, rules: list[dict]) -> tuple[list[str], int]:
    """Return (first_user_texts, total_uncategorised_tokens) for sessions with no matching rule."""
    from ccspy.categories import categorise

    rows = store.query(
        """
        SELECT s.session_id, s.first_user_text,
               COALESCE(SUM(t.input_tokens + t.output_tokens +
                            t.cache_creation_tokens + t.cache_read_tokens), 0) as tok
        FROM sessions s
        LEFT JOIN turns t ON s.session_id = t.session_id
        WHERE s.first_user_text != ''
          AND s.started_at >= ?
        GROUP BY s.session_id, s.first_user_text
        """,
        (since,),
    )

    texts: list[str] = []
    total_tokens = 0
    for r in rows:
        text = r["first_user_text"] or ""
        if not text:
            continue
        cat = categorise(text, rules)
        if cat == "uncategorized":
            texts.append(text)
            total_tokens += r["tok"] or 0

    return texts, total_tokens


def analyse(texts: list[str]) -> list[SuggestedRule]:
    """Greedy keyword clustering → list of SuggestedRule."""
    if not texts:
        return []

    # Build keyword → {session indices} map
    kw_sessions: dict[str, set[int]] = defaultdict(set)
    session_kws: list[set[str]] = []

    for i, text in enumerate(texts):
        words = set(_tokenise(text))
        session_kws.append(words)
        for w in words:
            kw_sessions[w].add(i)

    # Rank keywords by session frequency
    kw_freq = Counter({k: len(v) for k, v in kw_sessions.items()})
    top_kws = [k for k, c in kw_freq.most_common(200) if c >= MIN_CLUSTER_SIZE]

    suggestions: list[SuggestedRule] = []
    used: set[int] = set()

    for seed in top_kws:
        active = kw_sessions[seed] - used
        if len(active) < MIN_CLUSTER_SIZE:
            continue

        # Co-occurring keywords in these sessions
        co: Counter[str] = Counter()
        for si in active:
            for w in session_kws[si]:
                if w != seed and w in kw_sessions:
                    co[w] += 1

        threshold = max(2, len(active) * CO_OCCUR_RATIO)
        companions = [
            w for w, c in co.most_common(8)
            if c >= threshold and w in set(top_kws)
        ][:4]

        match_any = [seed] + companions
        samples = [texts[i][:120] for i in list(active)[:3]]

        suggestions.append(SuggestedRule(
            suggested_name=seed,
            match_any=match_any,
            session_count=len(active),
            sample_texts=samples,
        ))
        used.update(active)

        if len(suggestions) >= MAX_SUGGESTIONS:
            break

    return suggestions


def delete_rule(category_name: str, categories_path: Path) -> bool:
    """Remove the [[rule]] block with the given category name. Returns True if found."""
    import re
    if not categories_path.exists():
        return False
    content = categories_path.read_text(encoding="utf-8")
    # Split on every [[rule]] boundary; prepend sentinel newline so the first block splits cleanly
    parts = re.split(r'(?=\n\[\[rule\]\])', "\n" + content)
    pattern = re.compile(rf'\bcategory\s*=\s*"{re.escape(category_name)}"')
    new_parts = [p for p in parts if not pattern.search(p)]
    if len(new_parts) == len(parts):
        return False
    result = "".join(new_parts).lstrip("\n")
    result = re.sub(r"\n{3,}", "\n\n", result)
    categories_path.write_text(result, encoding="utf-8")
    return True


def rules_as_toml(rules: list[SuggestedRule]) -> str:
    """Render accepted rules as TOML entries ready to append to categories.toml."""
    lines: list[str] = []
    for r in rules:
        if not r.accepted:
            continue
        keywords = ", ".join(f'"{w}"' for w in r.match_any)
        lines.append(f'\n[[rule]]\ncategory = "{r.suggested_name}"\nmatch_any = [{keywords}]')
    return "\n".join(lines) + "\n"


def append_rules(rules: list[SuggestedRule], categories_path: Path) -> int:
    """Append accepted rules to categories.toml. Returns number of rules written."""
    toml = rules_as_toml(rules)
    if not toml.strip():
        return 0
    with categories_path.open("a", encoding="utf-8") as fh:
        fh.write(toml)
    return sum(1 for r in rules if r.accepted)
