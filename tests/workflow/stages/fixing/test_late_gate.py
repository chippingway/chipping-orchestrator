# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What a fixing tick owes the gate, and what the gate leaves it holding.

The fixing-specific half of the size gate's coverage: the second seam a
candidate reaches a published pull request through (the no-feedback bounce),
the checkout that is not on this host when that bounce runs, and the reviewer
round this loop spends whether its fix is pushed or held. The gate's own
contract is pinned beside its owner, in
`test_published_gate.py` beside this one.
"""
from __future__ import annotations

import unittest

from orchestrator.git.measurement.models import MeasurementFailure
from orchestrator.workflow.engine import report_delivery_state as _delivery_state
from tests.workflow.stages.fixing import (
    fixing_test_support as fixing,
    published_gate_support as support,
)

AT_THE_CEILING = support.AT_THE_CEILING
BASE_OBJECT_PRESENT = support.BASE_OBJECT_PRESENT
CEILING = support.CEILING
COUNT_ADDED_LINES = support.COUNT_ADDED_LINES
FREEZE_BASE_COMMIT = support.FREEZE_BASE_COMMIT
LABEL_DECOMPOSING = support.LABEL_DECOMPOSING
MEASURED_BASE_SHA = support.MEASURED_BASE_SHA
MEASURED_CANDIDATE_SHA = support.MEASURED_CANDIDATE_SHA
PAST_THE_CEILING = support.PAST_THE_CEILING
UNDER_THE_CEILING = support.UNDER_THE_CEILING
_SizeGateFixtureMixin = support._SizeGateFixtureMixin
recorded_generation = support.recorded_generation

FIXING = fixing.FIXING
ISSUE = fixing.ISSUE
PR_HEAD_SHA = fixing.PR_HEAD_SHA
PR_NUMBER = fixing.PR_NUMBER
PUSH_BRANCH = fixing.PUSH_BRANCH
SHA_BEFORE = fixing.SHA_BEFORE
STAGE_FIXING = fixing.STAGE_FIXING
VALIDATING = fixing.VALIDATING
config = fixing.config
patch = fixing.patch

_HELD = (ISSUE, LABEL_DECOMPOSING)
# The two keywords a gated push names its commit and pins its ref by.
REVISION = "revision"
LEASE = "force_with_lease"
WRITE_PINNED_STATE = "write_pinned_state"
WRITE_REJECTED = "pinned write rejected"
SET_WORKFLOW_LABEL = "set_workflow_label"
RELABEL_REJECTED = "label write rejected"
# A second pull request on the same branch, for the record frozen on the
# first: the same head can be the tip of both.
OTHER_PR_NUMBER = PR_NUMBER + 1
# A path no checkout is at, for the host the frozen pair was not made on.
ABSENT_WORKTREE = fixing.Path("/tmp/orchestrator-absent-checkout")
REVIEW_ROUND = fixing.REVIEW_ROUND
PENDING_FIX_AT = fixing.PENDING_FIX_AT
SHA_AFTER = fixing.SHA_AFTER
# What the checkout stands on once something has moved it out from under the
# head this route read.
MOVED_HEAD = "m0vedc0m" * 5
# What the pull request stands on once somebody else has landed on it.
MOVED_PUBLICATION = "cafef00d" * 5

class StrandedBounceTest(
    unittest.TestCase, fixing._StrandedFixingFixtureMixin,
):
    """The second seam a candidate reaches a published pull request through.

    The no-feedback bounce publishes a commit an earlier run stranded, so it
    passes the same gate: a stranded commit is work nobody measured, and a
    bounce that pushed it would be the way past a ceiling every other route
    holds to.
    """

    def test_a_stranded_fix_is_measured_first(self) -> None:
        gh, issue = self._seed_stranded_bounce()

        mocks = self._bounced(gh, issue)

        mocks[COUNT_ADDED_LINES].assert_called_once()
        mocks[PUSH_BRANCH].assert_called_once()

    def test_an_oversized_one_stops_the_bounce(self) -> None:
        # Held means the gate has already handed the issue to the
        # adjudication, so the bounce may not relabel over it -- the reviewer
        # is not owed a look at a head that is not going out.
        gh, issue = self._seed_stranded_bounce()

        with patch.object(config, support.MAX_ADDED_LINES, CEILING):
            mocks = self._bounced(gh, issue, added_lines=PAST_THE_CEILING)

        mocks[PUSH_BRANCH].assert_not_called()
        self.assertEqual(gh.label_history, [_HELD])
        # The bounce counts a round for a stranded commit it publishes, and a
        # held one supersedes the rejected head just the same. Counted after
        # the call, it would be lost to a crash in the window the gate's own
        # relabel opens -- and no later tick counts it, since a settled
        # verdict publishes the accepted commit and this bounce then finds
        # nothing ahead of it.
        pinned = gh.pinned_data(ISSUE)
        self.assertEqual(pinned[REVIEW_ROUND], 3)
        self.assertIsNone(pinned.get(support.KEY_REVIEWER_COMMENT_ID))

    def test_a_refused_bounce_keeps_its_park(self) -> None:
        # A park posts its notice and leaves the flags in memory, so the
        # bounce owes the write even though it is not bouncing: without it
        # the next tick reads an issue nothing is waiting on and pushes the
        # very commit this one refused.
        gh, issue = self._seed_stranded_bounce()

        mocks = self._bounced(gh, issue, tree_readable=False)

        mocks[PUSH_BRANCH].assert_not_called()
        pinned = gh.pinned_data(fixing.ISSUE)
        self.assertTrue(pinned[fixing.AWAITING_HUMAN])
        self.assertEqual(
            pinned[fixing.PARK_REASON], support.PARK_MEASUREMENT_FAILED,
        )
        self.assertEqual(gh.label_history, [])

    def _bounced(self, gh, issue, **run_options):
        run_options.setdefault("branch_ahead_behind", (1, 0))
        return self._run_stranded_bounce(
            gh, issue, fixing.TEMP_ROOT, **run_options,
        )


class StrandedRaceTest(
    unittest.TestCase, fixing._StrandedFixingFixtureMixin,
):
    """A pull request somebody moved between the proof and the push.

    The stranded probe fetches, proves the branch ahead of the remote and not
    behind it, and hands that head on: it is what the push replaces. Left for
    the gate to read afterwards, a head somebody landed in between becomes the
    lease and is force-overwritten by work proved against the head it used to
    be on.
    """

    def test_a_head_moved_after_the_proof_refuses(self) -> None:
        gh, issue = self._seed_stranded_bounce()
        gh.get_pr(fixing.PR_NUMBER).head.sha = MOVED_PUBLICATION

        mocks = self._bounced(gh, issue)

        self._pushes(mocks).assert_not_called()
        self.assertEqual(gh.label_history, [])
        pinned = gh.pinned_data(ISSUE)
        self.assertTrue(pinned[fixing.AWAITING_HUMAN])
        self.assertEqual(
            pinned[fixing.PARK_REASON], support.PARK_MEASUREMENT_FAILED,
        )

    def test_the_head_it_proved_is_the_lease(self) -> None:
        # What says the refusal above is about the disagreement rather than
        # about the naming refusing every bounce: the ordinary world publishes,
        # pinned to the head the proof was taken against.
        gh, issue = self._seed_stranded_bounce()

        mocks = self._bounced(gh, issue)

        self.assertEqual(
            self._pushes(mocks).call_args.kwargs[LEASE], fixing.PR_HEAD_SHA,
        )

    def _pushes(self, mocks):
        """The seam both of these are decided at."""
        return mocks[PUSH_BRANCH]

    _bounced = StrandedBounceTest._bounced


class AbsentCheckoutRetryTest(
    unittest.TestCase, fixing._StrandedFixingFixtureMixin,
):
    """A frozen pair with no checkout to be measured in stops the tick."""

    def test_it_parks_rather_than_bouncing(self) -> None:
        # Failing open here means the stage runs: the no-feedback bounce
        # relabels to `validating` and hands the reviewer a head the pull
        # request never received, on a candidate nobody has read the size of.
        # Nothing this process can do repairs it -- the commit is on a host
        # this one is not -- so what the refusal owes is a human.
        gh, issue = self._seed_stranded_bounce()

        mocks = self._absent(gh, issue)

        mocks[PUSH_BRANCH].assert_not_called()
        mocks[COUNT_ADDED_LINES].assert_not_called()
        self.assertEqual(gh.label_history, [])
        pinned = gh.pinned_data(ISSUE)
        self.assertTrue(pinned[fixing.AWAITING_HUMAN])
        self.assertEqual(
            pinned[fixing.PARK_REASON], support.PARK_MEASUREMENT_FAILED,
        )
        self.assertEqual(pinned[support.KEY_CANDIDATE_SHA], MEASURED_CANDIDATE_SHA)

    def test_it_says_so_once(self) -> None:
        # A checkout that stays gone must not put a fresh notice on the
        # thread every poll and bury the first one.
        gh, issue = self._seed_stranded_bounce()

        self._absent(gh, issue)
        posted = len(gh.posted_comments)
        self._absent(gh, issue)

        self.assertEqual(len(gh.posted_comments), posted)

    def _absent(self, gh, issue):
        """One tick whose recorded pair has no checkout on this host."""
        gh.seed_state(ISSUE, **{
            **gh.pinned_data(ISSUE), **recorded_generation(),
        })
        return self._run_stranded_bounce(
            gh, issue, ABSENT_WORKTREE, branch_ahead_behind=(1, 0),
        )


def _pinned(scenario) -> dict:
    """The pinned comment this issue is carrying now."""
    return scenario.github.pinned_data(ISSUE)


class _RefusesTheRelabel:
    """The label write the hold makes last, and the window it opens."""

    def __call__(self, *called, **options):
        raise RuntimeError(RELABEL_REJECTED)


class PublishedFixCandidateTest(unittest.TestCase, _SizeGateFixtureMixin):
    """The commit a fix route read is the commit its push is about.

    The route reads the post-agent head to decide there is anything to publish
    at all, and the gate proves the checkout again before it measures. Between
    the two reads the worktree is writable, so the two have to be one decision
    -- otherwise a commit landing in that window is measured, pushed, and
    receipted while the route reports the fix it read as published.
    """

    def test_a_fix_publishes_the_head_it_read(self) -> None:
        scenario = self._seed_fix_round()

        mocks = self._run_fix_round(scenario)

        self.assertEqual(
            mocks[PUSH_BRANCH].call_args.kwargs[REVISION], SHA_AFTER,
        )

    def test_a_head_moved_between_the_reads_stops(self) -> None:
        scenario = self._seed_fix_round()

        mocks = self._run_fix_round(
            scenario, candidate_commit=support.FrozenCommit(sha=MOVED_HEAD),
        )

        mocks[COUNT_ADDED_LINES].assert_not_called()
        mocks[PUSH_BRANCH].assert_not_called()
        self.assertEqual(scenario.github.label_history, [])
        pinned = _pinned(scenario)
        self.assertTrue(pinned[fixing.AWAITING_HUMAN])
        self.assertEqual(
            pinned[fixing.PARK_REASON], support.PARK_MEASUREMENT_FAILED,
        )


class AdjudicatedRoundTest(unittest.TestCase, _SizeGateFixtureMixin):
    """What a fix loop owes when its candidate goes to adjudication instead."""

    def test_a_held_fix_owes_its_round_to_the_report(self) -> None:
        # The gate holding a candidate is not a park: the commit is on the
        # branch and a `single` verdict publishes it from there, so the head
        # the reviewer rejected is superseded either way and the round is
        # spent. What the round owes its REPORT holds when: that report is on
        # the pinned comment and not on the pull request, so nothing the write
        # completing its publication has to apply may be applied ahead of it.
        # Both roads read the same frozen pair, so neither can count twice.
        for route, opened, spent in (
            # The in_review route: the previous round was APPROVED, so the fix
            # starts a fresh count.
            ("in_review", {}, 0),
            # `pending_fix_at` unset is the reviewer's own CHANGES_REQUESTED
            # round: still the same review cycle, so the counter advances and
            # `MAX_REVIEW_ROUNDS` goes on meaning what it says.
            ("validating", {PENDING_FIX_AT: None, REVIEW_ROUND: 2}, 3),
        ):
            with self.subTest(route=route):
                scenario = self._seed_fix_round(**opened)

                with patch.object(config, support.MAX_ADDED_LINES, CEILING):
                    self._run_fix_round(
                        scenario, added_lines=PAST_THE_CEILING,
                    )

                recorded = _delivery_state.read_delivered_report(
                    scenario.github.read_pinned_state(scenario.issue),
                )
                self.assertIn((REVIEW_ROUND, spent), recorded.spends)
                self.assertNotEqual(_pinned(scenario)[REVIEW_ROUND], spent)

    def test_the_held_record_survives_the_relabel(self) -> None:
        # The hold's last act is the relabel, and there is a window after it:
        # the issue belongs to the adjudication and this caller still has a
        # write to make. So what the round owes is durable ahead of the gate,
        # on the record its report was written to -- a crash in that window
        # loses nothing, and the write that finally publishes the report is
        # the one that applies it.
        scenario = self._seed_fix_round(**{
            PENDING_FIX_AT: None, REVIEW_ROUND: 2,
        })
        github = scenario.github

        with patch.object(config, support.MAX_ADDED_LINES, CEILING), patch.object(
            github, SET_WORKFLOW_LABEL, _RefusesTheRelabel(),
        ), self.assertRaises(RuntimeError):
            self._run_fix_round(scenario, added_lines=PAST_THE_CEILING)

        recorded = _delivery_state.read_delivered_report(
            github.read_pinned_state(scenario.issue),
        )
        self.assertIn((REVIEW_ROUND, 3), recorded.spends)

    def test_a_parked_reading_spends_nothing(self) -> None:
        # A reading nobody could take stops the tick with a generation on the
        # pinned comment too, and that one IS a park: the developer's work is
        # still pending and its round is not spent.
        scenario = self._seed_fix_round()

        self._run_fix_round(
            scenario, added_lines=MeasurementFailure.DIFF_FAILED,
        )

        pinned = _pinned(scenario)
        self.assertEqual(pinned[REVIEW_ROUND], 1)
        self.assertIsNotNone(pinned.get(PENDING_FIX_AT))
