# Tasks: Menu Bar Usage Display

**Input**: Design documents from `/specs/001-menubar-usage-display/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/usage_parser.md, quickstart.md

**Tests**: Included. Constitution Principle III ("Quality Enforced, Not Suggested") mandates automated tests, enforced by CI (`.github/workflows/ci.yml`), with an optional local pre-commit convenience (`core.hooksPath`) for fast local feedback, and research.md R11 specifies `pytest` over fixture files as the testing approach.

**Organization**: Tasks are grouped by user story (spec.md P1/P2/P3) so each can be implemented and demoed independently.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no unmet dependencies)
- **[Story]**: Maps the task to US1, US2, or US3 — omitted for Setup, Foundational, and Polish tasks
- File paths are exact and relative to the repository root

## Note on scope vs. the original task proposal

The user-provided task list included a research task ("Investigate Claude Code
session log format"). That investigation was already completed empirically
during `/speckit-plan` Phase 0 — `research.md` (R1–R11) documents the actual
field names, the deduplication requirement (2.10× inflation without it), and
the confirmed absence of quota/rate-limit data, all from live session logs.
No separate research task is generated here; implementation tasks below cite
the specific research findings they implement instead.

---

## Phase 1: Setup

**Purpose**: Project skeleton and quality tooling — no app logic yet.

- [x] T001 Create project structure at repository root: empty `usage_parser.py`, empty `menubar_app.py`, `tests/__init__.py`, and `tests/fixtures/` directory, per `plan.md` Project Structure
- [x] T002 [P] Create `requirements.txt` pinning only the runtime dependency `rumps`, and `requirements-dev.txt` pinning `pytest` and `ruff` for contributors, per `plan.md` Technical Context
- [x] T003 [P] Configure `pytest` and `ruff` in `pyproject.toml` (test discovery path `tests/`, ruff target Python 3.11+)
- [x] T004 [P] Add `scripts/pre-commit` shell script that runs `ruff check .` and `pytest -q`, failing non-zero on either failure, plus a one-line note in README setup on running `git config core.hooksPath scripts` — this is an optional local convenience for contributors who want fast feedback before pushing; it is **not** the Principle III enforcement mechanism (see T004a)
- [x] T004a [P] Add `.github/workflows/ci.yml` running `ruff check .` and `pytest -q` on every push and pull request — the authoritative enforcement mechanism for Constitution Principle III, since it runs regardless of any local developer action. Run the pytest step as `pytest -q || [ $? -eq 5 ]` with a comment explaining that exit code 5 ("no tests collected") is tolerated until the Foundational phase (T009+) adds the first tests, so CI isn't falsely red on early Setup-phase commits

**Checkpoint**: Repository has structure, dependencies, and an enforceable quality gate (CI, not just a local hook). No behavior yet.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: The pure core (`usage_parser.py`) that every user story depends on. Constitution Principle II requires this module to import no UI code and perform no UI I/O — verified in T012.

**⚠️ CRITICAL**: No user story work may begin until this phase is complete and its tests pass.

- [x] T005 Define `UsageEntry`, `TokenTotals`, and `UsageSummary` dataclasses in `usage_parser.py`, matching the field maps in `data-model.md` (including `DEFAULT_LOG_ROOT = Path.home() / ".claude" / "projects"`)
- [x] T006 Implement `parse_entries(log_root=DEFAULT_LOG_ROOT) -> tuple[list[UsageEntry], int]` in `usage_parser.py`: recursive `*.jsonl` discovery, line-by-line JSON parsing with `errors="replace"`, the validation rules from `data-model.md` (skip non-`assistant` types, missing `message.id`/`usage`/`timestamp`, exclude `<synthetic>` model, include sidechain entries), and deduplication by `message.id` — first occurrence wins, per `research.md` R1, R2, R7, R8. Never raises; returns `([], 0)` for a missing/unreadable/empty directory
- [x] T007 Implement `aggregate(entries, now) -> UsageSummary` in `usage_parser.py` as a pure function (no file I/O, no internal `datetime.now()` call): bucket into `today` (local-timezone date match), `current_session` (the `session_id` owning the latest timestamp), `rolling_5h` (`timestamp >= now - 5h`), and `all_time`, per `data-model.md` and `research.md` R4–R6. Returns an all-zero `UsageSummary` with `current_session_id is None` for an empty entry list
- [x] T008 Implement `get_summary(log_root=DEFAULT_LOG_ROOT, now=None) -> UsageSummary` (composes T006 + T007, defaults `now` to current local time, propagates `skipped_lines`) and `format_tokens(n: int) -> str` (compact `1.2K`/`57.8M` rendering) in `usage_parser.py`, per `contracts/usage_parser.md`
- [x] T009 [P] Create fixture `.jsonl` files in `tests/fixtures/`: `normal.jsonl` (a few valid assistant entries across 2+ sessions), `duplicate_message_id.jsonl` (one `message.id` repeated 3+ times with identical usage — the regression guard for the 2.10× dedup bug in `research.md` R2), `malformed.jsonl` (invalid JSON lines mixed with valid ones), `empty.jsonl` (zero bytes), `multi_day.jsonl` (entries spanning a local-midnight boundary), `synthetic_model.jsonl` (entries with `message.model == "<synthetic>"` that must be excluded)
- [x] T010 [P] [depends: T006, T009] Unit tests for `parse_entries()` in `tests/test_usage_parser.py`: dedup collapses `duplicate_message_id.jsonl` to one entry, malformed lines increment `skipped_lines` without raising, empty file yields no entries, synthetic-model entries are excluded, a missing directory returns `([], 0)`
- [x] T011 [P] [depends: T007, T009] Unit tests for `aggregate()` in `tests/test_usage_parser.py`: today/current-session/rolling-5h bucketing with an injected fixed `now`, empty-list input returns an all-zero summary with `current_session_id is None`, a UTC timestamp just before local midnight buckets into the correct local day
- [x] T012 [depends: T005-T008] Add a test in `tests/test_usage_parser.py` (or a documented manual check run in CI) asserting `usage_parser` imports successfully in an environment without `rumps` installed — the executable form of quickstart.md V1, verifying Constitution Principle II

**Checkpoint**: `usage_parser` is fully implemented, tested, and confirmed UI-independent. Run `pytest -q` — all foundational tests pass before proceeding.

---

## Phase 3: User Story 1 - Quick-Glance Usage Check (Priority: P1) 🎯 MVP

**Goal**: Clicking the menu bar icon shows a dropdown with correct, deduplicated token usage.

**Independent Test**: Launch the app against real local session logs, click the icon, confirm the dropdown's totals match a manual deduplicated count (quickstart.md V3).

### Implementation for User Story 1

- [x] T013 [US1] Create `menubar_app.py`: a `rumps.App` subclass with a static menu bar title/icon and a single "Quit" menu item, per `contracts/usage_parser.md` UI-side contract — no data wiring yet
- [x] T013a [US1] [depends: T013] Configure the `rumps.App` in `menubar_app.py` to run as an accessory app with no Dock icon (set the underlying `NSApplication`'s activation policy to accessory, the equivalent of `LSUIElement`), per FR-002
- [x] T014 [US1] [depends: T013] In `menubar_app.py`, call `usage_parser.get_summary()` and render its result into the dropdown as four line items — Today, Current Session, Last 5 Hours, All Time — each formatted with `format_tokens()`, per FR-003 and FR-007. Trigger this on app startup so the menu is populated before first click
- [x] T015 [US1] [depends: T014] In `menubar_app.py`, render an explicit "No usage data found" menu item when `summary.entry_count == 0`, instead of empty/blank rows, per FR-008
- [x] T016 [US1] [depends: T013a, T014, T015] Manually run quickstart.md scenarios V2 (required breakdowns, no quota %, and no Dock icon/Cmd+Tab entry) and V3 (dropdown's All Time figure matches the deduplicating reference script) against real local data; fix any discrepancy before proceeding

**Checkpoint**: User Story 1 is fully functional and independently demoable — this is the MVP.

---

## Phase 4: User Story 2 - Usage Stays Current Without Interaction (Priority: P2)

**Goal**: The dropdown's numbers update on their own as new usage accrues, with no manual refresh.

**Independent Test**: With the app running, generate new Claude Code usage, wait one interval, reopen the dropdown, confirm the numbers increased (quickstart.md V6).

### Implementation for User Story 2

- [ ] T017 [US2] [depends: T014] In `menubar_app.py`, add a `rumps.Timer` with a 60-second interval (per `research.md` R10) whose callback re-runs `usage_parser.get_summary()` and refreshes the same dropdown items built in T014
- [ ] T018 [US2] [depends: T017] Add a manual "Refresh" menu item above "Quit" in `menubar_app.py` that triggers the same refresh callback as the timer, for on-demand updates without waiting
- [ ] T019 [US2] [depends: T017] Manually run quickstart.md V6: confirm Today/Last 5 Hours increase within 60 seconds of new usage with no user action, and remain unchanged across a tick with no new activity

**Checkpoint**: User Stories 1 and 2 both work — usage is visible and stays current automatically.

---

## Phase 5: User Story 3 - Simple Clone-and-Run Setup (Priority: P3)

**Goal**: A new user can clone the repo and have the app running in the menu bar within a few minutes, using only the README.

**Independent Test**: On a clean checkout, follow only the README (venv + `pip install -r requirements.txt` + run) and confirm the icon appears (quickstart.md, Install/Run sections).

### Implementation for User Story 3

- [ ] T020 [P] [US3] Write `README.md`: prerequisites, install (`git clone`, `python3 -m venv .venv`, `source .venv/bin/activate`, `pip install -r requirements.txt` — runtime only), run (`python menubar_app.py`), a short explanation of what Today/Current Session/Last 5 Hours/All Time mean and why there's no percentage-of-quota figure (per FR-007's resolution in `research.md` R3), and a **Contributing** section noting `pip install -r requirements-dev.txt` plus `pytest -q` / `ruff check .` for anyone running tests or lint
- [ ] T021 [P] [US3] Add a `LICENSE` file (open-source distribution per the constitution's Project Purpose)
- [ ] T022 [US3] [depends: T020, T021] Manually run quickstart.md V4 (missing log directory), V5 (malformed input survivability), and the Install section end-to-end on a fresh clone; confirm no undocumented steps were needed, and re-confirm no Dock icon or Cmd+Tab entry appears on this fresh install

**Checkpoint**: All three user stories are independently functional. Feature is complete for MVP scope.

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Final verification across the whole feature, not tied to a single story.

- [ ] T023 [P] Run the full quickstart.md validation suite (V1–V8) end-to-end and record results
- [ ] T024 [P] Run `ruff check .` across `usage_parser.py`, `menubar_app.py`, and `tests/`; fix any findings
- [ ] T025 [depends: T023, T024] Audit `menubar_app.py` to confirm it contains no token arithmetic, bucketing, or file I/O of its own — every number displayed must trace to a `usage_parser` return value, per Constitution Principle II

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — start immediately
- **Foundational (Phase 2)**: Depends on Setup (needs `tests/fixtures/` from T001) — **BLOCKS all user stories**
- **User Story 1 (Phase 3)**: Depends on Foundational completion only
- **User Story 2 (Phase 4)**: Depends on Foundational **and** T014 from US1 (extends the same dropdown-building code the timer refreshes) — not independent of US1 at the code level, though it is independently *testable* once US1 exists
- **User Story 3 (Phase 5)**: Depends on Foundational only for its content to be accurate; practically written last since the README documents the finished behavior from US1/US2
- **Polish (Phase 6)**: Depends on all three user stories being complete

### Parallel Opportunities

- Setup: T002, T003, T004, T004a in parallel after T001
- Foundational: T009 (fixtures) in parallel with T005–T008 (implementation); T010 and T011 both depend on their respective implementation + fixtures but touch the same test file, so run sequentially with each other
- User Story 3: T020 (README) and T021 (LICENSE) in parallel
- Polish: T023 and T024 in parallel

---

## Parallel Example: Foundational Phase

```bash
# After T001 (structure) completes, in parallel:
Task: "Create fixture .jsonl files in tests/fixtures/ (T009)"
Task: "Define UsageEntry/TokenTotals/UsageSummary dataclasses in usage_parser.py (T005)"
```

## Parallel Example: Setup Phase

```bash
# After T001 completes, in parallel:
Task: "Create requirements.txt and requirements-dev.txt (T002)"
Task: "Configure pytest and ruff in pyproject.toml (T003)"
Task: "Add scripts/pre-commit local convenience script (T004)"
Task: "Add .github/workflows/ci.yml quality gate (T004a)"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup
2. Complete Phase 2: Foundational — **critical path**; `pytest -q` must be green before continuing
3. Complete Phase 3: User Story 1
4. **STOP and VALIDATE**: run quickstart.md V1–V3 against real local data
5. This is a demoable MVP: clicking the icon shows correct, deduplicated usage

### Incremental Delivery

1. Setup + Foundational → pure core proven correct in isolation
2. + User Story 1 → MVP: manual click shows accurate data
3. + User Story 2 → usage stays current without interaction
4. + User Story 3 → anyone can clone and run it
5. + Polish → full quickstart suite green, Constitution II audit passed

---

## Notes

- Total: 27 tasks (T001–T025 plus T004a and T013a) across Setup, Foundational, 3 user stories, and Polish
- All dataclass/function work for `usage_parser.py` (T005–T008) is sequential within that single file — parallel markers are reserved for genuinely different files
- The deduplication regression guard (`duplicate_message_id.jsonl` fixture, T009 → T010) is the single highest-value test in this feature per `research.md` R2
- Commit after each task or logical group; `.github/workflows/ci.yml` (T004a) is the authoritative `pytest` + `ruff` gate on every push/PR — the local `scripts/pre-commit` hook (T004) is an optional convenience, not a substitute for CI
