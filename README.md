# ccspy — Claude Code Spy

> A local-first terminal dashboard for your AI coding agent token usage. See exactly where your tokens go, what it would cost on the pay-as-you-go API, and how you actually work.

![ccspy dashboard](CCSpy.jpeg)

**ccspy is read-only — it never touches your Claude Code or Codex data.**

---

## Supported tools

| Tool | Data source |
|------|-------------|
| **Claude Code** | `~/.claude/projects/**/*.jsonl` |
| **OpenAI Codex CLI** | `~/.codex/sessions/**/*.jsonl` |

Both sources are read automatically and merged into a unified dashboard. No configuration required if you use the default install locations.

---

## Features

- **Live session strip** — shows active sessions as they run, with sparkline and elapsed time
- **Token totals** — headline count with ≈ api-equiv cost, delta vs previous period, and in/out/cache breakdown
- **Daily sparkline** — per-day token volume with peak annotation and cost
- **By project** — horizontal bar chart of token share across your projects, filterable
- **By model** — Sonnet vs Haiku vs Opus vs GPT split with per-model api-equiv cost
- **By category** — keyword-rule categorisation of sessions (feature-build, debug, design, etc.) — fully customisable
- **Task breakdown** — per-project message count, avg task duration, and plan vs execute token split
- **Time-of-day** — 24-bar sparkline in your local timezone, peak hour annotation
- **Timing stats** — total time Claude spent building + total time Claude waited for you to continue
- **Subagent tracking** — spawned subagent count and avg per session
- **Drill-downs** — project → session → turn detail; pricing table; data sources
- **Command palette** (`:`) — fuzzy-search over all actions
- **Export** — dump current view to CSV

---

## Requirements

