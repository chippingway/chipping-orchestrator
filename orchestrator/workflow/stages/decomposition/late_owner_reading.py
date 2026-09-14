# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Fresh and latched owner-state readings before late-split effects.

An observed close outranks a later reopened issue. A failed or malformed
GitHub reading stays distinct from both an open and a closed owner.
"""
from __future__ import annotations

import logging

from orchestrator.workflow.engine import observations as _observations
from orchestrator.workflow.stages.decomposition.late_models import _LateContext, _OwnerState

log = logging.getLogger("orchestrator.workflow")


# The two states a GitHub issue reports. Anything else -- a shape with no
# state on it, an attribute that raised -- is a read that established nothing,
# which is not the same claim as "open".
_OPEN = "open"
_CLOSED = "closed"


def _read_owner(context: _LateContext) -> _OwnerState:
    """Say which of the three answers this issue gives, latch read first.

    The latch is asked ahead of GitHub because it holds the one reading GitHub
    cannot give back: a poll that found this issue closed while this very
    worker held it could hand that reading to nobody -- the scheduler admits
    no second worker for an issue one is already running -- and a human who
    reopened it in the meantime has taken it off the remote for good. Asking
    costs no request, so every barrier in this mode gets it.

    Otherwise re-fetched rather than read off the snapshot the tick opened
    with, which is the whole point: that snapshot is as old as the run that
    has just finished. The fetch and the state read share one guard, because a
    PyGithub issue is lazy and the request that can fail is as likely to be
    the attribute as the fetch.

    Fails closed twice over. An exception is unreadable, and so is a state
    that is neither of the two GitHub reports -- a shape with no state on it
    would otherwise default to "open" and let the tick publish on the strength
    of a read that established nothing.
    """
    if _latched_close(context):
        return _OwnerState.CLOSED
    try:
        owner_state = _owner_state(context)
    except Exception:
        log.exception(
            "issue=#%d could not be re-read after its late run finished; "
            "not acting on the verdict this tick",
            context.issue.number,
        )
        return _OwnerState.UNREADABLE
    if owner_state == _OPEN:
        return _OwnerState.OPEN
    if owner_state == _CLOSED:
        return _OwnerState.CLOSED
    log.error(
        "issue=#%d reported no readable state after its late run finished; "
        "not acting on the verdict this tick",
        context.issue.number,
    )
    return _OwnerState.UNREADABLE


def _latched_close(context: _LateContext) -> bool:
    """Whether a poll observed this issue closed and nothing has settled it.

    Said out loud when it answers, because it is the one closed reading that
    no request of this run's would ever show and an operator reading the log
    would otherwise see a cycle end against an issue GitHub reports open.
    """
    if not _observations.close_observed(
        context.spec.slug, context.issue.number,
    ):
        return False
    log.warning(
        "repo=%s issue=#%d was observed closed by a poll that could hand the "
        "reading to no worker; ending cycle %d here rather than asking "
        "GitHub, which a reopen since would answer differently",
        context.spec.slug, context.issue.number, context.generation.cycle_id,
    )
    return True


def _owner_state(context: _LateContext) -> str:
    """The state GitHub reports for this issue right now.

    Both shapes the workflow sees are honored, exactly as the dispatcher's own
    closed check honors them: PyGithub's `state`, and the `closed` flag the
    in-memory double carries. The flag is asked first and only when it is set,
    so a shape that merely lacks it does not read as open on its own.
    """
    owner = context.gh.get_issue(context.issue.number)
    if getattr(owner, "closed", False):
        return _CLOSED
    return getattr(owner, "state", "")
