# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The oversized publication an operator authorized, whole and every way not."""
from __future__ import annotations

import unittest
from types import MappingProxyType

from orchestrator.git.measurement.models import FINGERPRINT_FORMAT
from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.late_split import (
    exemption as _exemption,
    exemption_reading as _exemption_reading,
    keys as _late_keys,
    overrides as _overrides,
    state as _late_state,
)
from orchestrator.workflow.late_split.formats import InvalidLateValue
from tests.workflow.late_split.generation_test_support import (
    ADDITIONS,
    BASE_SHA,
    CANDIDATE_SHA,
    DIGEST_LENGTH,
    SHA_LENGTH,
    THRESHOLD,
    measured_generation,
)

# The comment the authorization was made in, and the digest of the
# contribution an operator read before making it.
AUTHORIZING_COMMENT_ID = 4242
CONTRIBUTION_DIGEST = "e" * DIGEST_LENGTH

# A commit made on top of the authorized one: work nobody read, carried by an
# object no authorization names. It stands in for a rewrite's product too --
# what makes the two different is the record that explains the object, and
# there is no such record here.
DESCENDANT_SHA = "d" * SHA_LENGTH

# The base a rewrite replays the accepted contribution over. Its own commit,
# since the whole of what a carried authorization moves is the pair.
REWRITTEN_BASE_SHA = "9" * SHA_LENGTH

# A digest cut in half: hex, and a hash of nothing anything could be compared
# against, which is why the field is read at its exact length.
_HALF_A_DIGEST = DIGEST_LENGTH // 2

_CANDIDATE_KEY = _overrides.LATE_OVERRIDE_CANDIDATE_SHA
_BASE_KEY = _overrides.LATE_OVERRIDE_BASE_SHA
_FINGERPRINT_KEY = _overrides.LATE_OVERRIDE_FINGERPRINT
_FORMAT_KEY = _overrides.LATE_OVERRIDE_FINGERPRINT_FORMAT
_ADDITIONS_KEY = _overrides.LATE_OVERRIDE_ADDITIONS
_THRESHOLD_KEY = _overrides.LATE_OVERRIDE_THRESHOLD
_COMMENT_KEY = _overrides.LATE_OVERRIDE_COMMENT_ID

# Every key one authorization leaves behind: the write that clears a
# generation may take none of them, which is what the record is for.
_SURVIVING_KEYS = (
    _CANDIDATE_KEY,
    _BASE_KEY,
    _FINGERPRINT_KEY,
    _FORMAT_KEY,
    _ADDITIONS_KEY,
    _THRESHOLD_KEY,
    _COMMENT_KEY,
)

# Values a hand edit or an older binary could leave in a commit field, none of
# which names one: an abbreviation, prose, a number, and a flag.
_NOT_A_COMMIT = (CANDIDATE_SHA[:7], "publish it as it stands", 7, True)

