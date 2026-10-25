# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The release walk, claiming every child it would start and reading each again.

A walk takes each child's writer claim before it vouches for any, reads each
again behind its claim, and releases all of them or none: a child another
poller on this host holds, one it moved or an operator held since the parent's
scan, one the read behind the claims cannot reach, or one whose pinned record
admission refuses or nobody could read holds the whole walk, parks nothing,
and leaves the next walk to try again. A child the scan itself reads held by
`paused` or `backlog` is kept back alone, until the hold is lifted, and so is
one a hold lands on behind the claimed re-read: each child is read again in
front of its relabel, which is made on that reading. The record decided on is
the one read behind the claims, on a late split's own register as on an
ordinary split's, and a genuinely fresh child -- no pinned record at all -- is
admitted.
"""
from __future__ import annotations

import itertools
import unittest
from functools import partial
from types import MappingProxyType
from unittest.mock import patch

from orchestrator.workflow.stages.decomposition import parents as _parents
from tests.support.fakes import make_issue
from tests.support.writer_claims import claimable, held_elsewhere
from tests.workflow.fixtures import KEY_AWAITING_HUMAN, LABEL_BLOCKED, LABEL_DONE, LABEL_READY
from tests.workflow.stages.decomposition import (
    child_claim_test_support as _support,
    late_published_support as _published,
    late_race_support as _race,
    late_test_support as _late,
    ready_test_support as _ready,
)
from tests.workflow.stages.decomposition.snapshot_client_support import Applied, SnapshotClient

_FIRST, _SECOND = _support.CHILDREN

# A version this build does not admit, on a record a child's seed would carry.
_ANOTHER_VERSION = 2

# The holds an operator applies to a child, neither of which a release lifts.
_HOLDS = ("paused", "backlog")

# What a walk releasing neither child answers it held.
_BOTH_HELD = ((_FIRST, []), (_SECOND, []))

# Where an operator's hold lands on the second child: ahead of any walk, as a
# walk's claim on it is granted, and while that walk admits the children's
# records -- behind its claimed re-read, ahead of every relabel.
_BEFORE_THE_WALK = "before the walk"

_ON_ITS_CLAIM = "as its claim is granted"

_WINDOWS = (_BEFORE_THE_WALK, _ON_ITS_CLAIM, "while the records are admitted")

# The pinned reads a walk takes up to the first child's admission: the
# parent's, then the first child's under its claim.
_READS_TO_THE_FIRST_RECORD = 2

# The fetches a walk takes of a child it releases: the scan, the reading under
# its claim, and the one in front of its relabel.
_READS_TO_THE_RELABEL = 3

# Where an operator's hold lands on the parent while its walk runs -- behind the
# scan's first child read, and behind the first relabel -- beside what that
# walk still released.
_PARENT_WINDOWS = MappingProxyType({
    ("get_issue", 1): (),
    ("move_workflow_label", 1): ((_FIRST, LABEL_READY),),
})

# How a superseded pull request reads while its supersession holds, and once
# a human reopens it.
_STATE_CLOSED = "closed"

_STATE_OPEN = "open"

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


class HeldReleaseTest(unittest.TestCase):
    """The same family, every fetch a snapshot of its own, an operator's hold applied to the second child."""

    def test_a_held_child_waits_for_its_hold(self) -> None:
        # Read off the scan, the hold keeps that child back while its sibling
        # is released. Read only behind the claims, it releases neither: the
        # scan the walk chose them from no longer says what they are, and the
        # next walk scans again, releasing the sibling alone. Landing while the
        # records are admitted -- behind that re-read -- it is read again in
        # front of the child's relabel, which is never made on a reading older
        # than the hold, and the child is held alone. Either way the held
        # child keeps its hold and its label until the hold is lifted, and each
        # child is released once.
        for hold, window in itertools.product(_HOLDS, _WINDOWS):
            with self.subTest(hold=hold, window=window):
                github, parent = _support.blocked_family(SnapshotClient())
                self._held_in(_Held(github, hold), parent, window)

                self.assertEqual(_support.walked(github, parent), [(_SECOND, [])])
                self.assertEqual(github.label_history, [(_FIRST, LABEL_READY)])
                self.assertEqual(github.label_names(_SECOND), [LABEL_BLOCKED, hold])
                github.lifted(_SECOND, hold)
                _support.walked(github, parent)

                self.assertEqual(github.label_history, list(_support.RELEASED))
                self.assertIsNone(github.pinned_data(_support.PARENT).get(KEY_AWAITING_HUMAN))

    def test_a_hold_in_the_publication_lookup_is_kept(self) -> None:
        # A split entered past publication asks its pull request last of all
        # in front of each relabel, behind the child's own read, so a hold
        # landing on the first child inside that lookup is one no reading the
        # relabel is made on shows. The relabel moves the workflow label alone:
        # the child is released with its hold still on it -- which the
        # dispatcher honors until it is lifted -- and its sibling as ever, each
        # once.
        for hold in _HOLDS:
            with self.subTest(hold=hold):
                client = SnapshotClient()
                owner = self._published(client)
                lands = _ready.LandsAfter(client, "get_pr", 1, Applied(_FIRST, hold))

                with patch.object(client, lands.request, lands):
                    _support.walked(client, owner)

                kept = sorted(client.label_names(_FIRST))
                self.assertEqual(client.label_history, list(_support.RELEASED))
                self.assertEqual(kept, sorted((hold, LABEL_READY)))

    def _published(self, client: SnapshotClient):
        """A late split's register on `client`, entered past publication, its pull request closed; the parent."""
        owner = _support.blocked_family(client, registered=True)[1]
        generation = _published.published_generation().with_split_children(_support.CHILDREN)
        client.seed_state(
            _support.PARENT, children=list(_support.CHILDREN), **_late.generation_state(generation),
        )
        _published.seed_published_pr(client, pr_state=_STATE_CLOSED)
        return owner

    def _held_in(self, held: _Held, parent, window: str) -> None:
        """Apply the hold to the second child in `window`, walking once where that window lies inside a walk.

        A walk the hold lands in as its claim is granted releases neither
        child; one it lands in while the records are admitted releases the
        first alone.
        """
        if window == _BEFORE_THE_WALK:
            held.on_claim(_SECOND)
            return
        if window == _ON_ITS_CLAIM:
            with _support.EditedOnClaim(held.on_claim).installed():
                self.assertEqual(_support.walked(held.github, parent), list(_BOTH_HELD))
            self.assertEqual(held.github.label_history, [], "nothing is released behind a stale scan")
            return
        lands = _ready.LandsAfter(held.github, "read_pinned_state", _READS_TO_THE_FIRST_RECORD, held.landed)
        with patch.object(held.github, lands.request, lands):
            self.assertEqual(_support.walked(held.github, parent), [(_SECOND, [])])


