# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""A Codex reviewer its account's usage limit stopped: the park it takes, and what answers it."""

from __future__ import annotations

import copy
import signal
import unittest
from operator import itemgetter
from unittest.mock import MagicMock, patch

from orchestrator import config
from orchestrator.agents import processes as _agent_processes, runner as _agent_runner
from tests.agents import agent_test_support as _agent_support, codex_stream_cases as _streams
from tests.workflow.stages.validating import validating_review_test_support as review_support

ISSUE = review_support.FRESH_REVIEW_ISSUE
PR = review_support.FRESH_REVIEW_PR
CONTINUE_ID = 1400
TRUSTED_LOGIN = "geserdugarov"
CODEX = "codex"
RUN_AGENT = review_support.RUN_AGENT
ROLE_REVIEWER = review_support.ROLE_REVIEWER
AWAITING_HUMAN = review_support.AWAITING_HUMAN
REVIEW_ROUND = review_support.REVIEW_ROUND
PR_NUMBER = review_support.PR_NUMBER
PARK_REASON = "park_reason"
AGENT_RUNS_USED = "agent_runs_used"
EVENT_NAME = "event"
PARK_EVENT = "park_awaiting_human"
REASON_FIELD = "reason"
USAGE_LIMIT = "reviewer_usage_limit"
# The flags a usage-limit park sets, beside the one launch it charged, and
# what it leaves as it found it.
PARKED = (True, USAGE_LIMIT, 1)
KEPT_FIELDS = (REVIEW_ROUND, PR_NUMBER, "branch", "codex_session_id")
NOTICE_HEADLINE = "Codex usage limit"
# The session the captured stream's `thread.started` names.
CAPTURED_SESSION = "01a12719-eef4-7330-b188-a4ccd5feef66"

# What the park's notice has to say -- the limit, the reset the provider gave,
# the command that retries the reviewer, and the provider's own words -- and
# what it must not, since nobody has a missing verdict to adjudicate.
NOTICE_SAYS = (
    NOTICE_HEADLINE,
    _streams.CAPTURED_RESET,
    "trusted `/orchestrator continue` retries the reviewer",
    f"> {_streams.CAPTURED_LIMIT_MESSAGE}",
)
NOTICE_OMITS = ("did not emit a VERDICT line", "manual adjudication")

# A park event's reason and the correlation it carries.
_PARK_CORRELATION = itemgetter(REASON_FIELD, "agent_role", "session_id", REVIEW_ROUND, PR_NUMBER)

# A review that completed and wrote about the limit rather than ran into it.
LIMIT_MENTION = f"The retry path now reports this provider refusal: {_streams.ROLLOUT_LIMIT_MESSAGE}"
_MENTION_EVENTS = (_streams.turn_started(), _streams.agent_message(LIMIT_MENTION), _streams.turn_completed())
COMPLETED_MENTION_STDOUT = _streams.codex_jsonl(*_MENTION_EVENTS)
_DISCONNECTED = _streams.turn_failed("stream disconnected before completion")
DISCONNECTED_STDOUT = _streams.codex_jsonl(_streams.turn_started(), _DISCONNECTED)

# `(run, park event reason, park_reason kept)`: a review that completed and
# only quoted the limit is the reviewer's text for a human, a Codex turn that
# failed on anything else is a crash the next tick retries, and a timeout is a
# timeout whatever its stream ended on.
NOT_LIMIT_STOPS = (
    (
        review_support._agent(last_message=LIMIT_MENTION, stdout=COMPLETED_MENTION_STDOUT, exit_code=0),
        "reviewer_no_verdict",
        None,
    ),
    (
        review_support._agent(last_message="", stdout=DISCONNECTED_STDOUT, exit_code=1),
        "reviewer_failed",
        "reviewer_failed",
    ),
    (
        review_support._agent(timed_out=True, stdout=_streams.CAPTURED_LIMIT_STDOUT),
        "reviewer_timeout",
        "reviewer_timeout",
    ),
)

