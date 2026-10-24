# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The release walk, claiming every child it would start and reading each again.

A walk takes each child's writer claim before it vouches for any, reads each
again behind its claim, and releases all of them or none: a child another
poller on this host holds, one it moved since the parent's scan, one the read
behind the claims cannot reach, or one whose pinned record admission refuses or
nobody could read holds the whole walk, parks nothing, and leaves the next walk
to try again. The record decided on is the one read behind the claims, on a
late split's own register as on an ordinary split's, and a genuinely fresh
child -- no pinned record at all -- is admitted.
"""
from __future__ import annotations

import unittest
from unittest.mock import patch

from orchestrator.workflow.stages.decomposition import parents as _parents
from tests.support.fakes import make_issue
from tests.support.writer_claims import claimable, held_elsewhere
from tests.workflow.fixtures import KEY_AWAITING_HUMAN, LABEL_DONE, LABEL_READY
from tests.workflow.stages.decomposition import child_claim_test_support as _support

_FIRST, _SECOND = _support.CHILDREN

# A version this build does not admit, on a record a child's seed would carry.
_ANOTHER_VERSION = 2

# What a human's edit leaves on the second child as its claim is granted,
# beside what the walk then releases.
_EDITED_ON_CLAIM = (
    ("refused", ()),
    ("admitted", _support.RELEASED),
)


class ClaimedReleaseTest(unittest.TestCase):
    """One `blocked` parent whose two children are both ready to start."""

    def setUp(self) -> None:
        github, parent = _support.blocked_family()
        self.github = github
        self.parent = parent

    def test_one_held_child_releases_none(self) -> None:
        with held_elsewhere(self.github.repo_id, _SECOND), self.assertLogs(_support.WORKFLOW_LOG):
            held = _support.walked(self.github, self.parent)

        self.assertEqual(self.github.label_history, [], "neither child is released")
        self.assertEqual(held, [(_FIRST, []), (_SECOND, [])])
        self.assertIsNone(self.github.pinned_data(_support.PARENT).get(KEY_AWAITING_HUMAN), "nothing parks")
        self.assertTrue(claimable(self.github.repo_id, _FIRST), "the claim taken first is given back")

        _support.walked(self.github, self.parent)

        self.assertEqual(self.github.label_history, list(_support.RELEASED))

    def test_a_child_moved_since_its_scan_waits(self) -> None:
        # Another poller finishes a child between the scan and the claims and
        # lets it go: read again under the claim it is no longer `blocked`, so
        # it is not put back to `ready`, and its sibling waits for a walk that
        # scans again.
        scan = _parents._read_child_labels(self.github, self.parent, list(_support.CHILDREN))
        with held_elsewhere(self.github.repo_id, _FIRST):
            self.github.add_issue(make_issue(_FIRST, label=LABEL_DONE, closed=True))

        _support.walked(self.github, self.parent, scan)

        self.assertEqual(self.github.label_history, [], "nothing is released off the stale scan")
        self.assertIsNone(self.github.pinned_data(_support.PARENT).get(KEY_AWAITING_HUMAN))

        _support.walked(self.github, self.parent)

        self.assertEqual(self.github.label_history, [(_SECOND, LABEL_READY)])

    def test_a_failed_reread_releases_none(self) -> None:
        scan = _parents._read_child_labels(self.github, self.parent, list(_support.CHILDREN))
        outage = ConnectionError("github unreachable")

        with patch.object(self.github, "get_issue", side_effect=outage), self.assertLogs(_support.WORKFLOW_LOG):
            held = _support.walked(self.github, self.parent, scan)

        self.assertEqual(self.github.label_history, [])
        self.assertEqual(held, [(_FIRST, []), (_SECOND, [])])

    def test_a_refused_child_record_releases_none(self) -> None:
        # Read again under its claim, the second child's record is one
        # admission refuses: nothing vouches for it, so neither child is
        # released, nothing is written to it, and the parent is not parked --
        # what the child needs is a human disposing of its record, not anything
        # this split could repair. The refusal is said locally.
        self.github.seed_state(_SECOND, raw=True, schema_version=_ANOTHER_VERSION, parent_number=_support.PARENT)
        refused = self.github.pinned_data(_SECOND)

        with self.assertLogs(_support.WORKFLOW_LOG, level="WARNING") as logged:
            held = _support.walked(self.github, self.parent)
            said = _said_refused(logged.output)

        self.assertEqual(self.github.label_history, [], "neither child is released")
        self.assertEqual(held, [(_FIRST, []), (_SECOND, [])])
        self.assertEqual(self.github.pinned_data(_SECOND), refused, "nothing is written to the child")
        self.assertEqual(self.github.posted_comments, [], "nothing is posted")
        self.assertIsNone(self.github.pinned_data(_support.PARENT).get(KEY_AWAITING_HUMAN), "nothing parks")
        self.assertTrue(said)

    def test_an_unread_child_record_releases_none(self) -> None:
        self.github.pinned_failures.unreadable.add(_SECOND)

        with self.assertLogs(_support.WORKFLOW_LOG):
            held = _support.walked(self.github, self.parent)

        self.assertEqual(self.github.label_history, [])
        self.assertEqual(held, [(_FIRST, []), (_SECOND, [])])
        self.assertIsNone(self.github.pinned_data(_support.PARENT).get(KEY_AWAITING_HUMAN))

    def test_a_raising_walk_gives_claims_back(self) -> None:
        refused = _support.RefusedWrite(self.github, self.github.set_workflow_label)

        with patch.object(self.github, "set_workflow_label", refused), self.assertRaises(RuntimeError):
            _support.walked(self.github, self.parent)

        self.assertEqual(refused.claimable_during, [False], "the child is relabelled under its claim")
        self.assertTrue(claimable(self.github.repo_id, _FIRST))
        self.assertTrue(claimable(self.github.repo_id, _SECOND))

        _support.walked(self.github, self.parent)

        self.assertEqual(self.github.label_history, list(_support.RELEASED))


class ClaimedReadingTest(unittest.TestCase):
    """The same family, whose second child's record a human edits as its claim is granted."""

    def setUp(self) -> None:
        github, parent = _support.blocked_family()
        self.github = github
        self.parent = parent

    def test_the_walk_reads_behind_its_claims(self) -> None:
        # The scan is taken first and each record only behind the claims. A
        # human's edit landing as the second child's claim is granted decides
        # the walk whatever that record read like before it: one left refused
        # holds both children, one left admitted -- over a record admission
        # refused when the walk began -- releases both.
        for edit, released in _EDITED_ON_CLAIM:
            with self.subTest(edit=edit):
                self.setUp()
                if released:
                    self._refuse(_SECOND)
                scan = _parents._read_child_labels(self.github, self.parent, list(_support.CHILDREN))

                with _support.EditedOnClaim(self._admit if released else self._refuse).installed():
                    _support.walked(self.github, self.parent, scan)

                self.assertEqual(self.github.label_history, list(released))
                self.assertIsNone(self.github.pinned_data(_support.PARENT).get(KEY_AWAITING_HUMAN))

    def _refuse(self, number: int) -> None:
        """Leave the second child's record one admission refuses, as a human's edit would; any other is left."""
        if number == _SECOND:
            self.github.seed_state(_SECOND, raw=True, schema_version=_ANOTHER_VERSION, parent_number=_support.PARENT)

    def _admit(self, number: int) -> None:
        """Leave the second child's record the supported seed its split owes it; any other is left."""
        if number == _SECOND:
            self.github.seed_state(_SECOND, parent_number=_support.PARENT)


