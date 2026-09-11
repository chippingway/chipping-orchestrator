# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The record a poll reads while a worker is retiring the cycle it names.

A published `single` drops its generation and then asks the latch, and the
record says nothing at all in between -- no cycle identity, which is the one
thing every reader of a close consults. A poll that reads it there is reading
a record whose worker is still holding the question open, so what it may not
do is call the reading spent: the barrier behind the write would find nothing
latched, and the observation would be gone with no durable half either.
"""
from __future__ import annotations

import unittest
from unittest.mock import patch

from orchestrator.workflow.engine import observations
from tests.support.fakes import FakeGitHubClient
from tests.workflow.engine import refused_submit_support as _support
from tests.workflow.engine.refused_submit_support import Retiring, Scheduler
from tests.workflow.observation_support import ObservedCloseCase, receipt_for


class RetirementInFlightTest(ObservedCloseCase, unittest.TestCase):
    """The ordering between the retirement write and the barrier behind it.

    A published `single` drops its cycle and then asks the latch, and the
    record says nothing at all in between. A poll reading it there is reading
    a record whose worker is still holding the question open, so what it may
    not do is call the reading spent.
    """

    def setUp(self) -> None:
        self._fresh_process()

    def test_a_retirement_in_flight_keeps_the_reading(self) -> None:
        # And the ordering between the two, which the record cannot describe:
        # the retirement write has landed and the barrier that would answer a
        # latched close has not. A reading called spent here is one the worker
        # asks for a moment later and does not find.
        github = _support.closed_owner(live=True)

        self._retired_under_a_worker(github)

        self.assertEqual(
            self._observed(_support.SPEC.slug), frozenset((_support.OWNER_NUMBER,)),
        )

    def test_a_retirement_in_flight_is_told(self) -> None:
        # The durable half of that reading, and the only half a restart still
        # has: a receipt is scoped to a cycle, and the record it is written
        # from no longer names one -- so the scope comes from the cycle the
        # worker is retiring.
        github = _support.closed_owner(live=True)

        self._retired_under_a_worker(github)

        marker = receipt_for(_support.OWNER_NUMBER, _support.CYCLE_ID)
        self.assertEqual(
            [body for _, body in github.posted_comments if marker in body],
            [body for _, body in github.posted_comments],
        )
        self.assertEqual(len(github.posted_comments), 1)

    def _retired_under_a_worker(self, github: FakeGitHubClient) -> None:
        """Refuse this tick's submit against a record mid-retirement."""
        retiring = observations.retiring(_support.SPEC.slug, _support.OWNER_NUMBER, _support.CYCLE_ID)
        with self.assertLogs(_support.WORKFLOW_LOG), retiring.held(), patch.object(
            github, _support.PINNED_READ, side_effect=Retiring(github),
        ):
            _support.offered(github, Scheduler(admits=False))


if __name__ == "__main__":
    unittest.main()
