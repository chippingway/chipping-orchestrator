# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from orchestrator.git import commands as _git_commands
from orchestrator.git.base_sync import pre_pr as _base_sync_pre_pr
from orchestrator.git.measurement.models import FrozenCommit
from tests.support.publication import LandingPush
from tests.workflow.fixtures import (
    LABEL_VALIDATING,
    _agent,
)
from tests.workflow.stages.conflicts import (
    report_debt_crashes as _crashes,
    round_record_support as _round_records,
)
from tests.workflow.stages.conflicts.conflicts_test_support import (
    CONFLICT_PR_HEAD_SHA,
    MOVED_PR_HEAD_SHA,
    RESOLVED_HEAD_SHA,
    _ResolvingConflictMixin,
)
from tests.workflow.stages.conflicts.dispatch_support import _DispatchedConflictMixin
from tests.workflow.stages.conflicts.report_debt_support import DEBT, owed

CONFLICT_ISSUE = 200

# The commit the recovered push publishes, and the one the rebase behind it
# rewrites it into: two pushes in one tick carry two commits, which is what
# tells a second push from the receipt of the first.
RECOVERED_CANDIDATE = "1ec04e5e" * 5
REBASED_CANDIDATE = "5eba5ed1" * 5
# What the checkout stands on once the rebase has rewritten the recovered
# commit, which is what the second push is named against and leased by.
REBASED_SHA = REBASED_CANDIDATE

CONFLICT_PR = 800
PUSH_BRANCH = "_push_branch"

# What each round a settled receipt can name is recorded as.
BASE_REBASED_CLEAN = "base_rebased_clean"
AGENT_RESOLVED = "agent_resolved"
RECOVERED_PUSH = "recovered_push"
DRIFT_RESOLVED = "drift_resolved"

# The pinned code-publication receipt, as the size gate's write leaves it, and
# the one a round that published the resolved head over the pull request's
# head leaves: that commit, the head it replaced, and the pull request.
PUBLISHED_SHA = "implementing_published_sha"
PUBLISHED_LEASE = "implementing_published_lease"
PUBLISHED_PR = "implementing_published_pr"
PROVED = (RESOLVED_HEAD_SHA, CONFLICT_PR_HEAD_SHA, CONFLICT_PR)

# The head a recovered push that precedes a rebase leaves in the gate's write.
PREAMBLE_SHA = "conflict_preamble_sha"

# The approval the gate writes ahead of its push: the head it is leased
# against, and what the route owes once the push lands.
APPROVED_LEASE = "late_approved_lease"
LATE_SPENDS = "late_spends"

# The park a proved debt with no room on the pinned comment is held under,
# and the room a human trimming that comment leaves once the debt is on it.
UNRECORDED_DEBT = "unrecorded_report_debt"
ROOM_MADE = 1_000

# What `git rev-list --count HEAD..origin/<base>` answers for a branch the
# recovered push leaves still behind its base.
BEHIND_BASE = "2\n"


def _assert_completed_round(test_case, github) -> None:
    state = github.pinned_data(CONFLICT_ISSUE)
    test_case.assertEqual(state.get("review_round"), 0)
    test_case.assertEqual(state.get("conflict_round"), 1)
    test_case.assertIn("last_conflict_resolved_at", state)


def _assert_combined_round_event(test_case, github) -> None:
    rounds = [
        event
        for event in github.recorded_events
        if event.get("event") == "conflict_round" and event.get("action") == "incremented"
    ]
    test_case.assertEqual(len(rounds), 1)
    test_case.assertEqual(rounds[0].get("outcome"), "base_rebased_clean")


