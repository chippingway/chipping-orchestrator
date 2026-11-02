# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Whether a whole-state write landed, and whether a teardown may run, each answered at the effect.

The writer marks only a state it sent as synced with what the comment now
carries, raises over a record admission refuses, and answers its other refusals
by returning. A state staged equal to what it last synced with already carries
that mark, so `written` takes its answer from the attempt in hand, and puts the
mark back wherever that attempt did not set it. Its strict sibling,
`strictly_written`, lands a state only over the very comment it last synced
with, and withholds it wherever that comment moved or the edit did not land --
and, handed what else the write rests on, only while that still stands and the
comment, read once more behind it, is still that comment reading as it was.
"""
from __future__ import annotations

import json
import unittest
from types import MappingProxyType

from orchestrator.github import pinned_refusal as _pinned_refusal
from orchestrator.workflow.engine import record_admission as _record_admission
from tests.support.fakes import FakeGitHubClient, make_issue

_ISSUE = 77

_RUNS = "agent_runs_used"

_RECORDED = MappingProxyType({_RUNS: 3})

_ANOTHER_VERSION = 2

# A count the caller stages, and a field another writer lays on the comment meanwhile.
_CHARGED = 4
_NOTE = "operator_note"

_EDITED = MappingProxyType({**_RECORDED, "schema_version": _ANOTHER_VERSION})

# (case, the record edited into another version, its read failing, whether the teardown runs)
_TEARDOWN_CASES = (
    ("current", False, False, True),
    ("refused", True, False, False),
    ("unreadable", False, True, False),
)


class WrittenTest(unittest.TestCase):
    """One record, read current, and written back unchanged."""

    def setUp(self) -> None:
        self.github = FakeGitHubClient([make_issue(_ISSUE)])
        self.issue = self.github.get_issue(_ISSUE)
        self.github.seed_state(self.issue, **_RECORDED)
        self.state = self.github.read_pinned_state(self.issue)
        self.read = self.state.synced

    def test_an_unchanged_state_that_lands_is_written(self) -> None:
        self.assertTrue(_record_admission.written(self.github, self.issue, self.state))
        self.assertEqual(self.github.write_state_calls, 1)

    def test_a_quiet_refusal_is_not_written(self) -> None:
        # A withheld state is answered by returning, and staged equal to what
        # it last synced with it already carries the writer's mark: the
        # answer is still no, and the mark it read with is kept.
        self.state.withheld = True

        self.assertFalse(_record_admission.written(self.github, self.issue, self.state))
        self.assertEqual(self.state.synced, self.read)
        self.assertEqual(self.github.write_state_calls, 0)

    def test_a_refused_record_raises(self) -> None:
        # A human edits the record into a version admission refuses after it
        # was read: the write raises, with nothing written and the mark kept.
        self.github.seed_state(self.issue, raw=True, schema_version=_ANOTHER_VERSION, **_RECORDED)

        with self.assertRaises(_pinned_refusal.RecordRefused):
            _record_admission.written(self.github, self.issue, self.state)
        self.assertEqual(self.state.synced, self.read)
        self.assertEqual(self.github.write_state_calls, 0)


class StrictlyWrittenTest(unittest.TestCase):
    """One record, read current, a change staged on it, and written only over the comment it was read from."""

    def setUp(self) -> None:
        self.github = FakeGitHubClient([make_issue(_ISSUE)])
        self.issue = self.github.get_issue(_ISSUE)
        self.github.seed_state(self.issue, **_RECORDED)
        self.state = self.github.read_pinned_state(self.issue)
        self.state.set(_RUNS, _CHARGED)

    def test_a_state_over_its_reading_lands(self) -> None:
        self.assertTrue(_record_admission.strictly_written(self.github, self.issue, self.state))

        landed = self.github.read_pinned_state(self.issue)
        self.assertEqual(landed.get(_RUNS), _CHARGED)
        self.assertTrue(landed.reads_as(json.loads(self.state.synced)), "it syncs with what landed")
        self.assertFalse(self.state.withheld)

    def test_a_moved_comment_takes_nothing(self) -> None:
        # Another writer lays a field on the comment after the read: nothing
        # is sent over it, its field is kept, and the caller is withheld.
        moved = self.github.read_pinned_state(self.issue)
        moved.set(_NOTE, "kept")
        self.github.write_pinned_state(self.issue, moved)

        self.assertFalse(_record_admission.strictly_written(self.github, self.issue, self.state))

        kept = self.github.read_pinned_state(self.issue)
        self.assertEqual(kept.get(_NOTE), "kept")
        self.assertEqual(kept.get(_RUNS), _RECORDED[_RUNS])
        self.assertTrue(self.state.withheld)

    def test_what_lands_behind_still_holds_the_edit(self) -> None:
        # The edit asks `still`, then the comment once more, right before it
        # leaves: a `still` answering no, or the comment replaced by one
        # carrying the same record while `still` was out, sends nothing.
        for name, still in (("still answers no", bool), ("the comment replaced", self._replaces)):
            with self.subTest(name):
                self.setUp()

                landed = _record_admission.strictly_written(self.github, self.issue, self.state, still=still)

                self.assertFalse(landed)
                self.assertEqual(self.github.pinned_data(_ISSUE)[_RUNS], _RECORDED[_RUNS])
                self.assertTrue(self.state.withheld)

    def test_a_state_never_synced_is_withheld(self) -> None:
        self.state.synced = None

        self.assertFalse(_record_admission.strictly_written(self.github, self.issue, self.state))
        self.assertTrue(self.state.withheld)

    def _replaces(self) -> bool:
        """A human posts the record, as it reads, as a new pinned comment in place of the one read."""
        self.github.seed_state(self.issue, **self.github.pinned_data(_ISSUE))
        return True


class TeardownAdmittedTest(unittest.TestCase):
    """A scratch checkout's teardown runs only over a record admission takes, read at the teardown."""

    def test_only_an_admitted_record_tears_down(self) -> None:
        for case, refused, unreadable, runs in _TEARDOWN_CASES:
            with self.subTest(case=case):
                github = _seeded(refused=refused, unreadable=unreadable)

                self.assertEqual(_record_admission.teardown_admitted(github, github.get_issue(_ISSUE)), runs)


def _seeded(*, refused: bool, unreadable: bool) -> FakeGitHubClient:
    """One issue's record, edited into another version where `refused`, and failing to read where `unreadable`."""
    github = FakeGitHubClient([make_issue(_ISSUE)])
    github.seed_state(_ISSUE, raw=refused, **(_EDITED if refused else _RECORDED))
    if unreadable:
        github.pinned_failures.unreadable.add(_ISSUE)
    return github


if __name__ == "__main__":
    unittest.main()
