# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Retry and guidance replies when a measurement park froze no candidate."""
from __future__ import annotations

import unittest
from unittest.mock import patch

from orchestrator import config
from tests.workflow.fixtures import (
    MEASURED_CANDIDATE_SHA,
    _agent,
)
from tests.workflow.stages.implementing import (
    late_gate_test_support as support,
    late_retry_payloads as _retry_payloads,
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
