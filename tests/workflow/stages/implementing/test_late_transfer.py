# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What a rewrite of an adjudicated commit may carry, and what it may not."""
from __future__ import annotations

import unittest
from types import MappingProxyType
from unittest.mock import patch

from orchestrator.git.measurement.models import (
    FingerprintFailure,
    FrozenCommit,
    MeasurementFailure,
)
from orchestrator.git.verification.probes import _WorktreeStatus
from orchestrator.workflow.late_split import (
    exemption as _exemption,
    overrides as _overrides,
    rewrites as _rewrites,
)
from orchestrator.workflow.stages.implementing import (
    late_gate as _gate,
    late_parks as _parks,
    late_transfer as _transfer,
    state as _state,
)
from orchestrator.workflow.state import WorkflowLabel
from tests.workflow.observation_support import ObservedCloseCase
from tests.workflow.stages.implementing import (
    late_transfer_test_support as _support,
)
from tests.workflow.stages.implementing.late_transfer_test_support import (
    ACCEPTED_DIGEST,
    ACCEPTED_SHA,
    FOREIGN_SHA,
    LEASED_SHA,
    MERGE_BASE_SHA,
    OTHER_DIGEST,
    PR_NUMBER,
    REWRITTEN_SHA,
    SOURCE_STAGE,
    STRANGER_SHA,
)

# Every way a group already on the comment claims the commit this issue
# exempts and cannot show what it claims. A value of None is the field being
# absent -- a crash between two halves of one write -- and anything else is a
# value nothing here would have written.
_STANDING_CLAIMS = MappingProxyType({
    "a partial one": {_rewrites.LATE_REWRITE_FROM_BASE_SHA: None},
    "one that names no rewritten commit": {
        _rewrites.LATE_REWRITE_TO_SHA: None,
    },
    "one at a phase this build does not write": {
        _rewrites.LATE_REWRITE_PHASE: "reverted",
    },
    "one for a kind this build does not authorize": {
        _rewrites.LATE_REWRITE_KIND: "amend",
    },
    "one for a kind the recorded stage does not make": {
        _rewrites.LATE_REWRITE_KIND: str(_rewrites.LateRewriteKind.CONFLICT_REBASE),
    },
    "one with a hand-edited accepted commit": {
        _rewrites.LATE_REWRITE_FROM_SHA: ACCEPTED_SHA[:7],
    },
})

_DIRTY_PATH = "orchestrator/x.py"

# Every way the issue this transfer would be granted on is not the one the
# rewrite was entered on, offered through the labels a fresh fetch reads back.
_MOVED_ISSUES = MappingProxyType({
    "one an operator paused": (str(SOURCE_STAGE), "paused"),
    "one an operator sent back to the backlog": (
        str(SOURCE_STAGE), "backlog",
    ),
    "one a relabel moved to another stage": (str(WorkflowLabel.FIXING),),
    "one carrying no workflow label at all": (),
})

# A commit the checkout resolved and this host cannot peel, which is what work
# made on another host reads back as.
_UNPEELABLE_HEAD = FrozenCommit(
    sha=REWRITTEN_SHA, failure=MeasurementFailure.CANDIDATE_ABSENT,
)

# Every way the evidence itself fails to describe a rewrite this build may
# authorize, offered through the record the squash hands in.
_UNUSABLE_EVIDENCE = MappingProxyType({
    "an unknown rewrite kind": {"kind": "amend"},
    "no rewrite kind at all": {"kind": None},
    "a kind the recorded stage does not make": {
        "kind": _rewrites.LateRewriteKind.CONFLICT_REBASE,
    },
    "an abbreviated accepted commit": {"from_sha": ACCEPTED_SHA[:7]},
    "an accepted base that is prose": {"from_base_sha": "the merge base"},
    "a rewritten base that is not a commit": {"to_base_sha": 7},
    "a pull request that is not an identity": {"pr_number": 0},
    "a stage no publication is entered from": {
        "source_stage": WorkflowLabel.READY,
    },
    "a lease that is no object id": {"lease": ACCEPTED_SHA[:8]},
})

