# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What the approval arc does with each shape a squash can hand it back."""
from __future__ import annotations

import unittest
from unittest.mock import patch

from orchestrator import config
from orchestrator.git.publication import models as _publication
from orchestrator.github.pinned_state import MAX_PINNED_BODY, pinned_state_body
from orchestrator.workflow.engine import report_record_values as _record_values
from orchestrator.workflow.stages.validating import review_verdicts as _verdicts
from tests.support.fakes import FakeComment, FakeUser
from tests.workflow.fixtures import _agent, approved_on
from tests.workflow.stages.validating import squash_approval_support as _support
from tests.workflow.stages.validating.squash_approval_support import (
    _CollapseWorldMixin,
    _MeasurementPark,
    _RefusesTheCollapse,
    _SquashApprovalFixtureMixin,
)

# The two sentences a notice about somewhere ELSE may not carry: the ordinary
# failure's, which puts the approved commits at HEAD, and the collapse's,
# which sends an operator to the head a record names.
COMMITS_AT_HEAD = "the original commits are still on the branch"

FROM_THE_RECORDED_HEAD = "reachable from the head the record names"

# The notice a failed squash parks with, the operator notes that fill a
# comment, and the approval whose squash is recorded, whose subject a later
# round reviews with feedback long enough that keeping it or not decides room.
SQUASH_FAILED_NOTICE = "squash-on-approval failed"

NOTES = "operator_notes"

APPROVED_SUBJECT = "review_approved_subject"

_LATER_FEEDBACK = "A later round's feedback. " * 100

# An orchestrator comment numbered near the widest id a record spells, so the
# park notice minted after it, and its ledger entry, are as wide as the
# measurement a park is taken under reserves: what decides room is then the
# verdict the park keeps, not the slack a narrow id leaves.
_WIDE_COMMENT = FakeComment(
    id=_record_values.MAX_RECORDED_NUMBER - 1_000, body="picking this up", user=FakeUser("orchestrator"),
)


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

    def test_the_squash_is_handed_both_numbers(self) -> None:
        # The subject the squash publishes is normalized against the pull
        # request AND the tracked issue, and this road is where both of them
        # reach it: the gate carries the issue whose own reference comes off
        # the line, and `pr_number` is the reviewer run's, which is the one
        # the line ends in. Built over any other issue, the rewrite would
        # strip a number this branch never carried and keep the one it did.
        gh, issue = self._setup()[:2]

        mocks = self._run_squash_approval(
            gh, issue, (True, _support.SQUASHED_SHA, 3, None),
        )

        squashed = mocks[_support.SQUASH_SEAM].call_args.args
        self.assertEqual(squashed[0].issue.number, _support.APPROVAL_ISSUE)
        self.assertEqual(squashed[-1], _support.APPROVAL_PR)

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
        pr.head.sha = _support.REVIEWED_SHA

        with patch.object(config, _support.SQUASH_ON_APPROVAL, False):
            mocks = self._run_validating(
                gh,
                issue,
                run_agent=_agent(last_message=approved_on(_support.REVIEWED_SHA)),
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

    def test_a_collapse_of_nothing_posts_no_notice(self) -> None:
        # The notice says how much history the force-push replaced, so the two
        # counts that replaced none of it owe nothing: 0 is the branch this
        # call left alone, and 1 is the one commit rewritten for its subject
        # -- one commit on the branch before and one after, on both. The
        # approval still flips to `documenting` for the final-docs hop either
        # way.
        for squashed_count in (0, 1):
            with self.subTest(squashed_count=squashed_count):
                gh, issue, pr = self._setup()
                pr.head.sha = _support.REVIEWED_SHA

                with patch.object(config, _support.SQUASH_ON_APPROVAL, True):
                    self._run_validating(
                        gh,
                        issue,
                        run_agent=_agent(last_message=approved_on(_support.REVIEWED_SHA)),
                        head_shas=(_support.REVIEWED_SHA,),
                        squash_result=(
                            True, _support.REVIEWED_SHA, squashed_count, None,
                        ),
                    )

                for _, body in gh.posted_pr_comments:
                    self.assertNotIn(":package: squashed", body)
                self.assertIn(
                    (_support.APPROVAL_ISSUE, _support.LABEL_DOCUMENTING),
                    gh.label_history,
                )


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
            gh, issue, _publication._SquashOutcome(error=error, standing=standing),
        )

        parked = [body for _, body in gh.posted_comments if "squash" in body]
        self.assertTrue(parked)
        return parked[-1]


