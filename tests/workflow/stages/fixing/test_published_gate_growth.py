# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""A pull request grown one fix at a time, round after round.

What one round on its own cannot say. Every fix is measured against what the
pull request COMES TO, so a change arriving in pieces meets the ceiling the
same way one arriving at once does: rounds at or under it publish and hand the
issue back for another review, and the first round whose cumulative reading
passes it is held with the remote standing exactly where the last landed push
left it.

The rounds before that one are the point. A landed push leaves a receipt
naming its commit and retires the generation it was measured under, and each
of those names ONE commit -- so the next fix is a candidate nobody has ruled
on, measured afresh from the base the remote names rather than from the head
the round before it published.
"""
from __future__ import annotations

import unittest

from orchestrator.workflow.engine import (
    report_delivery_state as _delivery_state,
)
from tests.workflow.stages.fixing import (
    fixing_test_support as fixing,
    published_gate_support as support,
)

AT_THE_CEILING = support.AT_THE_CEILING
CEILING = support.CEILING
COUNT_ADDED_LINES = support.COUNT_ADDED_LINES
FrozenCommit = support.FrozenCommit
LABEL_DECOMPOSING = support.LABEL_DECOMPOSING
LEASE = support.LEASE
MAX_ADDED_LINES = support.MAX_ADDED_LINES
MEASURED_BASE_SHA = support.MEASURED_BASE_SHA
PAST_THE_CEILING = support.PAST_THE_CEILING
REVISION = support.REVISION
UNDER_THE_CEILING = support.UNDER_THE_CEILING

FakeComment = fixing.FakeComment
FakeLabel = fixing.FakeLabel
FakeUser = fixing.FakeUser
FIXING = fixing.FIXING
ISSUE = fixing.ISSUE
PR_HEAD_SHA = fixing.PR_HEAD_SHA
PR_LAST_COMMENT_ID = fixing.PR_LAST_COMMENT_ID
PR_NUMBER = fixing.PR_NUMBER
PUSH_BRANCH = fixing.PUSH_BRANCH
REVIEW_ROUND = fixing.REVIEW_ROUND
VALIDATING = fixing.VALIDATING
config = fixing.config
patch = fixing.patch

# The commit each successive round leaves the checkout on.
FIX_COMMITS = support.GROWN_CANDIDATES

# The reviewer's next round of feedback, one comment per fix past the first.
# The rescan reads forward from the watermark the round before it consumed, so
# each id sits above the one it follows -- and clear of the report every round
# publishes, since a reviewer comment sharing an id with one of ours is read
# as ours and never reaches the next prompt at all.
NEXT_FEEDBACK_ID = fixing.CONCURRENT_COMMENT_ID

# How far apart those ids sit. Every landed round publishes its report onto the
# pull request, and the double numbers that comment straight above the highest
# id on the thread -- so consecutive reviewer ids would collide with one, and a
# reviewer comment carrying an id of ours is filtered out of the very next
# prompt as one of ours.
ROUND_STRIDE = 10

# What the pull request comes to at each round of the longest chain here: two
# fixes it may still carry -- the second landing exactly on the configured
# value -- and one that takes it past.
GROWN_PAST_THE_CEILING = (UNDER_THE_CEILING, AT_THE_CEILING, PAST_THE_CEILING)


class _GrownPullRequestMixin(support._SizeGateFixtureMixin):
    """Successive fix rounds on one open pull request."""

    def _grown(self, totals):
        """Run one fix round per total, and report what each of them did.

        `totals` is what the pull request comes to WITH that round's commit in
        it, which is the number the gate reads -- not the lines the round's
        own fix added. The world moves between rounds the way production moves
        it: a landed push puts its commit on the pull request, the reviewer
        reads that head and asks for another change, and the issue comes back
        to `fixing` carrying the comment.
        """
        scenario = self._seed_fix_round()
        rounds = []
        for index, total in enumerate(totals):
            if index:
                self._reviewer_asks_again(scenario, index)
            rounds.append(self._fix_round(scenario, index, total))
        return scenario, rounds

    def _fix_round(self, scenario, index, total):
        """One whole fixing tick, from the head the pull request stands on.

        That head is what the round begins at, because a fix round opens with
        the branch in sync with its publication -- the reviewer has just read
        it -- and it is what this round hands the gate as the head its push
        replaces. A push that lands moves the pull request onto the commit it
        published, which is where the round after this one begins.
        """
        pull_request = scenario.github.get_pr(PR_NUMBER)
        candidate = FIX_COMMITS[index]
        with patch.object(config, MAX_ADDED_LINES, CEILING):
            mocks = self._run_fix_round(
                scenario,
                head_shas=(pull_request.head.sha, candidate),
                candidate_commit=FrozenCommit(sha=candidate),
                added_lines=total,
            )
        if mocks[PUSH_BRANCH].called:
            pull_request.head.sha = candidate
        return mocks

    def _reviewer_asks_again(self, scenario, index):
        """The relabel and the comment that open the next fix round.

        The reviewer read the head the round before published and asked for
        another change, which is a `validating` tick ending on the `fixing`
        label. Written onto the issue rather than through the client, so the
        label history this scenario reads is the fixing stage's own.
        """
        scenario.issue.labels = [FakeLabel(FIXING)]
        scenario.issue.comments.append(FakeComment(
            id=NEXT_FEEDBACK_ID + index * ROUND_STRIDE,
            body=fixing.FIX_FEEDBACK,
            user=FakeUser(fixing.ALICE),
            created_at=fixing.datetime.now(fixing.timezone.utc)
            - fixing.timedelta(hours=1),
        ))

    def _measured_pairs(self, rounds):
        """The base and candidate every round was counted over, in order."""
        return [
            tuple(mocks[COUNT_ADDED_LINES].call_args.args[1:])
            for mocks in rounds
        ]

    def _handed_on(self, landed):
        """The labels a chain of landed rounds and one held round writes."""
        history = [(ISSUE, VALIDATING) for _fix in landed]
        history.append((ISSUE, LABEL_DECOMPOSING))
        return history


class GrowingPullRequestTest(unittest.TestCase, _GrownPullRequestMixin):
    """A branch that crosses the ceiling in pieces is held at the crossing."""

    def test_the_round_that_crosses_is_held(self) -> None:
        # One fix past the line and several, because what the gate reads is
        # the same either way: the whole pull request. Nothing is pushed, the
        # remote is left standing on the last fix that was allowed -- the
        # second chain ends on one exactly at the ceiling -- and the issue
        # goes to the adjudication instead of back to the reviewer.
        for landed in (
            (UNDER_THE_CEILING,),
            (UNDER_THE_CEILING, AT_THE_CEILING),
        ):
            with self.subTest(landed=len(landed)):
                scenario, rounds = self._grown((*landed, PAST_THE_CEILING))

                self._assert_unpushed(rounds[-1])
                self.assertEqual(
                    scenario.github.get_pr(PR_NUMBER).head.sha,
                    FIX_COMMITS[len(landed) - 1],
                )
                self.assertEqual(
                    scenario.github.label_history, self._handed_on(landed),
                )

    def test_a_landed_round_measures_the_next(self) -> None:
        # The receipt a landed push writes names ONE commit, so it settles the
        # question for that commit and for nothing committed on top of it.
        # Read as "this branch is published", the next fix would join the pull
        # request unmeasured -- which is the way past the ceiling a cumulative
        # count exists to close. Each round publishes its own commit, leased
        # to the head the round before it left the pull request on.
        _scenario, rounds = self._grown((UNDER_THE_CEILING, AT_THE_CEILING))

        for index, mocks in enumerate(rounds):
            with self.subTest(round=index):
                mocks[COUNT_ADDED_LINES].assert_called_once()
                pushed = self._assert_pushed_once(mocks)
                self.assertEqual(pushed.kwargs[REVISION], FIX_COMMITS[index])
                self.assertEqual(
                    pushed.kwargs[LEASE],
                    FIX_COMMITS[index - 1] if index else PR_HEAD_SHA,
                )


class HeldAfterSeveralFixesTest(unittest.TestCase, _GrownPullRequestMixin):
    """What the round that took a grown pull request past the ceiling left."""

    def setUp(self) -> None:
        scenario, rounds = self._grown(GROWN_PAST_THE_CEILING)
        self.scenario = scenario
        self.rounds = rounds

    def test_every_round_measures_the_frozen_base(self) -> None:
        # The base is what the REMOTE says the pull request is cut from, and
        # it stays that whatever this branch has published since. Re-frozen
        # from the head the round before put on the pull request, every
        # reading would be one fix's own diff and the ceiling would never be
        # reached however far the change grew.
        self.assertEqual(self._measured_pairs(self.rounds), [
            (MEASURED_BASE_SHA, commit)
            for commit in FIX_COMMITS[:len(self.rounds)]
        ])

    def test_the_hold_records_the_whole_change(self) -> None:
        # The number the adjudication is handed is the whole pull request
        # rather than the fix that crossed the line, and the pair and the
        # publication beside it are what a settled verdict republishes from --
        # none of them re-derivable once the label has left this stage.
        pinned = self._pinned(self.scenario)

        self.assertEqual(pinned[support.KEY_ADDITIONS], PAST_THE_CEILING)
        self.assertEqual(pinned[support.KEY_BASE_SHA], MEASURED_BASE_SHA)
        self.assertEqual(pinned[support.KEY_CANDIDATE_SHA], FIX_COMMITS[2])
        self.assertEqual(pinned[support.KEY_PUBLISHED_SHA], FIX_COMMITS[1])
        self.assertEqual(pinned[support.KEY_SOURCE_STAGE], FIXING)

    def test_the_receipt_names_what_was_published(self) -> None:
        # A hold publishes nothing, so the last push this branch made is still
        # the last push it made. Moved on to the held candidate, the tick that
        # settles the adjudication would read a commit the pull request has
        # never had as one it already carries and skip the push that puts it
        # there.
        self.assertEqual(
            self._pinned(self.scenario)[support.KEY_RECEIPT_SHA],
            FIX_COMMITS[1],
        )

    def test_the_hold_holds_what_its_report_owes(self) -> None:
        # The round that crossed the line wrote its report, and a report the
        # pull request has not got may not leave the feedback it answers
        # recorded as read or the reviewer round it lands on spent. Both ride
        # that report's own record, frozen ahead of the gate, and the write
        # that completes the publication is what applies them -- so the reader
        # still names the round before this one and the counter still stands
        # where that round left it.
        pinned = self._pinned(self.scenario)
        landed = len(self.rounds) - 1

        self.assertEqual(
            pinned[PR_LAST_COMMENT_ID],
            NEXT_FEEDBACK_ID + (landed - 1) * ROUND_STRIDE,
        )
        self.assertEqual(pinned[REVIEW_ROUND], landed - 1)

    def test_the_held_record_carries_its_round(self) -> None:
        # What says the held round is still owed a count is the record, whose
        # frozen pairs name the reader to advance and the counter to spend.
        # Recomputed by whichever tick finally publishes, the round would be
        # read off a counter that has moved since and counted twice.
        recorded = _delivery_state.read_delivered_report(
            self.scenario.github.read_pinned_state(self.scenario.issue),
        )
        landed = len(self.rounds) - 1

        self.assertIn(
            (PR_LAST_COMMENT_ID, NEXT_FEEDBACK_ID + landed * ROUND_STRIDE),
            recorded.watermarks,
        )
        self.assertIn((REVIEW_ROUND, landed), recorded.spends)
