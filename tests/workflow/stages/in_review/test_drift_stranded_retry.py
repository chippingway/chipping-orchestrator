# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The same branch under an approved pull request, and the retry that publishes it.

A resume here can leave a commit the pull request never receives -- one parked
for the report it did not write, one a shutdown killed before anything was
recorded -- and the resume behind it commits AGAIN, whether it runs from here
or from the `validating` the stale approval was handed back to. The checkout
is two commits above the pull request by then, and the head that run began at
is the stranded commit rather than anything the pull request carries.

What such a publication replaces is the pull request's own head, so the branch
goes out whole under the report that describes it and the approval earned
against the old requirements is dropped behind it. Leased against the head the
run began at instead, the size gate is entered on a commit the pull request
has never seen and every tick over that branch parks unmeasured.
"""

from __future__ import annotations

import unittest
from types import MappingProxyType

from tests.workflow import drift_reports as world
from tests.workflow.fixtures import LABEL_IN_REVIEW, LABEL_VALIDATING, _agent

ISSUE = 1_795

PR = 17_950

PUSH_BRANCH = "_push_branch"

REVIEW_ROUND = "review_round"

# What a reviewer that ran says: no verdict, so it parks and nothing else runs.
REVIEW_REPLY = "Looked it over."

# The rounds a nearly spent review budget has left, which an edit to the
# requirements must not hand the next reviewer.
SPENT_ROUNDS = 2

# The final-docs handoff the approval left on the head the edit landed on,
# which is all the ready ping asks of a mergeable pull request.
READY_TO_PING = MappingProxyType({
    "docs_checked_sha": world.PUBLISHED_HEAD,
    "docs_verdict": "updated",
})


class InReviewStrandedRetryTest(unittest.TestCase, world._DriftReportMixin):
    def test_a_handed_back_retry_publishes_the_branch(self) -> None:
        # The resume committed and reported nothing, so the commit stayed in
        # the worktree and the stale approval was handed back. The reply
        # resumes the session on `validating`, which commits again and
        # reports: both commits and the report go out, on the fresh budget
        # the edit has already bought.
        self.seeded(
            ISSUE, PR, LABEL_IN_REVIEW,
            review_round=SPENT_ROUNDS, **READY_TO_PING,
        )
        self.drift("fixed the criteria", **world.STRANDS)
        # The hand-back; `InReviewReportDebtTest` is what asserts it.
        self.drift(REVIEW_REPLY, committed=False)
        world.human_reply(self)

        retried = self.drift(world.reported(), **world.RETRY_OVER_STRANDED)
        self.reconcile()

        retried[PUSH_BRANCH].assert_called_once()
        self.assertEqual(len(self.published_reports()), 1)
        self.assertEqual(
            (self.pull_request.head.sha, self.pinned()[REVIEW_ROUND]),
            (world.FIXED_HEAD, 0),
        )

    def test_a_retry_commits_over_what_the_kill_left(self) -> None:
        # The same branch with nothing recorded at all: the shutdown sweep
        # kills a resume that had already committed, so this stage re-detects
        # the same edit and resumes again. That resume commits on top of the
        # stranded commit and reports, and both go out from here before the
        # approval the edit made stale is handed back.
        self.seeded(ISSUE, PR, LABEL_IN_REVIEW, **READY_TO_PING)
        self.drift(
            _agent(session_id=world.DEV_SESSION, interrupted=True),
            **world.STRANDS,
        )

        retried = self.drift(world.reported(), **world.RETRY_OVER_STRANDED)
        self.reconcile()

        retried[PUSH_BRANCH].assert_called_once()
        self.assertEqual(len(self.published_reports()), 1)
        self.assertEqual(
            (self.pull_request.head.sha, self.github.label_history[-1:]),
            (world.FIXED_HEAD, [(ISSUE, LABEL_VALIDATING)]),
        )
