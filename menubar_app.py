"""Thin UI shell: a rumps status bar app displaying Claude Code usage.

Per `specs/001-menubar-usage-display/contracts/usage_parser.md`'s "UI-side
contract", this module performs no parsing, bucketing, or arithmetic on
usage data itself -- it only reads fields off `UsageSummary` (and the
`TokenTotals` it carries, via `.input`/`.output`/`.cache_read`/
`.cache_creation`/`.total`) and formats them via `usage_parser.format_tokens`.

The dropdown is populated at startup with four top-level line items (Today,
Current Session, Last 5 Hours, All Time), each showing that bucket's
combined-total token count. Per FR-007, the dropdown must also expose the
raw input/output/cache-read/cache-creation breakdown per bucket, not just
the combined total -- each of the four items is therefore also a submenu
(rumps' `MenuItem` doubles as a submenu container) holding four further
line items with that breakdown, so all five numbers per bucket (total,
input, output, cache read, cache creation) are present in the menu
structure. Per FR-008, when there is no local usage data at all
(`summary.entry_count == 0`), the four top-level items (and, with them,
their submenus) are hidden and replaced with a single explicit "No usage
data found" item instead of showing four all-zero rows.

Per FR-013, the dropdown also exposes two further stable top-level items --
Session Usage and Week Usage -- sourced from `usage_percentage.
get_usage_percentages()` rather than the local session logs. These are a
best-effort enhancement (Constitution Principle VI) entirely independent of
FR-008's empty-log-data state: they are updated on every `_refresh()` call
regardless of whether `summary.entry_count == 0`, and each is hidden
individually when its own field is `None` (e.g. it's valid for one to show
while the other stays hidden).
"""

import AppKit
import rumps

import usage_parser
import usage_percentage


