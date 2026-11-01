# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""A late revision whose run finished on a report, the capture it left, and the dispatch that finishes it.

A revision's return is captured on its report (`late_revision_road`), and the
one held by an operator's control mid-run is kept whole for the dispatcher's
recovery, which a whole dispatch of the issue asks before the late
coordinator (`CapturedRevisionCase._dispatched`). Every case here shares the
report the run finishes on, the record it is read back from, the moves an
operator or another road makes while it waits, and what a revision finished
once leaves (`finished`).
"""
from __future__ import annotations

import contextlib
from pathlib import Path
from unittest.mock import MagicMock, patch

from orchestrator.agents.models import AgentInvocation
from orchestrator.github import labels as _labels, pinned_state as _pinned_state
from orchestrator.workflow.engine import (
    completion_records as _completion_records,
    completion_routes as _completion_routes,
    completion_spelling as _completion_spelling,
    issue_processing as _issue_processing,
    report_outcome_models as _outcome_models,
)
from orchestrator.workflow.state import WorkflowLabel
from tests.support.fakes import FakeLabel
from tests.workflow import captured_fixes as _fixes, fixtures as _fixtures, git_owners as _git_owners
from tests.workflow.stages.decomposition import (
    late_content_support as _content_support,
    late_requirements_support as _requirements_support,
    late_revision_support as _revision_support,
    late_run_support as _run_support,
    late_test_support as _late_support,
)

# The report a revision finishes on, and the text it hands the delivery: the
# outcome a revision's return is captured on.
DEV_REPORT_TEXT = "The importer now resumes from the last batch it committed."

DEV_REPORT = f"revised the importer.\n\nREPORT: READY\n{DEV_REPORT_TEXT}\nREPORT: END"

# Where a captured return lives on the pinned comment, and the delivery its
# report is handed to.
CAPTURED = _completion_records.DEVELOPER_COMPLETION
DELIVERED = "developer_report_delivery"

# The stages a captured return is read at.
PENDING = _completion_records.CaptureStage.PENDING
HANDED_OFF = _completion_records.CaptureStage.HANDED_OFF
RETIRED = _completion_records.CaptureStage.RETIRED

# The two controls an operator holds an issue with mid-run.
CONTROLS = (_revision_support.PAUSED_LABEL, _labels.BACKLOG_LABEL)

# Where the commit handing a capture to the delivery is lost -- the process
# lost as it went out, or its answer lost once it landed -- and whether the
# next dispatch's recovery is what lands it then.
LOST_HANDOFFS = ((_fixes.SENT, True), (_fixes.ANSWER, False))

# Where the commit withdrawing a capture behind its park is lost: as it went
# out, or once it landed.
LOST_WITHDRAWALS = (_fixes.SENT, _fixes.LANDED)

# The replies a generation records as still owed a whole quote.
OWED_REPLIES = "late_owed_replies"

# A field somebody fills the pinned comment with.
_NOTE = "operator_note"

# The seam a checkout's tree is read through.
_TREE_READ = "_worktree_status"

# The random half of a captured invocation's identity.
_NONCE = "00000000000000a3"

# The boundary the owner read's claim names, and the park an owner nobody
# could read takes.
_OWNER_CHECK = "owner_check"
_UNREAD_PARK = "late_owner_unreadable"


def capture_of(pinned: dict):
    """The captured completion a pinned record carries, read as its own reader reads it; None for none."""
    return _completion_spelling.read_record(pinned.get(CAPTURED))


def spelled_capture(cycle: int) -> dict:
    """A pending capture of a late revision run in late cycle `cycle`, as the pinned comment spells it."""
    number = _late_support.LATE_ISSUE_NUMBER
    digest = _late_support.CONTRIBUTION_DIGEST
    return _completion_spelling.spelled(_completion_records.CompletionCapture(
        invocation=AgentInvocation(
            repo=_fixtures._TEST_SPEC.slug, issue=number, comment=number, cycle=cycle, ordinal=1, nonce=_NONCE,
        ),
        handoff=_completion_records.CompletionHandoff(
            _completion_routes.CompletionRoute.LATE_REVISION, WorkflowLabel.DECOMPOSING, digest,
        ),
        run=_completion_records.CompletionRun(
            command=_revision_support.DEV_SPEC, prompt_revision=digest, worktree=_run_support.WORKTREE_NAME,
            branch=_run_support.WORKTREE_NAME, before_sha=_late_support.CANDIDATE_SHA,
            source_sha=_content_support.REVISED_SHA,
        ),
        outcome=_outcome_models._ReadyReport(DEV_REPORT_TEXT),
        accounting=_completion_records.CaptureAccounting.SETTLED,
    ))


class CapturedRevisionCase(_revision_support.RevisionCase):
    """A late issue whose developer revision finished on a report, held or not."""

    def _held(self, control: str = _revision_support.PAUSED_LABEL, **revised):
        """One revision an operator holds the issue under with `control` as it runs, finishing on its report."""
        return self._revise(reply=_revision_support.PausedDuringRun(self, DEV_REPORT, control), **revised)

    def _released(self, control: str = _revision_support.PAUSED_LABEL) -> None:
        """The operator takes `control` back off the issue."""
        self.issue.labels = [label for label in self.issue.labels if label.name != control]

    def _hand_edit(self, **fields) -> None:
        """Somebody edits the pinned comment in place, each of `fields` set."""
        pinned = self.github._pinned[_late_support.LATE_ISSUE_NUMBER]
        pinned.state_data.update(fields)

    def _filled(self, spare: int) -> None:
        """Somebody fills the pinned comment until only `spare` characters are left; `spare` 0 empties the note."""
        self._hand_edit(**{_NOTE: ""})
        if spare:
            size = len(_pinned_state.pinned_state_body(self._pinned(), escaped_in_full=True))
            room = _pinned_state.MAX_PINNED_BODY - size - spare
            self._hand_edit(**{_NOTE: "x" * room})

    def _lost_at_the_handoff(self, lost: str, stage=HANDED_OFF) -> contextlib.AbstractContextManager:
        """The block in which the edit moving a capture to `stage`, handed off by default, is lost as `lost` says."""
        losing = contextlib.ExitStack()
        losing.enter_context(patch.object(
            self.github, "edit_pinned_state", _fixes.LostAtTheHandoff(self.github, lost, str(stage)),
        ))
        losing.enter_context(contextlib.suppress(SystemExit))
        return losing

    def _developer_runs(self) -> int:
        """How many developer runs this issue has spawned."""
        return sum(
            spawned["agent_role"] == _content_support.ROLE_DEVELOPER
            for spawned in self._events_named(_content_support.EVENT_AGENT_SPAWN)
        )

    def _dispatched(
        self,
        seed=None,
        measurement=_revision_support.REMEASURED_OVERSIZED,
        applied: str | None = None,
        alongside: contextlib.AbstractContextManager | None = None,
    ) -> MagicMock:
        """Dispatch the issue whole, as a poll does, over the checkout a captured run left; the spawn it went through.

        The checkout is the one the capture names, at `seed`'s head -- the
        commit the revision left by default -- and every commit it names is
        one the store holds. A later run answers with a split. `applied` is a
        control an operator applies as the checkout's tree is read -- inside
        a recovery, behind its readings of the thread and ahead of any write.
        `alongside` is held over the harness's own seams for the dispatch.
        """
        ran = getattr(capture_of(self._pinned()), "run", None)
        spawn = MagicMock(return_value=_run_support.agent_reply(_late_support.SPLIT_REPLY))
        seeded = seed or _run_support.WorktreeSeed(head=_content_support.REVISED_SHA)
        with contextlib.ExitStack() as stack:
            stack.enter_context(_run_support.late_run_context(spawn, worktree=seeded, measurement=measurement))
            if ran is not None:
                checkout = MagicMock(return_value=Path(ran.worktree))
                stack.enter_context(_git_owners.seam_patch("_worktree_path", checkout))
            if applied is not None:
                stack.enter_context(_AppliedAsRead(self.issue, applied).patched())
            stack.enter_context(_git_owners.seam_patch("_commit_present", MagicMock(return_value=True)))
            if alongside is not None:
                stack.enter_context(alongside)
            _issue_processing._process_issue(self.github, _fixtures._TEST_SPEC, self.issue)
        return spawn


class _AppliedAsRead:
    """A checkout's tree read with an operator's control applied to the issue as it is read."""

    def __init__(self, issue, control: str) -> None:
        self._issue = issue
        self._control = FakeLabel(control)
        self._reads = _git_owners.GIT_SEAM_OWNERS[_TREE_READ]._worktree_status

    def __call__(self, worktree):
        """Apply the control, then answer the read the harness holds."""
        self._issue.labels.append(self._control)
        return self._reads(worktree)

    def patched(self) -> contextlib.AbstractContextManager:
        """The read, held in place of the one the harness holds for the block."""
        return _git_owners.seam_patch(_TREE_READ, MagicMock(side_effect=self))


class BehindTheUnreadPark:
    """GitHub refusing the owner read behind a recovery's handoff once, `aside()` done behind the park it takes.

    The owner read is the first fetch of the issue once the capture reads
    handed off and the cycle stands at the read's claimed boundary -- the
    fetches the claim's own write asks behind are taken ahead of it -- and,
    refused, it parks the issue for the owner nobody could read; the aside
    lands right behind the edit that writes that park, ahead of anything
    after it. The number of comments said as the aside is done is kept
    (`said`), None until it is.
    """

    def __init__(self, case: CapturedRevisionCase, aside) -> None:
        self._case = case
        self._aside = aside
        self._fetches = case.github.get_issue
        self._edits = case.github.edit_pinned_state
        self.refused = False
        self.said: int | None = None

    def patched(self) -> contextlib.AbstractContextManager:
        """The fetch and the strict edit, held in place of the double's for the block."""
        held = contextlib.ExitStack()
        held.enter_context(patch.object(self._case.github, "get_issue", self._fetch))
        held.enter_context(patch.object(self._case.github, "edit_pinned_state", self._edit))
        return held

    def _fetch(self, number: int):
        pinned = self._case._pinned()
        handed = getattr(capture_of(pinned), "stage", None) is HANDED_OFF
        claimed = pinned.get(_late_support.KEYS.phase) == _OWNER_CHECK
        if handed and claimed and not self.refused:
            self.refused = True
            raise RuntimeError("GitHub did not answer the owner read")
        return self._fetches(number)

    def _edit(self, issue, state, **options):
        sent = self._edits(issue, state, **options)
        parked = self._case._pinned().get(_late_support.KEYS.park_reason) == _UNREAD_PARK
        if parked and self.said is None:
            self.said = len(self._case._bodies())
            self._aside()
        return sent


