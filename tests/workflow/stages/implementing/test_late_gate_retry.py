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
from orchestrator.workflow.stages.implementing import (
    continue_command as _continue_command,
    late_parks as _late_parks,
    state as _implementing_state,
)
from tests.workflow.fixtures import (
    LABEL_DECOMPOSING,
    MEASURED_CANDIDATE_SHA,
    SHA_LENGTH,
    _agent,
)
from tests.workflow.interleaving import _RacesPastTheStep
from tests.workflow.stages.implementing import late_gate_test_support as support

_ANSWERS_THE_PARK = "_answers_the_measurement_park"
_PARKED_CONTINUE_DECISION = "_parked_continue_decision"

_MOVED_SHA = "e" * SHA_LENGTH
# What a checkout somebody moved reads as, and the two successive readings of
# one that moves mid-tick: the recorded commit when a reconciliation proves it
# before starting, and something else by the time the gate reads it again.
# Nothing of this tick's put it there.
_MOVED_HEAD = FrozenCommit(sha=_MOVED_SHA)
_HEAD_MOVES = (FrozenCommit(sha=MEASURED_CANDIDATE_SHA), _MOVED_HEAD)
# The same move onto a commit this host names and cannot peel: an object a
# prune took, or work made somewhere else. It carries an id, which is what
# makes it the sharpest of these -- a name is exactly what a park records.
_HEAD_MOVES_TO_ABSENT = (
    FrozenCommit(sha=MEASURED_CANDIDATE_SHA),
    FrozenCommit(
        sha=_MOVED_SHA, failure=MeasurementFailure.CANDIDATE_ABSENT,
    ),
)

# What a checkout a recordless park comes back to can be standing on, none of
# which anything ties to this issue: the commit the developer left, one a
# rebase or reset moved it to, and one a rebuilt worktree cannot name at all.
_RECORDLESS_CHECKOUTS = (
    ("the head it was left on", None),
    ("a head somebody moved", _MOVED_HEAD),
    ("a head nothing can read", FrozenCommit(
        failure=MeasurementFailure.CANDIDATE_UNREADABLE,
    )),
)

# Each of them under both switch settings, since the switch decides what
# ENTERS the gate and decides nothing about a park already waiting on one.
_RECORDLESS_RETRIES = tuple(
    (checkout, head, decomposing)
    for checkout, head in _RECORDLESS_CHECKOUTS
    for decomposing in (True, False)
)
_REAPED_WORKTREE = support.Path("/nonexistent/orchestrator-reaped-worktree")
# The step a checkout that is gone stops the reading at, which is what the
# record names beside `measurement_failed`: the commit is not on this host.
_CHECKOUT_GONE = MeasurementFailure.CANDIDATE_ABSENT
_DECOMPOSING = (support.GATE_ISSUE_NUMBER, LABEL_DECOMPOSING)
_AGENT_TIMEOUT = "agent_timeout"
_PRE_IMPLEMENT_SHA = "pre_implement_sha"
_PRE_TIMEOUT_SHA = "sha-pre"
_POST_TIMEOUT_SHA = "sha-post"
# The sentence the generic parked-continue classifier posts, which a
# measurement park must never reach.
_NEEDS_GUIDANCE = "needs your actual guidance"
_DECOMPOSE = "DECOMPOSE"
# The reply a human writes to make the developer change the work, and
# what a resumed run says when it has.
_GUIDANCE = "drop the generated fixtures from this"
_FINISHED = "done"
# What a resumed run says when it answered instead of building.
_ASKED = "which half of this did you mean?"

# What a scrubbed transport failure hands up for a human to read, and the two
# things the notice built around it has to say for itself: which invocation
# could not be taken, and where the operator reads what it wrote.
_REMOTE_SAID = "fatal: Authentication failed for 'https://github.com/o/r/'"
_LS_REMOTE = "ls-remote"
_GIT_PLUMBING = "orchestrator.git_plumbing"

# The hidden receipt every comment this workflow posts carries, which is what
# the user-content hash reads a bot comment by once its id has been evicted.
_ORCH_COMMENT_MARKER = "<!--orchestrator-comment-->"

