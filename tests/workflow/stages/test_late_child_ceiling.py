# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What a child of a late split is measured to be, and what the number earns.

A split exists to turn one oversized candidate into children that each land
under the ceiling, so the whole arrangement rests on a child being held to the
same reading its parent was: the frozen base against the commit being
published, across every path, over however many commits the slice took. These
drive that end to end -- the split that really creates the child, a real
checkout, git's own count, and the tick's own publication -- because the claim
is about the number rather than about what a gate does with one it was handed.

What the boundary is, and what a child may carry over from the issue that
created it, are the other half. Exactly at the ceiling publishes and one line
past it is held; an exemption an older binary wrote buys a child no more than
it buys anybody; and neither the exemption nor the authorization beside it is
something the split hands down or a later commit inherits.
"""

from __future__ import annotations

import unittest
from types import MappingProxyType

from orchestrator.workflow.late_split import (
    exemption_reading as _exemption_reading,
    overrides as _overrides,
)
from tests.workflow.fixtures import (
    LABEL_DECOMPOSING,
    LABEL_VALIDATING,
    _authorized_exemption,
    _legacy_exemption,
)
from tests.workflow.stages import (
    late_child_test_support as support,
    slice_checkout as _slice,
)
from tests.workflow.stages.implementing import late_gate_test_support as _gate

# The whole bypass, as a child's pinned comment would have to carry it: the
# adjudication's exact-SHA claim, and the terms an operator authorized it on.
_BYPASS_KEYS = (
    _exemption_reading.LATE_EXEMPT_SHA,
    _overrides.LATE_OVERRIDE_CANDIDATE_SHA,
    _overrides.LATE_OVERRIDE_BASE_SHA,
    _overrides.LATE_OVERRIDE_FINGERPRINT,
    _overrides.LATE_OVERRIDE_ADDITIONS,
    _overrides.LATE_OVERRIDE_THRESHOLD,
    _overrides.LATE_OVERRIDE_COMMENT_ID,
)

# How deep a child sits, as the ancestry group spells it. That group outlives
# every generation on the issue, so it is a different field from the one a
# generation carries the same number in.
_ANCESTRY_DEPTH = "late_ancestry_depth"

# One line of work past the slice, which is what a developer resumed on a
# human's guidance comes back with.
_ONE_MORE_LINE = 1

# The three readings of this candidate that are not the whole of it: the last
# commit alone, the paths carrying the implementation alone, and everything
# that is not documentation. Each is a number the gate could have come back
# with had it measured an increment or a subset of the paths.
_NARROWER_READINGS = MappingProxyType({
    "the last commit alone": _slice.LATEST_COMMIT_ONLY,
    "the implementation paths alone": _slice.IMPLEMENTATION_ONLY,
    "everything but the documentation": _slice.WITHOUT_DOCUMENTATION,
})


class ChildCumulativeReadingTest(support._SliceGateCase, unittest.TestCase):
    """A child's candidate is its whole diff, not the part a reading picks."""

    def test_every_commit_and_every_path_is_counted(self) -> None:
        # The number git produced for `base...candidate`, which is the sum of
        # what all three commits wrote across implementation, tests and
        # documentation alike -- and it is the number the record the
        # adjudication reconciles from carries.
        self._run_slice(ceiling=_slice.LARGEST_NARROWER_READING)

        self.assertEqual(self._measured(), _slice.WHOLE_SLICE)
        self.assertEqual(
            self._pinned()[_gate.KEY_ADDITIONS], _slice.WHOLE_SLICE,
        )

    def test_the_cumulative_reading_is_what_holds_it(self) -> None:
        # Held under a ceiling every narrower reading of the same candidate
        # clears -- which is the counterfactual beside it, run over these very
        # commits. Incremental measurement and path exclusions are the two
        # ways a slice is grown past a ceiling one commit and one directory at
        # a time, and the cumulative reading is what buys neither of them.
        mocks = self._run_slice(ceiling=_slice.LARGEST_NARROWER_READING)

        self._assert_held(mocks)
        self.assertEqual(
            self._labelled(), [(self.issue.number, LABEL_DECOMPOSING)],
        )

    def test_a_narrower_reading_would_publish_it(self) -> None:
        for reading, narrower in _NARROWER_READINGS.items():
            with self.subTest(reading=reading):
                self.setUp()

                mocks = self._run_slice(
                    ceiling=_slice.LARGEST_NARROWER_READING,
                    added_lines=narrower,
                )

                self._assert_published(mocks)


class ChildCeilingBoundaryTest(support._SliceGateCase, unittest.TestCase):
    """Where the line is drawn for a child, counted in real added lines."""

    def test_a_child_exactly_at_the_ceiling_publishes(self) -> None:
        # Strictly past is the trigger, so the candidate that measures to the
        # configured value goes out exactly as a small one does. The
        # generation is dropped with it and the ancestry the split wrote is
        # not: a child that lost its lineage on publishing would mint its next
        # generation as a root at depth 0 and buy the split another one.
        mocks = self._run_slice(ceiling=_slice.WHOLE_SLICE)

        self._assert_published(mocks)
        self.assertEqual(self._measured(), _slice.WHOLE_SLICE)
        self.assertEqual(
            self._labelled(), [(self.issue.number, LABEL_VALIDATING)],
        )
        pinned = self._pinned()
        self.assertNotIn(_gate.KEY_CANDIDATE_SHA, pinned)
        self.assertEqual(
            pinned[_ANCESTRY_DEPTH], self.seeded[_ANCESTRY_DEPTH],
        )

    def test_a_child_one_line_past_it_is_held(self) -> None:
        # The same commits under a ceiling one line lower: nothing pushed, no
        # pull request, and the issue handed to the adjudication that splits
        # it again.
        mocks = self._run_slice(ceiling=_slice.WHOLE_SLICE - 1)

        self._assert_held(mocks)
        self.assertEqual(
            self._labelled(), [(self.issue.number, LABEL_DECOMPOSING)],
        )


