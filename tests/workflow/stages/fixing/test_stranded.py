# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Tests for fixing stranded behavior."""

from __future__ import annotations

import unittest

from tests.workflow.stages.fixing import fixing_test_support as support

IssueScenario = support.IssueScenario

ALICE = support.ALICE
AWAITING_HUMAN = support.AWAITING_HUMAN
CONTINUE_WORD = support.CONTINUE_WORD
DEBOUNCE_CONFIG = support.DEBOUNCE_CONFIG
DEBOUNCE_SECONDS = support.DEBOUNCE_SECONDS
DEV_SESSION = support.DEV_SESSION
FakeComment = support.FakeComment
FakeUser = support.FakeUser
IN_REVIEW = support.IN_REVIEW
ISSUE = support.ISSUE
MagicMock = support.MagicMock
NOTHING_TO_DO_MESSAGE = support.NOTHING_TO_DO_MESSAGE
PARK_PUSH_FAILED = support.PARK_PUSH_FAILED
PARK_REASON = support.PARK_REASON
PENDING_FIX_AT = support.PENDING_FIX_AT
PR_LAST_COMMENT_ID = support.PR_LAST_COMMENT_ID
PUSH_BRANCH = support.PUSH_BRANCH
REVIEW_ROUND = support.REVIEW_ROUND
SHA_BEFORE = support.SHA_BEFORE
SHA_SAME = support.SHA_SAME
TRIGGER_ID = support.TRIGGER_ID
VALIDATING = support.VALIDATING
_StrandedFixingFixtureMixin = support._StrandedFixingFixtureMixin
_agent = support._agent
config = support.config
datetime = support.datetime
patch = support.patch
timedelta = support.timedelta
timezone = support.timezone
PR_NUMBER = support.PR_NUMBER

# A pull request somebody else pushed to while the resume was out, and the
# commit a checkout something moved mid-reading is standing on.
MOVED_PR_HEAD = "cafef00d" * 5

# The divergence a case seeds, and the counts of a branch standing exactly
# where its remote is.
AHEAD_BEHIND = "branch_ahead_behind"
IN_SYNC = (0, 0)

# What a dev says when the feedback names nothing to change.
ACKED_MESSAGE = (
    "The branch already satisfies the comment.\n\n"
    "ACK: nothing to fix; 'continue' names no defect"
)

# Every reading that leaves the branch unplaced against its pull request,
# named by the shape it stands for.
UNPROVED_SHAPES = (
    ("remote moved", {AHEAD_BEHIND: (1, 2)}),
    ("loose tree", {AHEAD_BEHIND: (1, 0), "dirty_files": ("AGENTS.md",)}),
    ("unreadable tree", {AHEAD_BEHIND: IN_SYNC, "tree_readable": False}),
    (
        "unreadable divergence",
        {AHEAD_BEHIND: IN_SYNC, "branch_divergence_readable": False},
    ),
    (
        "fetch failed",
        {
            AHEAD_BEHIND: IN_SYNC,
            "authed_fetch_result": MagicMock(returncode=1, stderr="boom"),
        },
    ),
    # The counts said the two agree and the checkout was somewhere else by the
    # time its own head was read: the ground moved between two commands, so
    # the geometry they describe is about a checkout that no longer exists.
    (
        "checkout moved under the count",
        {
            AHEAD_BEHIND: IN_SYNC,
            "fetched_branch_tip": SHA_SAME,
            "head_shas": (SHA_SAME, SHA_SAME, MOVED_PR_HEAD),
        },
    ),
)


