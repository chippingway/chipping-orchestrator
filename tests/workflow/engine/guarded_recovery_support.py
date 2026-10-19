# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The workflow's dormant guarded recovery operations, handed explicitly to the git owner's recovery contexts.

No recovery road the workflow builds a context for carries them yet
(`workflow/engine/rewrite_recovery_parks.py`), so a case hands them in itself
(`guarded`): the recorder ahead of every reset, the settled-aware answer a
landed reset is owed, the proof before a park that keeps the attempt, the
park every recovery park is recorded through, and the guarded clear. It hands
them to the context the git owner's fail-closed abort is taken over
(`guarded_roads`), which every tick whose fetch of the branch fails
(`unfetched`) reaches, to the refresh's eligibility gate and the clear of an
unmoved anchor beside it, to the dispatcher's held anchor
(`answers_a_held_anchor`), or to a context read off the comment as it stands
(`recovery_context`), for a case asking the park proof or the guarded hold
alone. A real-git finish case whose every tick takes the guarded abort and
clears is a `GuardedRecoveryCase`.
"""
from __future__ import annotations

import subprocess
from contextlib import contextmanager
from dataclasses import replace
from functools import partial
from unittest.mock import patch

from orchestrator.git import branch_transport
from orchestrator.git.base_sync import (
    attempt_records as _attempt_records,
    eligibility as _eligibility,
    recovery_holds as _recovery_holds,
    snapshot as _snapshot,
)
from orchestrator.git.base_sync.models import _AutoRebaseRecoveryContext
from orchestrator.workflow.engine import (
    rewrite_landing_retirement as _retirement,
    rewrite_recovery_parks as _parks,
    verification_settlement_state as _settlement,
)
from tests.workflow.engine import (
    rewrite_finish_git_support as git_support,
    rewrite_finish_readings as readings,
    rewrite_handoff_test_support as handoff,
    rewrite_verification_recovery_support as support,
)

AWAITING = "awaiting_human"

# The park's flag and the attempt's anchor and base tip, as a case reads them together.
ATTEMPT_FIELDS = (AWAITING, readings.KEY_PENDING_PUSH, readings.KEY_REWRITE_BASE)

# The git owner's abort, its clear of an unmoved anchor, and the branch transport's fetch, read before any case patches
# them.
_ABORT = _snapshot._abort_recovery_unverified

_UNMOVED = _snapshot._clear_unchanged_recovery

# The refresh's eligibility gate, handed the dormant proof, park, settled-aware retirement, and clear.
_GATED = partial(
    _eligibility._auto_rebase_label_is_eligible,
    proves_before_a_park=_parks.proves_before_a_park,
    lands_a_park=_parks.lands_a_park,
    settles_over_a_release=_retirement.retires_over_the_reset,
    lands_a_clear=_parks.lands_a_clear,
)

_FETCH = branch_transport._authed_fetch


def guarded(context: _AutoRebaseRecoveryContext) -> _AutoRebaseRecoveryContext:
    """`context` carrying every dormant guarded operation in place of the answers the workflow hands it today."""
    return replace(
        context,
        settles_over_a_reset=partial(_retirement.retires_over_the_reset, context),
        records_before_a_reset=_parks.records_the_reset,
        proves_before_a_park=_parks.proves_before_a_park,
        lands_a_park=_parks.lands_a_park,
        lands_a_clear=_parks.lands_a_clear,
    )


@contextmanager
def guarded_roads():
    """The git owner's abort and clear of an unmoved anchor, and the refresh's eligibility gate, taken `guarded`."""
    with (
        patch.object(_snapshot, "_abort_recovery_unverified", lambda context, detail: _ABORT(guarded(context), detail)),
        patch.object(_snapshot, "_clear_unchanged_recovery", lambda context: _UNMOVED(guarded(context))),
        patch.object(_eligibility, "_auto_rebase_label_is_eligible", lambda context, *_answers: _GATED(context)),
    ):
        yield


def unfetched(spec, ref: str, **options) -> subprocess.CompletedProcess:
    """The branch transport's fetch, failing for issue #7's branch alone."""
    if "issue-7" in ref:
        return subprocess.CompletedProcess([], 1, "", "fetch failed")
    return _FETCH(spec, ref, **options)


def parking(_issue, state, *, over: dict, **_options) -> bool:
    """Whether a pinned-comment edit is a park's record, which the comment lacks."""
    return bool(state.get(AWAITING)) and not over.get(AWAITING)


