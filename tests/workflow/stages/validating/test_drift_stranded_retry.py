# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""A drift resume that commits over work an earlier one left on the branch.

A resume can leave a commit the pull request never receives -- one parked for
the report it did not write, one a shutdown killed before anything was
recorded -- and the resume behind it commits AGAIN. The checkout is then two
commits above the pull request, and the head that run began at is the stranded
commit rather than anything the pull request carries.

What such a publication replaces is the pull request's own head, so the branch
goes out whole under the report that describes it. Leased against the head the
run began at instead, the size gate is entered on a commit the pull request
has never seen, every tick over that branch parks unmeasured, and neither the
accumulated code nor its report ever lands.
"""

from __future__ import annotations

import unittest

from tests.workflow import drift_reports as world
from tests.workflow.fixtures import LABEL_VALIDATING, _agent

ISSUE = 1_793

PR = 17_930

PUSH_BRANCH = "_push_branch"

PARK_REASON = "park_reason"


class StrandedRetryPublicationTest(unittest.TestCase, world._DriftReportMixin):
    def test_a_retry_publishes_over_the_stranded(self) -> None:
        # The resume committed and reported nothing, so its commit stayed in
        # the worktree and the pull request is standing under it. The reply
        # resumes the session, which commits again and reports this time:
        # both commits go out, and the report that describes the branch as it
        # stands goes out with them.
        self.seeded(ISSUE, PR, LABEL_VALIDATING)
        self.drift("fixed the criteria", **world.STRANDS)
        world.human_reply(self)

        retried = self.drift(world.reported(), **world.RETRY_OVER_STRANDED)

        retried[PUSH_BRANCH].assert_called_once()
        self.assertIsNone(self.pinned().get(PARK_REASON))
        self.assertEqual(self.pull_request.head.sha, world.FIXED_HEAD)
        self.reconcile()
        self.assertEqual(len(self.published_reports()), 1)

    def test_a_retry_commits_over_what_the_kill_left(self) -> None:
        # The same branch with nothing recorded at all: the shutdown sweep
        # kills a resume that had already committed, so the next tick
        # re-detects the same edit and resumes again. That resume commits on
        # top of the stranded commit and reports, and the publication is
        # entered on the head the pull request is standing on -- which is
        # neither end of the run in hand.
        self.seeded(ISSUE, PR, LABEL_VALIDATING)
        self.drift(
            _agent(session_id=world.DEV_SESSION, interrupted=True),
            **world.STRANDS,
        )

        retried = self.drift(world.reported(), **world.RETRY_OVER_STRANDED)

        retried[PUSH_BRANCH].assert_called_once()
        self.assertEqual(self.pull_request.head.sha, world.FIXED_HEAD)
        self.reconcile()
        self.assertEqual(len(self.published_reports()), 1)
