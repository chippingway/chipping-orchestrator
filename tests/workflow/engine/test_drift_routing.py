# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Workflow drift routing and acknowledgement tests."""
from __future__ import annotations

import unittest
from unittest.mock import patch

from orchestrator import config
from orchestrator.workflow.engine import (
    content_hash as _content_hash,
    drift,
    issue_processing as _issue_processing,
    pickup as _pickup,
    prompt_context as _prompt_context,
)
from orchestrator.workflow.stages.decomposition import blocked as _blocked
from orchestrator.workflow.stages.in_review import handler as _in_review
from orchestrator.workflow.stages.validating import handler as _validating
from tests.support.fakes import DEFAULT_PR_HEAD_SHA
from tests.workflow import published_reports as _published_reports
from tests.workflow.engine import drift_test_support as support
from tests.workflow.repo_values import EXISTING_CHECKOUT


class HandlePickupInitializesUserContentHashTest(
    unittest.TestCase, support._PatchedWorkflowMixin,
):
    def test_pickup_with_decompose_off_seeds_hash(self) -> None:
        gh = support.FakeGitHubClient()
        issue = support.make_issue(1)
        gh.add_issue(issue)

        with patch.object(config, "DECOMPOSE", False):
            self._run(
                lambda: _pickup._handle_pickup(gh, support._TEST_SPEC, issue),
                run_agent=support._agent(last_message="q"),
                has_new_commits=False,
            )

        state = gh.pinned_data(1)
        self.assertIn(support.KEY_USER_CONTENT_HASH, state)
        # Hash filters the pickup comment by id (it has been recorded in
        # `orchestrator_comment_ids`), so it should match a re-computation
        # over the same set.
        orch_ids = set(state.get("orchestrator_comment_ids") or [])
        self.assertEqual(
            state[support.KEY_USER_CONTENT_HASH],
            _content_hash._compute_user_content_hash(issue, orch_ids),
        )

    def test_pickup_with_decompose_on_seeds_hash(self) -> None:
        gh = support.FakeGitHubClient()
        issue = support.make_issue(2)
        gh.add_issue(issue)

        with patch.object(config, "DECOMPOSE", True):
            self._run(
                lambda: _pickup._handle_pickup(gh, support._TEST_SPEC, issue),
                run_agent=support._agent(
                    session_id="dec-sess",
                    last_message=(
                        "fits one\n\n```orchestrator-manifest\n"
                        '{"decision": "single", "rationale": "small"}\n'
                        "```"
                    ),
                ),
            )

        state = gh.pinned_data(2)
        self.assertIn(support.KEY_USER_CONTENT_HASH, state)


class UserContentChangePromptIncludesCommentsTest(unittest.TestCase):
    """A drift triggered by a NEW human comment (not a body edit) must
    surface that comment to the dev. Quoting only title/body would leave
    the dev unaware of the acceptance criterion the human just posted."""

    def test_recent_comments_quoted_in_resume_prompt(self) -> None:
        issue = support.make_issue(1, title="t", body="b")
        issue.comments.append(support.FakeComment(
            id=support._PROMPT_COMMENT_ID,
            body="new acceptance criterion: handle empty input",
            user=support.FakeUser(support.TRUSTED_AUTHOR),
        ))
        comments_text = _prompt_context._recent_comments_text(issue)
        prompt = drift._build_user_content_change_prompt(
            issue, comments_text,
        )
        self.assertIn("new acceptance criterion", prompt)
        self.assertIn("Conversation so far", prompt)
        self.assertIn("Updated issue body", prompt)


