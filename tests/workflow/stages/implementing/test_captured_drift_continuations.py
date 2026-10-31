# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""A held continuation of a mid-implementation drift park, handed on only over an admission that still stands.

A body edit's resume of the developer session that parks -- on a question, or
on a timeout -- is answered by a human's reply or a bare continue, and that
answer resumes the session on the implementing resume road. Held as it
reports, its capture is finished by the implementing recovery, whose
disposition hands the report on only once the capture's admission reads
again, behind the strict edit's walk to the comment last: a control applied
during that walk hands nothing on, settles, consumes, or publishes nothing,
and leaves the park standing, and the dispatch behind it publishes the report
once. A count of the branch that git cannot take holds it the same way: no
proof the run left nothing, so nothing is withdrawn, settled, or parked until
a dispatch whose count returns publishes it.
"""
from __future__ import annotations

import unittest
from itertools import product
from types import MappingProxyType, SimpleNamespace
from unittest.mock import MagicMock, patch

from orchestrator.git.worktrees import creation as _worktree_creation
from orchestrator.workflow.engine import completion_handoff as _handoff
from orchestrator.workflow.stages.implementing import disposition as _disposition
from tests.support.fakes import FakeComment, FakeUser
from tests.workflow import captured_drifts as _drifts, fix_reports as _fix_world
from tests.workflow.fixtures import Launched, _agent, _reported
from tests.workflow.stages.implementing import held_capture_test_support as _held

_SESSION = "dev-sess"

# The issue's developer session, pinned under its command, and the edit that
# resumes it.
_SESSION_PIN = MappingProxyType({"dev_agent": "claude", _held.SESSION_PIN: _SESSION})

_EDITED_BODY = "updated requirements"

# Where a human's answer lands: above everything the seeded thread carries.
_ANSWER_ID = 9_000

# The two answers a drift resume's park takes, each beside what that resume
# came back as to park so: a reply to the question it asked, and a bare
# continue behind a run that timed out.
_CONTINUATIONS = MappingProxyType({
    "reply": (
        MappingProxyType({"last_message": "Which option should I use?"}),
        FakeComment(id=_ANSWER_ID, body="Use the existing helper.", user=FakeUser("alice")),
    ),
    "continue": (
        MappingProxyType({"timed_out": True, "last_message": ""}),
        FakeComment(id=_ANSWER_ID, body="/orchestrator continue", user=FakeUser("alice")),
    ),
})

_HOLDS = tuple(product(_CONTINUATIONS, (_held.PAUSED, _held.BACKLOG)))

# What the answer's resume comes back as: its report, on the conversation it resumed.
_REPORTED = _agent(session_id=_SESSION, last_message=_reported())

# A run that committed nothing, and the checkout a run that committed left.
_COMMITTED_NOTHING = MappingProxyType({"has_new_commits": False, "head_shas": _held.UNMOVED})

_LEFT_A_COMMIT = MappingProxyType({"has_new_commits": True, "head_shas": _held.LEFT})

# The branch's commit count as the disposition asks it, the owner's own
# reading, over a `rev-list` git could not walk.
_UNCOUNTED = SimpleNamespace(_has_new_commits=_worktree_creation._has_new_commits)

_FAILED_WALK = SimpleNamespace(returncode=1, stdout="", stderr="fatal: failed to read history")

# A recovery whose checkout reads as the commit the held run left at its
# admission and once behind it, will not read the time after, and reads as
# that commit again from then on.
_LOST_ONCE = MappingProxyType({"head_shas": (_held.SOURCE, _held.SOURCE, "", _held.SOURCE)})


class _HeldContinuations(_held.HeldCaptureTicks):
    """Whole dispatches of an edited implementing issue whose drift resume parked, its answer's resume held."""

    def _continued(self, continuation: tuple, control: str):
        """The edited issue whose drift resume parked, the answer's resume of that park held under `control`."""
        parks_as, answer = continuation
        github, issue = self.seeded(**_SESSION_PIN)
        issue.body = _EDITED_BODY
        parked = _agent(session_id=_SESSION, **parks_as)
        self.dispatch(github, issue, parked, **_COMMITTED_NOTHING)
        self.assertTrue(github.pinned_data(_held.ISSUE)["awaiting_human"])
        issue.comments.append(answer)
        self.held_mid_run(github, issue, _REPORTED, control, has_new_commits=True)
        self._lifted(issue, control)
        return github, issue

    def _recovered(self, github, issue, **seams) -> None:
        """Dispatch once over the checkout the held run left, read as `seams` say; no developer may run."""
        recovered = self.dispatch(github, issue, MagicMock(), **{**_LEFT_A_COMMIT, **seams})
        recovered[_held.RUN_AGENT].assert_not_called()

    def _lifted(self, issue, control: str) -> None:
        """Take every `control` label off `issue`."""
        applied = [label for label in issue.labels if label.name == control]
        for label in applied:
            issue.labels.remove(label)


