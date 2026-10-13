# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The workflow's guarded recovery operations, reached through the production roads that hand them to the git owner.

Every recovery context the workflow builds carries them
(`workflow/engine/rewrite_recovery_parks.py`): the recorder ahead of every
reset, the settled-aware answer a landed reset is owed, the proof before a
park that keeps the attempt, and the park every recovery park is recorded
through. A case reaches them as a live tick does: through the git owner's
fail-closed abort, which every per-tick base refresh whose fetch of the branch
fails (`unfetched`) takes, through the dispatcher's hold of an anchor it keeps
a handler back for (`answers_a_held_anchor`), or -- asking the park proof
alone -- over a context read off the comment as it stands
(`recovery_context`). A real-git finish case is a `GuardedRecoveryCase`.
"""
from __future__ import annotations

import subprocess
from functools import partial
from unittest.mock import patch

from orchestrator import config
from orchestrator.git import branch_transport
from orchestrator.git.base_sync import attempt_records as _attempt_records, snapshot as _snapshot
from orchestrator.git.base_sync.models import _AutoRebaseRecoveryContext
from orchestrator.github.verification_evidence import VerifiedCommand
from orchestrator.workflow.engine import (
    dispatch_guards as _dispatch_guards,
    rewrite_recovery as _rewrite_recovery,
    verification_record_state as _record_state,
    verification_settlement_state as _settlement,
)
from orchestrator.workflow.engine.rewrite_finish_models import FinishRoad
from tests.workflow.engine import (
    rewrite_finish_git_support as git_support,
    rewrite_finish_readings as readings,
    rewrite_handoff_test_support as handoff,
    rewrite_verification_recovery_support as support,
)

AWAITING = "awaiting_human"

# The park's flag and the attempt's anchor and base tip, as a case reads them together.
ATTEMPT_FIELDS = (AWAITING, readings.KEY_PENDING_PUSH, readings.KEY_REWRITE_BASE)

# The branch transport's fetch, read before any case patches it.
_FETCH = branch_transport._authed_fetch


def unfetched(spec, ref: str, **options) -> subprocess.CompletedProcess:
    """The branch transport's fetch, failing for issue #7's branch alone."""
    if "issue-7" in ref:
        return subprocess.CompletedProcess([], 1, "", "fetch failed")
    return _FETCH(spec, ref, **options)


def parking(_issue, state, *, over: dict) -> bool:
    """Whether a pinned-comment edit is a park's record, which the comment lacks."""
    return bool(state.get(AWAITING)) and not over.get(AWAITING)


BEFORE_THE_RECORD = handoff.Boundary("before the park is recorded", "edit_pinned_state", parking)


def recovery_context(case) -> _AutoRebaseRecoveryContext:
    """The context the workflow's recovery hands every road, over `case`'s comment and checkout as they now read.

    Taken off the recovery itself (`rewrite_recovery.recovers`), its fetch of
    the branch stopped before any road is chosen, so a case handing it to a
    git owner's road directly takes that road with exactly what a live
    recovery would hand it.
    """
    state = case.gh.read_pinned_state(case.issue)
    read = _AutoRebaseRecoveryContext(
        gh=case.gh,
        spec=case._spec,
        issue=case.issue,
        state=state,
        worktree=case._wt,
        pr_number=git_support.PR_NUMBER,
        label=git_support.REVIEWING,
        pending_pre_rebase_sha=state.get(readings.KEY_PENDING_PUSH),
        pending_rewrite=_attempt_records._pending_rewrite(state),
    )
    handed: list[_AutoRebaseRecoveryContext] = []
    with patch.object(_snapshot, "_fetch_recovery_snapshot", handed.append):
        _rewrite_recovery.recovers(read)
    return handed[0]


def records_a_newer_run(case):
    """Record a newer transaction beside `case`'s settled run, carrying its binding, as another road would; it.

    Its transcript is the configured command passing, as the settled run's own
    reads, and it raises the revision floor past that run.
    """
    state = case.gh.read_pinned_state(case.issue)
    binding = readings.pinned_records(case)[1].binding
    command = config.VERIFY_COMMANDS[0]
    passed = (VerifiedCommand(command=command, exit_status=0, output=git_support.CHECKED),)
    newer = _record_state.mint_pending_evidence(state, git_support.ISSUE, binding, passed)
    case.assertTrue(_record_state.record_pending_evidence(state, newer))
    case.gh.write_pinned_state(case.issue, state)
    return newer


