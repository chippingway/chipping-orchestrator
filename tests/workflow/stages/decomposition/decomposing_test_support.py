# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

from orchestrator.workflow.stages.decomposition import run as _decomposing, split_seeds as _split_seeds
from tests.support.fakes import (
    FakeGitHubClient,
)
from tests.support.writer_claims import held_elsewhere
from tests.workflow.fixtures import (
    _TEST_SPEC,
    _manifest,
    _PatchedWorkflowMixin,
    _reported,
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
IMPLEMENTED_MESSAGE = _reported()


class _DecomposingWorkflowMixin(_PatchedWorkflowMixin):
    def _run_decomposing(self, gh, issue, **run_options):
        return self._run(
            lambda: _decomposing._handle_decomposing(gh, _TEST_SPEC, issue),
            **run_options,
        )

    def _held_by_another_poller(self, gh, *issue_numbers: int):
        """These issues' writer claims, held by another poller on this host for the block."""
        return held_elsewhere(gh.repo_id, *issue_numbers)


class _ChildCreationSnapshotRecorder:
    def __init__(self, gh: FakeGitHubClient, parent_number: int) -> None:
        self.snapshots: list[list] = []
        self._gh = gh
        self._parent_number = parent_number
        self._create_child = gh.create_child_issue

    def __call__(self, **kwargs):
        recorded = self._gh.pinned_data(self._parent_number).get(KEY_CHILDREN)
        self.snapshots.append(list(recorded or []))
        return self._create_child(**kwargs)


class _ExpectedChildCountRecorder:
    def __init__(self, gh: FakeGitHubClient, parent_number: int) -> None:
        self.expected_counts: list[int | None] = []
        self._gh = gh
        self._parent_number = parent_number
        self._create_child = gh.create_child_issue

    def __call__(self, **kwargs):
        parent_state = self._gh.pinned_data(self._parent_number)
        self.expected_counts.append(parent_state.get("expected_children_count"))
        return self._create_child(**kwargs)


class _ChildSeedOrderRecorder:
    def __init__(self, gh: FakeGitHubClient, parent_number: int) -> None:
        self.snapshots: list[list] = []
        self._gh = gh
        self._parent_number = parent_number
        self._write_state = gh.write_pinned_state

    def __call__(self, target_issue, state):
        if target_issue.number != self._parent_number:
            parent_state = self._gh.pinned_data(self._parent_number)
            self.snapshots.append(list(parent_state.get(KEY_CHILDREN) or []))
        return self._write_state(target_issue, state)


class _ReachedFirstByAnotherPoller:
    """A child create whose child another poller on this host dispatches before the split seeds it.

    That poller's dispatcher finds the split's receipt and no seed, so it
    holds the child -- parked on a pinned comment of its own -- under the
    child's claim, and lets the claim go before the split asks for it.
    """

    def __init__(self, gh: FakeGitHubClient) -> None:
        self._gh = gh
        self._create_child = gh.create_child_issue

    def __call__(self, **kwargs):
        child = self._create_child(**kwargs)
        with held_elsewhere(self._gh.repo_id, child.number):
            _split_seeds.holds_unseeded(
                self._gh, child, self._gh.workflow_label(child), self._gh.read_pinned_state(child),
            )
        return child