# Every way the publication the rewrite claims is not the one this call froze.
_DISAGREEING_PUBLICATIONS = MappingProxyType({
    "an entry that refused": _support.entry(refusal="the tree is dirty"),
    "another pull request": _support.entry(pr_number=PR_NUMBER + 1),
    "another stage": _support.entry(stage=WorkflowLabel.IN_REVIEW),
    "a remote that moved off the lease": _support.entry(
        published_sha=STRANGER_SHA,
    ),
})

# A reading that established nothing names no paths -- which is what a clean
# tree names too, and why the probe answers on `readable` as well.
_UNPUBLISHABLE_TREES = MappingProxyType({
    "one carrying something loose": _WorktreeStatus(
        readable=True, paths=(_DIRTY_PATH,),
    ),
    "one nothing could read": _WorktreeStatus(readable=False),
})

_MOVED_CHECKOUTS = MappingProxyType({
    "a head that moved": STRANGER_SHA,
    "a head this host cannot peel": _UNPEELABLE_HEAD,
})

# Every way the two contributions are not one contribution.
_UNEQUAL_CONTRIBUTIONS = MappingProxyType({
    "an accepted pair whose content is gone": {
        ACCEPTED_SHA: FingerprintFailure.CONTENT_ABSENT,
    },
    "a rewritten pair whose base is gone": {
        REWRITTEN_SHA: FingerprintFailure.BASE_ABSENT,
    },
    "an accepted pair the record does not describe": {
        ACCEPTED_SHA: OTHER_DIGEST,
    },
    "a rewrite that picked something up": {REWRITTEN_SHA: OTHER_DIGEST},
})


class _TransferCase(ObservedCloseCase):
    """One squash of an accepted commit, asked for a permit."""

    def setUp(self) -> None:
        super().setUp()
        self._fresh_process()
        self.reading = _support.readings(self)
        self._adjudicated()

    def _adjudicated(self, **overrides) -> None:
        """Seed the pinned comment a settled `single` verdict leaves."""
        seeded = _support.adjudicated(**overrides)
        self.github = seeded.github
        self.issue = seeded.issue
        self.state = seeded.state

    def _carried(self, **gate_overrides) -> str:
        """What the gate is told about this rewrite once the permit is asked."""
        gate = _support.gate(
            self.github, self.issue, self.state, **gate_overrides,
        )
        return _transfer._carried_over(gate, REWRITTEN_SHA)

    def _claimed(self, damage: dict) -> None:
        """Leave an authorization already standing on the comment.

        Written the way a real one is and then damaged the way a real one gets
        damaged: a group that never round-tripped would be a shape this domain
        cannot produce, and the reader would refuse it for the wrong reason.
        """
        _rewrites.record_rewrite_authorization(
            self.state, _support.rewrite(), ACCEPTED_DIGEST,
        )
        for key, written in damage.items():
            if written is None:
                self.state.data.pop(key, None)
            else:
                self.state.data[key] = written
        self.github.write_pinned_state(self.issue, self.state)

    def _assert_untouched(self) -> None:
        """The exemption is where the adjudication left it, and alone."""
        self.assertTrue(_exemption.is_exempt(self.state, ACCEPTED_SHA))
        pinned = self.github.pinned_data(self.issue.number)
        self.assertEqual(pinned[_exemption.LATE_EXEMPT_SHA], ACCEPTED_SHA)
        self.assertFalse(_rewrites.carries_rewrite_authorization(self.state))


