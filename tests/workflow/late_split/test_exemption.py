# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The one commit an accepted candidate publishes under, and what it carries.

The seeds sit beside the cases rather than in a module of their own, and that
is what the member count here buys: every record a case is asked about is
written through the owner's own writer, so a case cannot be posed against a
comment no write would produce -- and damage is made the way a live comment
gets damaged, by taking a member out of a group that really round-tripped.
"""
from __future__ import annotations

import unittest
from types import MappingProxyType

from orchestrator.git.measurement.models import FINGERPRINT_FORMAT
from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.late_split import (
    exemption as _exemption,
    exemption_reading as _exemption_reading,
    keys as _late_keys,
    state as _late_state,
)
from orchestrator.workflow.late_split.formats import InvalidLateValue
from tests.workflow.late_split import exemption_test_support as _exemption_support
from tests.workflow.late_split.generation_test_support import (
    BASE_SHA,
    CANDIDATE_SHA,
    DIGEST_LENGTH,
    SHA_LENGTH,
    measured_generation,
)

# Values a hand edit or an older binary could leave in the field, none of
# which names one commit: an abbreviation, prose, a number, and a flag.
_NOT_A_COMMIT = (CANDIDATE_SHA[:7], "one coherent change", 7, True)
DESCENDANT_SHA = "d" * SHA_LENGTH

# A digest cut in half: hex, and a hash of nothing anything could be compared
# against, which is why the field is read at its exact length.
_HALF_A_DIGEST = DIGEST_LENGTH // 2

_BASE_KEY = _exemption_reading.LATE_EXEMPT_BASE_SHA
_CANDIDATE_KEY = _exemption_reading.LATE_EXEMPT_CANDIDATE_SHA
_FINGERPRINT_KEY = _exemption_reading.LATE_EXEMPT_FINGERPRINT
_FORMAT_KEY = _exemption_reading.LATE_EXEMPT_FINGERPRINT_FORMAT

# What the exempt commit carries, as the group it is written and dropped as.
_IDENTITY_KEYS = (_BASE_KEY, _CANDIDATE_KEY, _FINGERPRINT_KEY, _FORMAT_KEY)

# Every key one accepted candidate leaves behind: the write that clears a
# generation may take none of them, which is what the whole record is for.
_SURVIVING_KEYS = (_exemption_reading.LATE_EXEMPT_SHA, *_IDENTITY_KEYS)

# Every pinned comment that carries an exemption and no identity anything may
# act on. A value of None is the field being absent outright, which covers
# both a comment written before this group existed and one a crash left half
# written; anything else is a value nothing here would have written -- an
# abbreviated end, a truncated digest, a version spelled as text or minted by
# a scheme this build does not compute, and a pair whose candidate is not the
# commit the exemption names.
_UNUSABLE_IDENTITIES = MappingProxyType({
    "no base": {_BASE_KEY: None},
    "no candidate": {_CANDIDATE_KEY: None},
    "no fingerprint": {_FINGERPRINT_KEY: None},
    "no format": {_FORMAT_KEY: None},
    "an abbreviated base": {_BASE_KEY: BASE_SHA[:7]},
    "a candidate that is prose": {_CANDIDATE_KEY: "one coherent change"},
    "a truncated fingerprint": {
        _FINGERPRINT_KEY: _exemption_support.CONTRIBUTION_DIGEST[:_HALF_A_DIGEST],
    },
    "a fingerprint that is not text at all": {_FINGERPRINT_KEY: 7},
    "a format spelled as text": {_FORMAT_KEY: str(FINGERPRINT_FORMAT)},
    "a format nothing here computes": {_FORMAT_KEY: FINGERPRINT_FORMAT + 1},
    "another commit's contribution": {_CANDIDATE_KEY: BASE_SHA},
})


# What a caller can hand the write that is not the shape the field takes: an
# abbreviated end, a candidate that is prose, and a digest cut in half.
_REFUSED_WRITES = MappingProxyType({
    "an abbreviated base": {
        "base_sha": BASE_SHA[:7],
        "candidate_sha": CANDIDATE_SHA,
        "fingerprint": _exemption_support.CONTRIBUTION_DIGEST,
    },
    "a candidate that is prose": {
        "base_sha": BASE_SHA,
        "candidate_sha": "one coherent change",
        "fingerprint": _exemption_support.CONTRIBUTION_DIGEST,
    },
    "a truncated fingerprint": {
        "base_sha": BASE_SHA,
        "candidate_sha": CANDIDATE_SHA,
        "fingerprint": _exemption_support.CONTRIBUTION_DIGEST[:_HALF_A_DIGEST],
    },
})


class RecordedExemptionTest(unittest.TestCase):
    """What the field holds, and what it refuses to hold."""

    def test_the_measured_commit_round_trips(self) -> None:
        state = _exemption_support.empty_state()

        _exemption.record_exemption(state, CANDIDATE_SHA)

        self.assertEqual(_exemption_reading.read_exemption(state), CANDIDATE_SHA)
        self.assertTrue(_exemption_reading.is_exempt(state, CANDIDATE_SHA))

    def test_an_absent_field_exempts_nothing(self) -> None:
        state = _exemption_support.empty_state()

        self.assertIsNone(_exemption_reading.read_exemption(state))
        self.assertFalse(_exemption_reading.is_exempt(state, CANDIDATE_SHA))

    def test_a_value_that_is_not_a_commit_is_refused(self) -> None:
        for written in _NOT_A_COMMIT:
            with self.subTest(written=written):
                state = _exemption_support.empty_state()

                with self.assertRaises(InvalidLateValue):
                    _exemption.record_exemption(state, written)

                self.assertEqual(state.data, {})

    def test_a_damaged_field_exempts_nothing(self) -> None:
        # The gate reads this to decide whether a candidate may publish
        # unmeasured, so a value nobody here wrote has to answer "measure it"
        # rather than "let it through".
        for written in _NOT_A_COMMIT:
            with self.subTest(written=written):
                state = PinnedState(
                    data={_exemption_reading.LATE_EXEMPT_SHA: written},
                )

                self.assertIsNone(_exemption_reading.read_exemption(state))
                self.assertFalse(
                    _exemption_reading.is_exempt(state, CANDIDATE_SHA),
                )

    def test_a_moved_exemption_drops_the_identity(self) -> None:
        # An identity describes the commit the field named when it was
        # written. Left standing while that field moves on, it would match by
        # name alone the next time a verdict put the first commit back --
        # handing a later adjudication a digest taken over a base it never
        # measured, which is the one thing an id like this may not do.
        state = _exemption_support.identified_state()

        _exemption.record_exemption(state, DESCENDANT_SHA)

        self.assertEqual(_exemption_reading.read_exemption(state), DESCENDANT_SHA)
        for key in _IDENTITY_KEYS:
            with self.subTest(key=key):
                self.assertNotIn(key, state.data)

    def test_re_recording_one_commit_keeps_it(self) -> None:
        # The crash-recovery window: a settlement that died between the
        # exemption write and its handoff writes the exemption again on the
        # retry, over an identity its own earlier pass derived from the pair
        # this generation is still frozen on.
        state = _exemption_support.identified_state()

        _exemption.record_exemption(state, CANDIDATE_SHA)

        carried = _exemption_reading.read_semantic_identity(state)
        self.assertEqual(carried.fingerprint, _exemption_support.CONTRIBUTION_DIGEST)
        self.assertEqual(carried.base_sha, BASE_SHA)

    def test_clearing_takes_the_whole_record(self) -> None:
        # The identity describes the commit the exemption names, so a comment
        # that exempts none may not go on describing what one carried.
        state = _exemption_support.identified_state()
        state.data["pr_number"] = 12

        _exemption.clear_exemption(state)

        self.assertEqual(state.data, {"pr_number": 12})


class ExemptionScopeTest(unittest.TestCase):
    """One commit is exempt; the next one is a fresh candidate."""

    def test_a_new_commit_is_not_exempt(self) -> None:
        # The whole invalidation rule: work committed on top of an accepted
        # candidate is work nobody adjudicated, and it is measured as such.
        state = _exemption_support.exempted_state()

        self.assertFalse(_exemption_reading.is_exempt(state, BASE_SHA))

    def test_an_unnamable_candidate_is_not_exempt(self) -> None:
        state = _exemption_support.exempted_state()

        for asked in _NOT_A_COMMIT:
            with self.subTest(asked=asked):
                self.assertFalse(_exemption_reading.is_exempt(state, asked))

    def test_it_outlives_its_own_generation(self) -> None:
        # Both halves are written precisely so the generation CAN be cleared:
        # dropping the commit would send the same candidate back through the
        # gate and into a second adjudication, and dropping what it carries
        # would leave the retirement as the only reader that ever knew which
        # base the accepted work was measured over.
        state = _exemption_support.identified_state()
        _late_state.write_late_generation(state, measured_generation())

        _late_state.clear_late_generation(state)

        self.assertEqual(_exemption_reading.read_exemption(state), CANDIDATE_SHA)
        carried = _exemption_reading.read_semantic_identity(state)
        self.assertEqual(carried.base_sha, BASE_SHA)
        for key in _SURVIVING_KEYS:
            with self.subTest(key=key):
                self.assertNotIn(key, _late_keys.LATE_STATE_KEYS)


class SemanticIdentityTest(unittest.TestCase):
    """What the exempt commit carries, and every way it carries nothing.

    The two halves of one contract: a record whole enough to act on round
    trips entire, and a record this domain cannot vouch for -- refused on the
    way in, damaged on the pinned comment, or simply older than the field --
    hands back nothing while the exact commit stays exempt.
    """

    def test_the_accepted_contribution_round_trips(self) -> None:
        carried = _exemption_reading.read_semantic_identity(_exemption_support.identified_state())

        self.assertEqual(carried.exempt_sha, CANDIDATE_SHA)
        self.assertEqual(carried.candidate_sha, CANDIDATE_SHA)
        self.assertEqual(carried.base_sha, BASE_SHA)
        self.assertEqual(carried.fingerprint, _exemption_support.CONTRIBUTION_DIGEST)
        # The version travels with the digest because two ids taken under
        # different rules are not comparable and nothing about them says so.
        self.assertEqual(carried.fingerprint_format, FINGERPRINT_FORMAT)

    def test_a_field_that_is_not_its_shape_is_refused(self) -> None:
        # Recording one would move the failure onto a reader that has a
        # comparison to make and nothing sound to make it against.
        for field, written in _REFUSED_WRITES.items():
            with self.subTest(field=field):
                state = _exemption_support.exempted_state()

                with self.assertRaises(InvalidLateValue):
                    _exemption.record_semantic_identity(state, **written)

                self.assertIsNone(_exemption_reading.read_semantic_identity(state))

    def test_another_commits_identity_is_refused(self) -> None:
        # It would describe a change this issue never adjudicated, under the
        # authority of a verdict that was about something else.
        state = _exemption_support.exempted_state()

        with self.assertRaises(InvalidLateValue):
            _exemption.record_semantic_identity(
                state,
                base_sha=BASE_SHA,
                candidate_sha=DESCENDANT_SHA,
                fingerprint=_exemption_support.CONTRIBUTION_DIGEST,
            )

        self.assertIsNone(_exemption_reading.read_semantic_identity(state))

    def test_a_damaged_record_transfers_nothing(self) -> None:
        for described, damage in _UNUSABLE_IDENTITIES.items():
            with self.subTest(record=described):
                state = _exemption_support.damaged_state(damage)

                self.assertIsNone(_exemption_reading.read_semantic_identity(state))
                # The exact commit is exempt on its own field: a damaged
                # identity costs a later tick the transfer, never the decision
                # a human already made.
                self.assertTrue(_exemption_reading.is_exempt(state, CANDIDATE_SHA))

    def test_a_legacy_comment_transfers_nothing(self) -> None:
        # The whole of what an older binary wrote, and what every issue that
        # earned a verdict before this group existed still carries.
        state = _exemption_support.exempted_state()

        self.assertIsNone(_exemption_reading.read_semantic_identity(state))
        self.assertTrue(_exemption_reading.is_exempt(state, CANDIDATE_SHA))

    def test_an_identity_exempts_no_descendant(self) -> None:
        # The identity says which CHANGE was accepted and may not widen which
        # COMMIT is: work committed on top of the accepted candidate is work
        # nobody adjudicated, and the gate measures it as the fresh candidate
        # it is whatever the record remembers beside it.
        state = _exemption_support.identified_state()

        self.assertFalse(_exemption_reading.is_exempt(state, DESCENDANT_SHA))
        self.assertEqual(
            _exemption_reading.read_semantic_identity(state).candidate_sha,
            CANDIDATE_SHA,
        )


if __name__ == "__main__":
    unittest.main()


class ClaimedExemptionTest(unittest.TestCase):
    """Telling a comment that never had a verdict from one something damaged.

    The readers beside this answer None for both, which is right for the gate
    -- its only move is to measure the candidate afresh -- and wrong for a
    caller whose move is to walk past the issue as though nothing were in
    flight. What that caller asks is presence, and these are the three answers
    it can get.
    """

    def test_a_comment_with_no_verdict_claims_none(
        self,
    ) -> None:
        self.assertFalse(_exemption_reading.unreadable_exemption(_exemption_support.empty_state()))

    def test_a_whole_record_shows_its_claim(self) -> None:
        self.assertFalse(_exemption_reading.unreadable_exemption(_exemption_support.identified_state()))

    def test_a_legacy_comment_is_complete(self) -> None:
        # The exempt commit and nothing beside it, which is the whole of what
        # an older binary wrote. It costs a later tick the transfer rather
        # than the verdict, so it may not read as damage.
        self.assertFalse(_exemption_reading.unreadable_exemption(_exemption_support.exempted_state()))

    def test_an_exemption_that_is_not_a_commit(
        self,
    ) -> None:
        for written in _NOT_A_COMMIT:
            with self.subTest(written=written):
                state = _exemption_support.exempted_state()
                state.data[_exemption_reading.LATE_EXEMPT_SHA] = written

                self.assertTrue(_exemption_reading.unreadable_exemption(state))

    def test_an_unreadable_identity_still_claims(
        self,
    ) -> None:
        # A group with a member present that does not read back whole says
        # what this commit contributes and cannot be held to it.
        for described, damage in _UNUSABLE_IDENTITIES.items():
            with self.subTest(record=described):
                self.assertTrue(
                    _exemption_reading.unreadable_exemption(_exemption_support.damaged_state(damage)),
                )
