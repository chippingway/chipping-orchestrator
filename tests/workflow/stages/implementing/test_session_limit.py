# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Tests for implementing session limit behavior."""

from __future__ import annotations

import unittest
from types import MappingProxyType
from typing import NamedTuple

from orchestrator.agents import models as _agent_models
from orchestrator.agents.backends import agy as _agy
from orchestrator.workflow.stages.implementing import session_read as _session_read
from tests.support import agy_stream as stream
from tests.workflow.agent_failure_values import WEEKLY_LIMIT_MESSAGE, agy_quota_stop
from tests.workflow.fixtures import EVENT_PARK_AWAITING_HUMAN
from tests.workflow.stages.implementing import retry_test_support as support

DEFAULT_SESSION = support.DEFAULT_SESSION
_agent = support._agent

_QUOTA_ISSUE = 2212
_EXIT_STRUCTURED = 3
_EXIT_TIMED_OUT = -1
_PARK_SESSION_LIMIT = "agent_session_limit"
_AGENT_SILENT = "agent_silent"
_CONTINUE_RETRY = "reply with exactly `/orchestrator continue` to retry"
_QUOTA_NOTICE = "agent stopped because its account quota is exhausted"
_NAMED_RESET = f"The quota resets in {stream.QUOTA_RESET}, counted from when the run stopped."
_NO_RESET = "The failure named no reset interval."
_QUOTA_WORDING = "Individual quota reached"
_EXIT_CODES = "_Agent subprocess exit code:_ {0} · _orchestrator's normalized failure code:_ {1}"
# What the notice says in place of a subprocess return the timeout's kill left
# uncaptured, where the runner's `-1` is a sentinel rather than a return.
_NOT_CAPTURED = "not captured (the run timed out and was killed)"
_UNRESET_QUOTA = f"RESOURCE_EXHAUSTED (code 429): {_QUOTA_WORDING}. Please upgrade your subscription."
_REPORT = support.DONE_MESSAGE
_QUOTA_PROSE = f"Done. The log I was asked about says: {stream.QUOTA_MESSAGE}"
_QUOTA_TERMINAL = stream.terminal(stream.FAILURE, response=_REPORT, error=stream.QUOTA_MESSAGE)
_ACTIVE_TOOL = stream.ToolStream.tool_step(1, state="ACTIVE", args={"CommandLine": "pytest"})
_PROSE_STREAM = f"{stream.step(1, text_delta=_QUOTA_PROSE)}\n{stream.terminal(response=_QUOTA_PROSE)}"
_MALFORMED = "model output was malformed"
_MALFORMED_TERMINAL = stream.terminal(stream.FAILURE, response=None, error=_MALFORMED)
# The pinned park flag, its reason, and the silent-park streak, as a
# retryable silent park and a real question leave them on a fresh issue.
_PARK_KEYS = ("awaiting_human", "park_reason", "silent_park_count")
_SILENT_PARK = (True, _AGENT_SILENT, 1)
_QUESTION_PARK = (True, None, 0)
# A run that committed and left uncommitted work beside its commit.
_DIRTY_COMMIT = MappingProxyType({
    "head_shas": ["before-quota", "after-quota"],
    "has_new_commits": [False, True],
    "dirty_files": ("pending.md",),
    "push_branch": True,
})
# What every other park says, none of which a quota park may claim.
_OTHER_PARK_NOTICES = (
    "agent produced no output",
    "agent needs your input",
    "agent command execution failed",
    "session/usage limit",
)

