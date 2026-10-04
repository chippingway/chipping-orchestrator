# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Latch and settle the closes this process has observed for each issue owner.

The shared state owner keeps every registry under one lock. Receipt claims,
retiring cycles, and publication holds use that same state; a settlement
requested while a publication holds the owner waits for its final release. A
latched close is scoped to the cycle it ends, so a close another poller on
this host settled cannot end the cycle that poller started after it, and one
no read could tie to a cycle ends none until a read does."""
from __future__ import annotations

from orchestrator.workflow.engine import observation_state as _observation_state


def observe_close(
    repo_slug: str, issue_number: int, read_at: int | None = None,
) -> None:
    """Latch a close this poll saw, so what reads it cannot miss it.

    `read_at` is a moment no later than the read that found the issue closed,
    where its reader knew one (`claim_notes.moment`). A latch keeps the latest
    moment it is given. Each is a closed reading, and what one proves -- that
    no other poller has held the issue since it was taken -- the newest
    proves soonest: a close read again after another poller restarted the
    cycle is a close of the fresh cycle, which an older moment would never
    tie to it.
    """
    key = _observation_state._owner_key(repo_slug, issue_number)
    with _observation_state._lock:
        _observation_state._observed.add(key)
        if read_at is not None:
            moment = int(read_at)
            _observation_state._since[key] = max(moment, _observation_state._since.get(key, moment))


def scope_close(repo_slug: str, issue_number: int, cycle_id: int) -> None:
    """Say which cycle the close held on this issue ends.

    Taken only where a read of the record is followed by a read of the issue
    that still finds it closed, or where both are taken under this process's
    writer claim: either way the issue was closed while the record named this
    cycle, so this is the cycle a close ends. A record read after a closed
    reading proves nothing of the kind -- another poller on this host may have
    settled the cycle that close ended and started a fresh one in between, an
    operator's restart being exactly that -- and only the scope tells a close
    that ended the old one from a close that ends the new one.
    """
    with _observation_state._lock:
        _observation_state._scopes[_observation_state._owner_key(repo_slug, issue_number)] = int(cycle_id)


def close_ends(
    repo_slug: str, issue_number: int, cycle_id: int, *, repo_id: int | None = None,
) -> bool:
    """Whether the close held on this issue is one that ends this cycle.

    A close scoped to a cycle ends that one. One no read has tied to a cycle
    -- its record could not be read, or the issue was open again by the read
    that would have confirmed it -- ends the cycle it is asked about only where
    no other poller has held the issue since it was read. Asked under the
    issue's writer claim, with the repository's id: every hold of another
    poller this process has found on the key having ended before the moment
    the latch was read at says the record the asker holds is the one the close
    was read against, and the close is scoped to that cycle from then on.
    Anywhere else it ends none, since the cycle it is asked about may be one
    another poller started after it; it is still held, routing the issue to a
    pass under the claim.
    """
    key = _observation_state._owner_key(repo_slug, issue_number)
    with _observation_state._lock:
        return _observation_state._ends(key, cycle_id, repo_id)


def close_scope(repo_slug: str, issue_number: int) -> int | None:
    """The cycle the close held on this issue ends, or `None` if none is known.

    `None` both where no close is held and where one is held that no read has
    tied to a cycle -- the two a caller holding other proof of the cycle
    answers alike.
    """
    key = _observation_state._owner_key(repo_slug, issue_number)
    with _observation_state._lock:
        if key not in _observation_state._observed:
            return None
        return _observation_state._scopes.get(key)


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