class ParentHoldReleaseTest(unittest.TestCase):
    """An operator's hold landing on the parent while its walk runs, every fetch a snapshot of its own."""

    def test_a_parent_hold_stops_the_rest(self) -> None:
        # The parent is read again in front of every relabel, so a hold an
        # operator applies to it while the walk scans its children releases
        # none of them, and one applied behind the first relabel releases no
        # more; the parent keeps the hold. Lifted, the next walk releases what
        # is left, each child once.
        for hold, window in itertools.product(_HOLDS, _PARENT_WINDOWS):
            with self.subTest(hold=hold, window=window):
                client, owner = _support.blocked_family(SnapshotClient())
                lands = _ready.LandsAfter(client, *window, Applied(_support.PARENT, hold))

                with (
                    patch.object(client, lands.request, lands),
                    self.assertLogs(_support.WORKFLOW_LOG, level="INFO"),
                ):
                    _support.walked(client, owner)

                self.assertEqual(client.label_history, list(_PARENT_WINDOWS[window]))
                self.assertIn(hold, client.label_names(_support.PARENT))
                client.lifted(_support.PARENT, hold)
                _support.walked(client, owner)
                self.assertEqual(client.label_history, list(_support.RELEASED))


class _Held:
    """An operator's `paused` or `backlog` landing on the second child as GitHub holds it."""

    def __init__(self, github: SnapshotClient, hold: str) -> None:
        self.github = github
        self._hold = hold

    def on_claim(self, number: int) -> None:
        """Apply the hold where `number` is the second child; any other is left."""
        if number == _SECOND:
            self.github.applied(_SECOND, self._hold)

    def landed(self, gh, issue) -> None:
        """Apply the hold behind whichever request it lands after."""
        self.github.applied(_SECOND, self._hold)


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

    def test_a_reopen_in_the_last_read_holds_it(self) -> None:
        # The split was entered past publication, and the pull request its
        # children took over reopens while the walk reads the first child
        # again in front of its relabel. That read keeps an operator's hold
        # from being written away, and the licence is asked behind it, the
        # last request in front of the relabel: every child is held and none
        # released.
        github, parent, reopen = self._reopened_register()

        with reopen.installed(), self.assertLogs(_support.WORKFLOW_LOG, level="ERROR"):
            held = _support.walked(github, parent)

        self.assertEqual((github.label_history, held), ([], list(_BOTH_HELD)))

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


    def _reopened_register(self) -> tuple:
        """A register whose split superseded a pull request, reopened behind the first child's last read.

        The client, the parent, and the fetch the reopen lands behind.
        """
        github, parent = _support.blocked_family(registered=True)
        generation = _published.published_generation().with_split_children(_support.CHILDREN)
        github.seed_state(
            _support.PARENT, children=list(_support.CHILDREN), **_late.generation_state(generation),
        )
        published = _published.seed_published_pr(github, pr_state=_STATE_CLOSED)
        reopened = partial(setattr, published, "state", _STATE_OPEN)
        return github, parent, _race.MovedOnRead(github, _FIRST, _READS_TO_THE_RELABEL, reopened)


def _said_refused(output: list[str]) -> bool:
    """Whether a warning names the refused child's pinned comment."""
    return any(f"issue=#{_SECOND} pinned comment" in line for line in output)


if __name__ == "__main__":
    unittest.main()
