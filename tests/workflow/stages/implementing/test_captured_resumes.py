# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""An implementing run's captured report, held under a live pause and finished by the recovery after it.

A human reply and an operator's `/orchestrator continue` each resume the
developer on a parked issue. The run's report is captured as it returns, and
while the issue is held nothing it was handed is consumed: the park stands,
the reply boundary stays below the reply or the command, and the session is
neither pinned nor charged. Unpaused, the dispatcher's recovery settles
exactly what that run was handed -- the reply batch, or the commands the
retry consumed -- takes the park down, charges the resumed conversation once,
and publishes the commit under the captured report, with no developer
running again. A run that reports without committing parks as its own tick
always did, and withdraws its capture first, so the reply that answers the
park is captured afresh. A report captured while an earlier capture's report
still waits unbound for its push replaces that capture by carrying it, and
its recovery publishes the later report. What the recovery settles of the
session is what the run's own tick would have: the pin its launch kept, and
one resume charged however the transfer behind it was interrupted.
"""
from __future__ import annotations

import sys
import unittest
from types import MappingProxyType
from unittest.mock import MagicMock, patch

from tests.support.fakes import FakeComment, FakeUser
from tests.workflow.fixtures import _agent, _reported, accounted
from tests.workflow.stages.implementing import held_capture_test_support as _held

_PARKED_AT = 900
_ANSWER_ID = 1100
_SESSION = "sess-resumed"

_AWAITING = "awaiting_human"
_BOUNDARY = "last_action_comment_id"

# A parked issue whose conversation is pinned under a command: the resume
# answering a human reply runs on it.
_PARKED = MappingProxyType({
    _AWAITING: True,
    _BOUNDARY: _PARKED_AT,
    "dev_agent": "claude",
    _held.SESSION_PIN: _SESSION,
})

# The same park, taken over a session failure an operator retries.
_SILENT = MappingProxyType({**_PARKED, "park_reason": "agent_silent"})

# What a resume answering each of those reads as delivered: the reply, or
# the command.
_GUIDANCE = "use the existing helper instead"
_CONTINUE = "/orchestrator continue"

# The control an operator holds each resume's issue under, while it runs.
_HELD_UNDER = MappingProxyType({_GUIDANCE: _held.BACKLOG, _CONTINUE: _held.PAUSED})

# A reply posted after the park a failed push took, and a conversation an
# earlier cycle left pinned.
_LATER_REPLY_ID = 10000
_PRIOR_SESSION = "prior-session"
_RESUMES = "dev_resume_count"
_STAGE = "stage"
_ORDINAL = "ordinal"

# The report transaction an issue's settled publication leaves `null`.
_TRANSACTION = "developer_report_pending"


def _finished():
    """What the developer's run comes back as: its report, on the conversation it resumed."""
    return _agent(session_id=_SESSION, last_message=_reported())


def _answered(answer: str, comment_id: int = _ANSWER_ID) -> FakeComment:
    """A trusted human's reply above the park, saying `answer`."""
    return FakeComment(id=comment_id, body=answer, user=FakeUser("alice"))


class HeldResumeTest(unittest.TestCase, _held.HeldCaptureTicks):
    """A held resume's capture settles exactly what its run was handed, once the recovery finishes it."""

    def test_each_resume_settles_what_it_delivered(self) -> None:
        # The reply held under `backlog` and the retry under `paused` alike:
        # held, the park and its boundary stand and nothing is pinned or
        # charged; recovered, the boundary moves over the answer the run
        # consumed, the park comes down, the resumed conversation is charged
        # once, and the commit is published under the captured report -- one
        # accounted exit, one report, no second run.
        for parked, answer in ((_PARKED, _GUIDANCE), (_SILENT, _CONTINUE)):
            with self.subTest(answer=answer):
                github, issue = self.seeded(**parked)
                issue.comments.append(_answered(answer))
                held = self.held_mid_run(github, issue, _finished(), control=_HELD_UNDER[answer])
                self.held_ticks(github, issue)
                self.unpaused(github, issue)
                self._settled(held, self.published(github))

    def _settled(self, held: dict, recovered: dict) -> None:
        """`held` kept the park over the answer; `recovered` consumed it once and charged the conversation once."""
        self.assertEqual(
            (held[_AWAITING], held[_BOUNDARY], held.get("dev_resume_count")),
            (True, _PARKED_AT, None),
        )
        self.assertGreaterEqual(recovered[_BOUNDARY], _ANSWER_ID)
        self.assertEqual(
            (
                recovered[_AWAITING],
                recovered[_held.SESSION_PIN],
                recovered["dev_resume_count"],
                accounted(recovered),
                recovered[_held.CAPTURED]["stage"],
            ),
            (False, _SESSION, 1, (1, 1), _held.HANDED_OFF),
        )


class UnpublishedCaptureTest(unittest.TestCase, _held.HeldCaptureTicks):
    """A captured report its run's own tick publishes nothing under is withdrawn before the park."""

    def test_a_report_with_no_commit_is_withdrawn(self) -> None:
        # Unpaused, the first implementation reports and commits nothing, so
        # its tick parks on the question as ever -- the capture retired first,
        # its invocation kept, and nothing published. The next dispatch finds
        # nothing to recover and leaves the park to the reply it waits on.
        github, issue = self.seeded()
        for runs in (1, 0):
            ran = self.dispatch(
                github,
                issue,
                _finished(),
                has_new_commits=False,
                head_shas=_held.UNMOVED,
            )
            self.assertEqual(ran[_held.RUN_AGENT].call_count, runs)
            self._withdrawn(github.pinned_data(_held.ISSUE))
        self.assertEqual(github.opened_prs, [])

    def _withdrawn(self, parked: dict) -> None:
        """`parked` waits on the question, its capture retired as no longer applying."""
        withdrawn = parked[_held.CAPTURED]
        self.assertEqual(
            (withdrawn["stage"], withdrawn["reason"], parked[_AWAITING]),
            (_held.RETIRED, "invalidated", True),
        )


