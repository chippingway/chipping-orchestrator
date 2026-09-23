# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import contextlib
import unittest
from typing import NamedTuple
from unittest.mock import MagicMock, patch

from orchestrator.github.labels import PAUSED_LABEL
from orchestrator.workflow.engine import content_hash as _content_hash
from tests.support.fakes import (
    DEFAULT_PR_HEAD_SHA,
    FakeComment,
    FakeGitHubClient,
    FakeLabel,
    FakePR,
    FakeUser,
    make_issue,
)
from tests.workflow.fixtures import (
    AGENT_RUN_CHARGE_KEYS,
    AGENT_RUN_CHARGE_WRITES,
    MEASURED_CANDIDATE_SHA,
    _agent,
    _issue_branch,
    _PatchedWorkflowMixin,
)

# The head this stage reads before the resume and the one it leaves the
# checkout at. The second IS the commit the size gate proves that checkout to,
# because in production the two are one read of one worktree: the route names
# the commit it means to publish and the gate refuses a checkout standing
# anywhere else.
BEFORE_SHA = DEFAULT_PR_HEAD_SHA
RESOLVED_SHA = MEASURED_CANDIDATE_SHA

DRIFT_ISSUE = 500
DRIFT_PR = 5000
INTERRUPTED_ISSUE = 501
INTERRUPTED_PR = 5001
SETTLEMENT_ISSUE = 502
SETTLEMENT_PR = 5002
DEV_SESSION = "dev-sess"
RESOLVING_CONFLICT = "workflow:resolving_conflict"

# The reply a human writes onto the issue thread while the rebase is in
# flight, and where both readers stood before it.
DRIFT_REPLY_ID = 200
READ_THROUGH = 100
DRIFT_REPLY = "rebase onto main and keep the CLI flag as it is"
ACK_REPLY = "ACK: the existing commits already cover it"
QUESTION_REPLY = "which of the two did you mean?"
RUN_AGENT = "run_agent"
LAST_ACTION_COMMENT_ID = "last_action_comment_id"
USER_CONTENT_HASH = "user_content_hash"
STALE_HASH = "stale-hash"

class _Outcome(NamedTuple):
    """One way a body-edit resume can end, and what it records about its
    prompt."""

    described: str
    run: object
    committed: bool
    paused: bool
    settles: bool


# What each outcome does to the record of the prompt it was given, whether the
# resume left a commit behind, and whether an operator paused mid-run.
_SETTLES = (
    _Outcome("a published resolution", _agent(session_id=DEV_SESSION, last_message="rebased"), True, False, True),
    _Outcome("an ACK", _agent(session_id=DEV_SESSION, last_message=ACK_REPLY), False, False, True),
    _Outcome("a question", _agent(session_id=DEV_SESSION, last_message=QUESTION_REPLY), False, False, True),
    _Outcome("a timeout", _agent(session_id=DEV_SESSION, timed_out=True), False, False, True),
    _Outcome("a shutdown kill", _agent(session_id=DEV_SESSION, interrupted=True), False, False, False),
    _Outcome("a live pause", _agent(session_id=DEV_SESSION, last_message="rebased"), True, True, False),
)


def _of_this_tick(pinned: dict) -> dict:
    """One pinned record less the launch ledger no handler owns.

    The agent-run circuit charges a launch durably before any process exists,
    so those fields are on the comment whatever the launch came to. What a
    case about a tick leaving nothing behind is asking about is everything
    else.
    """
    return {
        field: recorded for field, recorded in pinned.items()
        if field not in AGENT_RUN_CHARGE_KEYS
    }


# The launch the run circuit turned away, which every other row is measured
# against: the one outcome whose tick may leave nothing of its own behind.
_REFUSED = _Outcome(
    "a refused launch",
    _agent(session_id=DEV_SESSION, invoked=False),
    False, False, False,
)


def _paused_mid_run(github, paused: bool):
    """The freshly fetched view a live-pause guard reads after a run returns.

    Nothing is patched for an unpaused case, so the guard reads the client the
    tick was given and answers as it does in production.
    """
    if not paused:
        return contextlib.nullcontext()
    view = make_issue(SETTLEMENT_ISSUE, label=RESOLVING_CONFLICT)
    view.labels.append(FakeLabel(PAUSED_LABEL))
    return patch.object(github, "get_issue", MagicMock(return_value=view))


