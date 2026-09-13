# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Which window of one interrupted exemption transfer a comment says it is in.

The refresh pins its anchor, rebases, grants the permission, pushes, and
receipts that push, and a process can die in any of the windows between. What
these cases pin is the reading a later tick takes off the comment alone, and
the fail-closed direction every record nobody can check is answered in.

Nothing here publishes, parks, or routes: the classification is read by no
caller yet and waits for the recovery that is taught to decide on it.
"""
from __future__ import annotations

import unittest
from dataclasses import replace
from types import MappingProxyType

from orchestrator.git.base_sync import transfers
from orchestrator.workflow.late_split import (
    exemption as _exemption,
    rewrites as _rewrites,
)
from tests.git.base_sync import (
    base_sync_helpers as fixtures,
    transfers_test_support as seed,
)

# A group something took a member out of, or left a value in that nothing here
# would have written. `None` is the member taken out.
TAKEN_APART = MappingProxyType({
    "an exemption that is not a commit": {
        _exemption.LATE_EXEMPT_SHA: "not-a-commit",
    },
    "an identity short of its base": {
        _exemption.LATE_EXEMPT_BASE_SHA: None,
    },
    "a permission short of its accepted base": {
        _rewrites.LATE_REWRITE_FROM_BASE_SHA: None,
    },
})

# A permission whose every field reads back whole and whose terms came from
# some other attempt than the one in front of this recovery.
FROM_ELSEWHERE = MappingProxyType({
    "a commit this checkout is not on": {
        "to_sha": fixtures.MOVED_PR_HEAD_SHA,
    },
    "a lease against some other head": {"lease": seed.FOREIGN_SHA},
    "some other publication": {"pr_number": seed.OTHER_PR_NUMBER},
    "some other stage": {"source_stage": seed.OTHER_STAGE},
    "an accepted pair that is not this issue's": {
        "from_base_sha": seed.FOREIGN_SHA,
    },
})

# A debt standing beside a permission that does not agree with it. The two go
# down in one write, so either disagreement is a comment something took apart.
DISAGREEING_DEBTS = MappingProxyType({
    "owed for some other commit": (seed.FOREIGN_SHA, seed.ACCEPTED_SHA),
    "pinned to some other head": (seed.REPLAYED_SHA, seed.FOREIGN_SHA),
})

# A permission whose own fields read back whole and whose attempt record says
# something else. The replay goes down before the gate the grant is made
# inside, so a permission standing here can never be older than the record
# beside it and either one describing something else is a contradiction.
CONTRADICTING_RECORDS = MappingProxyType({
    "a replay record naming another commit": replace(
        seed.RECORDED, sha=seed.FOREIGN_SHA,
    ),
    "a replay record nobody can read": seed.DAMAGED,
    "terms declared for another publication": replace(
        seed.DECLARED, pr_number=seed.OTHER_PR_NUMBER,
    ),
    "terms declared for another stage": replace(
        seed.DECLARED, stage=seed.OTHER_STAGE,
    ),
})


def _damage(state, damage: dict) -> None:
    """Take one member out of a group, or leave one nobody here wrote."""
    for key, written in damage.items():
        state.data.pop(key, None)
        if written is not None:
            state.set(key, written)


class UncarriedVerdictTest(unittest.TestCase):
    """The comments that cost a recovery nothing, and why each is one."""

    def test_no_verdict_is_no_transfer(self) -> None:
        """An issue that never earned one is the ordinary interrupted rebase.

        It is the overwhelming majority, and it pays no git and no request for
        a question that is not about it.
        """
        context = seed.context()

        self.assertEqual(
            transfers._carried_by(context, seed.REPLAYED_SHA),
            transfers._Handoff.NOTHING,
        )

    def test_a_legacy_exemption_still_carries(self) -> None:
        """An exemption written before the identity existed is not damage.

        It carries the exempt commit and nothing beside it, which is complete
        for what it says -- so it costs the tick the transfer rather than the
        verdict, and reads as a rewrite no permission was ever written for.
        """
        context = seed.context()
        seed.adjudicated(context.state, identity=False)

        self.assertEqual(
            transfers._carried_by(context, seed.REPLAYED_SHA),
            transfers._Handoff.UNRECORDED,
        )


class HandoffWindowTest(seed.TransferCase):
    """How far the transfer got, for each window a crash can land in."""

    def test_an_exemption_alone_is_unrecorded(self) -> None:
        """A grant the crash came before leaves the record to be rebuilt."""
        self.assertEqual(self._carried(), transfers._Handoff.UNRECORDED)

    def test_a_permission_and_its_debt_stand(self) -> None:
        """A grant that landed and a push that did not owes the receipt."""
        seed.granted(self.state)

        self.assertEqual(self._carried(), transfers._Handoff.OUTSTANDING)

    def test_a_receipted_permission_is_over(self) -> None:
        """A settled transfer leaves a recovery nothing left to move."""
        seed.settled(self.state)

        self.assertEqual(self._carried(), transfers._Handoff.SETTLED)

    def test_a_permission_binds_without_a_record(self) -> None:
        """A comment from before that record existed still carries a claim.

        There is nothing to cross-bind the terms to, so the permission is held
        by its lease and the adjudicated pair alone -- which is the
        compatibility this owner owes issues that earned a verdict first.
        """
        self._fresh(pending_rewrite=seed.ABSENT)
        seed.granted(self.state)

        self.assertEqual(self._carried(), transfers._Handoff.OUTSTANDING)

    def test_a_permission_binds_before_the_replay(self) -> None:
        """The window before that write leaves no terms to cross-bind to.

        Nothing on the comment names the publication the attempt was made
        for, so the permission is held to the anchor and the adjudicated pair
        alone -- which is what an interrupted grant can still be proved by.
        """
        self._fresh(pending_rewrite=seed.DECLARED)
        seed.granted(self.state)

        self.assertEqual(self._carried(), transfers._Handoff.OUTSTANDING)


class PriorRotationTest(seed.TransferCase):
    """A settled record outlives the attempt that earned it."""

    def test_a_rotation_onto_the_anchor_is_past(self) -> None:
        """The exemption it moved is the head this rebase was anchored to.

        Read as a claim about the attempt in hand it would be bound by that
        earlier lease, come back as a group nobody can vouch for, and park a
        rebase that has not started.
        """
        self._rotated_before(seed.ACCEPTED_SHA)

        self.assertEqual(self._carried(), transfers._Handoff.UNRECORDED)

    def test_a_rotation_elsewhere_is_passed_over(self) -> None:
        """The head in hand is not the commit that record is about."""
        self._rotated_before(fixtures.MOVED_PR_HEAD_SHA)

        self.assertEqual(self._carried(), transfers._Handoff.UNRECORDED)

    def test_a_rotation_a_newer_verdict_moved_past(self) -> None:
        """A settled group is history once the exemption has moved past it.

        Built through the writers in the order the workflow makes them: a
        transfer settles onto the replay, the reporting owner drops the proof
        behind the record it filed, and a later adjudication accepts fresh
        work. Nothing clears the group in any of that -- only the next grant
        does -- so it stands over a commit nothing exempts, which the
        fail-closed reader answers with the same bare None a damaged record
        gets. Read as damage, the rebase of the newly accepted commit would
        park, and so would every rebase this issue could ever earn again.
        """
        self._fresh()
        seed.settled(self.state)
        _rewrites.forget_transfer_proof(self.state)
        seed.adjudicated(self.state, accepted=seed.NEWER_SHA)
        self.context = replace(
            self.context,
            pending_pre_rebase_sha=seed.NEWER_SHA,
            pending_rewrite=replace(
                seed.RECORDED, sha=seed.NEWER_REPLAY_SHA,
            ),
        )

        self.assertEqual(
            self._carried(seed.NEWER_REPLAY_SHA),
            transfers._Handoff.UNRECORDED,
        )

    def _rotated_before(self, onto: str) -> None:
        """Settle an earlier attempt's transfer onto this commit."""
        self._fresh()
        _exemption.clear_exemption(self.state)
        seed.adjudicated(self.state, accepted=seed.FOREIGN_SHA)
        seed.settled(self.state, replace(
            seed.GRANTED,
            from_sha=seed.FOREIGN_SHA,
            to_sha=onto,
            lease=seed.FOREIGN_SHA,
        ))


