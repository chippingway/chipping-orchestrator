# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What the approval arc does with each shape a squash can hand it back."""
from __future__ import annotations

import unittest
from unittest.mock import patch

from orchestrator import config
from orchestrator.git.publication import models as _publication
from orchestrator.git.publication.models import _SquashOutcome
from tests.support.fakes import FakePRRef
from tests.workflow.fixtures import REVIEW_APPROVED_MESSAGE, _agent
from tests.workflow.stages.validating import squash_approval_support as _support
from tests.workflow.stages.validating.squash_approval_support import _MeasurementPark, _SquashApprovalFixtureMixin

# The two sentences a notice about somewhere ELSE may not carry: the ordinary
# failure's, which puts the approved commits at HEAD, and the collapse's,
# which sends an operator to the head a record names.
COMMITS_AT_HEAD = "the original commits are still on the branch"

FROM_THE_RECORDED_HEAD = "reachable from the head the record names"


class SquashOnApprovalTest(
    unittest.TestCase,
    _SquashApprovalFixtureMixin,
):
    """Squash approved branches and preserve the approval handoff."""

    def test_lands_in_review_without_re_review(
        self,
    ) -> None:
        # End-to-end: validating approves, squash + force-push runs (mocked
        # to succeed), the squash PR comment is posted, the issue lands in
        # in_review, and the next in_review tick pings HITL WITHOUT
        # spawning the reviewer on the rewritten head.
        gh, issue, pr = self._setup()

        mocks_v = self._run_squash_approval(
            gh,
            issue,
            (True, _support.SQUASHED_SHA, 3, None),
        )

        # Squash helper was called exactly once on the approval path.
        self._assert_squash_handoff(gh, pr, mocks_v)

        # Step 2: simulate the documenting no-change exit (final docs
        # pass found nothing to commit) and run the in_review tick.
        # Approved + mergeable; the ping MUST fire and must NOT re-run
        # the reviewer agent (its run_agent call would otherwise be
        # visible in mocks_r below).
        mocks_r = self._run_review_after_squash(gh, issue, pr)
        # The orchestrator is manual-merge-only: the post-squash head
        # earns a HITL ping for the human to merge by hand. No
        # orchestrator-initiated merge call fires.
        self._assert_ready_ping(gh, mocks_r)

    def test_failure_parks_without_relabel(self) -> None:
        # Push rejected / lease violation / dirty tree all surface as
        # `success=False`. The orchestrator parks awaiting_human, leaves
        # the issue in `validating`, and does NOT seed watermarks (the
        # original commits remain on the branch and a human can decide
        # what to do).
        gh, issue, _pr = self._setup()

        mocks = self._run_squash_approval(
            gh,
            issue,
            (
                False,
                None,
                0,
                "force-push with lease rejected (concurrent update)",
            ),
        )

        # Park happened: awaiting_human flag set, HITL message posted to
        # the issue thread.
        self._assert_squash_parked(gh, mocks)
        # And it says the approved commits are where a human squashing by
        # hand will find them.
        self.assertTrue(any(
            COMMITS_AT_HEAD in body
            for _, body in gh.posted_comments
        ))

    def test_a_held_park_reaches_the_pinned_comment(self) -> None:
        # A hold is not always the adjudication. The gate also holds on a
        # reading nobody could take -- a diff that would not run, a tree it
        # could not prove -- and that one is a PARK: it words its own notice
        # and leaves the flags in memory for whoever ran it. Lost, the issue
        # keeps a frozen candidate with no `awaiting_human` and no
        # `park_reason`, so every later tick runs the reviewer again over work
        # nobody read the size of.
        github, issue = self._setup()[:2]

        self._run_squash_approval(github, issue, _MeasurementPark())

        state = github.pinned_data(_support.APPROVAL_ISSUE)
        self.assertTrue(state[_support.AWAITING_HUMAN])
        self.assertEqual(state[_support.PARK_REASON], _support.PARK_MEASUREMENT_FAILED)
        self.assertNotIn(
            (_support.APPROVAL_ISSUE, _support.LABEL_DOCUMENTING), github.label_history,
        )

    def test_squash_off_preserves_legacy_behavior(self) -> None:
        # Kill switch: with SQUASH_ON_APPROVAL=off nothing is collapsed and no
        # squash notice is posted. The switch itself is the squash owner's --
        # a collapse an earlier tick already made has to be finished whichever
        # way it is set -- so the stage still hands the issue over and acts on
        # the nothing-squashed answer it gets back.
        gh, issue, pr = self._setup()
        # Make pr.head.sha match REVIEWED_SHA -- legacy path: the local
        # HEAD the reviewer saw is what the remote PR points at, since no
        # force-push happened.
        pr.head = FakePRRef(sha=_support.REVIEWED_SHA)

        with patch.object(config, _support.SQUASH_ON_APPROVAL, False):
            mocks = self._run_validating(
                gh,
                issue,
                run_agent=_agent(last_message=REVIEW_APPROVED_MESSAGE),
                head_shas=(_support.REVIEWED_SHA,),
                squash_result=(True, _support.REVIEWED_SHA, 0, None),
            )

        mocks["_squash_and_force_push"].assert_called_once()
        # No squash notice posted.
        for _, body in gh.posted_pr_comments:
            self.assertNotIn(":package: squashed", body)
        # And the legacy approval flow flips to `documenting` (the
        # final-docs hop) regardless of SQUASH_ON_APPROVAL.
        self.assertIn((_support.APPROVAL_ISSUE, _support.LABEL_DOCUMENTING), gh.label_history)

    def test_single_commit_posts_no_notice(self) -> None:
        # The helper returns `squashed_count=0` when there's only one
        # commit on top of base -- nothing to squash. The orchestrator
        # must skip the squash PR comment (the helper returns the same
        # SHA back).
        gh, issue, pr = self._setup()
        pr.head = FakePRRef(sha=_support.REVIEWED_SHA)

        with patch.object(config, _support.SQUASH_ON_APPROVAL, True):
            self._run_validating(
                gh,
                issue,
                run_agent=_agent(last_message=REVIEW_APPROVED_MESSAGE),
                head_shas=(_support.REVIEWED_SHA,),
                # Helper success no-op: nothing to squash.
                squash_result=(True, _support.REVIEWED_SHA, 0, None),
            )

        for _, body in gh.posted_pr_comments:
            self.assertNotIn(":package: squashed", body)
        # Approval still flips to `documenting` (the final-docs hop)
        # even when there's only one commit (so no squash notice).
        self.assertIn((_support.APPROVAL_ISSUE, _support.LABEL_DOCUMENTING), gh.label_history)


