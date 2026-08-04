# Implementation Plan: Menu Bar Usage Display

**Branch**: `001-menubar-usage-display` | **Date**: 2026-08-04 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/001-menubar-usage-display/spec.md`

## Summary

A macOS menu bar app that reads Claude Code's local session logs and shows
token usage in a dropdown, refreshed on a 60-second timer. Two modules enforce
the constitution's pure-core/thin-UI split: `usage_parser.py` (stdlib only,
no `rumps`) locates and parses `~/.claude/projects/**/*.jsonl`, deduplicates
assistant turns, and aggregates them into windowed totals; `menubar_app.py`
is a thin `rumps.App` that renders whatever the parser returns.

Phase 0 research against live data drove two decisions that shape the build:

1. **Deduplication by `message.id` is mandatory.** Claude Code writes one line
   per content block, each repeating the same turn-level usage. Naive summing
   inflates totals by **2.10×** on the reference corpus.
2. **Quota percentages are not derivable locally.** No rate-limit, quota, or
   reset field exists anywhere in the logs, so FR-007 was narrowed to raw token
   counts rather than adding the network call the constitution forbids.

## Technical Context

**Language/Version**: Python 3.11+ (needs `datetime.fromisoformat` `Z` support; 3.14.6 on the dev machine)

**Primary Dependencies**: `rumps` (UI only). Core uses stdlib exclusively — `json`, `pathlib`, `datetime`, `dataclasses`, `collections`

**Storage**: None. Every refresh recomputes from `~/.claude/projects/**/*.jsonl` (FR-011)

**Testing**: `pytest` over checked-in fixture `.jsonl` files; `ruff` for lint. Both gated by a hook (Constitution III)

**Target Platform**: macOS only (FR-012)

**Project Type**: Single-project desktop utility — status bar app, no window, no Dock icon

**Performance Goals**: Full refresh under 500 ms. Measured: **45 ms** for 4,006 lines / 11 MB / 8 files

**Constraints**: Zero network calls; zero authentication; no persistence; no packaging or code signing; refresh must not block the menu bar

**Scale/Scope**: Two source modules plus tests. Reference corpus 8 files / 11 MB / 1,669 raw entries → 783 unique turns / 7 sessions. Design headroom to ~10× before threading is warranted

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Gate | Pre-Phase 0 | Post-Phase 1 |
|-----------|------|-------------|--------------|
| I. Minimal, justified stack | Python 3.11+; `rumps` the only UI dep; nothing new without stdlib justification | PASS | **PASS** — deps are `rumps` + stdlib. `watchdog` was considered for file watching and rejected (R9); `pytest`/`ruff` are dev-only and mandated by III |
| II. Pure core, thin UI | Parsing/aggregation in a module free of `rumps`; UI only consumes it | PASS | **PASS** — `usage_parser.py` imports no UI module; contract forbids it and quickstart V1 tests it. All arithmetic lives in the core; `menubar_app.py` only reads fields and formats |
| III. Quality enforced, not suggested | Lint + tests enforced by a hook, not convention | PASS | **PASS** — `pytest` + `ruff` wired to a pre-commit hook as a setup task; `aggregate()` is pure with injected `now`, so time-dependent logic is deterministically testable |
| IV. No polished distribution for MVP | Clone + venv + pip only | PASS | **PASS** — install is `venv` + `pip install -r requirements.txt`. No py2app, signing, Homebrew, or LaunchAgent anywhere in scope |
| V. Simplicity over generality | Reject complexity serving hypothetical needs | PASS | **PASS** — synchronous refresh (no threading) justified by the 45 ms measurement; no incremental-parse cache; no config file; no plugin/data-source abstraction |
| Technical constraints | macOS only; local `.jsonl` only; no persistence | PASS | **PASS** — no network call exists in the design (quickstart V7 asserts it). The FR-007 quota conflict was resolved *by narrowing the requirement*, per the Governance clause, not by relaxing the constraint |

**Result**: All gates pass in both evaluations. Complexity Tracking is empty —
no violations required justification.

## Project Structure

### Documentation (this feature)

```text
specs/001-menubar-usage-display/
├── plan.md              # This file (/speckit-plan command output)
├── spec.md              # Feature specification (FR-007 + SC-002 amended in Phase 0)
├── research.md          # Phase 0 output — 11 decisions, empirically grounded
├── data-model.md        # Phase 1 output — UsageEntry, UsageSummary, TokenTotals
├── quickstart.md        # Phase 1 output — install + 8 validation scenarios
├── contracts/
│   └── usage_parser.md  # Phase 1 output — public core interface
├── checklists/
│   └── requirements.md  # Spec quality checklist
└── tasks.md             # Phase 2 output (/speckit-tasks — NOT created here)
```

### Source Code (repository root)

```text
claude-usage-menubar/
├── usage_parser.py          # Pure core: discovery, parsing, dedup, aggregation
├── menubar_app.py           # Thin rumps.App: icon, dropdown, 60s timer
├── tests/
│   ├── test_usage_parser.py # Unit tests over the core
│   └── fixtures/            # Small .jsonl files: normal, duplicate message.id,
│                            # malformed, empty, multi-day, multi-session,
│                            # synthetic-model, timezone-boundary
├── requirements.txt         # rumps (+ pytest, ruff for dev)
├── README.md                # Install + run instructions (SC-001)
└── LICENSE
```

**Structure Decision**: Flat two-module layout at the repository root, exactly
as proposed in the plan input. A `src/` package adds no value at this size and
would contradict Principle V. The split is not cosmetic — it is the physical
enforcement of Principle II, and quickstart V1 verifies the core imports with
`rumps` absent.

### Module responsibilities

**`usage_parser.py`** — public surface per [`contracts/usage_parser.md`](contracts/usage_parser.md):
`DEFAULT_LOG_ROOT`, `parse_entries()`, `aggregate()`, `get_summary()`,
`format_tokens()`, plus the `UsageEntry` / `UsageSummary` / `TokenTotals`
dataclasses. Never raises, never caches, never opens a socket.

**`menubar_app.py`** — a `rumps.App` with a static icon, a dropdown listing
Today / Current session / Last 5 hours / All time, a manual Refresh item, and
Quit. Calls `get_summary()` once at startup and on each `rumps.Timer` tick.
Contains no arithmetic beyond delegating to `format_tokens()`.

## Phase 0 — Research (complete)

Full findings in [`research.md`](research.md). Eleven decisions, all validated
against the live corpus rather than assumed:

| ID | Decision |
|----|----------|
| R1 | Parse only `type == "assistant"`; usage lives in `message.usage` |
| R2 | **Deduplicate by `message.id`** — 1,669 entries → 783 unique; 2.10× inflation otherwise |
| R3 | **No quota/reset data exists locally** — FR-007 narrowed to raw counts |
| R4 | Convert UTC timestamps to local time before day-bucketing |
| R5 | "Current session" = `sessionId` holding the latest timestamp (not file mtime) |
| R6 | Add a rolling 5-hour window for recent activity |
| R7 | Skip malformed lines with a counter; read with `errors="replace"` |
| R8 | Exclude `<synthetic>` model entries; include sidechain entries |
| R9 | Synchronous refresh, no cache — 45 ms measured, 500 ms budget |
| R10 | `rumps.Timer` at 60 s, plus an immediate refresh at startup |
| R11 | `pytest` over fixture files; no UI tests in the MVP |

## Phase 1 — Design (complete)

- [`data-model.md`](data-model.md) — `UsageEntry` and `UsageSummary` field
  maps, validation rules, the deduplication invariant, and the empty/degraded
  state matrix.
- [`contracts/usage_parser.md`](contracts/usage_parser.md) — the core's public
  interface and the four module invariants (no UI import, never raises, no
  cache, no network), plus the UI-side constraints on `menubar_app`.
- [`quickstart.md`](quickstart.md) — install steps and eight runnable
  validation scenarios, including V1 (core imports without `rumps`) and V3 (a
  reference script the app's all-time total must match, which is the
  deduplication regression guard).

### Spec amendments made during this phase

Phase 0 evidence forced two spec edits, both recorded in `research.md` R3 and
confirmed with the project owner:

- **FR-007** — dropped percentage-of-quota and reset timing; now raw token
  counts across today / current session / rolling window.
- **SC-002** — parity claim scoped to token counts, with an explicit
  "counted exactly once" clause; quota parity marked out of scope.

An assumption covering `<synthetic>` exclusion and sidechain inclusion was also
added.

## Complexity Tracking

No Constitution Check violations. Nothing to justify.
