"""Unit tests for `usage_percentage.get_usage_percentages()`.

Per `research.md` R13, this module shells out to the `claude` CLI; these
tests never invoke a real subprocess -- `subprocess.run` is mocked in every
test via `unittest.mock.patch`. Three of the four fixture `result` strings
below (`FIXTURE_NORMAL`, `FIXTURE_ZERO`, `FIXTURE_NEAR_100`) are
hand-constructed from R13's evidenced label/suffix fragments, updated per
R13's follow-up addendum to use the owner-observed absolute reset
timestamp phrasing (e.g. "resets 8:10pm") rather than R13's original
relative-phrasing guess ("resets in 4d 2h"); `FIXTURE_MALFORMED` is the
verbatim real captured cost-report string, unchanged. Each is wrapped in
the same JSON envelope shape R13 describes for the real captured `claude
-p "/usage" --output-format json` output (a `"result"` string field
alongside cost/turn/session metadata), then `json.dumps`'d to stand in for
the mocked stdout.

Per `research.md` R15, `_get_usage_percentages_unsafe()` now resolves the
`claude` binary via `_resolve_claude_binary()` *before* ever calling
`subprocess.run()`. Every test below that expects `subprocess.run` to
actually be invoked (and its mocked return value/side_effect to matter)
therefore also patches `usage_percentage._resolve_claude_binary` to return
a fixed dummy path via the module-scoped `_patch_resolve_claude_binary`
autouse fixture below -- without it, these tests would silently depend on
whether a real `claude` binary happens to exist on whatever machine runs
them, rather than actually exercising the mocked `subprocess.run`. The
resolver-fallback behavior itself (missing configured path, `shutil.which`
fallback, both absent) is covered by its own dedicated tests, which
override/bypass this fixture as needed.
"""

from __future__ import annotations

import json
import subprocess
from unittest import mock

import pytest

import usage_percentage
from usage_percentage import UsagePercentages, get_usage_percentages

FIXTURE_NORMAL = (
    "Current session               45% used   resets 8:10pm\n"
    "Current week (all models)     12% used   resets Aug 9, 12pm"
)

FIXTURE_ZERO = (
    "Current session               0% used   resets 8:10pm\n"
    "Current week (all models)     0% used   resets Aug 9, 12pm"
)

FIXTURE_NEAR_100 = (
    "Current session                99% used   resets 8:10pm\n"
    "Current week (all models)      100% used   resets Aug 9, 12pm"
)

FIXTURE_MALFORMED = (
    "Total cost:            $0.0000\n"
    "Total duration (API):  0s\n"
    "Total duration (wall): 0s\n"
    "Total code changes:    0 lines added, 0 lines removed\n"
    "Usage:                 0 input, 0 output, 0 cache read, 0 cache write"
)


def _envelope(result: str) -> str:
    """Wrap a `result` string in the CLI's real JSON envelope shape (R13)."""
    return json.dumps(
        {
            "type": "result",
            "subtype": "success",
            "is_error": False,
            "duration_ms": 1234,
            "duration_api_ms": 0,
            "num_turns": 0,
            "result": result,
            "session_id": "fixture-session",
            "total_cost_usd": 0.0,
            "uuid": "fixture-uuid",
        }
    )


def _completed(stdout: str, returncode: int = 0) -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess(
        args=["claude", "-p", "/usage", "--output-format", "json"],
        returncode=returncode,
        stdout=stdout,
        stderr=(
            "⚠ claude.ai connectors are disabled because ANTHROPIC_API_KEY "
            "or another auth source is set and takes precedence over your "
            "claude.ai login · Unset it to load your organization's "
            "connectors\n"
        ),
    )