class UnvouchedClaimTest(seed.TransferCase):
    """Every record a recovery may not act on answers the same way."""

    def test_a_group_something_took_apart(self) -> None:
        """Damaged the way a live comment is: a member out of a whole group."""
        for described, damage in TAKEN_APART.items():
            with self.subTest(described):
                self._fresh()
                seed.granted(self.state)
                _damage(self.state, damage)

                self._refuses()

    def test_a_permission_from_another_attempt(self) -> None:
        """Whole is not the same as this attempt's, field by field."""
        for described, terms in FROM_ELSEWHERE.items():
            with self.subTest(described):
                self._fresh()
                seed.granted(self.state, replace(seed.GRANTED, **terms))

                self._refuses()

    def test_a_debt_that_does_not_agree(self) -> None:
        """A permit that grants re-writes both records, so both are asked."""
        for described, (commit, lease) in DISAGREEING_DEBTS.items():
            with self.subTest(described):
                self._fresh()
                seed.granted(self.state)
                seed.owes(self.state, commit, lease)

                self._refuses()

    def test_a_digest_from_another_reading(self) -> None:
        """It describes a contribution this issue never adjudicated."""
        seed.granted(self.state, digest=seed.OTHER_DIGEST)

        self._refuses()

    def test_a_proof_nothing_can_report_from(self) -> None:
        """A settlement and a reading this build cannot account for at once."""
        seed.settled(self.state)
        self.state.set(_rewrites.LATE_REWRITE_PROOF, "a reading nobody takes")

        self._refuses()

    def test_a_record_that_contradicts_it(self) -> None:
        """The attempt's own record and the permission over it disagree."""
        for described, pending in CONTRADICTING_RECORDS.items():
            with self.subTest(described):
                self._fresh(pending_rewrite=pending)
                seed.granted(self.state)

                self._refuses()

    def _refuses(self) -> None:
        """Nothing is assembled and nothing is settled over these terms."""
        self.assertEqual(self._carried(), transfers._Handoff.UNVOUCHED)
