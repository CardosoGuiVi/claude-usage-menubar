# claude-usage-menubar

A macOS menu bar app that shows your Claude Code token usage — Today,
Current Session, Last 5 Hours, and All Time — computed entirely from your
local session logs, with no network calls.

## Prerequisites

- macOS (the only supported platform)
- Python 3.11 or newer

## Install

```bash
git clone <repo-url> claude-usage-menubar
cd claude-usage-menubar
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

That's it — no code signing, no `.app` bundle, no Homebrew step.

## Run

```bash
python menubar_app.py
```

An icon appears in the macOS menu bar. Click it to see the usage breakdown,
and quit the app from the dropdown's **Quit** item.

## What the numbers mean

The app reads your Claude Code session logs under `~/.claude/projects/` and
sums the token usage recorded on each assistant turn (deduplicated, since
Claude Code writes the same turn's usage on more than one line):

- **Today** — total tokens used since local midnight.
- **Current Session** — total tokens used in your most recently active
  Claude Code session.
- **Last 5 Hours** — a rolling total over the last 5 hours, mirroring the
  session-window granularity Claude Code itself uses.
- **All Time** — total tokens across every local session log found.

### Why isn't there a percentage-of-quota figure?

Because it can't be computed truthfully from what's on disk. Your plan's
quota and its reset time live on Anthropic's servers, not in your local
session logs — there is nothing in those files that identifies a limit or a
reset countdown. Showing a number would mean either calling an authenticated
API (which this app deliberately never does) or guessing at a limit, which
would just be misleading. So this app shows exactly what it can back up:
real, local token counts, and nothing more.

## Contributing

```bash
pip install -r requirements-dev.txt   # pytest, ruff — needed only for tests/lint
pytest -q
ruff check .
```

Both must pass before a change is merged. `.github/workflows/ci.yml` is the
authoritative gate and runs these on every push and pull request. There is
also an optional local pre-commit convenience hook — see
[`scripts/pre-commit`](scripts/pre-commit) for how to enable it with
`git config core.hooksPath scripts` — but it's purely for fast local
feedback and is never a substitute for CI passing.
