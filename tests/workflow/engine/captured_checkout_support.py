# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""A pre-PR checkout on a real repository whose developer run captured its completion, and the base moving past it.

The issue's branch is checked out at its layout path in a clone of a bare
remote, with one commit on it -- the commit the run reported on -- and its
completion is captured on the issue's pinned comment through its own
checkpoint, as a producer lands one. The base then advances on the remote
from another clone, so the tick's own base fetch is what brings the advance
into this clone, and its refresh is what would rebase the checkout over it.

The road's owner is stood in for by one that hands the capture to the report
delivery through the existing transfer and stops the tick there, which is
where the road's own publication would take over.

A reading the recovery cannot take is left unanswered for a block: the
issue's thread, and the checkout's head where its branch names an object the
store does not hold, as a damaged store leaves it.
"""
from __future__ import annotations

import contextlib
import subprocess
from types import MappingProxyType
from unittest.mock import patch

from orchestrator.git.worktrees import naming as _naming, paths as _worktree_paths
from orchestrator.workflow.engine import completion_handoff as _handoff, completion_records as _records
from orchestrator.workflow.state import WorkflowLabel
from tests.git.worktrees import real_git_test_support as _real_git
from tests.support.fakes import FakeGitHubClient, make_issue
from tests.support.github.models import FakeLabel
from tests.workflow.engine import (
    completion_dispatch_support as _dispatch,
    completion_recovery_support as _captures,
    refused_checkouts_support as _refused,
)

NUMBER = 61

PENDING = _records.CaptureStage.PENDING.value
HANDED_OFF = _records.CaptureStage.HANDED_OFF.value

# The report a capture became, bound and settled: its delivery spent, as the delivery's own transaction spends it.
SETTLED = MappingProxyType({"developer_report_delivery": None})

# The block a tick's real refresh runs in: nothing beyond the disk's own transport stands in for it.
REAL_REFRESH = contextlib.nullcontext()

# Accounting its checkpoint landed for an invocation, and the count it covers.
ACCOUNTED = MappingProxyType({
    "issue_usage_receipts": {"floor": 0, "recent": [[1, "0000000000000001"]]},
    "issue_agent_runs": 1,
})

# A hand edit spelling the capture as nothing any build writes.
DAMAGED = MappingProxyType({_captures.FIELD: None})

# Where a world stands: on the commit the run reported on, with its capture pending or handed off.
KEPT_PENDING = (True, PENDING)
KEPT_HANDED_OFF = (True, HANDED_OFF)

_IMPLEMENTING = str(WorkflowLabel.IMPLEMENTING)

# An object id no store in these worlds holds.
_MISSING = "ffffffffffffffffffffffffffffffffffffffff"


def stage_of(github: FakeGitHubClient) -> str | None:
    """The stage the issue's capture stands at on its pinned comment, or None where it carries none."""
    captured = github.pinned_data(NUMBER).get(_captures.FIELD)
    return captured.get("stage") if isinstance(captured, dict) else None


class Transferring(_dispatch.RoadOwner):
    """A road's owner that hands the capture to the report delivery through the existing transfer, and stops."""

    def __call__(self, admitted) -> bool:
        """Transfer the admitted capture into the delivery, and stop the tick behind it."""
        super().__call__(admitted)
        _handoff.transfer(admitted.gh, admitted.issue, admitted.state, admitted.capture.invocation)
        return True


class CapturedCheckout:
    """The issue, its checkout on the commit the run reported on, and the advanced base."""

    def __init__(self, case, github: FakeGitHubClient, *, label: str = _IMPLEMENTING) -> None:
        self.disk = _refused._Disk(case)
        self.github = github
        self.owner = Transferring()
        self._base_before = self.disk.base()
        branched = self.disk.branch(NUMBER, push=False)
        self._branch = branched[0]
        self.source = branched[1]
        self._checkout = _worktree_paths._worktree_path(self.disk.spec, NUMBER)
        self.issue = make_issue(NUMBER, label=label)
        github.add_issue(self.issue)
        github.seed_state(NUMBER, branch=self._branch)
        self.base_after = self.disk.advance_base()

    def captured(self) -> _records.CompletionCapture:
        """Land the capture of the run that finished on the checkout's commit, as its producer would."""
        run = _records.CompletionRun(
            command=_captures.COMMAND,
            prompt_revision=_captures.PROMPT,
            worktree=str(self._checkout),
            branch=self._branch,
            before_sha=self._base_before,
            source_sha=self.source,
        )
        return _captures.landed_capture(self.github, self.issue, run, _captures.road())

    def standing(self) -> tuple[bool, str | None]:
        """Whether the checkout still stands on the commit the run reported on, and the stage its capture is at."""
        head = _real_git._run_git("rev-parse", "HEAD", cwd=self._checkout).strip()
        return head == self.source, stage_of(self.github)

    def on_the_advance(self) -> bool:
        """Whether the checkout has been carried onto the advanced base."""
        ancestry = ("merge-base", "--is-ancestor", self.base_after, "HEAD")
        try:
            _real_git._run_git(*ancestry, cwd=self._checkout)
        except subprocess.CalledProcessError:
            return False
        return True

    def controlled(self, control: str, *, held: bool) -> None:
        """An operator applies `control`, or takes it off."""
        if held:
            self.issue.labels.append(FakeLabel(control))
        else:
            self.issue.labels.remove(FakeLabel(control))

    def hand_edit(self, **fields) -> None:
        """Somebody edits the pinned comment in place between ticks, setting `fields`."""
        pinned = self.github._pinned[NUMBER]
        pinned.state_data.update(fields)

    def owned(self) -> contextlib.AbstractContextManager:
        """Every road owned by this world's transferring owner for the block."""
        return _dispatch.owned(self.owner)


def unread_thread(world: CapturedCheckout) -> contextlib.AbstractContextManager:
    """For the block, the issue's thread will not read."""
    return patch.object(world.github, "comments_after", side_effect=RuntimeError("thread unread"))


def dangling_head(world: CapturedCheckout) -> contextlib.AbstractContextManager:
    """The issue's branch made to name an object the store does not hold, until the block it opens ends.

    Written as the loose ref itself, since git refuses to point a ref at an
    object it cannot read, and a damaged store is exactly where one does. The
    block's end points it back at the commit the run reported on.
    """
    spec = world.disk.spec
    loose = spec.target_root.joinpath(".git", "refs", "heads", _naming._branch_name(spec, NUMBER))
    loose.write_text(f"{_MISSING}\n")
    restored = contextlib.ExitStack()
    restored.callback(loose.write_text, f"{world.source}\n")
    return restored
