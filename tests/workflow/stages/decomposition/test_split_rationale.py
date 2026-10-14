# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The rationale an ordinary split records on its parent: when it lands, what it keeps, and what outlives a failure."""
from __future__ import annotations

import json
import unittest
from types import MappingProxyType
from unittest.mock import patch

from orchestrator.github.pinned_state import PinnedState, pinned_state_body, pinned_state_from_comment
from orchestrator.workflow.stages.decomposition import state as _state
from orchestrator.workflow.stages.decomposition.late_result_models import MAX_RATIONALE, RATIONALE_TRUNCATION_MARKER
from tests.support.fakes import FakeComment, FakeGitHubClient, FakeIssue, make_issue
from tests.workflow.fixtures import (
    KEY_AWAITING_HUMAN,
    KEY_PARENT_NUMBER,
    LABEL_BLOCKED,
    LABEL_DECOMPOSING,
    _agent,
    _manifest,
)
from tests.workflow.stages.decomposition.decomposing_test_support import _DecomposingWorkflowMixin

KEY_SPLIT_RATIONALE = "split_rationale"
KEY_SPLIT_ATTEMPT = "split_attempt"
KEY_EXPECTED_CHILDREN_COUNT = "expected_children_count"
KEY_UMBRELLA = "umbrella"
KEY_DEP_GRAPH = "dep_graph"
KEY_CHILDREN = "children"
RUN_AGENT = "run_agent"
DECOMPOSER_SESSION = "dec-sess"
PARENT_NUMBER = 90
_STATE_COMMENT_ID = 900

# The manifest field the rationale arrives in.
_FIELD = "rationale"

# Two slices, the second needing the first, so the checkpoint carries a graph.
_SLICES = (
    {"title": "A", "body": "a", "depends_on": []},
    {"title": "B", "body": "b", "depends_on": [0]},
)

# What the parent says it keeps for its own pass, carrying everything the
# pinned comment's rendering has to escape: its own terminator, quotes, a
# backslash, a fence, and a character JSON spells as a surrogate pair.
_RATIONALE = 'The parent keeps the "docs" pass --> under C:\N{REVERSE SOLIDUS}path\n```fence``` \N{GRINNING FACE}'

# What an earlier split of the same parent recorded, which no later split may be read back with.
_EARLIER = "an earlier split kept the release notes"

_OVERLONG = "r" * (MAX_RATIONALE + 10)

# The markers an ordinary split writes in one write ahead of its first child.
_CHECKPOINT = (KEY_EXPECTED_CHILDREN_COUNT, KEY_UMBRELLA, KEY_SPLIT_ATTEMPT, KEY_DEP_GRAPH, KEY_SPLIT_RATIONALE)


def _cut(rationale: str) -> str:
    """What a rationale past the bound is recorded as: a prefix and the marker."""
    prefix = rationale[:MAX_RATIONALE - len(RATIONALE_TRUNCATION_MARKER)]
    return f"{prefix}{RATIONALE_TRUNCATION_MARKER}"


# What each manifest's rationale field is recorded as, over the earlier split's.
_RECORDED = MappingProxyType({
    "absent": ({}, None),
    "null": ({_FIELD: None}, None),
    "empty": ({_FIELD: ""}, None),
    "blank": ({_FIELD: " \n\t "}, None),
    "number": ({_FIELD: 42}, None),
    "boolean": ({_FIELD: True}, None),
    "list": ({_FIELD: [_RATIONALE]}, None),
    "object": ({_FIELD: {"why": _RATIONALE}}, None),
    "padded": ({_FIELD: f"  {_RATIONALE}\n"}, _RATIONALE),
    "overlong": ({_FIELD: _OVERLONG}, _cut(_OVERLONG)),
})


