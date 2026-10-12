# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""A report that moves under a landed rewrite's announcement or retirement, its settled run invalidated over it.

The real-git finish case (`rewrite_verification_recovery_support`): issue #7's
rebased head reviewed and its finish publishing the landing, the run of the
configured command settled under the anchor and proved ready before the
announcement. Another road then settles and reviews a later report of the
head -- while the announcement's notice is posted, or while the relabel to
`workflow:validating` is made -- so the write behind that step, the
checkpoint or the retirement, is refused over the moved records. That refusal
is movement read under the run: it is invalidated into history whole there and
then, its revision and binding kept, with the attempt standing and the later
report left as that road wrote it. Putting the earlier report and review back
before the next poll revives nothing: the recovery routes the head with
nothing current and the attempt retired. The run is never made again, nothing
is pushed, and no developer is launched.
"""
from __future__ import annotations

import unittest
from unittest.mock import patch

from orchestrator.workflow.engine import verification_settlement_state as _settlement
from orchestrator.workflow.state import WorkflowLabel
from tests.workflow.engine import (
    rewrite_finish_git_support as git_support,
    rewrite_finish_readings as readings,
    rewrite_verification_recovery_support as support,
    verification_report_fixture as _report,
)

# The report and review records a later report's settlement moves, as the
# pinned comment spells them.
_MOVED_RECORDS = (
    "developer_report_current",
    "developer_report_handoff",
    "review_subject",
    "review_returned_subject",
)

_CURRENT_REPORT = "developer_report_current"


def _announcing(_pr_number, body: str, *_args, **_kwargs) -> bool:
    """Whether a pull-request post is a landing's announcement."""
    return body.startswith(":mag:")


def _relabelling(_issue, label, *_args, **_kwargs) -> bool:
    """Whether a label write is the route to `workflow:validating`."""
    return label == WorkflowLabel.VALIDATING


# Each final write a step's moved report refuses: the step the report moves
# behind, and the call of it that is that step.
_FINAL_WRITES = (
    ("the announcement's checkpoint", "pr_comment", _announcing),
    ("the retirement behind the relabel", "set_workflow_label", _relabelling),
)


class _ReportMovesBehind:
    """A client step that, once the call `picks` names has answered, has another road settle a later report.

    Before it does, it keeps the run current then (`settled`) and the report
    and review records as they stood (`restores` writes them back).
    """

    def __init__(self, case: support.CapturedRunCase, head: str, live, picks) -> None:
        self._case = case
        self._head = head
        self._live = live
        self._picks = picks
        self._before: dict = {}
        self.settled = None

    def __call__(self, *args, **kwargs):
        answered = self._live(*args, **kwargs)
        if not self._before and self._picks(*args, **kwargs):
            case = self._case
            pinned = readings.pinned(case)
            self._before = {key: pinned.get(key) for key in _MOVED_RECORDS}
            self.settled = readings.pinned_records(case)[1]
            case.state = case.gh.read_pinned_state(case.issue)
            _report.settles_report(case, 3, "Covered a base that moved twice as well.", head=self._head)
            case.gh.write_pinned_state(case.issue, case.state)
        return answered

    def restores(self) -> None:
        """Write the report and review records back as they stood before the later report moved them."""
        state = self._case.gh.read_pinned_state(self._case.issue)
        for key, recorded in self._before.items():
            state.set(key, recorded)
        self._case.gh.write_pinned_state(self._case.issue, state)


class FinalWriteMoveTest(support.CapturedRunCase, unittest.TestCase):
    """A run a refused final write read its report moving under is invalidated before the finish stops."""

    def test_a_moved_report_invalidates_the_run(self) -> None:
        # The checkpoint or the retirement is refused over the later report:
        # the run is invalidated then, the attempt and that report kept, and
        # the next poll, over the earlier report put back, routes the head
        # with nothing current rather than with the run.
        for name, step, picks in _FINAL_WRITES:
            with self.subTest(write=name):
                self.setUp()
                moves = self._finishes_moving(step, picks)

                self._assert_invalidated(moves.settled)
                self.assertEqual(self._held(), (self.anchor, 3))
                moves.restores()
                self.recovers()

                self._assert_invalidated(moves.settled)
                self.assertEqual(readings.relabels(self)[-1], WorkflowLabel.VALIDATING)
                self.assertEqual(readings.attempt(readings.pinned(self)), readings.RETIRED)

    def _finishes_moving(self, step: str, picks) -> _ReportMovesBehind:
        """Publish a reviewed rebase's finish with a later report settling behind the `step` call `picks`; the move."""
        head = self.lands_a_reviewed_rebase()
        moves = _ReportMovesBehind(self, head, getattr(self.gh, step), picks)
        with patch.object(self.gh, step, moves):
            self.finishes(head)
        return moves

    def _held(self) -> tuple:
        """The anchor the attempt still stands on, and the revision of the report settled current."""
        pinned = readings.pinned(self)
        return pinned[readings.KEY_PENDING_PUSH], pinned[_CURRENT_REPORT]["revision"]

    def _assert_invalidated(self, settled) -> None:
        """`settled` invalidated whole behind the anchor's evidence, run once, nothing pushed or launched."""
        retired = (*git_support.invalidated(self), (settled.receipt, readings.INVALIDATED))
        self.assertEqual(readings.pinned_records(self), (None, None, retired))
        entry = _settlement.read_evidence_history(self.gh.read_pinned_state(self.issue))[-1]
        self.assertEqual((entry.revision, entry.binding), (settled.revision, settled.binding))
        made = (self.runs(), self.pushes.call_count, self.developer.call_count)
        self.assertEqual(made, (1, 0, 0))


if __name__ == "__main__":
    unittest.main()