# Every pinned comment that authorizes nothing. A value of None is the field
# absent outright, which covers both a comment written before the group
# existed and one a crash left half written; anything else is a value nothing
# here would have written -- an abbreviated end, a truncated digest, a version
# spelled as text or minted by a scheme this build does not compute, a
# measurement nobody took, a comment that names none, and a reading at or
# under its own ceiling, which describes a candidate the gate publishes
# untouched and so a decision nobody had to make.
_UNUSABLE_RECORDS = MappingProxyType({
    "no candidate": {_CANDIDATE_KEY: None},
    "no base": {_BASE_KEY: None},
    "no fingerprint": {_FINGERPRINT_KEY: None},
    "no format": {_FORMAT_KEY: None},
    "no additions": {_ADDITIONS_KEY: None},
    "no threshold": {_THRESHOLD_KEY: None},
    "no comment": {_COMMENT_KEY: None},
    "an abbreviated candidate": {_CANDIDATE_KEY: CANDIDATE_SHA[:7]},
    "a base that is prose": {_BASE_KEY: "the base it was read over"},
    "a truncated fingerprint": {
        _FINGERPRINT_KEY: CONTRIBUTION_DIGEST[:_HALF_A_DIGEST],
    },
    "a fingerprint that is not text at all": {_FINGERPRINT_KEY: 7},
    "a format spelled as text": {_FORMAT_KEY: str(FINGERPRINT_FORMAT)},
    "a format nothing here computes": {_FORMAT_KEY: FINGERPRINT_FORMAT + 1},
    "additions spelled as text": {_ADDITIONS_KEY: str(ADDITIONS)},
    "additions nothing measured": {_ADDITIONS_KEY: -1},
    "a threshold nothing configured": {_THRESHOLD_KEY: -1},
    "a threshold spelled as a flag": {_THRESHOLD_KEY: True},
    "a comment that is no identity": {_COMMENT_KEY: 0},
    "a comment spelled as text": {_COMMENT_KEY: str(AUTHORIZING_COMMENT_ID)},
    "a candidate exactly at the ceiling": {_ADDITIONS_KEY: THRESHOLD},
    "a candidate under the ceiling": {_ADDITIONS_KEY: THRESHOLD - 1},
})

# What a caller can hand the write that is not the term the field takes, and
# the one whole-shaped set of terms that still authorizes nothing: a
# measurement the gate would have published without asking anybody.
_REFUSED_TERMS = MappingProxyType({
    "an abbreviated candidate": {"candidate_sha": CANDIDATE_SHA[:7]},
    "a base that is prose": {"base_sha": "the base it was read over"},
    "a truncated fingerprint": {
        "fingerprint": CONTRIBUTION_DIGEST[:_HALF_A_DIGEST],
    },
    "a fingerprint that is not text at all": {"fingerprint": 7},
    "additions nothing measured": {"additions": -1},
    "a threshold spelled as a flag": {"threshold": True},
    "a threshold spelled as text": {"threshold": str(THRESHOLD)},
    "a measurement the gate would publish": {"additions": THRESHOLD},
    "a comment that is no identity": {"comment_id": 0},
    "a comment spelled as text": {"comment_id": str(AUTHORIZING_COMMENT_ID)},
})


def authorized_publication(**replaced) -> _overrides.LateOversizedPublication:
    """The terms one operator authorized, with whatever a case replaces."""
    terms = {
        "candidate_sha": CANDIDATE_SHA,
        "base_sha": BASE_SHA,
        "fingerprint": CONTRIBUTION_DIGEST,
        "additions": ADDITIONS,
        "threshold": THRESHOLD,
        "comment_id": AUTHORIZING_COMMENT_ID,
    }
    return _overrides.LateOversizedPublication(**{**terms, **replaced})


def authorized_state() -> PinnedState:
    """A pinned comment carrying one whole authorization and nothing else."""
    state = PinnedState(data={})
    _overrides.record_publication_override(state, authorized_publication())
    return state


def damaged_state(damage: dict) -> PinnedState:
    """That record with one field absent, or carrying what nobody here wrote."""
    state = authorized_state()
    for key, written in damage.items():
        if written is None:
            state.data.pop(key, None)
        else:
            state.data[key] = written
    return state


