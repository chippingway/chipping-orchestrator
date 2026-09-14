# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Measurement retries retain an unreadable or moved frozen pair."""
from __future__ import annotations

import unittest

from orchestrator.git.measurement.models import MeasurementFailure
from tests.workflow.fixtures import (
    MEASURED_CANDIDATE_SHA,
    _agent,
)
from tests.workflow.stages.implementing import (
    late_gate_test_support as support,
    late_retry_doubles as _retry_doubles,
    late_retry_payloads as _retry_payloads,
)


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
