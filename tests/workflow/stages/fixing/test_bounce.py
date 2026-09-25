# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What the no-feedback bounce does about a commit nobody published.

The validating route reaches that exit carrying an unanswered reviewer round:
the feedback that started it is a comment the orchestrator authored, so every
rescan filters it out and no later tick re-runs the dev on it. A commit an
earlier round left in the worktree -- a run whose outcome the live-pause guard
discarded, a run killed before its push -- therefore has to be published here
or the reviewer re-reads a head that is missing it.

The relabel is only as bold as the probe it stands on, and the probe answers
in words rather than yes-or-nothing: a branch PROVED to be carrying nothing
unpublished is the one reading that lets the bounce land. Each refusal beside
it -- a tree nobody could read, a tree holding loose work, a fetch that did not
return, a divergence git would not count, a remote that has moved -- may be a
branch holding the very commit this exit is the last tick to publish, so the
bounce holds and says so once instead of handing the reviewer a head nobody
placed.
"""

from __future__ import annotations

import unittest
from types import MappingProxyType

from orchestrator.git.verification.status import _WorktreeStatus
from tests.workflow.stages.fixing import fixing_test_support as support

AHEAD_BEHIND = "branch_ahead_behind"
AUTHED_FETCH = support.AUTHED_FETCH
AUTHED_FETCH_RESULT = "authed_fetch_result"
AWAITING_HUMAN = support.AWAITING_HUMAN
DIRTY_FILES = "dirty_files"
DIVERGENCE_READABLE = "branch_divergence_readable"
FETCHED_TIP = "fetched_branch_tip"
HEAD_SHAS = "head_shas"
TREE_STATES = "tree_states"
ALICE = support.ALICE
FakeComment = support.FakeComment
FakeUser = support.FakeUser
ISSUE = support.ISSUE
LAST_ACTION_COMMENT_ID = support.LAST_ACTION_COMMENT_ID
PARK_REASON = support.PARK_REASON
TREE_READABLE = "tree_readable"
MagicMock = support.MagicMock
datetime = support.datetime
timedelta = support.timedelta
timezone = support.timezone
PENDING_FIX_REVIEWER_COMMENT_ID = support.PENDING_FIX_REVIEWER_COMMENT_ID
PUSH_BRANCH = support.PUSH_BRANCH
REVIEW_ROUND = support.REVIEW_ROUND
RUN_AGENT = support.RUN_AGENT
TEMP_ROOT = support.TEMP_ROOT
VALIDATING = support.VALIDATING
_StrandedFixingFixtureMixin = support._StrandedFixingFixtureMixin

# The round the fixture seeds, and the one a published fix moves it to.
SEEDED_ROUND = 2
SPENT_ROUND = 3

# What a bounce held over a branch nobody could place files itself under, and
# a phrase of its notice no other park on this issue writes.
UNPROVED_PARK_REASON = "stranded_unproved"
UNPROVED_NOTICE_MARK = "cannot be handed back for review"

# What a human writes while the branch reading is out on the network, which is
# after the rescan that found nothing has already been taken, and the id it
# lands on: above every watermark the tick opened with, and one below the
# notice the park posts behind it.
LATE_GUIDANCE = "one more thing before this goes back to review"
LATE_COMMENT_ID = support.REVIEWER_FEEDBACK_ID + 2


# A checkout that is not on disk at all: a terminal cleanup ran, or the
# orchestrator moved host between the commit and this tick.
ABSENT_WORKTREE = TEMP_ROOT / "orchestrator-test-fixing-absent"

# What each probe refusal is seeded with, named by the shape it stands for,
# and the clause the notice each earns has to carry: the refusals are what an
# operator acts on, and "could not be established" names none of them.
# The counts a branch standing exactly where its remote is answers with, one
# carrying a commit the pull request has not got, and one whose remote has
# moved past it.
IN_SYNC = (0, 0)
STRANDED = (1, 0)
MOVED_REMOTE = (1, 2)

# The commit a checkout in sync with its publication is standing on, and the
# one something moved it onto between the count and the read of its own head.
LEVEL_HEAD = support.PR_HEAD_SHA
MOVED_CHECKOUT_HEAD = "cafef00d" * 5

# The world a branch standing exactly where its publication is answers with:
# the counts agree, and the checkout's own head IS the tip they were taken
# against.
LEVEL = MappingProxyType({
    AHEAD_BEHIND: IN_SYNC,
    FETCHED_TIP: LEVEL_HEAD,
    HEAD_SHAS: (LEVEL_HEAD,),
})

# A checkout that picks up loose work between the reading that opens the
# placement and the one that re-proves it: the fetch and the count are network
# and subprocess time, and nothing about them moves HEAD.
DIRTIED_MID_READING = (
    _WorktreeStatus(readable=True, paths=()),
    _WorktreeStatus(readable=True, paths=("stray.py",)),
)

UNPROVED_SHAPES = (
    (
        "loose tree",
        {AHEAD_BEHIND: STRANDED, DIRTY_FILES: ("AGENTS.md",)},
        "carrying work nothing has committed",
    ),
    (
        "unreadable tree",
        {AHEAD_BEHIND: STRANDED, TREE_READABLE: False},
        "could not read the state of the checkout",
    ),
    ("remote moved", {AHEAD_BEHIND: MOVED_REMOTE}, "commits this checkout has not"),
    (
        "unreadable divergence",
        {AHEAD_BEHIND: STRANDED, DIVERGENCE_READABLE: False},
        "would not say how far the checkout stands",
    ),
    (
        "fetch failed",
        {
            AHEAD_BEHIND: STRANDED,
            AUTHED_FETCH_RESULT: MagicMock(returncode=1, stderr="boom"),
        },
        "could not be fetched",
    ),
    (
        "checkout moved under the count",
        {**LEVEL, HEAD_SHAS: (MOVED_CHECKOUT_HEAD,)},
        "moved while it was being read",
    ),
    (
        "tree dirtied under the count",
        {**LEVEL, TREE_STATES: DIRTIED_MID_READING},
        "carrying work nothing has committed",
    ),
)


class NoFeedbackBounceTest(unittest.TestCase, _StrandedFixingFixtureMixin):

    def test_bounce_publishes_the_stranded_commit(self) -> None:
        # The clean worktree HEAD is strictly ahead of the remote PR branch --
        # the fix a dev run committed under a live `paused` and never got to
        # push. The bounce publishes it and counts the reviewer round it
        # spends, so the head the reviewer reads next tick carries the fix.
        gh, issue = self._seed_stranded_bounce()

        mocks = self._run_stranded_bounce(
            gh, issue, TEMP_ROOT, branch_ahead_behind=STRANDED,
        )

        # No agent ran: this tick republishes what an earlier one committed.
        mocks[RUN_AGENT].assert_not_called()
        mocks[PUSH_BRANCH].assert_called_once()
        self._assert_bounced(gh, round_n=SPENT_ROUND)

    def test_missing_worktree_bounces_unprobed(self) -> None:
        # Nothing on disk to publish from. The probe is left armed to prove
        # the handler gates on the checkout's existence before spending a
        # fetch on a path that is not there.
        gh, issue = self._seed_stranded_bounce()

        mocks = self._run_stranded_bounce(
            gh, issue, ABSENT_WORKTREE, branch_ahead_behind=STRANDED,
        )

        mocks[AUTHED_FETCH].assert_not_called()
        mocks[PUSH_BRANCH].assert_not_called()
        self._assert_bounced(gh, round_n=SEEDED_ROUND)

    def test_a_proved_empty_branch_bounces(self) -> None:
        # The checkout and its remote agree exactly, so there is nothing this
        # exit could publish and the reviewer may have the head as it stands.
        gh, issue = self._seed_stranded_bounce()

        mocks = self._run_stranded_bounce(gh, issue, TEMP_ROOT, **LEVEL)

        mocks[PUSH_BRANCH].assert_not_called()
        self._assert_bounced(gh, round_n=SEEDED_ROUND)

    def test_failed_push_counts_no_round(self) -> None:
        # The push was attempted and refused, so the commit is still local:
        # counting the round would spend one on a head the reviewer cannot
        # see. The bounce itself stands and a later push carries the commit.
        gh, issue = self._seed_stranded_bounce()

        mocks = self._run_stranded_bounce(
            gh,
            issue,
            TEMP_ROOT,
            branch_ahead_behind=STRANDED,
            push_branch=False,
        )

        mocks[PUSH_BRANCH].assert_called_once()
        self._assert_bounced(gh, round_n=SEEDED_ROUND)

    def _assert_bounced(self, gh, *, round_n: int) -> None:
        """A landed bounce: bookmarks dropped, back to `validating`."""
        pinned_data = gh.pinned_data(ISSUE)
        self.assertEqual(pinned_data.get(REVIEW_ROUND), round_n)
        self.assertIsNone(pinned_data.get(PENDING_FIX_REVIEWER_COMMENT_ID))
        self.assertIn((ISSUE, VALIDATING), gh.label_history)


class _ReplyLandingUnderTheProbe:
    """A fetch that puts a human reply on the thread while it is out.

    The one seam that stands between the rescan and the park, which is the
    whole window this race lives in. The id puts it above every watermark this
    tick opened with and below the notice the park mints behind it -- exactly
    the ordering that lets an unbounded stamp cross a comment nobody read.
    """

    def __init__(self, issue) -> None:
        self._issue = issue

    def __call__(self, *_args, **_kwargs):
        self._issue.comments.append(FakeComment(
            id=LATE_COMMENT_ID,
            body=LATE_GUIDANCE,
            user=FakeUser(ALICE),
            created_at=datetime.now(timezone.utc) - timedelta(hours=1),
        ))
        return MagicMock(returncode=0, stdout="", stderr="")


class UnprovedBranchHoldTest(unittest.TestCase, _StrandedFixingFixtureMixin):
    """The bounce a reading nobody could take does not get to make.

    Every refusal the probe makes reads exactly like an empty branch, and each
    of them may be a checkout holding the commit this exit is the last tick to
    publish. So the relabel waits for a reading rather than for the absence of
    one, and the wait is announced -- this is the last road of the tick, so
    nothing behind it would ever say so.

    Waiting on a READING rather than on a person is what the park means here,
    so a later quiet poll takes it again: the refusals include conditions no
    human touches, and a fetch that comes back is the whole of the repair.
    """

    def test_unproved_shapes_hold_and_say_why(self) -> None:
        # Nothing is spent, nothing is cleared, no label moves, and the
        # notice names the reading that refused rather than leaving an
        # operator to guess which of five it was.
        for shape, run_options, detail in UNPROVED_SHAPES:
            with self.subTest(shape=shape):
                gh, mocks = self._held_bounce(**run_options)

                mocks[PUSH_BRANCH].assert_not_called()
                mocks[RUN_AGENT].assert_not_called()
                self._assert_held(gh, detail)

    def test_a_standing_park_gets_no_second_notice(self) -> None:
        # The reading is taken again on every quiet poll, so a condition that
        # keeps refusing reaches this road repeatedly: announced each time it
        # would bury its own first notice under a thread of identical ones.
        gh, _ = self._held_bounce(branch_ahead_behind=MOVED_REMOTE)

        mocks = self._run_stranded_bounce(
            gh, gh.get_issue(ISSUE), TEMP_ROOT,
            branch_ahead_behind=MOVED_REMOTE,
        )

        mocks[AUTHED_FETCH].assert_called_once()
        self.assertEqual(self._notices(gh), 1)
        self.assertNotIn((ISSUE, VALIDATING), gh.label_history)

    def test_a_reading_that_returns_bounces(self) -> None:
        # The park waits on a reading, not on a person: a poll that can take
        # the reading publishes what it places and hands the round back, with
        # no reply, no agent run, and exactly one handoff. Without that the
        # issue would sit on a fetch that failed once until somebody wrote.
        gh, _ = self._held_bounce(
            branch_ahead_behind=STRANDED,
            authed_fetch_result=MagicMock(returncode=1, stderr="boom"),
        )

        mocks = self._run_stranded_bounce(
            gh, gh.get_issue(ISSUE), TEMP_ROOT, branch_ahead_behind=STRANDED,
        )

        mocks[RUN_AGENT].assert_not_called()
        mocks[PUSH_BRANCH].assert_called_once()
        self.assertEqual(self._notices(gh), 1)
        pinned_data = gh.pinned_data(ISSUE)
        self.assertFalse(pinned_data.get(AWAITING_HUMAN))
        self.assertIsNone(pinned_data.get(PARK_REASON))
        self.assertEqual(pinned_data.get(REVIEW_ROUND), SPENT_ROUND)
        self.assertIsNone(pinned_data.get(PENDING_FIX_REVIEWER_COMMENT_ID))
        self.assertEqual(
            [entry for entry in gh.label_history if entry[0] == ISSUE],
            [(ISSUE, VALIDATING)],
        )

    def test_a_comment_landing_mid_probe_stays_unread(self) -> None:
        # The rescan is taken at the top of the tick and placing the branch is
        # a network call, so a human writing in that window wrote something
        # this tick never looked at -- numbered BELOW the notice posted after
        # it. Carried to the thread's tip, the park watermark would record
        # their comment as delivered and the next quiet poll would place the
        # branch, bounce, and hand the reviewer a head over guidance nobody
        # ever answered. The bounded walk stops at their comment instead, so
        # the poll after this one resumes the developer on it.
        gh, issue = self._seed_stranded_bounce()

        self._run_stranded_bounce(
            gh, issue, TEMP_ROOT,
            branch_ahead_behind=MOVED_REMOTE,
            authed_fetch_result=_ReplyLandingUnderTheProbe(issue),
        )

        landed = next(
            comment for comment in issue.comments
            if comment.body == LATE_GUIDANCE
        )
        # The notice really did land above it, which is the ordering the
        # unbounded stamp would have crossed.
        self.assertGreater(issue.comments[-1].id, landed.id)
        # An unset mark has crossed nothing, which the bounded walk answers
        # when it cannot vouch for a boundary at all.
        crossed = gh.pinned_data(ISSUE).get(LAST_ACTION_COMMENT_ID) or 0
        self.assertLess(crossed, landed.id)
        resumed = self._run_stranded_bounce(
            gh, gh.get_issue(ISSUE), TEMP_ROOT,
            branch_ahead_behind=MOVED_REMOTE,
        )
        resumed[RUN_AGENT].assert_called_once()

    def _held_bounce(self, **run_options):
        """One bounce over a branch the probe would not place."""
        gh, issue = self._seed_stranded_bounce()
        return gh, self._run_stranded_bounce(
            gh, issue, TEMP_ROOT, **run_options,
        )

    def _notices(self, gh) -> int:
        """How many times this hold has announced itself on the thread."""
        return len([
            body for _, body in gh.posted_comments
            if UNPROVED_NOTICE_MARK in body
        ])

    def _assert_held(self, gh, detail: str) -> None:
        """A bounce that did not happen, under a notice naming the refusal."""
        pinned_data = gh.pinned_data(ISSUE)
        self.assertEqual(pinned_data.get(REVIEW_ROUND), SEEDED_ROUND)
        self.assertEqual(
            pinned_data.get(PENDING_FIX_REVIEWER_COMMENT_ID),
            support.REVIEWER_FEEDBACK_ID,
        )
        self.assertTrue(pinned_data.get(AWAITING_HUMAN))
        self.assertEqual(pinned_data.get(PARK_REASON), UNPROVED_PARK_REASON)
        self.assertNotIn((ISSUE, VALIDATING), gh.label_history)
        self.assertIn(
            detail,
            "\n".join(body for _, body in gh.posted_comments),
        )


if __name__ == "__main__":
    unittest.main()
