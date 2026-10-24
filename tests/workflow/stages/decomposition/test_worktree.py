# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import unittest
from unittest.mock import patch

from orchestrator import config
from orchestrator.workflow.engine import issue_processing as _issue_processing
from tests.support.fakes import (
    FakeGitHubClient,
    make_issue,
)
from tests.workflow.fixtures import (
    _TEST_SPEC,
    BACKEND_CLAUDE,
    KEY_AWAITING_HUMAN,
    LABEL_DECOMPOSING,
    LABEL_READY,
    _agent,
    _manifest,
    _reported,
)
from tests.workflow.stages.decomposition.decomposing_test_support import (
    _DecomposingWorkflowMixin,
)
from tests.workflow.stages.decomposition.decomposition_test_support import _comment_with_marker

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
REFUSED_SPLIT_ISSUE_NUMBER = 625
REFUSED_HANDOFF_ISSUE_NUMBER = 626
UNREADABLE_HANDOFF_ISSUE_NUMBER = 627
ANOTHER_VERSION = 2

SINGLE_MANIFEST_PAYLOAD = '{"decision": "single", "rationale": "fits"}'
SPLIT_MANIFEST = _manifest(
    '{"decision": "split", "children": ['
    '{"title": "A", "body": "a", "depends_on": []},{"title": "B", "body": "b", "depends_on": []}]}'
)
READ_ONLY_FRAGMENT = "read-only"
IMPLEMENTED_MESSAGE = "implemented"


