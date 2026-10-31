# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Finish a captured requirements-drift resume on `in_review` the recovery admitted, with no developer run.

A body edit on an approved pull request resumes the developer on its own road
(`drift`), launched on the drift road (`implementing/drift_road`), and a
return a live hold, a lost write, or a restart kept from its disposition is
handed here. It is finished by that very disposition (`drift._dispose_drift_result`)
once what its tick settled around the run is staged from the capture
(`implementing/captured_drift.settled_resume`), beside the move to
`validating` the edit owes -- the marker its tick stages with the refreshed
requirements before the run, so no write may make the baseline durable
without it. The report then goes through the existing drift outcome, the
delivery, the size gate, and the exact-revision publication; a pushed fix,
an `ACK:`, and a report with no commit hand the issue back to `validating`
with `review_round` reset, the round accounting this stage keeps, and a park
leaves that move owed for `validating`'s reply road.

The disposition needs the pull request it reads, and the carry of the shared
IssueComment cursor ahead of the report re-reads both surfaces, each a request
of its own behind the admission's readings. So this owner fetches the pull
request and runs the disposition inside `captured_rereads.rereads`: every
reading a handoff's effect stands on is taken again immediately before the
report is handed on, behind all of those requests, and a control applied, a
label moved, a close, an edit, a checkout moved, or a push meanwhile holds the
capture with nothing written, for the next dispatch to decide afresh. A pull
request that would not read holds it too.

What the run's prompt delivered is settled as the capture froze it -- the
issue thread's half of the reading, as this road settles it, its bound
holding the reply boundary below what the excerpt cut -- and the carry of the
shared IssueComment cursor behind it crosses this orchestrator's own posts,
the delivered stretch, and the comments that prompt quoted on either surface:
the capture froze the stretch of each it read (`delivered`), and the comments
inside them are read back into the record the carry alone is handed
(`_DriftResume.carried`), as its own tick's carry is handed the prompt's
record. A comment written after the prompt was read is numbered past those
stretches, so it stays above the cursor for the next scan; a surface that
would not read holds the capture with nothing written.
"""
from __future__ import annotations

import logging
from pathlib import Path

from orchestrator.workflow.engine import (
    completion_recovery_models as _recovery_models,
    drift_delivery as _drift_delivery,
    prompt_delivery as _prompt_delivery,
)
from orchestrator.workflow.stages.implementing import captured_drift as _captured_drift, captured_rereads as _rereads
from orchestrator.workflow.stages.in_review import drift as _drift, models as _models, state as _state

log = logging.getLogger("orchestrator.workflow")

_PR_NUMBER = "pr_number"

# The ends one delivered stretch is spelled as: the issue thread's comes
# first, and a pull request conversation's after it.
_ONE_STRETCH = 2


def recovers(admitted: _recovery_models.AdmittedCompletion) -> bool:
    """Finish the admitted capture through the stage's drift disposition; True, since this tick is its."""
    context = _context(admitted)
    carried = None if context is None else _carried(context, admitted)
    if carried is None:
        return True
    rebuilt = _captured_drift.settled_resume(admitted)
    context.state.set(_state._HANDOFF_PENDING, True)
    run = admitted.capture.run
    with _rereads.rereads(admitted):
        _drift._dispose_drift_result(context, _models._DriftResume(
            worktree=Path(run.worktree),
            dev_result=rebuilt,
            paused=False,
            before_sha=run.before_sha,
            delivery=_captured_drift.frozen_reading(admitted),
            carried=carried,
        ))
    return True


def _context(admitted: _recovery_models.AdmittedCompletion) -> _models._InReviewContext | None:
    """The in_review tick's handles over the admitted reading, its pull request fetched; None where none read."""
    number = int(admitted.state.get(_PR_NUMBER))
    try:
        pull_request = admitted.gh.get_pr(number)
    except Exception:  # noqa: BLE001 - a pull request nobody could fetch holds the capture, never invalidates it
        log.warning(
            "issue=#%d could not fetch the pull request its captured drift resume is finished on; holding the tick",
            admitted.issue.number,
        )
        return None
    return _models._InReviewContext(admitted.gh, admitted.spec, admitted.issue, admitted.state, pull_request, number)


def _carried(
    context: _models._InReviewContext, admitted: _recovery_models.AdmittedCompletion,
) -> _prompt_delivery.PromptDeliverySnapshot | None:
    """The record the cursor carry is handed: what the run's prompt quoted on either surface, read back; None unread.

    Read back over the stretches the capture froze
    (`implementing/drift_road.DriftReading.over_both_surfaces`): the issue
    thread's, above what its excerpt left out and through the newest comment
    it read, and the pull request conversation's, through the newest comment
    it quoted there. Every comment still inside them was quoted, or is
    nobody's input, and one written since the prompt was read is numbered
    past them, so it stays out of this record.
    """
    stretches = admitted.capture.handoff.delivered
    if not stretches:
        return _captured_drift.frozen_reading(admitted)
    try:
        thread, conversation = _read_back(context, stretches)
    except Exception:  # noqa: BLE001 - a surface nobody could read holds the capture, never invalidates it
        log.warning(
            "issue=#%d could not read back the comments its captured drift resume quoted; holding the tick",
            admitted.issue.number,
        )
        return None
    return _drift_delivery._quoted_back(thread, conversation, context.state)


def _read_back(context: _models._InReviewContext, stretches: tuple) -> tuple[list, list]:
    """The comments inside `stretches` on the issue thread and, where they name one, the pull request conversation."""
    pinned = context.state.comment_id
    read = context.gh.comments_after(context.issue, stretches[0], state_comment_id=pinned)
    thread = _inside(read, stretches)
    if len(stretches) == _ONE_STRETCH:
        return thread, []
    return thread, _inside(_drift._drift_unread_pr_conv(context), stretches[_ONE_STRETCH:])


def _inside(comments: list, stretches: tuple) -> list:
    """The `comments` numbered inside the first of `stretches`: above its first end, and through its second."""
    after, through = stretches[:_ONE_STRETCH]
    return [comment for comment in comments if after < comment.id <= through]