class _ParentAtEachCreate:
    """Every child create, seen with the parent's pinned record as it stood when the create was asked for."""

    def __init__(self, gh: FakeGitHubClient) -> None:
        self.records: list[dict] = []
        self._gh = gh
        self._create_child = gh.create_child_issue

    def __call__(self, **kwargs):
        self.records.append(self._gh.pinned_data(PARENT_NUMBER))
        return self._create_child(**kwargs)


class _DiesSeedingAChild:
    """A process that dies at the first write to a child's pinned comment, after the parent recorded it."""

    def __init__(self, gh: FakeGitHubClient) -> None:
        self._write = gh.write_pinned_state

    def __call__(self, issue, state):
        if issue.number != PARENT_NUMBER:
            raise KeyboardInterrupt("seed")
        return self._write(issue, state)


class _SplitRationaleCase(unittest.TestCase, _DecomposingWorkflowMixin):
    """A decomposing tick whose decomposer answers with a split."""

    def _parent(self) -> tuple[FakeGitHubClient, FakeIssue]:
        """A `decomposing` parent a drift reset left with no manifest, still holding an earlier split's rationale."""
        gh = FakeGitHubClient()
        issue = make_issue(PARENT_NUMBER, label=LABEL_DECOMPOSING)
        gh.add_issue(issue)
        gh.seed_state(
            issue,
            children=[],
            dep_graph={},
            expected_children_count=None,
            split_attempt=None,
            umbrella=None,
            split_rationale=_EARLIER,
        )
        return gh, issue

    def _split(self, gh: FakeGitHubClient, issue: FakeIssue, slices: tuple[dict, ...], **fields):
        """Run the tick on a non-umbrella split of these slices, with these fields beside its children."""
        payload = {"decision": "split", "umbrella": False, "children": list(slices)}
        payload.update(fields)
        answer = _agent(session_id=DECOMPOSER_SESSION, last_message=_manifest(json.dumps(payload)))
        return self._run_decomposing(gh, issue, run_agent=answer)


class SplitRationaleCheckpointTest(_SplitRationaleCase):
    """The rationale is part of the checkpoint a split writes before its first child."""

    def test_the_rationale_lands_before_any_child(self) -> None:
        gh, issue = self._parent()
        recorder = _ParentAtEachCreate(gh)
        gh.create_child_issue = recorder

        self._split(gh, issue, _SLICES, rationale=_RATIONALE)

        final = gh.pinned_data(PARENT_NUMBER)
        checkpoint = {key: recorder.records[0].get(key) for key in _CHECKPOINT}
        self.assertEqual(checkpoint, {
            KEY_EXPECTED_CHILDREN_COUNT: len(_SLICES),
            KEY_UMBRELLA: False,
            KEY_SPLIT_ATTEMPT: final[KEY_SPLIT_ATTEMPT],
            KEY_DEP_GRAPH: {"1": [0]},
            KEY_SPLIT_RATIONALE: _RATIONALE,
        }, "written with the split's other markers before the first create")
        self.assertEqual(len(recorder.records), len(_SLICES))
        self.assertEqual(
            {record.get(KEY_SPLIT_RATIONALE) for record in recorder.records}, {_RATIONALE},
            "no child record write drops it",
        )
        self.assertIn((PARENT_NUMBER, LABEL_BLOCKED), gh.label_history)
        self.assertEqual(final[KEY_SPLIT_RATIONALE], _RATIONALE)
        self.assertEqual(self._read_back(final), _RATIONALE, "read back through the pinned comment")

    def test_each_split_writes_its_own_rationale(self) -> None:
        # A value nobody can read as an account clears the earlier one and
        # still splits; text replaces it, stripped and cut to the bound.
        for case, (fields, recorded) in _RECORDED.items():
            with self.subTest(rationale=case):
                self._assert_split_records(fields, recorded)

    def _read_back(self, record: dict) -> str | None:
        """The rationale a later reader takes off the pinned comment this record is written as."""
        pinned = pinned_state_from_comment(
            FakeComment(id=_STATE_COMMENT_ID, body=pinned_state_body(record)),
            trusted_login=None,
            issue_number=PARENT_NUMBER,
        )
        return _state._recorded_split_rationale(pinned)

    def _assert_split_records(self, fields: dict, recorded: str | None) -> None:
        gh, issue = self._parent()

        self._split(gh, issue, _SLICES, **fields)

        parent = gh.read_pinned_state(issue)
        self.assertEqual(len(gh.created_child_issues), len(_SLICES), "the split is not refused")
        self.assertIn((PARENT_NUMBER, LABEL_BLOCKED), gh.label_history)
        self.assertFalse(parent.get(KEY_AWAITING_HUMAN))
        self.assertTrue(parent.carries(KEY_SPLIT_RATIONALE))
        self.assertEqual(parent.get(KEY_SPLIT_RATIONALE), recorded)
        self.assertEqual(_state._recorded_split_rationale(parent), recorded)


