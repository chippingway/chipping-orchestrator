# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Tests for fixing failure behavior."""

from __future__ import annotations

import shutil
import tempfile
import unittest
from pathlib import Path

from orchestrator.agents import models as _agent_models
from orchestrator.agents.backends import agy as _agy
from orchestrator.github.pinned_state import PinnedState
from tests.support import agy_stream as _agy_stream
from tests.workflow.stages.fixing import (
    fixing_test_support as support,
    report_crash_support as crash,
)

IssueScenario = support.IssueScenario

ALICE = support.ALICE
AWAITING_HUMAN = support.AWAITING_HUMAN
DEBOUNCE_CONFIG = support.DEBOUNCE_CONFIG
DEBOUNCE_SECONDS = support.DEBOUNCE_SECONDS
DEV_SESSION = support.DEV_SESSION
DEV_SESSION_ID = support.DEV_SESSION_ID
DOCUMENTING = support.DOCUMENTING
FIX_FEEDBACK = support.FIX_FEEDBACK
FRESH_SESSION = support.FRESH_SESSION
FakeComment = support.FakeComment
FakeUser = support.FakeUser
ISSUE = support.ISSUE
LAST_ACTION_COMMENT_ID = support.LAST_ACTION_COMMENT_ID
PARK_PUSH_FAILED = support.PARK_PUSH_FAILED
PARK_REASON = support.PARK_REASON
PR_LAST_COMMENT_ID = support.PR_LAST_COMMENT_ID
PUSHED_FIX_MESSAGE = support.PUSHED_FIX_MESSAGE
RESUME_SESSION_ID = support.RESUME_SESSION_ID
RUN_AGENT = support.RUN_AGENT
SHA_AFTER = support.SHA_AFTER
SHA_BEFORE = support.SHA_BEFORE
TRIGGER_ID = support.TRIGGER_ID
VALIDATING = support.VALIDATING
_FixingFixtureMixin = support._FixingFixtureMixin
_agent = support._agent
config = support.config
datetime = support.datetime
patch = support.patch
timedelta = support.timedelta
timezone = support.timezone

_ALICE_USER = FakeUser(ALICE)
_LABEL_VALIDATING = (ISSUE, VALIDATING)
_CLEANUP_QUESTION_WT = "_cleanup_question_worktree"
_CLEANUP_TERMINAL_BRANCH = "_cleanup_terminal_branch"
_DIRTY_FILE_NAME = "orchestrator/uncommitted_work.py"
_DIRTY_CONTENT = "# uncommitted work from interrupted session\n"


