# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What the size gate names and pins a conflict publication by, and refuses.

The conflict seams read the remote themselves and lease their force-push
against what they read, which makes them the callers that establish a head --
and the ones a reconciliation is reached through, since no developer ran on a
rebase or a recovered push. Both facts are the gate's terms rather than the
caller's alone: the head is compared against the publication this gate reads
for itself, and the reconciliation is what the switch has nothing left to say
about.

## The two readings of one head

A caller that establishes a head has pinned its own decision to it, and the
publication it is about is standing on a head this gate reads for itself.

A caller that establishes a head has pinned its own decision to it, and the
publication it is about is standing on a head this gate reads for itself.
Those are two readings of one fact -- the tip of the branch the push is going
onto -- so the gate compares them instead of preferring either. Where they
disagree the pull request moved between the two, which is somebody else's push
landing mid-tick: freezing either would record a head that is not what the
branch would be pushed onto, and an oversized candidate would be persisted and
routed to the adjudication on evidence already overtaken.

## The switch, and what "no developer ran" does not buy

`DECOMPOSE=off` decides new work and nothing else, and every seam here IS new
work: a rebase and a recovered push are each taken with no agent behind them,
but nothing on the pinned comment asked for either commit to be read. So both
of them publish unmeasured.

What the switch does not turn off is the naming and the lease. Those are the
caller's own claims -- the commit it read and means to publish, and the ref
tip it read off the remote -- so an install with the gate off still refuses a
checkout that moved and still pins its force-push, rather than pushing
whatever the checkout points at onto whatever the remote is standing on by
then.
"""
from __future__ import annotations

import unittest
from unittest.mock import patch

from orchestrator import config
from orchestrator.git.measurement.models import FrozenCommit
from tests.support.fakes import FakeComment, FakeUser
from tests.workflow.fixtures import MEASURED_CANDIDATE_SHA, _agent
from tests.workflow.stages.conflicts.conflict_resume_test_support import (
    _MovesThePullRequest,
)
from tests.workflow.stages.conflicts.conflicts_test_support import (
    CONFLICT_PR_HEAD_SHA,
    MOVED_PR_HEAD_SHA,
    RESOLVED_HEAD_SHA,
    _ResolvingConflictMixin,
)

CONFLICT_ISSUE = 200
CONFLICT_FILE = "a.py"

# The head this stage reads before it rebases, which is the head its pull
# request is standing on unless a case moves one of them.
BEFORE_HEAD = CONFLICT_PR_HEAD_SHA
MERGED_HEAD = RESOLVED_HEAD_SHA

# A head a caller established that is no whole object id, so nothing a later
# tick could compare anything to.
ABBREVIATED_HEAD = "be40e5ba"

# The commit an interrupted tick left on the branch and never pushed, and what
# the checkout stands on once something has moved it out from under the
# reading this stage took.
RECOVERED_HEAD = "1ec04e5e" * 5
MOVED_CHECKOUT = "m0vedc0m" * 5

# What `git rev-list --count HEAD..origin/<base>` answers for a branch whose
# recovered commits already carry their base, which is the reading that makes
# the recovered push a round of its own.
ON_BASE = "0\n"

EVENT = "event"
ACTION = "action"
INCREMENTED = "incremented"
CONFLICT_ROUND_EVENT = "conflict_round"
SHA = "sha"

RUN_AGENT = "run_agent"
PUSH_BRANCH = "_push_branch"

LABEL_VALIDATING = "workflow:validating"
LABEL_DECOMPOSING = "workflow:decomposing"

AWAITING_HUMAN = "awaiting_human"
CONFLICT_ROUND = "conflict_round"
LAST_ACTION_COMMENT_ID = "last_action_comment_id"
PARK_REASON = "park_reason"

# The reply that unsticks a parked rebase, and who left it.
HUMAN_REPLY_ID = 2000
HUMAN_LOGIN = "alice"
DEV_SESSION = "dev-sess"
PARK_MEASUREMENT_FAILED = "late_measurement_failed"
KEY_CANDIDATE_SHA = "late_candidate_sha"

DECOMPOSE = "DECOMPOSE"
MAX_ADDED_LINES = "MAX_ADDED_LINES"
COUNT_ADDED_LINES = "_count_added_lines"

# A ceiling the seeded diff is over, so a measured candidate would be held and
# an unmeasured one goes out.
CEILING = 5
PAST_THE_CEILING = 6

# What git answers a force-push pinned to a head the ref has moved off.
_LEASE_REJECTS = False
# The two keywords a gated push names its commit and pins its ref by.
REVISION = "revision"
LEASE = "force_with_lease"


class _ResolvedTickMixin(_ResolvingConflictMixin):
    """One conflict tick, seeded and run as the case it is about needs it.

    The seed rides with the run because the pull request a case is about is
    part of what it seeds: a head other than the one this stage reads is the
    whole premise of the refusals below.
    """

    def _clean_rebase(
        self, *, before: str = BEFORE_HEAD, pr_head: str = "", **run_options
    ):
        """One clean base rebase, pushed under the head this stage read."""
        return self._resolved(
            pr_head,
            merge_succeeded=True,
            head_shas=[before, MERGED_HEAD],
            push_branch=True,
            **run_options,
        )

    def _agent_resolution(self, *, pr_head: str = "", push_branch=True):
        """One dev-resolved conflict, pushed under the same read head."""
        return self._resolved(
            pr_head,
            merge_succeeded=False,
            conflicted_files=[CONFLICT_FILE],
            head_shas=[BEFORE_HEAD, MERGED_HEAD],
            push_branch=push_branch,
        )

    def _resolved(self, pr_head: str, **run_options):
        """Seed one conflict issue, run a tick over it, report both ends.

        The seed rides with the run because the pull request a case is about
        is part of what it seeds: a head other than the one this stage reads
        is the whole premise of the refusals here.
        """
        github, issue = self._seed()[:2]
        if pr_head:
            github.get_pr(self.pr_number).head.sha = pr_head
        return github, self._run_with_merge(github, issue, **run_options)[0]

    def _recovered_push(self, *, pr_head: str = "", **run_options):
        """One crash-recovered commit, ahead of a pull request on its base."""
        github, issue = self._seed()[:2]
        if pr_head:
            github.get_pr(self.pr_number).head.sha = pr_head
        run_options.setdefault(
            "candidate_commit", FrozenCommit(sha=RECOVERED_HEAD),
        )
        run_options.setdefault(
            "head_shas", [RECOVERED_HEAD, RECOVERED_HEAD],
        )
        return github, self._run_with_merge(
            github, issue,
            branch_ahead_behind=(1, 0),
            behind_base=ON_BASE,
            push_branch=True,
            **run_options,
        )[0]

    def _pushes(self, mocks):
        """The seam every one of these cases is decided at."""
        return mocks[PUSH_BRANCH]

    def _assert_refused(self, github, mocks) -> None:
        """Nothing pushed, nothing relabelled, and a human asked for."""
        self._pushes(mocks).assert_not_called()
        self.assertNotIn(
            (CONFLICT_ISSUE, LABEL_VALIDATING), github.label_history,
        )
        pinned = github.pinned_data(CONFLICT_ISSUE)
        self.assertTrue(pinned[AWAITING_HUMAN])
        self.assertEqual(pinned[PARK_REASON], PARK_MEASUREMENT_FAILED)


class ResolvingConflictHeadAgreementTest(
    unittest.TestCase, _ResolvedTickMixin,
):
    """A push whose two readings of its publication's head disagree."""

    def test_a_moved_publication_refuses_a_rebase(self) -> None:
        # The clean rebase leases its force-push against the head it read out
        # of the checkout. Preferring that over the head the pull request is
        # standing on NOW would freeze a tip the branch has already left, and
        # a candidate past the ceiling would be routed to the adjudication
        # against a publication nobody measured it on.
        github, mocks = self._clean_rebase(pr_head=MOVED_PR_HEAD_SHA)

        self._assert_refused(github, mocks)

    def test_a_moved_publication_refuses_a_fix(self) -> None:
        # The same for the other conflict seam: an agent resolution is
        # leased against the pre-rebase head too, so it owes the same
        # agreement before anything is measured or pushed.
        github, mocks = self._agent_resolution(pr_head=MOVED_PR_HEAD_SHA)

        self._assert_refused(github, mocks)

    def test_a_moved_publication_refuses_a_recovery(self) -> None:
        # The third seam, and the one that named no head at all until the
        # comparison started carrying its own tip. A recovered push is
        # licensed by "ahead of the remote and not behind it", which is a
        # claim about the ref the fetch a line earlier put there -- so that
        # ref is what it must be pinned to. Left unnamed, a foreign push
        # landing between that reading and the gate becomes the head the
        # entry freezes AND the lease the force-push is pinned to: the
        # commits an interrupted tick left are measured, published over
        # somebody else's work, and handed to the reviewer as a resolved
        # round.
        moved = self._recovered_push(pr_head=MOVED_PR_HEAD_SHA)

        moved[1][COUNT_ADDED_LINES].assert_not_called()
        self.assertNotIn(
            (CONFLICT_ISSUE, LABEL_DECOMPOSING), moved[0].label_history,
        )
        self._assert_refused(*moved)

    def test_an_unreadable_divergence_refuses(self) -> None:
        # The reading the head comparison rests on. A ref nothing could
        # resolve and a comparison git refused both answer zero and zero,
        # which is what an in-sync branch answers -- so read as one, a stale
        # worktree is rebased, spawned over, and force-pushed on evidence
        # nobody took.
        unread = self._clean_rebase(branch_divergence_readable=False)

        unread[1][COUNT_ADDED_LINES].assert_not_called()
        unread[1][RUN_AGENT].assert_not_called()
        self._pushes(unread[1]).assert_not_called()
        self.assertNotIn(
            (CONFLICT_ISSUE, LABEL_VALIDATING), unread[0].label_history,
        )
        self.assertTrue(unread[0].pinned_data(CONFLICT_ISSUE)[AWAITING_HUMAN])
        self.assertIn(
            "could not be read", unread[0].posted_comments[-1][1],
        )

    def test_a_head_that_is_no_object_id_refuses(self) -> None:
        # Not dropped in favour of the read head, which is what a fallback
        # would do: a caller that established a head made its own decision on
        # it, and pinning the push to a fact that decision was never taken
        # over is the substitution this comparison exists to stop.
        github, mocks = self._clean_rebase(before=ABBREVIATED_HEAD)

        self._assert_refused(github, mocks)

    def test_agreeing_heads_publish(self) -> None:
        # The ordinary answer, and what says the two refusals above are about
        # a disagreement rather than about the comparison being made at all.
        github, mocks = self._clean_rebase()

        mocks[PUSH_BRANCH].assert_called_once()
        self.assertIn((CONFLICT_ISSUE, LABEL_VALIDATING), github.label_history)


