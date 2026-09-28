# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import unittest
from functools import partial
from types import SimpleNamespace
from unittest.mock import patch

from orchestrator import config
from orchestrator.config.environment import parse_verify_commands
from orchestrator.git.verification.models import VerifyResult
from tests.workflow.fixtures import (
    LABEL_DOCUMENTING,
    LABEL_IN_REVIEW,
    REVIEW_APPROVED_MESSAGE,
    _agent,
)
from tests.workflow.stages.validating import (
    disposed_verdict_test_support as _disposed,
    review_verdict_test_support as _world,
    validating_verify_test_support as verify_support,
)

ISSUE = 7
VERIFY_PYTEST = "pytest -q"
VERIFY_SLOW = "pytest --slow"
VERIFY_FAILED = "failed"
VERIFY_TIMEOUT = "timeout"
VERIFY_OK = "ok"
PARK_VERIFY_FAILED = "verify_failed"
PARK_VERIFY_TIMEOUT = "verify_timeout"
VERIFY_TIMEOUT_SECONDS = 123
CURRENT_TIMEOUT_SECONDS = 600
RUN_VERIFY_COMMANDS = "_run_verify_commands"
AWAITING_HUMAN = "awaiting_human"
PARK_REASON = "park_reason"
VERIFY_COMMANDS_SETTING = "VERIFY_COMMANDS"
REVIEW_SHA = "rev-sha"
# The reviewer session a round ran, where the pinned comment records it, the
# lifetime count of agent runs charged on the issue, and the pull-request post
# an approval announces itself with.
REVIEWER_SESSION = "rev-sess"
LAST_REVIEW_SESSION = "last_review_session_id"
AGENT_RUNS_USED = "agent_runs_used"
ISSUE_AGENT_RUNS = "issue_agent_runs"
PR_COMMENT = "pr_comment"
APPROVAL_NOTICE = "review approved"

# Each verify gate another road runs an agent during, and what it leaves: the
# park reason and reviewer session recorded, and the runs charged and folded
# into the usage totals beside every relabel. A passing gate has another run
# behind its approval comment as well.
_RUN_AROUND_THE_GATE = (
    (
        VerifyResult(status=VERIFY_OK),
        ((None, REVIEWER_SESSION), (3, 3, [(ISSUE, LABEL_DOCUMENTING)])),
    ),
    (
        VerifyResult(status=VERIFY_FAILED, command=VERIFY_PYTEST, exit_code=1),
        ((PARK_VERIFY_FAILED, REVIEWER_SESSION), (2, 2, [])),
    ),
)


def _runs_an_agent(case) -> None:
    """Another road's agent run on `case`'s issue: the lifetime charge it took, and the usage it folded."""
    state = case.github.read_pinned_state(case.issue)
    state.set(AGENT_RUNS_USED, state.get(AGENT_RUNS_USED) + 1)
    state.set(ISSUE_AGENT_RUNS, (state.get(ISSUE_AGENT_RUNS) or 0) + 1)
    case.github.write_pinned_state(case.issue, state)


def _charged_gate(case, verified: VerifyResult, *_args) -> VerifyResult:
    """A verify gate answering `verified`, while another road runs an agent on `case`'s issue."""
    _runs_an_agent(case)
    return verified


def _left(github) -> tuple:
    """The park and reviewer session the comment records, and the runs charged and folded beside every relabel."""
    pinned = github.pinned_data(ISSUE)
    return (
        (pinned.get(PARK_REASON), pinned.get(LAST_REVIEW_SESSION)),
        (pinned.get(AGENT_RUNS_USED), pinned.get(ISSUE_AGENT_RUNS), github.label_history),
    )