class UnreadOnceClosed:
    """The pinned comment refusing every read once a fetch has read the issue closed, while it stays closed."""

    def __init__(self, case: CapturedRevisionCase) -> None:
        self._case = case
        self._fetches = case.github.get_issue
        self._reads = case.github.read_pinned_state
        self.seen = False

    def patched(self) -> contextlib.AbstractContextManager:
        """The fetch and the read, held in place of the double's for the block."""
        held = contextlib.ExitStack()
        held.enter_context(patch.object(self._case.github, "get_issue", self._fetch))
        held.enter_context(patch.object(self._case.github, "read_pinned_state", self._read))
        return held

    def _fetch(self, number: int):
        fetched = self._fetches(number)
        self.seen = self.seen or fetched.closed
        return fetched

    def _read(self, issue):
        if self.seen and self._case.issue.closed:
            raise RuntimeError("GitHub did not answer the pinned comment read")
        return self._reads(issue)


def finished(case: CapturedRevisionCase, source: str) -> dict:
    """Assert `case`'s revision finished once on `source`, its report handed to the delivery; the record it left.

    The generation advanced once onto `source`, the park answered, the
    guidance it was handed consumed on every baseline, the replies it owed
    repaid, and the capture handed off in the commit that records its report
    under the `decomposing` route, revision 1.
    """
    pinned = case._pinned()
    case.assertEqual(
        (pinned[_content_support.KEY_GENERATION], pinned[_late_support.KEYS.candidate_sha]),
        (_late_support.NEXT_GENERATION, source),
    )
    case.assertFalse(pinned[_late_support.KEYS.awaiting])
    case.assertEqual(
        (pinned[_content_support.KEY_COMMENT_WATERMARK], pinned[_content_support.KEY_LAST_ACTION_COMMENT_ID]),
        (case.guidance.id, case.guidance.id),
    )
    case.assertEqual(
        pinned[_requirements_support.KEY_USER_CONTENT_HASH], _requirements_support.requirements(case.issue),
    )
    case.assertNotIn(OWED_REPLIES, pinned)
    handed = capture_of(pinned)
    case.assertEqual((handed.stage, handed.source_sha), (HANDED_OFF, source))
    delivered = pinned[DELIVERED]
    case.assertEqual(
        (delivered["report"], delivered["route"], delivered["revision"]),
        (DEV_REPORT_TEXT, str(WorkflowLabel.DECOMPOSING), 1),
    )
    return pinned
