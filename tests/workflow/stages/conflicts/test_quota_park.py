# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""A body edit's resume an account quota stopped after it committed, on the rebase stage's report road."""

from __future__ import annotations

import unittest

from orchestrator.workflow.engine import report_delivery as _report_delivery
from tests.workflow import agent_failure_values as agent_failures, drift_reports as world
from tests.workflow.session_limit_parks import assert_session_limit_park
from tests.workflow.stages.conflicts import drift_report_support as conflict

RUN_AGENT = "run_agent"
PUSH_BRANCH = "_push_branch"
CONTINUE = "/orchestrator continue"
# The debt the missing-report park records: a report owed, and the work it
# would describe marked as described by nothing yet.
OWED = _report_delivery.OWED_REPORT
DEBT = (OWED, _report_delivery.UNREPORTED_WORK)


class ResolvingConflictQuotaReportTest(unittest.TestCase, conflict._ConflictDriftReportMixin):
    """The missing-report park's debt, under the session limit a quota stop takes."""

    def test_quota_stop_over_a_commit_owes_report(self) -> None:
        # The run committed and the account quota stopped it before it could
        # report. Nothing is pushed or recorded, and the debt the missing-report
        # park would record stands -- the report owed, the commit undescribed --
        # but the park is the session limit, so the bare continue after the
        # reset resumes the developer, and the report it writes is what goes
        # out and pays the debt.
        self.seeded_on_conflict()
        with self.assertLogs("orchestrator.workflow", level="WARNING"):
            self.drift(agent_failures.agy_quota_stop(), committed=True)[PUSH_BRANCH].assert_not_called()

        assert_session_limit_park(self, self.github, conflict.ISSUE)
        self.assertEqual(self._debt(), [True, True])
        self.assertEqual(self.published_reports(), [])
        world.human_reply(self, CONTINUE)

        self.drift(world.reported(), committed=False)[RUN_AGENT].assert_called_once()

        self.assertIsNone(self.pinned().get(OWED))
        self.assertEqual(len(self.published_reports()), 1)

    def _debt(self) -> list:
        """The debt flags as the pinned comment carries them."""
        pinned = self.pinned()
        return [pinned.get(flag) for flag in DEBT]