class ResolvingConflictResumedRoundTest(
    unittest.TestCase, _ResolvedTickMixin,
):
    """A parked rebase resumed on a human reply, and the head it began at.

    The local head is no claim about the remote here: a parked worktree may be
    mid-rebase or already ahead of its publication. What the push replaces is
    the pull request's tip, so that is what this seam reads BEFORE the session
    resumes -- the agent is out for minutes, and a tip read afterwards is
    whatever landed while it was away.
    """

    def test_a_move_during_a_resume_refuses(self) -> None:
        # Left for the gate to read after the resume, the commit somebody
        # else pushed becomes the head the entry freezes AND the lease the
        # force-push is pinned to -- so the resolution is measured, published
        # over their work, and handed to the reviewer as a resolved round.
        moved, moved_seams = self._resumed(moved=MOVED_PR_HEAD_SHA)

        moved_seams[COUNT_ADDED_LINES].assert_not_called()
        self._assert_refused(moved, moved_seams)

    def test_a_resume_pins_the_head_it_read(self) -> None:
        # The ordinary answer, and what says the refusal above is about the
        # move rather than about the resume never being able to publish.
        resumed, resumed_seams = self._resumed()

        pushed = self._pushes(resumed_seams).call_args
        self.assertEqual(pushed.kwargs[REVISION], MEASURED_CANDIDATE_SHA)
        self.assertEqual(pushed.kwargs[LEASE], BEFORE_HEAD)
        self.assertIn(
            (CONFLICT_ISSUE, LABEL_VALIDATING), resumed.label_history,
        )

    def _resumed(self, *, moved: str = ""):
        """One parked rebase resumed on a fresh reply, run to its push."""
        github, issue = self._seed(extra_state={
            AWAITING_HUMAN: True,
            CONFLICT_ROUND: 1,
            LAST_ACTION_COMMENT_ID: 1000,
        })[:2]
        issue.comments.append(FakeComment(
            id=HUMAN_REPLY_ID,
            body="the conflict in foo.py is structural",
            user=FakeUser(HUMAN_LOGIN),
        ))
        resolved = _agent(session_id=DEV_SESSION, last_message="resolved")
        return github, self._run_with_merge(
            github, issue,
            head_shas=[BEFORE_HEAD, MERGED_HEAD],
            push_branch=True,
            run_agent_result=_MovesThePullRequest(
                github.get_pr(self.pr_number), moved, resolved,
            ) if moved else resolved,
        )[0]


