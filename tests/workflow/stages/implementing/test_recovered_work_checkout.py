# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The quiet recoveries of committed work, over a checkout at the issue's path on the flat branch.

A timeout park whose run stranded a commit, a candidate a crashed tick froze
and never disposed of, a measurement park a human asked to retry, an approved
commit whose checkout came back, and an authorization a human gave are all
finished without a developer: the commit in the checkout is measured and
published, or handed to an adjudication, through the size gate. A body edit
before any session reads that commit too, and parks or clears its park over
it. So each admits the checkout before it reads the tree or clears anything,
and one on the flat branch carrying an oversized commit refuses
(`naming.BranchRefused`) with the record, the label, and the thread as they
were -- measured, recorded, announced, and routed nowhere.
"""
from __future__ import annotations

import unittest
from unittest.mock import patch

from orchestrator import config
from tests.support.fakes import FakeComment, FakeUser
from tests.workflow.report_values import _recovered_report
from tests.workflow.stages.implementing import flat_commit_support as _flat
from tests.workflow.stages.implementing.late_gate_test_support import recorded_generation


def _frozen(world: _flat.FlatCommitWorld) -> dict:
    """The generation a size gate froze over the flat checkout's commit, as the record pins it."""
    return recorded_generation(
        root_issue=_flat.ISSUE, current_issue=_flat.ISSUE, threshold=1,
        candidate_sha=world.candidate, base_sha=world.base,
    )


class RecoveredWorkCheckoutTest(unittest.TestCase):
    """Each quiet recovery of committed work, over the flat checkout's oversized commit."""

    def setUp(self) -> None:
        self.world = _flat.FlatCommitWorld(self)

    def test_a_timeout_park_recovers_nothing(self) -> None:
        self.world.seeds(awaiting_human=True, park_reason="agent_timeout", pre_implement_sha=self.world.base)

        self.world.refuses(self)

    def test_a_frozen_candidate_is_not_measured(self) -> None:
        self.world.seeds(implementing_incomplete_run_sha=self.world.candidate, **_frozen(self.world))

        self.world.refuses(self)

    def test_a_measurement_retry_measures_nothing(self) -> None:
        # The bare continue is written before the baseline is seeded, so it
        # reads as the reply it is rather than as an edit.
        reply = FakeComment(id=1, body="/orchestrator continue", user=FakeUser("alice"))
        self.world.issue.comments.append(reply)
        self.world.seeds(
            awaiting_human=True, park_reason="late_measurement_failed", last_action_comment_id=0,
            implementing_incomplete_run_sha=self.world.candidate, **_frozen(self.world),
        )

        self.world.refuses(self)

    def test_a_moved_candidate_is_not_republished(self) -> None:
        # The approved commit is the flat checkout's head, which reads as the
        # checkout having come back to it.
        self.world.seeds(
            awaiting_human=True, park_reason="late_candidate_moved", late_approved_sha=self.world.candidate,
        )

        self.world.refuses(self)

    def test_an_authorization_publishes_nothing(self) -> None:
        self.enterContext(patch.object(config, "ALLOWED_ISSUE_AUTHORS", ("alice",)))
        candidate = self.world.candidate
        command = FakeComment(id=1, body=f"/orchestrator authorize-oversized {candidate}", user=FakeUser("alice"))
        self.world.issue.comments.append(command)
        self.world.seeds(
            awaiting_human=True, park_reason="late_unauthorized_exemption", last_action_comment_id=0,
            late_exempt_sha=self.world.candidate, **_recovered_report(self.world.issue),
        )

        self.world.refuses(self)

    def test_a_body_edit_announces_nothing(self) -> None:
        # No developer session is recorded, and the body changed since the
        # baseline the record holds.
        self.world.seeds(awaiting_human=True, park_reason="agent_failed", user_content_hash="before-the-edit")

        self.world.refuses(self)


if __name__ == "__main__":
    unittest.main()
