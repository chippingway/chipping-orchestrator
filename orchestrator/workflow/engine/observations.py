# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Latch and settle the closes this process has observed for each issue owner.

The shared state owner keeps every registry under one lock. Receipt claims,
retiring cycles, and publication holds use that same state; a settlement
requested while a publication holds the owner waits for its final release."""
from __future__ import annotations

from orchestrator.workflow.engine import observation_state as _observation_state


def observe_close(repo_slug: str, issue_number: int) -> None:
    """Latch a close this poll saw, so what reads it cannot miss it."""
    with _observation_state._lock:
        _observation_state._observed.add(_observation_state._owner_key(repo_slug, issue_number))


def close_observed(repo_slug: str, issue_number: int) -> bool:
    """Whether a close is latched on this issue and nothing has settled it.

    The barrier every irreversible step of a late cycle is asked past. It
    costs no request, which is why it can be asked as often as there are
    steps.
    """
    with _observation_state._lock:
        return _observation_state._owner_key(repo_slug, issue_number) in _observation_state._observed


def observed_closes(repo_slug: str) -> frozenset[int]:
    """Which of this repo's issues are owed a cleanup pass regardless."""
    with _observation_state._lock:
        return frozenset(
            issue_number
            for held_slug, issue_number in _observation_state._observed
            if held_slug == repo_slug
        )


def settle_close(repo_slug: str, issue_number: int) -> None:
    """Drop a latched close, now that a pass has actually run it.

    Called from the worker that ran the cleanup, once it has returned --
    never from the submit that admitted it. An admitted submit is not a
    cancellation persisted: the worker refetches the issue over GitHub first,
    and a read that fails leaves the cycle unmarked with nothing saying a
    close was ever seen.

    The receipt memo goes with it, so an observation made later against the
    same issue is written down again rather than assumed durable from a
    reading this pass has already discharged. The generation moves in the
    same breath, which is what makes that true of a receipt still being
    posted as this runs: the claim it was taken under is stale from here on,
    and the memo behind it is refused rather than written over the reading
    this settlement just ended.

    DEFERRED while a worker is acting on the issue, because the barriers
    standing immediately before that worker's push read the same latch and the
    publications they guard carry no late cycle for a poll to recognise. The
    drop itself is not refused -- it is taken again on the way out of that
    window, where it is the same decision one moment later -- so nothing is
    kept for good and nothing is dropped out from under the reader it was for.
    """
    key = _observation_state._owner_key(repo_slug, issue_number)
    with _observation_state._lock:
        if key in _observation_state._publishing:
            _observation_state._deferred.add(key)
            return
        _observation_state._settled(key)
