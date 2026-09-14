# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""A `single` verdict taken over a pull request the remote already carries.

The reading a `single` accepts is a claim about what THAT pull request would
come to with the candidate in it, so what the settlement owes before it
publishes is a proof that the pull request is still the one the claim was
about -- readable, open, and standing where the reading found it -- and then
the push itself, made from here because this is the last tick holding the
evidence. The pre-publication side of the same verdict is in
`test_late_settlement.py`.
"""
from __future__ import annotations

import unittest
from types import MappingProxyType
from unittest.mock import patch

from orchestrator.workflow.stages.decomposition.late_result_models import _LateDisposition
from tests.support.fakes import LazyPullRequest
from tests.workflow.fixtures import LABEL_DECOMPOSING
from tests.workflow.stages.decomposition import late_test_support as _late_support
from tests.workflow.stages.decomposition.late_published_support import (
    published_generation,
    seed_published_pr,
)
from tests.workflow.stages.decomposition.late_run_support import WorktreeSeed
from tests.workflow.stages.decomposition.late_settlement_support import (
    PARK_HOLD_FAILED,
    PARK_PR_UNRECONCILED,
    SINGLE_RUN,
    GuardedLateCase,
)

EDIT_PR_BODY = "edit_pr_body"

PR_CLOSED = "closed"

PR_NUMBER = "pr_number"
SET_WORKFLOW_LABEL = "set_workflow_label"
LABEL_WRITE_REJECTED = "label write rejected"


def _CRASHES(*_called, **_options):
    """The label write a settled verdict dies on, past its own push."""
    raise RuntimeError(LABEL_WRITE_REJECTED)


ACCEPTED_NOTICE = "authorized to publish unsplit"

# What a settled generation leaves behind on the pinned comment: none of it.
_RETIRED_KEYS = (
    _late_support.KEYS.candidate_sha,
    _late_support.KEYS.base_sha,
    _late_support.KEYS.phase,
    _late_support.KEYS.plan_pr_number,
    _late_support.KEYS.plan_pr_body,
    _late_support.KEYS.resources,
)


class _PublishedVerdictMixin:
    """The seed and the readings one post-publication verdict is decided by."""

    def _seed_settled(self, *, published: bool = True) -> None:
        """The pinned comment a crash left, with the verdict already read."""
        if published:
            seed_published_pr(self.github)
        self.github.seed_state(self.issue.number, **{
            **_late_support.generation_state(published_generation()),
            _late_support.KEYS.verdict: "single",
            _late_support.KEYS.run_cycle_id: published_generation().cycle_id,
            _late_support.KEYS.run_generation: published_generation().generation,
            _late_support.KEYS.source_sha: _late_support.CANDIDATE_SHA,
            _late_support.KEYS.exempt_sha: _late_support.CANDIDATE_SHA,
        })

    def _label(self):
        """The workflow label this issue is wearing now."""
        return self.github.workflow_label(self.issue)

    def _seed_held(self) -> None:
        """Leave the frozen publication wearing this cycle's own hold.

        Taken by an adjudication tick rather than seeded, because what the
        release meets is the marked description that tick actually wrote.
        """
        self._seed_published()
        self._decide(SINGLE_RUN)

    def _refuse_read(self, failing: str) -> None:
        """Leave the frozen publication refusing one of its lazy reads.

        A fetched pull request has asked GitHub nothing, so the request that
        can fail is an attribute read behind the lookup rather than the lookup
        itself.
        """
        self.github.add_pr(LazyPullRequest(
            self.github.get_pr(_late_support.PUBLISHED_PR_NUMBER), failing=failing,
        ))

    def _seed_published(self, *, stage=None, **pr_fields) -> None:
        """Re-seed this issue as one whose verdict was taken past publication.

        The branch is pinned beside the generation because that is what the
        handoff which opened this pull request wrote: a record carrying a
        number and no branch is the legacy shape, where the resolver answers
        with a pre-slug ref -- so a fixture seeding one while putting the pull
        request on a namespaced branch would be a record no tick produces, and
        every reader asked to reconcile the two would be right to refuse.
        """
        seed_published_pr(self.github, **pr_fields)
        entered = (
            published_generation(stage=stage) if stage
            else published_generation()
        )
        self.github.seed_state(
            self.issue.number,
            branch=_late_support.PUBLISHED_BRANCH,
            **_late_support.generation_state(entered),
        )

    def _assert_unpublished(self, outcome) -> None:
        """Nothing handed on, and the record left for the next tick to read."""
        self.assertNotEqual(outcome.disposition, _LateDisposition.SETTLED)
        self.assertEqual(self._label(), LABEL_DECOMPOSING)
        pinned = self._pinned()
        self.assertEqual(pinned.get(_late_support.KEYS.park_reason), PARK_PR_UNRECONCILED)
        self.assertEqual(pinned.get(_late_support.KEYS.candidate_sha), _late_support.CANDIDATE_SHA)


class PublishedSingleReconciliationTest(
    GuardedLateCase, _PublishedVerdictMixin, unittest.TestCase,
):
    """Where a verdict taken past publication puts the commit it accepted.

    The push belongs to the settlement because the settlement is the last tick
    holding the evidence, and the label goes to the stage the record names
    rather than back to `implementing`.
    """

    def test_it_publishes_onto_the_frozen_publication(self) -> None:
        # The push belongs to this tick because only this tick still holds the
        # evidence: the verdict was taken against one pull request standing on
        # one head, and the retirement a line later takes the record that said
        # so away. Landed, the debt it was recorded under is paid.
        self._seed_published()

        outcome = self._settle()

        self.assertEqual(outcome.disposition, _LateDisposition.SETTLED)
        pinned = self._pinned()
        self.assertEqual(pinned.get(PR_NUMBER), _late_support.PUBLISHED_PR_NUMBER)
        self.assertIsNone(pinned.get(_late_support.KEYS.approved_sha))
        self.assertIsNone(pinned.get(_late_support.KEYS.approved_lease))

    def test_it_continues_at_the_stage_it_came_from(self) -> None:
        # The stage the gate took the issue out of is the only owner of the
        # completion the candidate still owes -- a docs watermark and its
        # `in_review` handoff, a conflict round, another reviewer look. Sending
        # it to `implementing` instead walks the issue back to a point it had
        # already passed.
        self._seed_published()

        self._settle()

        self.assertEqual(self._label(), _late_support.PUBLISHED_SOURCE_STAGE)

    def test_every_source_stage_is_continued_at(self) -> None:
        # The five states the gate can take an issue out of are the five it
        # can put one back into, and each is the only owner of the completion
        # its candidate still owes.
        for stage in _late_support.PUBLISHED_SOURCE_STAGES:
            with self.subTest(stage=stage):
                self.setUp()
                self._seed_published(stage=stage)

                self._settle()

                self.assertEqual(self._label(), stage)

    def test_a_landed_push_finishes_its_tick(self) -> None:
        # The push happens before the relabel and the retirement, so a tick
        # that dies in between comes back to a live generation over a pull
        # request the commit is already on. Read as external movement, the one
        # publication refused forever would be the one this verdict made.
        self._seed_published()
        with patch.object(self.github, SET_WORKFLOW_LABEL, _CRASHES), self.assertRaises(RuntimeError):
            self._settle()
        # The push landed before the label write died, so the pull request is
        # standing on the accepted candidate when the retry looks.
        self.github.get_pr(_late_support.PUBLISHED_PR_NUMBER).head.sha = _late_support.CANDIDATE_SHA

        outcome = self._settle(worktree=WorktreeSeed(push=False))

        self.assertEqual(outcome.disposition, _LateDisposition.SETTLED)
        self.assertEqual(self._label(), _late_support.PUBLISHED_SOURCE_STAGE)
        pinned = self._pinned()
        # Nothing is owed: pushing again would be a second push of a commit
        # that is already there, and a debt on the record freezes this branch
        # out of the base refresh for the rest of the issue's life.
        self.assertIsNone(pinned.get(_late_support.KEYS.approved_sha))
        self.assertIsNone(pinned.get(_late_support.KEYS.approved_lease))

    def test_the_receipt_names_the_publication(self) -> None:
        # The accepted-settlement write. This road freezes no entry, so the
        # number has to be carried in from the reconciliation that proved it
        # -- and without it the recovery behind this push has no identity to
        # prove and a branch to search for one instead.
        self._seed_published()

        self._settle()

        pinned = self._pinned()
        self.assertEqual(pinned[_late_support.KEYS.receipt_sha], _late_support.CANDIDATE_SHA)
        self.assertEqual(pinned[_late_support.KEYS.receipt_pr], _late_support.PUBLISHED_PR_NUMBER)

    def test_a_push_that_missed_keeps_the_verdict(self) -> None:
        # A refused push here is usually the lease doing its job. The verdict
        # is durable, so the retry asks for the same commit against the same
        # head rather than handing a stage a pull request that never got it.
        self._seed_published()

        outcome = self._settle(worktree=WorktreeSeed(push=False))

        self.assertEqual(outcome.disposition, _LateDisposition.PARKED)
        self.assertEqual(self._label(), LABEL_DECOMPOSING)
        pinned = self._pinned()
        self.assertEqual(pinned.get(_late_support.KEYS.approved_sha), _late_support.CANDIDATE_SHA)
        self.assertEqual(pinned.get(_late_support.KEYS.approved_lease), _late_support.PUBLISHED_HEAD_SHA)
        self.assertEqual(pinned.get(_late_support.KEYS.park_reason), PARK_PR_UNRECONCILED)

    def test_a_settled_publication_is_refused(self) -> None:
        # Dropping the number here -- what a pre-publication verdict rightly
        # does with a stale pointer -- would push onto a branch whose pull
        # request a human settled and open a second one for a change that was
        # adjudicated against the first.
        self._seed_published(pr_state=PR_CLOSED)

        outcome = self._settle()

        self._assert_unpublished(outcome)


class PublishedCheckoutProofTest(
    GuardedLateCase, _PublishedVerdictMixin, unittest.TestCase,
):
    """The checkout a settled verdict may hand its stage, and what fails it.

    What a human accepted is one commit with nothing loose beside it, and the
    worktree it was accepted from is writable through the whole adjudication,
    through the push itself, and through the tick that died between a landed
    push and the retry that finishes it. Every stage the label is about to
    hand this issue to works from that checkout.
    """

    def test_a_mutated_checkout_keeps_the_verdict(self) -> None:
        # A recorded verdict settles with no run behind it, so the read-only
        # proof a finished run passes does not run again -- and an
        # adjudication is a human reading a diff over hours, with the worktree
        # writable the whole time. Every stage past this one works from the
        # CHECKOUT, so one left on an unmeasured descendant would reach
        # review, a squash, and a merge with nobody having read it, even
        # though the push itself names the accepted id.
        for mutation in (
            WorktreeSeed(head=_late_support.OTHER_SHA),
            WorktreeSeed(dirty=("scratch.txt",)),
        ):
            with self.subTest(mutation=mutation):
                self.setUp()
                self._seed_settled()

                outcome = self._settle(worktree=mutation)

                self._assert_unpublished(outcome)

    def test_a_push_that_moved_it_holds_the_handoff(self) -> None:
        # The window the pre-push proof cannot cover: a push is a request and
        # the worktree is writable for the whole of it. What went out is the
        # accepted commit, so the pull request is right; what is wrong is the
        # CHECKOUT, and every stage the label is about to hand this issue to
        # works from that -- the reviewer reads a head ahead of the pushed
        # branch as unpublished work, the squash rewrites what is on it.
        for mutation in (
            WorktreeSeed(head_after_push=_late_support.OTHER_SHA),
            WorktreeSeed(dirty_after_push=("scratch.txt",)),
        ):
            with self.subTest(mutation=mutation):
                self.setUp()
                self._seed_published()

                outcome = self._settle(worktree=mutation)

                self._assert_unpublished(outcome)

    def test_a_landed_retry_proves_the_checkout(self) -> None:
        # A retry finishing a settlement whose own push landed makes no push
        # of its own, so nothing in it would read the checkout -- and the
        # worktree has been writable since the process that pushed died. The
        # commit is on the pull request either way; what may not be handed on
        # is a checkout carrying loose edits or an unmeasured descendant.
        for mutation in (
            WorktreeSeed(head=_late_support.OTHER_SHA),
            WorktreeSeed(dirty=("scratch.txt",)),
        ):
            with self.subTest(mutation=mutation):
                self.setUp()
                self._seed_landed_push()

                outcome = self._settle(worktree=mutation)

                self._assert_unpublished(outcome)

    def _seed_landed_push(self) -> None:
        """Leave the settlement whose own push landed and whose tick died."""
        self._seed_published()
        with patch.object(self.github, SET_WORKFLOW_LABEL, _CRASHES), self.assertRaises(RuntimeError):
            self._settle()
        self.github.get_pr(_late_support.PUBLISHED_PR_NUMBER).head.sha = _late_support.CANDIDATE_SHA


# One whole receipt group, and the three ways it stops being one. A member
# carrying a value nothing can read is the plain shape. A group naming no
# publication at all is the second: the commit says what was published and
# the number says where it went, and neither is derivable from the other. A
# member whose KEY has gone is the third, and only presence tells it from the
# `null` an initial publication writes for the head it froze none of.
_WHOLE_RECEIPT = MappingProxyType({
    _late_support.KEYS.receipt_sha: _late_support.CANDIDATE_SHA,
    _late_support.KEYS.receipt_lease: _late_support.PUBLISHED_HEAD_SHA,
    _late_support.KEYS.receipt_pr: _late_support.PUBLISHED_PR_NUMBER,
})

_DAMAGED_GROUPS = (
    (
        "a member nothing can read",
        {**_WHOLE_RECEIPT, _late_support.KEYS.receipt_pr: "not-a-number"},
    ),
    (
        "no publication named at all",
        {**_WHOLE_RECEIPT, _late_support.KEYS.receipt_pr: None},
    ),
    (
        "a member whose key is gone",
        {
            member: held for member, held in _WHOLE_RECEIPT.items()
            if member != _late_support.KEYS.receipt_lease
        },
    ),
)


class PublishedVerdictRefusalTest(
    GuardedLateCase, _PublishedVerdictMixin, unittest.TestCase,
):
    """Every proof the settlement owes before it publishes, and what fails it.

    The reading a `single` accepts is a claim about ONE pull request standing
    on one head, so a publication that cannot be read, has been settled, or
    has moved is not the one the verdict was about -- and the candidate is
    left for a tick that can prove it rather than pushed on a claim that has
    been overtaken.
    """

    def test_a_state_nothing_could_read_is_refused(self) -> None:
        # A fetched pull request asks GitHub nothing, so the request that
        # fails is an attribute read behind the lookup -- and the settlement
        # meets it taking this cycle's hold back off the same pull request,
        # one step ahead of the proof. Left to raise, the tick would end with
        # the branch still carrying the accepted candidate and nothing on the
        # thread saying why.
        self._seed_held()
        self._refuse_read("state")

        outcome = self._settle()

        self._assert_unreleased(outcome)

    def test_a_head_nothing_could_read_is_refused(self) -> None:
        # The other lazy read, refused for the same reason: neither the
        # description this generation displaced nor the candidate it accepted
        # may be acted on through a pull request nobody could read.
        self._seed_held()
        self._refuse_read("head")

        outcome = self._settle()

        self._assert_unreleased(outcome)

    def test_a_moved_publication_is_refused(self) -> None:
        # Something pushed to it during the adjudication, so what the verdict
        # was taken over is not what the branch would come to.
        self._seed_published(head=_late_support.OTHER_SHA)

        outcome = self._settle()

        self._assert_unpublished(outcome)

    def test_a_fork_at_the_frozen_head_is_refused(self) -> None:
        # The shape every other term agrees on: a fork carries this
        # repository's ref names over its commits, so the branch and the
        # frozen head both match while the pull request is one this issue
        # never made. Accepted, the settlement would push this repository's
        # branch and hand the reviewer somebody else's change.
        self._seed_published(head_repo=_late_support.FORK_REPO)

        outcome = self._settle()

        self._assert_unpublished(outcome)

    def test_a_publication_elsewhere_is_refused(self) -> None:
        # The number and the branch are separate fields on one pinned comment
        # and this road pushes the branch it resolves for itself. A pull
        # request standing at the frozen head on some other ref passes every
        # other check here -- so waved through, the push would grow a branch
        # that pull request never carried while the handoff named it as the
        # change the accepted candidate is in.
        self._seed_published(head_branch=_late_support.FOREIGN_BRANCH)

        outcome = self._settle()

        self._assert_unpublished(outcome)

    def test_a_pre_publication_verdict_pins_nothing(self) -> None:
        # A verdict taken before anything was published names no pull
        # request to have been measured against, so its push reads the remote
        # for itself rather than being pinned to a frozen head.
        self._settle()

        self.assertIsNone(self._pinned().get(_late_support.KEYS.approved_lease))

    def _assert_unreleased(self, outcome) -> None:
        """Nothing handed on, and the hold left for the next tick to retry."""
        self.assertNotEqual(outcome.disposition, _LateDisposition.SETTLED)
        self.assertEqual(self._label(), LABEL_DECOMPOSING)
        pinned = self._pinned()
        self.assertEqual(pinned.get(_late_support.KEYS.park_reason), PARK_HOLD_FAILED)
        self.assertEqual(pinned.get(_late_support.KEYS.candidate_sha), _late_support.CANDIDATE_SHA)


class DamagedReceiptGroupTest(
    GuardedLateCase, _PublishedVerdictMixin, unittest.TestCase,
):
    """The refusal that is about the RECORD rather than about the remote.

    This road reaches the transport without the size gate's own door, and the
    push it makes writes a fresh receipt group over whatever the comment
    carries. A group that does not read back whole is the one record that
    write destroys rather than corrects, so the reconciliation refuses it
    before it asks the remote anything.
    """

    def test_a_damaged_receipt_group_is_refused(self) -> None:
        # The road that reaches the transport without the size gate's own
        # door: nothing else here reads the receipt group, and the push this
        # settlement makes writes a fresh one over whatever is on the comment.
        # So a group that does not read back whole is refused before the
        # remote is even asked -- a member carrying a value nothing can use,
        # and a member whose key has gone, which is the one an "is the commit
        # readable" check walks straight past -- and the damaged record is
        # left exactly as it stands for the human who repairs it.
        for described, group in _DAMAGED_GROUPS:
            with self.subTest(group=described):
                self.setUp()
                self._seed_published(head=_late_support.CANDIDATE_SHA)
                self.github.seed_state(
                    self.issue.number, **{**self._pinned(), **group},
                )

                outcome = self._settle()

                self._assert_unpublished(outcome)
                self.assertEqual(self._receipt_group(), group)

    def _receipt_group(self) -> dict:
        """Whatever of the receipt group the comment carries now."""
        members = (_late_support.KEYS.receipt_sha, _late_support.KEYS.receipt_lease, _late_support.KEYS.receipt_pr)
        return {
            member: held for member, held in self._pinned().items()
            if member in members
        }

class PublishedOwnPushTest(
    GuardedLateCase, _PublishedVerdictMixin, unittest.TestCase,
):
    """The one moved head this road forgives, and what it takes to earn it.

    A pull request standing on the accepted candidate is this settlement's own
    push having landed on a tick that died before the label behind it -- but
    only where a DURABLE record says so, and the commit is not one. This call
    runs ahead of the exemption, the approval, and the push, so on a fresh
    pass nothing of this workflow's has reached the remote at all.
    """

    def test_a_move_onto_the_candidate_is_refused(self) -> None:
        # The exact-candidate move on a FRESH pass, which is the one the
        # commit alone cannot explain. This call runs ahead of the exemption,
        # the approval, and the push behind them, so nothing of this
        # workflow's has touched the remote: a pull request standing on the
        # accepted candidate got there because something else -- an agent that
        # pushed its own commit -- put it there. Read as this settlement's own
        # push landing, the record is retired and the issue handed on over a
        # publication nobody proved.
        self._seed_published(head=_late_support.CANDIDATE_SHA)

        outcome = self._settle()

        self._assert_unpublished(outcome)

    def test_a_rewind_onto_a_stale_receipt_is_refused(self) -> None:
        # The sharp form of the same move. The receipt is never cleared, so an
        # accepted candidate this issue published in an earlier round is a
        # commit it goes on naming -- and a pull request somebody rewound onto
        # that commit then agrees with every local fact there is. What dates a
        # receipt to THIS settlement is the head it replaced, which has to be
        # the head the verdict was measured over: an earlier attempt's names
        # another, and one written before the pair was recorded names none.
        for lease in (_late_support.OTHER_SHA, None):
            with self.subTest(lease=lease):
                self.setUp()
                self._seed_published(head=_late_support.CANDIDATE_SHA)
                self.github.seed_state(self.issue.number, **{
                    **self._pinned(),
                    **_WHOLE_RECEIPT,
                    _late_support.KEYS.receipt_lease: lease,
                })

                outcome = self._settle()

                self._assert_unpublished(outcome)

    def test_a_receipt_for_another_pr_is_refused(self) -> None:
        # The move neither the commit nor the head it replaced catches. A
        # branch pushed from that head before, onto a publication since closed
        # and REPLACED by another on the same ref, dates a receipt to this
        # settlement while the push it records went somewhere else -- so the
        # number it names has to be the one the verdict was frozen on. Absent,
        # and unreadable, are the same answer: a record this build cannot tie
        # to any publication may not license a carve-out from the refusal that
        # catches somebody else's branch move.
        for described, identity in (
            ("another pull request", _late_support.PUBLISHED_PR_NUMBER + 1),
            ("none at all", None),
            ("one nothing can read", "not-a-number"),
        ):
            with self.subTest(receipt=described):
                self.setUp()
                self._seed_published(head=_late_support.CANDIDATE_SHA)
                self.github.seed_state(self.issue.number, **{
                    **self._pinned(),
                    _late_support.KEYS.receipt_sha: _late_support.CANDIDATE_SHA,
                    _late_support.KEYS.receipt_lease: _late_support.PUBLISHED_HEAD_SHA,
                    _late_support.KEYS.receipt_pr: identity,
                })

                outcome = self._settle()

                self._assert_unpublished(outcome)

    def test_a_receipt_for_the_candidate_finishes_it(self) -> None:
        # And the same head with a record behind it is the window the
        # carve-out exists for: the receipt says this workflow pushed exactly
        # that commit, so the pull request is standing where this issue put
        # it and what is left to finish is the label and the retirement.
        self._seed_published(head=_late_support.CANDIDATE_SHA)
        self.github.seed_state(self.issue.number, **{
            **self._pinned(),
            _late_support.KEYS.receipt_sha: _late_support.CANDIDATE_SHA,
            _late_support.KEYS.receipt_lease: _late_support.PUBLISHED_HEAD_SHA,
            _late_support.KEYS.receipt_pr: _late_support.PUBLISHED_PR_NUMBER,
        })

        outcome = self._settle(worktree=WorktreeSeed(push=False))

        self.assertEqual(outcome.disposition, _LateDisposition.SETTLED)
        self.assertEqual(self._label(), _late_support.PUBLISHED_SOURCE_STAGE)
