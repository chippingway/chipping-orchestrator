# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Reference-counted publication holds that defer close-observation settlement.

An admitted worker keeps the reading through queueing, refetch, and mutation.
Only its final release spends a deferred settlement, so overlapping workers
and refused polls cannot erase a close still owed to a running publication."""
from __future__ import annotations

import contextlib

from orchestrator.workflow.engine import observation_state as _observation_state


def claim_publication(repo_slug: str, issue_number: int) -> None:
    """Hold this issue's readings for a worker that has been given it.

    Taken where the CLAIM is -- the scheduler admitting a submit -- rather
    than where the worker first reads anything. Between those two lie the
    queue, the refetch and the label checks, and a poll meeting the issue in
    that gap has its own submit refused for the very reason this exists: a
    worker already has it. Dropping the reading there would take it out from
    under a barrier that has not run yet.

    Counted rather than flagged, because the holds nest: the dispatch takes
    one of its own over the whole handler, and the sequential path -- which
    has no claim to inherit -- takes that one alone.
    """
    key = _observation_state._owner_key(repo_slug, issue_number)
    with _observation_state._lock:
        _observation_state._publishing[key] = _observation_state._publishing.get(key, 0) + 1


def release_publication(repo_slug: str, issue_number: int) -> None:
    """Give one hold back, and settle what the last of them postponed.

    What a hold changes is WHEN a drop lands, not whether. Under it a settle
    is recorded rather than taken, and the recorded one is applied as the last
    hold goes -- the same drop, one moment later, where it can no longer be
    taken out from under the barrier it was for. Nothing is kept for good, so
    an issue somebody reopens inherits no latch a later poll would never
    clear.

    The release and the drop it discharges are ONE critical section, because
    between them this owner would be holding neither: a poll latching a fresh
    close there would have it erased by a settlement taken for the reading
    before it, and its receipt memo with it, while the generation moved twice
    for one settlement. So a settle arriving as the last hold goes is either
    under this lock -- deferred, and taken here -- or past it and taken for
    itself, and there is no third moment for it to arrive in.
    """
    key = _observation_state._owner_key(repo_slug, issue_number)
    with _observation_state._lock:
        held = _observation_state._publishing.get(key, 0) - 1
        if held > 0:
            _observation_state._publishing[key] = held
            return
        _observation_state._publishing.pop(key, None)
        if key in _observation_state._deferred:
            _observation_state._deferred.discard(key)
            _observation_state._settled(key)


@contextlib.contextmanager
def publishing(repo_slug: str, issue_number: int):
    """One hold, for a caller whose whole use of it is one block.

    The dispatch takes this over the handler it runs, which is the hold the
    sequential path has and the only one it has. A worker reached through the
    scheduler takes it under the claim that admitted it, and the two nest.
    """
    claim_publication(repo_slug, issue_number)
    try:
        yield
    finally:
        release_publication(repo_slug, issue_number)
