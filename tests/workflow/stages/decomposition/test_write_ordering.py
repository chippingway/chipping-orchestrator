# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import unittest

from tests.support.fakes import (
    FakeGitHubClient,
    make_issue,
)
from tests.workflow.fixtures import (
    LABEL_DECOMPOSING,
    LABEL_READY,
    _agent,
    _manifest,
)
from tests.workflow.stages.decomposition import child_baseline_support as _baseline_support
from tests.workflow.stages.decomposition.decomposing_test_support import (
    _ChildSeedOrderRecorder,
    _DecomposingWorkflowMixin,
    _ExpectedChildCountRecorder,
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
CHILD_BASELINE_ORDER_ISSUE_NUMBER = 84
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
    '{"decision": "split", "children": ['
    '{"title": "A", "body": "a", "depends_on": []},{"title": "B", "body": "b", "depends_on": []}]}'
)
ONE_SLICE_MANIFEST = _manifest('{"decision": "split", "children": [{"title": "A", "body": "a", "depends_on": []}]}')
READ_ONLY_FRAGMENT = "read-only"
IMPLEMENTED_MESSAGE = "implemented"


class DecompositionWriteOrderingTest(
    unittest.TestCase,
    _DecomposingWorkflowMixin,
):
    def test_split_persists_expected_count_first(self) -> None:
        # `expected_children_count` MUST be on the parent before any
        # child is created on GitHub. Otherwise a SIGKILL after the
        # first child creation leaves `children=[#x]` without an
        # `expected_children_count`, and the recovery (legacy branch)
        # incorrectly finalizes to `blocked`.
        gh = FakeGitHubClient()
        issue = make_issue(
            EXPECTED_COUNT_ORDER_ISSUE_NUMBER,
            label=LABEL_DECOMPOSING,
        )
        gh.add_issue(issue)
        manifest = SPLIT_MANIFEST

        recorder = _ExpectedChildCountRecorder(gh, issue.number)
        gh.create_child_issue = recorder

        self._run_decomposing(
            gh,
            issue,
            run_agent=_agent(session_id=DECOMPOSER_SESSION, last_message=manifest),
        )

        self.assertEqual(recorder.expected_counts[0], 2)
        self.assertEqual(
            gh.pinned_data(EXPECTED_COUNT_ORDER_ISSUE_NUMBER).get("expected_children_count"),
            2,
        )

    def test_parent_records_child_before_child_state(self) -> None:
        # Order matters: parent state records the new child BEFORE the
        # child's pinned state is seeded. Otherwise a SIGKILL between
        # `create_child_issue` returning and the parent write leaves
        # an orphan child (parent doesn't know about it), and the next
        # tick re-spawns the decomposer to create a duplicate.
        gh = FakeGitHubClient()
        issue = make_issue(CHILD_STATE_ORDER_ISSUE_NUMBER, label=LABEL_DECOMPOSING)
        gh.add_issue(issue)
        manifest = ONE_SLICE_MANIFEST

        recorder = _ChildSeedOrderRecorder(gh, issue.number)
        gh.write_pinned_state = recorder

        self._run_decomposing(
            gh,
            issue,
            run_agent=_agent(session_id=DECOMPOSER_SESSION, last_message=manifest),
        )

        # Exactly one child was created and its pinned state was seeded
        # AFTER the parent recorded the child number.
        self.assertEqual(len(recorder.snapshots), 1)
        self.assertEqual(
            len(recorder.snapshots[0]),
            1,
            "parent must record the child number before the child's pinned state is seeded",
        )

    def test_a_child_is_baselined_before_release(self) -> None:
        # The child's drift baseline lands in its seed -- its first pinned
        # write, behind the parent's record of it -- so the split releases a
        # child already baselined at what it was created saying, rather than
        # leaving a later poll to take whatever it says by then.
        gh = FakeGitHubClient()
        issue = make_issue(CHILD_BASELINE_ORDER_ISSUE_NUMBER, label=LABEL_DECOMPOSING)
        gh.add_issue(issue)
        seeds = _ChildSeedOrderRecorder(gh, issue.number)
        gh.write_pinned_state = seeds
        releases = _ReleaseRecorder(gh)
        gh.set_workflow_label = releases

        self._run_decomposing(
            gh,
            issue,
            run_agent=_agent(session_id=DECOMPOSER_SESSION, last_message=ONE_SLICE_MANIFEST),
        )

        baseline = seeds.baselines[0]
        self.assertEqual(
            baseline, _baseline_support.reading(gh.created_child_issues[0]), "the seed records the baseline",
        )
        self.assertEqual(releases.baselines, [baseline], "and it is on the child at its release")


class _ReleaseRecorder:
    """A relabel that notes, as each issue goes `ready`, the drift baseline its record carries by then."""

    def __init__(self, gh: FakeGitHubClient) -> None:
        self.baselines: list[str | None] = []
        self._gh = gh
        self._relabel = gh.set_workflow_label

    def __call__(self, target_issue, label, **options):
        if label == LABEL_READY:
            pinned = self._gh.pinned_data(target_issue.number)
            self.baselines.append(pinned.get(_baseline_support.KEY_BASELINE))
        return self._relabel(target_issue, label, **options)
