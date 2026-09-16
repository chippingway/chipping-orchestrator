# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What a squash records before it runs, and every way it records nothing."""
from __future__ import annotations

import unittest

from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.late_split import (
    collapses as _collapses,
    handoffs as _late_handoffs,
    keys as _late_keys,
    state as _late_state,
)
from orchestrator.workflow.late_split.formats import InvalidLateValue
from tests.workflow.late_split.generation_test_support import (
    BASE_SHA,
    CANDIDATE_SHA,
    SHA_LENGTH,
    measured_generation,
)

# How many commits the recorded squash replaces. Two is the ordinary collapse,
# and one is the branch whose single commit is rewritten for its subject --
# the fewest a squash replaces, so it is what the boundary is read at.
COLLAPSED_COMMITS = 2

REWRITTEN_COMMITS = 1

# How short an abbreviation has to be to still look like a commit: git prints
# one at this width, and it is not an id this domain ever recorded.
ABBREVIATED = 12

_HEAD = _collapses.LATE_COLLAPSE_HEAD
_BASE = _collapses.LATE_COLLAPSE_BASE_SHA
_COUNT = _collapses.LATE_COLLAPSE_COUNT

_HANDOFF = _late_handoffs.LATE_COLLAPSE_HANDOFF

_COLLAPSE_KEYS = (_HEAD, _BASE, _COUNT)

# Every value a recorded end can carry and not be a commit: an abbreviation,
# a number, prose, and the field simply not being there.
_UNUSABLE_ENDS = (
    None,
    CANDIDATE_SHA[:ABBREVIATED],
    CANDIDATE_SHA.upper(),
    "the head it collapsed",
    1,
)

# Every value the count can carry and not be a number of commits a squash
# replaced. Zero replaces nothing, so a record claiming it describes no
# rewrite anybody made.
_UNUSABLE_COUNTS = (None, 0, -2, True, 2.0, "2")


def _recorded(count: int = COLLAPSED_COMMITS) -> PinnedState:
    """A pinned comment carrying one whole pending collapse."""
    state = PinnedState(data={})
    _collapses.record_pending_collapse(
        state,
        head=CANDIDATE_SHA,
        base_sha=BASE_SHA,
        count=count,
    )
    return state


class RecordedCollapseTest(unittest.TestCase):
    """The three terms one squash says it is about to collapse."""

    def test_a_whole_record_reads_back_whole(self) -> None:
        # Both counts a squash replaces, since the record is the same either
        # way: two is the ordinary collapse, and one is the branch whose
        # single commit was rewritten for its subject -- which leaves the
        # recovery exactly as little to tell it from an untouched branch by.
        for count in (REWRITTEN_COMMITS, COLLAPSED_COMMITS):
            with self.subTest(count=count):
                collapse = _collapses.read_pending_collapse(_recorded(count))

                self.assertEqual(collapse.head, CANDIDATE_SHA)
                self.assertEqual(collapse.base_sha, BASE_SHA)
                self.assertEqual(collapse.count, count)

    def test_a_comment_with_no_claim_reads_absent(self) -> None:
        state = PinnedState(data={})

        self.assertFalse(_collapses.carries_pending_collapse(state))
        self.assertIsNone(_collapses.read_pending_collapse(state))

    def test_the_clear_leaves_every_other_field_alone(self) -> None:
        state = _recorded()
        state.set("branch", "topic")

        _collapses.clear_pending_collapse(state)

        self.assertFalse(_collapses.carries_pending_collapse(state))
        self.assertEqual(state.get("branch"), "topic")


class UnusableCollapseTest(unittest.TestCase):
    """A record that cannot vouch for itself is no record, and still a claim.

    The two answers are deliberately different. Nothing may be ACTED on --
    the branch a damaged record describes could be anything -- while the
    comment is still claiming a collapse is outstanding, which is what keeps
    a caller from reading the one commit on the branch as nothing to squash.
    """

    def test_a_damaged_end_reads_back_as_no_collapse(self) -> None:
        for unusable in _UNUSABLE_ENDS:
            for key in (_HEAD, _BASE):
                with self.subTest(key=key, value=unusable):
                    state = _recorded()
                    state.set(key, unusable)
                    self.assertIsNone(
                        _collapses.read_pending_collapse(state),
                    )
                    self.assertTrue(
                        _collapses.carries_pending_collapse(state),
                    )

    def test_a_count_no_squash_replaces_is_absent(self) -> None:
        for unusable in _UNUSABLE_COUNTS:
            with self.subTest(value=unusable):
                state = _recorded()
                state.set(_COUNT, unusable)
                self.assertIsNone(_collapses.read_pending_collapse(state))

    def test_a_partial_group_is_still_a_claim(self) -> None:
        for present in _COLLAPSE_KEYS:
            with self.subTest(key=present):
                state = PinnedState(data={present: None})
                self.assertTrue(
                    _collapses.carries_pending_collapse(state),
                )
                self.assertIsNone(_collapses.read_pending_collapse(state))