class HeldContinuationTest(unittest.TestCase, _HeldContinuations):
    """A held reply or continue on a drift park is handed on once, and never past a control applied at its handoff."""

    def test_a_control_at_the_handoff_holds_it(self) -> None:
        # The answer's resume is held as it reports, and the control comes
        # off; an operator applies it again as the strict editor sending the
        # transfer's edit walks to the comment, under either control: nothing
        # is handed on, settled, consumed, or published, and the park stands.
        # Once that control comes off too, the next dispatch publishes the
        # report once, with no developer run.
        for name, control in _HOLDS:
            with self.subTest(continuation=name, control=control), _fix_world.author_policy():
                github, issue = self._continued(_CONTINUATIONS[name], control)
                self._held_at_the_handoff(github, issue, control)
                self._lifted(issue, control)
                self._recovered(github, issue)
                self.published(github)

    def test_an_uncounted_branch_keeps_it(self) -> None:
        # The answer's resume is held as it reports, and the control comes
        # off over a branch git cannot count ahead of its base, under either
        # control and for either answer: that is no proof the run left
        # nothing, so the capture is kept with nothing withdrawn, settled,
        # consumed, parked, or published -- the reply boundary and the
        # baseline as the hold left them. The dispatch whose count returns
        # publishes the report once, with no developer run.
        for name, control in _HOLDS:
            with self.subTest(continuation=name, control=control), _fix_world.author_policy():
                github, issue = self._continued(_CONTINUATIONS[name], control)
                self._recovered_uncounted(github, issue)
                self._recovered(github, issue)
                self.published(github)

    def _held_at_the_handoff(self, github, issue, control: str) -> None:
        """Recover once as an operator applies `control` during the transfer's walk: nothing moves or is opened."""
        before = (github.pinned_data(_held.ISSUE), [])
        transfer = _drifts.HeldAtTheWalk(github, issue, control, _handoff.transfer)
        with patch.object(_handoff, "transfer", transfer):
            self._recovered(github, issue)
        self.assertTrue(transfer.applied)
        self.assertEqual((github.pinned_data(_held.ISSUE), github.opened_prs), before)

    def _recovered_uncounted(self, github, issue) -> None:
        """Recover once as git fails to count the branch ahead of its base: nothing moves or is opened."""
        before = Launched.over(github, _held.ISSUE)
        unwalked = SimpleNamespace(_git=MagicMock(return_value=_FAILED_WALK))
        with (
            patch.object(_disposition, "_worktree_creation", _UNCOUNTED),
            patch.object(_worktree_creation, "commands", unwalked),
        ):
            self._recovered(github, issue)
        unwalked._git.assert_called()
        after = Launched.over(github, _held.ISSUE)
        self.assertEqual((after, github.opened_prs), (before, []))


class CapturedHeadTest(unittest.TestCase, _HeldContinuations):
    """A held answer's recovery never reads a HEAD that will not read behind its capture as a run that left nothing."""

    def test_a_lost_head_keeps_it(self) -> None:
        # The checkout reads as the commit the held run left at the
        # recovery's admission and once behind it, and will not read the time
        # after, under either control and for either answer: the disposition
        # answers on the head the capture names rather than reading the run
        # as one that left nothing and parking it as a question, its capture
        # withdrawn, and the admission read again before the handoff keeps
        # the capture over that reading with nothing written or published.
        # The dispatch whose head reads publishes the report once, with no
        # developer run.
        for name, control in _HOLDS:
            with self.subTest(continuation=name, control=control), _fix_world.author_policy():
                continued = self._continued(_CONTINUATIONS[name], control)
                before = Launched.over(continued[0], _held.ISSUE)
                self._recovered(*continued, **_LOST_ONCE)
                kept = Launched.over(continued[0], _held.ISSUE)
                self.assertEqual((kept, continued[0].opened_prs), (before, []))
                self._recovered(*continued)
                self.published(continued[0])


if __name__ == "__main__":
    unittest.main()
