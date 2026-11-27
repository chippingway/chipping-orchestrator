# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The publication a squash-on-approval may rewrite, and what refuses it.

The squash force-pushes onto a pull request the remote already carries, so it
goes through the same post-publication gate the other nine pushes do -- the
measurement included, on the commit the squash MADE, since that is the object
the push would put on the pull request. The cases below are the refusals it
owes on the way in; `SquashSizeGateRealGitTest` beside them is the reading it
owes once there is a commit to take one over.

One of those refusals is a hole a lease cannot cover: CLOSING a pull request
does not move its branch, so a `--force-with-lease` still succeeds against a
publication nobody can merge. That is why the entry is asked while the branch
is still intact -- refused, the reviewer-approved commits stay exactly where
they are and the caller parks for a human.
"""
from __future__ import annotations

import subprocess
import unittest
from unittest.mock import patch

from orchestrator.git import commands as _git_commands
from orchestrator.git.measurement import commits as _measurement_commits
from orchestrator.git.verification import probes as _verification_probes
from tests.workflow.stages.validating import squash_git_support as squash_support
from tests.workflow.stages.validating.squash_gate_support import (
    SQUASH_PR_NUMBER,
    PublicationSeed,
    _squash_gate,
)

CLOSED = "closed"
MERGED = "merged"

# What the fixture's topic branch adds over the base: one line per commit,
# three commits. The squash collapses them into one commit whose diff from
# that base is the same three lines, which is what the gate counts.
ADDED_LINES = 3
UNDER_THE_CEILING = ADDED_LINES + 1
AT_THE_CEILING = ADDED_LINES
PAST_THE_CEILING = ADDED_LINES - 1
MAX_ADDED_LINES = "MAX_ADDED_LINES"

LABEL_DECOMPOSING = "workflow:decomposing"

AWAITING_HUMAN = "awaiting_human"
PARK_REASON = "park_reason"
PARK_MEASUREMENT_FAILED = "late_measurement_failed"
KEY_APPROVED_SHA = "late_approved_sha"
KEY_APPROVED_LEASE = "late_approved_lease"

_GIT_HARDENED = "_git_hardened"
# The reset a rollback makes, and the exit code a refused one reports. It
# takes the ref and the index and leaves the working tree alone: the squash
# has the same tree as the head it replaces, so nothing is restored by taking
# the worktree too except an edit somebody made while the rewrite ran.
_ROLLBACK_RESET = ("reset", "--mixed")
_GIT_FAILED = 128


# Which head read the squash's own id comes back on: the plan takes one
# before it runs, and this is the one after the squash commit.
_AFTER_THE_SQUASH = 1


# Which proof of the checkout the gate takes for itself: this owner reads it
# once before the gate, and the gate reads it again.
_THE_GATES_OWN_PROOF = 1


class _RefusesTheRollbackReset:
    """A worktree whose rollback will not go through.

    Everything else runs for real -- the soft reset the squash makes, the
    commit, the probes -- so what the case is about is the one command that
    decides whether the approved commit is still reachable.
    """

    def __init__(self) -> None:
        self._hardened = _git_commands._git_hardened

    def __call__(self, *args, **options):
        if args[:2] == _ROLLBACK_RESET:
            return subprocess.CompletedProcess(
                args=list(args), returncode=_GIT_FAILED,
                stdout="", stderr="rollback refused",
            )
        return self._hardened(*args, **options)


class _MovesPastTheFirstProof:
    """A checkout that answers the squash once and something else after.

    The race the candidate binding closes. The reading this owner takes before
    the gate agrees, so nothing refuses there; the one the gate takes for
    itself finds a commit somebody landed in between.
    """

    def __init__(self, fixture) -> None:
        self._fixture = fixture
        self._proofs = 0
        self._proves = _measurement_commits._prove_candidate_commit

    def __call__(self, worktree, revision):
        # A real commit, so the gate can measure and publish it: a sha no
        # object backs would refuse for the wrong reason.
        if self._proofs == _THE_GATES_OWN_PROOF:
            self._fixture._commits_over(self._proofs)
        self._proofs += 1
        return self._proves(worktree, revision)


class _CommitsOverTheSquash:
    """A head read that leaves a commit behind after it answers.

    The race this owner has to fail closed on: the squash's own id is read,
    and by the time the gate proves the checkout for itself something has
    committed over it. Only the read that follows the squash moves anything --
    the one the plan takes before it runs is answered as it is.
    """

    def __init__(self, fixture) -> None:
        self._fixture = fixture
        self._reads = 0
        # Bound before the seam is replaced, so answering does not re-enter
        # the double that is standing in for it.
        self._reads_the_head = _verification_probes._head_sha

    def __call__(self, worktree) -> str:
        answered = self._reads_the_head(worktree)
        if self._reads == _AFTER_THE_SQUASH:
            self._fixture._commits_over(self._reads)
        self._reads += 1
        return answered
KEY_CANDIDATE_SHA = "late_candidate_sha"
KEY_ADDITIONS = "late_additions"

MOVED_HEAD = "cafe1234" * 5
ABBREVIATED_HEAD = "cafe1234"


class SquashGateRealGitTest(
    squash_support.SquashGitFixtureMixin,
    unittest.TestCase,
):
    """Every reading the gate takes before a squash may rewrite anything."""

    def test_an_open_publication_is_pushed(self) -> None:
        # The ordinary answer, and what says the refusals below are about the
        # readings rather than about the gate refusing everything. The push is
        # named against the squashed commit and pinned to the head the entry
        # froze, which is the pre-squash head this owner read.
        original_head = self._head_sha()

        squash_run = self._squash()

        self.assertTrue(squash_run.success)
        self.assertEqual(squash_run.count, 3)
        pushed = squash_run.push_mock.call_args
        self.assertEqual(pushed.kwargs["revision"], self._head_sha())
        self.assertEqual(pushed.kwargs["force_with_lease"], original_head)

    def test_a_closed_publication_refuses_the_squash(self) -> None:
        # The hole the lease cannot cover: closing a pull request does not
        # move its branch, so a force-with-lease against the head this owner
        # read still succeeds -- onto a publication nobody can merge, over
        # commits a human closed the review on.
        self._assert_refused(self._squash(publication=PublicationSeed(state=CLOSED)))

    def test_a_merged_publication_refuses_the_squash(self) -> None:
        # The same reading from its other end: there is nowhere for the push
        # to land, and rewriting the branch under a merged pull request
        # rewrites history somebody has already taken.
        self._assert_refused(self._squash(publication=PublicationSeed(state=MERGED)))

    def test_a_moved_publication_refuses(self) -> None:
        # Somebody pushed to the pull request while the review ran, so the
        # head this owner read is not the head the squash would rewrite away.
        self._assert_refused(self._squash(publication=PublicationSeed(head=MOVED_HEAD)))

    def test_a_head_that_is_no_object_id_refuses(self) -> None:
        # Evidence a later tick could not compare anything to is not
        # evidence, and this is the one push that has no measurement standing
        # behind it -- the lease is the whole of what protects the branch.
        self._assert_refused(self._squash(publication=PublicationSeed(head=ABBREVIATED_HEAD)))

    def test_an_unreadable_publication_refuses(self) -> None:
        # A fetched pull request asks GitHub nothing, so the request that
        # fails is the attribute read behind the lookup. Left to raise it
        # would take the squash down mid-rewrite instead of refusing it.
        self._assert_refused(self._squash(publication=PublicationSeed(
            pinned_number=SQUASH_PR_NUMBER + 1,
        )))

    def _assert_refused(self, squash_run) -> None:
        """Refused, with the approved commits exactly where they were."""
        self.assertFalse(squash_run.success)
        self.assertEqual(squash_run.count, 0)
        self.assertIsNotNone(squash_run.error)
        squash_run.push_mock.assert_not_called()
        self.assertEqual(len(self._commits_on_branch()), 3)
        status = squash_support.run_git("status", "--porcelain", cwd=self.work)
        self.assertEqual(status.strip(), "")


class SquashSizeGateRealGitTest(
    squash_support.SquashGitFixtureMixin,
    unittest.TestCase,
):
    """The reading the squashed commit itself earns before it is published.

    The tree is the one the reviewer just approved, so the count is ordinarily
    the one the last gated push already answered. Ordinarily is not always:
    the base moves, and this is the last push before a human is asked to
    merge, so a pull request that has crossed the ceiling since anyone looked
    would otherwise reach the merge button unadjudicated.
    """

    def test_a_candidate_under_the_ceiling_publishes(self) -> None:
        # The ordinary answer: measured, under, pushed -- and the commit that
        # went out is the commit that was measured.
        squash_run = self._squash(**{MAX_ADDED_LINES: UNDER_THE_CEILING})

        self.assertTrue(squash_run.success)
        self.assertFalse(squash_run.held)
        self.assertEqual(
            squash_run.push_mock.call_args.kwargs["revision"],
            self._head_sha(),
        )

    def test_a_candidate_at_the_ceiling_publishes(self) -> None:
        # `additions <= MAX_ADDED_LINES` is the whole of the rule, so exact
        # equality is the last size that ships rather than the first that
        # does not.
        squash_run = self._squash(**{MAX_ADDED_LINES: AT_THE_CEILING})

        self.assertTrue(squash_run.success)
        self.assertEqual(squash_run.count, ADDED_LINES)

    def test_an_oversized_candidate_is_held(self) -> None:
        # Past the ceiling nothing is pushed and the issue goes to the
        # adjudication. The caller is told the gate owns it rather than being
        # handed a failure, so it neither parks over the hold nor carries on
        # with a handoff the gate has just taken out of its hands.
        squashed = self._gate_subject()

        squash_run = self._squash(
            publication=PublicationSeed(gate=squashed),
            **{MAX_ADDED_LINES: PAST_THE_CEILING},
        )

        self.assertTrue(squash_run.held)
        self.assertFalse(squash_run.success)
        self.assertIsNone(squash_run.error)
        squash_run.push_mock.assert_not_called()
        self.assertIn(
            (squashed.issue.number, LABEL_DECOMPOSING),
            squashed.gh.label_history,
        )

    def test_a_held_squash_keeps_the_commit_it_made(self) -> None:
        # NOT rolled back, unlike every failure here. The squashed commit is
        # what a settled verdict publishes from this branch, so restoring the
        # pre-squash head would leave the record naming a commit this host no
        # longer has.
        squashed = self._gate_subject()

        self._squash(
            publication=PublicationSeed(gate=squashed),
            **{MAX_ADDED_LINES: PAST_THE_CEILING},
        )

        self.assertEqual(len(self._commits_on_branch()), 1)
        self.assertEqual(
            squashed.gh.pinned_data(squashed.issue.number)[KEY_CANDIDATE_SHA],
            self._head_sha(),
        )

    def test_the_record_names_the_squash_it_measured(self) -> None:
        # The commit the record freezes is the commit the push would put on
        # the pull request. Measuring the head it replaces instead would gate
        # one commit and publish another.
        squashed = self._gate_subject()
        original_head = self._head_sha()

        self._squash(
            publication=PublicationSeed(gate=squashed),
            **{MAX_ADDED_LINES: PAST_THE_CEILING},
        )

        pinned = squashed.gh.pinned_data(squashed.issue.number)
        self.assertNotEqual(pinned[KEY_CANDIDATE_SHA], original_head)
        self.assertEqual(pinned[KEY_ADDITIONS], ADDED_LINES)

    def test_a_moved_publication_is_never_measured(self) -> None:
        # The entry is asked while the branch is still intact, so a head that
        # moved out from under the reading costs a refusal rather than a
        # rewrite, a measurement, and a rollback.
        squash_run = self._squash(
            publication=PublicationSeed(head=MOVED_HEAD),
            **{MAX_ADDED_LINES: UNDER_THE_CEILING},
        )

        self.assertFalse(squash_run.success)
        self.assertFalse(squash_run.held)
        self.assertEqual(len(self._commits_on_branch()), 3)

    def _gate_subject(self):
        """The gate this squash runs under, kept so a case can read it back."""
        return _squash_gate(self, PublicationSeed())


class SquashRollbackDebtRealGitTest(
    squash_support.SquashGitFixtureMixin,
    unittest.TestCase,
):
    """What the debt an approved squash records does when the push fails.

    The gate approves the squashed commit before it goes out, so a refused
    push leaves an approval naming a commit whose fate the ROLLBACK decides:
    reset, and that commit is only in the reflog; not reset, and the branch
    may still be standing on it. The record follows the reset rather than the
    intent to make one.
    """

    def test_a_failed_push_forgets_its_debt(self) -> None:
        # The gate approves the squashed commit before the push and records
        # it as one still owed a publication. The rollback puts the branch
        # back on the pre-squash head, so that commit is only in the reflog --
        # and a debt naming it would stop every later tick for a publication
        # that is never coming.
        squashed = self._gate_subject()

        squash_run = self._squash(
            publication=PublicationSeed(gate=squashed),
            push_result=False,
            **{MAX_ADDED_LINES: UNDER_THE_CEILING},
        )

        self.assertFalse(squash_run.success)
        self.assertFalse(squash_run.held)
        pinned = squashed.gh.pinned_data(squashed.issue.number)
        self.assertIsNone(pinned[KEY_APPROVED_SHA])
        self.assertIsNone(pinned[KEY_APPROVED_LEASE])

    def test_a_failed_rollback_keeps_its_debt(self) -> None:
        # The rollback is what makes the approved commit unreachable, and so
        # what licenses dropping the debt naming it. Refused, the branch may
        # still be standing on that commit while the approval is the only
        # record of the one commit this issue may publish -- dropped there,
        # the retry has nothing to ask for by id and the next tick measures
        # whatever the checkout became instead.
        squashed = self._gate_subject()

        with patch.object(
            _git_commands, _GIT_HARDENED, _RefusesTheRollbackReset(),
        ):
            squash_run = self._squash(
                publication=PublicationSeed(gate=squashed),
                push_result=False,
                **{MAX_ADDED_LINES: UNDER_THE_CEILING},
            )

        self.assertFalse(squash_run.success)
        pinned = squashed.gh.pinned_data(squashed.issue.number)
        self.assertIsNotNone(pinned[KEY_APPROVED_SHA])
        self.assertIsNotNone(pinned[KEY_APPROVED_LEASE])

    def _gate_subject(self):
        """The gate this squash runs under, kept so a case can read it back."""
        return _squash_gate(self, PublicationSeed())


class SquashCheckoutRealGitTest(
    squash_support.SquashGitFixtureMixin,
    unittest.TestCase,
):
    """The commit this owner publishes is the commit its squash made.

    The gate proves the checkout for itself, and a first generation has no
    record to prove it against -- so a checkout something moved between the
    squash and the freeze would be measured and published as if it were the
    squash, while the caller went on to record the id it made and hand a pull
    request off under it.
    """

    def test_a_checkout_that_moved_publishes_nothing(self) -> None:
        # Refused before the gate, so nothing is measured and nothing goes
        # out. The branch is left exactly as it was found rather than reset:
        # whatever moved it made a commit nobody here can account for.
        squashed = self._gate_subject()

        squash_run = self._squash(
            publication=PublicationSeed(gate=squashed),
            **{MAX_ADDED_LINES: UNDER_THE_CEILING},
            head_reads=_CommitsOverTheSquash(self),
        )

        self.assertFalse(squash_run.success)
        self.assertTrue(squash_run.held)
        squash_run.push_mock.assert_not_called()
        self._assert_parked(squashed)
        # Left as it was found rather than reset: whatever moved the checkout
        # made a commit nobody here can account for.
        self.assertEqual(len(self._commits_on_branch()), 2)

    def test_a_move_past_the_first_proof_refuses(self) -> None:
        # The window the reading before the gate cannot cover: the gate proves
        # the checkout again for itself, so a commit landing between the two
        # would be measured and pushed as if it were the squash. Bound as the
        # candidate, it is refused before anything is persisted or pushed.
        squashed = self._gate_subject()

        squash_run = self._squash(
            publication=PublicationSeed(gate=squashed),
            **{MAX_ADDED_LINES: UNDER_THE_CEILING},
            proved_heads=_MovesPastTheFirstProof(self),
        )

        self.assertFalse(squash_run.success)
        squash_run.push_mock.assert_not_called()
        self._assert_parked(squashed)

    def _gate_subject(self):
        """The gate this squash runs under, kept so a case can read it back."""
        return _squash_gate(self, PublicationSeed())

    def _assert_parked(self, squashed) -> None:
        """The gate's own park shape, left in memory for its caller.

        Read off the state rather than the pinned comment, because that is
        where the gate leaves a park: the stage handler that ran this is what
        carries the flags to the comment, and does so for every hold. What is
        pinned down here is the shape, and the write is pinned down over the
        whole approval handoff in the validating tests.
        """
        self.assertTrue(squashed.state.get(AWAITING_HUMAN))
        self.assertEqual(
            squashed.state.get(PARK_REASON), PARK_MEASUREMENT_FAILED,
        )
        self.assertEqual(squashed.gh.label_history, [])
