# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""An approval squashed onto the tree it approved and documented unchanged, walked through to the ready ping.

Walked whole by the dispatcher: the reviewer approves the report of the
approved commit on its own run, the squash publishes another head on the same
tree and carries that run onto it, the carry settles, the final-docs pass finds
nothing to change, and `in_review` pings the head as ready. The ping rests on
the carry -- the run on the approved commit, answering for the squash -- and is
said once, after everything it vouches for, whatever GitHub does to the write
recording it. Quiet ticks behind it do nothing at all.
"""
from __future__ import annotations

import unittest
from unittest.mock import patch

from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.engine import verification_settlement_state as _settlement
from tests.workflow import published_reports as _published_reports
from tests.workflow.stages.validating import (
    readiness_journey_support as _readiness,
    squash_evidence_test_support as _squash,
    squash_rebase_journey_support as _journey,
)

HEAD = _journey.HEAD

SQUASHED = _journey.SQUASHED

# What the walk tells from the start, in order: the report the pull request was
# opened with, the reviewer spawned and the artifact of its own run on the
# approved commit, the squash's carry of that run onto the head it published,
# the docs pass, and the ready ping last.
WALKED_IN = (
    (_readiness.REPORT, HEAD),
    (_readiness.SPAWN, _journey.REVIEWER),
    (_readiness.ARTIFACT, _readiness.REVIEWER_REPORTED, HEAD, HEAD),
    (_readiness.ARTIFACT, _readiness.REVIEWER_REPORTED, HEAD, SQUASHED),
    (_readiness.SPAWN, _journey.DOCUMENTER),
    (_readiness.READY,),
)

# What the walk ran: the reviewer and the docs pass, one run of the approval's
# verification gate, and the reviewer's own run of the approved commit as the
# evidence the ping rests on.
RAN = ((_journey.REVIEWER, _journey.DOCUMENTER), 1, HEAD)

# The client request a ping's record lands through, and the record naming the
# head it pinged.
EDIT_PINNED_STATE = "edit_pinned_state"

PINGED = "ready_ping_sha"


class EquivalentSquashReadinessTest(_journey._SquashRebaseJourney, unittest.TestCase):
    """The squash's carry is what the ready ping rests on, said once behind everything it vouches for."""

    def test_a_squash_is_pinged_over_its_carry(self) -> None:
        # GitHub refuses the write recording the ping, so the next dispatch
        # finds it on the thread and records it rather than saying it again.
        # The reviewer was handed the report and ran the configured suite
        # once; the approval's own verification gate ran once; the ping
        # names the squash, the head the carry answers for, over a run of the
        # approved commit.
        unrecorded = self._walks_into_an_unrecorded_ping()

        self.dispatched()

        self.assertEqual(unrecorded, (1, None))
        self.assertEqual(self.told(), WALKED_IN)
        self.assert_ready_on(SQUASHED)
        self.assertEqual(self._ran(), RAN)
        self.assertIn(f"> {_published_reports.DELIVERED_REPORT}", self.spawned(_journey.REVIEWER)[0])
        self.assert_quiet()

    def _walks_into_an_unrecorded_ping(self) -> tuple:
        """Approve, squash, settle the carry, and pass the docs unchanged; then ping with the ping's record refused.

        Returns the pings on the thread and the head recorded as pinged.
        """
        self.dispatched(_journey.approval_on(HEAD), squash_result=_squash.LandsTheSquash(self))
        self.dispatched()
        self.dispatched(_journey.DOCS)
        with patch.object(self.github, EDIT_PINNED_STATE, _readiness.RefusesTheSettlement(self.github)):
            self.dispatched()
        return len(self.ready_pings()), self.pinned().get(PINGED)

    def _ran(self) -> tuple:
        """The roles spawned, the verification gate's runs, and the commit the current evidence ran on."""
        carried = _settlement.read_current_evidence(PinnedState(state_data=self.pinned()))
        return self.roles(), self.verifications, carried.binding.tested_sha


if __name__ == "__main__":
    unittest.main()
