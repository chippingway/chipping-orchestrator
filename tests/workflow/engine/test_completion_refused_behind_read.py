# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""A transfer refused behind a verification's repository read reads the comment again before it answers.

The read is a request of its own, and another road may write the comment while
it is out. Whatever refuses the transfer behind it -- here the recording's own
refusal of a delivery it cannot record, before any commit is asked, its
revision past the bound an older unbound delivery already stands at -- the
comment is read again, and a caller whose reading it no longer is makes no
whole-state write: a capture a hand edit damaged meanwhile survives that write.
"""
from __future__ import annotations

import contextlib
import unittest
from types import MappingProxyType

from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.engine import completion_handoff as _handoff, report_delivery_state as _delivery_state
from orchestrator.workflow.engine.report_record_values import MAX_RECORDED_NUMBER, RecordRefusal
from orchestrator.workflow.engine.report_records import DELIVERED_REPORT, DeliveredReport, ReportMode
from orchestrator.workflow.state import WorkflowLabel
from tests.workflow.engine import completion_test_support as support, report_commit_test_support as commit_support

_REPOSITORY_READ = "is_own_repository"
_DAMAGED_CAPTURE = MappingProxyType({support.FIELD: None})

# An earlier report delivered and never bound, at the widest revision a record
# holds, so the delivery a transfer mints past it is one no reader takes.
_OLDEST = DeliveredReport(
    receipt=f"issue-{support.ISSUE}-report-{MAX_RECORDED_NUMBER}",
    report_revision=MAX_RECORDED_NUMBER,
    mode=ReportMode.PUBLISH,
    route=WorkflowLabel.IMPLEMENTING,
    requirements_revision=support.REQUIREMENTS,
    report="An earlier report nobody published.",
)


def _beside_the_oldest() -> support.CompletionWorld:
    """An issue whose VERIFIED capture stands beside that earlier delivery, as a later tick reads it."""
    world = support.seeded()
    world.captures(world.completion(message=support.VERIFIED))
    alone = PinnedState()
    _delivery_state.stage_delivered_report(alone, _OLDEST)
    oldest = {DELIVERED_REPORT: alone.get(DELIVERED_REPORT)}
    commit_support.another_road(world.github, world.issue, **oldest)
    return world.restarted()


class RefusedBehindTheReadTest(unittest.TestCase):
    """A recording refused before its commit, behind the repository read, holds back a caller whose reading moved."""

    def test_an_unrecordable_delivery_holds_it_back(self) -> None:
        """Refused as an invalid record, the transfer leaves its caller writable unless the comment moved meanwhile.

        A capture a hand edit damaged during the repository read holds the
        caller back, and is still the damaged claim after that caller's
        whole-state write behind the refusal.
        """
        for edited in (False, True):
            world = _beside_the_oldest()
            during = contextlib.nullcontext()
            if edited:
                during = commit_support.behind(world.github, world.issue, _REPOSITORY_READ, **_DAMAGED_CAPTURE)
            with during:
                refusal = world.asks(_handoff.transfer, world.invocation()).refusal
            world.github.write_pinned_state(world.issue, world.state)
            with self.subTest(edited=edited):
                self.assertIs(refusal, RecordRefusal.INVALID_RECORD)
                self.assertIs(world.state.withheld, edited)
                self.assertIn(support.FIELD, world.record())
                self.assertIs(world.record()[support.FIELD] is None, edited)


if __name__ == "__main__":
    unittest.main()