class SquashParkRoomTest(
    unittest.TestCase,
    _SquashApprovalFixtureMixin,
    _CollapseWorldMixin,
):
    """A failed squash's park is measured as the write it lands in, before its notice is posted."""

    def test_a_kept_verdict_is_measured_with_the_park(self) -> None:
        # The recovery of a squash an earlier tick did not finish holds no
        # verdict, so the park its failed squash takes keeps a later round's
        # verdict pinned beside it -- and is measured keeping it. With room, the
        # park lands and adds what it adds; one character short of that, nothing
        # is posted on the thread or written, rather than a notice announcing a
        # park whose write then does not fit.
        added, landed = self._parks_beside_a_later_verdict()
        self.assertEqual(landed, (True, _support.PARK_SQUASH_FAILED, True))

        left = self._parks_beside_a_later_verdict(spare=added - 1)

        self.assertEqual(left[1], (False, None, True))

    def _parks_beside_a_later_verdict(self, spare=None) -> tuple:
        """What recovering a squash that fails beside a later round's verdict adds to the comment, and leaves.

        Filled first with operator notes to `spare` characters short of its
        ceiling, where given. The characters the tick added, beside whether a
        squash-failure notice was posted, the park reason, and whether the
        later verdict still waits.
        """
        github, issue, pr = self._setup()
        pr.issue_comments.append(_WIDE_COMMENT)
        self._records_a_collapse(github)
        later = _verdicts.ReturnedVerdict(
            1, _verdicts.CHANGES_REQUESTED, github.read_pinned_state(issue).get(APPROVED_SUBJECT), _LATER_FEEDBACK,
        )
        self._pins(github, _verdicts.RETURNED_VERDICT, later.recorded())
        if spare is not None:
            self._fills_to(github, spare)
        before = len(pinned_state_body(github.pinned_data(_support.APPROVAL_ISSUE)))

        self._run_squash_approval(github, issue, _RefusesTheCollapse())

        return (
            len(pinned_state_body(github.pinned_data(_support.APPROVAL_ISSUE))) - before,
            self._left(github, later),
        )

    def _left(self, github, later) -> tuple:
        """Whether a squash-failure notice was posted, the park reason, and whether `later` still waits."""
        pinned = github.pinned_data(_support.APPROVAL_ISSUE)
        notices = [
            body for _, body in github.posted_comments if SQUASH_FAILED_NOTICE in body
        ]
        waiting = _verdicts.ReturnedVerdict.read(pinned.get(_verdicts.RETURNED_VERDICT))
        return (bool(notices), pinned.get(_support.PARK_REASON), waiting == later)

    def _fills_to(self, github, spare: int) -> None:
        """Fill the pinned comment with operator notes to `spare` characters short of its ceiling."""
        self._pins(github, NOTES, "")
        body = pinned_state_body(github.pinned_data(_support.APPROVAL_ISSUE))
        room = MAX_PINNED_BODY - len(body) - spare
        self._pins(github, NOTES, "x" * room)


class SquashSubjectReferenceTest(
    unittest.TestCase,
    _SquashApprovalFixtureMixin,
    _CollapseWorldMixin,
):
    """The pull request each road hands the squash its subject references.

    Whether the subject spells it is the squash owner's to decide. What the
    stage owes is the number, from whichever road holds one: the reviewer run
    on an approval, the pinned comment on a recovery.
    """

    def test_both_roads_hand_the_pull_request_in(self) -> None:
        for recovered in (False, True):
            with self.subTest(recovered=recovered):
                github, issue = self._approved_issue()
                if recovered:
                    self._records_a_collapse(github)

                mocks = self._lands_a_collapse(github, issue)

                self.assertEqual(
                    mocks[_support.SQUASH_SEAM].call_args.args[-1],
                    _support.APPROVAL_PR,
                )

    def test_a_damaged_number_references_nothing(self) -> None:
        # Read as an identity first: a value that is not a whole positive
        # number would otherwise be spelled into a force-pushed subject as a
        # reference no pull request answers to.
        github, issue = self._approved_issue()
        self._records_a_collapse(github)
        self._pins(github, _support.PR_NUMBER_KEY, True)

        mocks = self._run_squash_approval(github, issue, _RefusesTheCollapse())

        self.assertIsNone(mocks[_support.SQUASH_SEAM].call_args.args[-1])


if __name__ == "__main__":
    unittest.main()