class FirstTimeHashSeedingIsDurableTest(
    unittest.TestCase, support._PatchedWorkflowMixin,
):
    """Reviewer point 3: `_detect_user_content_change` must persist the
    first-time baseline via `gh.write_pinned_state` immediately, so a
    later edit after a parked/idle tick is not silently absorbed as the
    new baseline.

    A child waiting on `workflow:blocked` is the one issue nothing is
    persisted for: its requirements are compared once it is released to
    `ready`, which decides on a missing baseline itself."""

    def test_validating_no_reply_persists_baseline(
        self,
    ) -> None:
        # Legacy state (no `user_content_hash`) parked on awaiting_human
        # with no new comments. `_handle_validating`'s awaiting-human
        # path returns without writing state on a real no-reply tick;
        # the durability fix in `_detect_user_content_change` must still
        # have written the baseline by then.
        gh = support.FakeGitHubClient()
        issue = support.make_issue(100, label=support.LABEL_VALIDATING, body="initial body")
        gh.add_issue(issue)
        pr = support.FakePR(number=1000, head_branch="orchestrator/chippingway__chipping-orchestrator/issue-100")
        gh.add_pr(pr)
        gh.seed_state(
            100,
            pr_number=pr.number,
            awaiting_human=True,
            last_action_comment_id=support._INITIAL_LAST_ACTION_COMMENT_ID,
            review_round=1,
        )

        # Tick: no new comments and no hash baseline. Park branch
        # returns early without writing state.
        self._run(
            lambda: _validating._handle_validating(gh, support._TEST_SPEC, issue),
            run_agent=support._agent(),
        )

        # Baseline durably persisted by the first-call branch in
        # `_detect_user_content_change`.
        state = gh.pinned_data(100)
        self.assertIsNotNone(state.get(support.KEY_USER_CONTENT_HASH))

    def test_blocked_child_poll_records_nothing(self) -> None:
        # A child waiting on a sibling with no baseline recorded, edited
        # between two due dependency polls: neither writes or tells
        # anything, so no edit made while it waits is taken as its baseline.
        gh = support.FakeGitHubClient()
        child = support.make_issue(
            support._BLOCKED_CHILD_ISSUE_NUMBER,
            label=support.LABEL_BLOCKED,
            body="child body",
        )
        gh.add_issue(child)
        gh.seed_state(
            support._BLOCKED_CHILD_ISSUE_NUMBER,
            parent_number=support._BLOCKED_PARENT_ISSUE_NUMBER,
        )
        recorded = gh.pinned_data(support._BLOCKED_CHILD_ISSUE_NUMBER)

        child.body = "child body, edited"
        self._poll_blocked(gh, child)
        child.body = "child body, edited again"
        self._poll_blocked(gh, child)

        self.assertEqual(gh.pinned_data(support._BLOCKED_CHILD_ISSUE_NUMBER), recorded)
        self.assertEqual(
            (gh.write_state_calls, gh.label_history, gh.posted_comments),
            (0, [], []),
        )

    def _poll_blocked(self, gh, child) -> None:
        """One due dependency poll of the waiting child."""
        self._run(
            lambda: _blocked._handle_blocked(gh, support._TEST_SPEC, child),
            run_agent=support._agent(),
        )


class ReadyBaselineDecisionTest(unittest.TestCase):
    """The drift check `ready` asks before anything implements, and what it calls a missing baseline."""

    def test_a_staged_baseline_writes_nothing(self) -> None:
        # Asked over a reading its caller holds, a first encounter and an
        # observed reading the thread still matches each stage that reading's
        # fingerprint on the state as the baseline and write nothing: the
        # caller's own checkpoint lands it.
        for recorded_as in (None, "observed_user_content_hash"):
            with self.subTest(recorded_as=recorded_as):
                case = support._content_change_case(
                    "body", "body",
                    comments=(support.FakeComment(id=1, body=support.CONTINUE_COMMAND),),
                )
                prior = case.state.data.pop(support.KEY_USER_CONTENT_HASH)
                if recorded_as is not None:
                    case.state.set(recorded_as, prior)

                held = list(case.issue.comments)
                changed = drift._detect_user_content_change(case.github, case.issue, case.state, reading=held)

                self.assertIsNone(changed)
                self.assertEqual(case.state.get(support.KEY_USER_CONTENT_HASH), case.current_hash)
                self.assertEqual(case.github.write_state_calls, case.before_writes)

    def test_only_a_string_reading_is_a_baseline(self) -> None:
        # Either reading the check compares against counts, spelled as its
        # writers spell it; a value of any other shape is no reading at all.
        for record, unbaselined in (
            ({}, True),
            ({support.KEY_USER_CONTENT_HASH: 7}, True),
            ({"observed_user_content_hash": None}, True),
            ({support.KEY_USER_CONTENT_HASH: "a reading"}, False),
            ({"observed_user_content_hash": "a reading"}, False),
        ):
            with self.subTest(record=record):
                state = support.PinnedState(data=dict(record))
                self.assertEqual(drift._unbaselined(state), unbaselined)


