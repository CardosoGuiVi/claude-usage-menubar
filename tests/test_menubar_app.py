"""Unit tests for `menubar_app.UsageMenuBarApp`'s menu-building logic.

Per `research.md` R11, the MVP deliberately has no automated tests that
drive a real `NSApplication` event loop (that remains manual/empirical, as
documented in `specs/001-menubar-usage-display/tasks.md` T016/T019 and
verified by whoever implements a `menubar_app.py` change). These tests do
not call `rumps.App.run()` — `rumps.App.__init__` never touches the real
menu bar (`NSStatusItem` is only created inside `run()`, see
`.venv/.../rumps/rumps.py`'s `App.run()`), so `UsageMenuBarApp()` can be
instantiated and its `_refresh()` called directly, off the real event
loop, without spinning up any UI. That keeps these tests fast and
non-flaky while still exercising real `rumps.MenuItem`/`Menu` objects
(not mocks), matching this project's "pure core / thin UI" boundary: only
`menubar_app`'s own menu-construction and title-updating logic is under
test here — `usage_parser.get_summary()` itself is monkeypatched so these
tests are independent of any real local Claude Code session data.
"""

from __future__ import annotations

from unittest import mock

import pytest
from rumps.rumps import SeparatorMenuItem

import menubar_app
import usage_parser
import usage_percentage
from usage_parser import TokenTotals, UsageSummary
from usage_percentage import UsagePercentages


def _make_summary() -> UsageSummary:
    """A non-empty `UsageSummary` with distinct values per bucket/category
    so a title mismatch in any of the 20 rendered numbers is unambiguous.
    """
    return UsageSummary(
        today=TokenTotals(input=1, output=2, cache_read=3, cache_creation=4),
        current_session=TokenTotals(
            input=10, output=20, cache_read=30, cache_creation=40
        ),
        rolling_5h=TokenTotals(
            input=100, output=200, cache_read=300, cache_creation=400
        ),
        all_time=TokenTotals(
            input=1000, output=2000, cache_read=3000, cache_creation=4000
        ),
        current_session_id="session-1",
        entry_count=1,
    )


@pytest.fixture
def app():
    """A `UsageMenuBarApp` instantiated with a stubbed `get_summary()`.

    Patches `usage_parser.get_summary` for the duration of each test (the
    same function object `menubar_app` calls, per the module-level `import
    usage_parser` + `usage_parser.get_summary()` call convention already
    used throughout `menubar_app.py`) so no real local session log data is
    read. Also patches `usage_percentage.get_usage_percentages` (same
    `mock.patch.object(...)` style) so no real `claude` subprocess is
    invoked, defaulting to an empty `UsagePercentages()` -- individual
    FR-013 tests below override this via a nested `mock.patch.object` call.
    `UsageMenuBarApp.__init__` calls `_refresh()` once already, so the
    returned app is immediately populated from `_make_summary()`.
    """
    with (
        mock.patch.object(usage_parser, "get_summary", return_value=_make_summary()),
        mock.patch.object(
            usage_percentage, "get_usage_percentages", return_value=UsagePercentages()
        ),
    ):
        yield menubar_app.UsageMenuBarApp()


def test_menu_order_session_week_then_buckets_then_refresh(app):
    """FR-013 follow-up: Session/Week must lead the dropdown, separated
    from the four FR-007 buckets (plus the FR-008 empty-state item) by a
    separator, which is itself separated from Refresh -- Quit is appended
    later by `rumps.App.run()`, so it is not part of this app-side list.
    """
    items = list(app.menu.values())

    assert items[0] is app._session_pct_item
    assert items[1] is app._week_pct_item
    assert isinstance(items[2], SeparatorMenuItem)
    assert items[3] is app._today_item
    assert items[4] is app._session_item
    assert items[5] is app._rolling_5h_item
    assert items[6] is app._all_time_item
    assert items[7] is app._empty_state_item
    assert isinstance(items[8], SeparatorMenuItem)
    assert items[9] is app._refresh_item