class ResolvingConflictRecoveredCandidateTest(
    unittest.TestCase, _ResolvedTickMixin,
):
    """The commit a recovered push publishes is the round it records.

    The fast path reads the checkout's head for itself, stamps it as the SHA
    that resolved the round, and hands the issue back to `validating`. The
    gate proves that head again before it measures, and between the two reads
    the worktree is writable -- so what goes onto the pull request and what
    the round names have to be one decision.
    """

    def test_a_recovered_push_records_what_it_sent(self) -> None:
        github, mocks = self._recovered_push()

        pushed = mocks[PUSH_BRANCH].call_args.kwargs[REVISION]
        self.assertEqual(pushed, RECOVERED_HEAD)
        self.assertEqual(self._resolved_sha(github), pushed)

    def test_a_moved_checkout_refuses_a_recovery(self) -> None:
        # Unbound, the commit that landed in the window is measured, pushed,
        # and handed to the reviewer while the round stamps the head this
        # stage read -- so the pull request carries one commit and
        # `conflict_round` names another.
        github, mocks = self._recovered_push(
            candidate_commit=FrozenCommit(sha=MOVED_CHECKOUT),
        )

        self._assert_refused(github, mocks)

    def _resolved_sha(self, github):
        """The commit the round this push finished is recorded under."""
        rounds = [
            event
            for event in github.recorded_events
            if event.get(EVENT) == CONFLICT_ROUND_EVENT
            and event.get(ACTION) == INCREMENTED
        ]
        self.assertEqual(len(rounds), 1)
        return rounds[0].get(SHA)


