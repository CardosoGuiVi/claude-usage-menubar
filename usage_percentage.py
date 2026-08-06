"""Best-effort core: session/week usage percentages via the `claude` CLI.

Kept separate from `usage_parser.py` (which reads local `.jsonl` session
logs) per Constitution Principle II's pure-core boundary -- this module is a
different kind of "core": it shells out to the locally-installed `claude`
binary rather than reading files, so it is not literally side-effect-free,
but it still MUST NOT import `rumps` or any UI module, MUST NOT write to
disk or cache between calls, and -- like `usage_parser.py` -- MUST NEVER
raise, under any failure condition (missing binary, timeout, nonzero exit,
unparseable JSON, unexpected text format). Per Constitution Principle VI
("Graceful Degradation for Unstable External Formats"), the CLI's `/usage`
text output is not a documented, versioned data contract -- any failure to
obtain or parse it degrades to "no percentage available" rather than
crashing or blocking the rest of the app. See `research.md` R13 for the
regexes, the evidence they're based on, and the fixture strings used in
this module's tests.
"""

from __future__ import annotations

import json
import re
import subprocess
from dataclasses import dataclass

# Per `research.md` R13: verbatim, evidenced/tested regexes. Permissive and
# whitespace/punctuation-tolerant (`[^\d%]{0,40}`) since the exact spacing
# of the real rendered line could not be confirmed byte-exact from the
# binary -- only the label text and the `% used` suffix are directly
# evidenced.
SESSION_PCT_RE = re.compile(
    r"Current session[^\d%]{0,40}(\d{1,3})\s*%\s*used", re.IGNORECASE
)
WEEK_PCT_RE = re.compile(
    r"Current week \(all models\)[^\d%]{0,40}(\d{1,3})\s*%\s*used", re.IGNORECASE
)


@dataclass(frozen=True)
class UsagePercentages:
    """Best-effort session/week usage percentages from the `claude` CLI.

    Both fields default to `None` -- the "nothing available" empty state,
    mirroring how `usage_parser.TokenTotals` defaults to zero-valued. The
    two fields are independent: it's valid for one to be populated and the
    other `None` (e.g. only one line matched in the CLI's output).
    """

    session_pct: int | None = None
    week_pct: int | None = None


def _extract_pct(pattern: re.Pattern[str], text: str) -> int | None:
    """Return the matched percentage, or `None` if absent or out of range.

    A matched number outside the sane 0-100 range is treated defensively
    as no match (in case of a garbled future format) rather than being
    clamped or asserted.
    """
    match = pattern.search(text)
    if match is None:
        return None
    value = int(match.group(1))
    if value < 0 or value > 100:
        return None
    return value


def get_usage_percentages(timeout: float = 5.0) -> UsagePercentages:
    """Run `claude -p "/usage" --output-format json` and parse the result.

    Never raises. Every failure mode -- the `claude` binary not being on
    `PATH` (`FileNotFoundError`), the subprocess hanging
    (`subprocess.TimeoutExpired`), any other OS-level failure (`OSError`),
    stdout bytes that aren't valid text in the local codec
    (`UnicodeDecodeError`, which `subprocess.run(text=True)` can raise and
    which is a `ValueError` subclass, not an `OSError` subclass -- caught
    explicitly rather than assumed), a nonzero exit code, non-JSON stdout, a
    JSON value that isn't a dict, or a missing/non-string `"result"` field
    -- degrades to the empty `UsagePercentages()` rather than propagating an
    exception, per Constitution Principle VI and `research.md` R13.

    The outer `try`/`except Exception` is deliberate defense-in-depth on top
    of the specific handling below: `menubar_app._refresh()` calls this
    function with no try/except of its own (both on the 60s timer and once
    from `__init__`), so an uncaught exception here would not just skip the
    percentage rows -- it would also stop that `_refresh()` call from
    reaching `usage_parser.get_summary()`, breaking the FR-007 token totals
    too. Given that blast radius, this function's "never raises" contract
    must hold even against a failure mode nobody anticipated, not just the
    ones enumerated above.

    stderr is intentionally ignored: R13 found the CLI writes a one-line
    auth-source warning banner to stderr that must not be parsed as data.

    A nonzero exit code does not short-circuit parsing -- whatever stdout
    was produced is still attempted, and only falls back to empty if that
    also fails to yield usable JSON/text.
    """
    try:
        return _get_usage_percentages_unsafe(timeout)
    except Exception:  # noqa: BLE001 -- deliberate last-resort safety net,
        # see the docstring above: this function's "never raises" contract
        # must hold against failure modes nobody anticipated, not just the
        # specific ones `_get_usage_percentages_unsafe()` already handles.
        return UsagePercentages()


def _get_usage_percentages_unsafe(timeout: float) -> UsagePercentages:
    """The actual logic, with its own specific exception handling.

    Split out from `get_usage_percentages()` so the specific `except`
    clauses below stay meaningful documentation of the failure modes we
    actually expect, while the outer function's blanket `except Exception`
    is a last-resort safety net, not the primary handling mechanism.
    """
    try:
        completed = subprocess.run(
            ["claude", "-p", "/usage", "--output-format", "json"],
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError, UnicodeDecodeError):
        return UsagePercentages()

    try:
        payload = json.loads(completed.stdout)
    except (json.JSONDecodeError, ValueError):
        return UsagePercentages()

    if not isinstance(payload, dict):
        return UsagePercentages()

    result = payload.get("result")
    if not isinstance(result, str):
        return UsagePercentages()

    return UsagePercentages(
        session_pct=_extract_pct(SESSION_PCT_RE, result),
        week_pct=_extract_pct(WEEK_PCT_RE, result),
    )
