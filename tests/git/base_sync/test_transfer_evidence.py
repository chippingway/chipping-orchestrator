# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The evidence one transfer is decided on, and the records that account for it.

Two halves of the same subject. What a permit is granted on -- both pairs, the
base the remote names, the anchor as the lease, and the publication the push
was made against -- and what a road with nothing left to publish reads to know
that finishing it would strand nothing: the receipt, the debt beside it, and
the rotation that says the verdict really moved.

Nothing here publishes or parks either. Only the publisher's own assembly is
on a running road; everything else waits for the recovery that is taught to
decide on it.
"""
from __future__ import annotations

import unittest
from dataclasses import replace
from types import MappingProxyType
from unittest.mock import patch

from orchestrator.git.base_sync import transfers
from orchestrator.git.measurement.models import (
    FrozenCommit,
    MeasurementFailure,
)
from orchestrator.workflow.late_split import (
    exemption as _exemption,
    rewrites as _rewrites,
)
from tests.git.base_sync import (
    base_sync_helpers as fixtures,
    transfers_test_support as seed,
)

FREEZE_BASE = "orchestrator.git.measurement.commits._freeze_base_commit"

# What the remote answers about the base the replay landed on, and the answer
# a host that could not establish it gives instead.
FROZEN_BASE = FrozenCommit(sha=seed.REPLAYED_BASE_SHA)
UNFROZEN_BASE = FrozenCommit(failure=MeasurementFailure.BASE_UNREADABLE)

# A receipt that cannot be dated to the attempt in hand: none at all, one
# whose members name another attempt's push, and one whose members are not
# values this build can read. The malformed half matters as much as the other:
# every member goes through a fail-closed reader, so a hand edit and a
# half-written write both answer as the absence a caller may not walk past.
UNDATABLE_RECEIPTS = MappingProxyType({
    "nothing receipted at all": None,
    "another commit": {"published": seed.FOREIGN_SHA},
    "another head": {"superseded": seed.FOREIGN_SHA},
    "another publication": {"pull_request": seed.OTHER_PR_NUMBER},
    "a commit that is not one": {"published": "not-a-commit"},
    "an abbreviated head": {"superseded": seed.ACCEPTED_SHA[:7]},
    "a publication that is not an identity": {"pull_request": "forty-two"},
})


def _unaccounted(context, carried) -> str:
    """Why finishing over this comment would strand a verdict, or ""."""
    return transfers._unaccounted_publication(
        context, seed.REPLAYED_SHA, carried,
    )


class ReconstructedTest(seed.TransferCase):
    """The evidence assembled where the grant never reached the comment."""

    def setUp(self) -> None:
        super().setUp()
        self.freeze = patch(FREEZE_BASE, return_value=FROZEN_BASE)
        self.freeze.start()
        self.addCleanup(self.freeze.stop)

    def test_the_dead_ticks_own_readings(self) -> None:
        """Both pairs, the remote's base, the anchor, and that tick's terms.

        The publication is the RECORD's rather than the issue's as it reads
        now, because that is what the permit checks the frozen pull request
        against: taken from today, a relabel or a repoint made while the
        process was down would pass as the terms the rewrite was made under.
        """
        self.assertEqual(self._rebuilt(), _rewrites.LateRewrite(
            kind=_rewrites.LateRewriteKind.AUTO_CLEAN_REBASE,
            from_sha=seed.ACCEPTED_SHA,
            from_base_sha=seed.ACCEPTED_BASE_SHA,
            to_sha=seed.REPLAYED_SHA,
            to_base_sha=seed.REPLAYED_BASE_SHA,
            pr_number=fixtures.PR_NUMBER,
            source_stage=seed.STAGE,
            lease=fixtures.PRE_REBASE_SHA,
        ))

    def test_the_terms_alone_still_vouch(self) -> None:
        """The window between git returning and the write naming its head.

        Nothing on the comment names a commit, so the head in hand is offered
        to the permit to be proved by what it contributes rather than asserted
        here to be the replay.
        """
        self._fresh(pending_rewrite=seed.DECLARED)

        self.assertEqual(self._rebuilt().to_sha, seed.REPLAYED_SHA)

    def test_another_commit_vouches_for_nothing(self) -> None:
        """A record that cannot be the terms this head is decided on."""
        recorded = {
            "a head that is not this one": replace(
                seed.RECORDED, sha=seed.FOREIGN_SHA,
            ),
            "terms this build cannot read": seed.DAMAGED,
        }
        for described, pending in recorded.items():
            with self.subTest(described):
                self._fresh(pending_rewrite=pending)

                self.assertIsNone(self._rebuilt())

    def test_only_an_unrecorded_rewrite_is_built(self) -> None:
        """A group already standing is never replaced by a fresh claim."""
        for carried in transfers._Handoff:
            if carried == transfers._Handoff.UNRECORDED:
                continue
            with self.subTest(carried):
                self.assertIsNone(self._rebuilt(carried))

    def test_a_half_that_cannot_be_shown(self) -> None:
        """Withheld rather than refused: the ordinary gate measures instead.

        A legacy verdict has no accepted pair for a transfer to be moved off,
        and a base the remote would not answer for is no commit to read a
        contribution over. Neither is a refusal reported -- in both the rebase
        is measured exactly as it always was.
        """
        _exemption.clear_exemption(self.state)
        seed.adjudicated(self.state, identity=False)

        self.assertIsNone(self._rebuilt())

        self._fresh()
        self.freeze.stop()
        self.addCleanup(self.freeze.start)
        with patch(FREEZE_BASE, return_value=UNFROZEN_BASE):
            self.assertIsNone(self._rebuilt())

    def _rebuilt(self, carried=transfers._Handoff.UNRECORDED):
        """What this comment offers the permit for the head in hand."""
        return transfers._reconstructed(
            self.context, seed.REPLAYED_SHA, carried,
        )


class PublisherEvidenceTest(unittest.TestCase):
    """The same evidence, assembled by the tick that makes the rewrite."""

    def test_a_publisher_names_its_own_terms(self) -> None:
        """It hands in no record because it is making one now."""
        context = fixtures._sync_context()
        seed.adjudicated(context.state)

        with patch(FREEZE_BASE, return_value=FROZEN_BASE):
            rewrite = transfers._rewritten_by_the_rebase(
                context, seed.ACCEPTED_SHA, seed.REPLAYED_SHA,
            )

        self.assertEqual(
            (rewrite.pr_number, rewrite.source_stage, rewrite.lease),
            (fixtures.PR_NUMBER, seed.STAGE, seed.ACCEPTED_SHA),
        )


class AccountedPublicationTest(seed.TransferCase):
    """Whether a rewrite the pull request already carries is explained."""

    def test_no_verdict_strands_nothing(self) -> None:
        """There is no transfer for a missing record to leave behind."""
        context = seed.context()

        self.assertEqual(
            _unaccounted(context, transfers._Handoff.NOTHING), "",
        )

    def test_a_settled_transfer_is_accounted_for(self) -> None:
        """The rotation and the receipt landed in one statement."""
        seed.settled(self.state)

        self.assertEqual(
            _unaccounted(self.context, transfers._Handoff.SETTLED), "",
        )

    def test_an_unlicensed_rewrite_is_too(self) -> None:
        """The ordinary cumulative gate published it and receipted it."""
        seed.receipted(self.state)

        self.assertEqual(
            _unaccounted(self.context, transfers._Handoff.UNRECORDED), "",
        )

    def test_an_unreadable_record_is_refused(self) -> None:
        """It is the only account of how the exemption came to name this."""
        self.assertEqual(
            _unaccounted(self.context, transfers._Handoff.UNVOUCHED),
            transfers._UNREADABLE_CLAIM,
        )

    def test_a_standing_transfer_names_its_window(self) -> None:
        """An operator reconciling the comment is told where it stopped."""
        self.assertEqual(
            _unaccounted(self.context, transfers._Handoff.OUTSTANDING),
            transfers._UNSETTLED_CLAIM.format(
                handoff=transfers._Handoff.OUTSTANDING,
            ),
        )

    def test_a_receipt_that_is_not_datable(self) -> None:
        """All three terms, because no two of them name one push.

        A receipt is never cleared, so on its own it goes on naming a commit
        this stage pushed rounds ago; the head it was pinned to is what dates
        it to the attempt in hand, and the pull request is what a replacement
        opened over the same ref cannot supply.
        """
        unreceipted = transfers._UNRECEIPTED.format(
            published=seed.REPLAYED_SHA,
            anchor=fixtures.PRE_REBASE_SHA,
            publication=fixtures.PR_NUMBER,
        )
        for described, recorded in UNDATABLE_RECEIPTS.items():
            with self.subTest(described):
                self._fresh()
                if recorded is not None:
                    seed.receipted(self.state, **recorded)

                self.assertEqual(
                    _unaccounted(self.context, transfers._Handoff.UNRECORDED),
                    unreceipted,
                )

    def test_a_debt_the_receipt_contradicts(self) -> None:
        """The receipt and the debt go down together or not at all.

        An approval still standing over a receipted commit is a write that did
        not land whole, and so is one this build cannot read: the fail-closed
        readers answer for a group a hand edit damaged exactly as they answer
        for one somebody paid, so the claim is asked by presence.
        """
        seed.settled(self.state)
        seed.owes(self.state, seed.REPLAYED_SHA, seed.ACCEPTED_SHA)

        self.assertEqual(
            _unaccounted(self.context, transfers._Handoff.SETTLED),
            transfers._UNPAID.format(owed=seed.REPLAYED_SHA),
        )

        self._fresh()
        seed.settled(self.state)
        seed.owes(self.state, "not-a-commit", seed.ACCEPTED_SHA)

        self.assertEqual(
            _unaccounted(self.context, transfers._Handoff.SETTLED),
            transfers._DAMAGED_DEBT,
        )


class RolledBackPublicationTest(seed.TransferCase):
    """Whether the record says a push landed on a remote that has moved."""

    def test_a_settled_transfer_landed(self) -> None:
        """The write that moved the exemption says the push had landed."""
        self.assertTrue(self._rolled_back(transfers._Handoff.SETTLED))

    def test_a_whole_receipt_says_the_same(self) -> None:
        """The head they rolled back to is the head a retry would lease to."""
        seed.receipted(self.state)

        self.assertTrue(self._rolled_back(transfers._Handoff.UNRECORDED))

    def test_a_push_never_made_claims_none(self) -> None:
        """The ordinary interrupted rebase records none, so none is read.

        A receipt this build cannot read is the same answer rather than a
        landing: it names no commit, so it vouches for no publication either.
        """
        self.assertFalse(self._rolled_back(transfers._Handoff.UNRECORDED))

        seed.receipted(self.state, published="not-a-commit")

        self.assertFalse(self._rolled_back(transfers._Handoff.UNRECORDED))

    def test_an_unnamed_head_claims_none(self) -> None:
        """An empty head matches no receipt rather than every one."""
        seed.receipted(self.state, published="")

        self.assertFalse(
            self._rolled_back(transfers._Handoff.UNRECORDED, head=""),
        )

    def _rolled_back(self, carried, head: str = seed.REPLAYED_SHA) -> bool:
        """Whether this replay is one somebody undid."""
        return transfers._rolled_back_publication(self.context, head, carried)


class RotatedOntoTest(seed.TransferCase):
    """Whether the comment now says the verdict is on the published head."""

    def test_a_spent_permission_has_moved_it(self) -> None:
        """The phase, the rewritten end, and the exemption agreeing."""
        seed.settled(self.state)

        self.assertTrue(self._rotated())

    def test_a_landed_push_alone_moved_nothing(self) -> None:
        """A permit re-asked inside the gate can decline after it granted."""
        seed.granted(self.state)

        self.assertFalse(self._rotated())

    def test_no_permission_moved_nothing(self) -> None:
        """Nothing licensed a move, so nothing is read as having made one."""
        self.assertFalse(self._rotated())

    def test_a_rotation_elsewhere_proves_nothing(self) -> None:
        """The previous attempt's history is not this head's proof."""
        _exemption.clear_exemption(self.state)
        seed.adjudicated(self.state, accepted=seed.FOREIGN_SHA)
        seed.settled(self.state, replace(
            seed.GRANTED,
            from_sha=seed.FOREIGN_SHA,
            to_sha=seed.ACCEPTED_SHA,
            lease=seed.FOREIGN_SHA,
        ))

        self.assertFalse(self._rotated())

    def _rotated(self) -> bool:
        """Whether the record says this head carries the verdict."""
        return transfers._rotated_onto(self.state, seed.REPLAYED_SHA)