class FixingFailureDispositionTest(unittest.TestCase, _FixingFixtureMixin):
    def test_missing_dev_session_spawns_fresh(self) -> None:
        # `dev_session_id` may be absent on a `fixing` issue whose prior
        # dev session was dropped by the silent-park fallback, or on
        # legacy state that pre-dates session tracking. The fixing
        # handler MUST NOT park on missing-session: `_resume_dev_with_text`
        # treats `dev_sid=None` as the fresh-spawn case, so the dev
        # resumes correctly with the locked backend. Asserting fresh
        # spawn here pins the "resume correctly" half of the
        # crash/restart contract (the other half -- park on missing
        # `pr_number` -- is in `FixingLabelRoutingTest`).
        long_ago = support.now_utc() - timedelta(hours=1)
        comment = FakeComment(
            id=TRIGGER_ID,
            body="please tighten the test",
            user=_ALICE_USER,
            created_at=long_ago,
        )
        pr = self._open_pr()
        scenario = IssueScenario(
            *self._seed(
                pr=pr,
                issue_comments=[comment],
                extra_state={DEV_SESSION_ID: None},
            )
        )

        with patch.object(config, DEBOUNCE_CONFIG, DEBOUNCE_SECONDS):
            self._mocks = self._run_fixing(
                scenario.github,
                scenario.issue,
                run_agent=_agent(
                    session_id=FRESH_SESSION,
                    last_message=PUSHED_FIX_MESSAGE,
                ),
                head_shas=(SHA_BEFORE, SHA_AFTER),
            )

        # The handler resumed with `resume_session_id=None` -- the locked
        # backend (`dev_agent=claude`) drives a fresh spawn rather than
        # parking on the missing session.
        self._mocks[RUN_AGENT].assert_called_once()
        call_args = self._mocks[RUN_AGENT].call_args
        self.assertIsNone(call_args.kwargs.get(RESUME_SESSION_ID))
        # Did NOT park -- the issue made progress instead (advancing
        # directly to validating for the reviewer to re-evaluate).
        self._pinned_data = scenario.github.pinned_data(ISSUE)
        self.assertFalse(self._pinned_data.get(AWAITING_HUMAN))
        self.assertIn(_LABEL_VALIDATING, scenario.github.label_history)
        self.assertNotIn((ISSUE, DOCUMENTING), scenario.github.label_history)

    def test_push_error_parks_with_transient_reason(self) -> None:
        # Push failure on the dev fix -> park awaiting_human in `fixing`
        # with the transient `push_failed` reason. The workflow label
        # MUST stay at `fixing` so the operator can see where the issue
        # is in the lifecycle; flipping to `validating` would imply the
        # fix landed when it did not.
        long_ago = support.now_utc() - timedelta(hours=1)
        comment = FakeComment(
            id=TRIGGER_ID,
            body=FIX_FEEDBACK,
            user=_ALICE_USER,
            created_at=long_ago,
        )
        self._pr = self._open_pr()
        scenario = IssueScenario(*self._seed(pr=self._pr, issue_comments=[comment]))

        with patch.object(config, DEBOUNCE_CONFIG, DEBOUNCE_SECONDS):
            self._run_fixing(
                scenario.github,
                scenario.issue,
                run_agent=_agent(
                    session_id=DEV_SESSION,
                    last_message=PUSHED_FIX_MESSAGE,
                ),
                head_shas=(SHA_BEFORE, SHA_AFTER),
                push_branch=False,
            )

        pinned_data = scenario.github.pinned_data(ISSUE)
        self.assertTrue(pinned_data.get(AWAITING_HUMAN))
        self.assertEqual(pinned_data.get(PARK_REASON), PARK_PUSH_FAILED)
        # Label stayed at `fixing` -- no relabel to `validating`.
        self.assertNotIn(_LABEL_VALIDATING, scenario.github.label_history)
        self.assertNotIn((ISSUE, DOCUMENTING), scenario.github.label_history)
        # The round reported, so what it consumed rides the record rather than
        # the readers: the report is still owed, and the write that finally
        # publishes it is the one that may record this feedback as answered.
        # The readers stay put so the retry has a batch to replay, and the
        # record is what stops the next tick resuming a second developer over
        # the identical prompt.
        self.assertLess(pinned_data.get(PR_LAST_COMMENT_ID), TRIGGER_ID)
        self.assertEqual(
            crash.frozen_record(PinnedState(state_data=pinned_data)).watermarks,
            (
                (LAST_ACTION_COMMENT_ID, TRIGGER_ID),
                (PR_LAST_COMMENT_ID, TRIGGER_ID),
            ),
        )

    def test_a_dirty_tree_releases_the_report_it_owes(self) -> None:
        # A tree this host PROVED is carrying something is a refusal no later
        # poll takes back and one no road here publishes over, so a round that
        # REPORTED ends on the terminal notice its report owns -- whether it
        # committed or not. Both alternatives announce one condition twice: a
        # round with nothing to push would park saying its developer asked a
        # question, with the human answering it answering nothing; and a round
        # that committed would take the push tail's own checkout park, keep the
        # record, and meet the recovery on the very next tick over the
        # identical refusal.
        #
        # The record is RELEASED with the notice: left standing, cleaning the
        # tree alone would publish the report and send the issue to review,
        # which is the decision this notice exists to put to a human. The DEBT
        # outlives it, the commit stays in the checkout, and the batch the
        # prompt delivered rides the park's own write -- there is no record
        # left to carry it, and the reply the notice asks for has to resume a
        # developer over what has really gone unanswered.
        for case, committed in (("committed", True), ("report only", False)):
            with self.subTest(round=case):
                pinned_data = self._dirty_round(committed=committed)

                self.assertEqual(
                    (pinned_data.get(AWAITING_HUMAN),
                     pinned_data.get(PARK_REASON),
                     pinned_data.get(crash.OWED_REPORT)),
                    (True, crash.UNDELIVERABLE, True),
                )
                self.assertIsNone(
                    crash.frozen_record(PinnedState(state_data=pinned_data)),
                )
                self.assertTrue(support.posted_comment_contains(
                    self._scenario.github, crash.UNPUBLISHABLE_PHRASE,
                ))
                self.assertNotIn(_LABEL_VALIDATING, scenario_labels(self))
                self.assertNotIn((ISSUE, DOCUMENTING), scenario_labels(self))
                self.assertGreaterEqual(
                    pinned_data.get(PR_LAST_COMMENT_ID), TRIGGER_ID,
                )

    def test_no_commit_question_parks_in_fixing(self) -> None:
        # Dev returned a clarifying question with no new commit. The
        # handler routes through `_on_question`, which parks
        # awaiting_human and posts the agent's text on the issue
        # thread. Label MUST stay at `fixing`.
        long_ago = support.now_utc() - timedelta(hours=1)
        comment = FakeComment(
            id=TRIGGER_ID,
            body="please address the lint",
            user=_ALICE_USER,
            created_at=long_ago,
        )
        pr = self._open_pr()
        scenario = IssueScenario(*self._seed(pr=pr, issue_comments=[comment]))

        with patch.object(config, DEBOUNCE_CONFIG, DEBOUNCE_SECONDS):
            self._run_fixing(
                scenario.github,
                scenario.issue,
                run_agent=_agent(
                    session_id=DEV_SESSION,
                    last_message="Should I prefer ruff or black for this?",
                ),
                # No new commit: head_sha unchanged between before/after.
                head_shas=(SHA_BEFORE, SHA_BEFORE),
            )

        self._pinned_data = scenario.github.pinned_data(ISSUE)
        self.assertTrue(self._pinned_data.get(AWAITING_HUMAN))
        self.assertIsNone(self._pinned_data.get(PARK_REASON))
        self.assertNotIn(_LABEL_VALIDATING, scenario.github.label_history)
        self.assertNotIn((ISSUE, DOCUMENTING), scenario.github.label_history)
        # Agent's question was surfaced to the human.
        self._joined = "\n".join(comment_body for _, comment_body in scenario.github.posted_comments)
        self.assertIn(
            "Should I prefer ruff or black for this?",
            self._joined,
        )

    def test_unfinished_command_validating_route(self) -> None:
        wt_path, dirty_file = _make_dirty_worktree(self, "fixing-failure-wt-")
        scenario = IssueScenario(
            *self._seed(
                pr=self._open_pr(
                    issue_comments=[
                        FakeComment(
                            id=support.REVIEWER_FEEDBACK_ID,
                            body=(
                                ":eyes: codex review (round 1/3) requested changes:\n\n"
                                "please fix the last-frame-wins docstring\n\n"
                                "<!--orchestrator-comment-->"
                            ),
                            user=FakeUser(support.ORCHESTRATOR),
                            created_at=support.now_utc() - timedelta(hours=2),
                        ),
                    ],
                ),
                issue_comments=[
                    FakeComment(
                        id=support.COMMAND_COMMENT_ID,
                        body=support.CONTINUE_COMMAND,
                        user=_ALICE_USER,
                        created_at=support.now_utc() - timedelta(minutes=10),
                    ),
                ],
                extra_state={
                    support.PENDING_FIX_AT: None,
                    support.PENDING_FIX_ISSUE_MAX_ID: None,
                    support.PENDING_FIX_REVIEWER_COMMENT_ID: support.REVIEWER_FEEDBACK_ID,
                    support.AWAITING_HUMAN: True,
                    support.PARK_REASON: support.PARK_AGENT_SILENT,
                    support.REVIEW_ROUND: 1,
                    support.PR_LAST_COMMENT_ID: support.INITIAL_PR_COMMENT_WATERMARK,
                },
            )
        )
        pinned = _assert_execution_park(
            self, scenario, _run_execution_failure(self, scenario, wt_path), dirty_file,
        )
        self.assertEqual(
            (
                pinned.get("pr_number"),
                pinned.get(support.PENDING_FIX_REVIEWER_COMMENT_ID),
                pinned.get(support.PENDING_FIX_AT),
            ),
            (support.PR_NUMBER, support.REVIEWER_FEEDBACK_ID, None),
        )
        _assert_continue_success(
            self,
            scenario,
            _run_continue_retry(self, scenario, wt_path),
            dirty_file,
            "please fix the last-frame-wins docstring",
        )

    def test_unfinished_command_in_review_route(self) -> None:
        wt_path, dirty_file = _make_dirty_worktree(self, "fixing-in-review-wt-")
        scenario = IssueScenario(
            *self._seed(
                pr=self._open_pr(),
                issue_comments=[
                    FakeComment(
                        id=TRIGGER_ID,
                        body="please address the lint",
                        user=_ALICE_USER,
                        created_at=support.now_utc() - timedelta(hours=1),
                    ),
                ],
                extra_state={
                    support.PENDING_FIX_ISSUE_IDS: [TRIGGER_ID],
                },
            )
        )
        pinned = _assert_execution_park(
            self, scenario, _run_execution_failure(self, scenario, wt_path), dirty_file,
        )
        self.assertEqual(
            (
                pinned.get("pr_number"),
                pinned.get(support.PENDING_FIX_AT),
                pinned.get(support.PENDING_FIX_ISSUE_MAX_ID),
                pinned.get(support.PENDING_FIX_ISSUE_IDS),
                pinned.get(support.PENDING_FIX_REVIEWER_COMMENT_ID),
            ),
            (support.PR_NUMBER, support.PENDING_FIX_AT_TS, TRIGGER_ID, [TRIGGER_ID], None),
        )
        _assert_continue_success(
            self,
            scenario,
            _run_continue_retry(self, scenario, wt_path),
            dirty_file,
            "please address the lint",
        )

    def _dirty_round(self, *, committed: bool) -> dict:
        """One fix round that reported over a checkout carrying loose work."""
        long_ago = support.now_utc() - timedelta(hours=1)
        comment = FakeComment(
            id=TRIGGER_ID,
            body="please rename helper",
            user=_ALICE_USER,
            created_at=long_ago,
        )
        pr = self._open_pr()
        scenario = IssueScenario(*self._seed(pr=pr, issue_comments=[comment]))
        self._scenario = scenario

        with patch.object(config, DEBOUNCE_CONFIG, DEBOUNCE_SECONDS):
            self._run_fixing(
                scenario.github,
                scenario.issue,
                run_agent=_agent(
                    session_id=DEV_SESSION,
                    last_message=PUSHED_FIX_MESSAGE,
                ),
                head_shas=(
                    (SHA_BEFORE, SHA_AFTER) if committed
                    else (SHA_BEFORE, SHA_BEFORE)
                ),
                dirty_files=["orchestrator/foo.py"],
            )
        return scenario.github.pinned_data(ISSUE)