class ResolvingConflictRecoveryPushTest(unittest.TestCase, _ResolvingConflictMixin):
    """Drive `_handle_resolving_conflict` through the crash-recovery push
    branches: an unpushed local commit ships on the next tick, a failed
    recovery push parks, and a recovered push onto a stale base falls
    through to the rebase path for a single combined round.
    """

    def test_recovery_pushes_local_commits(self) -> None:
        # Crash recovery: a previous tick committed a conflict resolution
        # but crashed before `_push_branch` returned (or before the post-
        # push state write landed). The next tick must push the local
        # commit and complete the round, NOT treat it as "no work needed"
        # and flip to validating with the resolution unpushed.
        gh, issue, _ = self._seed()

        merge_mock = MagicMock(return_value=(True, []))
        # Before the recovered push the handler probes whether the
        # worktree is still behind base via `git rev-list --count
        # HEAD..origin/<base>` -- the reading is the same either side of a
        # push, and taken first it says which round a held candidate would
        # owe. The crash-recovery scenario this test exercises has HEAD
        # already on base, so the probe returns 0 and the handler takes the
        # fast path to validating without a follow-up rebase.
        git_on_base = MagicMock(
            return_value=MagicMock(returncode=0, stdout="0\n", stderr=""),
        )

        with (
            patch.object(_base_sync_pre_pr, "_rebase_base_into_worktree", merge_mock),
            patch.object(_git_commands, "_git", git_on_base),
        ):
            mocks = self._run_resolving_conflict(
                gh,
                issue,
                run_agent=_agent(),
                push_branch=True,
                # HEAD ahead of `origin/<branch>` by one commit (the
                # unpushed resolution); not behind.
                branch_ahead_behind=(1, 0),
                # The recovered head this stage reads and the commit the gate
                # proves the checkout to are one read of one worktree, so the
                # push, the receipt, and the round all name the same commit.
                head_shas=[RESOLVED_HEAD_SHA, RESOLVED_HEAD_SHA],
            )
        # Recovered work pushed; rebase NOT attempted (we already have a
        # resolution waiting to ship).
        mocks[PUSH_BRANCH].assert_called_once()
        merge_mock.assert_not_called()
        # No agent spawn -- the recovery is a pure push, the dev already
        # produced the commit on the previous tick.
        mocks["run_agent"].assert_not_called()
        # Round completed: counter incremented, label flipped, marker
        # stamped exactly as on the happy-path resolve. The recovered
        # push hands straight back to `validating`; the single docs
        # pass is deferred to the post-approval hop.
        _assert_completed_round(self, gh)
        self.assertIn((CONFLICT_ISSUE, "workflow:validating"), gh.label_history)
        self.assertNotIn((CONFLICT_ISSUE, "workflow:documenting"), gh.label_history)
        # Nothing on this road says whether the commits it found ever had a
        # report, so the head the push left is owed one from the head the
        # push was leased against.
        self.assertEqual(
            self._pinned(gh).get(DEBT), owed(self, CONFLICT_PR_HEAD_SHA, RESOLVED_HEAD_SHA),
        )

    def test_unpushed_recovery_push_failure_parks(self) -> None:
        # Recovery push fails (e.g. force-with-lease lease miss because
        # the remote actually moved). Park rather than silently flipping
        # to validating with an unsynced local SHA.
        gh, issue, _ = self._seed()

        merge_mock = MagicMock(return_value=(True, []))
        # The behind-base probe runs BEFORE the push, because the round a
        # held candidate would owe has to be decided while the gate can still
        # be told about it. On base here, so this push would have completed
        # the round had it landed.
        git_on_base = MagicMock(
            return_value=MagicMock(returncode=0, stdout="0\n", stderr=""),
        )

        with (
            patch.object(_base_sync_pre_pr, "_rebase_base_into_worktree", merge_mock),
            patch.object(_git_commands, "_git", git_on_base),
        ):
            mocks = self._run_resolving_conflict(
                gh,
                issue,
                run_agent=_agent(),
                push_branch=False,
                branch_ahead_behind=(1, 0),
                head_shas=[RESOLVED_HEAD_SHA, RESOLVED_HEAD_SHA],
            )
        mocks[PUSH_BRANCH].assert_called_once()
        merge_mock.assert_not_called()
        self.assertTrue(gh.pinned_data(CONFLICT_ISSUE).get("awaiting_human"))
        self.assertNotIn((CONFLICT_ISSUE, "workflow:validating"), gh.label_history)
        # A push that never landed published no head a report is owed for.
        self.assertNotIn(DEBT, self._pinned(gh))

    def test_stale_base_falls_through_to_rebase(self) -> None:
        # The `fixing` drift router
        # (`_reconcile_parked_fixing`) reroutes here
        # when a stuck `push_failed` / `agent_timeout` park has
        # UNPUSHED FIX COMMITS on a base that has since advanced. The
        # recovered-push fast path would publish the fix to the PR
        # branch and flip straight to `validating` -- but the branch
        # is still behind base. Probe behind-base after the push and
        # fall through to the rebase path so the same tick integrates
        # base and consumes exactly ONE `conflict_round` for the
        # combined push+rebase reconciliation. Without this, the PR
        # would be republished still-behind-base and the round counter
        # would burn a slot toward `MAX_CONFLICT_ROUNDS` without ever
        # attempting the base rebase the reroute was meant to perform.
        gh, issue, _ = self._seed()

        # Clean rebase that actually moved HEAD (recovered push +
        # rebase pushes a different SHA than the recovered SHA).
        merge_mock = MagicMock(return_value=(True, []))
        # Probe says still 2 commits behind base after the recovered
        # push, forcing the fall-through.
        git_behind_base = MagicMock(
            return_value=MagicMock(returncode=0, stdout="2\n", stderr=""),
        )

        with (
            patch.object(_base_sync_pre_pr, "_rebase_base_into_worktree", merge_mock),
            patch.object(_git_commands, "_git", git_behind_base),
        ):
            mocks = self._run_resolving_conflict(
                gh,
                issue,
                run_agent=_agent(),
                # The recovered push lands, so the pull request stands on
                # what it published when the rebase behind it leases its own
                # push against the head that push left.
                push_branch=LandingPush(gh, self.pr_number),
                # Recovered push first, leased against the head the pull
                # request was standing on; then the rebased-head push, leased
                # against the head this stage reads back before it rebases.
                # Reading by reading: the recovered push names the commit it
                # publishes, then the rebase path compares its own before and
                # after, then the audit emit records what it left.
                branch_ahead_behind=(1, 0),
                head_shas=[
                    RECOVERED_CANDIDATE, RECOVERED_CANDIDATE,
                    REBASED_SHA, REBASED_SHA,
                ],
                # The rebase rewrites the recovered commit, so the second
                # push publishes a different one -- which is why it is a
                # push at all rather than the receipt of the first being
                # recognized. Reading by reading: the recovered push
                # measures it and then proves the checkout still on it, and
                # only the rebase behind that moves the head.
                candidate_commit=(
                    FrozenCommit(sha=RECOVERED_CANDIDATE),
                    FrozenCommit(sha=RECOVERED_CANDIDATE),
                    FrozenCommit(sha=REBASED_CANDIDATE),
                ),
            )

        # Both the recovered push AND the rebased-head push fired this
        # tick; the merge attempt ran in between.
        self.assertEqual(mocks[PUSH_BRANCH].call_count, 2)
        merge_mock.assert_called_once()
        # No agent spawn -- the rebase was clean.
        mocks["run_agent"].assert_not_called()
        # Single conflict_round increment for the combined push+rebase
        # reconciliation, NOT one per push.
        _assert_completed_round(self, gh)
        # The combined round outcome is the rebase path's
        # `base_rebased_clean`, not the fast-path `recovered_push`.
        _assert_combined_round_event(self, gh)
        # Hand back to validating after the rebase landed.
        self.assertIn((CONFLICT_ISSUE, "workflow:validating"), gh.label_history)
        self.assertNotIn((CONFLICT_ISSUE, "workflow:documenting"), gh.label_history)
        # Two pushes, one debt: the recovered push records what it owes and
        # the rebase behind it carries that onto the head it published, still
        # owed from the head the pull request stood on before either.
        self.assertEqual(
            self._pinned(gh).get(DEBT), owed(self, CONFLICT_PR_HEAD_SHA, REBASED_SHA),
        )

    def test_a_preamble_push_owes_its_own_report(self) -> None:
        # A recovered push that lands behind base leaves the round to the
        # rebase, but not the debt: that rebase can end the tick without a
        # tail of its own. Here it moves nothing -- the behind-base probe
        # failed closed -- so the no-op flip hands `validating` the head the
        # recovered push published, and that head is owed its report all the
        # same.
        gh, issue = self._seed()[:2]

        self._run_with_merge(
            gh,
            issue,
            merge_succeeded=True,
            behind_base="2\n",
            push_branch=LandingPush(gh, self.pr_number),
            branch_ahead_behind=(1, 0),
            head_shas=(RECOVERED_CANDIDATE,),
            candidate_commit=FrozenCommit(sha=RECOVERED_CANDIDATE),
        )

        self.assertEqual(
            (_round_records._outcomes_of(gh), gh.label_history, self._pinned(gh).get(DEBT)),
            (
                ["base_up_to_date"],
                [(CONFLICT_ISSUE, LABEL_VALIDATING)],
                owed(self, CONFLICT_PR_HEAD_SHA, RECOVERED_CANDIDATE),
            ),
        )