def _seed_drift_case(issue_number: int, pr_number: int):
    github = FakeGitHubClient()
    issue = make_issue(
        issue_number,
        label=RESOLVING_CONFLICT,
        body="updated body",
    )
    github.add_issue(issue)
    github.add_pr(FakePR(number=pr_number, head_branch=_issue_branch(issue_number)))
    github.seed_state(
        issue_number,
        pr_number=pr_number,
        dev_agent="claude",
        dev_session_id=DEV_SESSION,
        conflict_round=0,
        branch=_issue_branch(issue_number),
        user_content_hash="stale-hash",
    )
    return github, issue


def _assert_interrupted_drift_state(test_case, github) -> None:
    state = github.pinned_data(INTERRUPTED_ISSUE)
    test_case.assertEqual(state.get("user_content_hash"), "stale-hash")
    test_case.assertFalse(state.get("awaiting_human"))
    test_case.assertEqual(state.get("conflict_round"), 0)
    test_case.assertNotIn((INTERRUPTED_ISSUE, "workflow:validating"), github.label_history)
    test_case.assertFalse(
        any(
            "agent needs your input" in body or "existing work" in body or "timed out" in body
            for _, body in github.posted_comments
        )
    )


class HandleResolvingConflictHashDriftTest(
    unittest.TestCase,
    _PatchedWorkflowMixin,
):
    """Reviewer point 2: `resolving_conflict` is dispatched per tick too,
    so a body edit while the dev is resolving conflicts must surface to
    the dev. Mirrors the in_review pattern: post a PR notice and resume."""

    def test_drift_posts_pr_notice_and_resumes_dev(self) -> None:
        gh, issue = _seed_drift_case(DRIFT_ISSUE, DRIFT_PR)

        self._run_resolving_conflict(
            gh,
            issue,
            run_agent=_agent(session_id=DEV_SESSION, last_message="resolved with edit"),
            has_new_commits=True,
            dirty_files=(),
            push_branch=True,
            # Two SHAs, and the second is read once: the head the resume
            # produced is what the publication measures, what a hold would
            # name its round by, and what the `conflict_round` audit emit
            # records, so one reading travels to all three.
            head_shas=[BEFORE_SHA, RESOLVED_SHA],
        )

        # Pushed drift fix -> hand straight back to `validating`; the
        # single docs pass is deferred to the post-approval hop.
        self.assertIn((DRIFT_ISSUE, "workflow:validating"), gh.label_history)
        self.assertNotIn((DRIFT_ISSUE, "workflow:documenting"), gh.label_history)
        # Notice posted on the PR.
        self.assertTrue(
            any(
                "issue body changed" in body
                for _, body in gh.posted_pr_comments
            )
        )

    def test_interrupted_resume_keeps_state(self) -> None:
        # The drift resume routes through the shared
        # `_post_user_content_change_result`, which has no interrupted check
        # of its own. The conflicts caller must short-circuit BEFORE it so a
        # shutdown-sweep-killed run cannot ACK / park off partial output and
        # then persist the consumed-comment / refreshed-hash changes.
        gh, issue = _seed_drift_case(INTERRUPTED_ISSUE, INTERRUPTED_PR)
        before_writes = gh.write_state_calls

        mocks = self._run_resolving_conflict(
            gh,
            issue,
            run_agent=_agent(
                session_id=DEV_SESSION,
                last_message="",
                interrupted=True,
            ),
            has_new_commits=True,
            push_branch=True,
            head_shas=[BEFORE_SHA, RESOLVED_SHA],
        )

        # The drift resume spawned, then was seen interrupted.
        mocks["run_agent"].assert_called_once()
        mocks["_push_branch"].assert_not_called()
        # No durable state churn: the refreshed `user_content_hash`,
        # consumed-comment, and session mutations are all discarded.
        self.assertEqual(
            gh.write_state_calls, before_writes + AGENT_RUN_CHARGE_WRITES,
        )
        _assert_interrupted_drift_state(self, gh)