def test_timer_interval_is_5_minutes(app):
    """Per `research.md` R14, the single `rumps.Timer` that drives
    `_refresh()` (both the FR-007 token totals and the FR-013 percentages
    share it) must be widened to a 300 s (5 min) cadence.
    """
    assert app._timer.interval == 300


def test_session_and_week_items_are_not_disabled(app):
    """These two items must render enabled/normal-colored, not
    greyed-out -- a `MenuItem` created with no `callback` renders
    disabled in Cocoa (`setAction_(None)`), so both must have a callback
    (even a no-op one) set at construction time.
    """
    assert app._session_pct_item.callback is not None
    assert app._week_pct_item.callback is not None


def test_all_four_buckets_expose_five_numbers_each(app):
    """FR-007: each bucket must show total, input, output, cache read, and
    cache creation -- five numbers, not just the combined total.
    """
    buckets = [
        ("Today", app._today_item, app._today_children, _make_summary().today),
        (
            "Current Session",
            app._session_item,
            app._session_children,
            _make_summary().current_session,
        ),
        (
            "Last 5 Hours",
            app._rolling_5h_item,
            app._rolling_5h_children,
            _make_summary().rolling_5h,
        ),
        (
            "All Time",
            app._all_time_item,
            app._all_time_children,
            _make_summary().all_time,
        ),
    ]

    data_points = 0
    for label, parent, children, totals in buckets:
        assert parent.title == f"{label}: {usage_parser.format_tokens(totals.total)}"
        assert len(children) == 4
        input_item, output_item, cache_read_item, cache_creation_item = children
        assert input_item.title == f"Input: {usage_parser.format_tokens(totals.input)}"
        assert (
            output_item.title == f"Output: {usage_parser.format_tokens(totals.output)}"
        )
        assert (
            cache_read_item.title
            == f"Cache Read: {usage_parser.format_tokens(totals.cache_read)}"
        )
        assert (
            cache_creation_item.title
            == f"Cache Creation: {usage_parser.format_tokens(totals.cache_creation)}"
        )
        data_points += 5  # total + 4 categories

    assert data_points == 20


def test_submenu_children_added_exactly_once_across_repeated_refresh(app):
    """Repeated `_refresh()` calls must update titles in place, never
    re-add submenu children (which would duplicate/leak menu items) --
    the same stable-item invariant already relied on for the four
    top-level items.
    """
    assert len(list(app._today_item.values())) == 4

    for _ in range(5):
        app._refresh()

    assert len(list(app._today_item.values())) == 4
    assert len(list(app._session_item.values())) == 4
    assert len(list(app._rolling_5h_item.values())) == 4
    assert len(list(app._all_time_item.values())) == 4


def test_empty_state_hides_buckets_and_shows_empty_item(app):
    """FR-008: when there is no local usage data at all, the four
    top-level bucket items (and, with them, their submenus) are hidden and
    the explicit empty-state item is shown instead.
    """
    with mock.patch.object(
        usage_parser, "get_summary", return_value=UsageSummary(entry_count=0)
    ):
        app._refresh()

    assert app._today_item.hidden
    assert app._session_item.hidden
    assert app._rolling_5h_item.hidden
    assert app._all_time_item.hidden
    assert not app._empty_state_item.hidden

    # Submenu children survive untouched (not removed/duplicated) even
    # while their parent is hidden.
    assert len(list(app._today_item.values())) == 4


def test_empty_state_then_real_data_restores_buckets(app):
    """Recovering from the empty state on a later refresh (e.g. the user's
    first session just got written) must re-show the bucket items and the
    empty-state item must hide again, without leaking extra menu items.
    """
    with mock.patch.object(
        usage_parser, "get_summary", return_value=UsageSummary(entry_count=0)
    ):
        app._refresh()

    with mock.patch.object(usage_parser, "get_summary", return_value=_make_summary()):
        app._refresh()

    assert not app._today_item.hidden
    assert app._empty_state_item.hidden
    assert app._today_item.title == "Today: 10"
    assert len(list(app._today_item.values())) == 4