# Synthetic AGY runs that stopped on the account quota with no publishable
# output, each beside the reset line its park names: the structured stderr
# diagnostic, the plain one on an error terminal, a completed response the
# error terminal after it overrides, an unfinished tool step left beside the
# quota, a quota that named no reset, a cancelled terminal the CLI exited 0
# on -- a quota stop rather than a shutdown -- and a quota stop that also ran
# out the clock with a tool step still open.
_QUOTA_RUNS = (
    ("structured stderr, empty output", _agent_models.SubprocessResult(
        stream.init_event(), stream.quota_structured_stderr(), _EXIT_STRUCTURED, False, False,
    ), _NAMED_RESET),
    ("plain stderr, error terminal", _agent_models.SubprocessResult(
        stream.terminal(stream.FAILURE, response=None, error=stream.QUOTA_MESSAGE),
        stream.QUOTA_PLAIN_STDERR, 0, False, False,
    ), _NAMED_RESET),
    ("completed response, then an error terminal", _agent_models.SubprocessResult(
        f"{stream.step(4, text_delta=_REPORT)}\n{_QUOTA_TERMINAL}", "", 0, False, False,
    ), _NAMED_RESET),
    ("unfinished tool step beside the quota", _agent_models.SubprocessResult(
        f"{_ACTIVE_TOOL}\n{_QUOTA_TERMINAL}", "", 1, False, False,
    ), _NAMED_RESET),
    ("no reset named", _agent_models.SubprocessResult(
        stream.init_event(), stream.quota_structured_stderr(_UNRESET_QUOTA), _EXIT_STRUCTURED, False, False,
    ), _NO_RESET),
    ("cancelled terminal, exit 0", _agent_models.SubprocessResult(
        stream.terminal("CANCELED", response=None, error=stream.QUOTA_MESSAGE), "", 0, False, False,
    ), _NAMED_RESET),
    ("timed out beside an unfinished tool step", _agent_models.SubprocessResult(
        f"{_ACTIVE_TOOL}\n{_QUOTA_TERMINAL}", "", _EXIT_TIMED_OUT, True, False,
    ), _NAMED_RESET),
)


class _Park(NamedTuple):
    """The notice a park posted, its events' reasons and exit codes, and the pinned park."""

    notice: str
    events: list[tuple[str, int]]
    pinned: tuple


def _normalized(stdout: str, stderr: str = "", exit_code: int = 0) -> _agent_models.AgentResult:
    """A synthetic AGY run, normalized the way the backend hands it to a stage."""
    process_result = _agent_models.SubprocessResult(stdout, stderr, exit_code, False, False)
    return _agy.agy_result(_agent_models.AgentRunOptions(), process_result)


class SessionLimitMessageClassifierTest(unittest.TestCase):
    """A session/usage/weekly-quota notice returned as the CLI's FINAL message
    is a retryable session-failure, not a real agent question. `_on_question`
    keys the retryable `agent_silent` park off `_is_session_limit`, so
    the classifier must accept the known phrasings (including a curly
    apostrophe) as a prefix while ignoring a plain question or a mid-answer
    mention.
    """

    def test_matches_known_session_limit_phrasings(self) -> None:
        for last_message in (
            # The #705 shape, verbatim.
            "You've hit your session limit · resets 7pm (Asia/Novosibirsk)",
            # Curly apostrophe still hits (normalized before matching).
            "You’ve hit your session limit · resets 7pm",
            "You've reached your usage limit for now",
            WEEKLY_LIMIT_MESSAGE,
            "You’ve hit your weekly limit · resets Sep 25, 12pm",
            "You've reached your weekly limit for now",
            "You’ve reached your weekly limit",
            "Claude AI usage limit reached|1712345678",
            # Mixed casing / leading whitespace still trip the prefix match.
            "  CLAUDE USAGE LIMIT REACHED",
        ):
            with self.subTest(last_message=last_message):
                agent_result = _agent(session_id=DEFAULT_SESSION, last_message=last_message)
                self.assertTrue(
                    _session_read._is_session_limit(agent_result),
                    f"{last_message!r} should classify as a session limit",
                )

    def test_ignores_question_and_midanswer_mention(self) -> None:
        for last_message in (
            "",
            "Should I prefer ruff or black for this?",
            # A dev discussing the concept mid-answer must not be caught --
            # the marker is matched as a prefix, not anywhere in the body.
            "I added a note about the session limit handling in fixing.py.",
            # Quoting the weekly notice whole, mid-answer, is still an answer.
            "Done: the classifier now parks \"You've hit your weekly limit\" retryably.",
        ):
            with self.subTest(last_message=last_message):
                agent_result = _agent(session_id=DEFAULT_SESSION, last_message=last_message)
                self.assertFalse(
                    _session_read._is_session_limit(agent_result),
                    f"{last_message!r} must not classify as a session limit",
                )


