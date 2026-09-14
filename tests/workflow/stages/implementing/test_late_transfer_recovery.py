# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Recovered, changed, and abandoned authorization receipts during a rewrite transfer."""
from __future__ import annotations

import unittest

from orchestrator.workflow.late_split import (
    exemption_reading as _exemption_reading,
    overrides as _overrides,
    rewrite_fields as _rewrite_fields,
    rewrite_reading as _rewrite_reading,
    rewrite_values as _rewrite_values,
    rewrites as _rewrites,
)
from orchestrator.workflow.stages.implementing import (
    late_parks as _parks,
    late_transfer as _transfer,
    late_transfer_evidence as _late_transfer_evidence,
    late_transfer_reading as _late_transfer_reading,
    state as _state,
)
from orchestrator.workflow.state import WorkflowLabel
from tests.support import fakes as _github_fakes
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
            _parks._approved_commit(self.state), _transfer_payloads.REWRITTEN_SHA,
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
        _parks._approve(
            self.state, _transfer_payloads.STRANGER_SHA, _transfer_payloads.LEASED_SHA,
            _parks.LateApprovalBasis.READING,
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


class RevalidatedRecoveryTest(_transfer_case._RecoveryCase, unittest.TestCase):
    """Every way the terms a permit was granted on stopped being true.

    Each leaves an approval standing over a rewrite nothing revalidated, and
    each has to fall back to the ordinary cumulative gate rather than ride the
    debt's bare object id to the remote.
    """

    def test_a_legacy_authorization_is_revalidated(self) -> None:
        # The restart road asked over a comment whose operator authorization
        # is gone -- an older binary's record, or one a hand edit left. The
        # permission the grant wrote still names the rewrite, but the
        # exemption it would move licenses nothing without a human behind it,
        # so the permit refuses on the re-ask and the ordinary cumulative gate
        # measures the rewrite.
        _overrides.clear_publication_override(self.state)
        self.github.write_pinned_state(self.issue, self.state)

        self.assertEqual(self._re_asked(), "")
        self.assertFalse(self._bypasses())

    def test_a_stale_authorization_is_revalidated(self) -> None:
        # The same on a record that still reads whole and no longer describes
        # what is here: the digest is the one term the objects answer, so a
        # group somebody edited between the grant and this poll takes the
        # bypass down with it rather than riding the debt's object id out.
        self._recovered({
            _overrides.LATE_OVERRIDE_FINGERPRINT: _transfer_payloads.OTHER_DIGEST,
        })

        self.assertEqual(self._re_asked(), "")
        self.assertFalse(self._bypasses())

    def test_a_malformed_permission_is_measured(self) -> None:
        # The record the recovery would rebuild its evidence from is one this
        # build cannot read, so there is nothing to re-ask the permit over --
        # and the approval may not answer for it either, or an oversized
        # rewrite nothing revalidated would be pushed.
        for described, damage in _transfer_case._STANDING_CLAIMS.items():
            with self.subTest(claim=described):
                self._recovered(damage)

                self.assertEqual(self._re_asked(), "")
                self.assertFalse(self._bypasses())

    def test_a_disagreeing_digest_is_measured(self) -> None:
        # The digest the permission recorded is what it says it was granted
        # over. One that disagrees with the contribution actually here is a
        # record somebody edited or one taken under other rules, and a grant
        # that carried on would write this reading's digest over it -- a
        # repair of evidence nobody checked, under the authority of the
        # transfer being decided. So the permit refuses and the record stands.
        self._recovered({_rewrite_fields.LATE_REWRITE_FINGERPRINT: _transfer_payloads.OTHER_DIGEST})

        self.assertEqual(self._re_asked(), "")
        authorized = _rewrite_reading.read_rewrite_authorization(
            self.github.read_pinned_state(self.issue),
        )
        self.assertEqual(authorized.fingerprint, _transfer_payloads.OTHER_DIGEST)
        self.assertEqual(
            authorized.phase, _rewrite_values.LateRewritePhase.AUTHORIZED,
        )

    def test_a_replaced_publication_is_measured(self) -> None:
        # The permission names the pull request and the stage the rewrite was
        # made against. Repointed or relabelled since, the push it licensed is
        # one nothing may make unmeasured.
        self.state.set(_state._PR_NUMBER, _transfer_payloads.PR_NUMBER + 1)

        self.assertEqual(self._re_asked(), "")

    def test_a_relabelled_issue_is_measured(self) -> None:
        self.issue.labels.clear()
        self.issue.labels.append(_github_fakes.FakeLabel(str(WorkflowLabel.FIXING)))

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


class AbandonedAuthorizationTest(_transfer_case._TransferCase, unittest.TestCase):
    """What a rollback owes when the push a permission licensed is refused."""

    def setUp(self) -> None:
        super().setUp()
        self._carried()
        self.gate = _support.gate(self.github, self.issue, self.state)

    def test_a_rollback_drops_the_permission(self) -> None:
        # Both heads a rewrite can be put back onto. A squash collapses the
        # accepted commit itself, so the reset lands on the commit the
        # exemption never left. A base rebase reads the pre-rebase anchor for
        # itself and goes back to THAT, which is the accepted commit only
        # while the branch was standing exactly on it -- and the equality of
        # the two contributions never said that it was. Either way the object
        # the permission was granted for is on no branch, and it goes with it.
        for restored in (_transfer_payloads.ACCEPTED_SHA, _transfer_payloads.LEASED_SHA):
            with self.subTest(restored=restored):
                self._carried()

                self.assertTrue(
                    _transfer._abandoned_authorization(self.gate, restored),
                )

                self.assertTrue(
                    _exemption_reading.is_exempt(self.state, _transfer_payloads.ACCEPTED_SHA),
                )
                identity = _exemption_reading.read_semantic_identity(self.state)
                self.assertEqual(identity.candidate_sha, _transfer_payloads.ACCEPTED_SHA)
                self.assertEqual(identity.fingerprint, _transfer_payloads.ACCEPTED_DIGEST)
                self.assertFalse(
                    _rewrite_reading.carries_rewrite_authorization(self.state),
                )

    def test_a_published_transfer_is_not_dropped(self) -> None:
        # Past the receipt the pull request carries the rewritten commit and
        # the exemption has already moved onto it, so there is no permission
        # left outstanding and nothing here to take back.
        _support.spent(self.state)

        self.assertFalse(
            _transfer._abandoned_authorization(self.gate, _transfer_payloads.ACCEPTED_SHA),
        )

        self.assertTrue(_exemption_reading.is_exempt(self.state, _transfer_payloads.REWRITTEN_SHA))

    def test_another_reset_drops_nothing(self) -> None:
        self.assertFalse(
            _transfer._abandoned_authorization(self.gate, _transfer_payloads.STRANGER_SHA),
        )

        self.assertTrue(
            _rewrite_reading.carries_rewrite_authorization(self.state),
        )

    def test_a_damaged_authorization_is_not_dropped(self) -> None:
        # Dropping a permission nobody can check would throw away the only
        # account of how the exemption came to name what it names.
        self.state.data.pop(_rewrite_fields.LATE_REWRITE_FROM_BASE_SHA)

        self.assertFalse(
            _transfer._abandoned_authorization(self.gate, _transfer_payloads.ACCEPTED_SHA),
        )

        self.assertTrue(
            _rewrite_reading.carries_rewrite_authorization(self.state),
        )

    def test_no_permission_drops_nothing(self) -> None:
        _rewrites.clear_rewrite_authorization(self.state)

        self.assertFalse(
            _transfer._abandoned_authorization(self.gate, _transfer_payloads.ACCEPTED_SHA),
        )
