# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Recovery reconstructs granted transfers and recognizes their landed pushes."""
from __future__ import annotations

import unittest

from orchestrator.workflow.late_split import (
    rewrite_fields as _rewrite_fields,
    rewrite_values as _rewrite_values,
    rewrites as _rewrites,
)
from orchestrator.workflow.stages.implementing import (
    late_approval_reading as _late_approval_reading,
    late_approval_state as _late_approval_state,
    late_transfer as _transfer,
    late_transfer_evidence as _late_transfer_evidence,
    late_transfer_reading as _late_transfer_reading,
)
from tests.workflow.stages.implementing import (
    late_transfer_case as _transfer_case,
    late_transfer_payloads as _transfer_payloads,
    late_transfer_test_support as _support,
)


class RecoveredTransferTest(_transfer_case._RecoveryCase, unittest.TestCase):
    """What the tick after a crash between the grant and its push may do.

    The permission and the debt went down together, so the recovery finds a
    commit an approval owes a push for and a record saying what that push may
    carry over. The debt alone would license the push by object id, and the
    terms the permit was granted on -- a pull request, a stage, a record, two
    fingerprints -- can each stop being true in between. So the permit is
    re-asked over the record itself rather than assumed, and the gate defers
    to it rather than answering on the approval.
    """

    def test_the_record_supplies_the_evidence(self) -> None:
        # The recovery has no plan behind it and no rewrite to describe, so
        # both pairs, the publication, and the lease come off the permission
        # the grant left -- and every question is asked again over them.
        carried = self._re_asked()

        self.assertEqual(carried, _transfer._CARRIED_OVER)
        self.assertEqual(
            _late_transfer_reading._outstanding_rewrite(self.state, _transfer_payloads.REWRITTEN_SHA),
            _support.rewrite(),
        )

    def test_a_permit_defers_the_approved_bypass(self) -> None:
        # The gate skips the reading for a commit an approval owes a push
        # for. Not this one: what licensed it was a permit, so the bypass
        # waits on the permit answering again.
        self.assertEqual(
            _late_approval_reading._approved_commit(self.state), _transfer_payloads.REWRITTEN_SHA,
        )
        self.assertTrue(
            _late_transfer_reading._licensed_by_a_permit(self.state),
        )
        self.assertFalse(self._bypasses())

    def test_an_ordinary_approval_still_bypasses(self) -> None:
        # Every approval but a permit's is the gate's own earlier reading,
        # brought back by a crash, and it answers exactly as it always did.
        _rewrites.clear_rewrite_authorization(self.state)

        self.assertTrue(self._bypasses())

    def test_an_unreadable_published_record_defers(self) -> None:
        # `published` is recognized only from a record this build can vouch
        # for entirely. Announced over fields nothing else here understands,
        # it would say the transfer is over and the approval beside it would
        # be spent on an object id with neither the permit nor a reading
        # behind it.
        for described, damage in _transfer_case._STANDING_CLAIMS.items():
            with self.subTest(claim=described):
                self._recovered({
                    **damage,
                    _rewrite_fields.LATE_REWRITE_PHASE: str(
                        _rewrite_values.LateRewritePhase.PUBLISHED,
                    ),
                })

                self.assertTrue(
                    _late_transfer_reading._licensed_by_a_permit(self.state),
                )
                self.assertFalse(self._bypasses())

    def test_a_published_record_bound_away_defers(self) -> None:
        # The phase-bound end of a `published` record is the rewritten commit,
        # and it has to BE the one this issue exempts. Bound to any other, the
        # record has not been shown to describe a transfer that is over.
        self._recovered({
            _rewrite_fields.LATE_REWRITE_PHASE: str(
                _rewrite_values.LateRewritePhase.PUBLISHED,
            ),
            _rewrite_fields.LATE_REWRITE_TO_SHA: _transfer_payloads.FOREIGN_SHA,
        })

        self.assertTrue(_late_transfer_reading._licensed_by_a_permit(self.state))
        self.assertFalse(self._bypasses())

    def test_a_spent_permission_bypasses_again(self) -> None:
        # A transfer that settled leaves its record behind for good. Read as a
        # standing claim it would send every later approval this issue earns
        # back through a measurement, which is the re-decision the bypass
        # exists to prevent.
        _support.spent(self.state)
        _late_approval_state._approve(
            self.state, _transfer_payloads.STRANGER_SHA, _transfer_payloads.LEASED_SHA,
            _late_approval_reading.LateApprovalBasis.READING,
        )

        self.assertFalse(_late_transfer_reading._licensed_by_a_permit(self.state))
        self.assertTrue(self._bypasses(_transfer_payloads.STRANGER_SHA))

    def test_a_permission_for_another_commit_defers(self) -> None:
        # The permission and the debt go down in one write for one commit, so
        # an approval standing beside an OUTSTANDING permission that names
        # some other commit is a comment disagreeing with itself. Compared
        # against the commit the record names, a hand-edited target would make
        # the permit invisible and the approval would look like any other.
        self.state.data[_rewrite_fields.LATE_REWRITE_TO_SHA] = _transfer_payloads.FOREIGN_SHA

        self.assertTrue(_late_transfer_reading._licensed_by_a_permit(self.state))
        self.assertFalse(self._bypasses())
        self.assertEqual(self._re_asked(), "")


class LostReceiptRecoveryTest(_transfer_case._RecoveryCase, unittest.TestCase):
    """The tick after a push that landed and a receipt that did not.

    The remote carries the rewritten commit and the comment still says a push
    is owed for it, so the recovery has to recognize its own landed push
    rather than read the pull request as one somebody moved -- refused there,
    it would remeasure a squash the pull request already has and route an
    oversized one back into adjudication with the work already published.
    """

    def setUp(self) -> None:
        super().setUp()
        self.landed = _support.gate(
            self.github,
            self.issue,
            self.state,
            rewrite=None,
            entry=_support.entry(published_sha=_transfer_payloads.REWRITTEN_SHA),
        )

    def test_the_permit_recognizes_its_own_push(self) -> None:
        carried = _transfer._carried_over(self.landed, _transfer_payloads.REWRITTEN_SHA)

        self.assertEqual(carried, _transfer._CARRIED_OVER)

    def test_a_spent_permission_reads_it_as_moved(self) -> None:
        # Past the receipt the same head is an ordinary moved remote again:
        # nothing is outstanding for it to be this permit's own push.
        _support.spent(self.state)

        self.assertFalse(
            _late_transfer_evidence._standing_where_the_permit_left_it(
                self.landed, _support.rewrite(),
            ),
        )
        self.assertEqual(
            _transfer._carried_over(self.landed, _transfer_payloads.REWRITTEN_SHA), "",
        )

    def test_a_stranger_is_still_a_moved_remote(self) -> None:
        moved = _support.gate(
            self.github,
            self.issue,
            self.state,
            rewrite=None,
            entry=_support.entry(published_sha=_transfer_payloads.FOREIGN_SHA),
        )

        self.assertEqual(_transfer._carried_over(moved, _transfer_payloads.REWRITTEN_SHA), "")
