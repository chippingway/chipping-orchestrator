# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The card a window's skill adoption is reported on.

The cases name what the card decides rather than what the tables under it draw:
which panel the card opens on, the section each adoption cell is folded into
and that no cell falls out of that split, the single notice a window with no
run at all is answered with, the order each table is opened in when the page
URL asked for one, and the caption that qualifies a quiet window. That caption
is the reading with the most to get wrong, so every evidence shape a window
with no adopting session can arrive in is here -- each one proof that tracking
recorded something, and so a window the card must not tell an operator to
switch tracking on for.

A level a window has no cell of is a separate reading from a window with no
cell at all, so both are driven here: the first says only that the level is
empty, the second is the one window the opt-in switch is named for.

Whether the window carried adoption evidence is also what the diagnostics above
are handed, so the two windows that flag separates -- a genuine no-trigger and
one nobody enabled tracking for -- are driven through the card rather than
through the diagnostics directly.
"""

from __future__ import annotations

import unittest
from collections.abc import Mapping

from orchestrator.observability.dashboard import skill_panel
from tests.observability.dashboard import skill_adoption_test_support as adopt, skill_matrix_test_support as matrix
from tests.observability.dashboard.skill_panel_test_support import (
    PanelStreamlit,
    all_markup,
    fold_markup,
    panel_markup,
    rate_row,
)

_ADOPTION_TABLE = "orch-skilladopt"

_TRIGGER_TABLE = "orch-skills"

_MATRIX_TABLE = "orch-skillmatrix"

_DIAGNOSTICS_FOLD = "Invocation-level diagnostics"

_PROJECT_FOLD = "Project-level skills"

_USER_FOLD = "User-level skills"

_HARNESS_FOLD = "Harness-level skills"

_UNCLASSIFIED_FOLD = "Unclassified skills"

_LEVEL_FOLDS = (_PROJECT_FOLD, _USER_FOLD, _HARNESS_FOLD)

_ENABLE_LABEL = "Enable"

_TRACK_SKILL_TRIGGERS = "TRACK_SKILL_TRIGGERS"

_QUIET_COHORT = 0

# One cell per source level, each in a repository of its own, so a section
# drawing another level's rows is readable off the markup it wrote.
_LEVEL_REPOS = (adopt.REPO_A, adopt.REPO_B, adopt.REPO_C)

_LEVEL_CELLS = (
    adopt.CellCase(repo=adopt.REPO_A),
    adopt.CellCase(repo=adopt.REPO_B, level=adopt.LEVEL_USER),
    adopt.CellCase(repo=adopt.REPO_C, level=adopt.LEVEL_HARNESS),
)

# Every evidence shape a window with no adopting session can arrive in, and the
# words the caption has to reach for. Availability alone reads as the genuine
# zero it is; without it the caption names whichever of the two diagnostics the
# window did record, so an operator can match it against those columns.
_CAPTION_CASES = (
    (adopt.CellCase(sessions=5, adopted=0), ("genuine 0% adoption",)),
    (adopt.CellCase(sessions=0, adopted=0, incidental=1), ("incidental",)),
    (adopt.CellCase(sessions=0, adopted=0, load_rows=2), ("loaded",)),
    (
        adopt.CellCase(sessions=0, adopted=0, load_rows=2, incidental=1),
        ("loaded", "incidental"),
    ),
)


def _render_card(
    *cases: adopt.CellCase,
    skill_runs: int = 2,
    with_runs: bool = True,
    query_params: Mapping[str, str] | None = None,
) -> PanelStreamlit:
    """Draw the whole card for those adoption cells onto a fake page."""
    page = PanelStreamlit(query_params)
    skill_panel.render_skill_adoption(
        st=page,
        skill_adoption_rows=adopt.cells(*cases),
        skill_rows=[rate_row(skill_runs=skill_runs)] if with_runs else [],
        skill_matrix_rows=matrix.cells(
            matrix.CellCase(repo=matrix.REPO_B),
            matrix.CellCase(repo=matrix.REPO_A),
        ),
    )
    return page


def _fold_heads(page: PanelStreamlit) -> list[str]:
    """What each fold-out is titled, ahead of the dot that qualifies it."""
    return [opened.label.split(" · ")[0] for opened in page.expanders]


class SkillCardLayoutTest(unittest.TestCase):
    """The invocation views open the card; adoption folds by level beneath."""

    def test_diagnostics_are_drawn_before_adoption(self) -> None:
        page = _render_card(adopt.CellCase())
        written = all_markup(page)
        self.assertLess(
            written.index("Skill adoption"), written.index(_TRIGGER_TABLE),
        )
        self.assertLess(
            written.index(_TRIGGER_TABLE), written.index(_MATRIX_TABLE),
        )
        self.assertLess(
            written.index(_MATRIX_TABLE), written.index(_ADOPTION_TABLE),
        )

    def test_every_panel_opens_collapsed_in_order(self) -> None:
        page = _render_card(*_LEVEL_CELLS)
        self.assertEqual(
            _fold_heads(page), [_DIAGNOSTICS_FOLD, *_LEVEL_FOLDS],
        )
        for opened in page.expanders:
            with self.subTest(fold=opened.label):
                self.assertFalse(opened.expanded)

    def test_a_window_with_no_runs_gets_one_notice(self) -> None:
        # The whole card is answered once rather than each of its tables
        # drawing an empty state of its own.
        page = _render_card(with_runs=False)
        self.assertEqual(len(page.notices), 1)
        self.assertIn("No `agent_exit` rows", page.notices[0])
        self.assertEqual(page.markdowns[1:], [])
        self.assertEqual(page.expanders, [])

    def test_each_table_reads_its_own_parameters(self) -> None:
        # The two tables carry separate parameters precisely so a click on one
        # leaves the other's order alone, so the card has to read each table's
        # own pair back rather than one for both.
        page = _render_card(
            adopt.CellCase(repo=adopt.REPO_A),
            adopt.CellCase(repo=adopt.REPO_B),
            query_params={"adopt_sort": "repo", "adopt_dir": "desc"},
        )
        adoption = fold_markup(page, _PROJECT_FOLD)
        self.assertLess(
            adoption.index(adopt.cell_fragment(adopt.REPO_B)),
            adoption.index(adopt.cell_fragment(adopt.REPO_A)),
        )
        drawn = panel_markup(page, _MATRIX_TABLE)
        self.assertLess(
            drawn.index(matrix.cell_fragment(matrix.REPO_A)),
            drawn.index(matrix.cell_fragment(matrix.REPO_B)),
        )


class SkillAdoptionLevelSectionTest(unittest.TestCase):
    """Each source level is read in a fold-out of its own, and none is lost."""

    def test_a_section_draws_only_its_own_level(self) -> None:
        page = _render_card(*_LEVEL_CELLS)
        for fold, repo in zip(_LEVEL_FOLDS, _LEVEL_REPOS):
            drawn_in = [
                other
                for other in _LEVEL_FOLDS
                if adopt.cell_fragment(repo) in fold_markup(page, other)
            ]
            with self.subTest(fold=fold):
                self.assertEqual(drawn_in, [fold])

    def test_an_unclassified_cell_keeps_a_section(self) -> None:
        # A claude run's load names no source directory, so it arrives with no
        # level and would fall out of a split that knew only the three.
        page = _render_card(
            adopt.CellCase(repo=adopt.REPO_A),
            adopt.CellCase(repo=adopt.REPO_B, level=adopt.LEVEL_UNKNOWN),
        )
        self.assertEqual(
            _fold_heads(page),
            [_DIAGNOSTICS_FOLD, *_LEVEL_FOLDS, _UNCLASSIFIED_FOLD],
        )
        unclassified = adopt.cell_fragment(adopt.REPO_B)
        self.assertIn(
            unclassified, fold_markup(page, _UNCLASSIFIED_FOLD),
        )
        self.assertNotIn(unclassified, fold_markup(page, _PROJECT_FOLD))

    def test_an_empty_level_says_only_that(self) -> None:
        # The level is empty because the window carried no such skill, which
        # is no evidence at all about a switch a sibling section's rows prove
        # is already on.
        page = _render_card(adopt.CellCase(repo=adopt.REPO_A))
        empty = fold_markup(page, _USER_FOLD)
        self.assertIn("No user-level skill was recorded", empty)
        self.assertNotIn(_TRACK_SKILL_TRIGGERS, empty)


class SkillAdoptionCaptionTest(unittest.TestCase):
    """A quiet window is qualified, never told to switch tracking on."""

    def test_each_evidence_shape_is_named_neutrally(self) -> None:
        for case, expected_words in _CAPTION_CASES:
            with self.subTest(case=case):
                captions = _render_card(case).captions
                self.assertEqual(len(captions), 1)
                for word in expected_words:
                    self.assertIn(word, captions[0])
                self.assertNotIn(_ENABLE_LABEL, captions[0])
                self.assertNotIn(_TRACK_SKILL_TRIGGERS, captions[0])

    def test_loads_nobody_was_offered_draw_no_rate(self) -> None:
        # The read model never turns a load into the offer it would have
        # needed, so a window whose sessions reported no offered set reaches
        # the card as loads beside a zero denominator: the cell draws an
        # undefined rate rather than a 100% adoption, and the caption says no
        # session reported the skill available -- not that the loads were
        # incidental, since the two are separate columns.
        page = _render_card(adopt.CellCase(sessions=0, adopted=0, load_rows=2))
        caption = page.captions[0]
        self.assertIn("no session reported one available", caption)
        self.assertNotIn("Only incidental", caption)
        adoption = fold_markup(page, _PROJECT_FOLD)
        self.assertIn('<span class="orch-skilladopt-zero">—</span>', adoption)
        # Every rate a cell draws ends its cell, so no percentage was drawn.
        self.assertNotIn("%<", adoption)

    def test_an_adopting_window_is_left_unqualified(self) -> None:
        # Nothing about a window where sessions adopted and runs triggered is
        # worth qualifying, so neither the card nor the folds under it caption.
        adopting = adopt.CellCase(sessions=5, adopted=3)
        self.assertEqual(_render_card(adopting).captions, [])

    def test_a_window_with_no_cells_defers(self) -> None:
        # The table already renders the notice naming the switch, and saying it
        # twice -- once per level section -- would read as three problems.
        page = _render_card()
        self.assertEqual(page.captions, [])
        self.assertEqual(_fold_heads(page), [_DIAGNOSTICS_FOLD])
        empty = panel_markup(page, f"{_ADOPTION_TABLE}-empty")
        self.assertIn(_TRACK_SKILL_TRIGGERS, empty)


class SkillDiagnosticsHandoffTest(unittest.TestCase):
    """Adoption evidence is what the diagnostics read the quiet case by."""

    def test_evidence_makes_a_quiet_window_genuine(self) -> None:
        page = _render_card(
            adopt.CellCase(sessions=5, adopted=0), skill_runs=_QUIET_COHORT,
        )
        written = " ".join(page.captions)
        self.assertIn("No agent run triggered a skill", written)
        self.assertNotIn(_ENABLE_LABEL, written)
        self.assertNotIn(_TRACK_SKILL_TRIGGERS, written)

    def test_no_evidence_names_the_switch(self) -> None:
        captions = _render_card(skill_runs=_QUIET_COHORT).captions
        self.assertEqual(len(captions), 1)
        self.assertIn(_ENABLE_LABEL, captions[0])
        self.assertIn(_TRACK_SKILL_TRIGGERS, captions[0])


if __name__ == "__main__":
    unittest.main()
