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

Per `research.md` R15: this module resolves the `claude` binary by an
absolute path rather than relying on a bare `"claude"` argv[0] and PATH
lookup, because the app is sometimes launched via an Automator "Run Shell
Script" wrapper (see README's "Optional: Launchpad shortcut" section) whose
process environment does not inherit the user's login-shell PATH/`.zshrc`
-- a bare `"claude"` silently resolves to nothing in that context, which
(per Principle VI) degrades to "no percentage available" without crashing,
but also never obtains real data, defeating the point of the feature. See
`_resolve_claude_binary()` for the fallback chain.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from dataclasses import dataclass

# Per `research.md` R15: the confirmed real path of the Homebrew-installed
# `claude` binary on the machine this project is developed on (Apple
# Silicon). A plain named constant, not an environment-variable-driven
# config surface -- Constitution Principle V rejects configurable-backend
# complexity for what is a single-machine personal tool; "configurable"
# here just means "a named constant in one obvious place," not something
# meant to vary at runtime. `_resolve_claude_binary()` below still falls
# back to a PATH lookup for other install locations (e.g. Intel Homebrew's
# `/usr/local/bin/claude`, or any environment where PATH genuinely does
# include it), so this constant does not need to be exhaustive.
CLAUDE_BINARY_PATH = "/opt/homebrew/bin/claude"

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

# Per `research.md` R13's follow-up addendum: the owner has since observed
# the real `/usage` output reports each reset as an absolute clock
# time/date (e.g. "8:10pm", "Aug 9, 12pm"), not the relative "resets in Xd
# Yh" phrasing R13's fixtures originally guessed. These regexes are
# intentionally as permissive/tolerant as `SESSION_PCT_RE`/`WEEK_PCT_RE`
# (arguably more so, since the reset phrasing is even less confirmed): each
# is anchored to its own label, `.search()`ed against that label's own
# line only (`[^\n)]+` cannot cross a newline into the other bucket's
# line), and captures everything after "resets" (optionally "resets at")
# up to end of line or a closing paren. Independent of the percentage
# match and of each other -- a missing reset phrase for one or both is a
# normal, valid outcome, not a parse failure.
SESSION_RESET_RE = re.compile(
    r"Current session.*?resets\s+(?:at\s+)?([^\n)]+)", re.IGNORECASE
)
WEEK_RESET_RE = re.compile(
    r"Current week \(all models\).*?resets\s+(?:at\s+)?([^\n)]+)", re.IGNORECASE
)


@dataclass(frozen=True)
class UsagePercentages:
    """Best-effort session/week usage percentages from the `claude` CLI.

    All four fields default to `None` -- the "nothing available" empty
    state, mirroring how `usage_parser.TokenTotals` defaults to
    zero-valued. Each field is independent: it's valid for any subset to
    be populated while the rest stay `None` (e.g. a percentage matched but
    its reset phrase didn't, or only one bucket's line matched at all).

    `session_reset`/`week_reset` hold the raw reset text as reported by
    the CLI (e.g. `"8:10pm"` or `"Aug 9, 12pm"`), with no leading
    `resets`/`at` word and no surrounding parens -- just the time/date
    text itself, so callers can format it directly (e.g.
    `f"(Resets {reset})"`).
    """

    session_pct: int | None = None
    week_pct: int | None = None
    session_reset: str | None = None
    week_reset: str | None = None


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


def _extract_reset(pattern: re.Pattern[str], text: str) -> str | None:
    """Return the matched reset text (stripped), or `None` if absent.

    A match that strips down to an empty string is treated the same as no
    match -- defensively, since an empty reset string would be a useless
    (and mildly confusing) thing to attach a "(Resets )" prefix to.
    """
    match = pattern.search(text)
    if match is None:
        return None
    value = match.group(1).strip()
    return value or None


def _resolve_claude_binary() -> str | None:
    """Resolve the `claude` binary to an absolute path, or `None` if it
    cannot be found anywhere.

    Per `research.md` R15: this exists because a bare `"claude"` argv[0]
    relies on `subprocess.run`'s own PATH lookup, which silently fails when
    this app is launched via an Automator "Run Shell Script" wrapper (see
    README's "Optional: Launchpad shortcut" section) -- that launch path
    does not inherit the user's login-shell PATH/`.zshrc`, so `"claude"`
    resolves to nothing even though it's installed and would resolve fine
    from a normal Terminal session.

    Fallback chain: (1) `CLAUDE_BINARY_PATH`, the confirmed Homebrew
    Apple-Silicon install location, if it exists on disk and is executable;
    (2) `shutil.which("claude")`, which still consults the calling
    process's actual PATH and so covers other install locations (e.g.
    Intel Homebrew's `/usr/local/bin/claude`) or environments where PATH
    genuinely does include it; (3) `None` if neither yields a usable path.
    """
    if os.path.isfile(CLAUDE_BINARY_PATH) and os.access(CLAUDE_BINARY_PATH, os.X_OK):
        return CLAUDE_BINARY_PATH
    return shutil.which("claude")


def get_usage_percentages(timeout: float = 5.0) -> UsagePercentages:
    """Resolve the `claude` binary (see `_resolve_claude_binary()` and
    `research.md` R15), run `claude -p "/usage" --output-format json`, and
    parse the result.

    Never raises. Every failure mode -- the `claude` binary not being
    resolvable at all (see `_resolve_claude_binary()`), the resolved path
    disappearing before exec (`FileNotFoundError`), the subprocess hanging
    (`subprocess.TimeoutExpired`), any other OS-level failure (`OSError`),
    stdout bytes that aren't valid text in the local codec
    (`UnicodeDecodeError`, which `subprocess.run(text=True)` can raise and
    which is a `ValueError` subclass, not an `OSError` subclass -- caught
    explicitly rather than assumed), a nonzero exit code, non-JSON stdout, a
    JSON value that isn't a dict, or a missing/non-string `"result"` field
    -- degrades to the empty `UsagePercentages()` rather than propagating an
    exception, per Constitution Principle VI and `research.md` R13/R15.

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

    Per `research.md` R15: resolves the `claude` binary to an absolute path
    via `_resolve_claude_binary()` first. If that returns `None`, there is
    no binary to run at all, so this returns the empty `UsagePercentages()`
    immediately without even attempting `subprocess.run()` -- per
    Constitution Principle VI this is a normal, expected degradation, not
    an error. Otherwise the resolved absolute path is passed as argv[0]
    instead of the literal string `"claude"`.
    """
    claude_binary = _resolve_claude_binary()
    if claude_binary is None:
        return UsagePercentages()

    try:
        completed = subprocess.run(
            [claude_binary, "-p", "/usage", "--output-format", "json"],
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError, UnicodeDecodeError):
        # Defense-in-depth: e.g. a race where the resolved path stops
        # existing between `_resolve_claude_binary()`'s check and this
        # exec, or a permissions problem not caught by `os.access()` above.
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
        session_reset=_extract_reset(SESSION_RESET_RE, result),
        week_reset=_extract_reset(WEEK_RESET_RE, result),
    )