class ChildBypassScopeTest(support._SliceGateCase, unittest.TestCase):
    """Nothing that let a parent publish is a thing its child may spend.

    The bypass is bound to one commit on one issue, and a child is neither:
    its slice is work no adjudicator ruled on and no operator read, so its
    first oversized candidate is the gate's question all over again.
    """

    def test_the_split_hands_a_child_no_bypass(self) -> None:
        # The sharpest shape there is: the parent authorized the very commit
        # this child's slice is committed at, over the very base it was cut
        # against. The write that creates and attributes a child carries
        # neither half of that across, so the child reaches its own gate with
        # nothing on its record that skips a reading -- and is measured.
        parent = self.github.pinned_data(self.parent.number)

        mocks = self._run_slice(ceiling=_slice.WHOLE_SLICE - 1)

        self._assert_measured(mocks)
        self._assert_held(mocks)
        pinned = self._pinned()
        for carried in _BYPASS_KEYS:
            with self.subTest(carried=carried):
                self.assertIn(carried, parent)
                self.assertNotIn(carried, self.seeded)
                self.assertNotIn(carried, pinned)

    def test_it_covers_no_commit_made_on_top(self) -> None:
        # And the same rule one issue down: both halves are exact-SHA claims,
        # so a commit made past the authorized one carries work nobody ruled
        # on and nobody read. What it is measured to is its own whole diff,
        # the slice underneath it included, rather than the line it added.
        grown = self.checkout.commit_on_top(_ONE_MORE_LINE)
        self._seed_child(**_authorized_exemption(
            self.checkout.candidate, self.checkout.base,
        ))

        mocks = self._run_slice(
            ceiling=_slice.WHOLE_SLICE - 1, candidate=grown,
        )

        self._assert_measured(mocks)
        self._assert_held(mocks)
        self.assertEqual(
            self._measured(), _slice.WHOLE_SLICE + _ONE_MORE_LINE,
        )


class ChildUnauthorizedExemptionTest(
    support._SliceGateCase, unittest.TestCase,
):
    """A child carrying an exemption no operator authorization stands behind.

    A `single` verdict used to record one with no gesture behind it, so a live
    child can carry an adjudication no human ever read. It buys no publication
    by itself: the candidate is counted like every other, and the count is the
    whole of what happens next. The decision that ends an oversized one's wait
    is made on one tick and acted on by the next, which is what a restart is
    -- nothing survives a tick here but the pinned comment.
    """

    def setUp(self) -> None:
        super().setUp()
        self._seed_child(**_legacy_exemption(self.checkout.candidate))

    def test_it_publishes_on_its_own_count(self) -> None:
        # The exemption changes nothing about a change the ceiling would have
        # let through, and the boundary stays inclusive over a real count.
        mocks = self._run_slice(ceiling=_slice.WHOLE_SLICE)

        self._assert_measured(mocks)
        self._assert_published(mocks)
        self.assertEqual(
            self._labelled(), [(self.issue.number, LABEL_VALIDATING)],
        )

    def test_past_the_ceiling_it_waits_for_a_person(self) -> None:
        # Not the adjudication, which has already answered this candidate --
        # the park asking the one question an exemption cannot answer for
        # itself, which is whether a human agreed to publish it.
        mocks = self._run_slice(ceiling=_slice.WHOLE_SLICE - 1)

        self._assert_held(mocks)
        pinned = self._pinned()
        self.assertTrue(pinned[_gate.AWAITING_HUMAN])
        self.assertEqual(
            pinned[_gate.PARK_REASON], _gate.PARK_UNAUTHORIZED_EXEMPTION,
        )

    def test_a_later_process_publishes_it(self) -> None:
        # The park's own command, read by a tick sharing nothing with the one
        # that took it: the terms go on the record and the commit publishes.
        self._run_slice(ceiling=_slice.WHOLE_SLICE - 1)
        self._authorize(self.checkout.candidate)

        mocks = self._run_slice(ceiling=_slice.WHOLE_SLICE - 1)

        self._assert_published(mocks)
        pinned = self._pinned()
        self.assertEqual(
            pinned[_overrides.LATE_OVERRIDE_CANDIDATE_SHA],
            self.checkout.candidate,
        )
        # And the terms that operator is held to are the cumulative reading
        # itself, so a later reader can still say what was authorized.
        self.assertEqual(
            pinned[_overrides.LATE_OVERRIDE_ADDITIONS], _slice.WHOLE_SLICE,
        )
        self.assertEqual(
            pinned[_overrides.LATE_OVERRIDE_THRESHOLD],
            _slice.WHOLE_SLICE - 1,
        )


if __name__ == "__main__":
    unittest.main()
