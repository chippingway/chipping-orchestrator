# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Whether a whole-state write landed, and whether a teardown may run, each answered at the effect.

The writer marks only a state it sent as synced with what the comment now
carries, raises over a record admission refuses, and answers its other refusals
by returning. A state staged equal to what it last synced with already carries
that mark, so `written` takes its answer from the attempt in hand, and puts the
mark back wherever that attempt did not set it.
"""
from __future__ import annotations

import unittest
from types import MappingProxyType

from orchestrator.github import pinned_refusal as _pinned_refusal
from orchestrator.workflow.engine import record_admission as _record_admission
from tests.support.fakes import FakeGitHubClient, make_issue

_ISSUE = 77

_RECORDED = MappingProxyType({"agent_runs_used": 3})

_ANOTHER_VERSION = 2

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