# The dispatch the agent seam stands in for, read before any test patches it.
_DISPATCH = _agent_runner.run_agent


class _CodexCli:
    """The real Codex backend, run over a CLI that printed `stdout` and exited `returncode`.

    The stand-in CLI writes nothing to the `-o` file the backend reads its
    final message from, as a turn the usage limit failed leaves it, so the
    result is the backend's own: an empty message beside that stream.
    """

    def __init__(self, stdout: str, returncode: int) -> None:
        self._stdout = stdout
        self._returncode = returncode

    def __call__(self, backend, prompt, cwd, **options):
        exited = _agent_support.completed(stdout=self._stdout, returncode=self._returncode)
        with patch.object(_agent_processes.subprocess, "Popen", return_value=exited):
            return _DISPATCH(backend, prompt, cwd, **options)


def _events(github, name: str) -> list[dict]:
    """The `name` events the ticks so far recorded, in order."""
    return [event for event in github.recorded_events if event[EVENT_NAME] == name]


class _CodexReviewTicks(review_support.FreshReviewFixtureMixin):
    def _ticks(self, github, issue, **run_options):
        """One validating tick under a Codex reviewer, the author allowlist on.

        A reviewer run the case names nothing else for is the captured Codex
        CLI stopping on the limit.
        """
        run_options.setdefault(
            RUN_AGENT, MagicMock(side_effect=_CodexCli(_streams.CAPTURED_LIMIT_STDOUT, returncode=1)),
        )
        with (
            patch.object(config, "REVIEW_AGENT", CODEX),
            patch.object(config, "ALLOWED_ISSUE_AUTHORS", (TRUSTED_LOGIN,)),
        ):
            return self._run_validating(github, issue, **run_options)

    def _pinned(self, github, *fields: str) -> tuple:
        """The issue's pinned `fields`, in order."""
        pinned = github.pinned_data(ISSUE)
        return tuple(pinned.get(field) for field in fields)

    def _park_reasons(self, github) -> list:
        return [event[REASON_FIELD] for event in _events(github, PARK_EVENT)]


class ReviewerUsageLimitJourneyTest(unittest.TestCase, _CodexReviewTicks):
    """A Codex reviewer the usage limit stopped parks until a trusted continue buys a fresh one."""

    def test_limit_parks_until_a_trusted_continue(self) -> None:
        github, issue = self._seeded()
        self._assert_parked(github, issue)
        # Another poll is no evidence the quota reset.
        self._assert_held(github, issue)
        self._assert_bought_reviewer(github, issue)
        # The bought reviewer read the command, so it buys nothing again.
        self._assert_held(github, issue)

    def _assert_parked(self, github, issue) -> None:
        """One tick whose reviewer stops on the limit: one launch, the round, PR, and worktree kept."""
        kept = self._pinned(github, *KEPT_FIELDS)
        mocks = self._ticks(github, issue)
        mocks[RUN_AGENT].assert_called_once()
        mocks["_cleanup_terminal_branch"].assert_not_called()
        self.assertEqual(self._pinned(github, AWAITING_HUMAN, PARK_REASON, AGENT_RUNS_USED), PARKED)
        self.assertEqual(self._pinned(github, *KEPT_FIELDS), kept)
        self.assertEqual(github.pulls[PR].state, "open")
        self.assertEqual(github.label_history, [])
        self._assert_notice(github)

    def _assert_notice(self, github) -> None:
        """The park's one notice, its event's reason and correlation, and no verdict reported."""
        self.assertEqual(len(github.posted_comments), 1)
        notice = github.posted_comments[0][1]
        for said in NOTICE_SAYS:
            self.assertIn(said, notice)
        for omitted in NOTICE_OMITS:
            self.assertNotIn(omitted, notice)
        self.assertEqual(
            [_PARK_CORRELATION(event) for event in _events(github, PARK_EVENT)],
            [(USAGE_LIMIT, ROLE_REVIEWER, CAPTURED_SESSION, 0, PR)],
        )
        self.assertEqual(_events(github, "review_verdict"), [])

    def _assert_held(self, github, issue) -> None:
        """A poll over the park, which runs, announces, posts, and writes nothing."""
        parked = copy.deepcopy(github.pinned_data(ISSUE))
        footprint = (github.write_state_calls, len(github.posted_comments))
        self._ticks(github, issue)[RUN_AGENT].assert_not_called()
        self.assertEqual(github.pinned_data(ISSUE), parked)
        self.assertEqual((github.write_state_calls, len(github.posted_comments)), footprint)

    def _assert_bought_reviewer(self, github, issue) -> None:
        """The operator's continue buys one fresh reviewer, no developer; that one stops on the limit too."""
        issue.comments.append(
            review_support.FakeComment(
                id=CONTINUE_ID, body="/orchestrator continue", user=review_support.FakeUser(TRUSTED_LOGIN),
            ),
        )
        bought = self._ticks(github, issue)[RUN_AGENT]
        bought.assert_called_once()
        self.assertEqual(bought.call_args.args[0], CODEX)
        self.assertIsNone(bought.call_args.kwargs.get("resume_session_id"))
        self.assertEqual(
            [event.get("agent_role") for event in _events(github, "agent_spawn")], [ROLE_REVIEWER, ROLE_REVIEWER],
        )
        self.assertEqual(
            self._pinned(github, PARK_REASON, AGENT_RUNS_USED, REVIEW_ROUND, "codex_session_id"),
            (USAGE_LIMIT, 2, 0, review_support.DEV_SESSION),
        )
        self.assertGreaterEqual(github.pinned_data(ISSUE)["last_action_comment_id"], CONTINUE_ID)
        self.assertEqual(self._park_reasons(github), [USAGE_LIMIT, USAGE_LIMIT])


