# Feature Specification: Menu Bar Usage Display

**Feature Branch**: `001-menubar-usage-display`

**Created**: 2026-08-04

**Status**: Draft

**Input**: User description: "Build a macOS status bar (menu bar) app that displays Claude Code token usage/consumption information. A friend built a similar tool; the goal is a lightweight, open-source utility that anyone using Claude Code can clone and run to keep an eye on their usage directly from the menu bar, without opening a terminal. The app runs as a macOS status bar item, not a regular window. Clicking the icon opens a dropdown showing usage information derived from local Claude Code session data (token counts, aggregated by period — e.g. today, this session, or similar breakdowns). Data is read from local Claude Code session logs only; no external API calls, no authentication. The display updates periodically on an interval. The app is a Python project distributed as a public, open-source GitHub repo; setup is clone + venv + pip install, with no code signing, Homebrew packaging, or signed .app bundle. Autostart on login is out of scope for this version. No support for non-macOS platforms, no historical data storage/database, no account/authentication system of its own. Success: a user can clone the repo, follow the README, and see live usage data in the menu bar within a few minutes; the numbers shown are traceable back to the same data that powers Claude Code's own /usage command."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Quick-Glance Usage Check (Priority: P1)

As a Claude Code user, I click the app's menu bar icon and immediately see my current token usage, so I can gauge how much I've used without opening a terminal or running `/usage`.

**Why this priority**: This is the entire reason the app exists. Without a working dropdown showing accurate usage, there is no product.

**Independent Test**: Launch the app with existing local Claude Code session logs present, click the menu bar icon, and confirm the dropdown displays usage numbers consistent with the underlying log data.

**Acceptance Scenarios**:

1. **Given** the app is running and local Claude Code session logs exist, **When** the user clicks the menu bar icon, **Then** a dropdown opens showing token usage aggregated by at least "today" and "current session" breakdowns.
2. **Given** the dropdown is open, **When** the user reads the displayed numbers, **Then** those numbers are consistent with what Claude Code's own `/usage` command would report for the same underlying session data.

---

### User Story 2 - Usage Stays Current Without Interaction (Priority: P2)

As a Claude Code user who keeps the app running in the background, I want the menu bar usage data to update on its own as I keep working, so I don't have to quit and relaunch the app or manually refresh to see current numbers.

**Why this priority**: Passive, always-current visibility is the app's core value proposition beyond a one-off manual check; without it, the app is no better than running `/usage` by hand.

**Independent Test**: With the app running and its dropdown showing a baseline usage figure, generate additional Claude Code usage (e.g., run a Claude Code session), wait for one refresh interval to elapse, then reopen the dropdown and confirm the numbers increased to reflect the new activity.

**Acceptance Scenarios**:

1. **Given** the app is running and displaying a usage figure, **When** new Claude Code usage accrues in the local session logs, **Then** the app updates its displayed figure within one polling interval without requiring the user to quit or manually refresh it.
2. **Given** no new usage has occurred since the last refresh, **When** the polling interval elapses, **Then** the displayed figures remain unchanged (no spurious changes).

---

### User Story 3 - Simple Clone-and-Run Setup (Priority: P3)

As a new user who has never used this tool before, I want to clone the repository and get the app running in the menu bar with a minimal, documented setup process, so I can start monitoring my usage right away.

**Why this priority**: Distribution simplicity determines whether anyone besides the author can actually adopt the tool; it's lower priority than the app working correctly, but still essential to the project's stated goal of being an open, cloneable utility.

**Independent Test**: On a clean macOS machine with only Python available, follow the README's setup instructions (clone, create a virtual environment, `pip install`) and confirm the app appears in the menu bar without any additional undocumented steps.

**Acceptance Scenarios**:

1. **Given** a user has cloned the public repository, **When** they follow the README's install steps (virtual environment + `pip install`), **Then** the app launches and shows an icon in the menu bar.
2. **Given** the install steps are followed on a machine with no prior Claude Code usage, **When** the app starts, **Then** it launches successfully and shows a clear empty/zero-usage state rather than failing.

---

### Edge Cases