class RegisteredReleaseTest(unittest.TestCase):
    """A late split's own register, whose release asks no lineage, over a genuinely fresh first child.

    No lineage is asked of these children, so the claimed reading's admission
    is the one question their records answer: a child with no pinned record
    at all, or a supported one, is started, and one admission refuses holds
    the whole walk with nothing written to or said on either and nothing
    parked.
    """

    def test_a_fresh_child_starts(self) -> None:
        github, parent = _support.blocked_family(registered=True)
        github.seed_state(_SECOND, parent_number=_support.PARENT)

        with self.assertNoLogs(_support.WORKFLOW_LOG, level="WARNING"):
            _support.walked(github, parent)

        self.assertEqual(github.label_history, list(_support.RELEASED))
        self.assertEqual(github.pinned_data(_FIRST), {}, "the fresh child is released with nothing written")

    def test_a_refused_member_holds_the_register(self) -> None:
        for shape in _support.UNADMITTED:
            with self.subTest(second=shape):
                github, parent = _support.blocked_family(registered=True)
                github.seed_state(_SECOND, raw=True, **_support.UNADMITTED[shape], awaiting_human=True)
                before = [_support.standing(github, number) for number in _support.CHILDREN]

                with self.assertLogs(_support.WORKFLOW_LOG, level="WARNING") as logged:
                    _support.walked(github, parent)
                    self.assertTrue(_said_refused(logged.output), "the refusal is said locally")

                self.assertEqual(github.label_history, [], "neither child is released")
                self.assertEqual([_support.standing(github, number) for number in _support.CHILDREN], before)
                self.assertIsNone(github.pinned_data(_support.PARENT).get(KEY_AWAITING_HUMAN), "nothing parks")


def _said_refused(output: list[str]) -> bool:
    """Whether a warning names the refused child's pinned comment."""
    return any(f"issue=#{_SECOND} pinned comment" in line for line in output)


if __name__ == "__main__":
    unittest.main()
