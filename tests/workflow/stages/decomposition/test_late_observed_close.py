# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The close no request this run could make would ever show it.

A poll that finds a late-split owner closed while a worker holds it can hand
that reading to no second worker, and a human who reopens the issue before the
next pass takes it off the remote for good. So the reading is latched, and the
run in flight asks the latch before every step the remote keeps: GitHub cannot
show it a close and a reopen that both happened inside one of its own steps,
and the latch can.

The steps here are the ADJUDICATION's: the spawn an oversized candidate pays
for, and the publication an accepted one earns. What the same latch does
between the steps that make a CHILD is `test_late_child_close`, and what a
process inheriting such a reading from a DEAD one does with it is
`test_late_inherited_close`, both beside this.

Every case here therefore runs against an issue GitHub reports OPEN. Nothing
the run could ask would stop it; the latch is the only thing that knows.
"""
from __future__ import annotations

import unittest

from orchestrator.workflow.stages.decomposition.late_result_models import _LateDisposition
from tests.workflow.fixtures import _TEST_SPEC
from tests.workflow.observation_support import ObservedCloseCase
from tests.workflow.stages.decomposition.late_observation_seams import (
    ISSUE_COMMENT,
    PR_SEARCH,
    latches_on_call,
    latches_on_retirement,
    latches_on_write,
)
from tests.workflow.stages.decomposition.late_run_support import (
    LateCase,
    agent_reply,
)
from tests.workflow.stages.decomposition.late_settlement_support import (
    settle_single,
)
from tests.workflow.stages.decomposition.late_test_support import (
    CANDIDATE_SHA,
    CYCLE_ID,
    KEYS,
    LATE_ISSUE_NUMBER,
    late_generation,
    seed_late_issue,
)

_WORKFLOW_LOG = "orchestrator.workflow"

REPO_SLUG = _TEST_SPEC.slug

# The one field that says a cycle is still there to end. A `single`
# publication drops the whole generation, and the sweep reads exactly this to
# decide whether anything is owed.
_KEY_CYCLE_ID = "late_cycle_id"

# One attempt bought by a continuation and not yet spent.
_GRANTED = 1


class LatchedCloseStopsTheSpawnTest(
    ObservedCloseCase, LateCase, unittest.TestCase,
):
    """No agent is paid for against an issue a poll already saw closed.

    The issue itself reads OPEN throughout -- a human reopened it -- so
    nothing this tick could ask GitHub would stop the spawn. The latch is the
    only thing that knows.
    """

    def setUp(self) -> None:
        super().setUp()
        self._fresh_process()
        self._latch_close(REPO_SLUG, LATE_ISSUE_NUMBER)

    def test_no_agent_is_spawned(self) -> None:
        with self.assertLogs(_WORKFLOW_LOG):
            outcome, spawn = self._adjudicate()

        spawn.assert_not_called()
        self.assertEqual(outcome.disposition, _LateDisposition.CANCELLED)

    def test_the_cancellation_is_persisted(self) -> None:
        # The barrier does not merely decline the tick: an observed close
        # ends the cycle, and the mark is what every gate below reads and
        # what the ending is entered from.
        with self.assertLogs(_WORKFLOW_LOG):
            self._adjudicate()

        pinned = self._pinned()
        self.assertTrue(pinned[KEYS.cancelled])
        self.assertTrue(pinned[KEYS.cancelled_at])

    def test_no_attempt_is_spent(self) -> None:
        # The gate runs before this barrier, so the slot it charged is in
        # memory when the latch fires -- and the cancellation the latch takes
        # is a write. No agent started, so the issue pays for nothing: the
        # counted attempt and the one a human bought are both handed back.
        self.issue = seed_late_issue(
            self.github, late_generation(), retry_cap_continued=_GRANTED,
        )

        with self.assertLogs(_WORKFLOW_LOG):
            self._adjudicate()

        self.assertEqual(self._pinned().get(KEYS.retry_grant), _GRANTED)
        self.assertNotIn(KEYS.retry_count, self._pinned())

    def test_a_settled_latch_lets_the_run_through(self) -> None:
        # The other side of it, so the barrier is not just "never spawn":
        # a latch a pass has taken is gone, and the tick behaves as it always
        # did.
        self._settle_latches(REPO_SLUG)

        outcome, spawn = self._adjudicate(agent_reply("nothing usable"))

        spawn.assert_called_once()
        self.assertNotEqual(outcome.disposition, _LateDisposition.CANCELLED)


class LatchedInsideTheSpawnRecordTest(
    ObservedCloseCase, LateCase, unittest.TestCase,
):
    """The write that says a run is about to start is itself a request.

    The tick's own gates are behind it, and the latch was asked once already
    -- but a worktree probe, a retry-budget write, and this record all stand
    between that reading and the spawn, and the poll runs beside every one of
    them. So the latch is asked once more, immediately against the step that
    puts an agent on somebody's repository.
    """

    def setUp(self) -> None:
        super().setUp()
        self._fresh_process()

    def test_no_agent_is_spawned(self) -> None:
        with self.assertLogs(_WORKFLOW_LOG), self._closing():
            outcome, spawn = self._adjudicate()

        spawn.assert_not_called()
        self.assertEqual(outcome.disposition, _LateDisposition.CANCELLED)
        self.assertTrue(self._pinned()[KEYS.cancelled])

    def test_no_attempt_is_spent(self) -> None:
        # The record this write carries is durable and the slot behind it is
        # deliberately not, so the latch asked against the spawn has to find
        # the accounting as the issue had it: a cancellation landing here ends
        # a cycle no agent ever ran for.
        self.issue = seed_late_issue(
            self.github, late_generation(), retry_cap_continued=_GRANTED,
        )

        with self.assertLogs(_WORKFLOW_LOG), self._closing():
            self._adjudicate()

        self.assertEqual(self._pinned().get(KEYS.retry_grant), _GRANTED)
        self.assertNotIn(KEYS.retry_count, self._pinned())

    def _closing(self):
        """Latch the close inside the write that records this attempt."""
        return latches_on_write(
            self.github, REPO_SLUG, LATE_ISSUE_NUMBER, KEYS.run_cycle_id,
        )


class _SettledSingleCase(ObservedCloseCase, LateCase):
    """One owner whose candidate is settled through to the retirement."""

    def setUp(self) -> None:
        super().setUp()
        self._fresh_process()

    def _settled(self):
        """Take the settlement road the decision on this candidate licenses."""
        return settle_single(self.github, self.issue)


class LatchedInsideSettlementTest(_SettledSingleCase, unittest.TestCase):
    """A settlement may not erase the cycle a close just ended.

    Publishing an accepted candidate drops the generation entirely -- the
    identity, the measurement, the verdict, all of it -- and the sweep that
    should end a cancelled cycle reads that generation to decide there is
    anything to end. So a close latched during the hold release or the
    pull-request lookup has to stop the publication, or the ending would have
    nothing left to run from.
    """

    def setUp(self) -> None:
        super().setUp()
        self._fresh_process()

    def test_the_cycle_is_marked_rather_than_dropped(self) -> None:
        with self.assertLogs(_WORKFLOW_LOG), self._closing():
            outcome = self._settled()

        pinned = self._pinned()
        self.assertEqual(outcome.disposition, _LateDisposition.CANCELLED)
        self.assertTrue(pinned[KEYS.cancelled])
        self.assertEqual(pinned[_KEY_CYCLE_ID], CYCLE_ID)

    def test_the_candidate_is_not_handed_on(self) -> None:
        # `implementing` is what makes another stage read the candidate as
        # publishable, and an issue somebody closed is not one to publish.
        with self.assertLogs(_WORKFLOW_LOG), self._closing():
            self._settled()

        self.assertEqual(self.github.label_history, [])

    def test_a_close_at_the_exemption_stops_it(self) -> None:
        # The step after the barrier above is itself a request, so the same
        # question is asked again behind it -- and again behind the handoff
        # label. A close that got through either would erase the generation a
        # receipt adopted from the thread has to be adopted AGAINST.
        with self.assertLogs(_WORKFLOW_LOG), self._closing_on_exemption():
            outcome = self._settled()

        pinned = self._pinned()
        self.assertEqual(outcome.disposition, _LateDisposition.CANCELLED)
        self.assertTrue(pinned[KEYS.cancelled])
        self.assertEqual(pinned[_KEY_CYCLE_ID], CYCLE_ID)
        self.assertEqual(self.github.label_history, [])

    def _closing(self):
        """Latch the close inside the pull-request search this run makes.

        Inside the settlement rather than ahead of it, because what this pins
        is the barrier the SETTLEMENT takes: a latch already standing when the
        adjudication finished is caught by the owner read in front of it.
        """
        return latches_on_call(
            self.github, REPO_SLUG, LATE_ISSUE_NUMBER, PR_SEARCH,
        )

    def _closing_on_exemption(self):
        """Latch the close inside the write that records the exemption."""
        return latches_on_write(
            self.github, REPO_SLUG, LATE_ISSUE_NUMBER, KEYS.exempt_sha,
        )


class LatchedInsideThePublicationTest(_SettledSingleCase, unittest.TestCase):
    """The last two windows a settlement has, and the one with no refusal left.

    The publication says what was decided and then retires the cycle that
    decided it. Both are requests; only the first can still be refused. Past
    the second the record has no cycle identity at all, and neither the sweep
    nor a receipt adopted from the thread has anything to end -- so the answer
    there is a reinstatement, from the generation still in this call's memory.
    """

    def test_a_close_at_the_notice_stops_it(self) -> None:
        with self.assertLogs(_WORKFLOW_LOG), self._closing(ISSUE_COMMENT):
            outcome = self._settled()

        pinned = self._pinned()
        self.assertEqual(outcome.disposition, _LateDisposition.CANCELLED)
        self.assertTrue(pinned[KEYS.cancelled])
        self.assertEqual(pinned[_KEY_CYCLE_ID], CYCLE_ID)

    def test_a_close_at_the_retirement_reinstates_it(self) -> None:
        with self.assertLogs(_WORKFLOW_LOG), self._retiring():
            outcome = self._settled()

        pinned = self._pinned()
        self.assertEqual(outcome.disposition, _LateDisposition.CANCELLED)
        self.assertTrue(pinned[KEYS.cancelled])
        self.assertEqual(pinned[_KEY_CYCLE_ID], CYCLE_ID)
        self.assertEqual(pinned[KEYS.candidate_sha], CANDIDATE_SHA)

    def test_a_close_at_the_window_exit_is_caught(self) -> None:
        # The interval a barrier taken before the exit would step over: the
        # retirement write has landed, the cycle is still advertised, and a
        # poll can still latch a close and receipt it against that cycle.
        with self.assertLogs(_WORKFLOW_LOG), self._retiring(after=True):
            outcome = self._settled()

        pinned = self._pinned()
        self.assertEqual(outcome.disposition, _LateDisposition.CANCELLED)
        self.assertTrue(pinned[KEYS.cancelled])
        self.assertEqual(pinned[_KEY_CYCLE_ID], CYCLE_ID)

    def test_a_run_nobody_latched_still_retires(self) -> None:
        # The baseline every window here is measured against: an accepted
        # candidate publishes and its cycle is dropped, which is the whole
        # point of a `single`.
        outcome = self._settled()

        pinned = self._pinned()
        self.assertEqual(outcome.disposition, _LateDisposition.SETTLED)
        self.assertIsNone(pinned.get(_KEY_CYCLE_ID))
        self.assertIsNone(pinned.get(KEYS.cancelled))

    def _closing(self, seam: str):
        """Latch the close inside one call the publication makes."""
        return latches_on_call(
            self.github, REPO_SLUG, LATE_ISSUE_NUMBER, seam,
        )

    def _retiring(self, *, after: bool = False):
        """Latch the close around the write that drops the cycle."""
        return latches_on_retirement(
            self.github, REPO_SLUG, LATE_ISSUE_NUMBER, after=after,
        )


if __name__ == "__main__":
    unittest.main()
