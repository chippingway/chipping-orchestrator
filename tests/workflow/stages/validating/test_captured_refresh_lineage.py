# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""A held refresh entered over a proved lineage, finished only while that lineage still stands.

The settled report a rebase left behind can be of neither head its debt names
-- the approved commit an approval's squash collapsed, or a final docs pass
documented, into the head the rebase replaced -- and the refresh is asked for
only once that lineage is proved and the approved report re-reads intact where
it settled. A refresh held as it reports keeps its capture, frozen over the
records that lineage was proved from, and its recovery asks the lineage again
before anything is recorded: the squash's carry or the docs pass's descent
proved again in the checkout, and the approved report re-read at its location.
Where both still stand the report is published and settled once, the approved
report left as it was written. A record the lineage stood on taken off, an
approved report removed, or a tree or descent git reads otherwise retires the
capture with nothing published; a tree, a descent, a location, or a record
nobody can read holds it with nothing written, and the dispatch whose
readings return finishes it once, with no developer run.
"""
from __future__ import annotations

import contextlib
import unittest
from types import MappingProxyType
from unittest.mock import MagicMock, patch

from orchestrator.git.verification import probes as _probes
from orchestrator.github.pull_request_reports import ReportLookup, ReportPresence
from orchestrator.workflow.engine import completion_checkpoint as _checkpoint, guards as _guards
from tests.workflow import captured_drifts as _drifts, captured_fixes as _fixes
from tests.workflow.git_owners import seam_patch
from tests.workflow.repo_values import _FAKE_TREE_SHA
from tests.workflow.stages.validating import (
    captured_refresh_test_support as _held,
    changed_docs_journey_support as _docs,
    report_refresh_test_support as _support,
    squash_rebase_journey_support as _journey,
)

RUN_AGENT = _held.RUN_AGENT

EVIDENCE_HISTORY = "verification_evidence_history"

# The tree the squash reads as where git reads it otherwise than its carry
# recorded, and as where git does not read it at all.
_OTHER_TREE = "7" * len(_FAKE_TREE_SHA)

_UNREAD_TREE = ""

# A dispatch's readings that leave every tree to the reading a case installs.
_OWN_TREES = MappingProxyType({"checkout_tree": None})


class _UnconfirmedAt:
    """Report re-reads, the one at `location` left unanswered and every other answered as `reread` answers it."""

    def __init__(self, reread, location) -> None:
        self._reread = reread
        self._location = location

    def __call__(self, where, **options):
        """Re-read the report at `where`, leaving the one location unanswered."""
        if where == self._location:
            return ReportLookup(ReportPresence.UNCONFIRMED)
        return self._reread(where, **options)


class _SquashTrees:
    """The trees git reads commits as: the squash's as `tree` -- another tree, or none -- every other the carry's."""

    def __init__(self, tree: str) -> None:
        self._tree = tree

    def __call__(self, _worktree, commit="HEAD"):
        """The tree `commit` reads as."""
        return self._tree if commit == _support.SQUASHED_HEAD else _FAKE_TREE_SHA

    def installed(self, _case) -> contextlib.AbstractContextManager:
        """These trees in place of the ones git reads, for as long as the context lasts."""
        return patch.object(_probes, "_tree_sha", side_effect=self)


def _approved_report_unconfirmed(case) -> contextlib.AbstractContextManager:
    """The approved report's location left unanswered for every re-read, the others answered as ever."""
    unconfirmed = _UnconfirmedAt(case.github.reread_report_location, case.opening_report.location)
    return patch.object(case.github, "reread_report_location", side_effect=unconfirmed)


def _approved_report_removed(case) -> contextlib.AbstractContextManager:
    """The approved report's comment taken off the pull request, ahead of the dispatch."""
    case.pull_request.issue_comments.remove(case.approved_comment())
    return contextlib.nullcontext()


# Every lineage reading a squashed refresh's recovery cannot take, as the
# context the recovery's dispatch runs under and its readings: the approved
# report's location, and the squash's tree.
UNREAD = (
    ("the approved report's location", _approved_report_unconfirmed, {}),
    ("the squash's tree", _SquashTrees(_UNREAD_TREE).installed, _OWN_TREES),
)

