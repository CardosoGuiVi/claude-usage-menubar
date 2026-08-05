"""Pure core: parse and aggregate Claude Code session log usage data.

This module MUST NOT import `rumps` or any UI module, MUST NOT raise on
malformed/missing/unreadable input, MUST NOT write to disk or cache between
calls, and MUST NOT open a network connection. See
`specs/001-menubar-usage-display/contracts/usage_parser.md` for the full
contract.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta
from pathlib import Path

DEFAULT_LOG_ROOT = Path.home() / ".claude" / "projects"


@dataclass(frozen=True)
class UsageEntry:
    """One deduplicated assistant turn extracted from a session log."""

    message_id: str
    session_id: str
    timestamp: datetime
    model: str
    input_tokens: int
    output_tokens: int
    cache_read_tokens: int
    cache_creation_tokens: int

    @property
    def total_tokens(self) -> int:
        return (
            self.input_tokens
            + self.output_tokens
            + self.cache_read_tokens
            + self.cache_creation_tokens
        )


@dataclass
class TokenTotals:
    """Zero-valued by default; the empty state for token aggregation."""

    input: int = 0
    output: int = 0
    cache_read: int = 0
    cache_creation: int = 0

    @property
    def total(self) -> int:
        return self.input + self.output + self.cache_read + self.cache_creation


@dataclass
class UsageSummary:
    """The aggregated, point-in-time view rendered in the dropdown."""

    today: TokenTotals = field(default_factory=TokenTotals)
    current_session: TokenTotals = field(default_factory=TokenTotals)
    rolling_5h: TokenTotals = field(default_factory=TokenTotals)
    all_time: TokenTotals = field(default_factory=TokenTotals)
    current_session_id: str | None = None
    last_activity: datetime | None = None
    entry_count: int = 0
    skipped_lines: int = 0


def _parse_timestamp(raw: object) -> datetime | None:
    """Parse an ISO 8601 timestamp string, tolerating a 'Z' suffix.

    Returns None if `raw` is missing or unparseable, rather than raising.
    """
    if not isinstance(raw, str) or not raw:
        return None
    normalized = raw.replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(normalized)
    except ValueError:
        return None


def _extract_entry(record: dict) -> UsageEntry | None:
    """Build a UsageEntry from one parsed JSON line, or None if it fails
    the validation rules in data-model.md (caller decides whether that
    counts as a skipped line or a legitimate exclusion).
    """
    if record.get("type") != "assistant":
        return None

    message = record.get("message")
    if not isinstance(message, dict):
        return None

    message_id = message.get("id")
    if not message_id:
        return None

    usage = message.get("usage")
    if not isinstance(usage, dict):
        return None

    timestamp = _parse_timestamp(record.get("timestamp"))
    if timestamp is None:
        return None

    model = message.get("model", "")

    def _token(key: str) -> int:
        value = usage.get(key, 0)
        if not isinstance(value, int) or value < 0:
            return 0
        return value

    return UsageEntry(
        message_id=message_id,
        session_id=record.get("sessionId", ""),
        timestamp=timestamp,
        model=model,
        input_tokens=_token("input_tokens"),
        output_tokens=_token("output_tokens"),
        cache_read_tokens=_token("cache_read_input_tokens"),
        cache_creation_tokens=_token("cache_creation_input_tokens"),
    )


def parse_entries(
    log_root: Path = DEFAULT_LOG_ROOT,
) -> tuple[list[UsageEntry], int]:
    """Recursively parse every `*.jsonl` file under `log_root`.

    Returns `(deduplicated_entries, skipped_line_count)`. Never raises —
    see `contracts/usage_parser.md` for the full guarantee table.
    """
    skipped_lines = 0
    seen_ids: set[str] = set()
    entries: list[UsageEntry] = []

    if not log_root.is_dir():
        return [], 0

    try:
        jsonl_files = sorted(log_root.glob("**/*.jsonl"))
    except OSError:
        return [], 0

    for jsonl_file in jsonl_files:
        try:
            with jsonl_file.open("r", encoding="utf-8", errors="replace") as fh:
                lines = fh.readlines()
        except OSError:
            # Unreadable file (permissions, race with deletion, etc.) —
            # contributes nothing, scan continues.
            continue

        for raw_line in lines:
            line = raw_line.strip()
            if not line:
                continue

            try:
                record = json.loads(line)
            except (json.JSONDecodeError, ValueError):
                skipped_lines += 1
                continue

            if not isinstance(record, dict):
                skipped_lines += 1
                continue

            entry = _extract_entry(record)
            if entry is None:
                skipped_lines += 1
                continue

            if entry.model == "<synthetic>":
                # Legitimate exclusion, not malformed data — do not
                # count toward skipped_lines (research R8).
                continue

            if entry.message_id in seen_ids:
                # Duplicate content-block line for an already-seen turn
                # (research R2) — valid data, just a duplicate.
                continue

            seen_ids.add(entry.message_id)
            entries.append(entry)

    return entries, skipped_lines


def aggregate(entries: list[UsageEntry], now: datetime) -> UsageSummary:
    """Bucket deduplicated entries into a point-in-time `UsageSummary`.

    Pure function: performs no file I/O and never calls `datetime.now()`
    internally — `now` is the caller-supplied reference time, which makes
    every time-dependent rule deterministic under test.

    `now` is expected to be timezone-aware. If it is naive (no `tzinfo`),
    it is treated as already being in system-local time: `datetime.astimezone()`
    called on a naive value assumes the system local timezone and attaches it,
    which is exactly what we want here. Entry timestamps are always aware
    (parsed from UTC in `parse_entries`), so `now` must become aware too
    before it can be compared against them without raising — this keeps the
    module's "never raises" contract even when a naive `now` is supplied.
    """
    if not entries:
        return UsageSummary()

    if now.tzinfo is None:
        now = now.astimezone()

    today_totals = TokenTotals()
    current_session_totals = TokenTotals()
    rolling_5h_totals = TokenTotals()
    all_time_totals = TokenTotals()

    local_today = now.astimezone().date()
    rolling_cutoff = now - timedelta(hours=5)

    latest_entry = max(entries, key=lambda entry: entry.timestamp)
    current_session_id = latest_entry.session_id

    for entry in entries:
        all_time_totals.input += entry.input_tokens
        all_time_totals.output += entry.output_tokens
        all_time_totals.cache_read += entry.cache_read_tokens
        all_time_totals.cache_creation += entry.cache_creation_tokens

        if entry.timestamp.astimezone().date() == local_today:
            today_totals.input += entry.input_tokens
            today_totals.output += entry.output_tokens
            today_totals.cache_read += entry.cache_read_tokens
            today_totals.cache_creation += entry.cache_creation_tokens

        if entry.session_id == current_session_id:
            current_session_totals.input += entry.input_tokens
            current_session_totals.output += entry.output_tokens
            current_session_totals.cache_read += entry.cache_read_tokens
            current_session_totals.cache_creation += entry.cache_creation_tokens

        if entry.timestamp >= rolling_cutoff:
            rolling_5h_totals.input += entry.input_tokens
            rolling_5h_totals.output += entry.output_tokens
            rolling_5h_totals.cache_read += entry.cache_read_tokens
            rolling_5h_totals.cache_creation += entry.cache_creation_tokens

    return UsageSummary(
        today=today_totals,
        current_session=current_session_totals,
        rolling_5h=rolling_5h_totals,
        all_time=all_time_totals,
        current_session_id=current_session_id,
        last_activity=latest_entry.timestamp,
        entry_count=len(entries),
    )


def get_summary(
    log_root: Path = DEFAULT_LOG_ROOT,
    now: datetime | None = None,
) -> UsageSummary:
    """Convenience composition: `parse_entries` then `aggregate`.

    The single function `menubar_app` is expected to call. When `now` is
    `None` it defaults to the current local time (timezone-aware).
    Propagates `skipped_lines` from `parse_entries` onto the returned
    summary, since `aggregate()` leaves that field at 0 by design. Never
    raises — both `parse_entries` and `aggregate` already never raise.
    """
    if now is None:
        now = datetime.now().astimezone()

    entries, skipped_lines = parse_entries(log_root)
    summary = aggregate(entries, now)
    return replace(summary, skipped_lines=skipped_lines)


_TOKEN_UNITS = ((1_000_000_000, "B"), (1_000_000, "M"), (1_000, "K"))


def format_tokens(n: int) -> str:
    """Render a token count compactly for menu display.

    Values under 1000 render as-is (e.g. `999`). Values >= 1000 render
    with one decimal place and a K/M/B suffix (e.g. `1234` -> `"1.2K"`,
    `57836773` -> `"57.8M"`). Negative values shouldn't occur in practice
    (token counts are defensively coerced to non-negative ints upstream),
    but are handled by rendering the magnitude with a leading `-` rather
    than raising.
    """
    if n < 0:
        return f"-{format_tokens(-n)}"

    if n < 1000:
        return str(n)

    for i, (threshold, suffix) in enumerate(_TOKEN_UNITS):
        if n >= threshold:
            rounded = round(n / threshold, 1)
            if rounded >= 1000 and i > 0:
                # Rounding pushed the value into the next larger unit
                # (e.g. 999999 -> "1000.0K" would be misleading; escalate
                # to "1.0M" instead).
                larger_threshold, larger_suffix = _TOKEN_UNITS[i - 1]
                return f"{n / larger_threshold:.1f}{larger_suffix}"
            return f"{rounded:.1f}{suffix}"

    # Unreachable given the checks above, but keeps the function total.
    return str(n)
