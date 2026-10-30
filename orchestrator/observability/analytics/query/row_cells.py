# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Reading one cell off a row the day-bucketed rollup answered with.

A `day` some drivers widen to a timestamp is narrowed back to the date the
rollup grouped by, so a page keying its series on days is not comparing a date
against midnight. A cost is never read off one cell: what a group spent is the
cohort `cost_cohorts.cost_cohort` reads off every cell its fragment selected,
because a single summed amount would merge the bases and read a NULL --
nothing priced -- as a zero.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any


def day_value(day: Any) -> Any:
    """Narrow a widened `day` column back to the date the rollup grouped by."""
    if isinstance(day, datetime):
        return day.date()
    return day