# Every lineage a squashed refresh's recovery finds refuted: the approved
# report gone from the pull request, and the squash read as another tree than
# its carry recorded.
REFUTED = (
    ("the approved report removed", _approved_report_removed, {}),
    ("the squash read as another tree", _SquashTrees(_OTHER_TREE).installed, _OWN_TREES),
)

# The evidence history the squash's carry is kept in, taken off the record,
# which retires the capture, and spelled as nothing its reader takes, which
# holds it.
HISTORY_MOVES = (
    ("the evidence history gone", _fixes.OMITTED, _fixes.RETIRED),
    ("the evidence history damaged", "not a history", _fixes.PENDING),
)

# How a refresh behind a rebase of the docs commit names the report the pull
# request carries: the approved commit, squashed and then documented into the
# docs commit that rebase replaced.
DOCUMENTED_INTO = f"the approved commit this orchestrator documented, in a final docs pass, into `{_docs.DOCS_HEAD}`"

# Whether the docs commit descends from the head its pass was entered on, as
# git answers: no answer at all, and no.
_UNREAD_DESCENT = None

_UNDESCENDED = False


class HeldSquashLineageTest(unittest.TestCase, _support._SquashedReports, _held.HeldRefreshes):
    """A held refresh entered over a proved approval squash, finished only over that lineage."""

    def test_a_squashed_refresh_is_finished_once(self) -> None:
        # The squash's carry proves the lineage again and the approved report
        # re-reads intact: the held refresh is finished once, with no
        # developer run, the approved report left as it was written.
        self.squashed_then_rebased()
        approved = self.approved_comment().body
        held = self.held_refresh()
        self.unheld()
        self.assert_finished(self.kept(held))
        self.assertEqual(self.approved_comment().body, approved)

    def test_an_unread_lineage_holds_it(self) -> None:
        # The approved report's location, or the squash's tree, nobody can
        # read: nothing proves the lineage gone, so the capture is kept with
        # nothing written or published; the dispatch whose readings return
        # finishes it once, with no developer run.
        for name, unread, readings in UNREAD:
            with self.subTest(name):
                self.squashed_then_rebased()
                held = self.held_refresh()
                self.lifts_the_control()
                before = self.standing()
                with unread(self):
                    self.dispatched(**readings)[RUN_AGENT].assert_not_called()
                self.assert_held(before)
                self.unheld()
                self.assert_finished(self.kept(held))

    def test_a_refuted_lineage_retires_it(self) -> None:
        # The approved report gone from the pull request, or the squash read
        # as another tree than its carry recorded: the report the refresh was
        # owed over no longer stands, so the capture is retired with nothing
        # recorded, published, charged, or parked.
        for name, refuted, readings in REFUTED:
            with self.subTest(name):
                self.squashed_then_rebased()
                held = self.held_refresh()
                self.lifts_the_control()
                with refuted(self):
                    self.dispatched(**readings)[RUN_AGENT].assert_not_called()
                self.assert_retired(held)

    def test_a_control_during_the_reads_holds_it(self) -> None:
        # The approved report is gone, and an operator holds the issue as the
        # recovery re-reads it: the refutation was read over an issue that
        # moved behind it, so nothing is retired or written; once the control
        # comes off, the next dispatch retires the capture.
        self.squashed_then_rebased()
        held = self.held_refresh()
        self.lifts_the_control()
        _approved_report_removed(self)
        before = self.standing()
        reread = _fixes.ReadAt(self, self.opening_report.location, control=_fixes.PAUSED)
        with patch.object(self.github, "reread_report_location", side_effect=reread):
            self.dispatched()[RUN_AGENT].assert_not_called()
        self.assert_held(before)
        self.unheld()
        self.assert_retired(held)

    def test_a_control_at_the_retirement_holds_it(self) -> None:
        # The approved report is gone, and an operator holds the issue as the
        # strict editor sending the retirement walks to the comment: the
        # admission read again behind that last read holds the edit, so the
        # capture stays pending with nothing written; once the control comes
        # off, the next dispatch retires it.
        self.squashed_then_rebased()
        held = self.held_refresh()
        self.lifts_the_control()
        _approved_report_removed(self)
        before = self.standing()
        retirement = _drifts.HeldAtTheWalk(self.github, self.issue, _fixes.PAUSED, _checkpoint.retire)
        with patch.object(_checkpoint, "retire", retirement):
            self.dispatched()[RUN_AGENT].assert_not_called()
        self.assertTrue(retirement.applied)
        self.assert_held(before)
        self.unheld()
        self.assert_retired(held)

    def test_a_moved_lineage_record_is_never_finished(self) -> None:
        # The evidence the squash's carry is kept in, taken off the record,
        # retires the capture; spelled as nothing its reader takes, it holds
        # it with nothing written. Neither publishes anything.
        for name, history, stage in HISTORY_MOVES:
            with self.subTest(name):
                self.squashed_then_rebased()
                self.held_refresh()
                _fixes.CapturedFixTicks.hand_edit(self, **{EVIDENCE_HISTORY: history})
                self.unheld()
                self.assert_waiting(stage)