class TestGetUsagePercentages:
    @pytest.fixture(autouse=True)
    def _fixed_claude_binary(self):
        """Patch `_resolve_claude_binary()` to a fixed dummy path for every
        test in this class, per `research.md` R15.

        `_get_usage_percentages_unsafe()` now calls `_resolve_claude_binary()`
        *before* `subprocess.run()`; without this fixture these tests would
        silently depend on whether a real `claude` binary happens to exist
        (at `usage_percentage.CLAUDE_BINARY_PATH` or on `PATH`) on whatever
        machine runs them, rather than actually exercising the mocked
        `subprocess.run` below -- almost certainly absent on a CI runner,
        likely present on a dev machine that has Claude Code installed,
        which would make the suite non-portable.
        """
        with mock.patch.object(
            usage_percentage, "_resolve_claude_binary", return_value="/fake/claude"
        ):
            yield

    def test_normal_output_parses_both_percentages(self) -> None:
        with mock.patch(
            "subprocess.run", return_value=_completed(_envelope(FIXTURE_NORMAL))
        ):
            result = get_usage_percentages()

        assert result == UsagePercentages(
            session_pct=45,
            week_pct=12,
            session_reset="8:10pm",
            week_reset="Aug 9, 12pm",
        )

    def test_zero_percent_session_parses_as_zero_not_missing(self) -> None:
        with mock.patch(
            "subprocess.run", return_value=_completed(_envelope(FIXTURE_ZERO))
        ):
            result = get_usage_percentages()

        # Classic falsy-vs-missing bug class: 0 must not be treated as None.
        assert result.session_pct == 0
        assert result.session_pct is not None
        assert result.week_pct == 0
        assert result.week_pct is not None
        assert result.session_reset == "8:10pm"
        assert result.week_reset == "Aug 9, 12pm"

    def test_near_100_and_100_parse_correctly(self) -> None:
        with mock.patch(
            "subprocess.run", return_value=_completed(_envelope(FIXTURE_NEAR_100))
        ):
            result = get_usage_percentages()

        assert result == UsagePercentages(
            session_pct=99,
            week_pct=100,
            session_reset="8:10pm",
            week_reset="Aug 9, 12pm",
        )

    def test_reset_text_absent_for_one_side_still_parses_the_other(self) -> None:
        """A percentage line with no reset phrase at all must not fail the
        whole parse -- the reset field for that side stays `None`, and the
        other side's percentage/reset are unaffected.
        """
        fixture = (
            "Current session               45% used\n"
            "Current week (all models)     12% used   resets Aug 9, 12pm"
        )
        with mock.patch("subprocess.run", return_value=_completed(_envelope(fixture))):
            result = get_usage_percentages()

        assert result == UsagePercentages(
            session_pct=45,
            week_pct=12,
            session_reset=None,
            week_reset="Aug 9, 12pm",
        )

    def test_reset_text_absent_for_both_sides_still_parses_percentages(self) -> None:
        fixture = (
            "Current session               45% used\n"
            "Current week (all models)     12% used"
        )
        with mock.patch("subprocess.run", return_value=_completed(_envelope(fixture))):
            result = get_usage_percentages()

        assert result == UsagePercentages(
            session_pct=45,
            week_pct=12,
            session_reset=None,
            week_reset=None,
        )

    def test_malformed_cost_report_yields_both_none(self) -> None:
        with mock.patch(
            "subprocess.run", return_value=_completed(_envelope(FIXTURE_MALFORMED))
        ):
            result = get_usage_percentages()

        assert result == UsagePercentages(session_pct=None, week_pct=None)

    def test_file_not_found_yields_empty_result(self) -> None:
        with mock.patch("subprocess.run", side_effect=FileNotFoundError()):
            result = get_usage_percentages()

        assert result == UsagePercentages()

    def test_timeout_yields_empty_result(self) -> None:
        with mock.patch(
            "subprocess.run",
            side_effect=subprocess.TimeoutExpired(cmd="claude", timeout=5.0),
        ):
            result = get_usage_percentages()

        assert result == UsagePercentages()

    def test_generic_os_error_yields_empty_result(self) -> None:
        with mock.patch("subprocess.run", side_effect=OSError("boom")):
            result = get_usage_percentages()

        assert result == UsagePercentages()

    def test_unicode_decode_error_yields_empty_result(self) -> None:
        """Regression test: `subprocess.run(text=True)` decodes stdout
        itself and can raise `UnicodeDecodeError` on non-UTF-8 bytes -- a
        `ValueError` subclass, not an `OSError` subclass, so it is not
        caught by the same except tuple as `FileNotFoundError`/`OSError`.
        A prior version of `get_usage_percentages()` missed this and let it
        propagate out of `_refresh()`, which would have broken the FR-007
        token totals too (see `research.md` R13 and the code review that
        caught this).
        """
        with mock.patch(
            "subprocess.run",
            side_effect=UnicodeDecodeError(
                "utf-8", b"\xff\xfe", 0, 1, "invalid start byte"
            ),
        ):
            result = get_usage_percentages()

        assert result == UsagePercentages()

    def test_unanticipated_exception_type_is_still_caught(self) -> None:
        """The outer `except Exception` in `get_usage_percentages()` is a
        deliberate last-resort safety net for failure modes beyond the
        specific ones `_get_usage_percentages_unsafe()` enumerates -- this
        asserts that guarantee directly, with an arbitrary exception type
        unrelated to subprocess/JSON/regex handling, rather than relying on
        code review alone.
        """
        with mock.patch("subprocess.run", side_effect=RuntimeError("boom")):
            result = get_usage_percentages()

        assert result == UsagePercentages()

    def test_non_json_stdout_yields_empty_result(self) -> None:
        with mock.patch("subprocess.run", return_value=_completed("not json at all")):
            result = get_usage_percentages()

        assert result == UsagePercentages()

    def test_missing_result_key_yields_empty_result(self) -> None:
        payload = json.dumps({"type": "result", "subtype": "success"})
        with mock.patch("subprocess.run", return_value=_completed(payload)):
            result = get_usage_percentages()

        assert result == UsagePercentages()

    def test_non_string_result_key_yields_empty_result(self) -> None:
        payload = json.dumps({"result": 12345})
        with mock.patch("subprocess.run", return_value=_completed(payload)):
            result = get_usage_percentages()

        assert result == UsagePercentages()

    def test_non_dict_json_yields_empty_result(self) -> None:
        payload = json.dumps(["not", "a", "dict"])
        with mock.patch("subprocess.run", return_value=_completed(payload)):
            result = get_usage_percentages()

        assert result == UsagePercentages()

    def test_nonzero_exit_code_still_attempts_to_parse_stdout(self) -> None:
        with mock.patch(
            "subprocess.run",
            return_value=_completed(_envelope(FIXTURE_NORMAL), returncode=1),
        ):
            result = get_usage_percentages()

        assert result == UsagePercentages(
            session_pct=45,
            week_pct=12,
            session_reset="8:10pm",
            week_reset="Aug 9, 12pm",
        )


