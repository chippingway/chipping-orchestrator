# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What one page load reads, in which wave, and under which key.

Streamlit lives in the optional `dashboard` dependency group, so the cases
below hand a wave a stand-in that records what it was asked to cache and hands
each reader back unwrapped -- which is the whole of what this owner reaches
Streamlit for. That is also what makes a built task readable: the callable in
it is the adapter with its arguments already bound, so a case can name the read
an entry spends its key on rather than standing a database up to watch rows
come back.

The keys are built by the filter and window owners rather than written out
here, because what a wave owes a page is its own keys passed through untouched
-- hand-rolled tuples would keep passing after the two spellings drifted apart.
"""

from __future__ import annotations

import unittest
from collections.abc import Callable
from types import MappingProxyType
from typing import Any

from orchestrator.observability.dashboard import (
    breakdowns,
    filters,
    read_plan,
    rollups,
    skills,
    windows,
)
from tests.observability.dashboard.dashboard_test_support import MAY22, MAY28

_REPO = "acme/widgets"

_EVENTS = ("agent_exit", "stage_enter")

_ISSUE = 42

_TZ_OFFSET = 7

# How many reads one page load issues across both waves.
_TOTAL_READS = 17

_TTL_ONE_MINUTE = 60

_HEATMAP_READ = "heatmap_rows"

# What one entry is named where the name itself is not what is under test.
_TASK_NAME = "one_read"

# What a page load's own timer read when it started, which the plan carries so
# the load line can be logged against it.
_STARTED_AT = 12.5

_CACHE_OPTIONS = MappingProxyType({
    "show_spinner": False,
    "ttl": _TTL_ONE_MINUTE,
})

# The window a run reports over, and the two keys its reads are stored under:
# the run's own filters hashed over that window, and over the equal-length span
# before it.
_WINDOW = windows.to_window(MAY22, MAY28)

_KEY = filters.cache_key(_WINDOW, _REPO, _EVENTS, None, _ISSUE)

_PREV_KEY = filters.cache_key(
    windows.previous_window(_WINDOW),
    _REPO,
    _EVENTS,
    None,
    _ISSUE,
)

# What a page hands an adapter: its own key and nothing else, for every entry
# but the heatmap.
_KEY_ONLY = (_KEY,)

# Every entry of the first wave: the name its result is read back by, the
# adapter it spends a key on, and the arguments bound into it. These seven are
# the reads the chrome above the fold -- the Cost details section among it -- is
# reduced from, so they are what has to come back before the page can paint
# anything.
_FIRST_WAVE = (
    ("summary", rollups.read_summary, _KEY_ONLY),
    ("prev_summary", rollups.read_prev_kpi, (_PREV_KEY,)),
    ("ts_points", rollups.read_time_series, _KEY_ONLY),
    ("review_round_rows", rollups.read_review_round, _KEY_ONLY),
    ("throughput_rows", breakdowns.read_throughput, _KEY_ONLY),
    ("cost_coverage_rows", breakdowns.read_cost_coverage, _KEY_ONLY),
    ("unpriced_reason_rows", breakdowns.read_unpriced_reasons, _KEY_ONLY),
)

# The ten the panels beneath that chrome are drawn from. The heatmap is the one
# entry with a second bound argument: the display offset decides which cell a
# row is counted into rather than which rows the window holds.
_SECOND_WAVE = (
    ("stage_rows", rollups.read_stage_breakdown, _KEY_ONLY),
    ("agent_exits", rollups.read_recent_agent_exits, _KEY_ONLY),
    ("issues_rows", rollups.read_top_cost_issues, _KEY_ONLY),
    ("backend_rows", breakdowns.read_backend_efficiency, _KEY_ONLY),
    ("repo_rows", breakdowns.read_repo_breakdown, _KEY_ONLY),
    (_HEATMAP_READ, breakdowns.read_hourly_heatmap, (_KEY, _TZ_OFFSET)),
    ("backend_daily_rows", breakdowns.read_backend_daily_tokens, _KEY_ONLY),
    ("skill_adoption_rows", skills.read_skill_adoption, _KEY_ONLY),
    ("skill_rows", skills.read_skill_trigger_rates, _KEY_ONLY),
    ("skill_matrix_rows", skills.read_skill_trigger_matrix, _KEY_ONLY),
)


class _FakeStreamlit:
    """The cache this owner reaches Streamlit for, and nothing else.

    A wave builder that wrote to the page would reach for `markdown`, `info`,
    or `plotly_chart` here and raise `AttributeError`: a parallel load runs
    these readers on worker threads, and only the main thread rendering
    between the two waves may write.
    """

    def __init__(self) -> None:
        self.cache_options: list[dict[str, Any]] = []

    def cache_data(self, **cache_options: Any) -> Callable[..., Any]:
        self.cache_options.append(cache_options)

        def decorator(reader: Callable[..., Any]) -> Callable[..., Any]:
            return reader

        return decorator


def _bound(wave: Any) -> list[tuple[str, Any, tuple]]:
    """Each task as the name, adapter, and arguments it was built with."""
    return [(name, task.func, task.args) for name, task in wave]


class _WaveSupport(unittest.TestCase):
    """Builds one page load's waves against a recording stand-in."""

    def _waves(self, tz_offset: Any = _TZ_OFFSET) -> Any:
        self.st = _FakeStreamlit()
        return read_plan.widget_readers(
            st=self.st,
            key=_KEY,
            prev_key=_PREV_KEY,
            tz_offset_choice=tz_offset,
        )