class SupersededReportTest(unittest.TestCase, _held.HeldCaptureTicks):
    """A report captured beside an earlier captured report still waiting unbound is kept, and published once."""

    def test_a_held_reply_supersedes_unbound_report(self) -> None:
        # The first implementation's report is handed to the delivery and its
        # push fails, so the delivery waits unbound and the issue parks. A
        # reply's resume reports again while an operator holds the issue: the
        # report is captured, replacing the handoff by carrying it, and nothing
        # else moves. Unpaused, the recovery publishes that later report with
        # no developer run, superseding the delivery that never went out. A
        # transaction an earlier cycle settled, its record left `null`, holds
        # none of it.
        for settled in ({}, {_TRANSACTION: None}):
            with self.subTest(settled=settled):
                self._superseded(**settled)

    def _superseded(self, **record) -> None:
        """The first report's push fails, a held reply's report carries its handoff, and the recovery publishes it."""
        github, issue = self.seeded(dev_agent="claude", **record)
        self.dispatch(
            github,
            issue,
            _agent(session_id=_SESSION, last_message=_reported("first")),
            has_new_commits=[False, True],
            push_branch=False,
        )
        issue.comments.append(_answered(_GUIDANCE, _LATER_REPLY_ID))
        held = self.held_mid_run(
            github,
            issue,
            _finished(),
            has_new_commits=True,
            head_shas=_held.LEFT,
        )[_held.CAPTURED]
        superseded = held["supersedes"]
        self.assertEqual(
            (held[_ORDINAL], superseded[_STAGE], superseded[_ORDINAL]),
            (2, _held.HANDED_OFF, 1),
        )
        self.unpaused(github, issue)
        recovered = self.published(github, revision=2)[_held.CAPTURED]
        self.assertEqual(
            (recovered[_STAGE], recovered[_ORDINAL]),
            (_held.HANDED_OFF, 2),
        )


class SessionSettlementTest(unittest.TestCase, _held.HeldCaptureTicks):
    """The session a recovery settles is what the run's own tick would have settled, once."""

    def test_an_interrupted_transfer_charges_once(self) -> None:
        # The process is lost as the transfer goes out, or right after it
        # landed: what the tick settled lands with the handoff or not at all.
        # Before it, the restarted dispatch's recovery settles the resumed
        # conversation from the capture; after it, the handed-off delivery is
        # published under a park already down. Either way the resume is
        # charged once and no developer runs again.
        for landed in (False, True):
            with self.subTest(landed=landed):
                github, issue = self.seeded(**_PARKED)
                issue.comments.append(_answered(_GUIDANCE))
                lost = patch.object(github, "edit_pinned_state", _LostAtTheTransfer(github, landed=landed))
                with lost, self.assertRaises(SystemExit):
                    self.dispatch(github, issue, _finished(), has_new_commits=True)
                self._restarted(github, issue, landed=landed)

    def test_a_fresh_spawn_keeps_its_launch_pin(self) -> None:
        # A first implementation on an issue an earlier conversation stays
        # pinned on, returning no session id of its own: its own tick leaves
        # that pin standing, and so does the recovery of its held return.
        kept = []
        for held in (False, True):
            github, issue = self.seeded(dev_agent="claude", **{_held.SESSION_PIN: _PRIOR_SESSION})
            finished = _agent(session_id=None, last_message=_reported())
            if held:
                self.held_mid_run(github, issue, finished, has_new_commits=[False])
                self.unpaused(github, issue)
            else:
                self.dispatch(github, issue, finished, has_new_commits=[False, True])
            kept.append(self.published(github).get(_held.SESSION_PIN))
        self.assertEqual(kept, [_PRIOR_SESSION, _PRIOR_SESSION])

    def _restarted(self, github, issue, *, landed: bool) -> None:
        """The record the lost process left, and the dispatch after it publishing with one resume charged."""
        lost = github.pinned_data(_held.ISSUE)
        left = (lost[_held.CAPTURED][_STAGE], lost.get(_RESUMES))
        expected = (_held.HANDED_OFF, 1) if landed else (_held.PENDING, None)
        self.assertEqual(left, expected)
        recovered = self.dispatch(github, issue, MagicMock(), has_new_commits=True, head_shas=_held.LEFT)
        recovered[_held.RUN_AGENT].assert_not_called()
        self.assertEqual(self.published(github)[_RESUMES], 1)


class _LostAtTheTransfer:
    """The strict edit, the process lost at the one handing a capture off: before it is sent, or once it landed."""

    def __init__(self, github, *, landed: bool) -> None:
        self._github = github
        self._landed = landed

    def __call__(self, issue, state, *, over: dict):
        """Send the edit, losing the process around the one that hands the capture off."""
        captured = state.get(_held.CAPTURED) or {}
        handing_off = captured.get(_STAGE) == _held.HANDED_OFF
        if handing_off and not self._landed:
            sys.exit("the process was lost as the transfer went out")
        sent = type(self._github).edit_pinned_state(self._github, issue, state, over=over)
        if handing_off:
            sys.exit("the process was lost once the transfer landed")
        return sent


if __name__ == "__main__":
    unittest.main()
