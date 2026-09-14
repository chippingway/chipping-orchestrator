# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What a human's reply to a measurement park buys, and what it may not.

A bare `/orchestrator continue` buys a second reading of the EXACT pair that
was recorded and nothing else -- no agent, and no substitute for a commit the
record names. Guidance buys the opposite: the developer is resumed, and what
it leaves is judged against the floor the park left on the branch rather than
against the base, so a clarifying question is not answered by publishing the
work it was asked about.

Some readings never reach a human at all. A base this host could not get to is
the transport rather than the work, so a bounded number of them in a row are
counted on the record and nothing else is done: no park, no mention, and a
pair the next tick re-reads by itself.
"""

from __future__ import annotations

import unittest
from unittest.mock import patch

from orchestrator.config import settings as config
from orchestrator.git.measurement.models import FrozenCommit, MeasurementFailure
from tests.workflow.fixtures import (
    MEASURED_CANDIDATE_SHA,
    _agent,
)
from tests.workflow.stages.implementing import (
    late_gate_test_support as support,
    late_retry_payloads as _retry_payloads,
)


class LateGateTimeoutRecoveryTest(support._GateCase, unittest.TestCase):
    """A commit recovered from a timeout is the same kind of candidate."""

    def test_a_recovered_commit_is_measured(self) -> None:
        # The recovery publishes without a human and without an agent, which
        # is exactly why it may not publish around the gate: an oversized
        # candidate would reach a branch and a pull request on the strength of
        # a run nobody read.
        self._seed(**{
            support.AWAITING_HUMAN: True,
            support.PARK_REASON: _retry_payloads._AGENT_TIMEOUT,
            _retry_payloads._PRE_IMPLEMENT_SHA: _retry_payloads._PRE_TIMEOUT_SHA,
        })

        mocks = self._run_gate(
                head_shas=(_retry_payloads._POST_TIMEOUT_SHA,),
                added_lines=support.OVERSIZED_ADDITIONS,
            )

        self._assert_no_agent(mocks)
        self._assert_measured(mocks)
        self._assert_held(mocks)
        self.assertIn(_retry_payloads._DECOMPOSING, self.github.label_history)


class LateGateStrandedPairTest(support._GateCase, unittest.TestCase):
    """A frozen pair with no park beside it, on a host that cannot show it.

    The crash window the persist-before-count ordering opens: the pair went
    down durably and the tick died before it was counted or parked, so nothing
    on the issue says the workflow is waiting for anything. On the host that
    froze it the next tick simply measures again; on a rebuilt one the
    checkout comes back at base and the ordinary flow would pay for a second
    developer over work the first one already finished.
    """

    def setUp(self) -> None:
        super().setUp()
        self._seed(**support.recorded_generation())

    def test_a_reaped_worktree_parks_before_spawning(self) -> None:
        mocks = self._run_gate(
            worktree=_retry_payloads._REAPED_WORKTREE, has_new_commits=False,
        )

        self._assert_no_agent(mocks)
        self._assert_unmeasured(mocks)
        self._assert_held(mocks)
        self._assert_parked()

    def test_an_absent_object_parks_before_spawning(self) -> None:
        # The checkout is there and the commit is not: a rebuilt host, or one
        # the branch never reached. A fresh run would produce different work,
        # so what the park asks for is the worktree rather than another agent.
        mocks = self._run_gate(
            recorded_commit=FrozenCommit(
                failure=MeasurementFailure.CANDIDATE_ABSENT,
            ),
            has_new_commits=False,
        )

        self._assert_no_agent(mocks)
        self._assert_held(mocks)
        self._assert_parked()

    def test_the_record_survives_for_the_retry(self) -> None:
        self._run_gate(worktree=_retry_payloads._REAPED_WORKTREE, has_new_commits=False)

        self._assert_frozen()

    def test_a_base_free_branch_still_reconciles(self) -> None:
        # The reading that would otherwise send this issue to a second
        # developer: "is there work to publish" is answered downstream by
        # asking whether the branch is ahead of the CURRENT base, and a base
        # that has since absorbed the candidate -- or a probe that could not
        # answer -- reads as a branch carrying nothing. The record names the
        # pair outright, so no heuristic is consulted at all.
        mocks = self._run_gate(
            has_new_commits=False, added_lines=support.SMALL_ADDITIONS,
        )

        self._assert_no_agent(mocks)
        self._assert_measured(mocks)
        self._assert_published(mocks)

    def test_a_lost_reading_re_enters_by_itself(self) -> None:
        # What a reading the transport lost leaves: a count on the record and
        # nothing anywhere saying a human is owed a reply. So the next tick is
        # this same reconciliation -- the recorded pair, no remote read, no
        # agent -- and the reading that lands is what ends the run of misses
        # on the record it is settled under.
        self._seed(**support.recorded_generation(
            measurement_miss_count=_retry_payloads._MISS_BOUND - 1,
        ))

        mocks = self._run_gate(
            has_new_commits=False, added_lines=support.OVERSIZED_ADDITIONS,
        )

        self._assert_no_agent(mocks)
        mocks[support.FREEZE_BASE_COMMIT].assert_not_called()
        self._assert_measured(mocks)
        self.assertIn(_retry_payloads._DECOMPOSING, self.github.label_history)
        pinned = self._pinned()
        self.assertEqual(pinned[support.KEY_CANDIDATE_SHA], MEASURED_CANDIDATE_SHA)
        self.assertNotIn(support.KEY_MISS_COUNT, pinned)
        self.assertNotIn(support.KEY_MEASUREMENT_FAILURE, pinned)

    def test_a_missing_recorded_base_stops_the_tick(self) -> None:
        # The other end of the pair, proved for the same reason: a host that
        # cannot show the object the count is taken against can neither
        # measure it nor defend a verdict over it. A fetch that brought
        # nothing back is the transport, so what the tick costs is one of the
        # readings this pair may lose and no second developer either way.
        mocks = self._run_gate(
            has_new_commits=False, base_object_present=False,
        )

        self._assert_no_agent(mocks)
        self._assert_unmeasured(mocks)
        self._assert_held(mocks)
        self._assert_missed()


class LateGateMovedPairTest(support._GateCase, unittest.TestCase):
    """A frozen pair whose checkout is no longer on the recorded commit.

    No developer ran on this path, so a head somewhere else is not fresh
    output: it is a checkout somebody moved, and measuring it would answer the
    size question about a commit nobody froze.
    """

    def setUp(self) -> None:
        super().setUp()
        self._seed(**support.recorded_generation())

    def test_a_moved_checkout_parks(self) -> None:
        # No developer ran on this path -- the run whose work this is finished
        # before the crash -- so a head somewhere else is not fresh output to
        # be measured in the recorded candidate's place. It is a checkout
        # somebody moved, and measuring it would answer the size question
        # about a commit nobody froze while the record naming the real one was
        # discarded.
        mocks = self._run_gate(
            has_new_commits=False,
            candidate_commit=_retry_payloads._MOVED_HEAD,
        )

        self._assert_no_agent(mocks)
        self._assert_unmeasured(mocks)
        self._assert_held(mocks)
        self._assert_parked()
        self._assert_frozen()

    def test_a_moved_checkout_parks_switched_off(self) -> None:
        # The switch decides whether NEW work is measured. Nothing here is
        # new: it is a reading a crashed tick recorded, and publishing the
        # head in its place is the switch failing open.
        with patch.object(config, _retry_payloads._DECOMPOSE, False):
            mocks = self._run_gate(
                has_new_commits=False,
                candidate_commit=_retry_payloads._MOVED_HEAD,
            )

        self._assert_no_agent(mocks)
        self._assert_held(mocks)
        self._assert_parked()
        self._assert_frozen()

    def test_a_head_that_moves_mid_tick_parks(self) -> None:
        # The head is proved against the record before this reconciliation
        # starts and read again inside the gate a moment later, and the
        # checkout is writable in between. No run of this tick produced
        # whatever it moved to -- so reading it as fresh work would measure
        # and publish it with the switch on, and push it unmeasured with the
        # switch off, both about a commit this reconciliation was never about.
        for decomposing in (True, False):
            with self.subTest(decompose=decomposing):
                self.setUp()

                with patch.object(config, _retry_payloads._DECOMPOSE, decomposing):
                    mocks = self._run_gate(
                        has_new_commits=False, candidate_commit=_retry_payloads._HEAD_MOVES,
                    )

                self._assert_no_agent(mocks)
                self._assert_unmeasured(mocks)
                self._assert_held(mocks)
                self._assert_parked()
                self._assert_frozen()

    def test_a_move_onto_an_absent_object_parks(self) -> None:
        # The same race with a head that NAMES a commit this host cannot peel.
        # A named one handed back from the reconciliation is one the park
        # downstream records -- minting a generation around it and dropping
        # the pair this retry exists to re-read -- so the refusal has to come
        # before the readability question rather than after it.
        for decomposing in (True, False):
            with self.subTest(decompose=decomposing):
                self.setUp()

                with patch.object(config, _retry_payloads._DECOMPOSE, decomposing):
                    mocks = self._run_gate(
                        has_new_commits=False,
                        candidate_commit=_retry_payloads._HEAD_MOVES_TO_ABSENT,
                    )

                self._assert_no_agent(mocks)
                self._assert_unmeasured(mocks)
                self._assert_held(mocks)
                self._assert_parked()
                self._assert_frozen()

    def test_the_switch_off_still_reconciles_the_pair(self) -> None:
        # And where the checkout IS on the recorded commit, the reading the
        # crashed tick recorded is taken with the switch either way: the
        # candidate was in the gate before the switch was touched.
        with patch.object(config, _retry_payloads._DECOMPOSE, False):
            mocks = self._run_gate(
                has_new_commits=False, added_lines=support.SMALL_ADDITIONS,
            )

        self._assert_no_agent(mocks)
        self._assert_measured(mocks)
        self._assert_published(mocks)

    def test_the_host_that_froze_it_measures_again(self) -> None:
        # The ordinary recovery, and the reason the probe is a proof rather
        # than a refusal: where the commits really are there, the tick picks
        # them up and the gate reads the same pair a second time.
        mocks = self._run_gate(added_lines=support.SMALL_ADDITIONS)

        self._assert_no_agent(mocks)
        self._assert_measured(mocks)
        self._assert_published(mocks)


class LateGateMissBoundTest(support._ParkedRetryCase, unittest.TestCase):
    """How many readings one pair may lose to the transport, and to whom.

    The bound the quiet retry is held to, and the order the record and the
    notice about it go out in: a miss nothing wrote down is one the fresh
    process behind this tick cannot count, so the pinned comment carries it
    before either sink or a human hears about it.
    """

    def test_the_bound_is_what_ends_the_quiet_retry(self) -> None:
        # Three readings this pair may lose in a row, and the fourth is a
        # transport that is not coming back on its own: committed work is
        # waiting behind a reading that will not happen, so it is handed over
        # with one mention rather than re-read every poll forever.
        for lost, parks in _retry_payloads._BOUNDED_MISSES:
            with self.subTest(lost=lost):
                self.setUp()
                self._park_after_misses(lost)

                mocks = self._run_gate(base_object_present=False)

                self._assert_no_agent(mocks)
                self._assert_held(mocks)
                if not parks:
                    self._assert_missed(count=lost + 1)
                    continue
                self._assert_parked()
                # The step the mention NAMED goes on the record with the
                # count, and only here: what the guard past this park asks is
                # whether the sentence already on the thread covers the step a
                # later reading stopped at.
                self._assert_announced(MeasurementFailure.BASE_ABSENT)

    def test_the_count_precedes_the_report(self) -> None:
        # Every tick is a fresh process, so a miss reported before it is
        # recorded is one a crash in that window loses -- and a retry that
        # cannot remember what it has lost is not bounded at all. Read off
        # what the pinned comment said when the sinks were handed the failure.
        self._park(support.BARE_CONTINUE)
        reported = support._RecordAtHandoff(self.github, support.EMIT_EVENT)

        with reported.held():
            self._run_gate(base_object_present=False)

        self.assertEqual(reported.pinned[support.KEY_MISS_COUNT], 1)

    def test_the_park_is_taken_over_a_written_record(self) -> None:
        # The same order where the bound runs out: the mention a human reads
        # names a pair whose count is already on the comment, so a crash
        # between the two leaves an issue that has said nothing rather than
        # one whose next reading starts the bound again.
        self._park_after_misses(_retry_payloads._MISS_BOUND)
        mentioned = support._RecordAtHandoff(self.github, support.POST_COMMENT)

        with mentioned.held():
            self._run_gate(base_object_present=False)

        self.assertEqual(
            mentioned.pinned[support.KEY_MISS_COUNT],
            _retry_payloads._MISS_BOUND + 1,
        )
        # And the step that mention names is durable with it, for the reason
        # the count is: announced and not written down, it is announced again
        # by the next poll, once a poll, for as long as the transport stays
        # where it is.
        self.assertEqual(
            mentioned.pinned[support.KEY_MEASUREMENT_FAILURE],
            MeasurementFailure.BASE_ABSENT,
        )

    def test_a_base_never_named_keeps_counting(self) -> None:
        # A base the remote would not answer for records no base at all, so
        # the pair is frozen afresh next tick -- same commit, new generation.
        # The misses travel with the CANDIDATE for exactly that reason: reset
        # with the generation counter beside it, this pair would go on losing
        # readings quietly forever and never reach the bound.
        self._park_state(
            support.BARE_CONTINUE,
            **support.recorded_generation(
                base_sha="", measurement_miss_count=1,
            ),
        )

        mocks = self._run_gate(frozen_base=FrozenCommit(
            failure=MeasurementFailure.BASE_UNREADABLE,
        ))

        self._assert_unmeasured(mocks)
        self._assert_missed(count=2)
        self.assertEqual(self._pinned()[support.KEY_GENERATION], 2)

    def test_a_base_this_host_reaches_ends_the_run(self) -> None:
        # The count is readings lost IN A ROW, so one that was taken ends the
        # row -- durably, since the tick after it is the one a stale count
        # would hand to a human early. The count and only it: the member
        # beside it says what the thread was TOLD, which a base coming back
        # does not unsay, and it moves when a notice naming another step takes
        # its place. Proved on a road that reaches the base and then fails for
        # a reason of its own, which is exactly that.
        self._park_after_misses(
            _retry_payloads._MISS_BOUND + 1, announced=MeasurementFailure.BASE_ABSENT,
        )

        mocks = self._run_gate(added_lines=MeasurementFailure.DIFF_FAILED)

        self._assert_measured(mocks)
        self._assert_parked()
        self.assertNotIn(support.KEY_MISS_COUNT, self._pinned())
        # And what the record names afterwards is the step THIS tick told the
        # human about, rather than the transport failure they were told about
        # before the base came back.
        self._assert_announced(MeasurementFailure.DIFF_FAILED)

    def test_a_fresh_candidate_starts_its_own(self) -> None:
        # Guidance is the opposite reply to a bare continue: the developer is
        # resumed, and what it commits is a candidate this park was never
        # about. Read as the parked pair's, the miss over that new commit
        # would be dropped on the floor -- nothing persisted, nothing
        # reported, and the record still naming work the branch has moved past
        # for the next tick to reconcile against.
        self._park_state(_retry_payloads._GUIDANCE, **support.recorded_generation(
            measurement_miss_count=_retry_payloads._MISS_BOUND,
            measurement_failure=MeasurementFailure.BASE_ABSENT,
        ))

        mocks = self._run_gate(
            run_agent=_agent(
                session_id=support.DEV_SESSION, last_message=_retry_payloads._FINISHED,
            ),
            head_shas=(MEASURED_CANDIDATE_SHA, _retry_payloads._MOVED_SHA),
            candidate_commit=_retry_payloads._MOVED_HEAD,
            frozen_base=FrozenCommit(
                failure=MeasurementFailure.BASE_UNREADABLE,
            ),
        )

        self._assert_resumed(mocks)
        self._assert_held(mocks)
        self._assert_missed()
        self.assertEqual(self._pinned()[support.KEY_CANDIDATE_SHA], _retry_payloads._MOVED_SHA)
        self.assertEqual(
            len(self._records(support.EVENT_LATE_FAILURE)), 1,
        )


class LateGateReapedWorktreeTest(support._ParkedRetryCase, unittest.TestCase):
    """A checkout that is gone is answered here, not by the generic refusal."""

    def test_an_absent_worktree_parks_on_the_evidence(self) -> None:
        # The command was the right one and it is answered here, not handed to
        # the generic classifier -- which would refuse it as carrying no
        # guidance, telling the operator to answer a question nobody asked and
        # consuming their reply against it. What it may not do is re-run the
        # developer: the recorded commit is the evidence, and a fresh checkout
        # is not it.
        self._park(support.BARE_CONTINUE)

        mocks = self._run_gate(worktree=_retry_payloads._REAPED_WORKTREE)

        self._assert_no_agent(mocks)
        self._assert_unmeasured(mocks)
        self._assert_held(mocks)
        self._assert_parked()
        posted = [body for _, body in self.github.posted_comments]
        self.assertIn("not on this host", posted[-1])
        self.assertFalse(any(_retry_payloads._NEEDS_GUIDANCE in body for body in posted))

    def test_an_absent_worktree_keeps_the_record(self) -> None:
        # And the retry it promises has something to come back to: the pair is
        # left exactly as it was, and the failure is reported like any other.
        self._park(support.BARE_CONTINUE)

        self._run_gate(worktree=_retry_payloads._REAPED_WORKTREE)

        self._assert_frozen()
        failures = self._records(support.EVENT_LATE_FAILURE)
        self.assertEqual(len(failures), 1)
        self.assertEqual(failures[0]["failure"], "measurement_failed")
        # And which step it stopped at, which is what tells this refusal from
        # a base a fetch could not bring on the very same pair.
        self.assertEqual(failures[0]["measurement_failure"], _retry_payloads._CHECKOUT_GONE)


if __name__ == "__main__":
    unittest.main()
