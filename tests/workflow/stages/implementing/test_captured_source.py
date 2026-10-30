# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""A report a capture handed off is published only from the commit the capture reported on.

The handed-off capture is the one record of the commit its report is about,
and the binding refuses any other publication of that report -- after the
push, with a pull request already open over it. So the size gate is named
that commit as its candidate wherever the report is still owed, and a
checkout something moved off it is parked before anything is measured,
pushed, or opened: on the captured run's own tick, on the recovery of a held
one, and on the tick after a process lost behind the transfer.
"""
from __future__ import annotations

import sys
import unittest
from unittest.mock import MagicMock, patch

from orchestrator.git.measurement import commits as _commits
from orchestrator.git.measurement.models import FrozenCommit
from orchestrator.git.verification import probes as _probes
from tests.workflow.fixtures import _agent, _reported
from tests.workflow.repo_values import HEAD_BEFORE_RUN
from tests.workflow.stages.implementing import held_capture_test_support as _held

# A commit something landed over the checkout after the capture.
_MOVED = "eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee"
_MOVED_COMMIT = FrozenCommit(sha=_MOVED)
_EDIT = "edit_pinned_state"
_PUSH = "_push_branch"


def _finished():
    """What the first implementation's run comes back as: its report, with no session named."""
    return _agent(session_id=None, last_message=_reported())


class CapturedSourceTest(unittest.TestCase, _held.HeldCaptureTicks):
    """A checkout moved off the captured source publishes nothing, the report kept for the commit it is about."""

    def test_its_own_tick_holds_the_source(self) -> None:
        # The run reports, its capture is handed off, and the checkout moves
        # before the gate reads it: nothing is measured or pushed.
        github, issue = self.seeded()
        ran = self.dispatch(
            github,
            issue,
            _finished(),
            has_new_commits=[False, True],
            head_shas=(HEAD_BEFORE_RUN, _held.SOURCE, _MOVED),
            candidate_commit=_MOVED_COMMIT,
        )
        self.assert_published_nothing(github, ran)

    def test_its_recovery_holds_the_source(self) -> None:
        # A held return's recovery hands the capture off, and the checkout
        # moves right behind that transfer: the gate parks it.
        github, issue = self.seeded()
        self.held_mid_run(github, issue, _finished(), has_new_commits=[False])
        with patch.object(github, _EDIT, _AtTheTransfer(github, moves=True)):
            ran = self.unpaused(github, issue)
        self.assert_published_nothing(github, ran)

    def test_a_restart_holds_the_source(self) -> None:
        # The process is lost once the transfer landed, and the checkout has
        # moved by the next tick: the restart shortcut publishes nothing.
        github, issue = self.seeded()
        lost = patch.object(github, _EDIT, _AtTheTransfer(github, moves=False))
        with lost, self.assertRaises(SystemExit):
            self.dispatch(github, issue, _finished(), has_new_commits=[False, True])
        ran = self.dispatch(
            github,
            issue,
            MagicMock(),
            has_new_commits=True,
            head_shas=(_MOVED,),
            candidate_commit=_MOVED_COMMIT,
        )
        ran[_held.RUN_AGENT].assert_not_called()
        self.assert_published_nothing(github, ran)

    def assert_published_nothing(self, github, ran) -> None:
        """Nothing pushed or opened, the issue parked, and the handed-off report still about the captured source."""
        pinned = github.pinned_data(_held.ISSUE)
        handoff = pinned[_held.CAPTURED]
        self.assertEqual(
            (ran[_PUSH].call_count, github.opened_prs, pinned.get("awaiting_human")),
            (0, [], True),
        )
        self.assertEqual(
            (handoff["stage"], handoff["source"]),
            (_held.HANDED_OFF, _held.SOURCE),
        )


class _AtTheTransfer:
    """The strict edit, and what happens once the one handing a capture off has landed.

    `moves` lands a commit over the checkout, which every later head reading
    and candidate proof then answers with; otherwise the process is lost.
    """

    def __init__(self, github, *, moves: bool) -> None:
        self._github = github
        self._moves = moves

    def __call__(self, issue, state, *, over: dict):
        """Send the edit, and move the checkout or lose the process behind the one handing a capture off."""
        sent = type(self._github).edit_pinned_state(self._github, issue, state, over=over)
        captured = state.get(_held.CAPTURED) or {}
        if captured.get("stage") != _held.HANDED_OFF:
            return sent
        if not self._moves:
            sys.exit("the process was lost once the transfer landed")
        _probes._head_sha.side_effect = None
        _probes._head_sha.return_value = _MOVED
        _commits._prove_candidate_commit.side_effect = self._proved
        return sent

    def _proved(self, worktree, revision: str) -> FrozenCommit:
        """The checkout's head proves to the moved commit; a named revision to itself."""
        return _MOVED_COMMIT if revision == "HEAD" else FrozenCommit(sha=revision)


if __name__ == "__main__":
    unittest.main()
