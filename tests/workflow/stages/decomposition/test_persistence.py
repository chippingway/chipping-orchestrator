# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import unittest

from tests.support.fakes import (
    FakeGitHubClient,
    make_issue,
)
from tests.support.writer_claims import claimed_on_creation
from tests.workflow.fixtures import (
    LABEL_DECOMPOSING,
    _agent,
    _manifest,
)
from tests.workflow.stages.decomposition.decomposing_test_support import (
    _ChildCreationSnapshotRecorder,
    _DecomposingWorkflowMixin,
)

KEY_DECOMPOSER_AGENT = "decomposer_agent"
KEY_DECOMPOSER_SESSION_ID = "decomposer_session_id"
KEY_CHILDREN = "children"
KEY_UMBRELLA = "umbrella"
CLEANUP_DECOMPOSE_WORKTREE = "_cleanup_decompose_worktree"
RUN_AGENT = "run_agent"
CONFIG_DECOMPOSE = "DECOMPOSE"
DECOMPOSER_SESSION = "dec-sess"
DEV_SESSION = "dev-sess"
TRUSTED_AUTHOR = "alice"
CREATED_AT = "2026-05-03T00:00:00+00:00"
PICKUP_ISSUE_NUMBER = 10
SINGLE_DECISION_ISSUE_NUMBER = 11
CONTEXT_HANDOFF_ISSUE_NUMBER = 73
SPLIT_DECISION_ISSUE_NUMBER = 12
UMBRELLA_SPLIT_ISSUE_NUMBER = 50
NON_UMBRELLA_SPLIT_ISSUE_NUMBER = 51
DEPENDENCY_SPLIT_ISSUE_NUMBER = 13
COMMITS_PARK_ISSUE_NUMBER = 40
DIRTY_PARK_ISSUE_NUMBER = 41
MALFORMED_MANIFEST_ISSUE_NUMBER = 14
QUESTION_PARK_ISSUE_NUMBER = 15
SILENT_FAILURE_ISSUE_NUMBER = 115
RESUME_ISSUE_NUMBER = 16
FILTERED_RESUME_ISSUE_NUMBER = 17
RETRY_CAP_ISSUE_NUMBER = 18
HUMAN_REPLY_COMMENT_ID = 1100
OUTSIDER_REPLY_COMMENT_ID = 1101
PRIOR_ACTION_COMMENT_ID = 900
DISABLED_PICKUP_ISSUE_NUMBER = 19
DISABLED_LABELED_ISSUE_NUMBER = 20
DISABLED_RATCHET_ISSUE_NUMBER = 21
RATCHET_FIRST_COMMENT_ID = 950
RATCHET_LATEST_COMMENT_ID = 960
DISABLED_MONOTONIC_ISSUE_NUMBER = 22
OLDER_COMMENT_ID = 500
PRESERVED_HIGH_WATERMARK = 10000
HALF_COMPLETE_DISABLED_PARENT_NUMBER = 50
RECOVERY_CHILD_NUMBERS = (101, 102)
PERSISTENCE_ISSUE_NUMBER = 80
SEED_CONTENTION_ISSUE_NUMBER = 81
KEY_AWAITING_HUMAN = "awaiting_human"
SEED_PARK = "could not seed its pinned state"
COMPLETE_RECOVERY_PARENT_NUMBER = 50
AWAITING_RECOVERY_PARENT_NUMBER = 51
AWAITING_RECOVERY_CHILD_NUMBER = 201
PARTIAL_RECOVERY_PARENT_NUMBER = 52
ORPHAN_RECOVERY_PARENT_NUMBER = 53
ORPHAN_REPAIR_PARENT_NUMBER = 60
HEALTHY_CHILD_NUMBER = 601
ORPHAN_CHILD_NUMBER = 602
STALE_PARK_COMMENT_ID = 999
EXPECTED_COUNT_ORDER_ISSUE_NUMBER = 82
CHILD_STATE_ORDER_ISSUE_NUMBER = 83
WORKTREE_ISSUE_NUMBER = 70
DIRTY_WORKTREE_ISSUE_NUMBER = 71
AWAITING_WORKTREE_ISSUE_NUMBER = 73
NON_STRING_RATIONALE_ISSUE_NUMBER = 72
FRESH_USAGE_ISSUE_NUMBER = 620
RESUMED_USAGE_ISSUE_NUMBER = 621
NO_COMMENT_USAGE_ISSUE_NUMBER = 622
INTERRUPTED_USAGE_ISSUE_NUMBER = 623
DIRTY_INTERRUPTED_USAGE_ISSUE_NUMBER = 624