class SquashParkNoticeTest(
    unittest.TestCase,
    _SquashApprovalFixtureMixin,
):
    """Which of the four places a failed squash says it left the branch.

    The reading is the squash owner's; the sentence is this stage's. What
    matters here is that no two of them are said in the same words, because
    each sends an operator somewhere different -- to HEAD, to a reflog entry
    the record names, into the branch's own history under later work, or
    nowhere until they have looked for themselves.
    """

    def test_a_retained_collapse_says_so(self) -> None:
        # A failure taken over a collapse this tick could not finish leaves
        # the branch standing on the squash, not on the approved history. An
        # operator told to squash it by hand would be looking for commits that
        # are not at HEAD.
        notice = self._parks_over(
            "the record it left cannot be proved",
            _publication.BRANCH_COLLAPSED,
        )

        self.assertNotIn(COMMITS_AT_HEAD, notice)
        self.assertIn("records a squash it could not finish", notice)

    def test_a_buried_record_is_not_called_collapsed(self) -> None:
        # A branch that grew PAST the recorded head was never rewritten, so
        # the approved commits are in its own history under the work on top of
        # them. The collapse sentence would send an operator to the reflog,
        # straight past the commits they are looking for -- and contradict the
        # refusal it is posted beside.
        notice = self._parks_over(
            "the branch stands on a commit made on top of it",
            _publication.BRANCH_BURIED,
        )

        self.assertNotIn(COMMITS_AT_HEAD, notice)
        self.assertNotIn(FROM_THE_RECORDED_HEAD, notice)
        self.assertIn("under whatever was committed on top of them", notice)

    def test_an_unplaced_failure_says_neither(self) -> None:
        # A failure the squash owner could not place -- a record it cannot
        # read whole, a recorded head no object here answers to -- is none of
        # the others. Worded as one, the notice sends an operator to a HEAD or
        # a reflog entry nothing established.
        notice = self._parks_over(
            "the record of it is not one this build can read",
            _publication.BRANCH_UNKNOWN,
        )

        self.assertNotIn(COMMITS_AT_HEAD, notice)
        self.assertNotIn(FROM_THE_RECORDED_HEAD, notice)
        self.assertIn("nothing here can say where that leaves the branch", notice)

    def _parks_over(self, error: str, standing: str) -> str:
        """The notice one failed squash leaves on the issue thread."""
        gh, issue = self._setup()[:2]

        self._run_squash_approval(
            gh, issue, _SquashOutcome(error=error, standing=standing),
        )

        parked = [body for _, body in gh.posted_comments if "squash" in body]
        self.assertTrue(parked)
        return parked[-1]


if __name__ == "__main__":
    unittest.main()