class GrantedTransferTest(_TransferCase, unittest.TestCase):
    """The permit, and everything one durable write puts down for it."""

    def test_an_equivalent_rewrite_earns_the_permit(self) -> None:
        # The permit is what licenses THIS tick's publication. Nothing is
        # rotated for it: the rewritten commit is on no remote yet, so a
        # verdict moved onto it here would sit on an object only this host
        # has the moment the push fails.
        carried = self._carried()

        self.assertEqual(carried, _transfer._CARRIED_OVER)
        self.assertTrue(_exemption.is_exempt(self.state, ACCEPTED_SHA))
        self.assertFalse(_exemption.is_exempt(self.state, REWRITTEN_SHA))

    def test_the_grant_is_durable_before_the_push(self) -> None:
        # The write happens inside the permit rather than behind the push, so
        # a process that dies on the way to the remote comes back to an issue
        # that says what the push it owes is allowed to carry over.
        self._carried()

        pinned = self.github.pinned_data(self.issue.number)
        self.assertEqual(pinned[_exemption.LATE_EXEMPT_SHA], ACCEPTED_SHA)
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
        self.assertEqual(identity.candidate_sha, ACCEPTED_SHA)
        self.assertEqual(identity.base_sha, MERGE_BASE_SHA)
        self.assertEqual(identity.fingerprint, ACCEPTED_DIGEST)

    def test_the_authorization_records_the_grant(self) -> None:
        self._carried()

        authorization = _rewrites.read_rewrite_authorization(self.state)
        self.assertEqual(authorization.rewrite, _support.rewrite())
        self.assertEqual(authorization.fingerprint, ACCEPTED_DIGEST)
        # The commit that was collapsed and the head the push is pinned to are
        # two facts, and the record keeps them apart.
        self.assertEqual(authorization.rewrite.from_sha, ACCEPTED_SHA)
        self.assertEqual(authorization.rewrite.lease, LEASED_SHA)

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
        self.assertEqual(pinned[_state._APPROVED_SHA], REWRITTEN_SHA)
        self.assertEqual(pinned[_state._APPROVED_LEASE], LEASED_SHA)
        self.assertIn(_rewrites.LATE_REWRITE_PHASE, pinned)


class RefusedEvidenceTest(_TransferCase, unittest.TestCase):
    """Refusals the record and the evidence answer on their own.

    None of them is a park: the exemption stays exactly where the adjudication
    put it and the rewritten commit falls through to the ordinary cumulative
    size gate, which is what every install did before an exemption could move.
    """

    def test_another_candidate_is_refused(self) -> None:
        gate = _support.gate(self.github, self.issue, self.state)

        self.assertEqual(_transfer._carried_over(gate, STRANGER_SHA), "")
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
            from_sha=STRANGER_SHA,
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
        self._adjudicated(authorized=OTHER_DIGEST)

        self.assertEqual(self._carried(), "")
        self._assert_untouched()

    def test_unusable_evidence_refuses(self) -> None:
        for described, overrides in _UNUSABLE_EVIDENCE.items():
            with self.subTest(evidence=described):
                self._adjudicated()

                carried = self._carried(rewrite=_support.rewrite(**overrides))

                self.assertEqual(carried, "")
                self._assert_untouched()


class RefusedProvenanceTest(_TransferCase, unittest.TestCase):
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
        self._adjudicated(base=STRANGER_SHA)

        self.assertEqual(self._carried(), "")
        self._assert_untouched()

    def test_a_base_the_rewrite_never_read_refuses(self) -> None:
        # The caller's own claim about what it replaced, held to the digest
        # the record proved. A base that fingerprints to something else is a
        # rewrite of a contribution nobody adjudicated, whatever the record
        # beside it says.
        carried = self._carried(rewrite=_support.rewrite(
            from_base_sha=STRANGER_SHA,
        ))

        self.assertEqual(carried, "")
        self._assert_untouched()

    def test_an_unreadable_standing_claim_refuses(self) -> None:
        # A grant REPLACES the authorization group rather than adding to it,
        # so a claim about the commit this issue exempts that this build
        # cannot read back is evidence a transfer may not overwrite to repair.
        for described, damage in _STANDING_CLAIMS.items():
            with self.subTest(claim=described):
                self._adjudicated()
                self._claimed(damage)

                self.assertEqual(self._carried(), "")
                self.assertTrue(_exemption.is_exempt(self.state, ACCEPTED_SHA))

    def test_a_claim_for_another_commit_is_replaced(self) -> None:
        # The one group that is not a claim about anything this transfer is
        # doing: a later exemption moved past it, so the end its phase binds
        # to names a commit nothing exempts. Read as a claim it would refuse
        # every transfer this issue could ever earn again.
        self._claimed({_rewrites.LATE_REWRITE_FROM_SHA: STRANGER_SHA})

        self.assertEqual(self._carried(), _transfer._CARRIED_OVER)
        self.assertEqual(
            _rewrites.read_rewrite_authorization(self.state).rewrite,
            _support.rewrite(),
        )