class AntigravityQuotaParkTest(unittest.TestCase, support._PatchedWorkflowMixin):
    """Synthetic AGY streams, normalized by the backend and parked by the
    implementing handler on a run that left no commit. The quota verdict the
    failure record carries is what routes the park, never the final message.
    """

    def test_quota_takes_the_session_limit_park(self) -> None:
        for name, process_result, reset_line in _QUOTA_RUNS:
            with self.subTest(run=name):
                self._assert_quota_park(process_result, reset_line)

    def test_successful_quota_prose_stays_an_answer(self) -> None:
        park = self._park(_normalized(_PROSE_STREAM))
        self.assertEqual(park.events, [("agent_question", 0)])
        self.assertEqual(park.pinned, _QUESTION_PARK)
        self.assertIn(f"> {_QUOTA_PROSE}", park.notice)
        self.assertNotIn(_QUOTA_NOTICE, park.notice)

    def test_quota_commit_over_dirty_tree_parks(self) -> None:
        # A quota stop's commit publishes only over a tree provably clean:
        # over a dirty one the publication seam's dirty-tree park would pin no
        # retryable reason and refuse the bare continue, so it parks as the
        # session limit instead, timed out or not, with nothing pushed.
        for timed_out in (True, False):
            with self.subTest(timed_out=timed_out), self.assertLogs("orchestrator.workflow", level="WARNING"):
                park = self._park(agy_quota_stop(timed_out=timed_out), **_DIRTY_COMMIT)
                self.assertEqual([reason for reason, _ in park.events], [_PARK_SESSION_LIMIT])
                self.assertEqual(park.pinned, _SILENT_PARK)

    def test_unrelated_failure_keeps_the_silent_park(self) -> None:
        with self.assertLogs("orchestrator.workflow", level="WARNING"):
            park = self._park(_normalized(_MALFORMED_TERMINAL, f"error: {_MALFORMED}"))
        self.assertEqual(park.events, [(_AGENT_SILENT, 1)])
        self.assertEqual(park.pinned, _SILENT_PARK)
        self.assertIn("agent produced no output", park.notice)
        self.assertNotIn(_QUOTA_NOTICE, park.notice)
        self.assertIn(_EXIT_CODES.format(0, 1), park.notice)

    def _assert_quota_park(self, process_result: _agent_models.SubprocessResult, reset_line: str) -> None:
        agent_result = _agy.agy_result(_agent_models.AgentRunOptions(), process_result)
        captured = None if process_result.timed_out else process_result.exit_code
        with self.assertLogs("orchestrator.workflow", level="WARNING") as logs:
            park = self._park(agent_result)
            warning = logs.output[-1]
        # The event keeps the normalized code it always carried.
        self.assertEqual(park.events, [(_PARK_SESSION_LIMIT, agent_result.exit_code)])
        self.assertEqual(park.pinned, _SILENT_PARK)
        self.assertIn(f"{_QUOTA_NOTICE};", park.notice)
        self.assertIn(_CONTINUE_RETRY, park.notice)
        self.assertIn(f"\n\n{reset_line}\n\n_Agent stderr (last 1KB):_", park.notice)
        self.assertIn(_QUOTA_WORDING, park.notice)
        self.assertIn(
            _EXIT_CODES.format(_NOT_CAPTURED if captured is None else captured, agent_result.exit_code), park.notice,
        )
        self.assertFalse([said for said in _OTHER_PARK_NOTICES if said in park.notice])
        self.assertIn(f"process_exit_code={captured} exit_code={agent_result.exit_code}", warning)

    def _park(self, agent_result: _agent_models.AgentResult, **run_options) -> _Park:
        """What one implementing tick left over `agent_result`, with no commit unless `run_options` say otherwise."""
        github = support.FakeGitHubClient()
        issue = support.make_issue(_QUOTA_ISSUE, label=support.LABEL_IMPLEMENTING)
        github.add_issue(issue)
        self._run_implementing(github, issue, run_agent=agent_result, **{"has_new_commits": False, **run_options})
        state = github.pinned_data(_QUOTA_ISSUE)
        return _Park(
            notice=github.posted_comments[-1][1],
            events=[
                (record["reason"], record["exit_code"])
                for record in github.recorded_events
                if record["event"] == EVENT_PARK_AWAITING_HUMAN
            ],
            pinned=tuple(map(state.get, _PARK_KEYS)),
        )