class DecompositionWorktreeTest(
    unittest.TestCase,
    _DecomposingWorkflowMixin,
):
    def test_uses_separate_implementer_worktree(self) -> None:
        # The decomposer must NOT taint the implementer's per-issue branch.
        # If it shared `_ensure_worktree`, a `split` decision would leave
        # the local `orchestrator/chippingway__chipping-orchestrator/issue-<n>` branch anchored at the
        # origin/main snapshot the decomposer saw, and the parent's
        # eventual implementer (after children merged to main) would
        # commit on a stale base.
        gh = FakeGitHubClient()
        issue = make_issue(WORKTREE_ISSUE_NUMBER, label=LABEL_DECOMPOSING)
        gh.add_issue(issue)
        manifest = _manifest(SINGLE_MANIFEST_PAYLOAD)

        mocks = self._run_decomposing(
            gh,
            issue,
            run_agent=_agent(session_id=DECOMPOSER_SESSION, last_message=manifest),
        )

        mocks["_ensure_decompose_worktree"].assert_called_with(
            _TEST_SPEC,
            WORKTREE_ISSUE_NUMBER,
        )
        mocks["_ensure_worktree"].assert_not_called()
        # Cleanup runs at function exit so the next consumer of issue 70
        # (here _handle_ready -> _handle_implementing on the next tick)
        # starts from a fresh checkout.
        mocks[CLEANUP_DECOMPOSE_WORKTREE].assert_called_with(
            _TEST_SPEC,
            WORKTREE_ISSUE_NUMBER,
        )

    def test_decompose_skips_cleanup_on_dirty_park(self) -> None:
        # Operator inspection requires the decomposer's worktree to
        # outlive the dirty/commits park.
        gh = FakeGitHubClient()
        issue = make_issue(DIRTY_WORKTREE_ISSUE_NUMBER, label=LABEL_DECOMPOSING)
        gh.add_issue(issue)
        manifest = _manifest(SINGLE_MANIFEST_PAYLOAD)

        mocks = self._run_decomposing(
            gh,
            issue,
            run_agent=_agent(session_id=DECOMPOSER_SESSION, last_message=manifest),
            has_new_commits=True,
        )

        self.assertTrue(gh.pinned_data(DIRTY_WORKTREE_ISSUE_NUMBER).get(KEY_AWAITING_HUMAN))
        mocks[CLEANUP_DECOMPOSE_WORKTREE].assert_not_called()

    def test_awaiting_human_skips_cleanup(self) -> None:
        # On the tick AFTER a dirty/commits park, awaiting_human is True
        # and no human reply has arrived yet. The handler must not clean
        # up the decomposer worktree -- the HITL message asks the operator
        # to inspect and reset it, and a subsequent-tick cleanup would
        # silently delete that state out from under them.
        gh = FakeGitHubClient()
        issue = make_issue(AWAITING_WORKTREE_ISSUE_NUMBER, label=LABEL_DECOMPOSING)
        gh.add_issue(issue)
        gh.seed_state(
            AWAITING_WORKTREE_ISSUE_NUMBER,
            awaiting_human=True,
            last_action_comment_id=STALE_PARK_COMMENT_ID,
            decomposer_agent=BACKEND_CLAUDE,
            decomposer_session_id=DECOMPOSER_SESSION,
        )

        mocks = self._run_decomposing(
            gh,
            issue,
            run_agent=_agent(),
        )

        mocks[RUN_AGENT].assert_not_called()
        mocks[CLEANUP_DECOMPOSE_WORKTREE].assert_not_called()

    def test_a_refused_split_write_keeps_worktree(self) -> None:
        # A human edits the parent's record into a version admission refuses
        # while the split releases its first child, so the parent's own write
        # behind that release is refused. The refusal is no failure for the
        # next dependency poll to retry: the dispatcher abandons the handler
        # on it, and the decomposer's worktree is kept rather than torn down.
        gh = FakeGitHubClient()
        issue = make_issue(REFUSED_SPLIT_ISSUE_NUMBER, label=LABEL_DECOMPOSING)
        gh.add_issue(issue)

        edits = _EditedOnRelease(gh)
        with patch.object(config, CONFIG_DECOMPOSE, True), patch.object(gh, "set_workflow_label", edits):
            mocks = self._run(
                lambda: _issue_processing._process_issue(gh, _TEST_SPEC, issue),
                run_agent=_agent(session_id=DECOMPOSER_SESSION, last_message=SPLIT_MANIFEST),
            )

        self.assertEqual(gh.pinned_data(REFUSED_SPLIT_ISSUE_NUMBER)["schema_version"], ANOTHER_VERSION)
        mocks[CLEANUP_DECOMPOSE_WORKTREE].assert_not_called()

    def test_a_refused_handoff_keeps_worktree(self) -> None:
        # With decomposition off, a parked decomposer hands the issue to the
        # developer, and a human edits the record into a version admission
        # refuses while that run is out. The report's guarded commit is
        # refused rather than raised, so the handler ends as an ordinary one;
        # the teardown asks the record itself and keeps the worktree.
        gh = FakeGitHubClient()
        issue = make_issue(REFUSED_HANDOFF_ISSUE_NUMBER, label=LABEL_DECOMPOSING)
        gh.add_issue(issue)
        gh.seed_state(
            REFUSED_HANDOFF_ISSUE_NUMBER, pickup_comment_id=100, awaiting_human=True, park_reason="decomposer_dirty",
        )

        with patch.object(config, CONFIG_DECOMPOSE, False):
            mocks = self._run(
                lambda: _issue_processing._process_issue(gh, _TEST_SPEC, issue),
                run_agent=_EditedWhileRunning(gh, REFUSED_HANDOFF_ISSUE_NUMBER),
                has_new_commits=[False, True],
            )

        self.assertEqual(gh.pinned_data(REFUSED_HANDOFF_ISSUE_NUMBER)["schema_version"], ANOTHER_VERSION)
        mocks[CLEANUP_DECOMPOSE_WORKTREE].assert_not_called()

    def test_an_unreadable_teardown_keeps_worktree(self) -> None:
        # The handoff above, its report's guarded commit refused over the
        # human's edit, with the record unreadable by the time the teardown
        # asks it again. That read proves no admission, and the run has
        # already met a refused record, so the worktree is kept too.
        gh = FakeGitHubClient()
        issue = make_issue(UNREADABLE_HANDOFF_ISSUE_NUMBER, label=LABEL_DECOMPOSING)
        gh.add_issue(issue)
        gh.seed_state(
            UNREADABLE_HANDOFF_ISSUE_NUMBER, pickup_comment_id=100, awaiting_human=True, park_reason="decomposer_dirty",
        )
        reads = _UnreadableAfterARefusal(gh)

        with patch.object(config, CONFIG_DECOMPOSE, False), patch.object(gh, "read_pinned_state", reads):
            mocks = self._run(
                lambda: _issue_processing._process_issue(gh, _TEST_SPEC, issue),
                run_agent=_EditedWhileRunning(gh, UNREADABLE_HANDOFF_ISSUE_NUMBER),
                has_new_commits=[False, True],
            )

        self.assertEqual(reads.refused, [UNREADABLE_HANDOFF_ISSUE_NUMBER], "the report's commit read the edit")
        mocks[CLEANUP_DECOMPOSE_WORKTREE].assert_not_called()

    def test_decompose_handles_non_string_rationale(self) -> None:
        # JSON-valid manifest with a non-string rationale (`[1,2,3]`,
        # `{}`, `42`) must not crash the handler at `.strip()` after
        # the agent already ran. Coerce to the placeholder.
        gh = FakeGitHubClient()
        issue = make_issue(
            NON_STRING_RATIONALE_ISSUE_NUMBER,
            label=LABEL_DECOMPOSING,
        )
        gh.add_issue(issue)
        self._run_decomposing(
            gh,
            issue,
            run_agent=_agent(
                session_id=DECOMPOSER_SESSION,
                last_message=_manifest('{"decision": "single", "rationale": [1, 2, 3]}'),
            ),
        )

        self.assertIn(
            (NON_STRING_RATIONALE_ISSUE_NUMBER, LABEL_READY),
            gh.label_history,
        )
        self.assertFalse(gh.pinned_data(NON_STRING_RATIONALE_ISSUE_NUMBER).get(KEY_AWAITING_HUMAN))
        rationale_comment = _comment_with_marker(
            gh,
            NON_STRING_RATIONALE_ISSUE_NUMBER,
            ":mag:",
        )
        self.assertIn("(no rationale provided)", rationale_comment)


