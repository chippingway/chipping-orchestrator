# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""A docs commit the size gate held, published by an adjudication that answered newer requirements, reported again.

Walked whole by the dispatcher from an approval that published its head as it
stands: the docs pass commits past the ceiling, so the gate holds the commit
and the late adjudication takes it. While it decides, a trusted human writes
guidance the adjudicator acknowledges -- requirements past the ones the
approval was given -- and a human then authorizes the oversized commit, which
the settlement publishes and hands back to the docs pass. That pass completes
from its receipt into `in_review`, whose approval no longer covers the
requirements, so the issue goes back to `workflow:validating` for a fresh
review. The settled report is still about the approved commit, under the old
requirements, while the pull request stands on the docs commit: the report
hold reads the docs commit as the rewrite it is and asks the developer for a
report of it against the requirements the issue carries now, with no human,
and the walk goes on through that review to one ready ping.
"""
from __future__ import annotations

import unittest
from unittest.mock import patch

from orchestrator import config
from orchestrator.git.measurement.models import AdditionMeasurement
from tests.workflow import drift_reports as _drift_world
from tests.workflow.fixtures import MEASURED_BASE_SHA, _agent
from tests.workflow.stages.decomposition.late_run_support import WorktreeSeed, adjudicate
from tests.workflow.stages.decomposition.late_test_support import SINGLE_REPLY
from tests.workflow.stages.validating import (
    changed_docs_journey_support as _docs,
    changed_docs_readings as _readings,
    readiness_journey_support as _readiness,
    squash_rebase_journey_support as _journey,
)

DOCS_HEAD = _docs.DOCS_HEAD

# The ceiling the docs commit's additions pass, and the guidance the
# adjudicator acknowledges while it decides on that commit.
CEILING = 10

PAST_THE_CEILING = CEILING + 1

GUIDANCE = "Keep the CLI flags unchanged as you finish this work."

ACKNOWLEDGED = "ACK: the CLI flags are already unchanged."

# The roles the walk runs from the docs pass on: the pass, the report refresh
# its changed requirements are owed, the fresh reviewer, and the next pass.
REPORTED_AGAIN = (_journey.DOCUMENTER, _journey.REFRESHER, _journey.REVIEWER, _journey.DOCUMENTER)


class AdjudicatedRequirementsTest(_docs._ChangedDocsWalk, unittest.TestCase):
    """Requirements an adjudication answered past the approval earn a report of the docs commit, then a review."""

    def setUp(self) -> None:
        super().setUp()
        for setting, configured in (
            ("SQUASH_ON_APPROVAL", False), ("MAX_ADDED_LINES", CEILING), ("ALLOWED_ISSUE_AUTHORS", ("alice",)),
        ):
            self.enterContext(patch.object(config, setting, configured))

    def test_the_docs_commit_is_reported_for_them(self) -> None:
        # The docs commit reaches `in_review` and is handed back for review;
        # the report hold records the rewrite the docs commit is and refreshes
        # the report for it under the current requirements, the reviewer
        # approves that report, and the pull request is told once.
        self.walks_into_documenting()
        self.changes_the_docs(added_lines=PAST_THE_CEILING)
        self.adjudicated_after_guidance()

        self.dispatched(verify_result=_readings.docs_run())
        for _ in range(2):
            self.dispatched(_journey.refresh())

        self.assert_reported_again()
        self.approved_into_review(DOCS_HEAD)
        self.assertEqual(self.roles(), REPORTED_AGAIN)
        self.assert_told_once(((_readiness.READY,),), DOCS_HEAD)

    def adjudicated_after_guidance(self) -> None:
        """The held docs commit adjudicated `single`, guidance acknowledged, and its publication authorized."""
        seed = WorktreeSeed(head=DOCS_HEAD)
        measured = AdditionMeasurement(
            base_sha=MEASURED_BASE_SHA, candidate_sha=DOCS_HEAD, additions=PAST_THE_CEILING,
        )
        adjudicate(self.github, self.issue, _agent(last_message=SINGLE_REPLY), worktree=seed)
        _drift_world.human_reply(self, GUIDANCE)
        acknowledges = _agent(last_message=ACKNOWLEDGED)
        adjudicate(self.github, self.issue, acknowledges, worktree=seed, measurement=measured)
        adjudicate(self.github, self.issue, _agent(last_message=SINGLE_REPLY), worktree=seed)
        _drift_world.human_reply(self, f"/orchestrator authorize-oversized {DOCS_HEAD}")
        adjudicate(self.github, self.issue, worktree=seed)
        self.pull_request.head.sha = DOCS_HEAD

    def assert_reported_again(self) -> None:
        """The docs pass and the report refresh ran, and a report of the docs commit settled under requirements now."""
        pinned = self.pinned()
        refreshed = pinned[_docs.CURRENT_REPORT]
        self.assertEqual(self.roles(), REPORTED_AGAIN[:2])
        reported = (refreshed["sha"], refreshed["requirements"])
        self.assertEqual(reported, (DOCS_HEAD, pinned["user_content_hash"]))


if __name__ == "__main__":
    unittest.main()