def _make_dirty_worktree(case: unittest.TestCase, prefix: str) -> tuple[Path, Path]:
    wt_dir = tempfile.mkdtemp(prefix=prefix)
    case.addCleanup(shutil.rmtree, wt_dir, ignore_errors=True)
    wt_path = Path(wt_dir)
    dirty_file = wt_path / _DIRTY_FILE_NAME
    dirty_file.parent.mkdir(parents=True, exist_ok=True)
    dirty_file.write_text(_DIRTY_CONTENT)
    return wt_path, dirty_file


def _run_execution_failure(case, scenario: IssueScenario, wt_path: Path) -> dict:
    agent_result = _agy.agy_result(
        _agent_models.AgentRunOptions(resume_session_id=DEV_SESSION),
        _agent_models.SubprocessResult(
            _agy_stream.ToolStream.canceled_active_command(), "", 1, False, False,
        ),
    )
    with (
        patch.object(config, DEBOUNCE_CONFIG, DEBOUNCE_SECONDS),
        patch.object(support.worktree_paths, support.WORKTREE_PATH, return_value=wt_path),
    ):
        return case._run_fixing(
            scenario.github,
            scenario.issue,
            run_agent=agent_result,
            head_shas=(SHA_BEFORE, SHA_BEFORE),
            dirty_files=[_DIRTY_FILE_NAME],
        )