class ResolvingConflictInterruptedHandoffTest(
    unittest.TestCase, _DispatchedConflictMixin,
):
    """A round whose push landed and whose hand to `validating` did not.

    The push's own write carries the settled round and the publication receipt
    beside it, so a later tick finishes the round from them -- and the report
    debt the rewrite owes has to come through with it, since `validating` is
    where that report is asked for.
    """

    def test_an_interrupted_handoff_keeps_the_debt(self) -> None:
        # Three windows past a push that landed. Ending before the gate's own
        # write leaves only the approval it took ahead of the push -- the
        # commit, the head it was leased against, and the round it owes --
        # which the reconciliation ahead of the next tick's handler pays by
        # republishing that same commit under a lease, writing the receipt
        # against the ORIGINAL head. Ending on the debt's own write leaves the
        # gate's write, and the next tick reads the debt off its receipt.
        # Ending at the relabel leaves the debt already down, since it is
        # written ahead of the label that hands the head on. The original
        # lease stays on the comment through every one, and the next tick
        # hands `validating` the head with its debt, counting the round once.
        owed_debt = owed(self, CONFLICT_PR_HEAD_SHA, RESOLVED_HEAD_SHA)
        for crash, owed_at_crash, republished in (
            (_crashes.dying_after_the_push, None, [RESOLVED_HEAD_SHA]),
            (_crashes.dying_on_the_debt, None, []),
            (_crashes.dying_on_the_handoff, owed_debt, []),
        ):
            with self.subTest(crash.__name__):
                gh = self._crashed(crash)
                self.assertEqual(
                    self._left_by(gh), ([], CONFLICT_PR_HEAD_SHA, owed_at_crash),
                )
                self.assertEqual(
                    self._finished(gh),
                    (republished, [(CONFLICT_ISSUE, LABEL_VALIDATING)], 1, owed_debt),
                )

    def test_a_receipt_proves_what_a_round_owes(self) -> None:
        # Only a round that rewrote the head owes a debt, and only one the
        # publication receipt proves: the commit it names has to be the one
        # the round settled, on the pull request the issue pins, over a head
        # it replaced. A body edit's commit is the developer's own work. A
        # receipt naming another commit, another pull request, or no head it
        # replaced proves no rewrite of this stage's, so the round is handed
        # on and the reviewer road holds the report it finds to the head.
        cases = (
            (BASE_REBASED_CLEAN, PROVED, True),
            (AGENT_RESOLVED, PROVED, True),
            (RECOVERED_PUSH, PROVED, True),
            (DRIFT_RESOLVED, PROVED, False),
            (AGENT_RESOLVED, (MOVED_PR_HEAD_SHA, CONFLICT_PR_HEAD_SHA, CONFLICT_PR), False),
            (AGENT_RESOLVED, (RESOLVED_HEAD_SHA, CONFLICT_PR_HEAD_SHA, CONFLICT_PR + 1), False),
            (AGENT_RESOLVED, (RESOLVED_HEAD_SHA, None, CONFLICT_PR), False),
        )
        for outcome, receipt, owes in cases:
            with self.subTest(outcome=outcome, receipt=receipt):
                expected = owed(self, CONFLICT_PR_HEAD_SHA, RESOLVED_HEAD_SHA) if owes else None
                self.assertEqual(
                    self._settled_over(outcome, receipt), ([outcome], expected),
                )

    def _crashed(self, crash):
        """A clean round whose push lands and whose process ends in `crash`."""
        gh, issue = self._seed()[:2]
        with crash(gh):
            self._run_with_merge(
                gh, issue,
                merge_succeeded=True,
                head_shas=[CONFLICT_PR_HEAD_SHA, RESOLVED_HEAD_SHA],
                push_branch=LandingPush(gh, self.pr_number),
            )
        return gh

    def _left_by(self, gh) -> tuple:
        """What a crash left durable: relabels, the head the push was leased against, and the debt.

        The lease is read off the approval while one stands, and off the
        receipt once the gate has written it.
        """
        pinned = self._pinned(gh)
        lease = pinned.get(APPROVED_LEASE) or pinned.get(PUBLISHED_LEASE)
        return (gh.label_history, lease, pinned.get(DEBT))

    def _finished(self, gh) -> tuple:
        """The whole dispatched tick behind a crash: commits pushed, relabels, round, debt."""
        mocks = self._run_with_merge(
            gh, gh.get_issue(CONFLICT_ISSUE),
            fetched_branch_tip=RESOLVED_HEAD_SHA,
            head_shas=[RESOLVED_HEAD_SHA],
            push_branch=LandingPush(gh, self.pr_number),
        )[0]
        pinned = self._pinned(gh)
        return (
            [pushed.kwargs["revision"] for pushed in mocks[PUSH_BRANCH].call_args_list],
            gh.label_history, pinned.get("conflict_round"), pinned.get(DEBT),
        )

    def _settled_over(self, outcome: str, receipt: tuple) -> tuple:
        """The rounds a settled `outcome` is counted as over `receipt`, and the debt it leaves."""
        published, lease, number = receipt
        gh, issue = self._seed(extra_state={
            _round_records.SETTLED_OUTCOME: outcome,
            _round_records.SETTLED_SHA: RESOLVED_HEAD_SHA,
            PUBLISHED_SHA: published,
            PUBLISHED_LEASE: lease,
            PUBLISHED_PR: number,
        })[:2]
        gh.get_pr(self.pr_number).head.sha = RESOLVED_HEAD_SHA
        self._run_with_merge(gh, issue, head_shas=[RESOLVED_HEAD_SHA])
        return (_round_records._outcomes_of(gh), self._pinned(gh).get(DEBT))