class AuthorizedPublicationTest(unittest.TestCase):
    """What one whole record holds, and which commit it holds it for."""

    def test_the_authorized_terms_round_trip(self) -> None:
        state = authorized_state()

        override = _overrides.read_publication_override(state)

        self.assertEqual(override.publication, authorized_publication())
        # The version travels with the digest because two ids taken under
        # different rules are not comparable and nothing about them says so.
        self.assertEqual(override.fingerprint_format, FINGERPRINT_FORMAT)
        self.assertTrue(_overrides.is_authorized(state, CANDIDATE_SHA))

    def test_no_record_authorizes_nothing(self) -> None:
        # Also the whole of what an older binary left behind: an issue whose
        # pinned comment predates this group carries none of its keys.
        state = PinnedState(data={})

        self.assertIsNone(_overrides.read_publication_override(state))
        self.assertFalse(_overrides.is_authorized(state, CANDIDATE_SHA))

    def test_a_commit_made_after_it_is_not_authorized(self) -> None:
        # The whole invalidation rule: work committed on top of the candidate
        # an operator read is work nobody read, and the gate measures it.
        state = authorized_state()

        self.assertFalse(_overrides.is_authorized(state, DESCENDANT_SHA))

    def test_an_unnamable_candidate_is_not_authorized(self) -> None:
        state = authorized_state()

        for asked in _NOT_A_COMMIT:
            with self.subTest(asked=asked):
                self.assertFalse(_overrides.is_authorized(state, asked))

    def test_a_second_write_replaces_the_record(self) -> None:
        # The fields match by name, so a member left behind by a narrower
        # write would read as part of the record beside it -- an
        # authorization half about one candidate and half about another.
        state = authorized_state()

        _overrides.record_publication_override(
            state,
            authorized_publication(
                candidate_sha=DESCENDANT_SHA,
                additions=ADDITIONS + 1,
                comment_id=AUTHORIZING_COMMENT_ID + 1,
            ),
        )

        authorized = _overrides.read_publication_override(state).publication
        self.assertEqual(authorized.candidate_sha, DESCENDANT_SHA)
        self.assertEqual(authorized.additions, ADDITIONS + 1)
        self.assertEqual(authorized.comment_id, AUTHORIZING_COMMENT_ID + 1)
        self.assertFalse(_overrides.is_authorized(state, CANDIDATE_SHA))


class RefusedAuthorizationTest(unittest.TestCase):
    """Terms this domain will not record, rather than record unusably."""

    def test_a_term_that_is_not_its_shape_is_refused(self) -> None:
        # Recording one would move the failure onto a reader that has a
        # candidate in hand and no sound grounds to let it publish.
        for described, replaced in _REFUSED_TERMS.items():
            with self.subTest(term=described):
                state = PinnedState(data={})

                with self.assertRaises(InvalidLateValue):
                    _overrides.record_publication_override(
                        state, authorized_publication(**replaced),
                    )

                self.assertEqual(state.data, {})

    def test_the_terms_answer_for_themselves(self) -> None:
        # Asked of the group rather than beside the writer, so a caller that
        # has not decided to record yet gets the same answer as one that has
        # -- and gets the term and the type it arrived as, never the value,
        # since a refusal about an unvouched-for value is read by a log.
        for described, replaced in _REFUSED_TERMS.items():
            with self.subTest(term=described):
                refusal = authorized_publication(**replaced).unusable_terms

                self.assertTrue(refusal)
                for named in replaced.values():
                    self.assertNotIn(str(named), refusal)

    def test_whole_terms_answer_nothing(self) -> None:
        # The other side of it, so the refusals above are about the term that
        # was replaced rather than about the property refusing everything.
        self.assertEqual(authorized_publication().unusable_terms, "")

    def test_omitted_terms_are_refused(self) -> None:
        # Every field defaults to a value this domain refuses, so a caller
        # that named none of them is told it has no authorization to record.
        state = PinnedState(data={})

        with self.assertRaises(InvalidLateValue):
            _overrides.record_publication_override(
                state, _overrides.LateOversizedPublication(),
            )

        self.assertEqual(state.data, {})


class DamagedAuthorizationTest(unittest.TestCase):
    """A record this build cannot vouch for entirely authorizes nothing."""

    def test_a_damaged_record_authorizes_nothing(self) -> None:
        # Every member IS the authorization here: what a bypass of the size
        # gate licenses is what a human looked at, so a record short of any
        # term costs the candidate a measurement rather than buying it one.
        for described, damage in _UNUSABLE_RECORDS.items():
            with self.subTest(record=described):
                state = damaged_state(damage)

                self.assertIsNone(_overrides.read_publication_override(state))
                self.assertFalse(
                    _overrides.is_authorized(state, CANDIDATE_SHA),
                )


