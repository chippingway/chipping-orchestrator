# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What a rewrite of an adjudicated commit may carry, and what it may not."""
from __future__ import annotations

import unittest
from unittest.mock import patch

from orchestrator.git.measurement.models import (
    FrozenCommit,
    MeasurementFailure,
)
from orchestrator.workflow.late_split import (
    exemption as _exemption,
    rewrites as _rewrites,
)
from orchestrator.workflow.stages.implementing import (
    late_transfer as _transfer,
    state as _state,
)
from tests.workflow.stages.implementing import (
    late_transfer_case as _transfer_case,
    late_transfer_payloads as _transfer_payloads,
    late_transfer_test_support as _support,
)


class GrantedTransferTest(_transfer_case._TransferCase, unittest.TestCase):
    """The permit, and everything one durable write puts down for it."""

    def test_an_equivalent_rewrite_earns_the_permit(self) -> None:
        # The permit is what licenses THIS tick's publication. Nothing is
        # rotated for it: the rewritten commit is on no remote yet, so a
        # verdict moved onto it here would sit on an object only this host
        # has the moment the push fails.
        carried = self._carried()

        self.assertEqual(carried, _transfer._CARRIED_OVER)
        self.assertTrue(_exemption.is_exempt(self.state, _transfer_payloads.ACCEPTED_SHA))
        self.assertFalse(_exemption.is_exempt(self.state, _transfer_payloads.REWRITTEN_SHA))

    def test_the_grant_is_durable_before_the_push(self) -> None:
        # The write happens inside the permit rather than behind the push, so
        # a process that dies on the way to the remote comes back to an issue
        # that says what the push it owes is allowed to carry over.
        self._carried()

        pinned = self.github.pinned_data(self.issue.number)
        self.assertEqual(pinned[_exemption.LATE_EXEMPT_SHA], _transfer_payloads.ACCEPTED_SHA)
        self.assertEqual(
            pinned[_rewrites.LATE_REWRITE_PHASE],
            str(_rewrites.LateRewritePhase.AUTHORIZED),
        )

    def test_the_identity_stays_on_the_accepted_pair(self) -> None:
        # It describes the commit the exemption names, and neither moves until
        # the receipt does: re-described here, a push that never landed would
        # leave the issue claiming a contribution over a commit no remote has.
        self._carried()

        identity = _exemption.read_semantic_identity(self.state)
        self.assertEqual(identity.candidate_sha, _transfer_payloads.ACCEPTED_SHA)
        self.assertEqual(identity.base_sha, _transfer_payloads.MERGE_BASE_SHA)
        self.assertEqual(identity.fingerprint, _transfer_payloads.ACCEPTED_DIGEST)

    def test_the_authorization_records_the_grant(self) -> None:
        self._carried()

        authorization = _rewrites.read_rewrite_authorization(self.state)
        self.assertEqual(authorization.rewrite, _support.rewrite())
        self.assertEqual(authorization.fingerprint, _transfer_payloads.ACCEPTED_DIGEST)
        # The commit that was collapsed and the head the push is pinned to are
        # two facts, and the record keeps them apart.
        self.assertEqual(authorization.rewrite.from_sha, _transfer_payloads.ACCEPTED_SHA)
        self.assertEqual(authorization.rewrite.lease, _transfer_payloads.LEASED_SHA)

    def test_the_debt_rides_the_grants_own_write(self) -> None:
        # The crash boundary the grant opens. A rewrite has already replaced
        # the branch's commits with one, so a comment explaining that commit
        # with no debt beside it is a branch the next squash finds with
        # nothing to squash -- reported as success, never measured, never
        # pushed. One write carries both or neither.
        writes = patch.object(
            self.github, "write_pinned_state",
            wraps=self.github.write_pinned_state,
        )
        with writes as recorded:
            self._carried()
            recorded.assert_called_once()

        pinned = self.github.pinned_data(self.issue.number)
        self.assertEqual(pinned[_state._APPROVED_SHA], _transfer_payloads.REWRITTEN_SHA)
        self.assertEqual(pinned[_state._APPROVED_LEASE], _transfer_payloads.LEASED_SHA)
        self.assertIn(_rewrites.LATE_REWRITE_PHASE, pinned)