class TestResolveClaudeBinary:
    """Per `research.md` R15: `_resolve_claude_binary()`'s fallback chain.

    Deliberately does NOT use `TestGetUsagePercentages`'s
    `_fixed_claude_binary` autouse fixture -- these tests exercise the
    resolver itself, so they patch `usage_percentage.CLAUDE_BINARY_PATH`
    and `shutil.which` directly instead.
    """

    def test_configured_path_missing_and_no_path_fallback_short_circuits(
        self,
    ) -> None:
        """Simulates "a different machine": the configured absolute path
        doesn't exist there, and PATH doesn't have `claude` either. Must
        gracefully degrade to the empty result, and -- critically -- must
        never even call `subprocess.run`, proving the short-circuit
        actually happens rather than merely happening to produce the same
        empty result via the existing `FileNotFoundError` catch.
        """
        with (
            mock.patch.object(
                usage_percentage, "CLAUDE_BINARY_PATH", "/nonexistent/path/claude"
            ),
            mock.patch("shutil.which", return_value=None),
            mock.patch("subprocess.run") as mock_run,
        ):
            result = get_usage_percentages()

        assert result == UsagePercentages()
        mock_run.assert_not_called()

    def test_shutil_which_fallback_is_used_when_configured_path_missing(
        self,
    ) -> None:
        """When the configured path doesn't exist but `shutil.which` finds
        `claude` elsewhere (e.g. `/usr/local/bin/claude` on an Intel Mac),
        that resolved path must be what's actually passed to
        `subprocess.run` as argv[0].
        """
        with (
            mock.patch.object(
                usage_percentage, "CLAUDE_BINARY_PATH", "/nonexistent/path/claude"
            ),
            mock.patch("shutil.which", return_value="/usr/local/bin/claude"),
            mock.patch(
                "subprocess.run",
                return_value=_completed(_envelope(FIXTURE_NORMAL)),
            ) as mock_run,
        ):
            result = get_usage_percentages()

        assert result.session_pct == 45
        assert mock_run.call_args.args[0][0] == "/usr/local/bin/claude"