- Python 3.11+
- [uv](https://docs.astral.sh/uv/getting-started/installation/) (recommended) or pip
- Claude Code and/or Codex CLI with at least one session on disk
- **Windows only:** [Windows Terminal](https://aka.ms/terminal) — required for proper Unicode and colour rendering (the default `cmd.exe` will not display correctly)

---

## Install

**From GitHub:**

```bash
uv tool install git+https://github.com/erohryan/CCSpy
```

**Clone and install locally:**

```bash
git clone https://github.com/erohryan/CCSpy
cd CCSpy
uv tool install .
```

**With pip:**

```bash
pip install git+https://github.com/erohryan/CCSpy
```

This puts `ccspy` on your PATH.

---

## Windows

### Install

Open **Windows Terminal** (PowerShell or cmd) and run the same install command:

```powershell
uv tool install git+https://github.com/erohryan/CCSpy
```

If `uv` is not installed, get it first:

```powershell
winget install astral-sh.uv
```

Then run:

```powershell
ccspy
```

### Data locations on Windows

| Purpose | Path |
|---------|------|
| Claude Code CLI sessions | `%USERPROFILE%\.claude\projects\` |
| Claude desktop app sessions | `%APPDATA%\Claude\projects\` |
| Codex CLI sessions | `%USERPROFILE%\.codex\sessions\` |
| ccspy config + cache | `%APPDATA%\ccspy\` |
| Category rules | `%APPDATA%\ccspy\categories.toml` |

ccspy checks the Claude Code CLI path first. If you installed via the Claude desktop app and the CLI path doesn't exist, it falls back to the `%APPDATA%\Claude\projects\` location automatically. If neither is found, set `CLAUDE_HOME` (see below).

### Environment variables

```powershell
# Override Claude data location (e.g. if you used the desktop app installer)
$env:CLAUDE_HOME = "$env:APPDATA\Claude"

# Override ccspy config directory
$env:CCSPY_CONFIG = "D:\my-ccspy-config"

# Set a preferred editor for category rules (defaults to Notepad)
$env:EDITOR = "code"   # VS Code
```

To make these permanent, run in PowerShell (user-scope, no admin needed):

```powershell
[System.Environment]::SetEnvironmentVariable("CLAUDE_HOME", "$env:APPDATA\Claude", "User")
```

Or: **Start → Edit the system environment variables → Environment Variables → User variables → New**

### Editing category rules on Windows

Press `e` in the dashboard to open `categories.toml` in Notepad. Set `EDITOR=code` (or any other editor on your PATH) to use a different one.

---

## Usage

```bash
ccspy              # dashboard — 7-day range
ccspy today        # since midnight local time
ccspy week         # last 7 days
ccspy month        # last 30 days

ccspy export --range 30d --format csv --out ~/report.csv
ccspy export --range 7d --format json

ccspy cache rebuild   # re-parse all JSONL files from scratch
ccspy cache clear     # delete the SQLite cache

ccspy --version
ccspy --help
```

---

## Keyboard shortcuts

| Key | Action |
|-----|--------|
| `1` | Today (since midnight) |
| `2` | Last 7 days |
| `3` | Last 30 days |
| `:` | Command palette — fuzzy search all actions |
| `p` | Project picker → drill into sessions |
| `s` | Session picker → drill into turns |
| `t` | Tool picker → drill into per-project usage |
| `u` | Suggest category rules from uncategorised sessions |
| `e` | Edit category rules in `$EDITOR` / Notepad |
| `c` | Toggle chart style — individual bars ↔ stacked proportion bar |
| `l` | Community leaderboard (opt-in) |
| `x` | Export current view to CSV |
| `/` | Filter dashboard by project name |
| `r` | Force reload + cache sync |
| `?` | Help overlay |
| `q` / `Ctrl-C` | Quit |

Inside drill-down screens, `Enter` navigates deeper and `Esc` goes back.

---

## Task breakdown

The **TASKS** panel shows per-project:

- **msgs** — number of distinct user messages sent (each message = one task)
- **avg duration** — median time from sending a message to Claude finishing
- **plan vs execute bar** — token share split between planning turns (reading, exploring, no file changes) and execution turns (Edit, Write, Bash)

This gives you a sense of how much of your AI usage is thinking vs doing across each project.

---

## Timing

The **TIMINGS** row shows cumulative time across all turns in the selected range:

- **building** — total time Claude spent processing your requests
- **waiting** — total time Claude sat idle waiting for you to continue (capped at 5 minutes per gap — longer gaps are treated as new requests, not continuations)

If you see "rebuild cache to populate", run `ccspy cache rebuild` once. This re-parses your JSONL files to capture the message timestamps needed for timing calculations.

---

## Categories

Categories classify your sessions by what you were doing. They're defined as keyword rules — first match wins.

| Platform | Config file |
|----------|-------------|
| macOS / Linux | `~/.config/ccspy/categories.toml` |
| Windows | `%APPDATA%\ccspy\categories.toml` |

Press `e` in the dashboard to open the file in your editor (`$EDITOR` on macOS/Linux, Notepad on Windows). Changes take effect immediately on the next reload. Press `u` to let ccspy suggest new rules from your uncategorised sessions.

**Default categories:** debug · feature-build · design · planning · refactor · test · review · docs · setup · data-model · performance · security · devops · question

**Example rule:**

```toml
[[rule]]
category = "debug"
match_any = ["fix", "bug", "broken", "error", "crash", "not working"]
```

Matching is case-insensitive substring against the first user message of each session.

---

## Money figures

All dollar amounts are labelled **api-equiv**. If you're on Claude Pro, Max, or a Codex subscription (flat-rate plans), these numbers are *not* your actual bill — they represent what the same token usage would cost on the pay-as-you-go API. Useful for understanding relative cost across projects and models.

Pricing is bundled with the package and updated manually. Run `: → Pricing table` in the command palette to see current rates.

---

## Non-standard data locations

If your Claude Code or Codex data is not in the default location (WSL, custom install, multiple accounts), set the appropriate env var before running ccspy.

**macOS / Linux**

```bash
export CLAUDE_HOME="/mnt/c/Users/yourname/.claude"   # e.g. WSL accessing Windows files
export CODEX_HOME="/path/to/your/.codex"
ccspy
```

Add to `~/.zshrc` or `~/.bashrc` to make permanent.

**Windows (PowerShell)**

```powershell
$env:CLAUDE_HOME = "$env:APPDATA\Claude"    # if using the Claude desktop app
$env:CODEX_HOME  = "D:\custom\.codex"       # if Codex is on another drive
ccspy
```

To set permanently (no admin required):

```powershell
[System.Environment]::SetEnvironmentVariable("CLAUDE_HOME", "$env:APPDATA\Claude", "User")
```

---

## Cache

The SQLite cache (`~/.config/ccspy/cache.db` on macOS/Linux, `%APPDATA%\ccspy\cache.db` on Windows) tracks file mtimes and byte offsets for incremental parsing — only new content is re-read on each sync. The `r` key triggers a sync without a full rebuild.

To start fresh:

```bash
ccspy cache rebuild
```

---

## Data locations

**macOS / Linux**

| Purpose | Path |
|---------|------|
| Claude Code transcripts | `~/.claude/projects/**/*.jsonl` |
| Codex CLI transcripts | `~/.codex/sessions/**/*.jsonl` |
| ccspy cache | `~/.config/ccspy/cache.db` |
| Category rules | `~/.config/ccspy/categories.toml` |
| Logs | `~/.config/ccspy/ccspy.log` |

**Windows**

| Purpose | Path |
|---------|------|
| Claude Code CLI transcripts | `%USERPROFILE%\.claude\projects\**\*.jsonl` |
| Claude desktop app transcripts | `%APPDATA%\Claude\projects\**\*.jsonl` |
| Codex CLI transcripts | `%USERPROFILE%\.codex\sessions\**\*.jsonl` |
| ccspy cache | `%APPDATA%\ccspy\cache.db` |
| Category rules | `%APPDATA%\ccspy\categories.toml` |
| Logs | `%APPDATA%\ccspy\ccspy.log` |

ccspy never writes to Claude or Codex data directories.

---

## License

MIT — see [LICENSE](LICENSE).
