# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What the no-feedback bounce is allowed to put on its pull request.

The bounce publishes a commit nobody measured -- an earlier round committed it
and never pushed it -- so it goes through the same cumulative gate the shared
dev-fix publication does. Allowed, the push carries whatever the branch
accumulated in one go, named against the commit that was measured and pinned
to the head the proof was taken against. Held, the bounce does not happen at
all: relabelling over the adjudication the gate just opened would publish the
very question it asked.

The refusals close the same windows the other gated seams close. A pull
request somebody moved between the proof and the push, and one somebody closed
in that window, each leave the commit on the branch for a round that can vouch
for it -- and a bounce behind a push that already landed finds nothing ahead,
so it counts no second round.
"""
from __future__ import annotations

import unittest

from tests.workflow.stages.fixing import bounce_gate_support as support, fixing_test_support as fixing

ADDED_LINES = support.ADDED_LINES
AHEAD_BEHIND = support.AHEAD_BEHIND
CANDIDATE_COMMIT = support.CANDIDATE_COMMIT
FETCHED_TIP = support.FETCHED_TIP
FrozenCommit = support.FrozenCommit
HEAD_SHAS = support.HEAD_SHAS
CEILING = support.CEILING
COUNT_ADDED_LINES = support.COUNT_ADDED_LINES
GET_PR = support.GET_PR
KEY_ADDITIONS = support.KEY_ADDITIONS
KEY_APPROVED_LEASE = support.KEY_APPROVED_LEASE
KEY_APPROVED_SHA = support.KEY_APPROVED_SHA
KEY_BASE_SHA = support.KEY_BASE_SHA
KEY_CANDIDATE_SHA = support.KEY_CANDIDATE_SHA
KEY_PUBLISHED_SHA = support.KEY_PUBLISHED_SHA
KEY_RECEIPT_LEASE = support.KEY_RECEIPT_LEASE
KEY_RECEIPT_SHA = support.KEY_RECEIPT_SHA
KEY_SOURCE_STAGE = support.KEY_SOURCE_STAGE
KEY_SPENDS = support.KEY_SPENDS
LABEL_DECOMPOSING = support.LABEL_DECOMPOSING
LEASE = support.LEASE
MAX_ADDED_LINES = support.MAX_ADDED_LINES
MEASURED_BASE_SHA = support.MEASURED_BASE_SHA
MOVED_HEAD = support.MOVED_HEAD
NOTHING_AHEAD = support.NOTHING_AHEAD
ONE_COMMIT = support.ONE_COMMIT
PARK_MEASUREMENT_FAILED = support.PARK_MEASUREMENT_FAILED
PARK_UNPROVED_BRANCH = "stranded_unproved"
PAST_THE_CEILING = support.PAST_THE_CEILING
PUBLICATION_HEAD = support.PUBLICATION_HEAD
REVISION = support.REVISION
SEEDED_ROUND = support.SEEDED_ROUND
SEVERAL_COMMITS = support.SEVERAL_COMMITS
SPENT_ROUND = support.SPENT_ROUND
STRANDED_CANDIDATE = support.STRANDED_CANDIDATE
UNDER_THE_CEILING = support.UNDER_THE_CEILING
_ClosedUnderTheProbe = support._ClosedUnderTheProbe

AWAITING_HUMAN = fixing.AWAITING_HUMAN
FIXING = fixing.FIXING
ISSUE = fixing.ISSUE
PARK_REASON = fixing.PARK_REASON
PENDING_FIX_REVIEWER_COMMENT_ID = fixing.PENDING_FIX_REVIEWER_COMMENT_ID
PR_NUMBER = fixing.PR_NUMBER
PUSH_BRANCH = fixing.PUSH_BRANCH
REVIEW_ROUND = fixing.REVIEW_ROUND
RUN_AGENT = fixing.RUN_AGENT
config = fixing.config
patch = fixing.patch


class GatedBounceTest(unittest.TestCase, support._GatedBounceMixin):
    """A stranded commit measured against what its pull request comes to."""

    def test_what_the_branch_accumulated_is_measured(self) -> None:
        # No run stands behind this push, so nothing else has read what the
        # pull request would come to with the commit in it. The reading is
        # cumulative -- from the base the REMOTE names to the checkout's head
        # -- so a round killed several commits in meets the ceiling on their
        # total rather than on the last one's diff, and one push carries the
        # tip either way.
        for ahead in (ONE_COMMIT, SEVERAL_COMMITS):
            with self.subTest(ahead=ahead[0]):
                scenario = self._seed_gated_bounce()

                mocks = self._bounce(
                    scenario,
                    **{AHEAD_BEHIND: ahead, ADDED_LINES: UNDER_THE_CEILING},
                )

                mocks[RUN_AGENT].assert_not_called()
                mocks[COUNT_ADDED_LINES].assert_called_once()
                self.assertEqual(
                    mocks[COUNT_ADDED_LINES].call_args.args[1:],
                    (MEASURED_BASE_SHA, STRANDED_CANDIDATE),
                )
                pushed = self._assert_pushed_once(mocks)
                self.assertEqual(pushed.kwargs[REVISION], STRANDED_CANDIDATE)
                self.assertEqual(pushed.kwargs[LEASE], PUBLICATION_HEAD)
                self._assert_bounced(scenario, round_n=SPENT_ROUND)

    def test_a_landed_bounce_leaves_a_receipt(self) -> None:
        # The receipt names what this branch put on the remote and the head it
        # replaced. Without the pair, a later tick reading a pull request
        # rewound onto a commit published rounds ago would take it for this
        # push having landed.
        scenario = self._seed_gated_bounce()

        self._bounce(scenario, added_lines=UNDER_THE_CEILING)

        pinned = self._pinned(scenario)
        self.assertEqual(pinned[KEY_RECEIPT_SHA], STRANDED_CANDIDATE)
        self.assertEqual(pinned[KEY_RECEIPT_LEASE], PUBLICATION_HEAD)


class HeldBounceTest(unittest.TestCase, support._GatedBounceMixin):
    """What a stranded commit past the ceiling stops the bounce from doing."""

    def setUp(self) -> None:
        self.scenario = self._seed_gated_bounce()
        with patch.object(config, MAX_ADDED_LINES, CEILING):
            self.mocks = self._bounce(
                self.scenario,
                **{
                    AHEAD_BEHIND: SEVERAL_COMMITS,
                    ADDED_LINES: PAST_THE_CEILING,
                },
            )

    def test_the_bounce_does_not_happen(self) -> None:
        # The gate owns the issue from here, so the relabel this exit exists
        # to make belongs to a bounce that is not happening: moving the issue
        # back to `validating` would hand a reviewer the head the adjudication
        # is still deciding about.
        self._assert_held(self.scenario, self.mocks)
        self.assertEqual(
            self.scenario.github.label_history, [(ISSUE, LABEL_DECOMPOSING)],
        )

    def test_the_hold_records_what_it_was_entered_on(self) -> None:
        # None of it is re-derivable once the adjudication label has replaced
        # the stage: the pair a settled verdict republishes from, and the
        # publication the reading was taken over.
        pinned = self._pinned(self.scenario)

        self.assertEqual(pinned[KEY_ADDITIONS], PAST_THE_CEILING)
        self.assertEqual(pinned[KEY_BASE_SHA], MEASURED_BASE_SHA)
        self.assertEqual(pinned[KEY_CANDIDATE_SHA], STRANDED_CANDIDATE)
        self.assertEqual(pinned[KEY_PUBLISHED_SHA], PUBLICATION_HEAD)
        self.assertEqual(pinned[KEY_SOURCE_STAGE], FIXING)

    def test_the_hold_spends_round_and_bookmarks(self) -> None:
        # A held fix supersedes the head the reviewer rejected exactly as a
        # landed one does, and the batch this bounce read is consumed either
        # way. Both ride the gate's own write, ahead of the label it moves:
        # applied after it they would be lost to any crash in that window,
        # with no later tick going back for them.
        pinned = self._pinned(self.scenario)

        self.assertEqual(pinned[REVIEW_ROUND], SPENT_ROUND)
        self.assertIsNone(pinned[PENDING_FIX_REVIEWER_COMMENT_ID])


class RefusedBounceTest(unittest.TestCase, support._GatedBounceMixin):
    """The publications the bounce may not make, and what it leaves instead."""

    def test_a_moved_pull_request_refuses(self) -> None:
        # The stranded proof was taken against the head the pull request was
        # standing on, and somebody landed on it since. The two readings do
        # not describe the same publication, so nothing is measured, nothing
        # is pushed, and the bounce does not relabel over a commit the pull
        # request never received.
        scenario = self._seed_gated_bounce()
        scenario.github.get_pr(PR_NUMBER).head.sha = MOVED_HEAD

        mocks = self._bounce(scenario, added_lines=UNDER_THE_CEILING)

        mocks[COUNT_ADDED_LINES].assert_not_called()
        self._assert_held(scenario, mocks)
        pinned = self._pinned(scenario)
        self.assertTrue(pinned[AWAITING_HUMAN])
        self.assertEqual(pinned[PARK_REASON], PARK_MEASUREMENT_FAILED)
        self.assertEqual(pinned[REVIEW_ROUND], SEEDED_ROUND)

    def test_a_closed_pull_request_refuses(self) -> None:
        # A closed pull request has nowhere for the push to land, so a reading
        # against it would adjudicate a question nobody can act on. The
        # preflight drains one that is already closed, so this is the state
        # arriving while the tick probes -- and the answer is the same refusal.
        scenario = self._seed_gated_bounce()

        with patch.object(
            scenario.github, GET_PR,
            side_effect=_ClosedUnderTheProbe(scenario.github, PR_NUMBER),
        ):
            mocks = self._bounce(scenario, added_lines=UNDER_THE_CEILING)

        mocks[COUNT_ADDED_LINES].assert_not_called()
        self._assert_held(scenario, mocks)
        # The preflight read an OPEN pull request, so nothing was drained to a
        # terminal: what refused is the gate, on its own reading.
        self.assertEqual(scenario.github.label_history, [])
        pinned = self._pinned(scenario)
        self.assertEqual(pinned[PARK_REASON], PARK_MEASUREMENT_FAILED)
        self.assertEqual(pinned[REVIEW_ROUND], SEEDED_ROUND)

    def test_a_missed_push_leaves_the_retry_owed(self) -> None:
        # The reading allowed the candidate and the push did not land, so the
        # commit is still owed a publication and the round it would spend is
        # unspent. Both ride the record: the approval names the commit and the
        # head to pin it to, and the bookkeeping this route owed travels with
        # it, because the tick that finally lands it has no run of its own to
        # re-derive a round or a consumed batch from. The bounce itself still
        # lands -- the commit waits on the branch for a push that can vouch
        # for it.
        scenario = self._seed_gated_bounce()

        mocks = self._bounce(
            scenario, added_lines=UNDER_THE_CEILING, push_branch=False,
        )

        self._assert_pushed_once(mocks)
        pinned = self._pinned(scenario)
        self.assertEqual(pinned[KEY_APPROVED_SHA], STRANDED_CANDIDATE)
        self.assertEqual(pinned[KEY_APPROVED_LEASE], PUBLICATION_HEAD)
        self.assertIn([REVIEW_ROUND, SPENT_ROUND], pinned[KEY_SPENDS])
        self._assert_bounced(scenario, round_n=SEEDED_ROUND)

    def test_a_bounce_behind_a_push_counts_once(self) -> None:
        # The tick that published the stranded commit died before its relabel,
        # so this one reaches the same exit over a branch that is level with
        # its publication. There is nothing left to vouch for, so nothing is
        # measured or pushed and the round that push already spent is not
        # spent again -- the bounce itself still lands.
        scenario = self._seed_gated_bounce(**{
            REVIEW_ROUND: SPENT_ROUND,
            **support.receipt_group(
                STRANDED_CANDIDATE,
                lease=PUBLICATION_HEAD,
                pull_request=PR_NUMBER,
            ),
        })
        scenario.github.get_pr(PR_NUMBER).head.sha = STRANDED_CANDIDATE

        mocks = self._bounce(
            scenario,
            **{
                AHEAD_BEHIND: NOTHING_AHEAD,
                # "Level with its publication" is one commit named three
                # times: the remote the landed push left, the head the
                # checkout is standing on, and the pull request's own.
                FETCHED_TIP: STRANDED_CANDIDATE,
                HEAD_SHAS: (STRANDED_CANDIDATE,),
                ADDED_LINES: UNDER_THE_CEILING,
            },
        )

        mocks[COUNT_ADDED_LINES].assert_not_called()
        mocks[PUSH_BRANCH].assert_not_called()
        self._assert_bounced(scenario, round_n=SPENT_ROUND)


class CheckoutRaceRefusalTest(unittest.TestCase, support._GatedBounceMixin):
    """The two windows a checkout can move in, and the refusal each earns.

    No developer runs on this exit, so nothing in the worktree is this route's
    output: a head that moved under it is somebody else's commit -- another
    tick, an operator, a stray descendant -- and publishing it would send the
    reviewer work nothing on this tick ever read.
    """

    def test_a_checkout_moved_mid_reading_refuses(self) -> None:
        # The checkout moves WHILE the branch is being placed: the commit is
        # frozen, the count is taken against that id, and the re-proof finds
        # the worktree somewhere else. The count is still sound -- it named an
        # immutable commit -- but the push it would license would go out over
        # a checkout nothing here has read, so the reading refuses and the
        # bounce never reaches the gate at all.
        scenario = self._seed_gated_bounce()

        mocks = self._bounce(
            scenario,
            **{
                ADDED_LINES: UNDER_THE_CEILING,
                # Frozen before the count, and something else by the time the
                # re-proof reads it -- with the gate agreeing about where the
                # checkout ended up, so nothing downstream would catch it:
                # unfrozen, this tick measures and pushes the later commit.
                HEAD_SHAS: (STRANDED_CANDIDATE, MOVED_HEAD),
                CANDIDATE_COMMIT: FrozenCommit(sha=MOVED_HEAD),
            },
        )

        mocks[COUNT_ADDED_LINES].assert_not_called()
        self._assert_refused_without_a_reading(scenario, mocks)

    def test_a_checkout_that_moved_refuses(self) -> None:
        # The other end of the same race: the reading placed the branch and
        # the checkout moved before the gate proved it. No developer ran on
        # this tick, so nothing in the worktree is this route's output and a
        # head that moved under it is a different commit entirely -- another
        # tick, an operator, a stray descendant. The reading counted one
        # commit and the gate proves the checkout to another, so the two do
        # not describe the same candidate.
        scenario = self._seed_gated_bounce()

        mocks = self._bounce(
            scenario,
            **{
                ADDED_LINES: UNDER_THE_CEILING,
                # What the branch-placement probe counted, and what the gate
                # finds the checkout standing on a moment later.
                HEAD_SHAS: (STRANDED_CANDIDATE,),
                CANDIDATE_COMMIT: FrozenCommit(sha=MOVED_HEAD),
            },
        )

        mocks[COUNT_ADDED_LINES].assert_not_called()
        self._assert_held(scenario, mocks)
        pinned = self._pinned(scenario)
        self.assertTrue(pinned[AWAITING_HUMAN])
        self.assertEqual(pinned[PARK_REASON], PARK_MEASUREMENT_FAILED)
        self._assert_nothing_spent(pinned)

    def _assert_refused_without_a_reading(self, scenario, mocks) -> None:
        """The bounce that never reached the gate: held under its own park."""
        self._assert_held(scenario, mocks)
        pinned = self._pinned(scenario)
        self.assertTrue(pinned[AWAITING_HUMAN])
        self.assertEqual(pinned[PARK_REASON], PARK_UNPROVED_BRANCH)
        self._assert_nothing_spent(pinned)

    def _assert_nothing_spent(self, pinned) -> None:
        """No round counted and the bookmark left for a round that can vouch."""
        self.assertEqual(pinned[REVIEW_ROUND], SEEDED_ROUND)
        self.assertEqual(
            pinned[PENDING_FIX_REVIEWER_COMMENT_ID], fixing.REVIEWER_FEEDBACK_ID,
        )


if __name__ == "__main__":
    unittest.main()
