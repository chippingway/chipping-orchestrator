# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Monotonic cycle/generation identities, the lineage bound, fingerprints."""
from __future__ import annotations

import unittest

from orchestrator.workflow.late_split import identity as _identity
from orchestrator.workflow.late_split.generation_reading import MAX_LINEAGE_DEPTH
from orchestrator.workflow.late_split.models import LateResource, LateResourceKind
from tests.workflow.late_split import generation_test_support as _support


class MonotonicIdentityTest(unittest.TestCase):
    """An identity only ever moves forward, whatever it is handed."""

    def test_each_predecessor_is_followed_by_one_more(self) -> None:
        self.assertEqual(_identity.next_identity(1), 2)
        self.assertEqual(_identity.next_identity(7), 8)

    def test_an_unusable_predecessor_starts_at_one(self) -> None:
        # A record that never carried an identity, one whose field was
        # hand-edited to something unreadable, and one carrying a number no
        # cycle could have had all start the sequence rather than continuing
        # a count nothing wrote.
        for predecessor in (None, 0, -4, "", "seven", [2], True, 2.9):
            with self.subTest(predecessor=predecessor):
                self.assertEqual(_identity.next_identity(predecessor), 1)

    def test_repeated_calls_never_reuse_a_number(self) -> None:
        seen = []
        current = 0
        for _ in range(5):
            current = _identity.next_identity(current)
            seen.append(current)
        self.assertEqual(seen, sorted(set(seen)))


class LineageDepthTest(unittest.TestCase):
    """A child is born one deeper, and only while the bound allows it."""

    def test_a_child_is_one_deeper(self) -> None:
        for depth in range(MAX_LINEAGE_DEPTH):
            with self.subTest(depth=depth):
                self.assertEqual(
                    _identity.child_lineage_depth(depth), depth + 1,
                )

    def test_the_bound_refuses_a_further_generation(self) -> None:
        # At the bound an indivisible oversized child has to resolve as one
        # change or ask a human; returning a depth here is what would let it
        # split instead.
        # 2.5 is the case a plain range check gets wrong: it is under the
        # bound, and adding one to it would hand a child depth 3.5.
        for depth in (MAX_LINEAGE_DEPTH, MAX_LINEAGE_DEPTH + 1, -1, None, 2.5):
            with self.subTest(depth=depth), self.assertRaises(_identity.LineageDepthExceeded):
                _identity.child_lineage_depth(depth)


class ResourceFingerprintTest(unittest.TestCase):
    """One ledger entry's telemetry identity: stable, bounded, name-free."""

    def test_one_resource_prints_the_same_every_time(self) -> None:
        # What makes a retried cleanup one step rather than two.
        self.assertEqual(
            _identity.resource_fingerprint(_support.FIRST_CHILD),
            _identity.resource_fingerprint(_support.FIRST_CHILD),
        )

    def test_the_print_ignores_how_far_the_entry_got(self) -> None:
        # State is the outcome a record reports separately; the print names
        # the resource, so a pending and a reconciled snapshot are one ref.
        self.assertEqual(
            _identity.resource_fingerprint(_support.SNAPSHOT),
            _identity.resource_fingerprint(_support.RECLAIMED_SNAPSHOT),
        )

    def test_two_resources_of_one_kind_differ(self) -> None:
        self.assertNotEqual(
            _identity.resource_fingerprint(_support.FIRST_CHILD),
            _identity.resource_fingerprint(_support.SECOND_CHILD),
        )

    def test_the_kind_is_part_of_the_print(self) -> None:
        # A branch and a ref spelled the same are two obligations.
        same_target = LateResource(
            kind=LateResourceKind.BRANCH, target=_support.SNAPSHOT_REF,
        )
        self.assertNotEqual(
            _identity.resource_fingerprint(same_target),
            _identity.resource_fingerprint(_support.SNAPSHOT),
        )

    def test_the_print_is_bounded_and_carries_no_name(self) -> None:
        printed = _identity.resource_fingerprint(_support.FIRST_CHILD)
        self.assertEqual(len(printed), _identity.RESOURCE_FINGERPRINT_LENGTH)
        self.assertNotIn(_support.FIRST_CHILD.target, printed)


class FingerprintTest(unittest.TestCase):
    """The two local fingerprints move on their own content and nothing else."""

    def test_title_and_body_are_told_apart(self) -> None:
        # Joined by a separator no issue text can hold, so moving a word from
        # the title into the body is a change rather than the same hash.
        moved = _identity.title_body_fingerprint("scope", " detail")
        split_across = _identity.title_body_fingerprint("scope ", "detail")
        self.assertNotEqual(moved, split_across)

    def test_the_same_content_fingerprints_the_same(self) -> None:
        self.assertEqual(
            _identity.title_body_fingerprint("t", "b"),
            _identity.title_body_fingerprint("t", "b"),
        )

    def test_a_comment_past_the_baseline_moves_it(self) -> None:
        baseline = _identity.comment_fingerprint(("answer one",))
        answered = _identity.comment_fingerprint(("answer one", "answer two"))
        self.assertNotEqual(baseline, answered)

    def test_comment_order_is_part_of_the_fingerprint(self) -> None:
        # Two answers swapped are not the same conversation, and reading them
        # as one would leave a resumed round quoting a reply nobody wrote last.
        self.assertNotEqual(
            _identity.comment_fingerprint(("first", "second")),
            _identity.comment_fingerprint(("second", "first")),
        )


if __name__ == "__main__":
    unittest.main()
