# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What a late split's umbrella still owes once a genuine edit replaced its manifest.

The drift reroute orphans the children the split made, and the ordinary decomposer tracks replacements in their
place. The snapshot was preserved for the originals, though, and the generation still records them as its
consumers -- so the ref is proved against them, read afresh because the umbrella's own scan is of the
replacements, while the branch, which no consumer has a claim on, is reclaimed as it always was. A replacement the
re-decomposition pointed at that ref is recorded beside them, so it holds the ref until its own work has ended too --
under an umbrella, or under a parent the re-decomposition left work of its own, which settles the ref before it goes
back to that work.
"""
from __future__ import annotations

import unittest
from contextlib import nullcontext
from dataclasses import dataclass
from types import MappingProxyType
from unittest.mock import patch

from orchestrator.git.snapshots.refs import SnapshotOutcome
from orchestrator.workflow.late_split.obligations import LateResourceState
from orchestrator.workflow.stages.decomposition import blocked as _blocked, run as _decomposing, umbrella as _umbrella
from tests.workflow.fixtures import _TEST_SPEC, _agent, _manifest, _PatchedWorkflowMixin
from tests.workflow.stages.decomposition import late_cleanup_support as _support
from tests.workflow.stages.decomposition.late_cleanup_support import OwnerSeed, RecordedDelete, SeededUmbrella

# Where a read of the original can fail: at the lookup itself, or past it, on
# the first attribute a lazy issue fetches itself for.
_AT_LOOKUP = "lookup"

_PAST_LOOKUP = "labels"

_REFUSED = "the original could not be read"

# What the edited umbrella is re-decomposed into: one replacement, which the
# split points at the ref the root's own split still holds.
_REPLACEMENT_MANIFEST = _manifest(
    '{"decision": "split", "umbrella": true, "rationale": "re-planned", '
    '"children": [{"title": "A", "body": "the whole of it, as the edit now asks"}]}'
)

# The same answer for a parent that keeps implementation of its own: the
# replacement runs first, and the parent goes back to its work after it.
_OWN_WORK_MANIFEST = _manifest(
    '{"decision": "split", "umbrella": false, "rationale": "re-planned", '
    '"children": [{"title": "A", "body": "the groundwork, as the edit now asks"}]}'
)

_STALE_BASELINE = "the requirements before the edit"

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
        for shape, original in _UNENDED.items():
            with self.subTest(shape=shape):
                seeded = _replaced(original)

                deleted = self._walk(seeded, original)

                self.assertEqual(deleted.refs, [])
                self.assertEqual(_support.resource_states(seeded.github), {
                    _support.SUPERSEDED_BRANCH: _support.STATE_RECONCILED,
                    _support.SNAPSHOT_REF: _support.STATE_RETAINED,
                })
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

    def _walk(self, seeded: SeededUmbrella, original: _Original) -> RecordedDelete:
        """Run the umbrella's poll, the original read the way `original` says."""
        deleted = RecordedDelete(SnapshotOutcome.DELETED)
        unreadable = patch.object(
            seeded.github,
            "get_issue",
            side_effect=_OriginalUnreadable(seeded.github, original.failing),
        ) if original.failing else nullcontext()
        with deleted.answering(), unreadable:
            _support.walk_owner(self, seeded)
        return deleted