class AuthorizationLifetimeTest(unittest.TestCase):
    """How long the record lasts, and which fields it may ever touch."""

    def test_it_outlives_its_own_generation(self) -> None:
        # The record is written so the generation CAN be cleared: dropping it
        # would send the authorized candidate back through the gate and into
        # the adjudication a human already answered.
        state = authorized_state()
        _late_state.write_late_generation(state, measured_generation())

        _late_state.clear_late_generation(state)

        self.assertTrue(_overrides.is_authorized(state, CANDIDATE_SHA))
        for key in _SURVIVING_KEYS:
            with self.subTest(key=key):
                self.assertNotIn(key, _late_keys.LATE_STATE_KEYS)

    def test_clearing_takes_the_whole_group(self) -> None:
        state = authorized_state()
        state.data["pr_number"] = 12

        _overrides.clear_publication_override(state)

        self.assertEqual(state.data, {"pr_number": 12})
        self.assertIsNone(_overrides.read_publication_override(state))

    def test_a_rewrite_carries_it_onto_the_new_pair(self) -> None:
        # The exemption moves onto the object a workflow rewrite replaced the
        # accepted commit with, and the authorization has to move with it: a
        # commit an exemption names and no authorization stands behind is one
        # the gate measures, so left behind it would hold a rewrite nobody has
        # to decide about again. The pair moves and nothing else does -- the
        # size, the ceiling, and the comment are what a human decided, and the
        # digest already describes the rewritten pair, since a transfer is
        # granted only over contributions that fingerprint alike.
        state = authorized_state()

        _overrides.carry_publication_override(
            state, CANDIDATE_SHA, DESCENDANT_SHA, REWRITTEN_BASE_SHA,
        )

        carried = _overrides.read_publication_override(state).publication
        self.assertEqual(carried.candidate_sha, DESCENDANT_SHA)
        self.assertEqual(carried.base_sha, REWRITTEN_BASE_SHA)
        self.assertEqual(carried.fingerprint, CONTRIBUTION_DIGEST)
        self.assertEqual(carried.additions, ADDITIONS)
        self.assertEqual(carried.threshold, THRESHOLD)
        self.assertEqual(carried.comment_id, AUTHORIZING_COMMENT_ID)
        self.assertFalse(_overrides.is_authorized(state, CANDIDATE_SHA))

    def test_a_record_it_may_not_redirect_is_left(self) -> None:
        # Two comments this write may not touch: one carrying no
        # authorization this build can read whole, and one whose
        # authorization is about some other commit. Redirected, either would
        # become a bypass for a candidate nobody granted one for.
        for shape, state in (
            ("damaged", damaged_state({_FINGERPRINT_KEY: None})),
            ("another candidate", authorized_state()),
        ):
            with self.subTest(shape=shape):
                before = dict(state.data)

                _overrides.carry_publication_override(
                    state, DESCENDANT_SHA, CANDIDATE_SHA, REWRITTEN_BASE_SHA,
                )

                self.assertEqual(state.data, before)

    def test_every_other_field_is_left_verbatim(self) -> None:
        # The pinned comment is shared, and an authorization is only ever
        # about its own fields: an exemption group and a field this build has
        # never heard of are both left exactly as they were found.
        state = PinnedState(data={})
        _exemption.record_exemption(state, DESCENDANT_SHA)
        _exemption.record_semantic_identity(
            state,
            base_sha=BASE_SHA,
            candidate_sha=DESCENDANT_SHA,
            fingerprint=CONTRIBUTION_DIGEST,
        )
        state.data["late_something_older"] = {"kept": [1, 2]}
        untouched = dict(state.data)

        _overrides.record_publication_override(state, authorized_publication())

        self.assertEqual(_exemption_reading.read_exemption(state), DESCENDANT_SHA)
        _overrides.clear_publication_override(state)
        self.assertEqual(state.data, untouched)


if __name__ == "__main__":
    unittest.main()
