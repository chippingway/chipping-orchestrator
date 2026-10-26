# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Reading one cell off a row the day-bucketed rollup answered with.

Two readings stand between a raw cell and the frozen result field it lands in.
A nullable USD cost is read as a float with a NULL collapsing to zero, because
a spend sum is NULL wherever no run in the group could be priced and a spend
field the dashboard sums cannot carry `None`. And a `day` some drivers widen to
a timestamp is narrowed back to the date the rollup grouped by, so a page
keying its series on days is not comparing a date against midnight.

Every cell is read at the position the projection's own SELECT list put it, so
a row narrower than that list is a broken query rather than a shape to pad.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from typing import Any


def cost_cell(row: Sequence[Any], index: int) -> float:
    """Read a nullable USD cost column as a float, treating NULL as zero."""
    return float(row[index] or 0)


def day_value(day: Any) -> Any:
    """Narrow a widened `day` column back to the date the rollup grouped by."""
    if isinstance(day, datetime):
        return day.date()
    return day
