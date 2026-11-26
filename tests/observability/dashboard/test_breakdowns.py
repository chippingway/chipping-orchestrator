# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Which read a comparison panel is drawn from, and under which key.

An adapter here settles two things and nothing else: the query owner's read a
panel is answered by, and the key that read is issued under. So the cases below
patch the binding both travel through and read back what was handed to it,
rather than standing a database up to observe the same two facts through rows.

The key is built by the filter owner rather than written out here, because what
an adapter owes a page is its own key passed through untouched -- a hand-rolled
tuple would keep passing after the two spellings drifted apart.
"""

from __future__ import annotations

import inspect
import unittest
from typing import Any
from unittest.mock import patch

from orchestrator.observability.analytics.query import breakdown_reads, rollup_reads
from orchestrator.observability.dashboard import (
    breakdowns,
    filter_binding,
    filters,
    windows,
)
from tests.observability.dashboard.dashboard_test_support import (
    MAY01,
    MAY07,
    utc_midnight,
)

_REPO = "owner/repo"

_EVENTS = ("stage_entered", "agent_exit")

_STAGES = ("implementing",)

_ISSUE = 42

_TZ_OFFSET_PARAMETER = "tz_offset_hours"

_TZ_OFFSET_HOURS = 7

_READ_FILTERED_ATTRIBUTE = "read_filtered"

# The key a run narrowed to one repo and issue stores its reads under.
_KEY = filters.cache_key(
    windows.DateWindow(start=utc_midnight(MAY01), end=utc_midnight(MAY07)),
    _REPO,
    _EVENTS,
    _STAGES,
    _ISSUE,
)

# What a page hands an adapter, which is what its cached key is built out of.
# A connection may never appear here: `st.cache_data` would have to hash a
# psycopg connection, which is unhashable, and a stringified one would make
# every refreshed socket look like a cache miss.
_KEY_ONLY = ("key",)

_KEY_AND_OFFSET = ("key", _TZ_OFFSET_PARAMETER)

# Each panel read, the query owner's read it names, and what a page calls it
# with. The rollup answers the three a whole day's bucket keeps the grouping
# for; the breakdown family answers the four that bucket threw the column away
# for.
_PANEL_READS = (
    (
        breakdowns.read_backend_efficiency,
        rollup_reads.get_backend_efficiency,
        _KEY_ONLY,
    ),
    (
        breakdowns.read_repo_breakdown,
        rollup_reads.get_repo_breakdown,
        _KEY_ONLY,
    ),
    (
        breakdowns.read_throughput,
        rollup_reads.get_throughput_breakdown,
        _KEY_ONLY,
    ),
    (
        breakdowns.read_cost_coverage,
        breakdown_reads.get_cost_coverage,
        _KEY_ONLY,
    ),
    (
        breakdowns.read_unpriced_reasons,
        breakdown_reads.get_unpriced_reasons,
        _KEY_ONLY,
    ),
    (
        breakdowns.read_backend_daily_tokens,
        breakdown_reads.get_backend_daily_tokens,
        _KEY_ONLY,
    ),
    (
        breakdowns.read_hourly_heatmap,
        breakdown_reads.get_hourly_heatmap,
        _KEY_AND_OFFSET,
    ),
)


def _extra_filters(key_arguments: tuple[str, ...]) -> dict[str, int]:
    """The filter a read carries beside the key, if its signature names one."""
    if key_arguments == _KEY_ONLY:
        return {}
    return {_TZ_OFFSET_PARAMETER: _TZ_OFFSET_HOURS}


class PanelReadOwnerTest(unittest.TestCase):
    """Each panel read issues its own query owner's read under the page's key."""

    def test_each_read_names_its_query_owner(self) -> None:
        # Identity, not behavior: a read bound to a copy of the owner's
        # function would answer every panel correctly and still leave a patch
        # aimed at that owner intercepting nothing.
        for read, getter, key_arguments in _PANEL_READS:
            with self.subTest(read=read.__name__):
                issued = self._issued(read, key_arguments)

                self.assertIs(issued.args[0], getter)
                self.assertIs(issued.args[1], _KEY)

    def test_the_offset_travels_beside_the_key(self) -> None:
        # Which cell a row is counted into is not which rows the window holds,
        # so the display offset is passed as its own filter rather than hashed
        # into the key the other five share.
        issued = self._issued(breakdowns.read_hourly_heatmap, _KEY_AND_OFFSET)

        self.assertEqual(
            issued.kwargs, {_TZ_OFFSET_PARAMETER: _TZ_OFFSET_HOURS},
        )

    def test_no_read_narrows_by_anything_else(self) -> None:
        for read, _, key_arguments in _PANEL_READS:
            if key_arguments == _KEY_AND_OFFSET:
                continue
            with self.subTest(read=read.__name__):
                self.assertEqual(self._issued(read, key_arguments).kwargs, {})

    def _issued(self, read: Any, key_arguments: tuple[str, ...]) -> Any:
        """What one adapter handed the binding, having handed its rows back."""
        with patch.object(
            filter_binding, _READ_FILTERED_ATTRIBUTE,
        ) as read_filtered:
            read_rows = read(_KEY, **_extra_filters(key_arguments))
            self.assertIs(read_rows, read_filtered.return_value)
            return read_filtered.call_args


class CacheKeySignatureTest(unittest.TestCase):
    """A page's call is the whole of what a cached read is stored under."""

    def test_each_read_takes_the_declared_arguments(self) -> None:
        for read, _, key_arguments in _PANEL_READS:
            with self.subTest(read=read.__name__):
                self.assertEqual(
                    tuple(inspect.signature(read).parameters),
                    key_arguments,
                )


if __name__ == "__main__":
    unittest.main()
