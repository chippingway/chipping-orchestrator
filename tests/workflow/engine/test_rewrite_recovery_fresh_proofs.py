# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""A captured run's publication and settlement proved over the world as it reads right then, not as the tick read it.

A finish recorded its run for the landed head and stopped short of settling
it, so the recovery publishes and settles it with the attempt still standing.
Every read of the issue through the client is a snapshot of it as it then
stands, as GitHub hands one back. The issue's requirements edited behind the
evidence step's last word are hashed over the issue fetched for the
publication's own proof, so nothing is posted and the run is abandoned. The
pull request's branch moved off the head while the settlement re-reads the
report is read by the anchor's own proof of the landing behind it, so the run
is abandoned rather than made current and the route held. And an artifact the
lookup finds edited under its receipt is kept as the refusal it is before the
abandonment is tried, so a comment read that goes unanswered behind it, with
the artifact put back, still ends in the run abandoned -- never settled by
this recovery or the next. Nothing runs again, nothing is pushed, and no
developer is launched.
"""
from __future__ import annotations

import unittest
from copy import copy
from functools import partial
from unittest.mock import patch

from orchestrator.git.base_sync import rewrite_facts
from orchestrator.workflow.engine.rewrite_finish_models import FinishOutcome
from tests.workflow.engine import (
    rewrite_finish_git_support as git_support,
    rewrite_finish_readings as readings,
    rewrite_verification_recovery_support as support,
)
from tests.workflow.interleaving import _RacesPastTheCall

_EDITED_BODY = "Also cover a moved base."


def _hangs(case: support.CapturedRunCase, owner, step: str, nth: int, raced) -> None:
    """Have `raced` made once, just after call number `nth` of `owner`'s `step` answers."""
    races = _RacesPastTheCall(getattr(owner, step), nth, raced)
    case.enterContext(patch.object(owner, step, races))


def _moves_the_branch(case: support.CapturedRunCase) -> None:
    """Point the pull request's branch, on the remote and on GitHub, back at the head the rebase replaced."""
    case._git("update-ref", f"refs/heads/{git_support.BRANCH}", case.anchor, cwd=case._remote)
    case.pull_request.head.sha = case.anchor


def _puts_back_unread(case: support.CapturedRunCase, posted, body: str) -> None:
    """Put `body` back on the comment `posted`, then have the next read of the pinned comment go unanswered once."""
    posted.body = body
    case.gh.pinned_failures.unanswered_once.add(case.issue.number)


class FreshProofRecoveryTest(support.CapturedRunCase, unittest.TestCase):
    """The proofs a captured run is published and settled over read the world afresh, and keep what they read."""

    def setUp(self) -> None:
        support.CapturedRunCase.setUp(self)
        snapshots = patch.object(self.gh, "get_issue", lambda _number: copy(self.issue))
        self.enterContext(snapshots)

    def test_an_edit_before_the_post_posts_nothing(self) -> None:
        # The body is edited right behind the evidence step's last word: the
        # publication's proof hashes the issue fetched for it, refuses the
        # run, and abandons it with nothing posted, routing the head to the
        # fresh reviewer.
        head, captured = self.captures()
        edits = partial(setattr, self.issue, "body", _EDITED_BODY)
        _hangs(self, rewrite_facts, "_reads_the_checkout", 2, edits)

        self.recovers()

        self.assert_abandoned(captured)
        self.assert_recovered(head)
        self.assertEqual(self.posted(captured), [])

    def test_a_branch_moved_while_settling_abandons(self) -> None:
        # The branch is pointed off the head while the settlement re-reads the
        # report: the anchor's proof of the landing behind it refuses the
        # settlement, so the run is abandoned rather than made current, and
        # the route held with nothing announced.
        captured = self.captures()[1]
        arms = partial(_hangs, self, self.gh, "reread_report_location", 1, partial(_moves_the_branch, self))
        _hangs(self, self.gh, support.POST, 1, arms)

        self.recovers()

        self.assert_abandoned(captured)
        self.assertEqual(readings.pinned(self)[readings.KEY_PENDING_PUSH], self.anchor)
        self.assert_unannounced()

    def test_an_edited_artifact_stays_refused(self) -> None:
        # The post lands with its answer lost and is then edited under its
        # receipt. The lookup finds it edited, it is put back, and the
        # comment read for the abandonment goes unanswered once: the refusal
        # was kept before that read, so the run is abandoned all the same and
        # the head routed -- and the next poll settles nothing.
        head = self.lands_a_reviewed_rebase()
        with patch.object(self.gh.report_failures, "lost", {git_support.PR_NUMBER}):
            self.assertEqual(self.finishes(head), FinishOutcome.HELD)
        captured = readings.pinned_records(self)[0]
        thread = self.pull_request.issue_comments
        posted = next(comment for comment in thread if captured.receipt in comment.body)
        restores = partial(_puts_back_unread, self, posted, posted.body)
        _hangs(self, self.gh, support.POST, 1, restores)
        posted.body = f"{posted.body}\nEdited by hand."

        self.recovers()
        self.recovers()

        self.assert_abandoned(captured)
        self.assert_recovered(head)


if __name__ == "__main__":
    unittest.main()
