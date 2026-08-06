# Phase 0 Research: Menu Bar Usage Display

**Feature**: `001-menubar-usage-display` | **Date**: 2026-08-04

All findings below were derived empirically from the live session logs on this
machine (8 `.jsonl` files, 11 MB, 4,006 lines, 1,669 assistant entries across 7
sessions). Figures are reproducible with the commands noted in each section.

---

## R1: Session log schema

**Decision**: Parse only lines where top-level `type == "assistant"`, reading
token counts from `message.usage` and the event time from the top-level
`timestamp`.

**Findings**: Each `.jsonl` line is one JSON object. Observed `type` values:
`assistant`, `user`, `system`, `mode`, `permission-mode`, `ai-title`,
`last-prompt`, `file-history-snapshot`, `attachment`, `file-history-delta`.
Only `assistant` entries carry a `message.usage` block. Every assistant entry
observed had usage present (0 missing out of 1,669).

Relevant fields on an assistant entry:

| Field | Purpose |
|-------|---------|
| `timestamp` | ISO 8601 UTC, `Z`-suffixed (e.g. `2026-08-04T13:26:19.258Z`) |
| `sessionId` | Groups entries into a session; matches the `.jsonl` filename |
| `message.id` | Assistant message ID (`msg_…`) — the deduplication key |
| `message.model` | e.g. `claude-sonnet-5`, `claude-opus-5`, `<synthetic>` |
| `message.usage.input_tokens` | Uncached input tokens |
| `message.usage.output_tokens` | Generated tokens |
| `message.usage.cache_read_input_tokens` | Tokens served from cache |
| `message.usage.cache_creation_input_tokens` | Tokens written to cache |
| `isSidechain` | `true` for subagent turns |

**Rationale**: Restricting to `assistant` entries keeps the parser simple and
matches where the billable token data actually lives.

**Alternatives considered**: Walking every entry type and summing any `usage`
key found — rejected as needlessly broad; no other type carries usage.

---

## R2: Deduplication is mandatory (2.10× over-count without it)

**Decision**: Deduplicate by `message.id`, counting each unique ID exactly once
(first occurrence wins).

**Findings**: 1,669 assistant entries contain only **783 unique `message.id`
values** — 594 IDs repeat, one appearing 13 times. Inspecting a repeated ID
shows the usage block is written **verbatim** on each line, with only
`timestamp` and `uuid` differing:

```
msg_011CdhnT5n2pvZb9BJKRBDeH  ×7 occurrences
  ts=13:26:19.258Z  in=5538 out=689 cache_read=36335 cache_creation=14900
  ts=13:26:21.272Z  in=5538 out=689 cache_read=36335 cache_creation=14900
  …identical usage on all 7 lines…
```

Claude Code appears to append one line per content block in an assistant turn,
each repeating the turn-level usage. Summing naively yields **273,210,838**
tokens; deduplicating yields **129,920,414** — an inflation factor of **2.10×**.

**Rationale**: Without dedup the app reports roughly double the real usage,
which directly violates SC-002 (numbers traceable to `/usage`). This is the
single highest-risk correctness detail in the feature.

**Alternatives considered**:
- Dedup by `requestId` — equivalent in practice (779 unique vs. 783), but
  `message.id` is the more semantically precise key and is always present.
- Take max/last per ID — unnecessary, since duplicates are byte-identical in
  their usage values.

---

## R3: Rate-limit percentages are NOT derivable locally (FR-007 amended)

**Decision**: Ship raw token counts only. Do **not** display
percentage-of-quota or reset timing.

**Findings**: An exhaustive key scan across all session files for any key
containing `limit`, `reset`, `quota`, or `utilization` returned exactly one
match: `message.content[].input.limit` — the `limit` parameter of a `Read` tool
call, unrelated to rate limits. Greps for `rate_limit`, `rateLimit`,
`resets_at`, `resetsAt`, `unified_rate`, `five_hour`, and `seven_day` matched
nothing. Claude Code's own `/usage` sources quota and reset data from the API,
not from these logs.