class TestUsagePercentages:
    """FR-013: session/week usage percentages from `usage_percentage`."""

    def test_both_percentages_present_with_resets(self, app):
        with mock.patch.object(
            usage_percentage,
            "get_usage_percentages",
            return_value=UsagePercentages(
                session_pct=45,
                week_pct=12,
                session_reset="8:10pm",
                week_reset="Aug 9, 12pm",
            ),
        ):
            app._refresh()

        assert app._session_pct_item.title == "Session: 45% used  (Resets 8:10pm)"
        assert not app._session_pct_item.hidden
        assert app._week_pct_item.title == "Week: 12% used  (Resets Aug 9, 12pm)"
        assert not app._week_pct_item.hidden
        assert app.title == "45% · 12%"

    def test_both_percentages_present_without_resets(self, app):
        """A percentage with no reset text (e.g. the CLI didn't report
        one) must render without a "(Resets ...)" clause at all, not a
        clause with an empty/placeholder value.
        """
        with mock.patch.object(
            usage_percentage,
            "get_usage_percentages",
            return_value=UsagePercentages(session_pct=45, week_pct=12),
        ):
            app._refresh()

        assert app._session_pct_item.title == "Session: 45% used"
        assert app._week_pct_item.title == "Week: 12% used"

    def test_only_session_present_week_hidden(self, app):
        with mock.patch.object(
            usage_percentage,
            "get_usage_percentages",
            return_value=UsagePercentages(session_pct=0, week_pct=None),
        ):
            app._refresh()

        # 0% must still show (falsy-but-not-missing), not be hidden.
        assert app._session_pct_item.title == "Session: 0% used"
        assert not app._session_pct_item.hidden
        assert app._week_pct_item.hidden
        # Partial availability: keep the two-part shape, em dash for the
        # missing side, so it's unambiguous which slot is which.
        assert app.title == "0% · –"

    def test_only_week_present_session_hidden(self, app):
        with mock.patch.object(
            usage_percentage,
            "get_usage_percentages",
            return_value=UsagePercentages(session_pct=None, week_pct=99),
        ):
            app._refresh()

        assert app._session_pct_item.hidden
        assert app._week_pct_item.title == "Week: 99% used"
        assert not app._week_pct_item.hidden
        assert app.title == "– · 99%"

    def test_both_none_hides_both_items(self, app):
        with mock.patch.object(
            usage_percentage,
            "get_usage_percentages",
            return_value=UsagePercentages(session_pct=None, week_pct=None),
        ):
            app._refresh()

        assert app._session_pct_item.hidden
        assert app._week_pct_item.hidden
        # Both missing: fall back to icon-only, no title text at all --
        # not an empty string and not a two-dash placeholder.
        assert app.title is None

    def test_percentages_update_independently_of_empty_log_data(self, app):
        """FR-013's percentages must not be skipped by FR-008's early return
        for `summary.entry_count == 0` -- they come from the `claude` CLI,
        not local session logs, so they update even when local usage data
        is entirely absent.
        """
        with (
            mock.patch.object(
                usage_parser, "get_summary", return_value=UsageSummary(entry_count=0)
            ),
            mock.patch.object(
                usage_percentage,
                "get_usage_percentages",
                return_value=UsagePercentages(session_pct=7, week_pct=3),
            ),
        ):
            app._refresh()

        # FR-008 empty-log-data state still applies to the bucket items...
        assert app._today_item.hidden
        assert not app._empty_state_item.hidden
        # ...but the percentage items are unaffected by it.
        assert app._session_pct_item.title == "Session: 7% used"
        assert not app._session_pct_item.hidden
        assert app._week_pct_item.title == "Week: 3% used"
        assert not app._week_pct_item.hidden
        assert app.title == "7% · 3%"