# The steps a second reading cannot change: nothing here can pin the diff,
# git refused it, or what came back was unreadable. Each is a park on the
# first miss, since the retry a transport fault is owed would buy the same
# answer over and over.
_UNRETRIED_STEPS = (
    MeasurementFailure.DIFF_UNPINNABLE,
    MeasurementFailure.DIFF_FAILED,
    MeasurementFailure.DIFF_UNREADABLE,
)

# How many readings one frozen pair may lose to the transport before the gate
# stops taking them again by itself. Read off the owner rather than spelled
# again, so a case names the bound rather than a number beside it.
_MISS_BOUND = _implementing_state._MEASUREMENT_MISSES_BEFORE_PARK

# The readings a pair has already lost, and whether the next one is the one
# that hands the issue over: the bound is on consecutive misses, so the tick
# that takes the last of them is quiet and the one past it is not.
_BOUNDED_MISSES = tuple(
    (lost, lost >= _MISS_BOUND) for lost in range(_MISS_BOUND + 1)
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
            support.PARK_REASON: _AGENT_TIMEOUT,
            _PRE_IMPLEMENT_SHA: _PRE_TIMEOUT_SHA,
        })

        mocks = self._run_gate(
                head_shas=(_POST_TIMEOUT_SHA,),
                added_lines=support.OVERSIZED_ADDITIONS,
            )

        self._assert_no_agent(mocks)
        self._assert_measured(mocks)
        self._assert_held(mocks)
        self.assertIn(_DECOMPOSING, self.github.label_history)


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
            worktree=_REAPED_WORKTREE, has_new_commits=False,
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
        self._run_gate(worktree=_REAPED_WORKTREE, has_new_commits=False)

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
            measurement_miss_count=_MISS_BOUND - 1,
        ))

        mocks = self._run_gate(
            has_new_commits=False, added_lines=support.OVERSIZED_ADDITIONS,
        )

        self._assert_no_agent(mocks)
        mocks[support.FREEZE_BASE_COMMIT].assert_not_called()
        self._assert_measured(mocks)
        self.assertIn(_DECOMPOSING, self.github.label_history)
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
            candidate_commit=_MOVED_HEAD,
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
        with patch.object(config, _DECOMPOSE, False):
            mocks = self._run_gate(
                has_new_commits=False,
                candidate_commit=_MOVED_HEAD,
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

                with patch.object(config, _DECOMPOSE, decomposing):
                    mocks = self._run_gate(
                        has_new_commits=False, candidate_commit=_HEAD_MOVES,
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

                with patch.object(config, _DECOMPOSE, decomposing):
                    mocks = self._run_gate(
                        has_new_commits=False,
                        candidate_commit=_HEAD_MOVES_TO_ABSENT,
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
        with patch.object(config, _DECOMPOSE, False):
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


class LateGateContinueTest(support._ParkedRetryCase, unittest.TestCase):
    """The bare continue a measurement park earns, and what it may not buy."""

    def test_a_bare_continue_remeasures(self) -> None:
        # What failed was a reading, and the developer that produced the commit
        # finished long ago: another run would buy a second answer to a
        # question nobody asked. A reading that lands is the answer, so the
        # park it was taken behind goes with it.
        self._park(support.BARE_CONTINUE)

        mocks = self._run_gate(added_lines=support.SMALL_ADDITIONS)

        self._assert_no_agent(mocks)
        self._assert_measured(mocks)
        self._assert_published(mocks)
        pinned = self._pinned()
        self.assertFalse(pinned.get(support.AWAITING_HUMAN))
        self.assertIsNone(pinned.get(support.PARK_REASON))
        self.assertEqual(
            pinned[support.LAST_ACTION_COMMENT_ID], support.REPLY_COMMENT_ID,
        )

    def test_a_step_no_retry_can_change_parks_at_once(self) -> None:
        # A diff nothing here can pin, one git refused, one nothing could
        # read: a second reading of any of them buys the same answer, so the
        # first is the one worth a human -- and none of them spends one of the
        # readings a transport fault is allowed to lose.
        for failure in _UNRETRIED_STEPS:
            with self.subTest(failure=failure):
                self.setUp()
                self._park(support.BARE_CONTINUE)

                mocks = self._run_gate(added_lines=failure)

                self._assert_no_agent(mocks)
                self._assert_held(mocks)
                self._assert_parked()
                self.assertNotIn(support.KEY_MISS_COUNT, self._pinned())

    def test_a_lost_reading_says_nothing(self) -> None:
        # A fetch that did not bring the base back is the transport rather
        # than the work, and the next tick is very often the whole of the fix:
        # the reading this one lost goes on the record, and nothing else
        # happens at all -- no mention, no reason, and a pair left exactly as
        # the retry behind it finds it.
        self._park(support.BARE_CONTINUE)

        mocks = self._run_gate(base_object_present=False)

        self._assert_no_agent(mocks)
        self._assert_unmeasured(mocks)
        self._assert_held(mocks)
        self._assert_missed()
        self._assert_frozen()

    def test_a_moved_head_refuses_the_bare_retry(self) -> None:
        # No agent ran, so a head somewhere else is not work this workflow
        # produced: the retry reads the exact pair that was recorded, and
        # measuring anything else answers the size question about a commit
        # nobody froze.
        self._park(support.BARE_CONTINUE)

        mocks = self._run_gate(
            candidate_commit=_MOVED_HEAD,
        )

        self._assert_no_agent(mocks)
        self._assert_unmeasured(mocks)
        self._assert_held(mocks)
        self._assert_parked()
        self._assert_frozen()

    def test_a_head_that_moves_mid_retry_parks(self) -> None:
        # The same race one road over: the bare continue proves the head
        # against the record, and the gate reads it again. What the retry
        # buys is a second reading of the EXACT pair, so the pair outlives a
        # head that moved under it rather than being superseded by one.
        for decomposing in (True, False):
            with self.subTest(decompose=decomposing):
                self.setUp()
                self._park(support.BARE_CONTINUE)

                with patch.object(config, _DECOMPOSE, decomposing):
                    mocks = self._run_gate(candidate_commit=_HEAD_MOVES)

                self._assert_no_agent(mocks)
                self._assert_unmeasured(mocks)
                self._assert_held(mocks)
                self._assert_parked()
                self._assert_frozen()

    def test_the_switch_off_refuses_it_too(self) -> None:
        # Publishing it unmeasured is the one thing the switch may not buy: no
        # reading covers that branch, and the record still names another one.
        self._park(support.BARE_CONTINUE)

        with patch.object(config, "DECOMPOSE", False):
            mocks = self._run_gate(
                candidate_commit=_MOVED_HEAD,
            )

        self._assert_no_agent(mocks)
        self._assert_held(mocks)
        self._assert_parked()
        self._assert_frozen()


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
        for lost, parks in _BOUNDED_MISSES:
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
        self._park_after_misses(_MISS_BOUND)
        mentioned = support._RecordAtHandoff(self.github, support.POST_COMMENT)

        with mentioned.held():
            self._run_gate(base_object_present=False)

        self.assertEqual(
            mentioned.pinned[support.KEY_MISS_COUNT],
            _MISS_BOUND + 1,
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
            _MISS_BOUND + 1, announced=MeasurementFailure.BASE_ABSENT,
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
        self._park_state(_GUIDANCE, **support.recorded_generation(
            measurement_miss_count=_MISS_BOUND,
            measurement_failure=MeasurementFailure.BASE_ABSENT,
        ))

        mocks = self._run_gate(
            run_agent=_agent(
                session_id=support.DEV_SESSION, last_message=_FINISHED,
            ),
            head_shas=(MEASURED_CANDIDATE_SHA, _MOVED_SHA),
            candidate_commit=_MOVED_HEAD,
            frozen_base=FrozenCommit(
                failure=MeasurementFailure.BASE_UNREADABLE,
            ),
        )

        self._assert_resumed(mocks)
        self._assert_held(mocks)
        self._assert_missed()
        self.assertEqual(self._pinned()[support.KEY_CANDIDATE_SHA], _MOVED_SHA)
        self.assertEqual(
            len(self._records(support.EVENT_LATE_FAILURE)), 1,
        )


class LateGateNoticeTest(support._ParkedRetryCase, unittest.TestCase):
    """What the mention a spent bound makes carries, and what ends it."""

    def test_the_notice_explains_the_step(self) -> None:
        # What the operator holding this issue is handed: the mentions and the
        # park reason a bare continue is read against, the member every other
        # surface carries -- and, because the member alone is a term this
        # vocabulary owns, the sentence saying which of a remote, a token, or
        # a throttled request they are looking at, with the line the transport
        # itself wrote scrubbed and carried from the freeze that took it.
        self._park_state(
            support.BARE_CONTINUE,
            **support.recorded_generation(
                base_sha="", measurement_miss_count=_MISS_BOUND,
            ),
        )

        self._run_gate(frozen_base=FrozenCommit(
            failure=MeasurementFailure.BASE_UNREADABLE, detail=_REMOTE_SAID,
        ))

        self._assert_parked()
        self._assert_announced(MeasurementFailure.BASE_UNREADABLE)
        notice = self.github.posted_comments[-1][1]
        self.assertIn(_LS_REMOTE, notice)
        self.assertIn(_GIT_PLUMBING, notice)
        self.assertIn(_REMOTE_SAID, notice)
        self.assertIn(_ORCH_COMMENT_MARKER, notice)

    def test_a_reading_that_lands_clears_the_step(self) -> None:
        # A count in hand is the end of every step a reading can stop at, so
        # the member the notice named describes a refusal that is over. The
        # record an oversized candidate leaves is what the adjudication is
        # driven from, and it survives this write: carried into it, the step
        # would describe a refusal nobody is making on an issue whose park
        # this same verdict retired.
        self._park_after_misses(
            _MISS_BOUND + 1, announced=MeasurementFailure.BASE_ABSENT,
        )

        mocks = self._run_gate(added_lines=support.OVERSIZED_ADDITIONS)

        self._assert_measured(mocks)
        self._assert_held(mocks)
        self.assertIn(_DECOMPOSING, self.github.label_history)
        pinned = self._pinned()
        self.assertEqual(
            pinned[support.KEY_ADDITIONS], support.OVERSIZED_ADDITIONS,
        )
        self.assertNotIn(support.KEY_MISS_COUNT, pinned)
        self.assertNotIn(support.KEY_MEASUREMENT_FAILURE, pinned)


class _WritesDuringTheTick:
    """Every durable write one tick made, as the client was handed it.

    A crash window is only visible in the writes themselves: what it leaves is
    a pinned comment some later tick reads as ordinary, so an assertion on the
    state a whole tick ends at cannot see it at all.
    """

    def __init__(self, github) -> None:
        self.writes: list[dict] = []
        self._github = github
        self._wrapped = github.write_pinned_state

    def __call__(self, issue, state):
        self.writes.append(dict(state.data))
        return self._wrapped(issue, state)

    def held(self):
        """Record the pinned writes of one tick."""
        return patch.object(self._github, "write_pinned_state", self)


class LateGateStalePairParkTest(support._ParkedRetryCase, unittest.TestCase):
    """A park and a record may never disagree about which pair they are about.

    The window between the durable write that records a FRESH candidate and
    the verdict that retires the park the last one left. A guided resume
    clears the latch and keeps the reason, so a crash in between would leave a
    park taken over one commit beside a record naming another -- and nothing
    on the comment says which commit a park was taken over, so the next tick
    reads the two as one pair and holds every later reading of it silently:
    none counted, none reported, and the notice a human is owed never reached.
    """

    def test_no_write_leaves_a_park_over_another_pair(self) -> None:
        self._park_state(_GUIDANCE, **support.recorded_generation(
            measurement_miss_count=_MISS_BOUND,
            measurement_failure=MeasurementFailure.BASE_ABSENT,
        ))
        writes = _WritesDuringTheTick(self.github)

        with writes.held():
            self._run_gate(
                run_agent=_agent(
                    session_id=support.DEV_SESSION, last_message=_FINISHED,
                ),
                head_shas=(MEASURED_CANDIDATE_SHA, _MOVED_SHA),
                candidate_commit=_MOVED_HEAD,
                added_lines=support.SMALL_ADDITIONS,
            )

        fresh = [
            written for written in writes.writes
            if written.get(support.KEY_CANDIDATE_SHA) == _MOVED_SHA
        ]
        self.assertTrue(fresh)
        for written in fresh:
            with self.subTest(park=written.get(support.PARK_REASON)):
                self.assertIsNone(written.get(support.PARK_REASON))

    def test_a_spent_park_does_not_silence_the_pair(self) -> None:
        # The reason outlives the latch: a resume consumes the one and leaves
        # the other standing, which is exactly the state seeded here. Read as
        # a notice still owed, every later reading of that pair would be held
        # silently -- a bound that never arrives, on an issue nothing says is
        # parked and no human is behind.
        self._seed(**{
            support.PARK_REASON: support.PARK_MEASUREMENT_FAILED,
            **support.recorded_generation(),
        })

        mocks = self._run_gate(
            has_new_commits=False, base_object_present=False,
        )

        self._assert_no_agent(mocks)
        self._assert_held(mocks)
        self._assert_missed()
        self.assertEqual(len(self._records(support.EVENT_LATE_FAILURE)), 1)


class LateGateGuidanceTest(support._ParkedRetryCase, unittest.TestCase):
    """Guidance resumes the developer, and the floor judges what it left."""

    def test_guidance_reaches_the_developer(self) -> None:
        # A reply with words in it is not a retry of the reading: the human is
        # asking for the work itself to change, which is the ordinary resume.
        self._park(_GUIDANCE)

        mocks = self._run_gate(
            run_agent=_agent(session_id=support.DEV_SESSION, last_message=_FINISHED),
            head_shas=(MEASURED_CANDIDATE_SHA, _MOVED_SHA),
            added_lines=support.SMALL_ADDITIONS,
        )

        self._assert_resumed(mocks)

    def test_a_resumed_question_publishes_nothing(self) -> None:
        # The park left committed work on the branch, so "ahead of base" says
        # nothing about what THIS run did. A developer that answered with a
        # question and committed nothing leaves HEAD on the recorded
        # candidate -- and publishing that would push the very commit whose
        # size nobody could read, over the question it was asked instead.
        self._park("which half of this is generated?")

        mocks = self._run_gate(
            run_agent=_agent(
                session_id=support.DEV_SESSION, last_message="Which fixtures do you mean?",
            ),
            head_shas=(MEASURED_CANDIDATE_SHA, MEASURED_CANDIDATE_SHA),
            added_lines=support.SMALL_ADDITIONS,
        )

        self._assert_resumed(mocks)
        self._assert_unmeasured(mocks)
        self._assert_held(mocks)
        pinned = self._pinned()
        self.assertTrue(pinned[support.AWAITING_HUMAN])
        self.assertIn(
            "Which fixtures do you mean?", self.github.posted_comments[-1][1],
        )

    def test_a_resumed_commit_advances_the_generation(self) -> None:
        # Both commits are here and a developer really did run, so the branch
        # genuinely moved: a fresh candidate under a fresh generation of the
        # same cycle, exactly as a revision under the adjudication label is.
        self._park(_GUIDANCE)

        mocks = self._run_gate(
            run_agent=_agent(
                session_id=support.DEV_SESSION, last_message=_FINISHED,
            ),
            head_shas=(MEASURED_CANDIDATE_SHA, _MOVED_SHA),
            candidate_commit=_MOVED_HEAD,
            added_lines=support.OVERSIZED_ADDITIONS,
        )

        self._assert_measured(mocks)
        self._assert_held(mocks)
        pinned = self._pinned()
        self.assertEqual(pinned[support.KEY_CANDIDATE_SHA], _MOVED_SHA)
        self.assertEqual(pinned[support.KEY_CYCLE_ID], 1)
        self.assertEqual(pinned[support.KEY_GENERATION], 2)

    def test_the_switch_off_supersedes_the_record(self) -> None:
        # Publishing the new head is what the switch says. Leaving the record
        # over work nobody is publishing is not: it names a commit this branch
        # has moved past and freezes the branch out of the base refresh.
        self._park(_GUIDANCE)
        recorded = support._RecordAtHandoff(self.github)

        with patch.object(config, _DECOMPOSE, False), recorded.held():
            mocks = self._resumed_past_the_record()

        self._assert_unmeasured(mocks)
        self._assert_published(mocks)
        pinned = self._pinned()
        self.assertNotIn(support.KEY_CANDIDATE_SHA, pinned)
        self.assertEqual(pinned[support.KEY_RETIRED_CYCLE], 1)

    def test_the_switch_off_retires_first(self) -> None:
        # And durably: what follows the retirement is a push, a pull request,
        # and the label that hands the issue to review, with the tick's own
        # write after all of it. A crash in that window would leave a
        # published pull request over a record that still says `measuring`.
        self._park(_GUIDANCE)
        recorded = support._RecordAtHandoff(self.github)

        with patch.object(config, _DECOMPOSE, False), recorded.held():
            self._resumed_past_the_record()

        self.assertNotIn(support.KEY_CANDIDATE_SHA, recorded.pinned)
        self.assertEqual(recorded.pinned[support.KEY_RETIRED_CYCLE], 1)

    def test_a_resumed_commit_is_measured(self) -> None:
        # And a run that really did commit is a fresh candidate: HEAD moved
        # off the floor the park left, so the gate measures what it produced.
        self._park(_GUIDANCE)

        mocks = self._run_gate(
            run_agent=_agent(session_id=support.DEV_SESSION, last_message=_FINISHED),
            head_shas=(MEASURED_CANDIDATE_SHA, _MOVED_SHA),
            candidate_commit=_MOVED_HEAD,
            added_lines=support.SMALL_ADDITIONS,
        )

        self._assert_resumed(mocks)
        self._assert_measured(mocks)
        self._assert_published(mocks)

    def _resumed_past_the_record(self):
        """One guidance resume whose developer committed a different SHA."""
        return self._run_gate(
            run_agent=_agent(
                session_id=support.DEV_SESSION, last_message=_FINISHED,
            ),
            head_shas=(MEASURED_CANDIDATE_SHA, _MOVED_SHA),
            candidate_commit=_MOVED_HEAD,
        )


class LateGateRecordlessRetryTest(support._ParkedRetryCase, unittest.TestCase):
    """A park a refusal took before any pair could be frozen."""

    def test_no_checkout_is_substituted_for_the_pair(self) -> None:
        # The park whose generation was never persisted: the revision would
        # not resolve, so no commit was named and the record carries none.
        # What a bare continue buys is a re-reading of the EXACT pair that was
        # recorded, and there is no pair -- so what a retry would take is a
        # FIRST reading, of whatever the checkout points at by then. Nothing
        # ties that head to this issue: a rebase, a reset, or a rebuilt
        # worktree all leave one, and measuring it publishes the base, or
        # somebody else's work, as this implementation.
        for checkout, head, decomposing in _RECORDLESS_RETRIES:
            with self.subTest(checkout=checkout, decompose=decomposing):
                self.setUp()
                self._park_without_a_record()

                with patch.object(config, _DECOMPOSE, decomposing):
                    mocks = self._run_gate(
                        added_lines=support.SMALL_ADDITIONS,
                        candidate_commit=head,
                    )

                self._assert_no_agent(mocks)
                self._assert_unmeasured(mocks)
                self._assert_held(mocks)
                self._assert_parked()

    def test_the_refusal_names_no_commit(self) -> None:
        # And what it says is true of the state it is about: nothing was
        # frozen, so the sentence may not promise a retry of a pair or name
        # the commit it would read.
        self._park_without_a_record()

        self._run_gate(candidate_commit=_MOVED_HEAD)

        notice = self.github.posted_comments[-1][1]
        self.assertIn("no commit was ever frozen", notice)
        self.assertNotIn(_MOVED_SHA, notice)
        self.assertNotIn(support.BARE_CONTINUE, notice)

    def test_a_reaped_checkout_is_still_reported(self) -> None:
        # Failure, then reap, then a bare continue: the refusal happened
        # before anything could be frozen, so the record carries no commit at
        # all -- and a report built from an empty identity is one the sinks
        # refuse, leaving the operator a park and nothing joinable to it. The
        # identity is minted for the report instead.
        self._park_without_a_record()

        self._run_gate(worktree=_REAPED_WORKTREE)

        failures = self._records(support.EVENT_LATE_FAILURE)
        self.assertEqual(len(failures), 1)
        self.assertEqual(failures[0]["failure"], "measurement_failed")
        self.assertEqual(failures[0]["measurement_failure"], _CHECKOUT_GONE)
        self.assertEqual(failures[0]["cycle_id"], 1)

    def test_a_reaped_checkout_claims_no_commit(self) -> None:
        # And what it says is true of the state it is about: no commit was
        # ever recorded, so the sentence may not name one.
        self._park_without_a_record()

        self._run_gate(worktree=_REAPED_WORKTREE)

        notice = self.github.posted_comments[-1][1]
        self.assertIn("no commit was ever frozen", notice)
        self.assertNotIn(MEASURED_CANDIDATE_SHA, notice)

    def test_a_new_candidate_is_still_bypassed(self) -> None:
        # The switch is not disarmed by the flag: an issue with no park behind
        # it is ordinary new work and publishes unmeasured, as it always has.
        with patch.object(config, _DECOMPOSE, False):
            mocks = self._run_gate()

        self._assert_unmeasured(mocks)
        self._assert_published(mocks)


class LateGateRecordlessGuidanceTest(
    support._ParkedRetryCase, unittest.TestCase,
):
    """What guidance to a park that froze nothing buys, and what it may not.

    The refusal a bare continue earns is not a dead end: a reply with words in
    it is guidance, so it never reaches that refusal at all and the developer
    is resumed. What it leaves is then judged the ordinary way -- which on
    this park is the whole difficulty, because there is no record of any kind
    on the issue and the branch already carries commits nothing names.
    """

    def setUp(self) -> None:
        super().setUp()
        self._park_without_a_record(reply=_GUIDANCE)

    def test_guidance_still_reaches_the_developer(self) -> None:
        mocks = self._resumed(head_shas=(MEASURED_CANDIDATE_SHA, _MOVED_SHA))

        self._assert_resumed(mocks)
        self._assert_measured(mocks)
        self._assert_published(mocks)

    def test_a_question_parks_over_the_inherited_work(self) -> None:
        # The commits on the branch predate this run and nothing on the issue
        # names them: the refusal that took this park could not freeze a
        # candidate, so there is no floor to judge the resume against and
        # ahead-of-base says "this run committed" for a run that committed
        # nothing. Published on that reading, the developer's question is
        # dropped and work a human was still deciding about goes to review.
        mocks = self._resumed(
            head_shas=(MEASURED_CANDIDATE_SHA, MEASURED_CANDIDATE_SHA),
            last_message=_ASKED,
        )

        self._assert_resumed(mocks)
        self._assert_unmeasured(mocks)
        self._assert_held(mocks)
        self.assertIn(_ASKED, self.github.posted_comments[-1][1])
        self.assertTrue(self._pinned()[support.AWAITING_HUMAN])

    def _resumed(self, last_message: str = _FINISHED, **run_options):
        """One guidance resume, and what the checkout says it left."""
        return self._run_gate(
            run_agent=_agent(
                session_id=support.DEV_SESSION, last_message=last_message,
            ),
            added_lines=support.SMALL_ADDITIONS,
            **run_options,
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

        mocks = self._run_gate(worktree=_REAPED_WORKTREE)

        self._assert_no_agent(mocks)
        self._assert_unmeasured(mocks)
        self._assert_held(mocks)
        self._assert_parked()
        posted = [body for _, body in self.github.posted_comments]
        self.assertIn("not on this host", posted[-1])
        self.assertFalse(any(_NEEDS_GUIDANCE in body for body in posted))

    def test_an_absent_worktree_keeps_the_record(self) -> None:
        # And the retry it promises has something to come back to: the pair is
        # left exactly as it was, and the failure is reported like any other.
        self._park(support.BARE_CONTINUE)

        self._run_gate(worktree=_REAPED_WORKTREE)

        self._assert_frozen()
        failures = self._records(support.EVENT_LATE_FAILURE)
        self.assertEqual(len(failures), 1)
        self.assertEqual(failures[0]["failure"], "measurement_failed")
        # And which step it stopped at, which is what tells this refusal from
        # a base a fetch could not bring on the very same pair.
        self.assertEqual(failures[0]["measurement_failure"], _CHECKOUT_GONE)


class _LandsTheRetry:
    """One operator writing the retry command, the instant a step has run.

    A class rather than a closure because a seam this repository patches is a
    value with a name, and because it has to fire ONCE: hung on a read and
    fired on every one of them, each later reading would answer against a
    thread the one before it never saw.
    """

    def __init__(self, case) -> None:
        self._case = case
        self.landed = False

    def __call__(self) -> None:
        if not self.landed:
            self.landed = True
            self._case._reply(support.BARE_CONTINUE)


class LateGateContinueRaceTest(support._ParkedRetryCase, unittest.TestCase):
    """A retry command that lands between two of one tick's own thread reads.

    Every road that reads a parked thread reads it again after the one above
    it handed the tick back, and both roads behind this park's own would SPEND
    the reply that ends it. The parked-continue classifier reads a command on
    a park that is not a session failure as one carrying no answer, refuses it
    and consumes the thread past its own refusal; the generic resume reads it
    as guidance and pays for a developer to answer it. Either way the
    operator's retry is gone and the reading they asked for is one nothing
    will ever take.
    """

    def test_a_retry_landing_mid_read_is_kept(self) -> None:
        # The window between this park's own reading of the thread and the
        # classifier's. Answered there, the operator is asked for guidance
        # they have no reason to write, and the watermark moves past both
        # their command and the sentence asking.
        mocks = self._races(_late_parks, _ANSWERS_THE_PARK)

        self._assert_deferred(mocks)

    def test_a_retry_landing_past_it_is_kept(self) -> None:
        # And the window after it, which only the resume can still see. Read
        # as guidance there, a developer is paid to answer a reply that asks
        # for a reading rather than for work.
        mocks = self._races(_continue_command, _PARKED_CONTINUE_DECISION)

        self._assert_deferred(mocks)

    def test_the_deferred_retry_re_measures(self) -> None:
        # What deferring buys. Nothing was consumed, so the command is still
        # the whole of the fresh batch on the next poll -- and the road that
        # can act on it takes the reading again and publishes on it, with no
        # developer paid for over work that is committed already.
        self._races(_continue_command, _PARKED_CONTINUE_DECISION)

        mocks = self._run_gate(added_lines=support.SMALL_ADDITIONS)

        self._assert_no_agent(mocks)
        self._assert_published(mocks)

    def _races(self, owner, step: str):
        """Run one tick with the retry landing the instant `step` returns."""
        self._seed(**{
            support.AWAITING_HUMAN: True,
            support.PARK_REASON: _late_parks.PARK_MEASUREMENT_FAILED,
            support.LAST_ACTION_COMMENT_ID: support.PRIOR_ACTION_COMMENT_ID,
            **support.recorded_generation(),
        })
        with patch.object(
            owner, step,
            _RacesPastTheStep(getattr(owner, step), _LandsTheRetry(self)),
        ):
            return self._run_gate()

    def _assert_deferred(self, mocks) -> None:
        """Nothing ran, nothing was said, and the command is still unread."""
        self._assert_no_agent(mocks)
        self._assert_held(mocks)
        self.assertEqual(self.github.posted_comments, [])
        self.assertEqual(
            self._pinned()[support.LAST_ACTION_COMMENT_ID],
            support.PRIOR_ACTION_COMMENT_ID,
        )


if __name__ == "__main__":
    unittest.main()
