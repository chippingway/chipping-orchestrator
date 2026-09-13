# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What an adjudication is worth at the gate without a human behind it.

An oversized candidate publishes without a reading only where two records name
it: the exemption a settlement wrote, and the terms an operator authorized
that publication on. These pin down the second half -- what the gate does with
an exemption standing alone, which is the shape an older binary left on live
issues and the shape a damaged authorization leaves on any of them.

What that costs is the measurement, and the reading then decides: a candidate
at or below the ceiling publishes exactly as it always did, and an oversized
one is parked for the authorization rather than routed back into an
adjudication that has already answered. What the park then reads, and the
command that ends it, are `test_late_consent`'s.
"""

from __future__ import annotations

import unittest
from types import MappingProxyType

from orchestrator import config
from orchestrator.git.measurement.models import FingerprintFailure
from orchestrator.workflow.stages.implementing import late_parks as _parks
from tests.workflow.fixtures import (
    MEASURED_CANDIDATE_SHA,
    SHA_LENGTH,
    _authorize_command,
    _authorized_exemption,
    _damaged_authorization,
    _fabricated_authorization,
    _legacy_exemption,
)
from tests.workflow.stages.implementing import (
    late_authority_test_support as legacy,
    late_gate_test_support as support,
)

_KEY_APPROVED_SHA = "late_approved_sha"
_KEY_APPROVED_BASIS = "late_approved_basis"
_KEY_EXEMPT_SHA = "late_exempt_sha"
_MAX_ADDED_LINES = "MAX_ADDED_LINES"

# A commit of the right shape that no record on these seeds names, which is
# what work committed on top of an accepted one looks like from the record's
# side: neither claim reaches it.
_DESCENDANT_SHA = "d" * SHA_LENGTH

# How much of a whole object id a hand edit leaves behind, which is the shape
# an exemption field reads back from as no exemption at all.
_ABBREVIATED = 7

# An approval an older binary wrote: the commit alone, with no account of what
# the push it licenses rests on.
_LEGACY_DEBT = MappingProxyType({_KEY_APPROVED_SHA: MEASURED_CANDIDATE_SHA})

# The debt an authorized settlement's handoff records, and the debt this
# gate's own count at or below the ceiling records.
_ADJUDICATION_DEBT = MappingProxyType({
    **_LEGACY_DEBT,
    _KEY_APPROVED_BASIS: str(_parks.LateApprovalBasis.ADJUDICATION),
})

_READING_DEBT = MappingProxyType({
    **_LEGACY_DEBT,
    _KEY_APPROVED_BASIS: str(_parks.LateApprovalBasis.READING),
})

# The two shapes a debt an operator's gesture is behind arrives in, which are
# the two a later tick may not spend without re-reading that gesture.
_REVALIDATED_DEBTS = MappingProxyType({
    "recorded as the adjudication's": _ADJUDICATION_DEBT,
    "an older binary's, with no basis": _LEGACY_DEBT,
})


class UnauthorizedExemptionTest(
    legacy._LegacyExemptionCase, unittest.TestCase,
):
    """An exemption alone lets nothing past: the candidate is measured."""

    def test_an_unauthorized_exemption_is_measured(self) -> None:
        # Three shapes reach the same place. The legacy comment never had an
        # authorization on it; the damaged one has a group this build cannot
        # read whole; and the fabricated one parses, names this candidate, and
        # describes a decision nobody made over a pair nobody froze -- the
        # digest being the one term the OBJECTS answer. A bypass nobody can
        # show the terms of is worth what a bypass nobody granted is worth.
        for shape, seeded in (
            ("legacy", _legacy_exemption()),
            ("damaged", _damaged_authorization()),
            ("fabricated", _fabricated_authorization()),
        ):
            with self.subTest(shape=shape):
                self.setUp()
                self._seed(**seeded)

                mocks = self._run_gate(added_lines=support.OVERSIZED_ADDITIONS)

                self._assert_measured(mocks)
                self._assert_held(mocks)

    def test_a_reading_nobody_can_take_is_measured(self) -> None:
        # A store that cannot hand back the content between two commits it
        # holds refuses on the same footing as a digest that disagrees: what
        # neither is, is grounds for a bypass. The authorization stays exactly
        # where it is, so a host that comes back publishes what it says.
        self._seed(**_authorized_exemption())

        mocks = self._run_gate(
            contribution_digest=FingerprintFailure.CONTENT_ABSENT,
            added_lines=support.OVERSIZED_ADDITIONS,
        )

        self._assert_measured(mocks)
        self._assert_held(mocks)
        self.assertIn(legacy.KEY_OVERRIDE_CANDIDATE_SHA, self._pinned())

    def test_a_descendant_is_a_fresh_candidate(self) -> None:
        # Both claims are about ONE object id, and neither is widened here: a
        # commit made on top of an authorized one carries work nobody ruled on
        # and nobody read, so it is measured as the fresh candidate it is.
        self._seed(**_authorized_exemption(_DESCENDANT_SHA))

        mocks = self._run_gate(added_lines=support.OVERSIZED_ADDITIONS)

        self._assert_measured(mocks)
        self._assert_held(mocks)

    def test_an_authorized_one_still_publishes(self) -> None:
        # The other side of the same rule, so the refusals above are about the
        # missing half rather than about the exemption having stopped working.
        self._seed(**_authorized_exemption())

        mocks = self._run_gate(added_lines=support.OVERSIZED_ADDITIONS)

        self._assert_unmeasured(mocks)
        self._assert_published(mocks)

    def test_the_ceiling_still_decides_the_rest(self) -> None:
        # What "measured like any other candidate" means at the other end of
        # the reading: nothing about a legacy exemption holds a change the
        # ceiling would have let through, and the boundary stays inclusive --
        # a candidate exactly at the configured value is not oversized, so it
        # never reaches the park at all.
        for described, ceiling in (
            ("under it", support.GATE_THRESHOLD),
            ("exactly at it", support.SMALL_ADDITIONS),
        ):
            with self.subTest(reading=described):
                self.setUp()
                self._seed_legacy()

                with support.patch.object(
                    config, _MAX_ADDED_LINES, ceiling,
                ):
                    mocks = self._run_gate(
                        added_lines=support.SMALL_ADDITIONS,
                    )

                self._assert_measured(mocks)
                self._assert_published(mocks)


class UnauthorizedDebtTest(legacy._LegacyExemptionCase, unittest.TestCase):
    """Whose decision a publication debt rests on, and who may spend it.

    An approval is spent by the tick that comes back after a crash without
    asking anybody, so the only thing that decides whether one may be spent is
    what it RESTS on -- which is why the record says, and why every case here
    is about a basis rather than about the records standing beside it.
    """

    def test_the_exemptions_own_debt_does_not_bypass(self) -> None:
        # The settlement writes the exemption and the approval in one breath,
        # so an approval it recorded is that adjudication wearing another
        # field rather than a reading this gate took. Read as an ordinary
        # approval it would publish the very candidate the record above it may
        # not. An approval an older binary wrote says nothing about its own
        # grounds, and there the exemption is the only evidence left -- so it
        # is read, and read conservatively.
        for described, debt in _REVALIDATED_DEBTS.items():
            with self.subTest(debt=described):
                self.setUp()
                self._seed_legacy(**debt)

                mocks = self._run_gate(
                    added_lines=support.OVERSIZED_ADDITIONS,
                )

                self._assert_measured(mocks)
                self._assert_held(mocks)

    def test_a_damaged_exemption_frees_nothing(self) -> None:
        # The crash state the other way round. A recorded basis says the debt
        # is the settlement's whatever the exemption beside it reads as.
        # Without one -- an approval an older binary wrote -- the exemption is
        # the only evidence there is, and a field this build cannot read is
        # not the same thing as an issue that never entered an adjudication:
        # it CLAIMS one and cannot say which commit, which is exactly what a
        # hand edit of that one field produces. Read alike, the truncated
        # record is the shape that publishes an adjudication's debt unmeasured.
        for described, debt in _REVALIDATED_DEBTS.items():
            with self.subTest(debt=described):
                self.setUp()
                self._seed(**{
                    **debt,
                    _KEY_EXEMPT_SHA: MEASURED_CANDIDATE_SHA[:_ABBREVIATED],
                })

                mocks = self._run_gate(
                    added_lines=support.OVERSIZED_ADDITIONS,
                )

                self._assert_measured(mocks)
                self._assert_held(mocks)

    def test_a_damaged_basis_bypasses_nothing(self) -> None:
        # The sharpest shape of all, and the one a single hand edit reaches:
        # the field the legacy fallback turns on, touched. Read as the absence
        # an older binary left, the approval beside it would answer as the
        # gate's own and an oversized candidate would publish with no
        # measurement and no exemption anywhere on the record.
        for described, written in (
            ("a spelling from nowhere", "damaged-basis"),
            ("a value of another type", 7),
        ):
            with self.subTest(basis=described):
                self.setUp()
                self._seed(**{
                    _KEY_APPROVED_SHA: MEASURED_CANDIDATE_SHA,
                    _KEY_APPROVED_BASIS: written,
                })

                mocks = self._run_gate(
                    added_lines=support.OVERSIZED_ADDITIONS,
                )

                self._assert_measured(mocks)
                self._assert_held(mocks)

    def test_an_authorized_debt_is_revalidated(self) -> None:
        # The crash window an authorized publication opens. The gate counted
        # this candidate and a human let it past, so the approval it left
        # rests on that gesture -- and a record damaged between the approval
        # and the push has to take the bypass down with it. Recorded as an
        # ordinary reading it would look like a count under the ceiling and
        # publish an oversized change nothing can show the grounds for.
        self._seed_legacy(**{
            _KEY_APPROVED_SHA: MEASURED_CANDIDATE_SHA,
            _KEY_APPROVED_BASIS: str(_parks.LateApprovalBasis.AUTHORIZATION),
        })

        mocks = self._run_gate(added_lines=support.OVERSIZED_ADDITIONS)

        self._assert_measured(mocks)
        self._assert_held(mocks)

    def test_an_authorized_publication_records_it(self) -> None:
        # And the basis the road actually writes, so the case above is about
        # this publication rather than about a value nothing produces. Read as
        # the comment stood BEFORE the push, since the landing that pays a
        # debt is also what drops it.
        self._park_awaiting_authorization(_authorize_command())
        recorded = support._RecordAtHandoff(self.github, support.FIND_OPEN_PR)

        with recorded.held():
            self._run_gate(added_lines=support.OVERSIZED_ADDITIONS)

        self.assertEqual(
            recorded.pinned[_KEY_APPROVED_BASIS],
            str(_parks.LateApprovalBasis.AUTHORIZATION),
        )

    def test_a_gate_owned_approval_still_bypasses(self) -> None:
        # And the approval this gate owns is untouched, exemption or no
        # exemption. A candidate the reading found at or below the ceiling on
        # an issue still carrying an older binary's exemption earns a genuine
        # approval, and a crash before the push must not re-judge it against a
        # base that has moved since -- which is the whole of what the approval
        # bypass is for.
        for described, seeded in (
            ("no exemption", {}),
            ("a legacy exemption beside it", _legacy_exemption()),
        ):
            with self.subTest(record=described):
                self.setUp()
                self._seed(**{**seeded, **_READING_DEBT})

                mocks = self._run_gate(added_lines=support.OVERSIZED_ADDITIONS)

                self._assert_unmeasured(mocks)
                self._assert_published(mocks)


if __name__ == "__main__":
    unittest.main()
