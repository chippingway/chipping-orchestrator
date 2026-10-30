# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What a rollup day cell reads back as before it lands in a result field."""
from __future__ import annotations

import unittest
from datetime import UTC, date, datetime

from orchestrator.observability.analytics.query.row_cells import day_value

_YEAR = 2026

_DAY_NUMBER = 25

_DAY = date(_YEAR, 5, _DAY_NUMBER)

_WIDENED_DAY = datetime(_YEAR, 5, _DAY_NUMBER, 0, 0, tzinfo=UTC)


class DayValueTest(unittest.TestCase):
    """The grouping key a driver may hand back widened."""

    def test_a_widened_day_narrows_to_its_date(self) -> None:
        self.assertEqual(day_value(_WIDENED_DAY), _DAY)

    def test_a_date_and_a_null_pass_through(self) -> None:
        self.assertEqual(day_value(_DAY), _DAY)
        self.assertIsNone(day_value(None))


if __name__ == "__main__":
    unittest.main()
