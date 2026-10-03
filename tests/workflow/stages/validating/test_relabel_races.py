# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What another road writes while the approval handoff moves the label, and who answers it.

The relabel to `documenting` is a request of its own, long enough for another
road to settle a later report on the same head, persist a later reviewer
verdict, or put a squash handoff of its own in place of the one this tick is
finishing. Each is past every reading the tail takes before the move, so the
move lands over it. The write that would end the handoff behind the label is
composed over the comment as it stands then, and made only where that comment
still carries this tick's handoff beside the report, pull-request, verdict,
and evidence records the move was taken over -- so it puts nothing older back,
and where any of them moved it leaves the record standing.

`documenting` answers none of these. Its next tick hands the issue back to
`validating` before any docs pass runs, where the recovery ahead of the
reviewer answers a handoff over the approval and head it names -- moving the
label again where that approval still covers what the comment carries, and
otherwise dropping the record for the reviewer -- and a verdict waits for the
road that finishes it.
"""
from __future__ import annotations

import unittest
from unittest.mock import patch

from orchestrator.workflow.engine import (
    report_settlement_state as _settlement,
    review_subjects as _review_subjects,
    verification_settlement_state as _settlement_of_evidence,
)
from orchestrator.workflow.stages.documenting import handler as _documenting
from orchestrator.workflow.stages.validating import review_verdicts as _verdicts
from tests.workflow import published_reports as _published_reports
from tests.workflow.fixtures import _agent
from tests.workflow.repo_values import _TEST_SPEC
from tests.workflow.stages.validating import squash_approval_support as _support
from tests.workflow.stages.validating.squash_approval_support import (
    _CollapseWorldMixin,
    _LandsWithACollapseRecorded,
    _RefusesTheCollapse,
    _SquashApprovalFixtureMixin,
)
from tests.workflow.stages.validating.test_squash_route import HANDED_ON

# The commit another road's squash published and recorded its handoff over.
REPLACED_HEAD = "b0a7ed01" * 5

# Where a documenting tick sends an issue carrying what `validating` owes.
HANDED_BACK = (_support.APPROVAL_ISSUE, "workflow:validating")


class _BehindTheRelabel:
    """A relabel to `documenting` behind which another road does `road`'s work on the issue."""

    def __init__(self, github, road) -> None:
        self._github = github
        self._relabels = github.set_workflow_label
        self._road = road

    def __call__(self, issue, label):
        answered = self._relabels(issue, label)
        if (issue.number, label) == HANDED_ON:
            self._road(self._github, issue)
        return answered


def _settles_a_later_report(github, issue) -> None:
    """Another road's settlement of a later report on the same head."""
    _published_reports.republishes_the_report(github, issue, "A later report.")


def _edits_the_report(github, issue) -> None:
    """A human editing the settled developer report in place on the pull request, which no pinned record shows."""
    location = _settlement.read_current_report(github.read_pinned_state(issue)).location
    landed = next(
        said for said in github.get_pr(_support.APPROVAL_PR).issue_comments if said.id == location.comment_id
    )
    landed.body = f"{landed.body}\nAnd something nobody reviewed."


def _replaces_the_handoff(github, issue) -> None:
    """Another road's squash, published and recorded over another commit than the one being finished."""
    github.get_pr(_support.APPROVAL_PR).head.sha = REPLACED_HEAD
    state = github.read_pinned_state(issue)
    state.set(_support.HANDOFF_KEY, REPLACED_HEAD)
    github.write_pinned_state(issue, state)


def _persists_a_later_verdict(github, issue) -> None:
    """Another road's later round, its change request persisted of the subject this tick approved."""
    state = github.read_pinned_state(issue)
    later = _verdicts.ReturnedVerdict(
        1,
        _verdicts.CHANGES_REQUESTED,
        state.get(_review_subjects.APPROVED_SUBJECT),
        "A later round's feedback.",
    )
    state.set(_verdicts.RETURNED_VERDICT, later.recorded())
    github.write_pinned_state(issue, state)


# What the documenting tick behind the relabel leaves of a record another road
# put down during it: kept exactly as it stood, no docs agent run, and the
# issue moved on and then handed straight back.
_HANDED_BACK_UNTOUCHED = (True, False, [HANDED_ON, HANDED_BACK])


# What moves during the relabel with no handoff record left standing over it,
# and the squash the approval took.
_OUTGROWN_DURING_THE_RELABEL = (
    ("a later report, no collapse", _settles_a_later_report, _support.NOTHING_TO_SQUASH),
    ("a report edited in place, no collapse", _edits_the_report, _support.NOTHING_TO_SQUASH),
    ("a report edited in place over a collapse", _edits_the_report, _LandsWithACollapseRecorded()),
)