class ResolvingConflictSwitchedOffTest(
    unittest.TestCase, _ResolvedTickMixin,
):
    """What the switch keeps a conflict publication out of, and what not."""

    def test_a_rebase_is_not_measured(self) -> None:
        # A rebase is work no developer ran for, and that is NOT what the
        # switch is asked: nothing on the record asked for this commit to be
        # read, so it is the new work `DECOMPOSE=off` publishes untouched.
        # Answered with the wider fact, an install that turned the gate off
        # has its resolutions measured anyway and a base that moved routes a
        # pull request nobody grew into an adjudication it never opted into.
        with patch.object(config, DECOMPOSE, False), patch.object(config, MAX_ADDED_LINES, CEILING):
            rebased = self._clean_rebase(added_lines=PAST_THE_CEILING)

        mocks = rebased[1]
        mocks[COUNT_ADDED_LINES].assert_not_called()
        self._pushes(mocks).assert_called_once()
        self.assertNotIn(
            (CONFLICT_ISSUE, LABEL_DECOMPOSING), rebased[0].label_history,
        )

    def test_a_recovered_push_is_not_measured_either(self) -> None:
        # The other seam that reaches the gate with no agent behind it: a
        # commit an interrupted tick left ahead of the remote. It has never
        # been read either, so the switch publishes it the same way.
        with patch.object(config, DECOMPOSE, False), patch.object(config, MAX_ADDED_LINES, CEILING):
            mocks = self._recovered_push(
                added_lines=PAST_THE_CEILING,
            )[1]

        mocks[COUNT_ADDED_LINES].assert_not_called()
        self._pushes(mocks).assert_called_once()

    def test_a_rebase_is_named_and_pinned(self) -> None:
        # What the switch does NOT turn off. Read as work with no terms
        # behind it, this push would carry whatever the checkout points at,
        # onto whatever the remote is standing on by then -- the two races
        # the naming and the lease exist to close.
        with patch.object(config, DECOMPOSE, False):
            mocks = self._clean_rebase()[1]

        pushed = mocks[PUSH_BRANCH].call_args
        self.assertEqual(pushed.kwargs[REVISION], MEASURED_CANDIDATE_SHA)
        self.assertEqual(pushed.kwargs[LEASE], BEFORE_HEAD)

    def test_a_retry_past_a_refusal_is_pinned(self) -> None:
        # An entry that refused persists no generation, deliberately: a
        # record naming a cycle and no candidate freezes nothing. So a tick
        # taken after the switch was turned off has nothing on the pinned
        # comment to tell a reconciliation from new work, and only what the
        # caller established says which it is.
        github = self._clean_rebase(pr_head=MOVED_PR_HEAD_SHA)[0]
        issue = github.get_issue(CONFLICT_ISSUE)
        self.assertNotIn(
            KEY_CANDIDATE_SHA, github.pinned_data(CONFLICT_ISSUE),
        )
        self._unparked(github)
        github.get_pr(self.pr_number).head.sha = BEFORE_HEAD

        with patch.object(config, DECOMPOSE, False):
            mocks = self._run_with_merge(
                github, issue,
                merge_succeeded=True,
                head_shas=[BEFORE_HEAD, MERGED_HEAD],
                push_branch=True,
            )[0]

        pushed = mocks[PUSH_BRANCH].call_args
        self.assertEqual(pushed.kwargs[REVISION], MEASURED_CANDIDATE_SHA)
        self.assertEqual(pushed.kwargs[LEASE], BEFORE_HEAD)

    def test_a_switched_off_fix_keeps_its_lease(self) -> None:
        # A dev-resolved conflict is the seam the switch really does bypass:
        # a developer ran, so it is new work rather than a reading this gate
        # already took. What it may not bypass is the LEASE -- the caller's
        # own claim about the ref it is rewriting, read off the remote by this
        # stage itself. Dropped here, `DECOMPOSE=off` becomes the setting that
        # turns a force-with-lease into a blind force-push.
        with patch.object(config, DECOMPOSE, False):
            mocks = self._agent_resolution()[1]

        self.assertEqual(
            mocks[PUSH_BRANCH].call_args.kwargs[LEASE], BEFORE_HEAD,
        )

    def test_a_switched_off_push_is_still_pinned(self) -> None:
        # What that lease buys, end to end: something landed on the pull
        # request while the dev was resolving, so the push git makes is
        # pinned to a head the ref no longer has and is rejected -- rather
        # than force-overwriting whoever landed, and rather than handing the
        # reviewer a branch nobody reconciled.
        with patch.object(config, DECOMPOSE, False):
            github, mocks = self._agent_resolution(
                pr_head=MOVED_PR_HEAD_SHA, push_branch=_LEASE_REJECTS,
            )

        self.assertEqual(
            mocks[PUSH_BRANCH].call_args.kwargs[LEASE], BEFORE_HEAD,
        )
        self.assertNotIn(
            (CONFLICT_ISSUE, LABEL_VALIDATING), github.label_history,
        )

    def _unparked(self, github) -> None:
        """Let the human answer the park the refused entry left behind."""
        pinned = github.pinned_data(CONFLICT_ISSUE)
        pinned[AWAITING_HUMAN] = False
        pinned.pop(PARK_REASON, None)
        github.seed_state(CONFLICT_ISSUE, **pinned)
