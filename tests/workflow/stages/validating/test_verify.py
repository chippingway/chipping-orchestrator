# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

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
# The pinned pull-request pointer, and a pull request another road points the
# issue at while the gate runs.
PR_POINTER = "pr_number"
OTHER_PR = 9_999
# A gate that failed, as the verification road reports it.
FAILED_RUN = VerifyResult(status=VERIFY_FAILED, command=VERIFY_PYTEST, exit_code=2, output="1 failed")


def _repoints(gh, issue) -> None:
    """Another road's write pointing `issue` at another pull request."""
    state = gh.read_pinned_state(issue)
    state.set(PR_POINTER, OTHER_PR)
    gh.write_pinned_state(issue, state)


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

    def test_a_repointed_failure_parks_nothing(self) -> None:
        # The gate fails while the issue is pointed at another pull request:
        # the result is about a pull request nobody reviews any more, so no
        # failure notice is posted and no park taken -- the run is recorded
        # over what moved, and the pointer kept as the other road left it.
        gh, issue = self._seeded()
        posted = len(gh.posted_comments)
        with patch.object(config, VERIFY_COMMANDS_SETTING, (VERIFY_PYTEST,)):
            self._run_validating(
                gh,
                issue,
                run_agent=_agent(last_message=REVIEW_APPROVED_MESSAGE),
                head_shas=(REVIEW_SHA,),
                verify_result=MagicMock(side_effect=lambda *_run: _repoints(gh, issue) or FAILED_RUN),
            )

        state = gh.pinned_data(ISSUE)
        parked = (bool(state.get(AWAITING_HUMAN)), state.get(PARK_REASON))
        self.assertEqual(parked, (False, None))
        self.assertEqual(
            (state[PR_POINTER], len(gh.posted_comments)), (OTHER_PR, posted),
        )
        self.assertNotIn((ISSUE, LABEL_DOCUMENTING), gh.label_history)

    def _assert_failed_comment(self, comment: str) -> None:
        self.assertIn("local verification failed", comment)
        self.assertIn(VERIFY_PYTEST, comment)
        self.assertIn("exited with code 2", comment)
        self.assertIn("TAIL_MARKER", comment)