class ReadyChildDispatchTest(unittest.TestCase, support._PatchedWorkflowMixin):
    """A split's child with no baseline, dispatched onto `ready` as a tick dispatches it."""

    def test_its_decomposer_runs_before_implementing(self) -> None:
        # Its first tick reroutes it and runs nothing; its second runs the
        # decomposer, which votes `single`; only its third runs an
        # implementer, on requirements its reroute baselined.
        gh, child = self._released()

        ran = [
            self._dispatched(gh, child, run_agent=support._agent(last_message=support.SINGLE_MANIFEST)),
            self._dispatched(gh, child, run_agent=support._agent(last_message=support.SINGLE_MANIFEST)),
            self._dispatched(
                gh, child, run_agent=support._agent(last_message=support._reported()),
                has_new_commits=[False, True], push_branch=True,
            ),
        ]

        self.assertEqual(ran, [0, 1, 1])
        self.assertEqual(
            [label for number, label in gh.label_history if number == support.READY_CHILD][:3],
            [support.LABEL_DECOMPOSING, support.LABEL_READY, support.LABEL_IMPLEMENTING],
        )

    def test_a_hold_defers_an_owed_reroute(self) -> None:
        # A reroute whose reset landed and whose relabel did not, on an issue
        # an operator holds: the dispatch relabels, says, and writes nothing
        # until the hold comes off, and then finishes the reroute.
        for hold in ("paused", "backlog"):
            with self.subTest(hold=hold):
                gh, child = self._released(ready_reroute={"orphans": [], "unbaselined": True})
                child.labels.append(support.FakeLabel(hold))

                held = self._dispatched(gh, child, run_agent=support._agent())
                untouched = (list(gh.label_history), list(gh.posted_comments), gh.write_state_calls)
                child.labels = [label for label in child.labels if label.name != hold]
                self._dispatched(gh, child, run_agent=support._agent())

                self.assertEqual((held, untouched), (0, ([], [], 0)))
                self.assertEqual(gh.label_history, [(support.READY_CHILD, support.LABEL_DECOMPOSING)])

    def _released(self, **pinned) -> tuple:
        """The child, on `ready`, its record linking it to its parent and carrying no baseline beside `pinned`."""
        child = support.make_issue(support.READY_CHILD, label=support.LABEL_READY, body="a slice")
        gh = support.FakeGitHubClient()
        gh.add_issue(child)
        gh.seed_state(support.READY_CHILD, parent_number=support.READY_PARENT, **pinned)
        return gh, child

    def _dispatched(self, gh, child, **run) -> int:
        """One dispatch of the child, through every guard a tick takes; how many agents it ran."""
        mocks = self._run(
            lambda: _issue_processing._process_issue(gh, support._TEST_SPEC, child),
            **run,
        )
        return mocks[support.RUN_AGENT].call_count


