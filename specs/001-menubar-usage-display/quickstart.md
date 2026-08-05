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

### V2 — Dropdown shows the required breakdowns, and no Dock presence (FR-002, FR-003, FR-007)

Run the app and click the menu bar icon.

**Expected**: the dropdown lists **Today**, **Current session**, **Last 5
hours**, and **All time**, each with a token count. No percentage-of-quota and
no reset countdown appear anywhere — those were removed by the FR-007
amendment (see `research.md` R3). Additionally, confirm no icon appears in the
Dock and no entry appears when cycling with Cmd+Tab — the app must behave as a
menu-bar-only accessory process, per FR-002.

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
pip install -r requirements-dev.txt   # pytest, ruff (contributors only)
pytest -q          # unit tests over tests/fixtures/*.jsonl
ruff check .       # lint
```

Both must pass; `.github/workflows/ci.yml` enforces this on every push/PR as
the authoritative Constitution Principle III gate, not left to convention —
the local `scripts/pre-commit` hook is an optional convenience only. Fixture
coverage is enumerated in `research.md` R11 — the duplicate-`message_id`
fixture is the regression guard for V3.

---

## Validation Results (T023)

**Date**: 2026-08-04 · **Environment**: real `~/.claude/projects/` session
logs on the dev checkout (V4/V5 used temporary directories as documented in
their scenarios above; V6 used a monkeypatched `usage_parser.get_summary`
pointed at a controlled temp directory with a directly-invoked timer
callback, per the T019 precedent, rather than a literal 60 s wait on real
new usage). All scenarios run end-to-end in a single consolidated pass
against the final state of the codebase (`usage_parser.py`, `menubar_app.py`
as they stand after T001–T022).

| ID | Scenario | Result | Evidence |
|----|----------|--------|----------|
| V1 | Core importable without `rumps` (Constitution II) | PASS | `python3 -c "import usage_parser; print(usage_parser.get_summary().entry_count)"` run under a system Python with no `rumps` installed → printed `1789`, exit 0, no `ImportError` |
| V2 | Dropdown breakdowns + no Dock/Cmd+Tab presence | PASS | App launched (`menubar_app.py`); `osascript`/System Events confirmed the running "Python" process has `background only: true` (no Dock icon, no Cmd+Tab entry). Live `UsageMenuBarApp` instance's menu items read: `'Today: 112.6M'`, `'Current Session: 51.1M'`, `'Last 5 Hours: 30.4M'`, `'All Time: 184.7M'`, `'No usage data found'` (hidden), `'Refresh'` — all four required breakdowns present; `grep -i "quota\|percent\|%"` over `menubar_app.py`/`usage_parser.py` returned no matches, confirming no quota/percentage/reset UI exists |
| V3 | Deduplication correctness (SC-002) | PASS | Reference dedup script and `usage_parser.get_summary()` run back-to-back in one process against the same live corpus: `deduplicated: 184,824,396` == `app all_time: 184,824,396` (`1,800` unique turns matched `entry_count: 1,800`); naive (non-deduplicated) total in the same run was `~2x` larger, confirming dedup is active and correct |
| V4 | Empty state does not crash (FR-008) | PASS | `usage_parser.get_summary(Path('/tmp/definitely-not-here'))` → printed `0 0 None`, exit 0, no traceback |
| V5 | Malformed input survivable (FR-009) | PASS | 3-line file (`not json` / valid-but-incomplete / truncated JSON) under `/tmp/ct/proj/s.jsonl` → `entries: 0 skipped: 3`, exit 0, no traceback |
| V6 | Auto-refresh reflects new usage, no drift when idle (FR-006, SC-003) | PASS | Adapted per T019: monkeypatched `usage_parser.get_summary` to a controlled temp dir, instantiated `UsageMenuBarApp`, stopped the real 60 s timer, and invoked `_on_timer(None)` directly. No-op tick: `Today`/`Last 5 Hours` titles unchanged (`'Today: 150'` both before and after). After appending a new usage line to the temp `.jsonl` and invoking `_on_timer(None)` again: titles changed to `'Today: 1.4K'` / `'Last 5 Hours: 1.4K'` — increase confirmed with no user action |
| V7 | No network traffic (FR-004, SC-005) | PASS | `socket.socket = None` sabotage, then `usage_parser.get_summary().entry_count` → printed `1811`, exit 0, no traceback |
| V8 | Refresh stays fast (research R9) | PASS | Three consecutive timed runs of `usage_parser.get_summary()` on the live corpus (~1,800+ entries across 61 `.jsonl` files): `72 ms`, `71 ms`, `71 ms` — well under the 500 ms budget |

**Summary**: 8/8 PASS. `pytest -q` (13 tests, after the FR-007 breakdown fix added tests/test_menubar_app.py) also re-confirmed green before
and after this pass. No discrepancies found; no code changes were required
by this validation run. Minor observed non-determinism in V3's exact token
counts across *separate* invocations (e.g. `184,766,513` vs. `184,824,396`
vs. `184,795,365` in earlier isolated runs) is expected and benign: this
validation was itself run from an active Claude Code session, which
continuously appends new entries to `~/.claude/projects/` while the checks
execute — the authoritative V3 comparison above was taken from both sides
computed within a single process invocation to eliminate that skew.

---

## Constitution II Audit (T025)

**Date**: 2026-08-04. Line-by-line audit of the final `menubar_app.py`
(post-T013–T018) against Constitution Principle II ("pure core / thin UI" —
`menubar_app.py` may read and format `usage_parser` output, but must
perform no parsing, bucketing, or arithmetic of its own).

| Check | Method | Result |
|---|---|---|
| No `+`/`-`/`*`/`/` applied to token counts | `grep -nE '[a-zA-Z_\.]+ *[+\-*/] *[a-zA-Z0-9_\.]+' menubar_app.py` | Only matches were prose inside comments/docstrings (e.g. "Last 5 Hours", "60 s timer", "T018"); zero arithmetic operators applied to any token/numeric identifier in executable code |
| No date/time bucketing logic | `grep -nE '\.date\(\)\|timedelta\|datetime\|astimezone\|tzinfo' menubar_app.py` | No matches — the file contains no `datetime` import and no time comparison of any kind |
| No file I/O | `grep -nE 'open\(\|glob\(\|json\.load\|Path\(' menubar_app.py` | No matches |
| No `import json` / direct file-reading imports | `grep -nE '^import\|^from' menubar_app.py` | Exactly three imports: `AppKit`, `rumps`, `usage_parser` — no `json`, no `pathlib` |
| Every displayed number traces to `usage_parser` | `grep -n "summary\.\|format_tokens(" menubar_app.py` | `summary` is assigned once, at `summary = usage_parser.get_summary()` (`_refresh()`). All four dropdown values are `usage_parser.format_tokens(summary.<bucket>.total)` for `<bucket>` in `today`, `current_session`, `rolling_5h`, `all_time` — `.total` is a `TokenTotals` property defined and summed in `usage_parser.py`, not in `menubar_app.py`. The only other field read is `summary.entry_count`, compared (not computed) against `0` to pick the empty-state branch (FR-008) |
| `usage_parser.py` doesn't import `rumps`/`AppKit` (cross-check of T012) | `grep -nE '^import\|^from' usage_parser.py` | `from __future__ import annotations`, `json`, `dataclasses`, `datetime`, `pathlib` — no `rumps`, no `AppKit` |

**Conclusion**: PASS. `menubar_app.py` performs no token arithmetic, no
date/time bucketing, and no file I/O; every number it displays is a direct
field/property read off the `UsageSummary`/`TokenTotals` returned by
`usage_parser.get_summary()`, passed through `usage_parser.format_tokens()`.
The pure-core/thin-UI split (Constitution Principle II) holds in both
directions: `menubar_app.py` imports only `AppKit`, `rumps`, and
`usage_parser`, and `usage_parser.py` imports neither `rumps` nor `AppKit`.
No code changes were required by this audit.

`pytest -q` (13 tests, after the FR-007 breakdown fix added tests/test_menubar_app.py) and `ruff check .` both re-confirmed green as part of
this final task.