def _assert_execution_park(
    case, scenario: IssueScenario, first_mocks: dict, dirty_file: Path,
) -> dict:
    pinned = scenario.github.pinned_data(ISSUE)
    case.assertEqual(
        (pinned.get(AWAITING_HUMAN), pinned.get(PARK_REASON)),
        (True, support.PARK_AGENT_EXECUTION_FAILED),
    )
    case.assertNotIn(_LABEL_VALIDATING, scenario.github.label_history)
    first_mocks[_CLEANUP_QUESTION_WT].assert_not_called()
    first_mocks[_CLEANUP_TERMINAL_BRANCH].assert_not_called()
    case.assertTrue(dirty_file.exists())
    case.assertEqual(dirty_file.read_text(), _DIRTY_CONTENT)
    case._assert_failure_notice(scenario)
    return pinned


def _run_continue_retry(case, scenario: IssueScenario, wt_path: Path) -> dict:
    retry_command_id = max(comment.id for comment in scenario.issue.comments) + 1
    scenario.issue.comments.append(
        FakeComment(
            id=retry_command_id,
            body=support.CONTINUE_COMMAND,
            user=_ALICE_USER,
            created_at=support.now_utc(),
        ),
    )
    with (
        patch.object(config, DEBOUNCE_CONFIG, DEBOUNCE_SECONDS),
        patch.object(support.worktree_paths, support.WORKTREE_PATH, return_value=wt_path),
    ):
        return case._run_fixing(
            scenario.github,
            scenario.issue,
            run_agent=_agent(
                session_id=support.FRESH_SESSION,
                last_message=support.PUSHED_FIX_MESSAGE,
            ),
            head_shas=(SHA_BEFORE, SHA_AFTER),
        )


def _assert_continue_success(
    case, scenario: IssueScenario, retry_mocks: dict, dirty_file: Path, expected_text: str,
) -> None:
    retry_mocks["_ensure_worktree"].assert_not_called()
    retry_mocks[_CLEANUP_QUESTION_WT].assert_not_called()
    retry_mocks[_CLEANUP_TERMINAL_BRANCH].assert_not_called()
    case.assertEqual(
        (
            scenario.github.pinned_data(ISSUE).get(AWAITING_HUMAN),
            scenario.github.pinned_data(ISSUE).get(PARK_REASON),
            dirty_file.exists(),
        ),
        (False, None, True),
    )
    retry_mocks[support.RUN_AGENT].assert_called_once()
    case.assertIn(expected_text, retry_mocks[support.RUN_AGENT].call_args.args[1])
    case.assertIsNone(retry_mocks[support.RUN_AGENT].call_args.kwargs.get(support.RESUME_SESSION_ID))
    case.assertIn(_LABEL_VALIDATING, scenario.github.label_history)


def scenario_labels(case) -> list:
    """The labels the tick this case just ran moved the issue through."""
    return case._scenario.github.label_history