**Conflict and resolution**: Spec FR-007 required both raw counts *and* a
percentage-of-plan-quota view with reset timing. Satisfying the latter would
require a network call, violating Constitution Principle I/technical
constraints ("no network calls, no external API") and spec FR-004/FR-005. Per
the constitution's Governance clause — conflicts are resolved by adjusting the
task, not the principle — **FR-007 was narrowed to raw token counts**, and
SC-002 was scoped to token-count traceability. This was confirmed with the
project owner on 2026-08-04. The spec's existing assumption already anticipated
this fallback ("shows the raw token counts … without a percentage rather than
guessing at a limit").

**Alternatives considered**:
- User-configured token budget to compute a percentage — rejected: the
  percentage would reflect a self-declared guess, not the real plan quota, and
  it adds a config surface that Principle V discourages.
- Amending the constitution to permit an authenticated API call — rejected by
  the owner; it would break the no-network and no-auth guarantees that define
  the project.

---

## R4: Timestamp normalization

**Decision**: Parse `timestamp` as UTC, then convert to the system's local
timezone before assigning an entry to a calendar day.

**Findings**: Timestamps are UTC with a `Z` suffix.
`datetime.fromisoformat()` on Python 3.11+ handles the `Z` suffix directly;
`.astimezone()` with no argument converts to system local time. Day totals
computed in local time for this machine:

```
2026-07-16   24,437,697        2026-07-27      218,330
2026-07-17    5,028,782        2026-08-03   32,364,599
2026-07-20    4,516,606        2026-08-04   57,836,773
```

**Rationale**: Spec assumption defines "today" by the local system clock, which
matches how a user thinks about their day. Bucketing in UTC would misattribute
evening usage for users west of UTC.

---

## R5: "Current session" definition

**Decision**: The current session is the `sessionId` with the most recent
entry timestamp across all projects; its total is the sum of its deduplicated
entries.

**Findings**: `sessionId` is present on every assistant entry and equals the
`.jsonl` filename stem. This machine has 7 distinct sessions; the largest holds
48.4 M tokens. Selecting by latest timestamp requires no extra state and needs
no knowledge of which terminal is "active".

**Alternatives considered**: Reading the most recently *modified* file
(`mtime`) — rejected as less reliable, since editors, backups, or sync tools
can touch mtime without the session being current.

---

## R6: Rolling recent-activity window

**Decision**: Include a rolling 5-hour token total alongside "today" and
"current session".

**Rationale**: The user's plan input asked for a "rolling recent-activity
view". A 5-hour window mirrors the block granularity `/usage` uses for session
windows and is fully computable from local timestamps, unlike the quota
percentage in R3.

---

## R7: Malformed and partial line handling

**Decision**: Wrap each line's `json.loads` in a `try`/`except`, increment a
skipped-line counter, and continue.

**Findings**: 0 malformed lines were observed in the current corpus — but
Claude Code appends to these files while the app reads them, so a torn final
line is expected in normal operation. Files are also opened with
`errors="replace"` to survive partial multi-byte UTF-8 writes.

**Rationale**: Satisfies FR-009 and the spec's edge cases without any locking
or coordination with the writing process.

---

## R8: Synthetic and sidechain entries

**Decision**: Exclude entries whose `message.model` is `<synthetic>`; include
sidechain (subagent) entries.

**Findings**: Model distribution across deduplicated entries —
`claude-sonnet-5` (1,188), `claude-opus-4-8` (379), `claude-opus-5` (98),
`<synthetic>` (4). Synthetic entries are locally generated placeholders (e.g.
interrupt notices), not real API turns. `isSidechain` was `false` for all
1,669 entries in this corpus, but subagent runs produce `true` — those consume
real tokens and must count.

---

## R9: Performance and refresh strategy

**Decision**: Re-scan and recompute synchronously on every timer tick, with no
caching. Target a full refresh in under 500 ms.

**Findings**: A full parse of the current corpus (4,006 lines, 11 MB, 8 files)
completes in **45 ms**. Projected to 10× the data, that is ~0.45 s.

**Rationale**: At measured speed a synchronous refresh will not visibly block
the menu bar, so the app avoids threading entirely — the simplest design that
satisfies Principle V and FR-011 (no persistence, always recomputed). If a
user's corpus ever pushes refresh past ~500 ms, moving the scan to a worker
thread is the documented escape hatch, deferred until measurement justifies it.

**Alternatives considered**:
- Incremental parsing with file offsets — rejected: it is a cache, which FR-011
  forbids, and 45 ms does not justify the complexity.
- `watchdog`/FSEvents file watching — rejected: adds a dependency that
  Principle I would require justifying, and polling already meets FR-006.

---

## R10: Timer mechanism

**Decision**: Use `rumps.Timer` with a 60-second interval, started at app
launch, plus one immediate refresh on startup so the menu is never empty.

**Rationale**: `rumps.Timer` is built into the one approved UI dependency and
runs on the main run loop, so menu updates are already thread-safe. A 60 s
interval satisfies SC-003 ("within a couple of minutes") at negligible cost
(45 ms of work per minute ≈ 0.08% duty cycle).

---

## R11: Testing approach

**Decision**: `pytest` unit tests against checked-in fixture `.jsonl` files
covering: normal entries, duplicate `message.id` groups, malformed lines, empty
files, missing directory, multi-day and multi-session data, synthetic-model
entries, and timezone boundary cases. No automated UI tests.

**Rationale**: Constitution Principle II makes the parser importable without
`rumps`, so the whole core is testable in isolation. Principle III requires
lint plus tests enforced by CI (`.github/workflows/ci.yml`), with an optional
local pre-commit convenience (`core.hooksPath`) for fast local feedback. The
dedup behavior from R2 is the most important thing to pin with a regression
test.

---

## R12: Percentage-of-quota revisited post-launch — still not derivable locally

**Decision**: Re-affirm R3. Continue shipping raw token counts only; do not
add session/week usage percentages in any form.

**Findings**: Investigated whether third-party tools solve what R3 could not.

- **ccusage** (ryoppippi/ccusage) computes cost/token totals and a naive
  linear burn-rate projection over 5-hour blocks, but has no
  percentage-of-plan-limit feature and no weekly window at all — not a
  precedent for this.
- **Claude-Code-Usage-Monitor** (Maciek-roboblog) hardcodes per-plan token
  ceilings (Pro 19,000 / Max5 88,000 / Max20 220,000 / Team 19,000
  "unverified") as a **local estimate**, selected via a manual `--plan` flag
  — it never auto-detects the plan tier. Its 5-hour session percentage is
  this rough estimate divided by the hardcoded ceiling. It explicitly does
  **not** compute a weekly percentage locally at all (`snapshots.py`: *"the
  analysis window is ~8 days, not 7"*); the weekly figure only appears via
  Claude Code's own statusline hook or an opt-in authenticated call to
  Anthropic's undocumented `api.anthropic.com/api/oauth/usage`.
- Checked whether Claude Code stores the account's plan tier locally: not
  under `~/.claude/` (`settings.json`, `stats-cache.json` have no tier
  fields), but **`~/.claude.json`** (a sibling file, not inside
  `~/.claude/`) does — `oauthAccount.organizationType` (e.g. `"claude_pro"`)
  and a `cachedUsageUtilization` block carrying `five_hour`/`seven_day`
  `utilization` percentages and `resets_at` timestamps. This is a
  server-fetched cache of Anthropic's own computed numbers, of undocumented
  refresh cadence — not something derived from the `.jsonl` session logs,
  and outside this project's local-session-logs-only data source. Session
  `.jsonl` logs themselves still carry no plan/tier field anywhere (matches
  R3); the only tier-like field is the unrelated `usage.service_tier`
  (API request-priority, e.g. `"standard"`).

**Conclusion**: the only two paths to a percentage are (a) an approximate,
hardcoded-limit local estimate with no reliable weekly equivalent, mirroring
Claude-Code-Usage-Monitor's own compromise, or (b) reading Claude Code's
internal `~/.claude.json` cache, which is an undocumented format outside this
project's declared data source (`~/.claude/projects/**/*.jsonl`) and would
mean displaying a server-computed number verbatim rather than anything this
app derives itself. Neither satisfies SC-002's traceability bar or this
project's scope. R3's decision stands: FR-007 stays raw-token-counts-only.
Users who want a percentage can compare the displayed totals against their
own known plan limit manually.

**Alternatives considered**:
- Hardcoded per-plan ceilings (à la Claude-Code-Usage-Monitor) — rejected:
  Anthropic doesn't publish these as a stable contract, so the ceilings would
  silently go stale as plans change, producing a confidently wrong number
  rather than no number.
- Reading `~/.claude.json`'s `cachedUsageUtilization` directly — rejected:
  it's an undocumented internal Claude Code file (also carrying account UUID
  and email), not a "local session log," and the app would just be
  re-displaying someone else's server-computed figure of unknown freshness,
  not computing anything itself.