class _StrandedResumeMixin(_StrandedFixingFixtureMixin):
    """The one tick every case here is, with a single fact moved.

    Each stranded case asks what a resume does when the dev commits nothing
    and the branch is already carrying work: the debounce the route reads
    before it spawns, the two identical head reads a no-commit run leaves,
    and the dev's answer are the same throughout, so they are named once and
    only what a case is ABOUT is spelled in it.
    """

    def _resumed(
        self,
        gh,
        issue,
        *,
        message: str = NOTHING_TO_DO_MESSAGE,
        **run_options,
    ):
        run_options.setdefault("head_shas", (SHA_SAME, SHA_SAME))
        with patch.object(config, DEBOUNCE_CONFIG, DEBOUNCE_SECONDS):
            return self._run_fixing(
                gh,
                issue,
                run_agent=_agent(
                    session_id=DEV_SESSION, last_message=message,
                ),
                **run_options,
            )

    def _pushes(self, mocks):
        """The seam every one of these cases is decided at."""
        return mocks[PUSH_BRANCH]

    def _acked_scenario(self):
        """A resume the dev was woken for by a human's `continue`."""
        comment = FakeComment(
            id=TRIGGER_ID,
            body=CONTINUE_WORD,
            user=FakeUser(ALICE),
            created_at=datetime.now(timezone.utc) - timedelta(hours=1),
        )
        return IssueScenario(
            *self._seed(pr=self._open_pr(), issue_comments=[comment]),
        )


class StrandedFixRecoveryTest(unittest.TestCase, _StrandedResumeMixin):
    def test_no_commit_with_stranded_fix_publishes_it(self) -> None:
        # The resume produced no new commit, but the clean worktree HEAD
        # is ahead of the remote PR branch: a prior parked run committed
        # a fix that was never pushed. The handler must publish it and
        # flip back to `validating` (bumping the round -- validating
        # route) instead of parking on a question the dev cannot answer.
        gh, issue = self._seed_stranded()

        mocks = self._resumed(
            gh,
            issue,
            message="nothing new to commit; the fix is already on HEAD",
            branch_ahead_behind=(1, 0),
        )

        self._pushes(mocks).assert_called_once()
        pinned_data = gh.pinned_data(ISSUE)
        self.assertFalse(pinned_data.get(AWAITING_HUMAN))
        self.assertEqual(pinned_data.get(REVIEW_ROUND), 3)
        self.assertIn((ISSUE, VALIDATING), gh.label_history)

    def test_unproved_shapes_park_the_question(self) -> None:
        # Every reading the probe cannot take answers "nothing stranded"
        # exactly as an empty branch does, and each of them may be a branch
        # holding a commit the pull request has not got: pushing over one
        # races a head nobody reconciled, and handing the round back
        # presents a pull request that may be short of the fix. So the
        # disposition publishes nothing and parks on the question it cannot
        # answer for itself.
        for shape, run_options in UNPROVED_SHAPES:
            with self.subTest(shape=shape):
                gh, issue = self._seed_stranded()

                mocks = self._resumed(gh, issue, **run_options)

                self._pushes(mocks).assert_not_called()
                self.assertTrue(gh.pinned_data(ISSUE).get(AWAITING_HUMAN))
                self.assertNotIn((ISSUE, VALIDATING), gh.label_history)

    def test_stranded_fix_push_error_parks_transient(self) -> None:
        # The deferred publish reuses the shared push tail, so a failed
        # push lands the standard `push_failed` transient park (which the
        # next tick's silent recovery can retry).
        gh, issue = self._seed_stranded()

        mocks = self._resumed(
            gh, issue, branch_ahead_behind=(1, 0), push_branch=False,
        )

        self._pushes(mocks).assert_called_once()
        pinned_data = gh.pinned_data(ISSUE)
        self.assertTrue(pinned_data.get(AWAITING_HUMAN))
        self.assertEqual(pinned_data.get(PARK_REASON), PARK_PUSH_FAILED)
        self.assertNotIn((ISSUE, VALIDATING), gh.label_history)


