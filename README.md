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
Claude Code writes the same turn's usage on more than one line), broken down
into four time buckets:

- **Today** — total tokens used since local midnight.
- **Current Session** — total tokens used in your most recently active
  Claude Code session.
- **Last 5 Hours** — a rolling total over the last 5 hours, mirroring the
  session-window granularity Claude Code itself uses.
- **All Time** — total tokens across every local session log found.

Each bucket's dropdown row shows its combined total, and opening it as a
submenu reveals the same total split into **Input**, **Output**, **Cache
Read**, and **Cache Creation** token counts.

If it's available, the dropdown also shows two more rows — **Session
Usage** and **Week Usage** — with the percentage-used figures Claude Code's
own `/usage` command reports. See below for where those come from and what
happens when they aren't available.

### Where do the token counts and the percentages each come from?

The raw token counts above (Today, Current Session, Last 5 Hours, All Time)
are computed entirely from your local session logs under
`~/.claude/projects/` — nothing is guessed, and no network request is
involved. Your plan's quota and its reset time live on Anthropic's servers,
not in those local logs, so this app never derives a percentage-of-quota
figure from them itself.

The **Session Usage** / **Week Usage** rows are different: they're read
directly from Claude Code's own `/usage` output, by running the `claude`
CLI you already have installed (`claude -p "/usage" --output-format json`)
as a local subprocess and parsing the percentages it reports. This is not a
network call this app makes — it's asking a binary already on your machine
to report a number it already computed, the same way running `/usage`
yourself in a Claude Code session would. This app never opens a network
socket and never reads or stores an API key or any other credential.

Because that subprocess call depends on Claude Code's own text output — not
a stable, documented data format — it's treated as a best-effort
enhancement. If the `claude` binary isn't installed, isn't on your `PATH`,
or its output can't be parsed (including if a future Claude Code update
changes its wording), the two percentage rows are simply omitted and
everything else — the token totals above — keeps working exactly as
before, with no error and no crash.

## Optional: Launchpad shortcut

Everything above (clone + venv + `pip install` + `python menubar_app.py`) is
the actual supported way to install and run this app — the steps below are
entirely optional and skippable. They just wrap the app you've already
cloned and installed so it also shows up in Launchpad and Spotlight like a
regular app. This is **not** a packaged distributable: it doesn't bundle a
Python interpreter or its dependencies, and it isn't code-signed, so it
only works on the machine (and clone) it was built from.

1. Open **Automator** (Applications > Automator, or search for it in
   Spotlight).
2. Choose **New Document**, then pick **Application** as the document
   type.
3. Search the actions library for **Run Shell Script** and drag it into
   the workflow.
4. Set the shell to `/bin/zsh` (or `/bin/bash`), leave "Pass input" as
   whatever the default is (nothing here reads from stdin), and paste in:

   ```bash
   cd "/absolute/path/to/claude-usage-menubar" && exec .venv/bin/python3 menubar_app.py
   ```

   Replace `/absolute/path/to/claude-usage-menubar` with the actual path
   to your own clone. The `cd` isn't cosmetic — `menubar_app.py` loads
   `icon.png` via a relative path, so the working directory has to be the
   project root or the icon won't load. Calling `.venv/bin/python3`
   directly (rather than `source .venv/bin/activate`, which doesn't behave
   the same way inside a Shell Script action) is what makes it use the
   project's installed dependencies without needing an active shell
   session.
5. Save (Cmd+S) with a name like "Claude Usage Menubar.app", to
   `/Applications` or `~/Applications`.
6. It now appears in Launchpad and Spotlight like any other app. Launching
   it just runs the same `menubar_app.py` clone on disk — there's nothing
   else to keep in sync, as long as that file still exists at the path in
   the script.

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