class HeldDocsLineageTest(_docs._ChangedDocsWalk, unittest.TestCase):
    """A held refresh of a rebased docs commit, finished only over the docs pass's lineage."""

    def test_a_docs_refresh_is_finished_once(self) -> None:
        # The descent of the docs commit nobody can read holds the capture
        # with nothing written; once it reads, the report is published and
        # settled about the rebased head with no developer run, its prompt
        # having named the docs pass's lineage, and the walk goes on through
        # one fresh review and docs pass to one ready ping.
        self._held_over_the_docs()
        self._held_through(_UNREAD_DESCENT)
        self.dispatched()
        settled = self.pinned()
        self.assertEqual(_fixes.stage_of(settled), _fixes.HANDED_OFF)
        self.assertEqual(settled[_docs.CURRENT_REPORT]["sha"], _journey.ADVANCED)
        self.approved_into_review(_journey.ADVANCED)
        self.assertIn(DOCUMENTED_INTO, self.spawned(_journey.REFRESHER)[0])
        self.assertEqual(self.roles().count(_journey.REFRESHER), 1)
        self.assert_ready_on(_journey.ADVANCED, self.refreshed)

    def test_a_refuted_docs_lineage_retires_it(self) -> None:
        # The docs commit read as not descending from the head its pass was
        # entered on: the lineage the refresh was owed over no longer holds,
        # so the capture is retired with nothing published or settled.
        self._held_over_the_docs()
        reported = self.pinned()[_docs.CURRENT_REPORT]
        self._recovered(_UNDESCENDED)
        retired = self.pinned()
        self.assertEqual(_fixes.stage_of(retired), _fixes.RETIRED)
        self.assertEqual(retired[_docs.CURRENT_REPORT], reported)

    def _held_over_the_docs(self) -> None:
        """Walk the docs commit into review, rebase it, and hold its refresh as it reports: captured, nothing else."""
        self.walks_into_documenting()
        self.changes_the_docs()
        self.dispatched()
        self.base_refresh(_journey.ADVANCED)
        with patch.object(_guards, "_paused_during_agent_run", return_value=True):
            self.dispatched(_journey.refresh())
        self.assertEqual(_fixes.stage_of(self.pinned()), _fixes.PENDING)

    def _held_through(self, descends) -> None:
        """One dispatch of the recovery, git answering `descends`, which writes nothing at all."""
        before = (self.pinned(), self.github.write_state_calls)
        self._recovered(descends)
        self.assertEqual((self.pinned(), self.github.write_state_calls), before)

    def _recovered(self, descends) -> None:
        """One dispatch of the recovery, git answering whether the docs commit descends as `descends`."""
        with seam_patch("_descends", MagicMock(return_value=descends)):
            self.dispatched()


if __name__ == "__main__":
    unittest.main()
