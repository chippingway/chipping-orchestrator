# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""A retired captured completion ends its tick, so no stage runs on the snapshot the recovery's readings outdated.

The dispatching worker read the issue before the recovery did. Where the
recovery's own fetch finds it closed, or its requirements edited, the capture
is retired on that reading -- and the implementing stage, run behind it on
the worker's snapshot, would launch a developer the close forbids, or hand
one requirements the edit replaced. So the tick ends at the retirement, and
the next one runs the stage over the issue as it then reads. The stage runs
whole here, its agent stood in for.
"""
from __future__ import annotations

import functools
import unittest
from dataclasses import replace
from types import MappingProxyType
from unittest.mock import patch

from orchestrator.workflow.engine import completion_records as _records, issue_processing as _issue_processing
from tests.workflow.engine import completion_recovery_support as _support
from tests.workflow.fixtures import _TEST_SPEC, _agent
from tests.workflow.patch_context import _patch_and_run
from tests.workflow.patch_models import _WorkflowRunContext

_RETIRED = _records.CaptureStage.RETIRED

_REQUIREMENT = "The implementation must also support the newly required export format."

# What the recovery's fetch finds that the worker's snapshot does not: the issue closed, or its body edited.
_FOUND = MappingProxyType({
    "closed": MappingProxyType({"closed": True}),
    "edited": MappingProxyType({"body": _REQUIREMENT}),
})


def _launches(world: _support.CapturedWorld):
    """Dispatch the world's issue once, as the worker read it, the stage run whole; the agent runner it reached."""
    context = _WorkflowRunContext(
        run_agent=_agent(last_message="Need clarification"),
        has_new_commits=False,
        head_shas=(_support.SOURCE,),
        issue_worktree=_support.WORKTREE,
    )
    dispatch = functools.partial(_issue_processing._process_issue, world.github, _TEST_SPEC, world.issue)
    return _patch_and_run(dispatch, context)["run_agent"]


class RetirementEndsTheTickTest(unittest.TestCase):
    """No stage runs behind a retirement on the dispatch's own snapshot."""

    def test_nothing_launches_behind_it(self) -> None:
        # Retired on what the recovery's fetch found, the capture leaves the
        # worker's snapshot behind: no developer is launched over it, and no
        # run is charged.
        for name, found in _FOUND.items():
            with self.subTest(name):
                world = _support.CapturedWorld()
                world.captured()

                with patch.object(world.github, "get_issue", return_value=replace(world.issue, **found)):
                    launched = _launches(world)

                self.assertEqual(launched.call_count, 0)
                self.assertEqual(_support.read_capture(world.record()).stage, _RETIRED)
                self.assertEqual(world.record()["agent_runs_used"], _support.RUNS_USED)

    def test_the_next_tick_reads_the_edit(self) -> None:
        # The next tick's worker reads the edited issue, and the developer it
        # launches is handed the requirements the recovery found.
        world = _support.CapturedWorld()
        world.captured()
        with patch.object(world.github, "get_issue", return_value=replace(world.issue, body=_REQUIREMENT)):
            _launches(world)
        world.issue.body = _REQUIREMENT

        launched = _launches(world)

        self.assertEqual(launched.call_count, 1)
        self.assertIn(_REQUIREMENT, launched.call_args.args[1])


if __name__ == "__main__":
    unittest.main()