class ResolvingConflictPreambleDebtTest(unittest.TestCase, _DispatchedConflictMixin):
    """The debt of a head a recovered push published ahead of a rebase.

    That push finishes no round, so no settled receipt brings a later tick
    back for it. What does is the head it hands the gate, written into the
    same write as the publication receipt when it lands -- or, where the
    process ended before that write, among the spends of the approval the gate
    took ahead of the push -- and read back once the receipt names it and the
    pull request still stands on it.
    """

    def test_a_crashed_preamble_keeps_its_debt(self) -> None:
        # The push landed and the process ended on the debt's own write. The
        # next tick finds the branch in sync on that head and rebases -- to
        # nothing, or onto a new head -- and either way hands `validating` a
        # debt owed from the head the pull request stood on before either
        # push. A pull request somebody has since moved off the head owes it
        # nothing, and that tick parks over the divergence with no debt.
        cases = (
            (
                "moved nothing",
                {},
                (LABEL_VALIDATING, None, owed(self, CONFLICT_PR_HEAD_SHA, RECOVERED_CANDIDATE)),
            ),
            (
                "rebased again",
                {"head_shas": (RECOVERED_CANDIDATE, RESOLVED_HEAD_SHA)},
                (LABEL_VALIDATING, None, owed(self, CONFLICT_PR_HEAD_SHA, RESOLVED_HEAD_SHA)),
            ),
            (
                "moved off",
                {"fetched_branch_tip": MOVED_PR_HEAD_SHA, "branch_ahead_behind": (0, 1)},
                (None, None, None),
            ),
        )
        for name, options, expected in cases:
            with self.subTest(name):
                gh = self._crashed_preamble()
                self.assertEqual(self._ticked_after(gh, **options), expected)

    def test_a_preamble_lost_before_its_receipt(self) -> None:
        # The push landed and the process ended before the gate wrote what it
        # paid, so neither the receipt nor the preamble head is on the comment
        # -- only the approval the gate took ahead of the push, carrying the
        # head it was leased against and the preamble head among the spends it
        # owes. The next tick's reconciliation pays that approval and writes
        # both against the original lease, and the stage behind it records the
        # debt from them before its rebase, which moves nothing, hands
        # `validating` the head.
        gh, issue = self._seed()[:2]
        with _crashes.dying_after_the_push(gh):
            self._behind_base(gh, issue)
        pinned = self._pinned(gh)
        self.assertEqual(
            (pinned.get(APPROVED_LEASE), pinned.get(LATE_SPENDS)),
            (CONFLICT_PR_HEAD_SHA, [[PREAMBLE_SHA, RECOVERED_CANDIDATE]]),
        )
        self.assertEqual((PUBLISHED_SHA in pinned, DEBT in pinned), (False, False))

        self.assertEqual(
            self._ticked_after(gh, candidate_commit=FrozenCommit(sha=RECOVERED_CANDIDATE)),
            (LABEL_VALIDATING, None, owed(self, CONFLICT_PR_HEAD_SHA, RECOVERED_CANDIDATE)),
        )

    def _crashed_preamble(self):
        """A recovered push that lands behind base, its process ending on the debt's write.

        What survives is the gate's own write: the receipt naming the pushed
        head, and that head beside it as the one still owed a debt.
        """
        gh, issue = self._seed()[:2]
        with _crashes.dying_on_the_debt(gh):
            self._behind_base(gh, issue)
        pinned = self._pinned(gh)
        self.assertEqual(
            (pinned.get(PREAMBLE_SHA), pinned.get(PUBLISHED_SHA), DEBT in pinned),
            (RECOVERED_CANDIDATE, RECOVERED_CANDIDATE, False),
        )
        return gh

    def _behind_base(self, gh, issue):
        """One tick whose recovered commit is ahead of the pull request and behind base, its push landing."""
        return self._run_with_merge(
            gh, issue,
            merge_succeeded=True,
            behind_base=BEHIND_BASE,
            branch_ahead_behind=(1, 0),
            head_shas=(RECOVERED_CANDIDATE,),
            candidate_commit=FrozenCommit(sha=RECOVERED_CANDIDATE),
            push_branch=LandingPush(gh, self.pr_number),
        )

    def _ticked_after(self, gh, **options) -> tuple:
        """The tick behind, over the head the preamble published: last relabel, preamble head, debt.

        The rebase moves nothing unless a case names the head it leaves.
        """
        run = {
            "merge_succeeded": True,
            "fetched_branch_tip": RECOVERED_CANDIDATE,
            "head_shas": (RECOVERED_CANDIDATE,),
            "push_branch": LandingPush(gh, self.pr_number),
            **options,
        }
        self._run_with_merge(gh, gh.get_issue(CONFLICT_ISSUE), **run)
        pinned = self._pinned(gh)
        relabelled = gh.label_history[-1][1] if gh.label_history else None
        return (relabelled, pinned.get(PREAMBLE_SHA), pinned.get(DEBT))


