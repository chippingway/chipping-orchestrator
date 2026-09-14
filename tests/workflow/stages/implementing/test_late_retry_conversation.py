# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Human guidance resumes the developer behind a measurement park."""
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
        # Retirement must be durable before the publication handoff.
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