- What happens when no local Claude Code session logs exist at all (brand-new user)? The app MUST show a clear empty/zero-usage state rather than erroring or crashing.
- What happens when a session log file is malformed or only partially written (e.g., Claude Code is actively writing to it while the app reads it)? The app MUST skip or gracefully ignore unreadable entries rather than crashing.
- What happens when there is a very large volume of historical session logs? The app MUST still complete a refresh in a reasonable time without freezing the menu bar.
- What happens when the `~/.claude/projects/` directory itself is missing or inaccessible? The app MUST show an empty/zero-usage or explanatory state rather than crashing.
- What happens when the user's system clock or session log timestamps are inconsistent (e.g., "today" boundary edge cases around midnight)? The app MUST use a consistent, documented definition of "today" (local system time) without crashing.
- If the `claude` binary is not on PATH, the subprocess call fails, or the output can't be parsed, the app MUST still show token totals normally and simply omit the percentage fields (no crash, no blocking error).

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The app MUST display a persistent icon in the macOS menu bar while running.
- **FR-002**: The app MUST NOT present a regular application window or Dock icon; it MUST operate purely as a status bar (menu bar extra) app.
- **FR-003**: Clicking the menu bar icon MUST open a dropdown showing current Claude Code usage information.
- **FR-004**: The app MUST derive all displayed usage data exclusively by reading local Claude Code session log files; it MUST NOT make any external network or API calls to produce that data.
- **FR-005**: The app MUST NOT require any login, authentication, or account setup of its own.
- **FR-006**: The app MUST refresh the displayed usage data automatically on a periodic interval, without requiring the user to manually trigger a refresh.
- **FR-007**: The dropdown MUST present raw token counts (input, output, cache read, cache creation, and a combined total) broken down by at least a "today" total, a "current session" total, and a rolling recent-activity window. These raw token-count totals MUST continue to be derived exclusively from local session logs per FR-004, never from a network call: research confirmed that no rate-limit, quota, or reset data exists in the local session logs themselves. See `research.md` R3 for the evidence and the decision record. (This requirement previously also barred any percentage-of-plan-quota display outright; that blanket prohibition is superseded by FR-013, which permits a specific, narrowly-scoped percentage source that was not available when FR-007 was first written — see `research.md` R13.)
- **FR-013**: The app MUST additionally display current-session and current-week usage percentages, sourced from Claude Code's own `/usage` output (via the `claude -p "/usage" --output-format json` subprocess), shown alongside the existing per-bucket token totals from FR-007. Per Constitution Principle VI, this is a best-effort enhancement: it MUST NOT be treated as part of the raw-token-count guarantee in FR-007, and its unavailability MUST NOT degrade or block the display of FR-007's token totals. See `research.md` R13 for the evidence and decision record.
- **FR-008**: The app MUST show a clear, non-error empty/zero-usage state when no local session log data exists.
- **FR-009**: The app MUST tolerate malformed, partial, or concurrently-written log entries without crashing.
- **FR-010**: The app MUST be installable by cloning the public repository and running a documented process limited to creating a Python virtual environment and running `pip install`; it MUST NOT require code signing, a packaged/signed `.app` bundle, or Homebrew distribution.
- **FR-011**: The app MUST NOT persist its own copy of usage data; every displayed refresh MUST be recomputed directly from the current local log files.
- **FR-012**: The app MUST run entirely on the local machine, with no account or authentication system of its own, and MUST support macOS only.

### Key Entities

- **Usage Session**: A single Claude Code working session recorded in a local session log file; contributes token counts (e.g., input, output, cache) toward aggregated totals.
- **Usage Snapshot**: The aggregated, point-in-time view of token usage the app computes and displays (e.g., "today" and "current session" totals), recomputed fresh on every refresh from the underlying session logs.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A first-time user can go from cloning the repository to seeing live usage data in their menu bar in under 5 minutes, using only the README instructions.
- **SC-002**: Token-count figures shown in the dropdown are traceable back to, and consistent with, the same underlying local session data that powers Claude Code's own `/usage` command. Specifically, each assistant message is counted exactly once (no duplicate-line inflation). This traceability guarantee covers FR-007's raw token counts only; the FR-013 percentage figures are sourced directly from Claude Code's own `/usage` output rather than computed by this app, so their accuracy is bounded by that output, not by this success criterion.
- **SC-003**: Newly-recorded Claude Code usage is reflected in the menu bar display within one polling interval (no more than a couple of minutes) without any user action.
- **SC-004**: The app runs without errors or crashes when local usage logs are missing, empty, or only partially written.
- **SC-005**: The entire setup and normal operation of the app requires zero network requests and zero credential entry.

## Assumptions

- The refresh/polling interval defaults to a short, unobtrusive period (on the order of a minute); the exact value is an implementation detail, not a user-facing configuration requirement for this version.
- Usage aggregation covers all local Claude Code session logs found on the machine (all projects), not scoped to a single project directory, since the goal is an overall usage picture matching `/usage`.
- A single local user/machine and a single active Claude Code account are assumed; multi-account or multi-profile switching is out of scope for this version.
- The menu bar icon itself does not need to render dynamic text or numbers; all usage figures are surfaced in the dropdown shown after a click, keeping the status bar presence minimal.
- "Today" is defined using the local system clock/timezone, consistent with how a user would informally think about their day's usage.
- Percentage-of-plan-quota and reset-timing figures are not derivable from local session logs alone (confirmed in Phase 0 research), so FR-007's raw token counts never depend on or guess at a limit; see `research.md` R3 and its reaffirmation in R12. FR-013 later added a narrow, separate path to a percentage figure — shelling out to Claude Code's own `/usage` command rather than reading session logs or calling a network API directly — which does not reopen the R3/R12 conflict since it stays within the amended constitution's local-subprocess allowance; see `research.md` R13. Reset-timing display remains out of scope.
- Entries recorded with a `<synthetic>` model are locally generated placeholders rather than real API turns and are excluded from totals; subagent (sidechain) entries do consume real tokens and are included.