def settles_elsewhere(case, head: str, written: str, raced: list) -> None:
    """Put the issue back as `written` and settle `head`'s captured run as another finish would, once; into `raced`.

    That finish dies before its announcement, so the attempt still stands.
    """
    if raced:
        return
    raced.append(head)
    case.issue.body = written
    finishing = partial(case.finishes, head, FinishRoad.RECOVERY)
    handoff.dies_at(case.gh, handoff.BEFORE_THE_ANNOUNCEMENT, finishing)


def answers_a_held_anchor(case) -> None:
    """The dispatcher's hold of the anchor `case`'s issue carries, answered as the dispatcher answers it."""
    label = case.gh.workflow_label(case.issue)
    state = case.gh.read_pinned_state(case.issue)
    _dispatch_guards._anchor_holds_the_tick(case.gh, case._spec, case.issue, label, state)


class GuardedRecoveryCase(support.CapturedRunCase):
    """The real-git finish case whose recoveries take the guarded operations the workflow hands the git owner."""

    def proves(self) -> bool:
        """The proof a park that keeps the attempt asks, over the comment and checkout as they now read."""
        context = recovery_context(self)
        return context.proves_before_a_park(context)

    def settles_then_dies(self) -> tuple:
        """Land a reviewed rebase, settle its run, and kill its finish before its announcement; the head and the run."""
        head = self.lands_a_reviewed_rebase()
        handoff.dies_at(self.gh, handoff.BEFORE_THE_ANNOUNCEMENT, partial(self.finishes, head))
        return head, readings.pinned_records(self)[1]

    def assert_invalidated(self, settled, pending: str | None = None) -> None:
        """`settled` invalidated whole behind the anchor's evidence, its revision and binding kept, `pending` beside it.

        `pending` is the receipt of a transaction another road recorded, None
        where nothing is pending. Nothing is announced or relabelled, and the
        run was made once, with nothing pushed or launched.
        """
        records = readings.pinned_records(self)
        retired = (*git_support.invalidated(self), (settled.receipt, readings.INVALIDATED))
        self.assertEqual(records[1:], (None, retired))
        self.assertEqual(getattr(records[0], "receipt", None), pending)
        entry = _settlement.read_evidence_history(self.gh.read_pinned_state(self.issue))[-1]
        self.assertEqual((entry.revision, entry.binding), (settled.revision, settled.binding))
        said = (support.announced(self), readings.relabels(self))
        self.assertEqual(said, ([], ()))
        self.assert_made_once()

    def assert_routed(self, head: str, current=None) -> None:
        """`head` announced once and routed, its attempt retired, `current` current with nothing pending; run once."""
        announced = (support.announced(self), len(readings.notices(self)))
        self.assertEqual(announced, ([head], 1))
        self.assertEqual(readings.relabels(self), readings.ROUTED)
        self.assertEqual(readings.attempt(readings.pinned(self)), readings.RETIRED)
        self.assertEqual(readings.pinned_records(self)[:2], (None, current))
        self.assert_made_once()

    def assert_made_once(self) -> None:
        """The run made once, by the finish that died, and nothing pushed or launched."""
        made = (self.runs(), self.pushes.call_count, self.developer.call_count)
        self.assertEqual(made, (1, 0, 0))

    def assert_released(self) -> None:
        """The issue parked for a human, and the attempt released."""
        pinned = readings.pinned(self)
        parked = (pinned[AWAITING], readings.attempt(pinned))
        self.assertEqual(parked, (True, readings.RETIRED))

    def pinned_fields(self, *keys: str) -> tuple:
        """What the pinned comment now carries under each of `keys`, None where it carries nothing."""
        pinned = readings.pinned(self)
        return tuple(pinned.get(key) for key in keys)