class RefusedEvidenceTest(_transfer_case._TransferCase, unittest.TestCase):
    """Refusals the record and the evidence answer on their own.

    None of them is a park: the exemption stays exactly where the adjudication
    put it and the rewritten commit falls through to the ordinary cumulative
    size gate, which is what every install did before an exemption could move.
    """

    def test_another_candidate_is_refused(self) -> None:
        gate = _support.gate(self.github, self.issue, self.state)

        self.assertEqual(_transfer._carried_over(gate, _transfer_payloads.STRANGER_SHA), "")
        self._assert_untouched()

    def test_a_push_with_no_rewrite_is_refused(self) -> None:
        # Nine of the ten seams that publish onto a pull request the remote
        # already carries add a commit rather than replacing one.
        self.assertEqual(self._carried(rewrite=None), "")
        self._assert_untouched()

    def test_a_rewrite_of_another_commit_is_refused(self) -> None:
        # The exemption names one commit and only it, so a squash of work
        # nobody adjudicated carries nothing -- which is the ordinary case.
        carried = self._carried(rewrite=_support.rewrite(
            from_sha=_transfer_payloads.STRANGER_SHA,
        ))

        self.assertEqual(carried, "")
        self._assert_untouched()

    def test_a_legacy_exemption_carries_nothing(self) -> None:
        # A comment written before the semantic record existed, or one whose
        # fingerprint could not be taken, exempts the exact commit and can
        # prove nothing about what it contributes.
        self._adjudicated(identity=False)

        self.assertEqual(self._carried(), "")
        self._assert_untouched()

    def test_an_unauthorized_exemption_moves_none(self) -> None:
        # An exemption is half a bypass: it says an ADJUDICATOR ruled the
        # change one whole, and the operator authorization beside it is what
        # says a human agreed to publish past the ceiling. A commit only the
        # exemption names is one the ordinary gate measures, so moving that
        # exemption onto a rewrite would hand the rewritten commit a
        # permission the accepted one never had -- and this grant is the one
        # road past the reading that no record names in advance.
        self._adjudicated(authorized=False)

        self.assertEqual(self._carried(), "")
        self._assert_untouched()

    def test_a_fabricated_authorization_moves_none(self) -> None:
        # Every term of an authorization but the digest is the pinned comment
        # agreeing with itself, and a hand edit arranges that as easily as a
        # crash: a group naming the accepted commit over a pair nobody read
        # parses whole and would license this grant. The digest is the one
        # term the OBJECTS answer, so it is re-taken between the pair the
        # record names and held to what that record says.
        self._adjudicated(authorized=_transfer_payloads.OTHER_DIGEST)

        self.assertEqual(self._carried(), "")
        self._assert_untouched()

    def test_unusable_evidence_refuses(self) -> None:
        for described, overrides in _transfer_case._UNUSABLE_EVIDENCE.items():
            with self.subTest(evidence=described):
                self._adjudicated()

                carried = self._carried(rewrite=_support.rewrite(**overrides))

                self.assertEqual(carried, "")
                self._assert_untouched()


class RefusedProvenanceTest(_transfer_case._TransferCase, unittest.TestCase):
    """Refusals about which record the permit would be granted under.

    The two ends of one rule: the exemption's own record has to prove itself
    before a permit rests on it, and an authorization already standing for
    that exemption is evidence a grant may not overwrite to repair.
    """

    def test_a_hand_edited_base_refuses(self) -> None:
        # The record's own base is what the accepted contribution is read
        # over, so a whole object id naming some other commit is the record
        # failing to prove itself rather than a field nothing ever reads: the
        # digest it carries describes a pair this issue never adjudicated.
        self._adjudicated(base=_transfer_payloads.STRANGER_SHA)

        self.assertEqual(self._carried(), "")
        self._assert_untouched()

    def test_a_base_the_rewrite_never_read_refuses(self) -> None:
        # The caller's own claim about what it replaced, held to the digest
        # the record proved. A base that fingerprints to something else is a
        # rewrite of a contribution nobody adjudicated, whatever the record
        # beside it says.
        carried = self._carried(rewrite=_support.rewrite(
            from_base_sha=_transfer_payloads.STRANGER_SHA,
        ))

        self.assertEqual(carried, "")
        self._assert_untouched()

    def test_an_unreadable_standing_claim_refuses(self) -> None:
        # A grant REPLACES the authorization group rather than adding to it,
        # so a claim about the commit this issue exempts that this build
        # cannot read back is evidence a transfer may not overwrite to repair.
        for described, damage in _transfer_case._STANDING_CLAIMS.items():
            with self.subTest(claim=described):
                self._adjudicated()
                self._claimed(damage)

                self.assertEqual(self._carried(), "")
                self.assertTrue(_exemption.is_exempt(self.state, _transfer_payloads.ACCEPTED_SHA))

    def test_a_claim_for_another_commit_is_replaced(self) -> None:
        # The one group that is not a claim about anything this transfer is
        # doing: a later exemption moved past it, so the end its phase binds
        # to names a commit nothing exempts. Read as a claim it would refuse
        # every transfer this issue could ever earn again.
        self._claimed({_rewrites.LATE_REWRITE_FROM_SHA: _transfer_payloads.STRANGER_SHA})

        self.assertEqual(self._carried(), _transfer._CARRIED_OVER)
        self.assertEqual(
            _rewrites.read_rewrite_authorization(self.state).rewrite,
            _support.rewrite(),
        )


