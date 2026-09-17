# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What one cell of the trigger matrix says, and how it is drawn.

The cases lead with the cohort that reached for a skill on none of its runs,
because that cell is the reason the panel pairs a catalog with the triggers at
all: it is toned down rather than dropped, and its denominator is not, since
the cohort's own run total is what the zero is read against. Beside it are the
whole-point rate a busy cell reports, the source level that keeps two
definitions of one name apart, the label an empty category is bucketed under,
and the escaping every naming column arrives needing.
"""

from __future__ import annotations

import unittest

from orchestrator.observability.dashboard import skill_matrix_rows
from orchestrator.observability.dashboard.skill_trigger_table import UNKNOWN
from tests.observability.dashboard.skill_matrix_test_support import (
    LEVEL_USER,
    CellCase,
    cell,
    cell_fragment,
)

_QUIET_CELL = CellCase(skill_runs=0)

# Three of the shared cell's four runs reached for the skill, so the rounded
# rate is readable off the markup.
_BUSY_SKILL_RUNS = 3

_BUSY_RATE = ">75%<"

_MUTED_ZERO = '<span class="orch-skillmatrix-zero">0</span>'

_MUTED_ZERO_RATE = '<span class="orch-skillmatrix-zero">0%</span>'

_PLAIN_COHORT_TOTAL = '<td class="r">4</td>'

_NAME_WITH_MARKUP = "a/<r&>"

_ESCAPED_NAME = "a/&lt;r&amp;&gt;"

# Every naming column of a cell the sink recorded no categories for.
_NAMING_COLUMNS = 5


def _rendered(case: CellCase) -> str:
    """The row that cell is drawn as."""
    return skill_matrix_rows.skill_matrix_row_html(cell(case))


class SkillMatrixQuietCellTest(unittest.TestCase):
    """The offered-but-never-triggered cell the panel exists to report."""

    def test_the_zero_is_toned_and_the_total_is_not(self) -> None:
        # The count and the rate carry the finding, while the cohort total is
        # the denominator that zero is read against rather than part of it --
        # toning that one too would report the cohort itself as quiet.
        markup = _rendered(_QUIET_CELL)

        self.assertIn(_MUTED_ZERO, markup)
        self.assertIn(_MUTED_ZERO_RATE, markup)
        self.assertIn(_PLAIN_COHORT_TOTAL, markup)


class SkillMatrixCellReadingsTest(unittest.TestCase):
    """What a cell that did trigger reports, and how it is labelled."""

    def test_a_rate_is_reported_in_whole_points(self) -> None:
        self.assertIn(
            _BUSY_RATE, _rendered(CellCase(skill_runs=_BUSY_SKILL_RUNS)),
        )

    def test_the_source_level_is_its_own_column(self) -> None:
        # A repository's own definition and a same-named one installed for
        # the operator are two rows, so a row that dropped the level would
        # report them as one another's duplicate.
        self.assertIn(
            cell_fragment(LEVEL_USER), _rendered(CellCase(level=LEVEL_USER)),
        )

    def test_an_empty_category_reads_unknown(self) -> None:
        markup = _rendered(
            CellCase(repo="", skill="", role="", backend="", level=""),
        )
        self.assertEqual(
            markup.count(cell_fragment(UNKNOWN)), _NAMING_COLUMNS,
        )

    def test_every_naming_column_is_escaped(self) -> None:
        markup = _rendered(
            CellCase(
                repo=_NAME_WITH_MARKUP,
                skill=_NAME_WITH_MARKUP,
                role=_NAME_WITH_MARKUP,
                backend=_NAME_WITH_MARKUP,
                level=_NAME_WITH_MARKUP,
            ),
        )
        self.assertEqual(markup.count(_ESCAPED_NAME), _NAMING_COLUMNS)
        self.assertNotIn(_NAME_WITH_MARKUP, markup)


if __name__ == "__main__":
    unittest.main()
