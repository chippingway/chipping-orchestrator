# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What the approval a publication is owed under rests on, and who may say it.

An approval is spent by the tick that comes back after a crash, without asking
anybody, so the only thing that decides whether one may be spent is what it
RESTS on. The owner that grants an approval is the only one that knows, and
the records standing around it are the same on every road -- so the basis is
written with the approval rather than inferred from its neighbours, read
fail-closed like every other late field, and dropped in the write that spends
the pair it describes.
"""

from __future__ import annotations

import unittest
from pathlib import Path

from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.stages.implementing import (
    late_approval_reading as _late_approval_reading,
    late_approval_state as _late_approval_state,
    late_gate_models as _late_gate_models,
    late_publication as _publication,
    late_push as _push,
    late_verdict_debt as _late_verdict_debt,
    state as _state,
)
from tests.support.fakes import FakeGitHubClient, make_issue
from tests.workflow.fixtures import (
    _TEST_SPEC,
    LABEL_IMPLEMENTING,
    MEASURED_CANDIDATE_SHA,
    SHA_LENGTH,
)

_ISSUE_NUMBER = 611
_LEASE_SHA = "9" * SHA_LENGTH
_WORKTREE = Path("/tmp/orchestrator-test-late-basis")

# What a hand edit and a build from somewhere else leave in the field: a value
# no vocabulary here carries, which reads back as no basis at all.
_NOT_A_BASIS = "an operator said so"

# The exemption an adjudication's settlement leaves, which is the one record a
# minted debt is classified from.
_KEY_EXEMPT_SHA = "late_exempt_sha"

# The push that landed, named by the commit it sent and the head it was
# pinned against, which is what a settlement is asked to reconcile against.
_LANDED = _publication._PublishedCandidate(
    held=False, revision=MEASURED_CANDIDATE_SHA, lease=_LEASE_SHA,
)


def _approved(
    basis: _late_approval_reading.LateApprovalBasis, *, lease: str = _LEASE_SHA,
) -> PinnedState:
    """A pinned comment carrying one approval granted on that basis.

    `lease=""` is the pre-publication shape -- what every implementing-seam
    approval is -- whose push takes its own reading of the remote.
    """
    state = PinnedState(data={})
    _late_approval_state._approve(state, MEASURED_CANDIDATE_SHA, lease, basis)
    return state


def _gate(state: PinnedState) -> _late_gate_models._Gate:
    """The one candidate a debt is about to be recorded for."""
    github = FakeGitHubClient()
    issue = make_issue(_ISSUE_NUMBER, label=LABEL_IMPLEMENTING)
    github.add_issue(issue)
    return _late_gate_models._Gate(
        gh=github,
        spec=_TEST_SPEC,
        issue=issue,
        state=state,
        worktree=_WORKTREE,
    )


class ApprovalBasisRecordTest(unittest.TestCase):
    """The three fields an approval is, written and dropped together."""

    def test_the_group_goes_down_together(self) -> None:
        # A lease with no approval names a head nobody owes a push for, an
        # approval whose lease was dropped force-pushes over whatever the pull
        # request has become, and one whose basis was dropped is a debt a
        # later tick has to guess the provenance of.
        state = _approved(_late_approval_reading.LateApprovalBasis.ADJUDICATION)

        self.assertEqual(
            state.get(_state._APPROVED_SHA), MEASURED_CANDIDATE_SHA,
        )
        self.assertEqual(state.get(_state._APPROVED_LEASE), _LEASE_SHA)
        self.assertEqual(
            _late_approval_reading._approved_basis(state),
            str(_late_approval_reading.LateApprovalBasis.ADJUDICATION),
        )

    def test_every_basis_round_trips(self) -> None:
        # The wire value is what the pinned comment carries, so each member
        # has to read back as itself rather than as the enum's repr.
        for basis in _late_approval_reading.LateApprovalBasis:
            with self.subTest(basis=str(basis)):
                self.assertEqual(
                    _late_approval_reading._approved_basis(_approved(basis)), str(basis),
                )

    def test_a_value_from_nowhere_is_no_basis(self) -> None:
        # Read fail-closed like every other late field: a spelling this build
        # does not carry is a basis nothing checked, and what a reader owes
        # such a record is the answer it can still defend.
        state = _approved(_late_approval_reading.LateApprovalBasis.AUTHORIZATION)
        state.set(_state._APPROVED_BASIS, _NOT_A_BASIS)

        self.assertEqual(_late_approval_reading._approved_basis(state), "")

    def test_an_older_binarys_approval_says_nothing(self) -> None:
        # The compatibility answer, and the honest one: a comment written
        # before this field existed carries an approval and no account of its
        # grounds, so the reader falls back rather than guessing.
        state = PinnedState(data={_state._APPROVED_SHA: MEASURED_CANDIDATE_SHA})

        self.assertEqual(_late_approval_reading._approved_basis(state), "")

    def test_the_drop_takes_the_basis_with_it(self) -> None:
        # The basis describes one approval and outlives none: left behind, it
        # would stand beside whatever debt this issue records next and claim
        # grounds nobody granted that one.
        state = _approved(_late_approval_reading.LateApprovalBasis.AUTHORIZATION)

        _late_approval_state._forget_approval(state)

        self.assertIsNone(state.get(_state._APPROVED_SHA))
        self.assertIsNone(state.get(_state._APPROVED_BASIS))

    def test_a_half_written_group_is_damage(self) -> None:
        # Presence rather than truth, which is the gap a road deciding whether
        # a debt was PAID has to act on: the readers answer "nothing owed" for
        # a group a hand edit left unreadable exactly as they answer for one
        # the write that pays a debt blanked, so a group standing over a
        # commit nobody can name would otherwise pass as a debt somebody paid.
        for described, key, written in (
            ("a commit that is not one", _state._APPROVED_SHA, "not-a-commit"),
            ("a commit taken from under its lease", _state._APPROVED_SHA, None),
            (
                "a lease that is not a commit",
                _state._APPROVED_LEASE,
                MEASURED_CANDIDATE_SHA[:7],
            ),
            (
                "a basis this build cannot name",
                _state._APPROVED_BASIS,
                _NOT_A_BASIS,
            ),
        ):
            with self.subTest(described):
                state = _approved(_late_approval_reading.LateApprovalBasis.READING)
                state.set(key, written)

                self.assertTrue(_late_approval_reading._unreadable_approval(state))

        # And every shape a sound comment arrives in. The paid one is a group
        # of nulls, since the write that ends a debt blanks these fields
        # rather than removing them, and the legacy one carries the commit
        # alone, which is complete for what it says.
        paid = _approved(_late_approval_reading.LateApprovalBasis.AUTHORIZATION)
        _late_approval_state._forget_approval(paid)

        for described, state in (
            ("one a settlement paid", paid),
            ("a whole group", _approved(_late_approval_reading.LateApprovalBasis.READING)),
            ("a pre-publication approval", _approved(
                _late_approval_reading.LateApprovalBasis.READING, lease="",
            )),
            ("an older binary's approval", PinnedState(
                data={_state._APPROVED_SHA: MEASURED_CANDIDATE_SHA},
            )),
        ):
            with self.subTest(described):
                self.assertFalse(_late_approval_reading._unreadable_approval(state))

    def test_an_operators_gesture_names_two(self) -> None:
        # The group readers ask about rather than either member, since what
        # they decide is whether a debt has to be revalidated. The gate's own
        # two are outside it: nobody's permission was involved, so the tick
        # after a crash owes nobody a question before it pushes.
        self.assertEqual(_late_approval_reading.AUTHORIZED_BASES, frozenset((
            _late_approval_reading.LateApprovalBasis.ADJUDICATION,
            _late_approval_reading.LateApprovalBasis.AUTHORIZATION,
        )))


class StandingBasisTest(unittest.TestCase):
    """What the claim an unproven landing puts back rests on."""

    def test_it_carries_what_granted_the_debt(self) -> None:
        # The debt this write puts back is the one that was already there, so
        # what it rests on is whatever granted it. Re-decided instead, an
        # operator's bypass would be replaced by ordinary debt at exactly the
        # write a crash behind it makes spendable.
        for basis in _late_approval_reading.LateApprovalBasis:
            with self.subTest(basis=str(basis)):
                self.assertEqual(
                    _late_approval_state._standing_basis(_approved(basis)), basis,
                )

    def test_a_record_that_never_said_says_nothing(self) -> None:
        # The comment an older build left: an approval and no account of its
        # grounds. Answered `unmeasured` instead, an unknown would be promoted
        # to a decision nobody made and the reader would stop falling back to
        # the exemption, which is the only evidence such a record ever had.
        state = _approved(_late_approval_reading.LateApprovalBasis.READING)
        state.set(_state._APPROVED_BASIS, None)

        self.assertIsNone(_late_approval_state._standing_basis(state))

    def test_a_damaged_one_is_carried_verbatim(self) -> None:
        # The opposite record, and the one a carry-forward may not launder: a
        # field a hand edit moved outside the vocabulary CLAIMS grounds it
        # cannot name, which the readers fail closed on. Put back as an
        # absence, one re-record would turn it into the legacy shape above and
        # the tick after that would spend the debt without asking anybody.
        state = _approved(_late_approval_reading.LateApprovalBasis.READING)
        state.set(_state._APPROVED_BASIS, _NOT_A_BASIS)

        self.assertEqual(_late_approval_state._standing_basis(state), _NOT_A_BASIS)

        _late_approval_state._owes_a_publication(state, MEASURED_CANDIDATE_SHA)

        self.assertEqual(state.get(_state._APPROVED_BASIS), _NOT_A_BASIS)

    def test_a_field_this_build_cannot_read_is_damage(self) -> None:
        # Presence and truth asked together, which is what tells the two
        # apart: an approval an older binary wrote carries no field and earns
        # the fallback to the exemption beside it, while one whose field
        # cannot be read claims grounds it cannot name and earns nothing.
        for described, written in (
            ("a spelling from nowhere", _NOT_A_BASIS),
            ("a value of another type", 7),
        ):
            with self.subTest(basis=described):
                state = _approved(_late_approval_reading.LateApprovalBasis.READING)
                state.set(_state._APPROVED_BASIS, written)

                self.assertTrue(_late_approval_reading._unreadable_basis(state))

    def test_nothing_else_is_damage(self) -> None:
        # Both shapes an absence arrives in -- a comment that never carried
        # the field, and one carrying it as JSON null, which is an older
        # binary's value or a hand edit -- and every value this build writes.
        unwritten = _approved(_late_approval_reading.LateApprovalBasis.READING)
        unwritten.set(_state._APPROVED_BASIS, None)
        defensible = [_approved(basis) for basis in _late_approval_reading.LateApprovalBasis]

        for state in (PinnedState(data={}), unwritten, *defensible):
            with self.subTest(basis=state.get(_state._APPROVED_BASIS)):
                self.assertFalse(_late_approval_reading._unreadable_basis(state))


class SeamMintedDebtTest(unittest.TestCase):
    """The debt the implementing seam records for itself, and its grounds.

    Nothing froze a publication head there, so the gate's own debt writer
    declines and this seam mints one. Which means it is the seam, rather than
    the owner that admitted the candidate, deciding what a later tick reads --
    so it may carry grounds and it may read them off the record, but it may
    never invent them.
    """

    def test_it_carries_what_already_stands(self) -> None:
        for basis in _late_approval_reading.LateApprovalBasis:
            with self.subTest(basis=str(basis)):
                state = _approved(basis)

                _late_approval_state._owes_a_publication(state, MEASURED_CANDIDATE_SHA)

                self.assertEqual(_late_approval_reading._approved_basis(state), str(basis))

    def test_an_unknown_one_stays_unknown(self) -> None:
        # The legacy shape: an older build recorded the commit alone. Upgraded
        # to `unmeasured`, it would stop being read as unknown and become debt
        # this workflow owns -- a bypass nobody would ever revalidate.
        state = PinnedState(data={_state._APPROVED_SHA: MEASURED_CANDIDATE_SHA})

        _late_approval_state._owes_a_publication(state, MEASURED_CANDIDATE_SHA)

        self.assertEqual(_late_approval_reading._approved_basis(state), "")
        self.assertIsNone(state.get(_state._APPROVED_BASIS))

    def test_a_minted_one_reads_the_exemption_claim(self) -> None:
        # Where no approval stands, the record decides -- on the CLAIM rather
        # than on the commit, since a field a hand edit truncated still says
        # an adjudication happened. Read alike with an issue that never
        # entered one, that record's debt is recorded as this workflow's own.
        for described, exempt in (
            ("naming the commit", MEASURED_CANDIDATE_SHA),
            ("truncated by a hand edit", MEASURED_CANDIDATE_SHA[:7]),
        ):
            with self.subTest(exemption=described):
                state = PinnedState(data={_KEY_EXEMPT_SHA: exempt})

                _late_approval_state._owes_a_publication(state, MEASURED_CANDIDATE_SHA)

                self.assertEqual(
                    _late_approval_reading._approved_basis(state),
                    str(_late_approval_reading.LateApprovalBasis.ADJUDICATION),
                )

    def test_an_issue_with_no_exemption_is_unmeasured(self) -> None:
        # And the ordinary answer, so the rule above is about the claim rather
        # than about this writer refusing to mint anything: a receipt, a
        # permit, or a candidate the switch kept out of the gate leaves debt
        # this workflow made for itself and re-derives on the next tick.
        state = PinnedState(data={})

        _late_approval_state._owes_a_publication(state, MEASURED_CANDIDATE_SHA)

        self.assertEqual(
            _late_approval_reading._approved_basis(state),
            str(_late_approval_reading.LateApprovalBasis.UNMEASURED),
        )


class UnmeasuredDebtBasisTest(unittest.TestCase):
    """What a publication that skipped the reading records for itself.

    Every road reaching it is a record this workflow made for itself and
    re-derives on the next tick -- a rewrite permit, a supersession the switch
    let past, a receipt the remote already carries -- so each answers for its
    own bypass and the debt it leaves needs no revalidating.
    """

    def test_it_records_the_unmeasured_basis(self) -> None:
        gate = _gate(PinnedState(data={}))

        staged = _late_verdict_debt._stages_unmeasured_debt(
            gate, MEASURED_CANDIDATE_SHA, _LEASE_SHA,
        )

        self.assertTrue(staged)
        self.assertEqual(
            _late_approval_reading._approved_basis(gate.state),
            str(_late_approval_reading.LateApprovalBasis.UNMEASURED),
        )

    def test_a_debt_already_standing_is_left(self) -> None:
        # The approval already names this commit, so there is nothing to
        # record -- and rewriting the basis here would relabel a debt an
        # operator's gesture is behind as one this workflow granted itself.
        gate = _gate(_approved(_late_approval_reading.LateApprovalBasis.ADJUDICATION))

        staged = _late_verdict_debt._stages_unmeasured_debt(
            gate, MEASURED_CANDIDATE_SHA, _LEASE_SHA,
        )

        self.assertFalse(staged)
        self.assertEqual(
            _late_approval_reading._approved_basis(gate.state),
            str(_late_approval_reading.LateApprovalBasis.ADJUDICATION),
        )


class PaidPublicationBasisTest(unittest.TestCase):
    """What survives the write that pays one debt and puts the next back.

    A push that landed drops the approval it was licensed by, and where the
    checkout it left is not provably what went out it records the same commit
    again as the head the pull request now stands on. Those are one write, so
    the grounds the second one rests on have to be read out of the record
    BEFORE the first takes them.
    """

    def test_the_replacement_claim_keeps_the_grounds(self) -> None:
        # Read after the drop, the claim would say `unmeasured` for a debt an
        # operator's gesture was behind -- and a record damaged in the window
        # behind this write would then be spent as ordinary debt by the tick
        # that comes back to it.
        for basis in _late_approval_reading.AUTHORIZED_BASES:
            with self.subTest(basis=str(basis)):
                gate = _gate(_approved(basis))

                _push._publication_paid(gate, _LANDED, unproven=True)

                self.assertEqual(
                    _late_approval_reading._approved_basis(gate.state), str(basis),
                )
                self.assertEqual(
                    gate.state.get(_state._APPROVED_SHA), MEASURED_CANDIDATE_SHA,
                )

    def test_a_proven_landing_leaves_no_debt(self) -> None:
        # The other exit: nothing is owed, so the whole group goes -- a basis
        # left behind would stand beside whatever this issue records next.
        gate = _gate(_approved(_late_approval_reading.LateApprovalBasis.ADJUDICATION))

        _push._publication_paid(gate, _LANDED, unproven=False)

        self.assertIsNone(gate.state.get(_state._APPROVED_SHA))
        self.assertIsNone(gate.state.get(_state._APPROVED_BASIS))


if __name__ == "__main__":
    unittest.main()