class StrandedAckFastPathTest(unittest.TestCase, _StrandedResumeMixin):
    """What the in_review-route ACK may hand back, and what it may not.

    The ack vouches for the FEEDBACK; what the fast path does with it --
    clear the bookmarks, advance the readers, present the pull request as
    needing nothing -- is a claim about the BRANCH. So it takes only the one
    reading that makes that claim: the checkout proved to be standing exactly
    where its publication is.
    """

    def test_ack_stranded_fix_publishes(self) -> None:
        # in_review route (`pending_fix_at` set): the dev ACKs a no-commit
        # resume, but the clean worktree HEAD is strictly ahead of the
        # remote PR branch -- a fix a prior parked run committed that
        # never reached the PR (e.g. a dirty-park whose stray files were
        # later cleaned up). The ACK fast path must stand down: returning
        # to `in_review` would clear the bookmarks and advance the
        # watermarks while the PR head still lacks the fix. The handler
        # publishes the stranded HEAD through the normal push tail and
        # routes to `validating` with the in_review-route round reset.
        scenario = self._acked_scenario()

        mocks = self._resumed(
            scenario.github,
            scenario.issue,
            message=(
                "The branch already satisfies the comment.\n\n"
                "ACK: nothing to fix; the change is already on HEAD"
            ),
            branch_ahead_behind=(1, 0),
        )

        self._pushes(mocks).assert_called_once()
        self.assertNotIn((ISSUE, IN_REVIEW), scenario.github.label_history)
        self.assertIn((ISSUE, VALIDATING), scenario.github.label_history)
        self._pinned_data = scenario.github.pinned_data(ISSUE)
        self.assertFalse(self._pinned_data.get(AWAITING_HUMAN))
        # in_review route: a pushed fix starts a fresh review cycle.
        self.assertEqual(self._pinned_data.get(REVIEW_ROUND), 0)
        self.assertIsNone(self._pinned_data.get(PENDING_FIX_AT))
        # Watermark advanced past the consumed feedback.
        self.assertGreaterEqual(self._pinned_data.get(PR_LAST_COMMENT_ID), TRIGGER_ID)

    def test_an_unproved_branch_stands_the_ack_down(self) -> None:
        # Every shape the probe cannot vouch for is a branch that may be
        # carrying a commit the pull request has not got, and the ack says
        # nothing about the publish state. Returning to `in_review` on one
        # would clear the bookmarks, advance the readers, and present the
        # pull request as complete over a head nobody placed -- so the fast
        # path stands down and the disposition behind it parks on the
        # question instead of answering it.
        for shape, run_options in UNPROVED_SHAPES:
            with self.subTest(shape=shape):
                scenario = self._acked_scenario()

                mocks = self._resumed(
                    scenario.github,
                    scenario.issue,
                    message=ACKED_MESSAGE,
                    **run_options,
                )

                self._pushes(mocks).assert_not_called()
                self.assertNotIn(
                    (ISSUE, IN_REVIEW), scenario.github.label_history,
                )
                self.assertNotIn(
                    (ISSUE, VALIDATING), scenario.github.label_history,
                )
                self.assertTrue(
                    scenario.github.pinned_data(ISSUE).get(AWAITING_HUMAN),
                )

    def test_a_branch_proved_empty_acks_to_in_review(self) -> None:
        # The checkout and its remote agree exactly, so the ack is about a
        # pull request that already carries everything: the bookmarks clear
        # and the ready-ping is re-armed without a push.
        scenario = self._acked_scenario()

        mocks = self._resumed(
            scenario.github,
            scenario.issue,
            message=ACKED_MESSAGE,
            branch_ahead_behind=IN_SYNC,
            # Standing exactly where the remote is: the counts agree AND the
            # checkout's own head reads as the tip they were taken against.
            fetched_branch_tip=SHA_SAME,
        )

        self._pushes(mocks).assert_not_called()
        self.assertIn((ISSUE, IN_REVIEW), scenario.github.label_history)
        self.assertNotIn((ISSUE, VALIDATING), scenario.github.label_history)
        self.assertFalse(scenario.github.pinned_data(ISSUE).get(AWAITING_HUMAN))


class StrandedPublicationRaceTest(unittest.TestCase, _StrandedResumeMixin):
    """A pull request somebody moved between the proof and the push.

    The stranded probe fetches, proves the branch ahead of the remote and not
    behind it, and hands that head on: it is what the push replaces. Left for
    the gate to read afterwards, a head somebody landed in between becomes the
    lease and is force-overwritten by work proved against the head it used to
    be on.
    """

    def test_a_head_moved_after_the_proof_refuses(self) -> None:
        gh, issue = self._seed_stranded()
        gh.get_pr(PR_NUMBER).head.sha = MOVED_PR_HEAD

        mocks = self._resumed(gh, issue, branch_ahead_behind=(1, 0))

        self._pushes(mocks).assert_not_called()
        self.assertNotIn((ISSUE, VALIDATING), gh.label_history)
        self.assertTrue(gh.pinned_data(ISSUE).get(AWAITING_HUMAN))