class UsageMenuBarApp(rumps.App):
    """Menu bar app shell for displaying Claude Code usage."""

    def __init__(self):
        super().__init__(
            name="Claude Usage", icon="icon.png", template=True, quit_button="Quit"
        )

        # Created once with stable identities and added to self.menu exactly
        # once. `rumps.App.run()` appends a "Quit" MenuItem to this same
        # self.menu object when the event loop starts, so `_refresh()` must
        # never call `self.menu.clear()` (which would also wipe out Quit) --
        # it only ever mutates `.title`/`.hidden` on these existing items.
        #
        # `_make_bucket_item()` builds one top-level bucket MenuItem plus its
        # four breakdown children (Input, Output, Cache Read, Cache
        # Creation), added to the parent's own submenu exactly once here --
        # the same stable-item-created-once-updated-in-place pattern used
        # everywhere else in this class, just one level deeper. `_refresh()`
        # only ever mutates `.title` on the returned items afterward; it
        # never re-adds them, so it stays safe to call any number of times.
        self._today_item, self._today_children = self._make_bucket_item("Today")
        self._session_item, self._session_children = self._make_bucket_item(
            "Current Session"
        )
        self._rolling_5h_item, self._rolling_5h_children = self._make_bucket_item(
            "Last 5 Hours"
        )
        self._all_time_item, self._all_time_children = self._make_bucket_item(
            "All Time"
        )
        # Per FR-013: two further stable top-level items, sourced from
        # `usage_percentage.get_usage_percentages()` rather than the local
        # session logs (see the module docstring above). Each is toggled
        # independently via `.hidden`/`.show()`/`.hide()` in `_refresh()`,
        # the same stable-item-created-once pattern used for the four
        # bucket items above.
        self._session_pct_item = rumps.MenuItem("Session Usage")
        self._week_pct_item = rumps.MenuItem("Week Usage")
        # Per FR-008: shown instead of the four data items (which are
        # hidden, not removed -- see `_refresh()`) when there is no local
        # usage data at all. Kept as a stable item alongside the four data
        # items, toggled via rumps.MenuItem's `.hidden`/`.show()`/`.hide()`,
        # rather than adding/removing menu entries, for the same reason
        # `.title` is used instead of `self.menu.clear()` above.
        self._empty_state_item = rumps.MenuItem("No usage data found")
        # Manual on-demand refresh (US2/T018), invoking the same `_refresh()`
        # the timer calls. Added to `self.menu` here -- before `run()` later
        # appends "Quit" to this same `self.menu` object -- so it lands
        # directly above Quit. A `rumps.separator` visually distinguishes it
        # from the four data rows above it (a small, low-cost addition; not
        # explicitly required by the task).
        self._refresh_item = rumps.MenuItem(
            "Refresh", callback=self._on_refresh_clicked
        )
        self.menu = [
            self._today_item,
            self._session_item,
            self._rolling_5h_item,
            self._all_time_item,
            self._empty_state_item,
            self._session_pct_item,
            self._week_pct_item,
            rumps.separator,
            self._refresh_item,
        ]

        self._refresh()

        # Per `research.md` R10: a 60 s `rumps.Timer` keeps the dropdown
        # current without user interaction (US2), on top of the immediate
        # refresh above so the menu is never empty at launch. `rumps.Timer`
        # runs on the main run loop (the same one `rumps.App.run()` later
        # drives via `AppHelper.runEventLoop()`), so this reuses the same
        # thread-safe `_refresh()` and requires no locking. Unlike the
        # `@rumps.timer` decorator (which only auto-starts timers registered
        # on a module-level list when `App.run()` is called), a `Timer`
        # built directly like this must be started explicitly -- done here,
        # in `__init__`, rather than in `run()`, so the timer is armed as
        # soon as the app object exists.
        self._timer = rumps.Timer(self._on_timer, 60)
        self._timer.start()

    @staticmethod
    def _make_bucket_item(label):
        """Build one top-level bucket `MenuItem` with a four-item submenu.

        Per FR-007, each bucket must expose all five numbers (total, input,
        output, cache read, cache creation), not just the combined total.
        The combined total stays on the parent item's own title (as
        before, preserving the at-a-glance "Today: 1.2K" style line); the
        four category breakdowns live in a submenu attached to that same
        item -- rumps' `MenuItem` is itself a `Menu` subclass, so any child
        `MenuItem`s `.add()`ed to it are rendered as a fly-out submenu.

        Called exactly once per bucket, from `__init__`, so the four child
        items are added to the parent's submenu exactly once; `_refresh()`
        only ever updates their `.title` afterward. Returns
        `(parent_item, (input_item, output_item, cache_read_item,
        cache_creation_item))`.
        """
        parent = rumps.MenuItem(label)
        input_item = rumps.MenuItem("Input")
        output_item = rumps.MenuItem("Output")
        cache_read_item = rumps.MenuItem("Cache Read")
        cache_creation_item = rumps.MenuItem("Cache Creation")
        parent.add(input_item)
        parent.add(output_item)
        parent.add(cache_read_item)
        parent.add(cache_creation_item)
        return parent, (input_item, output_item, cache_read_item, cache_creation_item)

    @staticmethod
    def _update_bucket(parent_item, children, label, totals):
        """Update one bucket's parent title and its four submenu children.

        `totals` is a `usage_parser.TokenTotals` (or duck-typed equivalent)
        already computed by the pure core; this only reads its
        `.total`/`.input`/`.output`/`.cache_read`/`.cache_creation` fields
        and passes each straight to `usage_parser.format_tokens()` -- no
        arithmetic happens here, per the UI-side contract.
        """
        input_item, output_item, cache_read_item, cache_creation_item = children
        parent_item.title = f"{label}: {usage_parser.format_tokens(totals.total)}"
        input_item.title = f"Input: {usage_parser.format_tokens(totals.input)}"
        output_item.title = f"Output: {usage_parser.format_tokens(totals.output)}"
        cache_read_item.title = (
            f"Cache Read: {usage_parser.format_tokens(totals.cache_read)}"
        )
        cache_creation_item.title = (
            f"Cache Creation: {usage_parser.format_tokens(totals.cache_creation)}"
        )

    def _update_percentages(self, percentages):
        """Update the two FR-013 percentage items from a
        `usage_percentage.UsagePercentages`.

        Reads only its two fields (`.session_pct`/`.week_pct`) and formats
        each into a title -- no parsing or arithmetic happens here, per the
        UI-side contract. Each item is shown/hidden independently of the
        other: a `None` field hides that item, an `int` field (including
        `0`) shows it with the formatted percentage.
        """
        if percentages.session_pct is None:
            self._session_pct_item.hide()
        else:
            self._session_pct_item.title = (
                f"Session Usage: {percentages.session_pct}% used"
            )
            self._session_pct_item.show()

        if percentages.week_pct is None:
            self._week_pct_item.hide()
        else:
            self._week_pct_item.title = f"Week Usage: {percentages.week_pct}% used"
            self._week_pct_item.show()

    def _on_timer(self, sender):
        """`rumps.Timer` callback (passed the `Timer` instance itself, per
        rumps' API): just re-runs `_refresh()` to keep the dropdown current.
        """
        self._refresh()

    def _on_refresh_clicked(self, sender):
        """`rumps.MenuItem` click callback (passed the `MenuItem` instance
        itself, per rumps' API) for the manual "Refresh" menu item: re-runs
        the same `_refresh()` the 60 s timer calls, for on-demand updates
        without waiting (US2/T018).
        """
        self._refresh()

    def _refresh(self):
        """Recompute usage and update the dropdown's line items in place.

        Calls `usage_parser.get_summary()` and updates the four existing
        top-level `MenuItem` instances -- Today, Current Session, Last 5
        Hours, All Time -- and, per FR-007, each of their four submenu
        children (Input, Output, Cache Read, Cache Creation), via
        `_update_bucket()`. Performs no arithmetic of its own; every
        displayed number is a field read off the returned `UsageSummary`'s
        `TokenTotals` (`.total`/`.input`/`.output`/`.cache_read`/
        `.cache_creation`) passed straight to `usage_parser.format_tokens()`.

        Per FR-008: when `summary.entry_count == 0` (no local Claude Code
        session data at all), the four top-level items (and, with them,
        their submenus) are hidden and the `_empty_state_item` ("No usage
        data found") is shown instead, rather than displaying four rows
        that would otherwise all read zero. Otherwise the four top-level
        items are shown and the empty-state item is hidden.

        Deliberately updates `.title`/`.hidden` on the existing items
        (added to `self.menu`, or to a bucket item's own submenu, exactly
        once, in `__init__`) rather than clearing and rebuilding the menu:
        `self.menu.clear()` would also remove the "Quit" item that
        `rumps.App.run()` adds to this same `self.menu` once the event
        loop starts. Kept as its own method (rather than inlined in
        `__init__`) so a periodic timer can call it again to keep the
        dropdown current -- safely, any number of times, before or after
        `run()`.

        Per FR-013: also calls `usage_percentage.get_usage_percentages()`
        and updates `_session_pct_item`/`_week_pct_item` via
        `_update_percentages()`, unconditionally and before the
        FR-008 empty-log-data early return below -- the percentage figures
        come from the `claude` CLI, not the local session logs, so they
        must stay entirely independent of whether any local usage data
        exists.
        """
        self._update_percentages(usage_percentage.get_usage_percentages())

        summary = usage_parser.get_summary()

        if summary.entry_count == 0:
            self._today_item.hide()
            self._session_item.hide()
            self._rolling_5h_item.hide()
            self._all_time_item.hide()
            self._empty_state_item.show()
            return

        self._empty_state_item.hide()
        self._today_item.show()
        self._session_item.show()
        self._rolling_5h_item.show()
        self._all_time_item.show()

        self._update_bucket(
            self._today_item, self._today_children, "Today", summary.today
        )
        self._update_bucket(
            self._session_item,
            self._session_children,
            "Current Session",
            summary.current_session,
        )
        self._update_bucket(
            self._rolling_5h_item,
            self._rolling_5h_children,
            "Last 5 Hours",
            summary.rolling_5h,
        )
        self._update_bucket(
            self._all_time_item, self._all_time_children, "All Time", summary.all_time
        )

    def run(self, **options):
        """Run the app as a Dock-less accessory process, then start rumps.

        Per FR-002, the app MUST NOT present a Dock icon or a regular
        application window. `rumps.App.run()` is what actually creates the
        underlying `NSApplication` (via `NSApplication.sharedApplication()`)
        -- it is *not* created during `App.__init__`, so the activation
        policy can only be set here (or later), not in `__init__`.
        `NSApplication.sharedApplication()` is a singleton accessor: calling
        it here first and setting the activation policy to "accessory"
        before delegating to `rumps.App.run()` (which calls
        `sharedApplication()` again and gets the same instance) is the
        runtime equivalent of setting `LSUIElement: True` in an Info.plist,
        without requiring an app bundle.
        """
        AppKit.NSApplication.sharedApplication().setActivationPolicy_(
            AppKit.NSApplicationActivationPolicyAccessory
        )
        super().run(**options)


if __name__ == "__main__":
    UsageMenuBarApp().run()