class WaveRegistryTest(_WaveSupport):
    """Which read each entry of a wave spends its key on, and in what order."""

    def test_the_first_wave_names_its_seven_reads(self) -> None:
        # The pair comes back above-the-fold first, because the caller renders
        # the chrome between the waves: swapping the two would leave the topbar
        # waiting on the ten panel reads it does not draw from.
        first_wave, _second_wave = self._waves()

        self.assertEqual(_bound(first_wave), list(_FIRST_WAVE))

    def test_the_second_wave_names_its_ten_reads(self) -> None:
        _first_wave, second_wave = self._waves()

        self.assertEqual(_bound(second_wave), list(_SECOND_WAVE))

    def test_the_heatmap_offset_is_whole_hours(self) -> None:
        # The offset arrives off a Streamlit selector, so it is narrowed to
        # hours before it is bound: a float in the key would make one wave's
        # heatmap a cache miss against the next on the same chosen zone.
        _first_wave, second_wave = self._waves(tz_offset=float(_TZ_OFFSET))

        offset = dict(second_wave)[_HEATMAP_READ].args[-1]
        self.assertIsInstance(offset, int)
        self.assertEqual(offset, _TZ_OFFSET)

    def test_every_task_is_cached_for_a_minute(self) -> None:
        # Streamlit reruns the whole script on every widget interaction, so an
        # uncached wave would put all seventeen queries on Postgres for each
        # nudge of the filter bar -- and without a spinner, because the load
        # is already bracketed by one the caller opens.
        self._waves()

        self.assertEqual(len(self.st.cache_options), _TOTAL_READS)
        for cache_options in self.st.cache_options:
            self.assertEqual(cache_options, _CACHE_OPTIONS)

    def test_the_declared_ttl_is_one_minute(self) -> None:
        # Pinned so a change to the span is a deliberate one: an unchanged
        # window goes back to Postgres on the first rerun after the minute is
        # up, so newly synced events reach a page within one -- and until then
        # tapping through the filter bar does not re-read every panel.
        self.assertEqual(read_plan.WIDGET_CACHE_TTL_SECONDS, _TTL_ONE_MINUTE)


class WidgetTaskTest(unittest.TestCase):
    """One entry of a wave: a name, and a read that has not happened yet."""

    def test_a_task_defers_its_read(self) -> None:
        # Building a wave must not issue anything: the caller hands the tasks
        # to the fan-out, which is what decides whether they run here or on a
        # pool, and a read issued during construction would run on neither.
        issued = []
        name, task = read_plan.widget_task(
            _FakeStreamlit(), _TASK_NAME, issued.append, _KEY,
        )

        self.assertEqual(name, _TASK_NAME)
        self.assertEqual(issued, [])

        task()

        self.assertEqual(issued, [_KEY])


class ReadKeyTest(unittest.TestCase):
    """The pair of keys a load's reads are stored under."""

    def test_current_and_previous_keys(self) -> None:
        # The delta pills and the cost-trend banner report this window against
        # the one before it, so both keys carry the same selections: a filter
        # applied to one of the two spans would compare unlike windows.
        key, prev_key = read_plan.build_read_keys(
            window=_WINDOW,
            repo_filter=_REPO,
            event_filter=list(_EVENTS),
            stage_filter=None,
            issue_filter=_ISSUE,
        )

        earlier = windows.previous_window(_WINDOW)
        self.assertEqual(
            key,
            (_WINDOW.start, _WINDOW.end, _REPO, _EVENTS, None, _ISSUE),
        )
        self.assertEqual(
            prev_key,
            (earlier.start, earlier.end, _REPO, _EVENTS, None, _ISSUE),
        )


class ReadPlanTest(_WaveSupport):
    """What the plan a page load is described by reports about itself."""

    def test_the_plan_counts_both_waves(self) -> None:
        # The load line is logged against this number, so a read added to
        # either wave has to be counted by it rather than by a literal.
        first_wave, second_wave = self._waves()

        plan = read_plan.DashboardReadPlan(
            first_wave=first_wave,
            second_wave=second_wave,
            parallel=False,
            started_at=_STARTED_AT,
        )

        self.assertEqual(plan.total_reads, _TOTAL_READS)


if __name__ == "__main__":
    unittest.main()
