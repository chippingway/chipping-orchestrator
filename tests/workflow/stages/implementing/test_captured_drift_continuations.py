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
once.
"""
from __future__ import annotations

import unittest
from itertools import product
from types import MappingProxyType
from unittest.mock import MagicMock, patch

from orchestrator.workflow.engine import completion_handoff as _handoff
from tests.support.fakes import FakeComment, FakeUser
from tests.workflow import captured_drifts as _drifts, fix_reports as _fix_world
from tests.workflow.fixtures import _agent, _reported
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


class HeldContinuationTest(unittest.TestCase, _held.HeldCaptureTicks):
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

    def _held_at_the_handoff(self, github, issue, control: str) -> None:
        """Recover once as an operator applies `control` during the transfer's walk: nothing moves or is opened."""
        before = (github.pinned_data(_held.ISSUE), [])
        transfer = _drifts.HeldAtTheWalk(github, issue, control, _handoff.transfer)
        with patch.object(_handoff, "transfer", transfer):
            self._recovered(github, issue)
        self.assertTrue(transfer.applied)
        self.assertEqual((github.pinned_data(_held.ISSUE), github.opened_prs), before)

    def _recovered(self, github, issue) -> None:
        """Dispatch once over the checkout the held run left; no developer may run."""
        recovered = self.dispatch(github, issue, MagicMock(), **_LEFT_A_COMMIT)
        recovered[_held.RUN_AGENT].assert_not_called()

    def _lifted(self, issue, control: str) -> None:
        """Take every `control` label off `issue`."""
        applied = [label for label in issue.labels if label.name == control]
        for label in applied:
            issue.labels.remove(label)


if __name__ == "__main__":
    unittest.main()
