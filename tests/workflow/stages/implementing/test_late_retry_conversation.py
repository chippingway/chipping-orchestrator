# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Continuation and guidance replies across held, stale, and missing measurement records."""
from __future__ import annotations

import unittest
from unittest.mock import patch

from orchestrator.config import settings as config
from orchestrator.git.measurement.models import FrozenCommit, MeasurementFailure
from orchestrator.workflow.stages.implementing import (
    continue_command as _continue_command,
    late_measurement_reply as _late_measurement_reply,
    late_measurement_state as _late_measurement_state,
)
from tests.workflow.fixtures import (
    MEASURED_CANDIDATE_SHA,
    _agent,
)
from tests.workflow.interleaving import _RacesPastTheStep
from tests.workflow.stages.implementing import (
    late_gate_test_support as support,
    late_retry_doubles as _retry_doubles,
    late_retry_payloads as _retry_payloads,
)


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
        for failure in _retry_payloads._UNRETRIED_STEPS:
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
            candidate_commit=_retry_payloads._MOVED_HEAD,
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

                with patch.object(config, _retry_payloads._DECOMPOSE, decomposing):
                    mocks = self._run_gate(candidate_commit=_retry_payloads._HEAD_MOVES)

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
                candidate_commit=_retry_payloads._MOVED_HEAD,
            )

        self._assert_no_agent(mocks)
        self._assert_held(mocks)
        self._assert_parked()
        self._assert_frozen()


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
                base_sha="", measurement_miss_count=_retry_payloads._MISS_BOUND,
            ),
        )

        self._run_gate(frozen_base=FrozenCommit(
            failure=MeasurementFailure.BASE_UNREADABLE, detail=_retry_payloads._REMOTE_SAID,
        ))

        self._assert_parked()
        self._assert_announced(MeasurementFailure.BASE_UNREADABLE)
        notice = self.github.posted_comments[-1][1]
        self.assertIn(_retry_payloads._LS_REMOTE, notice)
        self.assertIn(_retry_payloads._GIT_PLUMBING, notice)
        self.assertIn(_retry_payloads._REMOTE_SAID, notice)
        self.assertIn(_retry_payloads._ORCH_COMMENT_MARKER, notice)

    def test_a_reading_that_lands_clears_the_step(self) -> None:
        # A count in hand is the end of every step a reading can stop at, so
        # the member the notice named describes a refusal that is over. The
        # record an oversized candidate leaves is what the adjudication is
        # driven from, and it survives this write: carried into it, the step
        # would describe a refusal nobody is making on an issue whose park
        # this same verdict retired.
        self._park_after_misses(
            _retry_payloads._MISS_BOUND + 1, announced=MeasurementFailure.BASE_ABSENT,
        )

        mocks = self._run_gate(added_lines=support.OVERSIZED_ADDITIONS)

        self._assert_measured(mocks)
        self._assert_held(mocks)
        self.assertIn(_retry_payloads._DECOMPOSING, self.github.label_history)
        pinned = self._pinned()
        self.assertEqual(
            pinned[support.KEY_ADDITIONS], support.OVERSIZED_ADDITIONS,
        )
        self.assertNotIn(support.KEY_MISS_COUNT, pinned)
        self.assertNotIn(support.KEY_MEASUREMENT_FAILURE, pinned)


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
        self._park_state(_retry_payloads._GUIDANCE, **support.recorded_generation(
            measurement_miss_count=_retry_payloads._MISS_BOUND,
            measurement_failure=MeasurementFailure.BASE_ABSENT,
        ))
        writes = _retry_doubles._WritesDuringTheTick(self.github)

        with writes.held():
            self._run_gate(
                run_agent=_agent(
                    session_id=support.DEV_SESSION, last_message=_retry_payloads._FINISHED,
                ),
                head_shas=(MEASURED_CANDIDATE_SHA, _retry_payloads._MOVED_SHA),
                candidate_commit=_retry_payloads._MOVED_HEAD,
                added_lines=support.SMALL_ADDITIONS,
            )

        fresh = [
            written for written in writes.writes
            if written.get(support.KEY_CANDIDATE_SHA) == _retry_payloads._MOVED_SHA
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
        self._park(_retry_payloads._GUIDANCE)

        mocks = self._run_gate(
            run_agent=_agent(session_id=support.DEV_SESSION, last_message=_retry_payloads._FINISHED),
            head_shas=(MEASURED_CANDIDATE_SHA, _retry_payloads._MOVED_SHA),
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
        self._park(_retry_payloads._GUIDANCE)

        mocks = self._run_gate(
            run_agent=_agent(
                session_id=support.DEV_SESSION, last_message=_retry_payloads._FINISHED,
            ),
            head_shas=(MEASURED_CANDIDATE_SHA, _retry_payloads._MOVED_SHA),
            candidate_commit=_retry_payloads._MOVED_HEAD,
            added_lines=support.OVERSIZED_ADDITIONS,
        )

        self._assert_measured(mocks)
        self._assert_held(mocks)
        pinned = self._pinned()
        self.assertEqual(pinned[support.KEY_CANDIDATE_SHA], _retry_payloads._MOVED_SHA)
        self.assertEqual(pinned[support.KEY_CYCLE_ID], 1)
        self.assertEqual(pinned[support.KEY_GENERATION], 2)

    def test_the_switch_off_supersedes_the_record(self) -> None:
        # Publishing the new head is what the switch says. Leaving the record
        # over work nobody is publishing is not: it names a commit this branch
        # has moved past and freezes the branch out of the base refresh.
        self._park(_retry_payloads._GUIDANCE)
        recorded = support._RecordAtHandoff(self.github)

        with patch.object(config, _retry_payloads._DECOMPOSE, False), recorded.held():
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
        self._park(_retry_payloads._GUIDANCE)
        recorded = support._RecordAtHandoff(self.github)

        with patch.object(config, _retry_payloads._DECOMPOSE, False), recorded.held():
            self._resumed_past_the_record()

        self.assertNotIn(support.KEY_CANDIDATE_SHA, recorded.pinned)
        self.assertEqual(recorded.pinned[support.KEY_RETIRED_CYCLE], 1)

    def test_a_resumed_commit_is_measured(self) -> None:
        # And a run that really did commit is a fresh candidate: HEAD moved
        # off the floor the park left, so the gate measures what it produced.
        self._park(_retry_payloads._GUIDANCE)

        mocks = self._run_gate(
            run_agent=_agent(session_id=support.DEV_SESSION, last_message=_retry_payloads._FINISHED),
            head_shas=(MEASURED_CANDIDATE_SHA, _retry_payloads._MOVED_SHA),
            candidate_commit=_retry_payloads._MOVED_HEAD,
            added_lines=support.SMALL_ADDITIONS,
        )

        self._assert_resumed(mocks)
        self._assert_measured(mocks)
        self._assert_published(mocks)

    def _resumed_past_the_record(self):
        """One guidance resume whose developer committed a different SHA."""
        return self._run_gate(
            run_agent=_agent(
                session_id=support.DEV_SESSION, last_message=_retry_payloads._FINISHED,
            ),
            head_shas=(MEASURED_CANDIDATE_SHA, _retry_payloads._MOVED_SHA),
            candidate_commit=_retry_payloads._MOVED_HEAD,
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
        for checkout, head, decomposing in _retry_payloads._RECORDLESS_RETRIES:
            with self.subTest(checkout=checkout, decompose=decomposing):
                self.setUp()
                self._park_without_a_record()

                with patch.object(config, _retry_payloads._DECOMPOSE, decomposing):
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

        self._run_gate(candidate_commit=_retry_payloads._MOVED_HEAD)

        notice = self.github.posted_comments[-1][1]
        self.assertIn("no commit was ever frozen", notice)
        self.assertNotIn(_retry_payloads._MOVED_SHA, notice)
        self.assertNotIn(support.BARE_CONTINUE, notice)

    def test_a_reaped_checkout_is_still_reported(self) -> None:
        # Failure, then reap, then a bare continue: the refusal happened
        # before anything could be frozen, so the record carries no commit at
        # all -- and a report built from an empty identity is one the sinks
        # refuse, leaving the operator a park and nothing joinable to it. The
        # identity is minted for the report instead.
        self._park_without_a_record()

        self._run_gate(worktree=_retry_payloads._REAPED_WORKTREE)

        failures = self._records(support.EVENT_LATE_FAILURE)
        self.assertEqual(len(failures), 1)
        self.assertEqual(failures[0]["failure"], "measurement_failed")
        self.assertEqual(failures[0]["measurement_failure"], _retry_payloads._CHECKOUT_GONE)
        self.assertEqual(failures[0]["cycle_id"], 1)

    def test_a_reaped_checkout_claims_no_commit(self) -> None:
        # And what it says is true of the state it is about: no commit was
        # ever recorded, so the sentence may not name one.
        self._park_without_a_record()

        self._run_gate(worktree=_retry_payloads._REAPED_WORKTREE)

        notice = self.github.posted_comments[-1][1]
        self.assertIn("no commit was ever frozen", notice)
        self.assertNotIn(MEASURED_CANDIDATE_SHA, notice)

    def test_a_new_candidate_is_still_bypassed(self) -> None:
        # The switch is not disarmed by the flag: an issue with no park behind
        # it is ordinary new work and publishes unmeasured, as it always has.
        with patch.object(config, _retry_payloads._DECOMPOSE, False):
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
        self._park_without_a_record(reply=_retry_payloads._GUIDANCE)

    def test_guidance_still_reaches_the_developer(self) -> None:
        mocks = self._resumed(head_shas=(MEASURED_CANDIDATE_SHA, _retry_payloads._MOVED_SHA))

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
            last_message=_retry_payloads._ASKED,
        )

        self._assert_resumed(mocks)
        self._assert_unmeasured(mocks)
        self._assert_held(mocks)
        self.assertIn(_retry_payloads._ASKED, self.github.posted_comments[-1][1])
        self.assertTrue(self._pinned()[support.AWAITING_HUMAN])

    def _resumed(self, last_message: str = _retry_payloads._FINISHED, **run_options):
        """One guidance resume, and what the checkout says it left."""
        return self._run_gate(
            run_agent=_agent(
                session_id=support.DEV_SESSION, last_message=last_message,
            ),
            added_lines=support.SMALL_ADDITIONS,
            **run_options,
        )


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
        mocks = self._races(_late_measurement_reply, _retry_payloads._ANSWERS_THE_PARK)

        self._assert_deferred(mocks)

    def test_a_retry_landing_past_it_is_kept(self) -> None:
        # And the window after it, which only the resume can still see. Read
        # as guidance there, a developer is paid to answer a reply that asks
        # for a reading rather than for work.
        mocks = self._races(_continue_command, _retry_payloads._PARKED_CONTINUE_DECISION)

        self._assert_deferred(mocks)

    def test_the_deferred_retry_re_measures(self) -> None:
        # What deferring buys. Nothing was consumed, so the command is still
        # the whole of the fresh batch on the next poll -- and the road that
        # can act on it takes the reading again and publishes on it, with no
        # developer paid for over work that is committed already.
        self._races(_continue_command, _retry_payloads._PARKED_CONTINUE_DECISION)

        mocks = self._run_gate(added_lines=support.SMALL_ADDITIONS)

        self._assert_no_agent(mocks)
        self._assert_published(mocks)

    def _races(self, owner, step: str):
        """Run one tick with the retry landing the instant `step` returns."""
        self._seed(**{
            support.AWAITING_HUMAN: True,
            support.PARK_REASON: _late_measurement_state.PARK_MEASUREMENT_FAILED,
            support.LAST_ACTION_COMMENT_ID: support.PRIOR_ACTION_COMMENT_ID,
            **support.recorded_generation(),
        })
        with patch.object(
            owner, step,
            _RacesPastTheStep(getattr(owner, step), _retry_doubles._LandsTheRetry(self)),
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