class RefusedPublicationTest(_TransferCase, unittest.TestCase):
    """Refusals about which publication the rewrite was made against."""

    def test_an_unfrozen_publication_refuses(self) -> None:
        for described, entry in _DISAGREEING_PUBLICATIONS.items():
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
        self.state.set(_state._PR_NUMBER, PR_NUMBER + 1)

        self.assertEqual(self._carried(), "")
        self._assert_untouched()


class RefusedCheckoutTest(_TransferCase, unittest.TestCase):
    """Refusals the two local git reads answer.

    What a push would publish, and whether the objects the evidence names are
    ones this host really holds: the tree and the head it stands on, and the
    lease, which nothing else in the permit ever asks for as an object.
    """

    def test_an_unpublishable_tree_refuses(self) -> None:
        for described, status in _UNPUBLISHABLE_TREES.items():
            with self.subTest(tree=described):
                self._adjudicated()
                self.reading.tree = status

                self.assertEqual(self._carried(), "")
                self._assert_untouched()

    def test_a_checkout_that_moved_refuses(self) -> None:
        for described, head in _MOVED_CHECKOUTS.items():
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
            LEASED_SHA, (ACCEPTED_SHA, REWRITTEN_SHA, MERGE_BASE_SHA),
        )
        self.reading.absent.add(LEASED_SHA)

        self.assertEqual(self._carried(), "")
        self._assert_untouched()


class RefusedReadingTest(_TransferCase, unittest.TestCase):
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
        for described, labels in _MOVED_ISSUES.items():
            with self.subTest(issue=described):
                self._adjudicated(labels=labels)

                self.assertEqual(self._carried(), "")
                self._assert_untouched()

    def test_a_latched_close_refuses(self) -> None:
        # A close a poll observed while this worker holds the issue is one no
        # request of this tick's would ever show.
        self._latch_close(_support.SPEC.slug, self.issue.number)

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
        for described, digests in _UNEQUAL_CONTRIBUTIONS.items():
            with self.subTest(contribution=described):
                self._adjudicated()
                self.reading.digests = digests

                self.assertEqual(self._carried(), "")
                self._assert_untouched()


class _RecoveryCase(_TransferCase):
    """The comment a crash between the grant and its push leaves behind."""

    def setUp(self) -> None:
        super().setUp()
        self._carried()
        self.recovery = _support.gate(
            self.github, self.issue, self.state, rewrite=None,
        )

    def _re_asked(self) -> str:
        """What the permit answers when the recovery asks it again."""
        return _transfer._carried_over(self.recovery, REWRITTEN_SHA)

    def _bypasses(self, candidate: str = REWRITTEN_SHA) -> bool:
        """Whether the approval alone would carry this commit past the gate."""
        return _gate._approved_on_a_reading(self.recovery, candidate)

    def _recovered(self, damage: dict) -> None:
        """That comment, with one field of the permission moved or gone."""
        for key, written in damage.items():
            if written is None:
                self.state.data.pop(key, None)
            else:
                self.state.data[key] = written
        self.github.write_pinned_state(self.issue, self.state)


