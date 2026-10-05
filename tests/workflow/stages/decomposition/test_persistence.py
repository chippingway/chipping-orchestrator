# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import unittest
from unittest.mock import patch

from orchestrator.github.pinned_state import PINNED_STATE_MARKER
from orchestrator.workflow.engine import comments as _engine_comments
from tests.support.fakes import (
    FakeGitHubClient,
    FakeIssue,
    make_issue,
)
from tests.support.writer_claims import claimed_on_creation
from tests.workflow.fixtures import (
    KEY_AWAITING_HUMAN,
    KEY_PARENT_NUMBER,
    LABEL_BLOCKED,
    LABEL_DECOMPOSING,
    _agent,
    _manifest,
)
from tests.workflow.stages.decomposition.decomposing_test_support import (
    _ChildCreationSnapshotRecorder,
    _DecomposingWorkflowMixin,
    _ReachedFirstByAnotherPoller,
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
SEED_RECORD_ISSUE_NUMBER = 84
SEED_RETRY_ISSUE_NUMBER = 85
# What every split summary opens with, umbrella or not.
_SUMMARY = ":bookmark_tabs: decomposer split this into"
# The hidden receipt every split summary ends on, naming its parent and attempt.
_SUMMARY_RECEIPT = "<!--orchestrator-split-summary:issue={issue}:attempt={attempt}-->"
KEY_SPLIT_ATTEMPT = "split_attempt"
# An attempt no split in these cases minted.
_EARLIER_ATTEMPT = "0123456789abcdef"
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


class ClaimedSplitCompletionTest(
    unittest.TestCase,
    _DecomposingWorkflowMixin,
):
    """A split that seeds each child under the child's own writer claim.

    A child another poller holds when its seed is due is recorded and left
    unseeded, and the split publishes nothing past it: the next tick's
    recovery seeds it, posts the summary the split owed, and finalizes.
    """

    def test_a_held_child_defers_the_finalize(self) -> None:
        # The receipt of an earlier split attempt on the thread is not this
        # attempt's: the summary is still owed, and posted.
        gh, issue, created = self._left_to_recovery(SEED_CONTENTION_ISSUE_NUMBER)
        gh.comment(issue, _engine_comments._with_orch_marker(_receipt(issue.number, _EARLIER_ATTEMPT)))

        parent = gh.pinned_data(SEED_CONTENTION_ISSUE_NUMBER)
        self.assertEqual(parent.get(KEY_CHILDREN), created, "every child is recorded")
        self.assertEqual(_records(gh, created), [{}, {}], "and none is written")
        self.assertFalse(parent.get(KEY_AWAITING_HUMAN), "nothing parks")
        self.assertEqual(gh.label_history, [], "the parent is not finalized past them")
        self.assertEqual(_summaries(gh, SEED_CONTENTION_ISSUE_NUMBER), [], "nor summarized")

        self._run_decomposing(gh, issue, run_agent=_agent())[RUN_AGENT].assert_not_called()

        self._assert_recovered(gh, SEED_CONTENTION_ISSUE_NUMBER, created)

    def test_a_retried_recovery_posts_one_summary(self) -> None:
        # A refused summary is posted on the retry; a landed one is not posted
        # twice, even where a child's title quotes the pinned-state marker.
        for step in ("comment", "set_workflow_label"):
            with self.subTest(failing=step):
                gh, issue, created = self._left_to_recovery(SEED_RETRY_ISSUE_NUMBER)
                gh.get_issue(created[-1]).title = f"B {PINNED_STATE_MARKER}"
                refused = patch.object(gh, step, side_effect=RuntimeError("github refused the write"))

                with refused, self.assertRaises(RuntimeError):
                    self._run_decomposing(gh, issue, run_agent=_agent())

                self.assertEqual(gh.label_history, [], "the failed recovery finalizes nothing")

                self._run_decomposing(gh, issue, run_agent=_agent())

                self._assert_recovered(gh, SEED_RETRY_ISSUE_NUMBER, created)

    def test_a_released_child_is_seeded_in_place(self) -> None:
        # Another poller held each child for its missing seed, on a pinned
        # comment of its own, and let go: the seed lands on that one comment,
        # lifting the hold, and the split finalizes on the same tick.
        gh, issue = _decomposing_issue(SEED_RECORD_ISSUE_NUMBER)
        gh.create_child_issue = _ReachedFirstByAnotherPoller(gh)

        self._run_decomposing(
            gh,
            issue,
            run_agent=_agent(session_id=DECOMPOSER_SESSION, last_message=SPLIT_MANIFEST),
        )

        for child in gh.created_child_issues:
            records = [comment.id for comment in child.comments if PINNED_STATE_MARKER in comment.body]
            seed = gh.read_pinned_state(child)
            self.assertEqual(records, [seed.comment_id], f"#{child.number} carries one pinned record")
            self.assertEqual(seed.get(KEY_PARENT_NUMBER), SEED_RECORD_ISSUE_NUMBER)
            self.assertFalse(seed.get(KEY_AWAITING_HUMAN), "the hold the seed answers is lifted")
        self.assertEqual(len(_summaries(gh, SEED_RECORD_ISSUE_NUMBER)), 1)
        self.assertIn((SEED_RECORD_ISSUE_NUMBER, LABEL_BLOCKED), gh.label_history)

    def _left_to_recovery(self, number: int) -> tuple[FakeGitHubClient, FakeIssue, list[int]]:
        """A split whose every child another poller held as it was created, and the children it recorded.

        The attempt the split recorded is kept, for the summary its recovery
        posts to be held to.
        """
        gh, issue = _decomposing_issue(number)
        with claimed_on_creation(gh), self.assertLogs("orchestrator.workflow"):
            self._run_decomposing(
                gh,
                issue,
                run_agent=_agent(session_id=DECOMPOSER_SESSION, last_message=SPLIT_MANIFEST),
            )
        self.recorded_attempt = gh.pinned_data(number)[KEY_SPLIT_ATTEMPT]
        return gh, issue, [child.number for child in gh.created_child_issues]

    def _assert_recovered(self, gh: FakeGitHubClient, number: int, created: list[int]) -> None:
        """Every child seeded, one summary naming each and the recorded attempt, and the parent finalized once."""
        parents = {gh.pinned_data(child).get(KEY_PARENT_NUMBER) for child in created}
        self.assertEqual(parents, {number})
        summaries = _summaries(gh, number)
        self.assertEqual(len(summaries), 1, "the summary is posted exactly once")
        for child, title in zip(created, ("A", "B"), strict=True):
            self.assertIn(f"- #{child}: {title}", summaries[0])
        self.assertIn(_receipt(number, self.recorded_attempt), summaries[0])
        parent = gh.pinned_data(number)
        self.assertEqual(parent[KEY_SPLIT_ATTEMPT], self.recorded_attempt, "the recovery keeps the attempt")
        self.assertEqual(gh.label_history, [(number, LABEL_BLOCKED)])
        self.assertFalse(parent.get(KEY_AWAITING_HUMAN))


def _records(gh: FakeGitHubClient, numbers: list[int]) -> list[dict]:
    """What each of these issues' pinned records carries, in order."""
    return [gh.pinned_data(number) for number in numbers]


def _receipt(number: int, attempt: str) -> str:
    """The literal receipt a summary of this parent's split attempt ends on."""
    return _SUMMARY_RECEIPT.format(issue=number, attempt=attempt)


def _summaries(gh: FakeGitHubClient, number: int) -> list[str]:
    """The split summaries posted on one parent's thread."""
    return [
        body for posted_on, body in gh.posted_comments
        if posted_on == number and _SUMMARY in body
    ]


def _decomposing_issue(number: int) -> tuple[FakeGitHubClient, FakeIssue]:
    """A client holding one `decomposing` issue the decomposer is about to split."""
    gh = FakeGitHubClient()
    issue = make_issue(number, label=LABEL_DECOMPOSING)
    gh.add_issue(issue)
    return gh, issue