class RefusedCollapseWriteTest(unittest.TestCase):
    """A term the writer cannot vouch for is refused rather than recorded."""

    def test_an_end_that_is_no_commit_refuses(self) -> None:
        for unusable in _UNUSABLE_ENDS:
            with self.subTest(value=unusable):
                state = PinnedState(data={})
                with self.assertRaises(InvalidLateValue):
                    _collapses.record_pending_collapse(
                        state,
                        head=unusable,
                        base_sha=BASE_SHA,
                        count=COLLAPSED_COMMITS,
                    )
                self.assertFalse(
                    _collapses.carries_pending_collapse(state),
                )

    def test_a_count_no_squash_replaces_refuses(self) -> None:
        for unusable in _UNUSABLE_COUNTS:
            with self.subTest(value=unusable):
                state = PinnedState(data={})
                with self.assertRaises(InvalidLateValue):
                    _collapses.record_pending_collapse(
                        state,
                        head=CANDIDATE_SHA,
                        base_sha=BASE_SHA,
                        count=unusable,
                    )
                self.assertFalse(
                    _collapses.carries_pending_collapse(state),
                )


class CollapseOutlivesTheGenerationTest(unittest.TestCase):
    """The record survives the write that ends the generation beside it.

    A squash is measured under a generation the gate retires the moment it
    approves the commit, so a record cleared with one would be gone before the
    push it exists to recover ever happened.
    """

    def test_clearing_late_mode_leaves_it_standing(self) -> None:
        state = _recorded()
        _late_state.write_late_generation(state, measured_generation())

        _late_state.clear_late_generation(state)

        collapse = _collapses.read_pending_collapse(state)
        self.assertEqual(collapse.head, CANDIDATE_SHA)
        self.assertEqual(collapse.count, COLLAPSED_COMMITS)

    def test_the_keys_are_not_the_generations_own(self) -> None:
        for key in _COLLAPSE_KEYS:
            with self.subTest(key=key):
                self.assertNotIn(key, _late_keys.LATE_STATE_KEYS)


class SettledCollapseTest(unittest.TestCase):
    """The transition from the claim to the commit that succeeds it.

    The push landed and the notice went out, so nothing about the rewrite is
    outstanding -- but the relabel behind it is a second call, and an issue
    left on `validating` with nothing on the comment is one the next tick runs
    a second reviewer on, over a branch already published.
    """

    def test_the_claim_becomes_the_commit_it_settled(self) -> None:
        state = _recorded()

        _collapses.settle_pending_collapse(state, CANDIDATE_SHA)

        self.assertNotIn(_HEAD, state.data)
        self.assertEqual(
            _late_handoffs.read_settled_handoff(state), CANDIDATE_SHA,
        )

    def test_an_approval_collapsing_nothing(self) -> None:
        # There was no claim to end, and the label is the whole of what such
        # an approval ever owed.
        state = PinnedState(data={})

        _collapses.settle_pending_collapse(state, CANDIDATE_SHA)

        self.assertNotIn(_HANDOFF, state.data)

    def test_a_publication_naming_no_commit(self) -> None:
        # The claim ends whatever the publication is worth, since what ended
        # it is the push, and only the successor is held to a shape.
        for unusable in ("", *_UNUSABLE_ENDS):
            with self.subTest(unusable=unusable):
                state = _recorded()

                _collapses.settle_pending_collapse(state, unusable)

                self.assertNotIn(_HEAD, state.data)
                self.assertNotIn(_HANDOFF, state.data)

    def test_it_claims_no_outstanding_rewrite(self) -> None:
        # Nothing about the rewrite is outstanding by then, so nothing may
        # freeze the branch or refuse to resume over the record left behind.
        state = _recorded()

        _collapses.settle_pending_collapse(state, CANDIDATE_SHA)

        self.assertFalse(_collapses.carries_pending_collapse(state))
        self.assertIsNone(_collapses.read_pending_collapse(state))


class CollapseFieldSpellingTest(unittest.TestCase):
    """The wire strings live issues would carry."""

    def test_each_key_is_spelled_once(self) -> None:
        self.assertEqual(_HEAD, "late_collapse_head")
        self.assertEqual(_BASE, "late_collapse_base_sha")
        self.assertEqual(_COUNT, "late_collapse_count")

    def test_a_longer_object_id_is_still_a_commit(self) -> None:
        # git writes SHA-1 and SHA-256 object ids, and this domain records
        # whichever the repository uses.
        state = PinnedState(data={})
        wide = "f" * (SHA_LENGTH + 24)

        _collapses.record_pending_collapse(
            state, head=wide, base_sha=wide, count=COLLAPSED_COMMITS,
        )

        self.assertEqual(_collapses.read_pending_collapse(state).head, wide)


if __name__ == "__main__":
    unittest.main()