class ProvenBaseTest(_transfer_case._TransferCase, unittest.TestCase):
    """What the base branch the rewritten contribution sits over has to be.

    The end the two digests cannot speak for. Their equality says the rewrite
    contributes what was adjudicated OVER THE BASE IT NAMES, and a rebase is
    free to name one -- so a base carrying work no remote has subtracts that
    work from the answer, and the pair fingerprints alike while the object it
    names carries the adjudicated change and that bulk together.
    """

    def test_every_rewrite_earns_it_over_the_branch(self) -> None:
        # The proof is one question the permit asks of every road an exemption
        # can travel, so each authorized kind is held to it and each one still
        # earns the permit over a base the branch really carries.
        for kind, stage in _transfer_case._SUPPORTED_REWRITES.items():
            with self.subTest(rewrite=str(kind)):
                made = self._entered_from(kind, stage)

                self.assertEqual(self._carried(**made), _transfer._CARRIED_OVER)

    def test_a_base_the_branch_does_not_carry_refuses(self) -> None:
        # The forgery this proof is here for: `refs/remotes/<remote>/<base>`
        # is writable from the checkout the agent runs in, so a fork point
        # taken against it names whatever that ref was pointed at. Held to the
        # branch the remote really carries, the rewrite falls through to the
        # ordinary cumulative gate on every road it could have travelled.
        for kind, stage in _transfer_case._SUPPORTED_REWRITES.items():
            with self.subTest(rewrite=str(kind)):
                made = self._entered_from(kind, stage)
                self.reading.carried.discard(_transfer_payloads.MERGE_BASE_SHA)

                self.assertEqual(self._carried(**made), "")
                self._assert_untouched()

    def test_an_unnamed_base_branch_refuses(self) -> None:
        # A tip nothing established is not a branch to hold a base to, and
        # what refusing costs is the transfer rather than the decision: the
        # exemption stays where the adjudication put it.
        self.reading.base = FrozenCommit(
            failure=MeasurementFailure.BASE_UNREADABLE,
        )

        self.assertEqual(self._carried(), "")
        self._assert_untouched()

    def _entered_from(self, kind, stage) -> dict:
        """The same rewrite made by another owner, from the stage that makes it.

        The stage travels three times over because it is three claims: the
        evidence's own provenance, the publication the call was entered on,
        and the label the issue reads back as when the permit re-fetches it.
        """
        self._adjudicated(labels=(str(stage),))
        return {
            "rewrite": _support.rewrite(kind=kind, source_stage=stage),
            "entry": _support.entry(stage=stage),
        }


