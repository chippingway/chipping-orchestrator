# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""A capture a dependency hold kept waiting is decided before the implementer `ready` hands the issue to runs.

The `ready` decision is one of the stages a captured completion waits
through: it compares the requirements and hands the issue back to
implementation as it would without one. But the implementing tick that
handoff runs in-tick is the stage that would read the captured commit as
unreported work and launch the developer over it, so the capture is asked
about first, as the dispatcher asks ahead of every handler it reaches: with
no owner for its road it holds that tick, and an owner is handed it.
"""
from __future__ import annotations

import contextlib
import unittest

from orchestrator.git.worktrees import naming as _naming, paths as _paths
from orchestrator.workflow.engine import completion_records as _records
from orchestrator.workflow.stages.decomposition import blocked as _blocked
from tests.support.fakes import FakeGitHubClient
from tests.workflow.engine import completion_dispatch_support as _dispatch, completion_recovery_support as _captures
from tests.workflow.fixtures import _TEST_SPEC, _agent, _PatchedWorkflowMixin, _reported
from tests.workflow.stages.decomposition import ready_test_support as _support

_SOURCE = "c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0"

# Every reading of the checkout's head the tick takes: the commit the run left.
_HEADS = (_SOURCE,) * 8

# What the captured run ran as: in the child's own checkout, on its branch, leaving `_SOURCE`.
_RUN = _records.CompletionRun(
    command=_captures.COMMAND,
    prompt_revision=_captures.PROMPT,
    worktree=str(_paths._worktree_path(_TEST_SPEC, _support.CHILD)),
    branch=_naming._branch_name(_TEST_SPEC, _support.CHILD),
    before_sha=_captures.BEFORE,
    source_sha=_SOURCE,
)


class ReadyCaptureTest(unittest.TestCase, _PatchedWorkflowMixin, _support.ReadyTicks):
    """The handoff to implementation stops behind a capture nothing has decided."""

    def test_the_implementer_waits_behind_it(self) -> None:
        # Handed on as ever -- pickup, consumption, relabel -- and then held:
        # with no owner no implementer is launched over the captured commit,
        # and an owner is handed the capture first; either way it is left as
        # it was.
        for owner in (None, _dispatch.RoadOwner()):
            with self.subTest(owned=owner is not None):
                gh = FakeGitHubClient()
                child = _support.ready_child(gh)
                captured = _captures.landed_capture(gh, child, _RUN, _captures.road())

                with contextlib.nullcontext() if owner is None else _dispatch.owned(owner):
                    self.assertEqual(self._ready(gh, child), 0)

                self.assertEqual(gh.label_history[-1], _support.STARTED)
                self.assertEqual(_captures.read_capture(gh.pinned_data(_support.CHILD)), captured)
                self._handed(owner, captured)

    def _handed(self, owner: _dispatch.RoadOwner | None, captured: _records.CompletionCapture) -> None:
        """`owner`, where there is one, was handed `captured` and nothing else."""
        if owner is not None:
            self.assertEqual([admitted.capture for admitted in owner.handed], [captured])

    def _ready(self, gh: FakeGitHubClient, child) -> int:
        """The `ready` tick over a checkout standing on the captured commit; the agents it ran."""
        mocks = self._run(
            lambda: _blocked._handle_ready(gh, _TEST_SPEC, child),
            run_agent=_agent(session_id="dev-sess", last_message=_reported()),
            head_shas=_HEADS,
        )
        return mocks[_support.RUN_AGENT].call_count


if __name__ == "__main__":
    unittest.main()