class HandleValidatingVerifyGateTest(
    unittest.TestCase,
    verify_support.VerifyGateFixtureMixin,
):
    """Run verification only after an approved review verdict."""

    def test_empty_default_is_noop_on_approval(self) -> None:
        # With no `VERIFY_COMMANDS` configured, the gate short-circuits
        # to not_run inside the runner; the helper is still called once (so a
        # future config flip toggles the gate without code changes), but
        # the approval / squash / in_review handoff path is unchanged.
        gh, issue = self._seeded()
        mocks = self._run_validating(
            gh,
            issue,
            run_agent=_agent(last_message=REVIEW_APPROVED_MESSAGE),
            head_shas=(REVIEW_SHA,),
        )

        self.assertEqual(mocks[RUN_VERIFY_COMMANDS].call_count, 1)
        # The configured commands tuple was forwarded verbatim --
        # default-empty means the runner sees ().
        call = mocks[RUN_VERIFY_COMMANDS].call_args
        self.assertEqual(call.args[1], config.VERIFY_COMMANDS)
        self.assertEqual(config.VERIFY_COMMANDS, ())
        # The timeout is part of the configuration the result's context
        # revision is minted from, so it is forwarded verbatim too.
        self.assertEqual(call.args[2], config.VERIFY_TIMEOUT)
        # Handoff completed normally through the final-docs hop.
        self.assertIn((ISSUE, LABEL_DOCUMENTING), gh.label_history)
        state = gh.pinned_data(ISSUE)
        self.assertFalse(state.get(AWAITING_HUMAN))
        self.assertIsNone(state.get(PARK_REASON))

    def test_config_parses_two_command_separators(self) -> None:
        # `parse_verify_commands` accepts both `;` and `\n` separators so
        # the value fits on one line in a `.env` file. Blank lines and
        # `#`-commented lines are skipped.

        self.assertEqual(parse_verify_commands(""), ())
        self.assertEqual(
            parse_verify_commands(f"{VERIFY_PYTEST};ruff check ."),
            (VERIFY_PYTEST, "ruff check ."),
        )
        self.assertEqual(
            parse_verify_commands(f"{VERIFY_PYTEST}\nruff check .\n"),
            (VERIFY_PYTEST, "ruff check ."),
        )
        self.assertEqual(
            parse_verify_commands(f"\n#comment\n{VERIFY_PYTEST}\n\n"),
            (VERIFY_PYTEST,),
        )

    def test_verify_success_keeps_approval_flow(self) -> None:
        gh, issue = self._seeded()
        with patch.object(config, VERIFY_COMMANDS_SETTING, (VERIFY_PYTEST,)):
            mocks = self._run_validating(
                gh,
                issue,
                run_agent=_agent(last_message=REVIEW_APPROVED_MESSAGE),
                head_shas=(REVIEW_SHA,),
                verify_result=VerifyResult(status=VERIFY_OK),
            )

        mocks[RUN_VERIFY_COMMANDS].assert_called_once()
        # Approval comment posted; label flipped to `documenting` (the
        # final-docs hop).
        self.assertTrue(
            any(
                ":white_check_mark:" in body
                for _, body in gh.posted_pr_comments
            )
        )
        self.assertIn((ISSUE, LABEL_DOCUMENTING), gh.label_history)
        state = gh.pinned_data(ISSUE)
        self.assertFalse(state.get(AWAITING_HUMAN))

    def test_verify_failed_parks(self) -> None:
        gh, issue = self._seeded()
        with patch.object(config, VERIFY_COMMANDS_SETTING, (VERIFY_PYTEST,)):
            self._run_validating(
                gh,
                issue,
                run_agent=_agent(last_message=REVIEW_APPROVED_MESSAGE),
                head_shas=(REVIEW_SHA,),
                verify_result=VerifyResult(
                    status=VERIFY_FAILED,
                    command=VERIFY_PYTEST,
                    exit_code=2,
                    output="E   AssertionError: bad\nTAIL_MARKER",
                ),
            )

        state = gh.pinned_data(ISSUE)
        self.assertTrue(state.get(AWAITING_HUMAN))
        self.assertEqual(state.get(PARK_REASON), PARK_VERIFY_FAILED)
        # No in_review or documenting handoff -- the verify gate fires
        # BEFORE the approval / squash / final-docs route is reached.
        self.assertNotIn((ISSUE, LABEL_IN_REVIEW), gh.label_history)
        self.assertNotIn((ISSUE, LABEL_DOCUMENTING), gh.label_history)
        # No approval comment (gate fires BEFORE the approval post).
        self.assertFalse(
            any(
                ":white_check_mark:" in body
                for _, body in gh.posted_pr_comments
            )
        )
        self._assert_failed_comment(gh.posted_comments[-1][1])

    def test_verify_timeout_parks(self) -> None:
        # The park names the cap the run was killed under, not whatever the
        # setting reads by the time the comment is written.
        gh, issue = self._seeded()
        run = VerifyResult(
            status=VERIFY_TIMEOUT,
            command=VERIFY_SLOW,
            exit_code=None,
            output="hanging...",
            timeout=VERIFY_TIMEOUT_SECONDS,
        )
        with (
            patch.object(config, VERIFY_COMMANDS_SETTING, (VERIFY_SLOW,)),
            patch.object(config, "VERIFY_TIMEOUT", CURRENT_TIMEOUT_SECONDS),
        ):
            self._run_validating(
                gh,
                issue,
                run_agent=_agent(last_message=REVIEW_APPROVED_MESSAGE),
                head_shas=(REVIEW_SHA,),
                verify_result=run,
            )

        state = gh.pinned_data(ISSUE)
        self.assertTrue(state.get(AWAITING_HUMAN))
        self.assertEqual(state.get(PARK_REASON), PARK_VERIFY_TIMEOUT)
        self.assertNotIn((ISSUE, LABEL_IN_REVIEW), gh.label_history)
        self.assertNotIn((ISSUE, LABEL_DOCUMENTING), gh.label_history)
        last_comment = gh.posted_comments[-1][1]
        self.assertIn(VERIFY_SLOW, last_comment)
        self.assertIn("timed out after 123s", last_comment)
        self.assertNotIn(f"{CURRENT_TIMEOUT_SECONDS}s", last_comment)

    def test_runs_around_the_gate_are_kept(self) -> None:
        # Another road runs an agent while the gate runs, and -- where the
        # gate passes -- another behind the approval comment. The reviewer
        # round's own charge is part of the comment every later write is
        # measured against, so each charge is kept rather than written back
        # over by the count this round's charge left; and each run's usage is
        # added to the round's own, which both folded into the same totals. The
        # approval reaches `documenting`, and a failed gate's park lands with
        # the round's own record -- the reviewer session that approved.
        for verified, expected in _RUN_AROUND_THE_GATE:
            with self.subTest(verified.status):
                github, issue = self._seeded()
                world = SimpleNamespace(github=github, issue=issue)
                with (
                    patch.object(config, VERIFY_COMMANDS_SETTING, (VERIFY_PYTEST,)),
                    patch.object(github, PR_COMMENT, _world.AnotherRoadBehind(
                        world, PR_COMMENT, _disposed.saying(APPROVAL_NOTICE), _runs_an_agent,
                    )),
                ):
                    self._run_validating(
                        github,
                        issue,
                        run_agent=_agent(session_id=REVIEWER_SESSION, last_message=REVIEW_APPROVED_MESSAGE),
                        head_shas=(REVIEW_SHA,),
                        verify_result=partial(_charged_gate, world, verified),
                    )

                self.assertEqual(_left(github), expected)

    def _assert_failed_comment(self, comment: str) -> None:
        self.assertIn("local verification failed", comment)
        self.assertIn(VERIFY_PYTEST, comment)
        self.assertIn("exited with code 2", comment)
        self.assertIn("TAIL_MARKER", comment)
