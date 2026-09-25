# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What a silent `validating` recovery is allowed to put on its pull request.

Both transient parks that touch git end in a push onto a pull request the
remote already carries, and neither has a run behind it to have measured what
that push would take the pull request to. So they go through the same
cumulative gate every other fix does: the deferred push republishes a commit
the gate already ruled on, and the commit a timeout stranded is measured
before it joins anything.

The refusals are the point as much as the publications. A pull request nobody
can push onto, one somebody moved under the park, and a checkout that moved
between the recovery's own read and the gate's proof each leave the park where
it stands -- and a candidate the reading finds too big is handed to the
adjudication rather than pushed, with the round it spent counted inside the
gate's own write.
"""
from __future__ import annotations

import unittest
from types import MappingProxyType

from tests.workflow.stages.validating import recovered_gate_support as support

AWAITING_HUMAN = support.AWAITING_HUMAN
CEILING = support.CEILING
COUNT_ADDED_LINES = support.COUNT_ADDED_LINES
KEY_ADDITIONS = support.KEY_ADDITIONS
KEY_APPROVED_LEASE = support.KEY_APPROVED_LEASE
KEY_APPROVED_SHA = support.KEY_APPROVED_SHA
KEY_BASE_SHA = support.KEY_BASE_SHA
KEY_CANDIDATE_SHA = support.KEY_CANDIDATE_SHA
KEY_PUBLISHED_SHA = support.KEY_PUBLISHED_SHA
KEY_RECEIPT_LEASE = support.KEY_RECEIPT_LEASE
KEY_RECEIPT_PR = support.KEY_RECEIPT_PR
KEY_RECEIPT_SHA = support.KEY_RECEIPT_SHA
KEY_SOURCE_STAGE = support.KEY_SOURCE_STAGE
LABEL_DECOMPOSING = support.LABEL_DECOMPOSING
LABEL_VALIDATING = support.LABEL_VALIDATING
LEASE = support.LEASE
MAX_ADDED_LINES = support.MAX_ADDED_LINES
MEASURED_BASE_SHA = support.MEASURED_BASE_SHA
MOVED_HEAD = support.MOVED_HEAD
MOVED_MID_TICK = support.MOVED_MID_TICK
PARK_AGENT_TIMEOUT = support.PARK_AGENT_TIMEOUT
PARK_MEASUREMENT_FAILED = support.PARK_MEASUREMENT_FAILED
PARK_PUSH_FAILED = support.PARK_PUSH_FAILED
PARK_REASON = support.PARK_REASON
PAST_THE_CEILING = support.PAST_THE_CEILING
PRE_DEV_FIX_SHA = support.PRE_DEV_FIX_SHA
INTERRUPTED_RESUME_HEAD = support.INTERRUPTED_RESUME_HEAD
PUBLICATION_HEAD = support.PUBLICATION_HEAD
PUSH_BRANCH = support.PUSH_BRANCH
RECOVERY_ISSUE = support.RECOVERY_ISSUE
RECOVERY_PR = support.RECOVERY_PR
REVIEW_ROUND = support.REVIEW_ROUND
REVISION = support.REVISION
RUN_AGENT = support.RUN_AGENT
STRANDED_CANDIDATE = support.STRANDED_CANDIDATE
UNDER_THE_CEILING = support.UNDER_THE_CEILING
FrozenCommit = support.FrozenCommit
PUSH_RETRIED_DETAIL = support.PUSH_RETRIED_DETAIL
TIMEOUT_EMPTY_DETAIL = support.TIMEOUT_EMPTY_DETAIL
TIMEOUT_PUSHED_DETAIL = support.TIMEOUT_PUSHED_DETAIL
config = support.config
patch = support.patch

# What a pull request reads as once somebody has closed it without merging,
# and where the issue behind one lands.
_CLOSED = "closed"
LABEL_REJECTED = "rejected"

# The round the fixture parks on, and the one a published recovery moves it to.
PARKED_ROUND = 1
SPENT_ROUND = 2

# The run options a case seeds the branch geometry with, and the counts a
# checkout standing exactly where its publication is answers.
HEAD_SHAS = "head_shas"
AHEAD_BEHIND = "branch_ahead_behind"
FETCHED_TIP = "fetched_branch_tip"
IN_SYNC = (0, 0)
ONE_AHEAD = (1, 0)
# A branch carrying the commit an interrupted resume stranded AND the one the
# round above it committed before being killed.
TWO_AHEAD = (2, 0)

# A checkout standing exactly where its publication is: the counts agree and
# the head reads as the tip they were taken against, which is what says the
# killed run really did leave nothing behind.
LEVEL_WITH_THE_PUBLICATION = MappingProxyType({
    HEAD_SHAS: (PUBLICATION_HEAD,) * 6,
    AHEAD_BEHIND: IN_SYNC,
    FETCHED_TIP: PUBLICATION_HEAD,
})

# The same tick over a branch whose head is a commit an earlier interrupted
# resume left: the run found it there, so it committed nothing, and the pull
# request has never carried it.
STOOD_ON_A_STRANDED = MappingProxyType({
    AHEAD_BEHIND: ONE_AHEAD, FETCHED_TIP: PUBLICATION_HEAD,
})

# Every reading that leaves that branch unplaced, named by the shape it stands
# for. Each is a checkout that MAY be above its publication.
UNPLACED_BRANCHES = (
    ("remote moved", {AHEAD_BEHIND: (1, 2)}),
    ("unreadable divergence", {"branch_divergence_readable": False}),
    (
        "fetch failed",
        {"authed_fetch_result": support.MagicMock(returncode=1, stderr="no")},
    ),
    ("checkout moved under the count", {AHEAD_BEHIND: IN_SYNC}),
)


class DeferredPushRecoveryTest(
    unittest.TestCase, support._RecoveredPublicationMixin,
):
    """The push a `push_failed` park deferred, retried through the gate."""

    def test_an_approved_commit_is_unmeasured(self) -> None:
        # A reading already settled this commit, so the retry is the push that
        # reading licensed and nothing else: no agent, no second count, and
        # the two commits the push is named and pinned by come off the
        # approval rather than off whatever the remote says now.
        scenario = self._seed_deferred_push()

        mocks = self._recover(scenario)

        mocks[RUN_AGENT].assert_not_called()
        self._assert_unmeasured(mocks)
        pushed = self._assert_pushed_once(mocks)
        self.assertEqual(pushed.kwargs[REVISION], STRANDED_CANDIDATE)
        self.assertEqual(pushed.kwargs[LEASE], PUBLICATION_HEAD)

    def test_a_landed_push_settles_the_debt_it_paid(self) -> None:
        # The approval says one commit is still owed a publication, and left
        # standing past the push that made it, it freezes this branch out of
        # the pre-tick base refresh for the rest of the issue's life. The
        # receipt beside it is what names the commit that reached the remote.
        scenario = self._seed_deferred_push()

        self._recover(scenario)

        pinned = self._pinned(scenario)
        self.assertIsNone(pinned[KEY_APPROVED_SHA])
        self.assertIsNone(pinned[KEY_APPROVED_LEASE])
        self.assertEqual(pinned[KEY_RECEIPT_SHA], STRANDED_CANDIDATE)
        self.assertEqual(pinned[KEY_RECEIPT_LEASE], PUBLICATION_HEAD)
        self.assertEqual(pinned[KEY_RECEIPT_PR], RECOVERY_PR)

    def test_a_healed_park_counts_one_round(self) -> None:
        # The head the reviewer rejected is superseded, so the round is spent
        # exactly as a dev run's own push spends one -- and the mention the
        # park left is retired rather than being the thread's last word.
        scenario = self._seed_deferred_push()

        self._recover(scenario)

        self.assertEqual(self._pinned(scenario)[REVIEW_ROUND], SPENT_ROUND)
        self._assert_park_cleared(scenario)
        self._assert_recovery_followup(scenario.github, PUSH_RETRIED_DETAIL)

    def test_a_push_that_misses_leaves_it_owed(self) -> None:
        # Somebody pushed to the pull request while the issue sat parked, so
        # the lease the approval records refuses. Nothing may be dropped on
        # that answer: the commit is still owed a publication, the round it
        # would spend is unspent, and the park is what brings the next tick
        # back for it.
        scenario = self._seed_deferred_push()
        scenario.github.get_pr(RECOVERY_PR).head.sha = MOVED_HEAD

        mocks = self._recover(scenario, push_branch=False)

        self._assert_pushed_once(mocks)
        pinned = self._pinned(scenario)
        self.assertEqual(pinned[KEY_APPROVED_SHA], STRANDED_CANDIDATE)
        self.assertEqual(pinned[KEY_APPROVED_LEASE], PUBLICATION_HEAD)
        self.assertEqual(pinned[REVIEW_ROUND], PARKED_ROUND)
        self._assert_park_stands(scenario, PARK_PUSH_FAILED)

    def test_a_closed_pull_request_ends_the_issue(self) -> None:
        # A pull request somebody closed without merging leaves the ISSUE
        # open, so nothing about the issue's own state says the work is over
        # -- and every road below this ends in a push onto exactly that pull
        # request. The terminal answers it ahead of the recovery: the work is
        # rejected, nothing is pushed, and no reviewer is spawned over it.
        scenario = self._seed_deferred_push()
        scenario.github.get_pr(RECOVERY_PR).state = _CLOSED

        mocks = self._recover(scenario)

        mocks[PUSH_BRANCH].assert_not_called()
        mocks[RUN_AGENT].assert_not_called()
        self.assertIn(
            (RECOVERY_ISSUE, LABEL_REJECTED), scenario.github.label_history,
        )

class CrashedPublicationRecoveryTest(
    unittest.TestCase, support._RecoveredPublicationMixin,
):
    """The window a push that landed and a lost write leave behind.

    The branch is on the remote, the pull request carries the commit, and the
    write that would have cleared the park went down with the tick. What the
    receipt buys the retry is the round it does not count again -- but only
    while the group behind it says this issue's own push put the work there,
    onto the publication this call froze.
    """

    def test_a_crashed_tick_counts_no_round(self) -> None:
        # The push landed and the write carrying its receipt went down with
        # it; what died was the clear behind them, so the park is still up.
        # The retry finds the pull request standing on the commit, so its
        # push is the leased no-op that proves as much -- and the round the
        # tick that really published it counted is not counted again.
        # The publication that push went onto rides the receipt: without it
        # the record names none this call can hold the note to, and the
        # candidate goes back through the reading instead.
        scenario = self._crashed_tick(RECOVERY_PR)

        mocks = self._recover(scenario)

        self._assert_unmeasured(mocks)
        pushed = self._assert_pushed_once(mocks)
        self.assertEqual(pushed.kwargs[REVISION], STRANDED_CANDIDATE)
        self.assertEqual(pushed.kwargs[LEASE], STRANDED_CANDIDATE)
        self.assertEqual(self._pinned(scenario)[REVIEW_ROUND], SPENT_ROUND)
        self._assert_park_cleared(scenario)

    def test_a_foreign_receipt_is_measured(self) -> None:
        # The half the frozen head cannot supply. A pull request standing on
        # the commit says the work is THERE and nothing about how it got
        # there, so the number the receipt names has to be the one this call
        # froze: an earlier publication of this issue's, or a replacement
        # somebody opened after closing the original, would have the round,
        # the receipt and the relabel spent against a push this stage never
        # made.
        scenario = self._crashed_tick(RECOVERY_PR + 1)

        mocks = self._recover(scenario, added_lines=UNDER_THE_CEILING)

        # Measured rather than waved past, which is the safe road: the
        # reading decides the candidate and the push behind it is leased to
        # the head this call froze.
        self._assert_measured(mocks)

    def test_a_receipt_naming_no_publication_is_kept(self) -> None:
        # A number nothing can read and no number at all are the same record
        # from the published end, and neither is a question the reading can
        # answer: a group that claims a publication and cannot say which one
        # is damage, so measuring and publishing would put a fresh group down
        # over it and destroy what an operator would have repaired it from.
        for described, identity in (
            ("one nothing can read", "not-a-number"),
            ("none at all", None),
        ):
            with self.subTest(receipt=described):
                scenario = self._crashed_tick(identity)

                mocks = self._recover(
                    scenario,
                    added_lines=UNDER_THE_CEILING,
                    push_branch=False,
                )

                self._assert_unmeasured(mocks)
                mocks[PUSH_BRANCH].assert_not_called()
                pinned = self._pinned(scenario)
                self.assertEqual(pinned[KEY_RECEIPT_PR], identity)
                self.assertEqual(pinned[KEY_RECEIPT_SHA], STRANDED_CANDIDATE)
                self.assertEqual(
                    pinned[KEY_RECEIPT_LEASE], PUBLICATION_HEAD,
                )

    def _crashed_tick(self, identity):
        """The window a push that landed and a lost write leave, receipt and all."""
        scenario = self._seed_deferred_push(**{
            KEY_APPROVED_SHA: None,
            KEY_APPROVED_LEASE: None,
            KEY_RECEIPT_SHA: STRANDED_CANDIDATE,
            KEY_RECEIPT_LEASE: PUBLICATION_HEAD,
            KEY_RECEIPT_PR: identity,
            REVIEW_ROUND: SPENT_ROUND,
        })
        scenario.github.get_pr(RECOVERY_PR).head.sha = STRANDED_CANDIDATE
        return scenario


class TimedOutFixRecoveryTest(
    unittest.TestCase, support._RecoveredPublicationMixin,
):
    """The commit a killed run made, measured before it joins anything."""

    def test_a_stranded_commit_is_measured_first(self) -> None:
        # The one road to a published pull request that never reached the
        # gate: nothing measured what the killed run committed. The reading is
        # cumulative -- taken from the base the REMOTE names to the checkout's
        # head, so it covers everything the pull request comes to rather than
        # the diff of whatever the run got as far as committing.
        scenario = self._seed_timed_out()

        mocks = self._recover(scenario, added_lines=UNDER_THE_CEILING)

        mocks[RUN_AGENT].assert_not_called()
        self._assert_measured(mocks)
        self.assertEqual(
            mocks[COUNT_ADDED_LINES].call_args.args[1:],
            (MEASURED_BASE_SHA, STRANDED_CANDIDATE),
        )
        pushed = self._assert_pushed_once(mocks)
        self.assertEqual(pushed.kwargs[REVISION], STRANDED_CANDIDATE)
        self.assertEqual(pushed.kwargs[LEASE], PUBLICATION_HEAD)

    def test_a_commit_over_a_stranded_one_is_leased(self) -> None:
        # The round that timed out opened on a commit an EARLIER interrupted
        # resume left, so the anchor it stamped is where it found the checkout
        # and not where the pull request is: the branch stands two commits
        # above the publication. Read off that anchor, the push would be
        # leased to a commit the pull request never carried and the gate would
        # refuse it unmeasured, parking a human over work the branch is
        # holding. Leased to the tip the reading proved and named for the
        # commit it froze, the ordinary measurement and push happen instead.
        scenario = self._seed_timed_out(**{
            PRE_DEV_FIX_SHA: INTERRUPTED_RESUME_HEAD,
        })

        mocks = self._recover(
            scenario, added_lines=UNDER_THE_CEILING, **{AHEAD_BEHIND: TWO_AHEAD},
        )

        self._assert_measured(mocks)
        pushed = self._assert_pushed_once(mocks)
        self.assertEqual(pushed.kwargs[REVISION], STRANDED_CANDIDATE)
        self.assertEqual(pushed.kwargs[LEASE], PUBLICATION_HEAD)
        pinned = self._pinned(scenario)
        self.assertIsNone(pinned[PRE_DEV_FIX_SHA])
        self.assertEqual(pinned[KEY_RECEIPT_SHA], STRANDED_CANDIDATE)
        self.assertEqual(pinned[KEY_RECEIPT_LEASE], PUBLICATION_HEAD)
        self._assert_park_cleared(scenario)

    def test_a_published_recovery_closes_the_park(self) -> None:
        # The anchor the park stamped has been answered, so leaving it would
        # let a later tick compare a fresh head against a head from rounds
        # ago. The round and the follow-up are the rest of what the landed
        # push earns.
        scenario = self._seed_timed_out()

        self._recover(scenario, added_lines=UNDER_THE_CEILING)

        pinned = self._pinned(scenario)
        self.assertIsNone(pinned[PRE_DEV_FIX_SHA])
        self.assertEqual(pinned[KEY_RECEIPT_SHA], STRANDED_CANDIDATE)
        self.assertEqual(pinned[REVIEW_ROUND], SPENT_ROUND)
        self._assert_park_cleared(scenario)
        self._assert_recovery_followup(scenario.github, TIMEOUT_PUSHED_DETAIL)


class EmptyTimeoutRecoveryTest(
    unittest.TestCase, support._RecoveredPublicationMixin,
):
    """A timeout that left the head where it found it, answered by the BRANCH.

    "The run committed nothing" is a fact about the run, and what the next
    reviewer reads is the checkout. The head that run found can itself be a
    commit an earlier interrupted resume left, so the clear is taken off a
    reading of the branch: level with its publication clears, a commit the
    pull request has not got is published through the gate, and a reading
    nobody could take holds the park the timeout already filed.
    """

    def test_an_empty_run_is_never_measured(self) -> None:
        # The checkout is where the killed run found it AND where its pull
        # request is, so there is nothing to publish and nothing to read the
        # size of. The park clears all the same -- the reviewer is what the
        # issue needs next -- and the follow-up says which of the two things
        # happened.
        scenario = self._seed_timed_out()

        mocks = self._recover(scenario, **LEVEL_WITH_THE_PUBLICATION)

        self._assert_unmeasured(mocks)
        mocks[PUSH_BRANCH].assert_not_called()
        pinned = self._pinned(scenario)
        self.assertIsNone(pinned[PRE_DEV_FIX_SHA])
        self.assertEqual(pinned[REVIEW_ROUND], PARKED_ROUND)
        self._assert_park_cleared(scenario)
        self._assert_recovery_followup(scenario.github, TIMEOUT_EMPTY_DETAIL)

    def test_an_empty_run_publishes_what_it_stood_on(self) -> None:
        # The killed run left the head where it found it, and the head it
        # found is a commit an EARLIER interrupted resume left: the branch is
        # one ahead of its publication and nothing on the comment knows. The
        # clear is taken off the BRANCH rather than off the run, so that commit
        # is work to publish and goes out through the ordinary measurement --
        # read off the run alone it would send the next reviewer to a checkout
        # the pull request is short of, with no receipt and no gate debt to
        # stop it. What the healed park then tells the thread is the
        # publication and not whose commit it was: this run made none, so a
        # sentence crediting it would be describing work it never did.
        scenario = self._seed_timed_out(**{
            PRE_DEV_FIX_SHA: STRANDED_CANDIDATE,
        })

        mocks = self._recover(
            scenario, added_lines=UNDER_THE_CEILING, **STOOD_ON_A_STRANDED,
        )

        mocks[RUN_AGENT].assert_not_called()
        self._assert_measured(mocks)
        pushed = self._assert_pushed_once(mocks)
        self.assertEqual(pushed.kwargs[REVISION], STRANDED_CANDIDATE)
        self.assertEqual(pushed.kwargs[LEASE], PUBLICATION_HEAD)
        pinned = self._pinned(scenario)
        self.assertIsNone(pinned[PRE_DEV_FIX_SHA])
        self.assertEqual(pinned[REVIEW_ROUND], SPENT_ROUND)
        self._assert_park_cleared(scenario)
        self._assert_recovery_followup(scenario.github, TIMEOUT_PUSHED_DETAIL)

    def test_an_unplaced_branch_holds_the_park(self) -> None:
        # Every reading the probe cannot take answers "the run left nothing"
        # exactly as an empty branch does, and each of them may be a checkout
        # carrying a commit the pull request has not got. Cleared on one, the
        # reviewer runs next over a head nobody read -- so the park the
        # timeout already told a human about stands instead, with nothing
        # measured, nothing pushed, and the anchor kept for the tick that can
        # read the branch.
        for shape, run_options in UNPLACED_BRANCHES:
            with self.subTest(shape=shape):
                scenario = self._seed_timed_out(**{
                    PRE_DEV_FIX_SHA: STRANDED_CANDIDATE,
                })

                mocks = self._recover(scenario, **run_options)

                mocks[RUN_AGENT].assert_not_called()
                self._assert_unmeasured(mocks)
                mocks[PUSH_BRANCH].assert_not_called()
                self.assertEqual(
                    self._pinned(scenario)[PRE_DEV_FIX_SHA],
                    STRANDED_CANDIDATE,
                )
                self._assert_park_stands(scenario, PARK_AGENT_TIMEOUT)

    def test_a_moved_pull_request_refuses(self) -> None:
        # The push is leased to the tip the branch reading proved the
        # publication to be standing on, and the gate reads that publication
        # again for itself. The two disagree -- somebody moved the pull request
        # -- so naming the head is what makes their push refuse rather than be
        # adopted as the lease: nothing is measured, nothing is pushed, and the
        # park stands.
        scenario = self._seed_timed_out()
        scenario.github.get_pr(RECOVERY_PR).head.sha = MOVED_HEAD

        mocks = self._recover(scenario, added_lines=UNDER_THE_CEILING)

        self._assert_unmeasured(mocks)
        mocks[PUSH_BRANCH].assert_not_called()
        pinned = self._pinned(scenario)
        self.assertEqual(pinned[PRE_DEV_FIX_SHA], PUBLICATION_HEAD)
        self.assertEqual(pinned[REVIEW_ROUND], PARKED_ROUND)
        self.assertEqual(pinned[PARK_REASON], PARK_MEASUREMENT_FAILED)

    def test_a_checkout_that_moved_is_refused(self) -> None:
        # The recovery reads the head to decide there is anything to publish,
        # and the gate proves the checkout again behind it. A commit landing
        # in that window would otherwise be measured, pushed, and receipted as
        # the work the killed run left, so the two readings are one decision.
        scenario = self._seed_timed_out()

        mocks = self._recover(
            scenario,
            head_shas=(STRANDED_CANDIDATE,),
            candidate_commit=(FrozenCommit(sha=MOVED_MID_TICK),) * 4,
        )

        self._assert_unmeasured(mocks)
        mocks[PUSH_BRANCH].assert_not_called()
        pinned = self._pinned(scenario)
        self.assertEqual(pinned[PRE_DEV_FIX_SHA], PUBLICATION_HEAD)
        self.assertEqual(pinned[PARK_REASON], PARK_MEASUREMENT_FAILED)

    def test_a_retry_counts_one_round(self) -> None:
        # The first attempt measures the candidate and cannot land it, so what
        # it leaves is an approval and the round that reading owed. The second
        # publishes from there without measuring again, and the round the
        # first attempt froze is spent once rather than recomputed per poll.
        scenario = self._seed_timed_out()

        missed = self._recover(
            scenario, added_lines=UNDER_THE_CEILING, push_branch=False,
        )
        self.assertEqual(self._pinned(scenario)[REVIEW_ROUND], PARKED_ROUND)
        self._assert_park_stands(scenario, PARK_AGENT_TIMEOUT)

        landed = self._recover(scenario, added_lines=UNDER_THE_CEILING)

        missed[COUNT_ADDED_LINES].assert_called_once()
        landed[COUNT_ADDED_LINES].assert_not_called()
        self.assertEqual(self._pinned(scenario)[REVIEW_ROUND], SPENT_ROUND)
        self._assert_park_cleared(scenario)

    def test_an_oversized_accumulation_is_held(self) -> None:
        # What the killed run committed is measured as everything the pull
        # request comes to with it, so a run that got several commits in meets
        # the ceiling on their total. Past it, nothing is pushed, the issue
        # goes to the adjudication instead of back to the reviewer, and the
        # round it spent is counted inside the gate's own write -- ahead of
        # the label it moves, since no tick after this one would go back for
        # it.
        scenario = self._seed_timed_out()

        with patch.object(config, MAX_ADDED_LINES, CEILING):
            mocks = self._recover(scenario, added_lines=PAST_THE_CEILING)

        mocks[PUSH_BRANCH].assert_not_called()
        pinned = self._pinned(scenario)
        self.assertEqual(pinned[KEY_ADDITIONS], PAST_THE_CEILING)
        self.assertEqual(pinned[KEY_BASE_SHA], MEASURED_BASE_SHA)
        self.assertEqual(pinned[KEY_CANDIDATE_SHA], STRANDED_CANDIDATE)
        self.assertEqual(pinned[KEY_PUBLISHED_SHA], PUBLICATION_HEAD)
        self.assertEqual(pinned[KEY_SOURCE_STAGE], LABEL_VALIDATING)
        self.assertEqual(pinned[REVIEW_ROUND], SPENT_ROUND)
        self.assertEqual(
            scenario.github.label_history,
            [(RECOVERY_ISSUE, LABEL_DECOMPOSING)],
        )
        self._assert_nothing_healed(scenario)


if __name__ == "__main__":
    unittest.main()
