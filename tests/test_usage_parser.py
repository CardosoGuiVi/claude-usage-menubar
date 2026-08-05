"""Unit tests for `usage_parser.parse_entries()` and `usage_parser.aggregate()`.

Fixtures live in `tests/fixtures/` (see T009). Each `parse_entries()` test
copies only the one fixture file it needs into an isolated `tmp_path`
directory so that the fixtures directory as a whole (which contains files
for other tests) never interferes with a given test's entry/skip-count
assertions.

`aggregate()` tests (T011) construct `UsageEntry` objects directly in code
— `aggregate()` takes already-parsed entries and a caller-supplied `now`,
so no fixture files or `parse_entries()` involvement is needed there.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from usage_parser import TokenTotals, UsageEntry, aggregate, parse_entries

FIXTURES_DIR = Path(__file__).parent / "fixtures"
REPO_ROOT = Path(__file__).parent.parent


@pytest.fixture
def fixed_system_tz():
    """Force the process's local timezone for the duration of a test.

    `aggregate()` determines "local day" boundaries via bare
    `datetime.astimezone()` calls (no explicit tz argument), which resolve
    against the process's system-local timezone rather than any tzinfo
    attached to the values under test. To make local-day bucketing
    deterministic regardless of the machine actually running the test
    suite, we must therefore control the real system timezone (via the
    `TZ` environment variable plus `time.tzset()`) rather than only
    attaching explicit `tzinfo` objects to the test's datetimes.

    The original `TZ` value (and the tzset() state it implies) is always
    restored, even on failure, so this never leaks into other tests.
    """
    import os

    original = os.environ.get("TZ")

    def _set(tz_name: str) -> None:
        os.environ["TZ"] = tz_name
        time.tzset()

    yield _set

    if original is None:
        os.environ.pop("TZ", None)
    else:
        os.environ["TZ"] = original
    time.tzset()


def _isolated_fixture(tmp_path: Path, fixture_name: str) -> Path:
    """Copy a single fixture file into `tmp_path` and return the directory."""
    shutil.copy(FIXTURES_DIR / fixture_name, tmp_path / fixture_name)
    return tmp_path


class TestParseEntries:
    """Tests for `usage_parser.parse_entries()`."""

    def test_dedup_collapses_duplicate_message_id(self, tmp_path: Path) -> None:
        log_root = _isolated_fixture(tmp_path, "duplicate_message_id.jsonl")

        entries, skipped_lines = parse_entries(log_root)

        # msg_fixture_dup_001 appears 4x, msg_fixture_dup_002 appears 1x —
        # dedup by message.id must collapse this to exactly 2 entries.
        assert len(entries) == 2
        assert skipped_lines == 0
        message_ids = {entry.message_id for entry in entries}
        assert message_ids == {"msg_fixture_dup_001", "msg_fixture_dup_002"}

    def test_malformed_lines_increment_skipped_without_raising(
        self, tmp_path: Path
    ) -> None:
        log_root = _isolated_fixture(tmp_path, "malformed.jsonl")

        entries, skipped_lines = parse_entries(log_root)

        assert skipped_lines == 3
        assert len(entries) == 2

    def test_empty_file_yields_no_entries(self, tmp_path: Path) -> None:
        log_root = _isolated_fixture(tmp_path, "empty.jsonl")

        entries, skipped_lines = parse_entries(log_root)

        assert entries == []
        assert skipped_lines == 0

    def test_synthetic_model_entries_are_excluded(self, tmp_path: Path) -> None:
        log_root = _isolated_fixture(tmp_path, "synthetic_model.jsonl")

        entries, skipped_lines = parse_entries(log_root)

        # 2 synthetic entries excluded (not skipped), 1 real entry kept.
        assert len(entries) == 1
        assert entries[0].model != "<synthetic>"
        assert skipped_lines == 0

    def test_missing_directory_returns_empty(self) -> None:
        entries, skipped_lines = parse_entries(Path("/some/nonexistent/path"))

        assert entries == []
        assert skipped_lines == 0


def _make_entry(
    *,
    message_id: str,
    session_id: str,
    timestamp: datetime,
    input_tokens: int = 0,
    output_tokens: int = 0,
    cache_read_tokens: int = 0,
    cache_creation_tokens: int = 0,
    model: str = "claude-sonnet-4",
) -> UsageEntry:
    return UsageEntry(
        message_id=message_id,
        session_id=session_id,
        timestamp=timestamp,
        model=model,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cache_read_tokens=cache_read_tokens,
        cache_creation_tokens=cache_creation_tokens,
    )


class TestAggregate:
    """Tests for `usage_parser.aggregate()` (T011)."""

    def test_buckets_today_current_session_rolling_5h_all_time(
        self, fixed_system_tz
    ) -> None:
        # Force system-local time to UTC so "local day" and "UTC day" are
        # identical here, keeping this test's reasoning independent of
        # timezone conversion (that's exercised separately below).
        fixed_system_tz("UTC")

        now = datetime(2026, 8, 4, 12, 0, 0, tzinfo=UTC)

        # In the current session, in the rolling 5h window, and today.
        in_session_recent = _make_entry(
            message_id="m1",
            session_id="session-current",
            timestamp=now - timedelta(minutes=10),
            input_tokens=100,
            output_tokens=50,
            cache_read_tokens=10,
            cache_creation_tokens=5,
        )
        # A different session, still within the rolling 5h window and today.
        other_session_today = _make_entry(
            message_id="m2",
            session_id="session-other",
            timestamp=now - timedelta(hours=1),
            input_tokens=200,
            output_tokens=20,
            cache_read_tokens=0,
            cache_creation_tokens=0,
        )
        # Outside the rolling 5h window (now - 6h < now - 5h cutoff), but
        # still the same local calendar day as `now` (00:00-12:00 UTC).
        outside_rolling_but_today = _make_entry(
            message_id="m3",
            session_id="session-other",
            timestamp=now - timedelta(hours=6),
            input_tokens=300,
            output_tokens=30,
            cache_read_tokens=0,
            cache_creation_tokens=0,
        )
        # A previous calendar day entirely — excluded from today, rolling
        # 5h, and current session; counted only in all_time.
        previous_day = _make_entry(
            message_id="m4",
            session_id="session-other",
            timestamp=now - timedelta(days=1),
            input_tokens=400,
            output_tokens=40,
            cache_read_tokens=0,
            cache_creation_tokens=0,
        )

        entries = [
            in_session_recent,
            other_session_today,
            outside_rolling_but_today,
            previous_day,
        ]

        summary = aggregate(entries, now)

        # The latest entry by timestamp owns the "current session".
        assert summary.current_session_id == "session-current"
        assert summary.last_activity == in_session_recent.timestamp
        assert summary.entry_count == 4

        assert summary.current_session == TokenTotals(
            input=100, output=50, cache_read=10, cache_creation=5
        )

        assert summary.rolling_5h == TokenTotals(
            input=100 + 200, output=50 + 20, cache_read=10, cache_creation=5
        )

        assert summary.today == TokenTotals(
            input=100 + 200 + 300,
            output=50 + 20 + 30,
            cache_read=10,
            cache_creation=5,
        )

        assert summary.all_time == TokenTotals(
            input=100 + 200 + 300 + 400,
            output=50 + 20 + 30 + 40,
            cache_read=10,
            cache_creation=5,
        )

    def test_empty_list_returns_all_zero_summary(self) -> None:
        now = datetime(2026, 8, 4, 12, 0, 0, tzinfo=UTC)

        summary = aggregate([], now)

        assert summary.current_session_id is None
        assert summary.last_activity is None
        assert summary.entry_count == 0
        assert summary.today == TokenTotals()
        assert summary.current_session == TokenTotals()
        assert summary.rolling_5h == TokenTotals()
        assert summary.all_time == TokenTotals()

    def test_utc_timestamp_buckets_into_correct_local_day(
        self, fixed_system_tz
    ) -> None:
        # Asia/Tokyo is a fixed UTC+9 offset with no DST, which keeps this
        # test deterministic year-round. Force it as the *system* local
        # timezone (not just an explicit tzinfo on our test datetimes)
        # because aggregate() determines "local day" via bare
        # datetime.astimezone() calls, which resolve against the process's
        # actual system timezone.
        fixed_system_tz("Asia/Tokyo")

        # `now`: 2026-08-05T01:00:00Z == 2026-08-05 10:00 JST — local
        # "today" is August 5th in Tokyo.
        now = datetime(2026, 8, 5, 1, 0, 0, tzinfo=UTC)

        # Entry timestamp is late in the UTC calendar day of August 4th
        # (16:30 UTC), but 16:30 UTC + 9h == 2026-08-05 01:30 JST — the
        # *next* local calendar day relative to its own UTC date, and the
        # *same* local calendar day as `now`. A naive same-UTC-date
        # comparison (Aug 4 vs. Aug 5) would wrongly exclude this entry
        # from "today"; correct local-day bucketing must include it.
        late_utc_entry = _make_entry(
            message_id="m1",
            session_id="session-tokyo",
            timestamp=datetime(2026, 8, 4, 16, 30, 0, tzinfo=UTC),
            input_tokens=777,
            output_tokens=111,
            cache_read_tokens=22,
            cache_creation_tokens=3,
        )

        summary = aggregate([late_utc_entry], now)

        assert summary.entry_count == 1
        assert summary.current_session_id == "session-tokyo"
        assert summary.last_activity == late_utc_entry.timestamp
        assert summary.today == TokenTotals(
            input=777, output=111, cache_read=22, cache_creation=3
        )


class TestConstitutionCompliance:
    """T012: `usage_parser` must import with no `rumps` dependency.

    This is the executable form of quickstart.md V1 and enforces
    Constitution Principle II ("Pure Core, Thin UI") /
    `contracts/usage_parser.md` invariant 1: `usage_parser` MUST NOT
    import `rumps` or any UI module.

    A plain `import usage_parser` in this test process proves nothing on
    its own, because `rumps` is already installed here (it's a runtime
    dependency in `requirements.txt`, and CI installs both
    `requirements.txt` and `requirements-dev.txt` before running
    pytest) — so an accidental `import rumps` inside `usage_parser.py`
    would silently succeed rather than fail this suite.

    To make the check meaningful regardless of what happens to be
    installed, we run the import in a *subprocess* with
    `sys.modules["rumps"] = None` set before importing `usage_parser`.
    Per Python's import system, a `None` entry in `sys.modules` makes any
    subsequent `import rumps` (or `from rumps import ...`) raise
    `ImportError` immediately, without needing `rumps` to be physically
    absent from the environment. If `usage_parser` imports cleanly under
    that condition, it cannot have a module-level dependency on `rumps`.
    """

    def test_imports_without_rumps(self) -> None:
        probe = (
            "import sys\n"
            "sys.modules['rumps'] = None\n"
            "import usage_parser\n"
            "usage_parser.get_summary\n"
            "print('OK')\n"
        )

        result = subprocess.run(
            [sys.executable, "-c", probe],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=False,
        )

        assert result.returncode == 0, (
            f"usage_parser failed to import without rumps.\n"
            f"stdout: {result.stdout}\nstderr: {result.stderr}"
        )
        assert "OK" in result.stdout