class ProtectedReplacementTest(_PatchedWorkflowMixin, unittest.TestCase):
    """A replacement pointed at the ref keeps it until its own work ends.

    Whichever parent the re-decomposition left: an umbrella resolves once the
    ref goes, and a parent with work of its own goes back to it.
    """

    def test_a_reopened_replacement_keeps_the_ref(self) -> None:
        seeded, replacement = self._redecomposed()
        seeded.github.get_issue(_support.CHILD_NUMBER).closed = True
        # Resolved and put back by a human: the label says `done`, and the
        # issue is live again.
        seeded.github.set_workflow_label(replacement, _support.LABEL_DONE, guarded=False)

        held = self._walk(seeded)
        replacement.closed = True
        released = self._walk(seeded)

        self.assertEqual(held.refs, [])
        self.assertEqual(released.refs, [_support.SNAPSHOT_REF])
        self.assertEqual(
            _support.resource_states(seeded.github)[_support.SNAPSHOT_REF],
            _support.STATE_RECONCILED,
        )
        self.assertTrue(seeded.parent.closed)
        self.assertTrue(any(_RELEASE_MARKER in comment.body for comment in replacement.comments))

    def test_a_parent_with_own_work_settles_first(self) -> None:
        # Its children all resolved, the parent goes back to `ready` -- after
        # which nothing revisits what the split owes the remote. So the ref is
        # settled in front of that flip, and the parent waits on `blocked`
        # while a consumer the ledger records is still live.
        seeded, replacement = self._redecomposed(_OWN_WORK_MANIFEST)
        seeded.github.get_issue(_support.CHILD_NUMBER).closed = True
        seeded.github.set_workflow_label(replacement, _support.LABEL_DONE, guarded=False)

        held = self._walk(seeded, _blocked._handle_blocked)
        waited = seeded.github.workflow_label(seeded.parent)
        replacement.closed = True
        released = self._walk(seeded, _blocked._handle_blocked)

        self.assertEqual((held.refs, waited), ([], _support.LABEL_BLOCKED))
        self.assertEqual(released.refs, [_support.SNAPSHOT_REF])
        self.assertEqual(
            _support.resource_states(seeded.github)[_support.SNAPSHOT_REF],
            _support.STATE_RECONCILED,
        )
        self.assertEqual(seeded.github.workflow_label(seeded.parent), _support.LABEL_READY)
        self.assertTrue(any(_RELEASE_MARKER in comment.body for comment in replacement.comments))

    def _redecomposed(self, answer: str = _REPLACEMENT_MANIFEST):
        """A root's umbrella an edit re-decomposed into one replacement.

        The root sits at depth 0 and still holds its ref for the original,
        which is running when the edit lands. `answer` is the manifest the
        decomposer re-plans it with.
        """
        seeded = _support.split_umbrella(
            LateResourceState.RECONCILED,
            snapshot=LateResourceState.RETAINED,
            child_label=_support.LABEL_READY,
            owner=OwnerSeed(child_closed=False),
        )
        seeded.github.seed_state(_support.PARENT_NUMBER, **{
            **seeded.github.pinned_data(_support.PARENT_NUMBER),
            "late_lineage_depth": 0,
            "user_content_hash": _STALE_BASELINE,
        })
        _support.walk_owner(self, seeded)
        self._run(
            lambda: _decomposing._handle_decomposing(seeded.github, _TEST_SPEC, seeded.parent),
            run_agent=_agent(session_id="replanned", last_message=answer),
        )
        return seeded, seeded.github.created_child_issues[0]

    def _walk(self, seeded: SeededUmbrella, tick=_umbrella._handle_umbrella) -> RecordedDelete:
        """Run the parent's poll, the remote deleting whatever it is asked to."""
        deleted = RecordedDelete(SnapshotOutcome.DELETED)
        with deleted.answering():
            _support.walk_owner(self, seeded, tick)
        return deleted


def _replaced(original: _Original) -> SeededUmbrella:
    """A late split's umbrella whose manifest an edit has replaced.

    It still owes the branch and still holds the ref, and its one
    replacement is finished -- which is the reading that sends the poll to
    the terminal and the settlement in front of it.
    """
    seeded = _support.split_umbrella(
        LateResourceState.PENDING,
        snapshot=LateResourceState.RETAINED,
        child_label=original.label,
        owner=OwnerSeed(child_closed=original.closed),
    )
    seeded.replaced()
    return seeded


if __name__ == "__main__":
    unittest.main()
