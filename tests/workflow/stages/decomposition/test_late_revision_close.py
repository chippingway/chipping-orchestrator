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
"""
from __future__ import annotations

import unittest

from orchestrator.workflow.stages.decomposition.late_result_models import _LateDisposition
from tests.workflow.fixtures import _TEST_SPEC
from tests.workflow.observation_support import ObservedCloseCase
from tests.workflow.stages.decomposition.late_content_support import (
    KEY_COMMENT_WATERMARK,
)
from tests.workflow.stages.decomposition.late_observation_seams import (
    ISSUE_COMMENT,
    latches_on_call,
)
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
        with self.assertLogs(_WORKFLOW_LOG), self._closing():
            outcome, spawn = self._revise()

        spawn.assert_not_called()
        self.assertEqual(outcome.disposition, _LateDisposition.CANCELLED)
        self.assertTrue(self._pinned()[KEYS.cancelled])

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

    def _frozen(self) -> str:
        """The commit the generation was carrying before this tick ran."""
        return self.generation_sha


class _LatchesWhileRunning:
    """A developer run a poll observes the close during."""

    def __init__(self, case) -> None:
        self._case = case
        case.generation_sha = case._pinned()[KEYS.candidate_sha]

    def __call__(self, *_asked, **_answering):
        """Answer the run, having latched the close inside it."""
        self._case._latch_close(REPO_SLUG, LATE_ISSUE_NUMBER)
        return agent_reply(DEV_ACK)


if __name__ == "__main__":
    unittest.main()
