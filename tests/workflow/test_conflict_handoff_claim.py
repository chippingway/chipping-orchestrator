# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The move a counted conflict round owes, made through the dispatcher once its head is proved.

A body edit's resume on `workflow:resolving_conflict` commits the round that
spends the last of the conflict cap. Its push lands and the relabel handing the
head to `workflow:validating` does not, so the round is counted and the claim
naming the head it handed on stands. While nothing can prove the head the
checkout is on, the dispatched ticks hold: nothing is pushed, launched, charged
or counted, the cap parks nothing, and the claim stays. The first tick that can
prove the head makes the move, with the round counted once.
"""
from __future__ import annotations

import unittest
from functools import partial
from unittest.mock import patch

from orchestrator import config
from orchestrator.workflow.engine import issue_processing as _issue_processing
from orchestrator.workflow.state import WorkflowLabel
from tests.workflow import drift_reports as _drift_world, fix_report_crashes as _crashes
from tests.workflow.fixtures import _TEST_SPEC
from tests.workflow.stages.conflicts import drift_report_support as _conflict

# A counter one round short of the cap, which the resume's round then reaches.
AT_THE_CAP = 2

ROUND = "conflict_round"

CLAIM = "conflict_handed_sha"


class OwedMoveAtTheCapTest(unittest.TestCase, _conflict._ConflictDriftReportMixin):
    """A lost relabel at the conflict cap, its move held until its head is proved."""

    def test_an_unproved_head_holds_the_move(self) -> None:
        self.enterContext(patch.object(config, "MAX_CONFLICT_ROUNDS", AT_THE_CAP))
        self.seeded_on_conflict(**{ROUND: AT_THE_CAP - 1})
        with _crashes.dying_before_the_relabel(self):
            self.drift(_drift_world.reported())
        before = self.pinned()

        held = [
            self.drift([], committed=False, **_conflict.UNPROVED_HEAD)
            for _ in range(2)
        ]

        self.assertEqual(
            {ticked[name].call_count for ticked in held for name in ("_push_branch", "run_agent")},
            {0},
        )
        self.assertEqual(self.pinned(), before)
        self.assertEqual(self.github.label_history, [])

        self.drift([], committed=False)

        pinned = self.pinned()
        self.assertEqual(
            (pinned[ROUND], pinned.get(CLAIM), pinned.get("park_reason")),
            (AT_THE_CAP, None, None),
        )
        self.assertEqual(self.github.label_history, [(_conflict.ISSUE, WorkflowLabel.VALIDATING)])

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