class RefusedPublicationTest(_transfer_case._TransferCase, unittest.TestCase):
    """Refusals about which publication the rewrite was made against."""

    def test_an_unfrozen_publication_refuses(self) -> None:
        for described, entry in _transfer_case._DISAGREEING_PUBLICATIONS.items():
            with self.subTest(publication=described):
                self._adjudicated()

                self.assertEqual(self._carried(entry=entry), "")
                self._assert_untouched()

    def test_a_call_entered_on_nothing_refuses(self) -> None:
        # Nothing read the pull request the rewrite claims to be against, so
        # nothing confirmed it open or standing where the lease says.
        self.assertEqual(self._carried(entry=None), "")
        self._assert_untouched()

    def test_a_replaced_pull_request_refuses(self) -> None:
        # The entry proves the pull request was read, not that it is still the
        # one this issue's work belongs to.
        self.state.set(_state._PR_NUMBER, _transfer_payloads.PR_NUMBER + 1)

        self.assertEqual(self._carried(), "")
        self._assert_untouched()


class RefusedCheckoutTest(_transfer_case._TransferCase, unittest.TestCase):
    """Refusals the two local git reads answer.

    What a push would publish, and whether the objects the evidence names are
    ones this host really holds: the tree and the head it stands on, and the
    lease, which nothing else in the permit ever asks for as an object.
    """

    def test_an_unpublishable_tree_refuses(self) -> None:
        for described, status in _transfer_case._UNPUBLISHABLE_TREES.items():
            with self.subTest(tree=described):
                self._adjudicated()
                self.reading.tree = status

                self.assertEqual(self._carried(), "")
                self._assert_untouched()

    def test_a_checkout_that_moved_refuses(self) -> None:
        for described, head in _transfer_case._MOVED_CHECKOUTS.items():
            with self.subTest(checkout=described):
                self._adjudicated()
                self.reading.stands_on(head)

                self.assertEqual(self._carried(), "")
                self._assert_untouched()

    def test_a_lease_this_host_cannot_peel_refuses(self) -> None:
        # The lease is the one end of the evidence nothing else here reads as
        # an object: the checkout proves the rewritten commit and the two
        # fingerprints read both contributions, while the lease is compared
        # as an id and is ALLOWED to name a different commit from the accepted
        # one -- so a whole-looking id this repository does not hold would
        # otherwise carry a permit on evidence nobody can produce.
        self.assertNotIn(
            _transfer_payloads.LEASED_SHA,
            (
                _transfer_payloads.ACCEPTED_SHA, _transfer_payloads.REWRITTEN_SHA,
                _transfer_payloads.MERGE_BASE_SHA,
            ),
        )
        self.reading.absent.add(_transfer_payloads.LEASED_SHA)

        self.assertEqual(self._carried(), "")
        self._assert_untouched()


class RefusedReadingTest(_transfer_case._TransferCase, unittest.TestCase):
    """Refusals the owner read and the fingerprints answer."""

    def test_a_closed_owner_refuses(self) -> None:
        # The issue in hand was fetched when the tick began and a squash on
        # approval runs minutes later, so the snapshot says nothing about
        # whether anybody still wants this work.
        self.issue.closed = True

        self.assertEqual(self._carried(), "")
        self._assert_untouched()

    def test_an_issue_that_moved_refuses(self) -> None:
        # The entry read the source stage off the issue the tick opened with,
        # so a relabel or a pause during the rewrite is invisible to every
        # reading but this one -- and a permit granted under either would push
        # onto a pull request whose stage no longer owns the branch, or carry
        # on where an operator said stop.
        for described, labels in _transfer_case._MOVED_ISSUES.items():
            with self.subTest(issue=described):
                self._adjudicated(labels=labels)

                self.assertEqual(self._carried(), "")
                self._assert_untouched()

    def test_a_latched_close_refuses(self) -> None:
        # A close a poll observed while this worker holds the issue is one no
        # request of this tick's would ever show.
        self._latch_close(_transfer_payloads.SPEC.slug, self.issue.number)

        self.assertEqual(self._carried(), "")
        self._assert_untouched()

    def test_an_unreadable_owner_refuses(self) -> None:
        # A read that established nothing is not "still open", and it fails
        # closed rather than raising out of a gate mid-publication.
        with patch.object(
            self.github, "get_issue", side_effect=RuntimeError("no answer"),
        ):
            self.assertEqual(self._carried(), "")

        self._assert_untouched()

    def test_contributions_that_are_not_one_refuse(self) -> None:
        for described, digests in _transfer_case._UNEQUAL_CONTRIBUTIONS.items():
            with self.subTest(contribution=described):
                self._adjudicated()
                self.reading.digests = digests

                self.assertEqual(self._carried(), "")
                self._assert_untouched()
