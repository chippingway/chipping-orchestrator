# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What a late split's umbrella still owes once a genuine edit replaced its manifest.

The drift reroute orphans the children the split made, and the ordinary decomposer tracks replacements in their
place. The snapshot was preserved for the originals, though, and the generation still records them as its
consumers -- so the ref is proved against them, read afresh because the parent's own scan is of the
replacements, while the branch, which no consumer has a claim on, is reclaimed as it always was. A replacement the
ledger records beside them holds the ref until its own work has ended too. Both hold the ref under an umbrella and
under a parent the re-decomposition left work of its own, which settles the ref before it goes back to that work;
what that parent does once it is back is `test_late_hand_back`'s subject.
"""
from __future__ import annotations

import unittest
from contextlib import nullcontext
from dataclasses import dataclass
from itertools import product
from types import MappingProxyType
from unittest.mock import patch

from orchestrator.workflow.late_split.obligations import LateResourceState
from tests.workflow.fixtures import _PatchedWorkflowMixin
from tests.workflow.stages.decomposition import (
    late_cleanup_support as _support,
    replaced_manifest_support as _redecomposition,
)
from tests.workflow.stages.decomposition.late_cleanup_support import OwnerSeed, RecordedDelete, SeededUmbrella

# Where a read of the original can fail: at the lookup itself, or past it, on
# the first attribute a lazy issue fetches itself for.
_AT_LOOKUP = "lookup"

_PAST_LOOKUP = "labels"

_REFUSED = "the original could not be read"

_RELEASE_MARKER = "<!--orchestrator-late-release owner=41"


@dataclass(frozen=True)
class _Original:
    """How the child the split made stands when the umbrella next walks."""

    label: str
    closed: bool
    failing: str = ""


class _LazyIssue:
    """An issue whose facts are requests, the way a lazy PyGithub one's are.

    The lookup that handed it back asked GitHub nothing, so the request that
    fails is the ATTRIBUTE read behind it -- which is where a guard around
    the lookup alone stops covering.
    """

    def __init__(self, issue, *, failing: str) -> None:
        self._issue = issue
        self._failing = failing

    def __getattr__(self, name: str):
        if name == self._failing:
            raise RuntimeError(_REFUSED)
        return getattr(self._issue, name)


class _OriginalUnreadable:
    """A client read that fails for the split's own child, and for no other.

    The replacements have to stay readable: the umbrella's scan of them is
    what reaches the settlement at all, and a failure there abandons the tick
    before anything is proved.
    """

    def __init__(self, github, failing: str) -> None:
        self._read = github.get_issue
        self._failing = failing

    def __call__(self, number):
        if int(number) != _support.CHILD_NUMBER:
            return self._read(number)
        if self._failing == _AT_LOOKUP:
            raise RuntimeError(_REFUSED)
        return _LazyIssue(self._read(number), failing=self._failing)


# The ways an original can still have a claim on the ref: running, put back
# by a human (the reopen leaves its terminal label where it was), and
# unreadable -- closed, but with nothing this visit could prove it by, whether
# the lookup failed or the read behind a lookup that answered did.
_UNENDED = MappingProxyType({
    "open": _Original(_support.LABEL_READY, closed=False),
    "reopened": _Original(_support.LABEL_DONE, closed=False),
    "unreadable": _Original(_support.LABEL_DONE, closed=True, failing=_AT_LOOKUP),
    "unreadable past the lookup": _Original(
        _support.LABEL_DONE, closed=True, failing=_PAST_LOOKUP,
    ),
})


class ReplacedManifestCleanupTest(_PatchedWorkflowMixin, unittest.TestCase):
    """The original consumers decide the ref, whatever the manifest tracks now."""

    def test_an_unended_original_keeps_the_ref(self) -> None:
        for (shape, original), label in product(_UNENDED.items(), _support.HANDED_ON):
            with self.subTest(shape=shape, parent=label):
                seeded = _replaced(original, label)

                deleted = self._walk(seeded, original, label)

                self.assertEqual(deleted.refs, [])
                self.assertEqual(_support.resource_states(seeded.github), {
                    _support.SUPERSEDED_BRANCH: _support.STATE_RECONCILED,
                    _support.SNAPSHOT_REF: _support.STATE_RETAINED,
                })
                self.assertEqual(seeded.github.workflow_label(seeded.parent), label)
                self.assertFalse(seeded.parent.closed)

    def test_the_ref_goes_once_the_original_ends(self) -> None:
        running = _Original(_support.LABEL_READY, closed=False)
        seeded = _replaced(running)
        self.assertEqual(self._walk(seeded, running).refs, [])
        orphan = seeded.github.get_issue(_support.CHILD_NUMBER)
        orphan.closed = True

        released = self._walk(seeded, running)

        self.assertEqual(released.refs, [_support.SNAPSHOT_REF])
        self.assertEqual(
            _support.resource_states(seeded.github)[_support.SNAPSHOT_REF],
            _support.STATE_RECONCILED,
        )
        self.assertTrue(seeded.parent.closed)
        # Told the ref is gone, and nothing more: the orphan is not taken
        # back onto the manifest, relabelled, or reopened.
        self.assertEqual(len(orphan.comments), 1)
        self.assertTrue(orphan.closed)
        self.assertNotIn(_support.CHILD_NUMBER, dict(seeded.github.label_history))
        self.assertEqual(
            seeded.github.pinned_data(_support.PARENT_NUMBER)["children"],
            [_support.REPLACEMENT_CHILD],
        )

    def _walk(self, seeded: SeededUmbrella, original: _Original, label: str = _support.UMBRELLA) -> RecordedDelete:
        """Run the poll `label` answers to, the original read the way `original` says."""
        unreadable = patch.object(
            seeded.github,
            "get_issue",
            side_effect=_OriginalUnreadable(seeded.github, original.failing),
        ) if original.failing else nullcontext()
        with unreadable:
            return _redecomposition.walk(self, seeded, _support.HAND_OFFS[label])


class RecordedReplacementTest(_PatchedWorkflowMixin, unittest.TestCase):
    """A replacement the ledger records keeps the ref until its own work ends."""

    def test_a_reopened_replacement_keeps_the_ref(self) -> None:
        # Settled in front of either hand-off, since nothing revisits the
        # ledger past it: the parent waits on its label while the replacement
        # is live, and is handed on once the ref goes.
        for label in _support.HANDED_ON:
            with self.subTest(parent=label):
                seeded, replacement = _redecomposition.redecomposed(label)
                seeded.github.get_issue(_support.CHILD_NUMBER).closed = True
                # Resolved and put back by a human: the label says `done`,
                # and the issue is live again.
                seeded.github.set_workflow_label(replacement, _support.LABEL_DONE, guarded=False)

                held = _redecomposition.walk(self, seeded, _support.HAND_OFFS[label])
                self.assertEqual(held.refs, [])
                self.assertEqual(seeded.github.workflow_label(seeded.parent), label)
                replacement.closed = True
                released = _redecomposition.walk(self, seeded, _support.HAND_OFFS[label])

                self.assertEqual(released.refs, [_support.SNAPSHOT_REF])
                self.assertEqual(
                    _support.resource_states(seeded.github)[_support.SNAPSHOT_REF],
                    _support.STATE_RECONCILED,
                )
                self.assertEqual(seeded.github.workflow_label(seeded.parent), _support.HANDED_ON[label])
                self.assertTrue(any(_RELEASE_MARKER in comment.body for comment in replacement.comments))


def _replaced(original: _Original, label: str = _support.UMBRELLA) -> SeededUmbrella:
    """A late split's parent on `label` whose manifest an edit has replaced.

    It still owes the branch and still holds the ref, and its one
    replacement is finished -- which is the reading that sends the poll to
    the hand-off and the settlement in front of it.
    """
    seeded = _support.split_umbrella(
        LateResourceState.PENDING,
        snapshot=LateResourceState.RETAINED,
        child_label=original.label,
        owner=OwnerSeed(label=label, child_closed=original.closed),
    )
    seeded.replaced()
    return seeded


if __name__ == "__main__":
    unittest.main()