class SplitRationaleRetentionTest(_SplitRationaleCase):
    """A split stopped short of its finalize keeps its rationale, with no decomposer run to recover it from."""

    def test_a_refused_create_keeps_the_rationale(self) -> None:
        gh, issue = self._parent()
        refused = patch.object(gh, "create_child_issue", side_effect=RuntimeError("github refused the create"))

        with refused, self.assertLogs("orchestrator.workflow"):
            self._split(gh, issue, _SLICES, rationale=_RATIONALE)

        parent = gh.pinned_data(PARENT_NUMBER)
        self.assertTrue(parent.get(KEY_AWAITING_HUMAN), "the refused create parks the parent")
        self.assertEqual(gh.created_child_issues, [])
        self.assertEqual(parent.get(KEY_SPLIT_RATIONALE), _RATIONALE)

    def test_an_interrupted_split_keeps_it(self) -> None:
        # Killed between recording its one child and seeding it; the next
        # tick's recovery finalizes from the record, rationale and all.
        gh, issue = self._parent()

        with patch.object(gh, "write_pinned_state", _DiesSeedingAChild(gh)), self.assertRaises(KeyboardInterrupt):
            self._split(gh, issue, _SLICES[:1], rationale=_RATIONALE)

        created = [child.number for child in gh.created_child_issues]
        interrupted = gh.pinned_data(PARENT_NUMBER)
        self.assertEqual(interrupted.get(KEY_CHILDREN), created)
        self.assertEqual(interrupted.get(KEY_SPLIT_RATIONALE), _RATIONALE)

        self._run_decomposing(gh, issue, run_agent=_agent())[RUN_AGENT].assert_not_called()

        self.assertEqual(gh.label_history, [(PARENT_NUMBER, LABEL_BLOCKED)], "the recovery finalizes")
        self.assertEqual(gh.pinned_data(created[0]).get(KEY_PARENT_NUMBER), PARENT_NUMBER)
        self.assertEqual(gh.pinned_data(PARENT_NUMBER).get(KEY_SPLIT_RATIONALE), _RATIONALE)


class RecordedSplitRationaleTest(unittest.TestCase):
    """The accessor later consumers read the record through, tolerant of records this binary did not write."""

    def test_an_unusable_record_reads_as_none(self) -> None:
        for recorded in ({}, {KEY_SPLIT_RATIONALE: None}, {KEY_SPLIT_RATIONALE: 7}, {KEY_SPLIT_RATIONALE: ["why"]}):
            with self.subTest(recorded=recorded):
                self.assertIsNone(_state._recorded_split_rationale(PinnedState(state_data=recorded)))

    def test_text_reads_back_as_a_split_writes_it(self) -> None:
        # A hand edit that padded the text or ran it past the bound reads
        # back as the split that wrote it would have recorded it.
        for case in ("padded", "overlong"):
            fields, read = _RECORDED[case]
            with self.subTest(recorded=case):
                state = PinnedState(state_data={KEY_SPLIT_RATIONALE: fields[_FIELD]})
                self.assertEqual(_state._recorded_split_rationale(state), read)


if __name__ == "__main__":
    unittest.main()
