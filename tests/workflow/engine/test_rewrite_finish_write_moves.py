# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What moves under a landed rewrite's final steps -- its announcement, relabel, and retirement -- and the run over it.

The real-git finish case (`rewrite_verification_recovery_support`): issue #7's
rebased head reviewed and its finish publishing the landing, the run of the
configured command settled under the anchor and proved ready before the
announcement. Then something it rests on moves while a final step is answered.

Another road settles and reviews a later report of the head: while the
announcement's notice is posted, which refuses the checkpoint; while the
relabel is made, which the run's proof taken once more behind the relabel
reads; or while the retirement itself is sent, which the comment moving under
that write refuses. The run is invalidated into history whole either way, its
revision and binding kept, the later report left as that road wrote it --
the route held with the attempt standing where the write was refused, and
taken on to the fresh reviewer where the proof read it -- and putting the
earlier report and review back before the next poll revives nothing: the head
ends routed with nothing current, its notice and `base_rebased` event said
once.

Or the base advances while the notice is posted or the relabel made: the
proof behind the relabel reads it, invalidates the run, and holds the route
with the attempt standing, and the next tick continues the head to another
rebase it routes, each head announced once.

The run is never made again, and no developer is launched.
"""
from __future__ import annotations

import unittest
from collections.abc import Callable
from functools import partial
from typing import NamedTuple
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


def _retiring(_issue, state, *, over: dict) -> bool:
    """Whether a pinned-comment edit is the one that retires the attempt the comment still carries."""
    retires = state.get(readings.KEY_PENDING_PUSH) is None
    return retires and over.get(readings.KEY_PENDING_PUSH) is not None


class _Window(NamedTuple):
    """A final step something moves under: the client step, the call of it, and how the tick ends.

    `ahead` makes the move ahead of that call rather than behind it, and
    `standing` says whether the attempt still stands behind the tick -- a
    refused write keeps it, a proof that read the move takes the route on.
    """

    name: str
    step: str
    picks: Callable
    ahead: bool = False
    standing: bool = True


class _Step:
    """A client step that has `move` made once, on the call `picks` names: behind that call, or `ahead` of it."""

    def __init__(self, live, window: _Window, move) -> None:
        self._live = live
        self._window = window
        self._move = move
        self._moved = False

    def __call__(self, *args, **kwargs):
        picked = not self._moved and self._window.picks(*args, **kwargs)
        self._moved = self._moved or picked
        if picked and self._window.ahead:
            self._move()
        answered = self._live(*args, **kwargs)
        if picked and not self._window.ahead:
            self._move()
        return answered


class _LaterReport:
    """Another road settling and reviewing report 3 of the head, keeping first the run and the records it moves."""

    def __init__(self, case: support.CapturedRunCase, head: str) -> None:
        self._case = case
        self._head = head
        self._before: dict = {}
        self.settled = None

    def __call__(self) -> None:
        case = self._case
        pinned = readings.pinned(case)
        self._before = {key: pinned.get(key) for key in _MOVED_RECORDS}
        self.settled = readings.pinned_records(case)[1]
        case.state = case.gh.read_pinned_state(case.issue)
        _report.settles_report(case, 3, "Covered a base that moved twice as well.", head=self._head)
        case.gh.write_pinned_state(case.issue, case.state)

    def restores(self) -> None:
        """Write the report and review records back as they stood before report 3 moved them."""
        state = self._case.gh.read_pinned_state(self._case.issue)
        for key, recorded in self._before.items():
            state.set(key, recorded)
        self._case.gh.write_pinned_state(self._case.issue, state)


# Each final step a later report moves under: the notice's post, which the
# checkpoint behind it refuses; the relabel, which the proof behind it reads;
# and the retirement's own edit, which the comment moving under it refuses.
_REPORT_WINDOWS = (
    _Window("while the notice is posted", "pr_comment", _announcing),
    _Window("while the relabel is made", "set_workflow_label", _relabelling, standing=False),
    _Window("while the retirement is sent", "edit_pinned_state", _retiring, ahead=True),
)

# Each final step the base advances under, read by the proof behind the relabel.
_BASE_WINDOWS = _REPORT_WINDOWS[:2]


class FinalStepMoveTest(support.CapturedRunCase, unittest.TestCase):
    """A run something moved under during a final step is invalidated before the route is retired over it."""

    def test_a_moved_report_invalidates_the_run(self) -> None:
        # The run is invalidated in the tick the report moved in, that report
        # kept; the next poll, over the earlier report put back, finds nothing
        # current, and the head is announced once and routed.
        for window in _REPORT_WINDOWS:
            with self.subTest(window=window.name):
                self.setUp()
                head = self.lands_a_reviewed_rebase()
                moves = _LaterReport(self, head)
                self._finishes(head, window, moves)

                self._assert_invalidated(moves.settled)
                standing = self.anchor if window.standing else None
                self.assertEqual(self._held(), (standing, 3))
                moves.restores()
                self.recovers()

                self._assert_invalidated(moves.settled)
                self._assert_routed_once(head)

    def test_a_moved_base_holds_the_route(self) -> None:
        # The proof behind the relabel reads the base gone elsewhere: the run
        # is invalidated and the attempt kept, and the next tick continues
        # the head to another rebase and routes it, each head said once.
        for window in _BASE_WINDOWS:
            with self.subTest(window=window.name):
                self.setUp()
                head = self.lands_a_reviewed_rebase()
                self._finishes(head, window, partial(support.advances_the_base_again, self))

                self.assertEqual(self._tested(), [self.anchor, head])
                self.assertEqual(self._held()[0], self.anchor)
                self.recovers()

                self.assertEqual(self._tested(), [self.anchor, head])
                self._assert_routed_once(head, git_support.remote_head(self))
                self.assertEqual((self.runs(), self.pushes.call_count), (1, 1))

    def _finishes(self, head: str, window: _Window, move) -> None:
        """Publish `head`'s finish with `move` made on the call of the client's step `window` names."""
        stepping = _Step(getattr(self.gh, window.step), window, move)
        with patch.object(self.gh, window.step, stepping):
            self.finishes(head)

    def _held(self) -> tuple:
        """The anchor the attempt still stands on, or None, and the revision of the report settled current."""
        pinned = readings.pinned(self)
        return pinned[readings.KEY_PENDING_PUSH], pinned[_CURRENT_REPORT]["revision"]

    def _tested(self) -> list[str]:
        """The head every evidence record tested, where all went into history invalidated; [] where any did not."""
        records = readings.pinned_records(self)
        reasons = {why for _receipt, why in records[2]}
        if records[:2] != (None, None):
            return []
        if reasons != {readings.INVALIDATED}:
            return []
        history = _settlement.read_evidence_history(self.gh.read_pinned_state(self.issue))
        return [entry.binding.tested_sha for entry in history]

    def _assert_routed_once(self, *heads: str) -> None:
        """Each of `heads` filed as `base_rebased` and announced once, in order, and the attempt retired."""
        said = (support.announced(self), len(readings.notices(self)))
        self.assertEqual(said, (list(heads), len(heads)))
        self.assertEqual(readings.attempt(readings.pinned(self)), readings.RETIRED)

    def _assert_invalidated(self, settled) -> None:
        """`settled` invalidated whole behind the anchor's evidence and nothing current, its command run once."""
        retired = (*git_support.invalidated(self), (settled.receipt, readings.INVALIDATED))
        self.assertEqual(readings.pinned_records(self), (None, None, retired))
        entry = _settlement.read_evidence_history(self.gh.read_pinned_state(self.issue))[-1]
        self.assertEqual((entry.revision, entry.binding), (settled.revision, settled.binding))
        made = (self.runs(), self.developer.call_count)
        self.assertEqual(made, (1, 0))


if __name__ == "__main__":
    unittest.main()