class RecoveredTransferTest(_RecoveryCase, unittest.TestCase):
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
            _transfer._outstanding_rewrite(self.state, REWRITTEN_SHA),
            _support.rewrite(),
        )

    def test_a_permit_defers_the_approved_bypass(self) -> None:
        # The gate skips the reading for a commit an approval owes a push
        # for. Not this one: what licensed it was a permit, so the bypass
        # waits on the permit answering again.
        self.assertEqual(
            _parks._approved_commit(self.state), REWRITTEN_SHA,
        )
        self.assertTrue(
            _transfer._licensed_by_a_permit(self.state),
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
        for described, damage in _STANDING_CLAIMS.items():
            with self.subTest(claim=described):
                self._recovered({
                    **damage,
                    _rewrites.LATE_REWRITE_PHASE: str(
                        _rewrites.LateRewritePhase.PUBLISHED,
                    ),
                })

                self.assertTrue(
                    _transfer._licensed_by_a_permit(self.state),
                )
                self.assertFalse(self._bypasses())

    def test_a_published_record_bound_away_defers(self) -> None:
        # The phase-bound end of a `published` record is the rewritten commit,
        # and it has to BE the one this issue exempts. Bound to any other, the
        # record has not been shown to describe a transfer that is over.
        self._recovered({
            _rewrites.LATE_REWRITE_PHASE: str(
                _rewrites.LateRewritePhase.PUBLISHED,
            ),
            _rewrites.LATE_REWRITE_TO_SHA: FOREIGN_SHA,
        })

        self.assertTrue(_transfer._licensed_by_a_permit(self.state))
        self.assertFalse(self._bypasses())

    def test_a_spent_permission_bypasses_again(self) -> None:
        # A transfer that settled leaves its record behind for good. Read as a
        # standing claim it would send every later approval this issue earns
        # back through a measurement, which is the re-decision the bypass
        # exists to prevent.
        _support.spent(self.state)
        _parks._approve(
            self.state, STRANGER_SHA, LEASED_SHA,
            _parks.LateApprovalBasis.READING,
        )

        self.assertFalse(_transfer._licensed_by_a_permit(self.state))
        self.assertTrue(self._bypasses(STRANGER_SHA))

    def test_a_permission_for_another_commit_defers(self) -> None:
        # The permission and the debt go down in one write for one commit, so
        # an approval standing beside an OUTSTANDING permission that names
        # some other commit is a comment disagreeing with itself. Compared
        # against the commit the record names, a hand-edited target would make
        # the permit invisible and the approval would look like any other.
        self.state.data[_rewrites.LATE_REWRITE_TO_SHA] = FOREIGN_SHA

        self.assertTrue(_transfer._licensed_by_a_permit(self.state))
        self.assertFalse(self._bypasses())
        self.assertEqual(self._re_asked(), "")


class RevalidatedRecoveryTest(_RecoveryCase, unittest.TestCase):
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
            _overrides.LATE_OVERRIDE_FINGERPRINT: OTHER_DIGEST,
        })

        self.assertEqual(self._re_asked(), "")
        self.assertFalse(self._bypasses())

    def test_a_malformed_permission_is_measured(self) -> None:
        # The record the recovery would rebuild its evidence from is one this
        # build cannot read, so there is nothing to re-ask the permit over --
        # and the approval may not answer for it either, or an oversized
        # rewrite nothing revalidated would be pushed.
        for described, damage in _STANDING_CLAIMS.items():
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
        self._recovered({_rewrites.LATE_REWRITE_FINGERPRINT: OTHER_DIGEST})

        self.assertEqual(self._re_asked(), "")
        authorized = _rewrites.read_rewrite_authorization(
            self.github.read_pinned_state(self.issue),
        )
        self.assertEqual(authorized.fingerprint, OTHER_DIGEST)
        self.assertEqual(
            authorized.phase, _rewrites.LateRewritePhase.AUTHORIZED,
        )

    def test_a_replaced_publication_is_measured(self) -> None:
        # The permission names the pull request and the stage the rewrite was
        # made against. Repointed or relabelled since, the push it licensed is
        # one nothing may make unmeasured.
        self.state.set(_state._PR_NUMBER, PR_NUMBER + 1)

        self.assertEqual(self._re_asked(), "")

    def test_a_relabelled_issue_is_measured(self) -> None:
        self.issue.labels.clear()
        self.issue.labels.append(_support.FakeLabel(str(WorkflowLabel.FIXING)))

        self.assertEqual(self._re_asked(), "")


