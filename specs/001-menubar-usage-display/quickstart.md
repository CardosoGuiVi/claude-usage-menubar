# Quickstart & Validation: Menu Bar Usage Display

**Feature**: `001-menubar-usage-display` | **Date**: 2026-08-04

How to install, run, and prove this feature works. Interface details live in
[`contracts/usage_parser.md`](contracts/usage_parser.md); field semantics live
in [`data-model.md`](data-model.md).

---

## Prerequisites

- macOS (the only supported platform — FR-012)
- Python 3.11 or newer (`datetime.fromisoformat` must accept a `Z` suffix)
- Some existing Claude Code usage under `~/.claude/projects/` — optional; with
  none, the app must still start and show a zero state

---

## Install

```bash
git clone <repo-url> claude-usage-menubar
cd claude-usage-menubar
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

No code signing, no `.app` bundle, no Homebrew step — that is the whole
install (FR-010).

## Run

```bash
python menubar_app.py
```

An icon appears in the macOS menu bar. Quit from the dropdown's **Quit** item.

---

## Validation scenarios

### V1 — Core is importable without the UI dependency (Constitution II)

The single most important structural check. In an environment where `rumps` is
**not** installed:

```bash
python -c "import usage_parser; print(usage_parser.get_summary().entry_count)"
```

**Expected**: prints an integer without an `ImportError`. If this fails, the
pure-core/thin-UI separation has been violated.

### V2 — Dropdown shows the required breakdowns (FR-003, FR-007)

Run the app and click the menu bar icon.

**Expected**: the dropdown lists **Today**, **Current session**, **Last 5
hours**, and **All time**, each with a token count. No percentage-of-quota and
no reset countdown appear anywhere — those were removed by the FR-007
amendment (see `research.md` R3).

### V3 — Deduplication is correct (SC-002, research R2)

The highest-risk correctness property. Compare the app's all-time total against
a deduplicating reference count over the same files:

```bash
python - <<'PY'
import json, glob, pathlib
seen, dedup, naive = set(), 0, 0
root = pathlib.Path.home() / ".claude" / "projects"
for fn in root.glob("**/*.jsonl"):
    for line in open(fn, errors="replace"):
        try: o = json.loads(line)
        except Exception: continue
        if o.get("type") != "assistant": continue
        m = o.get("message", {}); u = m.get("usage") or {}
        if m.get("model") == "<synthetic>": continue
        t = sum(u.get(k, 0) or 0 for k in
                ("input_tokens", "output_tokens",
                 "cache_read_input_tokens", "cache_creation_input_tokens"))
        naive += t
        if m.get("id") in seen: continue
        seen.add(m.get("id")); dedup += t
print(f"unique turns : {len(seen):,}")
print(f"deduplicated : {dedup:,}   <-- app must match this")
print(f"naive (wrong): {naive:,}   ({naive/max(dedup,1):.2f}x inflated)")
PY
```

**Expected**: the app's **All time** figure equals the `deduplicated` value. On
the reference corpus the naive figure was 2.10× larger — if the app matches
*that* instead, deduplication is broken.

### V4 — Empty state does not crash (FR-008, SC-004)

```bash
python -c "
import pathlib, usage_parser as u
s = u.get_summary(pathlib.Path('/tmp/definitely-not-here'))
print(s.entry_count, s.today.total, s.current_session_id)
"
```

**Expected**: prints `0 0 None`. No traceback.

### V5 — Malformed input is survivable (FR-009)

```bash
mkdir -p /tmp/ct/proj && printf 'not json\n{"type":"assistant"}\n{"broken":\n' > /tmp/ct/proj/s.jsonl
python -c "
import pathlib, usage_parser as u
s = u.get_summary(pathlib.Path('/tmp/ct'))
print('entries:', s.entry_count, 'skipped:', s.skipped_lines)
"
```

**Expected**: `entries: 0 skipped: 3`. No traceback. This also mimics a torn
final line from Claude Code writing concurrently.

### V6 — Auto-refresh reflects new usage (FR-006, SC-003)

With the app running, note the **Today** figure, then run a Claude Code session
that consumes tokens. Wait up to 60 seconds and reopen the dropdown.

**Expected**: **Today** and **Last 5 hours** have increased without any manual
action. Reopening again with no further activity leaves the numbers unchanged
(no spurious drift).

### V7 — No network traffic (FR-004, SC-005)

```bash
python -c "
import socket; socket.socket = None
import usage_parser; print(usage_parser.get_summary().entry_count)
"
```

**Expected**: prints a count. Sabotaging sockets cannot break a module that
never opens one.

### V8 — Refresh stays fast (research R9)

```bash
python -c "
import time, usage_parser
t = time.perf_counter(); usage_parser.get_summary()
print(f'{(time.perf_counter()-t)*1000:.0f} ms')
"
```

**Expected**: well under 500 ms (45 ms on the reference corpus). Exceeding the
budget is the documented trigger for moving the scan off the main thread.

---

## Test suite

```bash
pytest -q          # unit tests over tests/fixtures/*.jsonl
ruff check .       # lint
```

Both must pass; Constitution Principle III requires this be enforced by a hook,
not left to convention. Fixture coverage is enumerated in `research.md` R11 —
the duplicate-`message_id` fixture is the regression guard for V3.
