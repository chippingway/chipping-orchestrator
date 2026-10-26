# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What one rollup cell reads back as before it lands in a result field."""
from __future__ import annotations

import unittest
from datetime import UTC, date, datetime
from decimal import Decimal

from orchestrator.observability.analytics.query.row_cells import (
    cost_cell,
    day_value,
)

_MISSING_INDEX = 5

_POPULATED_COST = Decimal("12.50")

_POPULATED_FLOAT = 12.5

_YEAR = 2026

_DAY_NUMBER = 25

_DAY = date(_YEAR, 5, _DAY_NUMBER)

_WIDENED_DAY = datetime(_YEAR, 5, _DAY_NUMBER, 0, 0, tzinfo=UTC)


class CostCellTest(unittest.TestCase):
    """A nullable USD column a page sums and cannot receive `None` from."""

    def test_null_and_zero_read_as_zero(self) -> None:
        # A spend sum is NULL wherever no run in the group was priced.
        for empty_cell in (
            cost_cell((None,), 0),
            cost_cell((Decimal(0),), 0),
        ):
            self.assertEqual(empty_cell, float(0))
            self.assertIsInstance(empty_cell, float)

    def test_a_column_the_row_never_carried_raises(self) -> None:
        # A row narrower than its SELECT list is a broken query, not a NULL.
        with self.assertRaises(IndexError):
            cost_cell(("only-one",), _MISSING_INDEX)

    def test_a_recorded_cost_converts_to_its_float(self) -> None:
        converted = cost_cell((_POPULATED_COST,), 0)
        self.assertEqual(converted, _POPULATED_FLOAT)
        self.assertIsInstance(converted, float)


class DayValueTest(unittest.TestCase):
    """The grouping key a driver may hand back widened."""

    def test_a_widened_day_narrows_to_its_date(self) -> None:
        self.assertEqual(day_value(_WIDENED_DAY), _DAY)

    def test_a_date_and_a_null_pass_through(self) -> None:
        self.assertEqual(day_value(_DAY), _DAY)
        self.assertIsNone(day_value(None))


if __name__ == "__main__":
    unittest.main()
