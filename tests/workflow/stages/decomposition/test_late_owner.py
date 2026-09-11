# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The fresh owner read a finished late run has to pass before it is acted on.

Three answers and three obligations: carry on, cancel the cycle, or record the
read as still owed. It is taken after EVERY completion -- the ones that decided
something and the ones that only parked -- because the run was paid for either
way and a closure during any of them strands the same generation and the same
plan-PR hold. What the park a failed read leaves does next is the module
beside this one.
"""
from __future__ import annotations

import unittest
from dataclasses import replace
from unittest.mock import patch

from orchestrator.workflow.late_split.models import (
    LateFailure,
    LatePhase,
    LateVerdict,
)
from orchestrator.workflow.stages.decomposition import (
    late_owner as _late_owner,
)
from orchestrator.workflow.stages.decomposition.late_models import (
    _LateDisposition,
)
from tests.workflow.fixtures import STAGE_DECOMPOSING
from tests.workflow.stages.decomposition import late_settlement_support as _support
from tests.workflow.stages.decomposition.late_settlement_support import GuardedLateCase, _ClosedDuringRun
from tests.workflow.stages.decomposition.late_test_support import (
    CANDIDATE_SHA,
    EVENT_LATE_FAILURE,
    KEYS,
    QUESTION_ASKED,
    generation_state,
    late_generation,
)

COMMENT = "comment"


def _park_reason(pinned) -> object:
    """What this pinned comment says the issue is being held for."""
    return pinned.get(KEYS.park_reason)


class OwnerReadTest(GuardedLateCase, unittest.TestCase):
    """What each of the three answers costs a completed adjudication."""

    def test_an_open_owner_lets_the_verdict_through(self) -> None:
        outcome = self._decide()

        self.assertEqual(outcome.disposition, _LateDisposition.DECIDED)
        self.assertEqual(self._pinned().get(KEYS.phase), LatePhase.OWNER_CHECK)
        self.assertEqual(self._events_named(_support.EVENT_LATE_CANCELLATION), [])
        self.assertFalse(self._pinned().get(KEYS.awaiting))

    def test_a_closed_owner_cancels_the_cycle(self) -> None:
        # The verdict is real and the run was paid for; what changed is that
        # nobody wants the issue any more, so the mark the cleanup path reads
        # goes down instead of the children going up.
        outcome = self._decide(_ClosedDuringRun(self.issue, _support.SPLIT_RUN))

        self.assertEqual(outcome.disposition, _LateDisposition.CANCELLED)
        self.assertIsNone(outcome.guarded_split)
        pinned = self._pinned()
        self.assertTrue(pinned.get(KEYS.cancelled))
        self.assertTrue(pinned.get(KEYS.cancelled_at))
        self.assertEqual(pinned.get(KEYS.phase), LatePhase.CANCELLING)
        self.assertEqual(self.github.created_child_issues, [])
        self.assertEqual(self.github.label_history, [])

    def test_a_cancellation_reaches_both_sinks(self) -> None:
        self._decide(_ClosedDuringRun(self.issue, _support.SPLIT_RUN))

        recorded = self._events_named(_support.EVENT_LATE_CANCELLATION)
        self.assertEqual(len(recorded), 1)
        self.assertEqual(recorded[0].get("stage"), STAGE_DECOMPOSING)
        self.assertEqual(recorded[0].get("source_sha"), CANDIDATE_SHA)

    def test_a_reopened_owner_resumes_nothing(self) -> None:
        # Irreversible within the cycle: the cancellation is what the cleanup
        # settles from, so an issue somebody reopened starts over rather than
        # picking the same adjudication back up.
        self._decide(_ClosedDuringRun(self.issue, _support.SPLIT_RUN))
        stamped = self._pinned().get(KEYS.cancelled_at)
        self.issue.closed = False

        outcome, spawn = self._adjudicate(_support.SPLIT_RUN)

        self.assertEqual(outcome.disposition, _LateDisposition.NOT_LATE)
        spawn.assert_not_called()
        self.assertEqual(self._pinned().get(KEYS.cancelled_at), stamped)

    def test_an_unreadable_owner_keeps_the_result(self) -> None:
        outcome = self._decide_unread()

        self.assertEqual(outcome.disposition, _LateDisposition.PARKED)
        pinned = self._pinned()
        self.assertTrue(pinned.get(KEYS.awaiting))
        self.assertEqual(_park_reason(pinned), _support.PARK_OWNER_UNREADABLE)
        # The run is not what failed, so its answer stays recorded and the
        # retry has nothing to re-earn.
        self.assertEqual(pinned.get(KEYS.verdict), LateVerdict.SPLIT)
        self.assertEqual(self.github.label_history, [])

    def test_a_state_naming_nothing_fails_closed(self) -> None:
        # A read that established nothing is not the same claim as "open", and
        # defaulting it either way would publish on the strength of it.
        with _support.stateless_owner(self.github), self.assertLogs(_support.WORKFLOW_LOG, level=_support.ERROR):
            outcome = self._decide()

        self.assertEqual(outcome.disposition, _LateDisposition.PARKED)
        self.assertEqual(
            _park_reason(self._pinned()), _support.PARK_OWNER_UNREADABLE,
        )

    def test_the_read_failure_is_recorded(self) -> None:
        self._decide_unread()

        recorded = self._events_named(EVENT_LATE_FAILURE)
        self.assertEqual(len(recorded), 1)
        self.assertEqual(
            recorded[0].get("failure"), LateFailure.OWNER_READ_FAILED,
        )
        self.assertEqual(recorded[0].get("stage"), STAGE_DECOMPOSING)


class InterruptedBoundaryTest(GuardedLateCase, unittest.TestCase):
    """A close caught mid-transaction keeps the boundary it interrupted.

    The whole tick is driven, because the hazard is not one write: a split
    that crashed mid-loop comes back through the WHOLE coordinator, and every
    step above the transaction names a boundary of its own -- the plan-PR
    hold reconciled before anything spawns, and the claim each completion
    writes on its way into the owner read. Any of them landing on the record
    would leave a cancellation observed here keeping a boundary that says no
    split ever started, and the reclamation would then read an empty ledger
    as the whole account and delete the ref out from under the child that
    loop had already created.
    """

    def test_a_close_mid_split_keeps_that_boundary(self) -> None:
        for phase in (LatePhase.SNAPSHOTTING, LatePhase.SPLITTING):
            with self.subTest(phase=phase):
                self._crashed_at(phase)

                self._decide(_ClosedDuringRun(self.issue, _support.SPLIT_RUN))

                pinned = self._pinned()
                self.assertTrue(pinned.get(KEYS.cancelled))
                self.assertEqual(pinned.get(KEYS.cancelled_phase), phase)

    def test_an_ordinary_close_still_names_the_read(self) -> None:
        # The other side of it: a cycle that never started a transaction is
        # cancelled at the boundary a completion really did reach.
        self._decide(_ClosedDuringRun(self.issue, _support.SPLIT_RUN))

        self.assertEqual(
            self._pinned().get(KEYS.cancelled_phase), LatePhase.OWNER_CHECK,
        )

    def test_a_kept_boundary_is_a_standing_claim(self) -> None:
        # What the guard reads the claim back as. A boundary it deliberately
        # did not rewind is as standing a claim as `owner_check` -- otherwise
        # every re-entered transaction would pay for a second write of the
        # claim it already made.
        kept = late_generation(
            phase=LatePhase.SPLITTING, owner_check_pending=True,
        )

        self.assertTrue(_late_owner._already_claimed(kept))
        self.assertFalse(
            _late_owner._already_claimed(replace(kept, phase=None)),
        )

    def _crashed_at(self, phase: LatePhase) -> None:
        """Re-seed this issue as a transaction that died at one boundary."""
        self.github.seed_state(
            self.issue.number, **generation_state(late_generation(phase=phase)),
        )


class UndecidedCompletionTest(GuardedLateCase, unittest.TestCase):
    """A run that decided nothing was still paid for, so it is guarded too."""

    def test_a_closed_owner_cancels_a_question(self) -> None:
        # Nothing is asked of a human who has closed the issue: the question
        # is recorded but never announced, and the cycle ends instead.
        outcome = self._decide(_ClosedDuringRun(self.issue, _support.QUESTION_RUN))

        self.assertEqual(outcome.disposition, _LateDisposition.CANCELLED)
        pinned = self._pinned()
        self.assertTrue(pinned.get(KEYS.cancelled))
        self.assertEqual(pinned.get(KEYS.verdict), LateVerdict.QUESTION)
        self.assertNotIn(QUESTION_ASKED, self._said())

    def test_an_unreadable_owner_holds_a_question(self) -> None:
        # Recorded, not announced: what the guard stands in front of includes
        # saying something to a thread it cannot prove is still there.
        outcome = self._decide_unread(_support.QUESTION_RUN)

        self.assertEqual(outcome.disposition, _LateDisposition.PARKED)
        pinned = self._pinned()
        self.assertEqual(pinned.get(KEYS.verdict), LateVerdict.QUESTION)
        self.assertEqual(_park_reason(pinned), _support.PARK_OWNER_UNREADABLE)
        self.assertNotIn(QUESTION_ASKED, self._said())

    def test_the_held_question_is_asked_once_it_heals(self) -> None:
        self._decide_unread(_support.QUESTION_RUN)

        outcome, spawn = self._adjudicate()

        spawn.assert_not_called()
        self.assertEqual(outcome.disposition, _LateDisposition.DECIDED)
        self.assertIn(QUESTION_ASKED, self._said())
        self.assertEqual(_park_reason(self._pinned()), _support.PARK_QUESTION)

    def _said(self) -> str:
        """Everything this tick posted on the issue, as one blob."""
        return "".join(
            body for _number, body in self.github.posted_comments
        )


class UnannouncedCompletionTest(GuardedLateCase, unittest.TestCase):
    """A completion nobody can be told about is recorded and stays quiet.

    Each case below finished a run and then parked. The park is what has to
    be durable; the sentence explaining it is what waits for a read that
    proves the issue is still there.
    """

    def test_a_closed_owner_says_nothing(self) -> None:
        # The park is durable, the cycle ends, and nobody is told about a run
        # on an issue they have closed.
        for completion in _support.PARKING_COMPLETIONS:
            with self.subTest(completion=completion[_support.NAME]):
                self.setUp()

                outcome = self._closed_during(completion)

                self.assertEqual(
                    outcome.disposition, _LateDisposition.CANCELLED,
                )
                self.assertTrue(self._pinned().get(KEYS.cancelled))
                self.assertEqual(
                    _park_reason(self._pinned()), completion[_support.REASON],
                )
                self.assertEqual(self.github.posted_comments, [])

    def test_an_unreadable_owner_says_nothing(self) -> None:
        # Nor does one this tick could not read. The park is recorded, the
        # read is left owed, and the notice waits for whatever re-takes the
        # park once the read heals -- which says the reason it fails for THEN.
        for completion in _support.PARKING_COMPLETIONS:
            with self.subTest(completion=completion[_support.NAME]):
                self.setUp()

                outcome = self._unread_during(completion)

                self.assertEqual(outcome.disposition, _LateDisposition.PARKED)
                self.assertEqual(
                    _park_reason(self._pinned()), completion[_support.REASON],
                )
                self.assertTrue(
                    self._pinned().get(KEYS.owner_check_pending),
                )
                self.assertEqual(self.github.posted_comments, [])

    def test_a_standing_park_is_not_replaced(self) -> None:
        # An issue already handed back to a human is stopped either way, and
        # swapping the reason for one they cannot answer would cost them the
        # thing they were actually asked. The pending marker is what brings
        # the next tick back to the read.
        outcome = self._decide_unread(_support.TIMEOUT_RUN)

        self.assertEqual(outcome.disposition, _LateDisposition.PARKED)
        self.assertEqual(_park_reason(self._pinned()), _support.PARK_TIMEOUT)
        self.assertTrue(self._pinned().get(KEYS.owner_check_pending))
        self.assertEqual(len(self._events_named(EVENT_LATE_FAILURE)), 1)

    def test_a_refused_notice_keeps_the_park(self) -> None:
        # The park is durable before the sentence is attempted, so a comment
        # GitHub refuses costs the notice and never the finished run: the
        # reason stands and the next tick reconciles from it.
        refused = patch.object(self.github, COMMENT, side_effect=RuntimeError)

        with refused, self.assertRaises(RuntimeError):
            self._decide(_support.TIMEOUT_RUN)

        self.assertTrue(self._pinned().get(KEYS.awaiting))
        self.assertEqual(_park_reason(self._pinned()), _support.PARK_TIMEOUT)

    def _closed_during(self, completion):
        """One completion whose issue a human closes while it runs."""
        outcome, _spawn = self._adjudicate(
            _ClosedDuringRun(self.issue, completion[_support.RUN]),
            worktree=completion[_support.TREE],
        )
        return outcome

    def _unread_during(self, completion):
        """One completion whose owner read fails, log line included."""
        with _support.unreadable_owner(self.github), self.assertLogs(_support.WORKFLOW_LOG, level=_support.ERROR):
            outcome, _spawn = self._adjudicate(
                completion[_support.RUN], worktree=completion[_support.TREE],
            )
        return outcome


if __name__ == "__main__":
    unittest.main()
