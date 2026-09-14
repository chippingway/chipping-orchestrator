# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Measurement retry notices describe the recorded candidate."""
from __future__ import annotations

import unittest

from orchestrator.git.measurement.models import FrozenCommit, MeasurementFailure
from tests.workflow.stages.implementing import (
    late_gate_test_support as support,
    late_retry_payloads as _retry_payloads,
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
