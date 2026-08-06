# Contract: `usage_parser` public interface

**Feature**: `001-menubar-usage-display` | **Date**: 2026-08-04

This is the boundary the constitution's Principle II ("Pure Core, Thin UI")
draws. `usage_parser` is importable and fully exercisable **without `rumps`
installed**; `menubar_app` consumes only the surface below and adds no
aggregation logic of its own.

---

## Module invariants

1. `usage_parser` MUST NOT import `rumps` or any UI module.
2. No function in this module raises on malformed, missing, or unreadable
   input — degraded input yields zero-valued results and a `skipped_lines`
   count (FR-008, FR-009).
3. No function writes to disk or caches between calls (FR-011).
4. No function opens a network connection (FR-004).

---

## `DEFAULT_LOG_ROOT: Path`

Module constant: `Path.home() / ".claude" / "projects"`. Exposed so tests can
substitute a fixture directory without monkey-patching `Path.home`.

---

## `parse_entries(log_root: Path = DEFAULT_LOG_ROOT) -> tuple[list[UsageEntry], int]`

Scan `log_root` recursively for `*.jsonl`, parse every line, and return
`(deduplicated_entries, skipped_line_count)`.

**Behavior**

- Discovers files via a recursive glob equivalent to `log_root/**/*.jsonl`.
- Opens files with `errors="replace"` to survive partially written UTF-8.
- Applies the `UsageEntry` validation rules from `data-model.md`.
- Deduplicates by `message_id`, first occurrence wins, **across all files**
  (not per-file — the same turn can appear in more than one file).
- Returns entries in no guaranteed order; callers must not depend on ordering.

**Guarantees**

| Input condition | Return |
|-----------------|--------|
| `log_root` does not exist | `([], 0)` |
| `log_root` unreadable (permissions) | `([], 0)` |
| No `.jsonl` files present | `([], 0)` |
| A file is unreadable mid-scan | That file contributes nothing; scan continues |
| Every line malformed | `([], <count of bad lines>)` |

Never raises.

---

## `aggregate(entries: list[UsageEntry], now: datetime) -> UsageSummary`

Pure function. Collapses entries into the windowed summary described in
`data-model.md`.

**Contract**

- MUST NOT perform file I/O, and MUST NOT call `datetime.now()` internally —
  `now` is injected so time-dependent behavior is deterministic under test.
- `now` MUST be timezone-aware; a naive value is treated as system-local.
- Called with `[]`, returns an all-zero `UsageSummary` with
  `current_session_id is None` and `last_activity is None`.
- Bucketing rules (today / current session / rolling 5h) are exactly as
  specified in `data-model.md`.

---

## `get_summary(log_root: Path = DEFAULT_LOG_ROOT, now: datetime | None = None) -> UsageSummary`

Convenience composition — `parse_entries` then `aggregate` — and the single
function `menubar_app` is expected to call. When `now` is `None` it defaults to
the current local time. Propagates `skipped_lines` from `parse_entries` onto
the returned summary. Never raises.

---

## `format_tokens(n: int) -> str`

Render a token count compactly for menu display: `1234` → `1.2K`,
`57836773` → `57.8M`, values under 1000 unchanged. Pure, no side effects.
Lives in the core so its behavior is unit-testable, even though only the UI
consumes it.

---

## UI-side contract (`menubar_app`)

Not a code API, but the constraints the thin shell must honor:

- Calls `get_summary()` on a `rumps.Timer` tick (5 min / 300 s) and once at
  startup.
- Performs **no** parsing, bucketing, or arithmetic on token values — it only
  reads fields off `UsageSummary` and passes them to `format_tokens`.
- Renders a static menu bar icon; all figures live in the dropdown
  (spec assumption).
- Provides a manual "Refresh" item and a "Quit" item.
- Shows an explicit empty state when `entry_count == 0` rather than a blank
  menu.