class RelabelRaceTest(
    unittest.TestCase,
    _SquashApprovalFixtureMixin,
    _CollapseWorldMixin,
):
    """The approval handoff's relabel, what lands during it, and the ticks that answer that."""

    def test_a_later_verdict_goes_back_to_validating(self) -> None:
        # Nothing the tail reads sees a verdict persisted during the relabel,
        # so the move lands over it. The documenting tick behind it neither
        # acts on it nor ends it: the issue goes back with it intact, and no
        # docs pass runs.
        observed = self._handed_back(_persists_a_later_verdict, _verdicts.RETURNED_VERDICT)[2]

        self.assertEqual(observed, _HANDED_BACK_UNTOUCHED)

    def test_a_replaced_handoff_reaches_its_recovery(self) -> None:
        # Another road's handoff, put in place of this tick's during the
        # relabel, is left standing and handed back rather than erased. The
        # recovery ahead of the reviewer then finds the approval covering the
        # head it names and carries its evidence onto that head, whose tree is
        # the tested one; the next tick's reconciliation publishes it, and the
        # recovery moves the label and ends the record -- with no reviewer, no
        # squash, and nothing erased unanswered.
        github, issue, observed = self._handed_back(_replaces_the_handoff, _support.HANDOFF_KEY)

        for mocks in (
            self._run_squash_approval(github, issue, _RefusesTheCollapse()),
            self._dispatches(github, issue, REPLACED_HEAD),
        ):
            mocks[_support.RUN_AGENT].assert_not_called()
            mocks[_support.SQUASH_SEAM].assert_not_called()
        self.assertEqual((observed, github.label_history[-1]), (_HANDED_BACK_UNTOUCHED, HANDED_ON))
        self.assertNotIn(_support.HANDOFF_KEY, github.pinned_data(_support.APPROVAL_ISSUE))
        self.assertEqual(
            _settlement_of_evidence.read_current_evidence(github.read_pinned_state(issue)).binding.target.target_head,
            REPLACED_HEAD,
        )

    def test_a_later_report_reaches_a_reviewer(self) -> None:
        # A later report settled during the relabel is kept, and this tick's
        # handoff is not ended over it: the move was taken over the report
        # before it. So the documenting tick hands the issue back, and the
        # recovery there will not spend the handoff under an approval of the
        # older report -- the reviewer reads the later one.
        github, issue, observed = self._handed_back(_settles_a_later_report, _support.HANDOFF_KEY)
        kept = _settlement.read_current_report(github.read_pinned_state(issue)).report_revision

        mocks = self._lands_a_collapse(github, issue)

        mocks[_support.RUN_AGENT].assert_called_once()
        self.assertEqual((observed, kept), (_HANDED_BACK_UNTOUCHED, 2))

    def test_an_outgrown_approval_goes_back(self) -> None:
        # What moves during the relabel leaves no handoff record standing
        # over it: an approval that collapsed nothing left none, and a report
        # edited in place moves no pinned record, so the handoff one left
        # ends as usual. The documenting tick asks the approval itself --
        # against the report the comment records as current and against its
        # words at their location -- and hands the issue back before any
        # docs pass.
        for name, road, squash in _OUTGROWN_DURING_THE_RELABEL:
            with self.subTest(name):
                github, issue = self._approved_issue()
                with patch.object(github, _support.SET_LABEL, _BehindTheRelabel(github, road)):
                    self._run_squash_approval(github, issue, squash)

                self.assertFalse(self._documents(github, issue)[_support.RUN_AGENT].called)
                self.assertEqual(github.label_history, [HANDED_ON, HANDED_BACK])

    def _relabels_behind(self, github, issue, road) -> None:
        """One approval tick whose squash lands, with `road` run behind its relabel."""
        with patch.object(github, _support.SET_LABEL, _BehindTheRelabel(github, road)):
            self._lands_a_collapse(github, issue)

    def _documents(self, github, issue):
        """The documenting tick behind the handoff."""
        return self._run(
            lambda: _documenting._handle_documenting(github, _TEST_SPEC, issue), run_agent=_agent(),
        )

    def _handed_back(self, road, key: str) -> tuple:
        """An approval tick with `road` run behind its relabel, and the documenting tick after it.

        The client and issue, and what that documenting tick left of the
        record under `key`: whether it is still exactly as the approval tick
        left it, whether a docs agent ran, and every label the issue took.
        """
        github, issue = self._approved_issue()
        self._relabels_behind(github, issue, road)
        standing = github.pinned_data(_support.APPROVAL_ISSUE).get(key)
        self.assertIsNotNone(standing)

        ran = self._documents(github, issue)[_support.RUN_AGENT].called

        kept = github.pinned_data(_support.APPROVAL_ISSUE).get(key) == standing
        return github, issue, (kept, ran, list(github.label_history))


if __name__ == "__main__":
    unittest.main()