SINGLE_MANIFEST_PAYLOAD = '{"decision": "single", "rationale": "fits"}'
SPLIT_MANIFEST = _manifest(
    '{"decision": "split", "children": [{"title": "A", "body": "a"},{"title": "B", "body": "b"}]}'
)
READ_ONLY_FRAGMENT = "read-only"
IMPLEMENTED_MESSAGE = "implemented"


class DecompositionChildPersistenceTest(
    unittest.TestCase,
    _DecomposingWorkflowMixin,
):
    def test_persists_children_incrementally(self) -> None:
        # Each successful child creation must flush the parent's
        # `children` list before the next iteration starts. Without this,
        # a process kill (no exception) between iterations leaves the
        # parent without a `children` record, the next tick re-spawns the
        # decomposer, and duplicate child issues are created. We probe
        # the contract by snapshotting the parent's persisted `children`
        # list at the moment each child creation begins.
        gh = FakeGitHubClient()
        issue = make_issue(PERSISTENCE_ISSUE_NUMBER, label=LABEL_DECOMPOSING)
        gh.add_issue(issue)
        manifest = _manifest(
            '{"decision": "split", "children": ['
            '{"title": "A", "body": "a"},'
            '{"title": "B", "body": "b"},'
            '{"title": "C", "body": "c"}'
            "]}"
        )

        recorder = _ChildCreationSnapshotRecorder(gh, issue.number)
        gh.create_child_issue = recorder

        self._run_decomposing(
            gh,
            issue,
            run_agent=_agent(session_id=DECOMPOSER_SESSION, last_message=manifest),
        )

        # iter 0: no children yet. iter 1: child[0] already persisted.
        # iter 2: child[0] + child[1] already persisted.
        self.assertEqual(len(recorder.snapshots), 3)
        self.assertEqual(recorder.snapshots[0], [])
        self.assertEqual(len(recorder.snapshots[1]), 1)
        self.assertEqual(len(recorder.snapshots[2]), 2)
        self.assertEqual(
            len(gh.pinned_data(PERSISTENCE_ISSUE_NUMBER).get(KEY_CHILDREN) or []),
            3,
        )

    def test_a_child_reached_first_parks_unseeded(self) -> None:
        # Another poller on this host dispatches the first child the moment it
        # exists, so its record is that poller's to write when this split goes
        # to seed it: the child stays recorded and unwritten, and the split
        # parks rather than creating the next one past it.
        gh = FakeGitHubClient()
        issue = make_issue(SEED_CONTENTION_ISSUE_NUMBER, label=LABEL_DECOMPOSING)
        gh.add_issue(issue)

        with claimed_on_creation(gh):
            self._run_decomposing(
                gh,
                issue,
                run_agent=_agent(session_id=DECOMPOSER_SESSION, last_message=SPLIT_MANIFEST),
            )

        created = [child.number for child in gh.created_child_issues]
        parent = gh.pinned_data(SEED_CONTENTION_ISSUE_NUMBER)
        self.assertEqual(len(created), 1, "no child is created past the one it could not seed")
        self.assertEqual(parent.get(KEY_CHILDREN), created)
        self.assertTrue(parent.get(KEY_AWAITING_HUMAN))
        self.assertIn(SEED_PARK, gh.posted_comments[-1][1])
        self.assertEqual(gh.pinned_data(created[0]), {})
