# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The reply a report-owed conflict park is resumed on, through the dispatcher.

A body edit's resume on `workflow:resolving_conflict` committed and wrote no
report, so the issue parks for one. A human answers with an instruction and a
long reply behind it, longer between them than the excerpt a drift prompt
quotes. The reply's run is resumed on the frozen drift prompt with every reply
whole, and the replies are marked read by what that prompt's record delivered
once the run is back -- so the instruction reaches the developer rather than
being marked read unseen, and the report the run writes goes out once for the
commit.
"""
from __future__ import annotations

import unittest
from functools import partial

from orchestrator.workflow.engine import (
    issue_processing as _issue_processing,
    prompt_context as _prompt_context,
)
from tests.workflow import drift_reports as _drift_world
from tests.workflow.fixtures import _TEST_SPEC
from tests.workflow.stages.conflicts import drift_report_support as _conflict

# A developer that finished, committed, and wrote no report at all.
UNREPORTED_REPLY = "rebased onto main and folded in the new criterion"

# The instruction a human answers the park with, and the background behind it,
# which alone fills the excerpt a drift prompt is bounded to.
INSTRUCTION = "Also cover the second criterion before anything else."

BACKGROUND = "background "

LONG_REPLY = BACKGROUND * (_prompt_context._EXCERPT_CHARS // len(BACKGROUND) + 1)


class ReportOwedReplyHandoffTest(unittest.TestCase, _conflict._ConflictDriftReportMixin):
    """Every reply to a report-owed park reaches the developer before it is marked read."""

    def test_every_reply_is_read_once_delivered(self) -> None:
        self.seeded_on_conflict(documented=False)
        self.drift(UNREPORTED_REPLY)["_push_branch"].assert_not_called()
        _drift_world.human_reply(self, INSTRUCTION)
        _drift_world.human_reply(self, LONG_REPLY)

        resumed = self.drift(_drift_world.reported(), **_drift_world.STRANDED)
        self.reconcile()

        prompt = resumed["run_agent"].call_args.args[1]
        self.assertEqual(
            (INSTRUCTION in prompt, LONG_REPLY.strip() in prompt),
            (True, True),
        )
        self.assertEqual(
            self.pinned()["last_action_comment_id"],
            self.issue.comments[-1].id,
        )
        resumed["_push_branch"].assert_called_once()
        self.assertEqual(len(self.published_reports()), 1)

    def _run_resolving_conflict(self, github, issue, *, run_agent, **run_options):
        """The tick the dispatcher runs, routing on the label the issue carries."""
        return self._run(
            partial(
                _issue_processing._route_issue_to_handler,
                github, _TEST_SPEC, issue, github.workflow_label(issue),
            ),
            run_agent=run_agent,
            **run_options,
        )


if __name__ == "__main__":
    unittest.main()
