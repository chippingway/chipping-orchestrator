# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Bare retry commands remeasure frozen work and survive thread-read races."""
from __future__ import annotations

import unittest
from unittest.mock import patch

from orchestrator import config
from orchestrator.workflow.stages.implementing import (
    continue_command as _continue_command,
    late_measurement_reply as _late_measurement_reply,
    late_measurement_state as _late_measurement_state,
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

    def test_an_undelivered_comment_still_remeasures(self) -> None:
        # Two comments past the mark that no resume hands a developer, and
        # each one read as a second voice makes this road call the batch
        # mixed and decline the retry. Our own notice is the window the park
        # itself opens: the operator writes while the agent is out and the
        # notice lands above them, so the resume behind this pays a developer
        # to answer `/orchestrator continue` as prose. A grant's command is
        # the run-limit cycle's leftover: the resume drops it, sees the
        # continue bare, and reserves it for this road -- which declined it,
        # so the park stands with nothing measured, refused, or said.
        for described, park in (
            ("our notice over it", self._park_under_our_notice),
            ("an answered grant under it", self._park_over_an_answered_grant),
        ):
            with self.subTest(comment=described):
                self.setUp()
                park()

                mocks = self._run_gate(added_lines=support.SMALL_ADDITIONS)

                self._assert_no_agent(mocks)
                self._assert_measured(mocks)
                self._assert_published(mocks)

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

    def test_a_retry_between_thread_reads_is_kept(self) -> None:
        for owner, step in (
            (_late_measurement_reply, _retry_payloads._ANSWERS_THE_PARK),
            (_continue_command, _retry_payloads._PARKED_CONTINUE_DECISION),
        ):
            with self.subTest(step=step):
                self.setUp()
                mocks = self._races(owner, step)

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