BEFORE_THE_RECORD = handoff.Boundary("before the park is recorded", "edit_pinned_state", parking)


def recovery_context(case) -> _AutoRebaseRecoveryContext:
    """The recovery context of `case`'s issue as its comment now reads, `guarded`, over its checkout."""
    state = case.gh.read_pinned_state(case.issue)
    return guarded(_AutoRebaseRecoveryContext(
        gh=case.gh,
        spec=case._spec,
        issue=case.issue,
        state=state,
        worktree=case._wt,
        pr_number=git_support.PR_NUMBER,
        label=git_support.REVIEWING,
        pending_pre_rebase_sha=state.get(readings.KEY_PENDING_PUSH),
        pending_rewrite=_attempt_records._pending_rewrite(state),
    ))


def answers_a_held_anchor(case) -> None:
    """The git owner's answer to the anchor the dispatcher holds `case`'s issue for, handed the dormant operations."""
    label = case.gh.workflow_label(case.issue)
    state = case.gh.read_pinned_state(case.issue)
    held = _recovery_holds._held_anchor_context(case.gh, case._spec, case.issue, state, label)
    _recovery_holds._answers_a_held_anchor(guarded(held), _parks.proves_before_a_park, _parks.lands_a_park)


class GuardedRecoveryCase(support.CapturedRunCase):
    """The real-git finish case whose every per-tick base refresh takes the git owner's abort and clears `guarded`."""

    def recovers(self, during=None) -> None:
        """One whole per-tick base refresh (`CapturedRunCase.recovers`), its roads handed the guarded operations."""
        with guarded_roads():
            support.CapturedRunCase.recovers(self, during)

    def proves(self) -> bool:
        """The dormant proof a park that keeps the attempt asks, over the comment and checkout as they now read."""
        return _parks.proves_before_a_park(recovery_context(self))

    def settles_then_dies(self) -> tuple:
        """Land a reviewed rebase, settle its run, and kill its finish before its announcement; the head and the run."""
        head = self.lands_a_reviewed_rebase()
        handoff.dies_at(self.gh, handoff.BEFORE_THE_ANNOUNCEMENT, partial(self.finishes, head))
        return head, readings.pinned_records(self)[1]

    def assert_invalidated(self, settled, pending: str | None = None, *, over=None) -> None:
        """`settled` invalidated whole behind the anchor's evidence, its revision and binding kept, `pending` beside it.

        `pending` is the receipt of a transaction another road recorded, None
        where nothing is pending; `over` is the run `settled` superseded where
        another road settled it in that run's place. Nothing is announced or
        relabelled, and the run was made once, with nothing pushed or launched.
        """
        records = readings.pinned_records(self)
        retired = [*git_support.invalidated(self), (settled.receipt, readings.INVALIDATED)]
        if over is not None:
            retired.insert(-1, (over.receipt, readings.SUPERSEDED))
        retired = tuple(retired)
        self.assertEqual(records[1:], (None, retired))
        self.assertEqual(getattr(records[0], "receipt", None), pending)
        entry = _settlement.read_evidence_history(self.gh.read_pinned_state(self.issue))[-1]
        self.assertEqual((entry.revision, entry.binding), (settled.revision, settled.binding))
        said = (support.announced(self), readings.relabels(self))
        self.assertEqual(said, ([], ()))
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