class BareAddAgentRunsIsNotDriftTest(
    unittest.TestCase, support._PatchedWorkflowMixin,
):
    """The command that buys an issue more agent runs is a control, not an edit.

    The dispatcher answers it and hands the SAME tick to the stage below, so a
    hash that counted the command would meet the handler as a body edit
    nobody made: `validating` would resume the developer on "the human edited
    the issue" instead of running the reviewer round the issue was stopped
    mid-way through.
    """

    def test_validating_runs_the_reviewer_not_the_dev(self) -> None:
        gh, issue = self._parked_and_bought()

        _published_reports.publishes_the_report(gh, issue)
        mocks = self._run(
            lambda: _validating._handle_validating(
                gh, support._TEST_SPEC, issue,
            ),
            run_agent=support._agent(
                last_message=support.REVIEW_APPROVED_MESSAGE,
            ),
            # The approval's evidence is published, over a checkout on this
            # host, before the approval is acted on.
            issue_checkout=EXISTING_CHECKOUT,
            # The round's checkout stands on the head its reviewer approved.
            head_shas=(DEFAULT_PR_HEAD_SHA,),
        )

        prompt = mocks[support.RUN_AGENT].call_args.args[1]
        self.assertNotIn("The human edited the issue", prompt)
        # An approved round routes on for the docs pass, which is the whole
        # proof that the reviewer -- and not the drift resume -- ran.
        self.assertIn(
            (support._ADD_AGENT_RUNS_ISSUE_NUMBER, support.LABEL_DOCUMENTING),
            gh.label_history,
        )

    def test_guidance_beside_the_command_still_drifts(self) -> None:
        # Words beside the command are requirements, and the drift road is how
        # they reach the agent that has to act on them.
        gh, issue = self._parked_and_bought(
            guidance="also handle the empty input case",
        )

        mocks = self._run(
            lambda: _validating._handle_validating(
                gh, support._TEST_SPEC, issue,
            ),
            run_agent=support._agent(
                session_id=support.DEV_SESSION,
                last_message="ACK: covered already",
            ),
            has_new_commits=False,
            dirty_files=(),
            head_shas=[support.SAME_SHA, support.SAME_SHA],
        )

        prompt = mocks[support.RUN_AGENT].call_args.args[1]
        self.assertIn("The human edited the issue", prompt)

    def _parked_and_bought(self, *, guidance: str = ""):
        """A validating issue whose thread carries the operator's command.

        The baseline is the hash of the thread WITHOUT it, which is what the
        stage recorded before the park: the command is written while the issue
        is stopped, and the tick that reads it is the one the handler runs on.
        """
        issue_number = support._ADD_AGENT_RUNS_ISSUE_NUMBER
        issue = support.make_issue(
            issue_number, label=support.LABEL_VALIDATING,
        )
        baseline = _content_hash._compute_user_content_hash(issue, set())
        issue.comments.append(support.FakeComment(
            id=support._ADD_AGENT_RUNS_COMMENT_ID,
            body="\n\n".join(
                part for part in (support.ADD_AGENT_RUNS_COMMAND, guidance)
                if part
            ),
            user=support.FakeUser(support.TRUSTED_AUTHOR),
        ))
        branch = f"orchestrator/chippingway__chipping-orchestrator/issue-{issue_number}"
        gh = support.FakeGitHubClient()
        gh.add_issue(issue)
        gh.add_pr(support.FakePR(
            number=support._ADD_AGENT_RUNS_PR_NUMBER, head_branch=branch,
        ))
        gh.seed_state(
            issue_number,
            pr_number=support._ADD_AGENT_RUNS_PR_NUMBER,
            branch=branch,
            dev_agent=support.BACKEND_CLAUDE,
            dev_session_id=support.DEV_SESSION,
            user_content_hash=baseline,
            agent_run_allowance=support._ADD_AGENT_RUNS_ALLOWANCE,
            agent_runs_used=support._ADD_AGENT_RUNS_SPENT,
            review_round=1,
        )
        return gh, issue