class ResolvingConflictUnrecordedDebtTest(unittest.TestCase, _DispatchedConflictMixin):
    """A proved rewrite whose report debt the pinned comment has no room for.

    Not a head nobody proved, which the reviewer road answers: a debt this
    stage owes and could not write down. Handed on without it, the reviewer
    road is given the report of the head the push replaced.
    """

    def test_a_debt_with_no_room_holds_the_handoff(self) -> None:
        # A comment the debt fills exactly takes it. One character short, the
        # round parks with nothing counted or relabelled and its settled round
        # left standing, and the tick after room is made records the debt and
        # hands the round on.
        owed_debt = owed(self, CONFLICT_PR_HEAD_SHA, RESOLVED_HEAD_SHA)
        handed = ([(CONFLICT_ISSUE, LABEL_VALIDATING)], 1, owed_debt)
        with self.subTest(room="exactly"):
            gh = self._near_the_limit(owed_debt, room=0)
            self.assertEqual(self._after_a_tick(gh), handed)
        with self.subTest(room="one short"):
            gh = self._near_the_limit(owed_debt, room=-1)
            self.assertEqual(self._after_a_tick(gh), ([], 0, None))
            self.assertEqual(self._held_by(gh), (UNRECORDED_DEBT, RESOLVED_HEAD_SHA))
            _crashes.leaving_room(gh, CONFLICT_ISSUE, {DEBT: owed_debt}, room=ROOM_MADE)
            self.assertEqual(self._after_a_tick(gh), handed)

    def test_a_preamble_with_no_room_holds_its_rebase(self) -> None:
        # The recovered push lands behind base with no room for its debt, so
        # the rebase behind it -- which here would move nothing and hand the
        # head on -- does not run: the round parks with the preamble head kept
        # in the gate's own write. The tick after room is made records the
        # debt from it before anything else, then rebases and hands it on.
        gh, issue = self._seed()[:2]
        owed_debt = owed(self, CONFLICT_PR_HEAD_SHA, RECOVERED_CANDIDATE)
        _crashes.leaving_room(gh, CONFLICT_ISSUE, {DEBT: owed_debt}, room=-1)
        self._behind_base(gh, issue)
        pinned = self._pinned(gh)
        self.assertEqual(
            (gh.label_history, pinned.get("park_reason"), pinned.get(PREAMBLE_SHA)),
            ([], UNRECORDED_DEBT, RECOVERED_CANDIDATE),
        )
        self.assertNotIn(DEBT, pinned)

        _crashes.leaving_room(gh, CONFLICT_ISSUE, {DEBT: owed_debt}, room=ROOM_MADE)

        self.assertEqual(
            self._ticked_after(gh, candidate_commit=FrozenCommit(sha=RECOVERED_CANDIDATE)),
            (LABEL_VALIDATING, None, owed_debt),
        )

    def _near_the_limit(self, debt: dict, *, room: int):
        """A settled rebase whose pinned comment has `room` characters left once `debt` is on it."""
        gh = self._seed(extra_state={
            _round_records.SETTLED_OUTCOME: BASE_REBASED_CLEAN,
            _round_records.SETTLED_SHA: RESOLVED_HEAD_SHA,
            PUBLISHED_SHA: RESOLVED_HEAD_SHA,
            PUBLISHED_LEASE: CONFLICT_PR_HEAD_SHA,
            PUBLISHED_PR: CONFLICT_PR,
        })[0]
        gh.get_pr(self.pr_number).head.sha = RESOLVED_HEAD_SHA
        _crashes.leaving_room(gh, CONFLICT_ISSUE, {DEBT: debt}, room=room)
        return gh

    def _after_a_tick(self, gh) -> tuple:
        """What the next dispatched tick leaves: relabels, round, and debt."""
        return self._finished(gh)[1:]

    def _held_by(self, gh) -> tuple:
        """The park a held round stands under, and the settled round still waiting for it."""
        pinned = self._pinned(gh)
        return (pinned.get("park_reason"), pinned.get(_round_records.SETTLED_SHA))

    _finished = ResolvingConflictInterruptedHandoffTest._finished

    _behind_base = ResolvingConflictPreambleDebtTest._behind_base

    _ticked_after = ResolvingConflictPreambleDebtTest._ticked_after


if __name__ == "__main__":
    unittest.main()