class _EditedOnRelease:
    """The client's relabel, with a human's edit of the parent's record landing as a child is released."""

    def __init__(self, gh: FakeGitHubClient) -> None:
        self._gh = gh
        self._relabels = gh.set_workflow_label

    def __call__(self, issue, label, **options):
        """Relabel, and edit the parent's record into another version behind a child's release."""
        self._relabels(issue, label, **options)
        if issue.number != REFUSED_SPLIT_ISSUE_NUMBER and label == LABEL_READY:
            edited = dict(self._gh.pinned_data(REFUSED_SPLIT_ISSUE_NUMBER), schema_version=ANOTHER_VERSION)
            self._gh.seed_state(REFUSED_SPLIT_ISSUE_NUMBER, raw=True, **edited)


class _EditedWhileRunning:
    """The agent runner, with a human's edit of the issue's record landing while the run is out."""

    def __init__(self, gh: FakeGitHubClient, issue_number: int) -> None:
        self._gh = gh
        self._issue_number = issue_number

    def __call__(self, *run_args, **run_options):
        """Edit the record into another version, and return the developer's finished run."""
        edited = dict(self._gh.pinned_data(self._issue_number), schema_version=ANOTHER_VERSION)
        self._gh.seed_state(self._issue_number, raw=True, **edited)
        return _agent(session_id=DEV_SESSION, last_message=_reported(IMPLEMENTED_MESSAGE))


class _UnreadableAfterARefusal:
    """The client's pinned read, failing every reading of an issue after one admission refuses."""

    def __init__(self, gh: FakeGitHubClient) -> None:
        self._gh = gh
        self._reads = gh.read_pinned_state
        self.refused: list[int] = []

    def __call__(self, issue):
        """Read the record, and leave it unreadable behind a reading admission refuses."""
        reading = self._reads(issue)
        if not reading.supported:
            self.refused.append(issue.number)
            self._gh.pinned_failures.unreadable.add(issue.number)
        return reading