class NoCommitAckDoesNotParkTest(
    unittest.TestCase, support._PatchedWorkflowMixin,
):
    """Reviewer point 4: a harmless clarification edit can elicit a
    no-commit reply from the dev ('existing work satisfies'). The
    validating / in_review / resolving_conflict drift paths must treat
    that as an ack rather than parking awaiting_human."""

    def test_validating_ack_does_not_park(self) -> None:
        gh = support.FakeGitHubClient()
        issue = support.make_issue(
            support._VALIDATING_ACK_ISSUE_NUMBER,
            label=support.LABEL_VALIDATING,
            body=support.CLARIFIED_BODY,
        )
        gh.add_issue(issue)
        pr = support.FakePR(
            number=support._VALIDATING_ACK_PR_NUMBER,
            head_branch="orchestrator/chippingway__chipping-orchestrator/issue-600",
        )
        gh.add_pr(pr)
        gh.seed_state(
            support._VALIDATING_ACK_ISSUE_NUMBER,
            pr_number=pr.number,
            dev_agent=support.BACKEND_CLAUDE,
            dev_session_id=support.DEV_SESSION,
            user_content_hash=support.STALE_HASH,
            review_round=1,
            branch="orchestrator/chippingway__chipping-orchestrator/issue-600",
        )

        self._run(
            lambda: _validating._handle_validating(gh, support._TEST_SPEC, issue),
            run_agent=support._agent(
                session_id=support.DEV_SESSION,
                last_message=(
                    "Reviewed the clarified body.\n\n"
                    "ACK: existing commits already cover the clarified body"
                ),
            ),
            has_new_commits=False,
            dirty_files=(),
            head_shas=[support.SAME_SHA, support.SAME_SHA],
        )

        state = gh.pinned_data(support._VALIDATING_ACK_ISSUE_NUMBER)
        # Crucial: must NOT park as a question.
        self.assertFalse(state.get(support.KEY_AWAITING_HUMAN))
        # Dev's ACK justification was posted on the issue as an FYI.
        self.assertTrue(any(
            support.EXISTING_WORK_MESSAGE in body
            for _, body in gh.posted_comments
        ))

    def test_in_review_ack_routes_to_validating(
        self,
    ) -> None:
        # A no-commit "ack" reply from the dev on an in_review drift
        # MUST bounce DIRECTLY back to `validating` (same destination
        # as the pushed-fix exit; docs do not run on the drift exit,
        # the single docs pass runs after reviewer approval before
        # `in_review` via the final-docs handoff). `review_round`
        # resets so the validating cap counts fresh rounds.
        gh = support.FakeGitHubClient()
        issue = support.make_issue(
            support._IN_REVIEW_ACK_ISSUE_NUMBER,
            label=support.LABEL_IN_REVIEW,
            body=support.CLARIFIED_BODY,
        )
        gh.add_issue(issue)
        pr = support.FakePR(
            number=support._IN_REVIEW_ACK_PR_NUMBER,
            head_branch="orchestrator/chippingway__chipping-orchestrator/issue-700",
        )
        gh.add_pr(pr)
        gh.seed_state(
            support._IN_REVIEW_ACK_ISSUE_NUMBER,
            pr_number=pr.number,
            dev_agent=support.BACKEND_CLAUDE,
            dev_session_id=support.DEV_SESSION,
            user_content_hash=support.STALE_HASH,
            pr_last_comment_id=0,
            pr_last_review_comment_id=0,
            pr_last_review_summary_id=0,
            branch="orchestrator/chippingway__chipping-orchestrator/issue-700",
        )

        self._run(
            lambda: _in_review._handle_in_review(gh, support._TEST_SPEC, issue),
            run_agent=support._agent(
                session_id=support.DEV_SESSION,
                last_message="ACK: no additional code change needed",
            ),
            has_new_commits=False,
            dirty_files=(),
            head_shas=[support.UNCHANGED_SHA, support.UNCHANGED_SHA],
        )

        state = gh.pinned_data(support._IN_REVIEW_ACK_ISSUE_NUMBER)
        # Must NOT park (the dev acknowledged, not asked a question).
        self.assertFalse(state.get(support.KEY_AWAITING_HUMAN))
        # MUST bounce directly to validating (no documenting hop) so
        # the reviewer re-evaluates against the updated body.
        self.assertIn(
            (support._IN_REVIEW_ACK_ISSUE_NUMBER, support.LABEL_VALIDATING),
            gh.label_history,
        )
        # And NOT through documenting -- no commit landed.
        self.assertNotIn(
            (support._IN_REVIEW_ACK_ISSUE_NUMBER, "workflow:documenting"),
            gh.label_history,
        )
        # review_round reset so the validating cap counts fresh rounds.
        self.assertEqual(state.get("review_round"), 0)
        # Dev's reply still posted on the issue as an FYI.
        self.assertTrue(any(
            support.EXISTING_WORK_MESSAGE in body
            for _, body in gh.posted_comments
        ))
