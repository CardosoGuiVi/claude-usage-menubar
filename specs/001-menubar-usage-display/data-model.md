# Phase 1 Data Model: Menu Bar Usage Display

**Feature**: `001-menubar-usage-display` | **Date**: 2026-08-04

Two dataclasses, both defined in `usage_parser.py`, both plain data with no
`rumps` import and no file I/O of their own. Field names mirror the source
JSON where practical so the mapping stays auditable (Constitution II).

---

## Entity: `UsageEntry`

One deduplicated assistant turn extracted from a session log. Maps to spec's
**Usage Session** contributor.

| Field | Type | Source | Notes |
|-------|------|--------|-------|
| `message_id` | `str` | `message.id` | Deduplication key; unique per turn |
| `session_id` | `str` | `sessionId` | Groups entries into a session |
| `timestamp` | `datetime` | `timestamp` | Parsed from UTC, tz-aware |
| `model` | `str` | `message.model` | e.g. `claude-sonnet-5` |
| `input_tokens` | `int` | `message.usage.input_tokens` | Uncached input |
| `output_tokens` | `int` | `message.usage.output_tokens` | Generated |
| `cache_read_tokens` | `int` | `message.usage.cache_read_input_tokens` | Served from cache |
| `cache_creation_tokens` | `int` | `message.usage.cache_creation_input_tokens` | Written to cache |

**Derived property**: `total_tokens` = sum of the four token fields.

### Validation rules

- A line is skipped entirely (counted as `skipped_lines`) if: it is not valid
  JSON, `type != "assistant"`, `message.id` is absent, `message.usage` is
  absent, or `timestamp` is absent or unparseable.
- Entries with `model == "<synthetic>"` are excluded — locally generated
  placeholders, not real API turns (research R8).
- Sidechain (subagent) entries **are** included; they consume real tokens.
- Missing individual token fields default to `0` rather than failing the entry.
- Negative token values are treated as `0` (defensive; not observed in practice).

### Deduplication invariant

**The most important rule in this feature.** Within a single parse run, the
first entry seen for a given `message_id` wins; all later occurrences are
discarded. Claude Code writes one line per content block in an assistant turn,
each repeating identical turn-level usage. On the reference corpus this
collapses 1,669 raw entries to 783 unique turns — without it, totals inflate
by **2.10×** (research R2).

---

## Entity: `UsageSummary`

The aggregated, point-in-time view rendered in the dropdown. Maps to spec's
**Usage Snapshot**. Recomputed from scratch on every refresh; never persisted
(FR-011).

| Field | Type | Meaning |
|-------|------|---------|
| `today` | `TokenTotals` | Entries whose local-time date is today |
| `current_session` | `TokenTotals` | Entries in the most recently active `session_id` |
| `rolling_5h` | `TokenTotals` | Entries with `timestamp >= now - 5h` |
| `all_time` | `TokenTotals` | Every included entry |
| `current_session_id` | `str \| None` | `None` when no data exists |
| `last_activity` | `datetime \| None` | Latest entry timestamp; `None` when empty |
| `entry_count` | `int` | Deduplicated entries counted |
| `skipped_lines` | `int` | Lines rejected by the validation rules above |

### Nested value: `TokenTotals`

`input`, `output`, `cache_read`, `cache_creation` (all `int`), plus a derived
`total`. A zero-valued instance is the empty state — never `None` — so the UI
can render "0 tokens" without null checks (FR-008).

### Aggregation rules

- **"Today"** is bucketed by local system timezone: each UTC timestamp is
  converted via `.astimezone()` before its date is compared to `date.today()`
  (research R4).
- **"Current session"** is the `session_id` owning the single latest timestamp
  across all projects — not the most recently modified file (research R5).
- **Rolling 5h** is computed against the wall clock at aggregation time, so it
  shifts continuously between refreshes (research R6).
- Aggregation is a **pure function**: `aggregate(entries, now) -> UsageSummary`.
  It performs no file I/O and takes `now` as a parameter, which makes every
  time-dependent rule testable with in-memory fixtures and a frozen clock.

### State transitions

None. There is no persisted state machine — each refresh produces a fresh
`UsageSummary` that fully replaces the previous one.

---

## Empty and degraded states

| Condition | Result |
|-----------|--------|
| `~/.claude/projects/` missing or unreadable | All-zero `UsageSummary`, `entry_count == 0` |
| Directory exists but holds no `.jsonl` files | All-zero `UsageSummary` |
| Files exist but every line is malformed | All-zero summary, `skipped_lines > 0` |
| No entries dated today | `today` is zero-valued; other windows still populate |

In every case the parser returns a valid `UsageSummary` and raises nothing, so
the UI layer never needs exception handling (FR-008, FR-009).