class ResolvingConflictDriftSettlementTest(
    unittest.TestCase,
    _PatchedWorkflowMixin,
):
    """What a finished body-edit resume records about the words it quoted.

    The prompt is frozen with the record of the thread it was cut from, and
    that record is what the requirements revision and the issue-thread cursor
    both come from. Only a run that reached an agent records it: a shutdown
    kill has no trustworthy result, a live pause stops before anything is
    persisted, and a launch the run circuit turned away started no process at
    all -- so each leaves the reply unread and the edit still an edit for
    whoever answers it next.

    This road reads the issue thread and nothing else, so an outcome that does
    record it moves that surface's cursor alone; the park a question or a
    timeout takes walks on from there through this tick's own notices, and
    stops at the first comment nobody has delivered.
    """

    def test_only_a_run_that_read_it_consumes_it(self) -> None:
        # Each case starts on its own edited issue: a notice left behind by
        # the case before would be a second comment for the next prompt.
        for case in _SETTLES:
            with self.subTest(outcome=case.described):
                gh, issue = self._seed()

                self.assertIn(DRIFT_REPLY, self._drifts(gh, issue, case))
                self._assert_recorded(gh, issue, case.settles)

    def test_a_refused_launch_leaves_nothing_durable(self) -> None:
        # The run circuit turns the launch away, so no process ever read the
        # prompt: the refusal it recorded where it was decided is the whole of
        # what this tick may say. Nothing of this road's own reaches the
        # comment -- not the requirements revision, not the reply the prompt
        # quoted -- and no park is taken in the name of a run that never
        # started, since a park would be a durable claim about an answer
        # nobody gave.
        gh, issue = self._seed()
        before = gh.pinned_data(SETTLEMENT_ISSUE)

        quoted = self._drifts(gh, issue, _REFUSED)

        self.assertIn(DRIFT_REPLY, quoted)
        self.assertEqual(
            _of_this_tick(gh.pinned_data(SETTLEMENT_ISSUE)),
            _of_this_tick(before),
        )
        self.assertEqual(gh.posted_comments, [])
        self.assertEqual(gh.label_history, [])

    def _seed(self):
        gh = FakeGitHubClient()
        issue = make_issue(
            SETTLEMENT_ISSUE,
            label=RESOLVING_CONFLICT,
            body="updated body",
            comments=[FakeComment(
                id=DRIFT_REPLY_ID, body=DRIFT_REPLY, user=FakeUser("alice"),
            )],
        )
        gh.add_issue(issue)
        gh.add_pr(FakePR(
            number=SETTLEMENT_PR,
            head_branch=_issue_branch(SETTLEMENT_ISSUE),
        ))
        gh.seed_state(
            issue,
            pr_number=SETTLEMENT_PR,
            dev_agent="claude",
            dev_session_id=DEV_SESSION,
            conflict_round=0,
            branch=_issue_branch(SETTLEMENT_ISSUE),
            **{
                USER_CONTENT_HASH: STALE_HASH,
                LAST_ACTION_COMMENT_ID: READ_THROUGH,
            },
        )
        return gh, issue

    def _drifts(self, gh, issue, case: _Outcome) -> str:
        """Run one whole tick over this edit and hand back its one prompt."""
        with _paused_mid_run(gh, case.paused):
            mocks = self._run_resolving_conflict(
                gh,
                issue,
                run_agent=case.run,
                has_new_commits=case.committed,
                dirty_files=(),
                push_branch=True,
                head_shas=(
                    [BEFORE_SHA, RESOLVED_SHA] if case.committed
                    else [BEFORE_SHA, BEFORE_SHA]
                ),
            )
        mocks[RUN_AGENT].assert_called_once()
        return mocks[RUN_AGENT].call_args.args[1]

    def _assert_recorded(self, gh, issue, settles: bool) -> None:
        """What the issue says it has read, and the revision it says it is at.

        The revision is the whole of what separates a run that read the
        prompt from one that did not, because the park a question or a
        timeout takes walks the thread on from wherever the settlement left
        it -- through this tick's own notices, and no further.
        """
        pinned = gh.pinned_data(SETTLEMENT_ISSUE)
        self.assertEqual(
            pinned.get(USER_CONTENT_HASH),
            _content_hash._compute_user_content_hash(issue, set())
            if settles else STALE_HASH,
        )
        if settles:
            self.assertGreaterEqual(
                pinned.get(LAST_ACTION_COMMENT_ID), DRIFT_REPLY_ID,
            )
        else:
            self.assertEqual(
                pinned.get(LAST_ACTION_COMMENT_ID), READ_THROUGH,
            )


if __name__ == "__main__":
    unittest.main()