class ReviewerUsageLimitScopeTest(unittest.TestCase, _CodexReviewTicks):
    """Only a reviewer run that ended on the limit parks on it, behind the timeout and interruption guards."""

    def test_only_a_run_ended_on_the_limit_parks(self) -> None:
        for agent_result, event_reason, kept in NOT_LIMIT_STOPS:
            with self.subTest(event_reason=event_reason):
                github, issue = self._seeded()
                self._ticks(github, issue, run_agent=agent_result)
                self.assertEqual(self._park_reasons(github), [event_reason])
                self.assertEqual(self._pinned(github, PARK_REASON), (kept,))
                self.assertNotIn(NOTICE_HEADLINE, github.posted_comments[-1][1])

    def test_quoted_limit_does_not_hold_an_approval(self) -> None:
        # A completed review approving the head while it quotes the provider's
        # limit is an approval like any other.
        github, issue = self._seeded()
        approval = review_support._agent(
            last_message=f"{LIMIT_MENTION}\n\n{review_support.REVIEW_APPROVED_MESSAGE}",
            stdout=COMPLETED_MENTION_STDOUT,
        )
        self._ticks(github, issue, run_agent=approval, head_shas=(review_support.BEFORE_FIX_SHA,))
        self.assertEqual(_events(github, PARK_EVENT), [])
        self.assertIn((ISSUE, review_support.LABEL_DOCUMENTING), github.label_history)

    def test_interrupted_limit_run_writes_nothing(self) -> None:
        # A reviewer the shutdown sweep killed is answered ahead of the limit
        # its stream ended on: no park, no notice, and no flags written.
        github, issue = self._seeded()
        killed = review_support._agent(
            interrupted=True, exit_code=-signal.SIGTERM, stdout=_streams.CAPTURED_LIMIT_STDOUT,
        )
        self._ticks(github, issue, run_agent=killed)
        self.assertEqual((_events(github, PARK_EVENT), github.posted_comments), ([], []))
        self.assertEqual(self._pinned(github, AWAITING_HUMAN), (None,))


if __name__ == "__main__":
    unittest.main()
