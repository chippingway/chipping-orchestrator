# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The close a developer revision has to catch on both sides of its run.

A resumed developer is the same kind of step a spawn is -- an agent on
somebody's repository, paid for and free to decide -- and the run takes
minutes to hours, which is the whole window a latched close exists for. So the
latch is asked on both sides of it, because neither side covers the other: the
first stops a reading already standing from buying a run at all, and the
second stops the remeasure that would otherwise write a fresh candidate over a
cycle a close already ended.

A poisoned session is guarded separately. That retry exists so a transcript
GitHub's own backend lost does not cost the issue a park, and an issue
somebody has closed is owed neither: it is a SECOND agent against work nobody
wants.

A run that finished on a report is captured as it returns, so the latch is
asked of its recovery too: a close latched behind the run, or while its
capture waited, ends the cycle with nothing re-measured, consumed, or
delivered. A close the recovery reads itself, which it cannot record as
ended, is latched there for the same barriers to end the cycle on. A
cancelled cycle is settled on its own road and never reaches the recovery
again, so the capture it leaves is never finished.
"""
from __future__ import annotations

import unittest

from orchestrator.workflow.stages.decomposition.late_result_models import _LateDisposition
from tests.workflow.fixtures import _TEST_SPEC, LABEL_REJECTED
from tests.workflow.observation_support import ObservedCloseCase
from tests.workflow.stages.decomposition import (
    captured_revision_moves as _moves,
    captured_revision_support as _captured,
)
from tests.workflow.stages.decomposition.late_content_support import (
    KEY_COMMENT_WATERMARK,
)
from tests.workflow.stages.decomposition.late_observation_seams import (
    ISSUE_COMMENT,
    latches_on_call,
)
from tests.workflow.stages.decomposition.late_requirements_support import KEY_USER_CONTENT_HASH
from tests.workflow.stages.decomposition.late_revision_support import (
    DEV_ACK,
    RevisionCase,
)
from tests.workflow.stages.decomposition.late_run_support import agent_reply
from tests.workflow.stages.decomposition.late_test_support import (
    KEYS,
    LATE_ISSUE_NUMBER,
)

_WORKFLOW_LOG = "orchestrator.workflow"

REPO_SLUG = _TEST_SPEC.slug

KEY_OWED_REPLIES = "late_owed_replies"

# The requirements baseline and the reply still owed a whole quote that the
# tick before this one left recorded.
RECORDED_HASH = "recorded-requirements"

OWED_ID = 7

# What a revision finished settles, none of which one a close ended may: its
# consumption of the guidance, and its report's delivery.
_UNSETTLED = (KEY_COMMENT_WATERMARK, _captured.DELIVERED)


class LatchedBeforeTheResumeTest(
    ObservedCloseCase, RevisionCase, unittest.TestCase,
):
    """A revision a poll already ended buys no developer run at all."""

    def setUp(self) -> None:
        self._fresh_process()
        self._seed_drifted()
        self._latch_close(REPO_SLUG, LATE_ISSUE_NUMBER)

    def test_no_developer_is_resumed(self) -> None:
        with self.assertLogs(_WORKFLOW_LOG):
            outcome, spawn = self._revise()

        spawn.assert_not_called()
        self.assertEqual(outcome.disposition, _LateDisposition.CANCELLED)

    def test_the_cancellation_is_persisted(self) -> None:
        with self.assertLogs(_WORKFLOW_LOG):
            self._revise()

        pinned = self._pinned()
        self.assertTrue(pinned[KEYS.cancelled])
        self.assertTrue(pinned[KEYS.cancelled_at])

    def test_the_guidance_is_left_unconsumed(self) -> None:
        # The reply is consumed by the run that acts on it, and no run acted:
        # a watermark moved here would drop a human's instruction with
        # nothing on the issue pointing at it.
        before = self._pinned().get(KEY_COMMENT_WATERMARK)

        with self.assertLogs(_WORKFLOW_LOG):
            self._revise()

        self.assertEqual(
            self._pinned().get(KEY_COMMENT_WATERMARK), before,
        )


class LatchedInsideTheNoticeTest(
    ObservedCloseCase, RevisionCase, unittest.TestCase,
):
    """The sentence this call says before it starts the developer.

    The notice is a request and the park answer behind it is a write, so the
    poll can observe the close inside either -- and what stands next is the
    resume itself.
    """

    def setUp(self) -> None:
        self._fresh_process()
        self._seed_drifted()

    def test_no_developer_is_resumed(self) -> None:
        # The cancellation is written, and the guidance is not consumed by it:
        # no run acted on the reply, so neither the late watermark nor the
        # issue-wide requirements baseline may say one did.
        before = self._pinned().get(KEY_COMMENT_WATERMARK)

        with self.assertLogs(_WORKFLOW_LOG), self._closing():
            outcome, spawn = self._revise()

        spawn.assert_not_called()
        self.assertEqual(outcome.disposition, _LateDisposition.CANCELLED)
        pinned = self._pinned()
        self.assertTrue(pinned[KEYS.cancelled])
        self.assertEqual(pinned.get(KEY_COMMENT_WATERMARK), before)
        self.assertNotIn(KEY_USER_CONTENT_HASH, pinned)

    def _closing(self):
        """Latch the close inside the notice this call posts."""
        return latches_on_call(
            self.github, REPO_SLUG, LATE_ISSUE_NUMBER, ISSUE_COMMENT,
        )


class LatchedDuringTheResumeTest(
    ObservedCloseCase, RevisionCase, unittest.TestCase,
):
    """A close arriving while the developer ran remeasures nothing.

    The run is paid for either way -- an agent that finished is not unpaid by
    a reading taken after it -- so what the barrier protects is the WRITE
    behind it: a remeasured candidate on a cycle a close already ended is a
    fresh candidate nobody asked for.
    """

    def setUp(self) -> None:
        self._fresh_process()
        self._seed_drifted()

    def test_the_candidate_is_not_remeasured(self) -> None:
        with self.assertLogs(_WORKFLOW_LOG):
            outcome, _ = self._revise(reply=_LatchesWhileRunning(self))

        pinned = self._pinned()
        self.assertEqual(outcome.disposition, _LateDisposition.CANCELLED)
        self.assertTrue(pinned[KEYS.cancelled])
        self.assertEqual(pinned[KEYS.candidate_sha], self._frozen())

    def test_the_reading_is_left_unsettled(self) -> None:
        # What the run left is not reconciled, so what it read is not settled
        # either: the cancellation writes the requirements baseline, the late
        # watermark, and the replies still owed as the prior tick left them.
        self.github.seed_state(LATE_ISSUE_NUMBER, **{
            **self._pinned(),
            KEY_USER_CONTENT_HASH: RECORDED_HASH,
            KEY_OWED_REPLIES: [OWED_ID],
        })
        before = self._pinned().get(KEY_COMMENT_WATERMARK)

        with self.assertLogs(_WORKFLOW_LOG):
            outcome, _ = self._revise(reply=_LatchesWhileRunning(self))

        pinned = self._pinned()
        self.assertEqual(outcome.disposition, _LateDisposition.CANCELLED)
        self.assertEqual(pinned[KEY_USER_CONTENT_HASH], RECORDED_HASH)
        self.assertEqual(pinned[KEY_OWED_REPLIES], [OWED_ID])
        self.assertEqual(pinned.get(KEY_COMMENT_WATERMARK), before)

    def _frozen(self) -> str:
        """The commit the generation was carrying before this tick ran."""
        return self.generation_sha


class LatchedOverACapturedRevisionTest(
    ObservedCloseCase, _captured.CapturedRevisionCase, unittest.TestCase,
):
    """A close latched over a revision whose report was captured revives none of it."""

    def setUp(self) -> None:
        self._fresh_process()
        self._seed_drifted()
        self.generation_sha = self._pinned()[KEYS.candidate_sha]

    def test_a_close_over_it_revives_nothing(self) -> None:
        # Latched while the run worked, or while its capture waited out a
        # pause -- or read by the recovery itself over a comment that would
        # not read again to record it, and latched then: either way the cycle
        # is cancelled with the candidate, the guidance, and the report left
        # as they stood, and the next dispatch settles the cancelled cycle's
        # terminal and finishes nothing of it.
        for latched in (
            self._latched_during_the_run, self._latched_while_it_waited, self._latched_while_measured,
            self._latched_in_the_last_read, self._read_closed_over_an_unread_comment,
        ):
            with self.subTest(latched=latched.__name__):
                self.setUp()
                with self.assertLogs(_WORKFLOW_LOG):
                    latched()
                    self._dispatched().assert_not_called()

                pinned = self._pinned()
                self.assertEqual(self.github.label_history, [(LATE_ISSUE_NUMBER, LABEL_REJECTED)])
                self.assertEqual(_captured.capture_of(pinned).stage, _captured.PENDING)
                self.assertEqual(pinned[KEYS.candidate_sha], self.generation_sha)
                self.assertEqual([field for field in _UNSETTLED if field in pinned], [])

    def _latched_during_the_run(self) -> None:
        """A run finishing on its report, a poll latching the close while it ran."""
        outcome, _ = self._revise(reply=_LatchesWhileRunning(self, _captured.DEV_REPORT))
        self.assertEqual(outcome.disposition, _LateDisposition.CANCELLED)

    def _latched_while_it_waited(self) -> None:
        """A run held under `paused`, a poll latching the close once the control comes off; its dispatch."""
        self._held()
        self._released()
        self._latch_close(REPO_SLUG, LATE_ISSUE_NUMBER)
        self._dispatched().assert_not_called()
        self.assertTrue(self._pinned()[KEYS.cancelled])

    def _latched_while_measured(self) -> None:
        """A run held under `paused` and released, a poll latching the close as its recovery measures; that dispatch.

        The close lands behind every reading the recovery took and ahead of
        the commit handing the report on, so that commit asks the latch again
        and the cycle is cancelled in the same dispatch, with nothing of it.
        """
        self._held()
        self._released()
        latching = _moves.MeasuredWhile(self._latch_close, REPO_SLUG, LATE_ISSUE_NUMBER)
        self._dispatched(alongside=latching.patched()).assert_not_called()
        self.assertTrue(self._pinned()[KEYS.cancelled])

    def _latched_in_the_last_read(self) -> None:
        """A run held and released, a poll latching the close as its recovery's question reads the comment last.

        The latch is the last thing that question asks, behind every request
        it makes, so the handoff is held and the cycle cancelled in the same
        dispatch, with nothing of it.
        """
        self._held()
        self._released()
        latching = _moves.InTheLastRead(self, self._latch_close, REPO_SLUG, LATE_ISSUE_NUMBER)
        self._dispatched(alongside=latching.patched()).assert_not_called()
        self.assertTrue(self._pinned()[KEYS.cancelled])

    def _read_closed_over_an_unread_comment(self) -> None:
        """A run held and released, closed with no poll to latch it as its recovery measures; reopened; its dispatch.

        The admission the handoff's edit asks again reads the close and holds
        the handoff, but the pinned comment will not read again to record the
        cancellation: the close is latched for the cycle instead, so the
        dispatch after the issue is reopened ends that cycle with nothing of it.
        """
        self._held()
        self._released()
        closing = _moves.MeasuredWhile(setattr, self.issue, "closed", True)
        unread = _captured.UnreadOnceClosed(self)
        with unread.patched():
            self._dispatched(alongside=closing.patched()).assert_not_called()
        self.assertTrue(unread.seen)
        self.assertFalse(self._pinned().get(KEYS.cancelled))
        self.assertIn(LATE_ISSUE_NUMBER, self._observed(REPO_SLUG))
        self.issue.closed = False
        self._dispatched().assert_not_called()
        self.assertTrue(self._pinned()[KEYS.cancelled])


class _LatchesWhileRunning:
    """A developer run a poll observes the close during, finishing on `reply`."""

    def __init__(self, case, reply: str = DEV_ACK) -> None:
        self._case = case
        self._reply = reply
        case.generation_sha = case._pinned()[KEYS.candidate_sha]

    def __call__(self, *_asked, **_answering):
        """Answer the run, having latched the close inside it."""
        self._case._latch_close(REPO_SLUG, LATE_ISSUE_NUMBER)
        return agent_reply(self._reply)


if __name__ == "__main__":
    unittest.main()
