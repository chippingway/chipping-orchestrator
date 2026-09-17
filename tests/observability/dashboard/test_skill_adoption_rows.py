# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What one cell of the adoption table says, and how it is drawn.

The cases lead with the two ways a cell can be quiet, because keeping them
apart is the reason the panel counts sessions rather than runs: a skill nobody
was offered has no denominator and reports an undefined rate, while one that
was offered and loaded by nobody reports a real zero -- the offered-but-ignored
finding the panel exists to surface. Beside them are the whole-point rate a
busy cell reports, the two diagnostics that are counted apart so neither can be
read as adoption, the source level that keeps two definitions of one name
apart, the label an empty category is bucketed under, and the escaping every
naming column arrives needing.
"""

from __future__ import annotations

import unittest

from orchestrator.observability.dashboard import skill_adoption_rows
from orchestrator.observability.dashboard.skill_trigger_table import UNKNOWN
from tests.observability.dashboard.skill_adoption_test_support import (
    LEVEL_USER,
    CellCase,
    cell,
    cell_fragment,
)

# Nobody was offered the skill, so the cell exists only for its diagnostics.
_UNOFFERED_CELL = CellCase(sessions=0, adopted=0, incidental=1)

# The skill was offered to every session and loaded by none of them.
_IGNORED_CELL = CellCase(adopted=0)

# Three of the shared cell's four sessions loaded the skill, so the rounded
# rate is readable off the markup.
_ADOPTED_SESSIONS = 3

_BUSY_RATE = ">75%<"

_MUTED_ZERO = '<span class="orch-skilladopt-zero">0</span>'

_MUTED_ZERO_RATE = '<span class="orch-skilladopt-zero">0%</span>'

_MUTED_UNDEFINED_RATE = '<span class="orch-skilladopt-zero">—</span>'

_PLAIN_SESSION_TOTAL = '<td class="r">4</td>'

_PLAIN_ONE = '<td class="r">1</td>'

_NAME_WITH_MARKUP = "a/<r&>"

_ESCAPED_NAME = "a/&lt;r&amp;&gt;"

# Every naming column of a cell the sink recorded no categories for.
_NAMING_COLUMNS = 5


def _rendered(case: CellCase) -> str:
    """The row that cell is drawn as."""
    return skill_adoption_rows.skill_adoption_row_html(cell(case))


class SkillAdoptionQuietCellTest(unittest.TestCase):
    """The two ways a cell reports that nobody loaded the skill."""

    def test_an_unoffered_skill_has_no_rate(self) -> None:
        # An em-dash rather than a percentage: with no session to divide by,
        # any number here would claim something the evidence does not say.
        markup = _rendered(_UNOFFERED_CELL)
        self.assertIn(_MUTED_UNDEFINED_RATE, markup)
        self.assertNotIn("%", markup)

    def test_an_ignored_skill_reports_a_real_zero(self) -> None:
        # The zero and its rate carry the offered-but-ignored finding, while
        # the offered total is the denominator that zero is read against
        # rather than part of it -- toning that one too would report the
        # cohort as unoffered.
        markup = _rendered(_IGNORED_CELL)

        self.assertIn(_MUTED_ZERO_RATE, markup)
        self.assertIn(_MUTED_ZERO, markup)
        self.assertIn(_PLAIN_SESSION_TOTAL, markup)


class SkillAdoptionCellReadingsTest(unittest.TestCase):
    """What a cell that was loaded reports, and how it is labelled."""

    def test_a_rate_is_reported_in_whole_points(self) -> None:
        self.assertIn(
            _BUSY_RATE, _rendered(CellCase(adopted=_ADOPTED_SESSIONS)),
        )

    def test_the_diagnostics_are_counted_apart(self) -> None:
        # A load a session never reported the skill available for, and a
        # `SKILL.md` only mentioned in passing, are each their own column, so
        # a cell nobody adopted still reports both without either raising it.
        markup = _rendered(CellCase(sessions=0, adopted=0, load_rows=1, incidental=1))
        self.assertEqual(markup.count(_PLAIN_ONE), 2)
        self.assertIn(_MUTED_UNDEFINED_RATE, markup)

    def test_the_source_level_is_its_own_column(self) -> None:
        # Two cells can carry the same four other names and differ only in the
        # definition behind them, so a row that dropped the level would report
        # a repository's own skill and a global one as one another's duplicate.
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