class LostReceiptRecoveryTest(_RecoveryCase, unittest.TestCase):
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
            entry=_support.entry(published_sha=REWRITTEN_SHA),
        )

    def test_the_permit_recognizes_its_own_push(self) -> None:
        carried = _transfer._carried_over(self.landed, REWRITTEN_SHA)

        self.assertEqual(carried, _transfer._CARRIED_OVER)

    def test_a_spent_permission_reads_it_as_moved(self) -> None:
        # Past the receipt the same head is an ordinary moved remote again:
        # nothing is outstanding for it to be this permit's own push.
        _support.spent(self.state)

        self.assertFalse(
            _transfer._standing_where_the_permit_left_it(
                self.landed, _support.rewrite(),
            ),
        )
        self.assertEqual(
            _transfer._carried_over(self.landed, REWRITTEN_SHA), "",
        )

    def test_a_stranger_is_still_a_moved_remote(self) -> None:
        moved = _support.gate(
            self.github,
            self.issue,
            self.state,
            rewrite=None,
            entry=_support.entry(published_sha=FOREIGN_SHA),
        )

        self.assertEqual(_transfer._carried_over(moved, REWRITTEN_SHA), "")


class AbandonedAuthorizationTest(_TransferCase, unittest.TestCase):
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
        for restored in (ACCEPTED_SHA, LEASED_SHA):
            with self.subTest(restored=restored):
                self._carried()

                self.assertTrue(
                    _transfer._abandoned_authorization(self.gate, restored),
                )

                self.assertTrue(
                    _exemption.is_exempt(self.state, ACCEPTED_SHA),
                )
                identity = _exemption.read_semantic_identity(self.state)
                self.assertEqual(identity.candidate_sha, ACCEPTED_SHA)
                self.assertEqual(identity.fingerprint, ACCEPTED_DIGEST)
                self.assertFalse(
                    _rewrites.carries_rewrite_authorization(self.state),
                )

    def test_a_published_transfer_is_not_dropped(self) -> None:
        # Past the receipt the pull request carries the rewritten commit and
        # the exemption has already moved onto it, so there is no permission
        # left outstanding and nothing here to take back.
        _support.spent(self.state)

        self.assertFalse(
            _transfer._abandoned_authorization(self.gate, ACCEPTED_SHA),
        )

        self.assertTrue(_exemption.is_exempt(self.state, REWRITTEN_SHA))

    def test_another_reset_drops_nothing(self) -> None:
        self.assertFalse(
            _transfer._abandoned_authorization(self.gate, STRANGER_SHA),
        )

        self.assertTrue(
            _rewrites.carries_rewrite_authorization(self.state),
        )

    def test_a_damaged_authorization_is_not_dropped(self) -> None:
        # Dropping a permission nobody can check would throw away the only
        # account of how the exemption came to name what it names.
        self.state.data.pop(_rewrites.LATE_REWRITE_FROM_BASE_SHA)

        self.assertFalse(
            _transfer._abandoned_authorization(self.gate, ACCEPTED_SHA),
        )

        self.assertTrue(
            _rewrites.carries_rewrite_authorization(self.state),
        )

    def test_no_permission_drops_nothing(self) -> None:
        _rewrites.clear_rewrite_authorization(self.state)

        self.assertFalse(
            _transfer._abandoned_authorization(self.gate, ACCEPTED_SHA),
        )
