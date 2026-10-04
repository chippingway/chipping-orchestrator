# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Shared process-local state behind close observations and publication holds.

Every registry is protected by the same lock. Settlement advances the owner
generation and clears its observation, the cycle that observation was scoped
to, the moment it was read at, and its receipt memo together; callers hold the
lock so those changes remain atomic with their own gate decisions. Whether a
latched close ends a given cycle is answered here too, under that lock, for
every cancellation barrier and for the retirement window alike."""
from __future__ import annotations

import threading

from orchestrator.scheduler import claim_notes as _claim_notes

# Closes observed and not yet settled; the cycle a read of the record said each
# one ends; a moment no later than the read that found each, where its reader
# knew one; the ones whose durable receipt is on the thread, against the
# generation it was posted for; the owners a receipt is being posted for right
# now; how many readings of each owner a pass has actually settled; and the
# owners whose thread has been asked about an inherited receipt, with the cycle
# it was asked for and the moment it was asked at; and the cycle a worker is
# retiring off each record right now. Module-level and
# lock-guarded, like the running-process registry the agent runner keeps: the
# writer is the polling thread and the readers are workers, so the record has
# to outlive both.
_observed: set[tuple[str, int]] = set()
_scopes: dict[tuple[str, int], int] = {}
_since: dict[tuple[str, int], int] = {}
_receipted: dict[tuple[str, int], int] = {}
_posting: set[tuple[str, int]] = set()
_settlements: dict[tuple[str, int], int] = {}
_scanned: dict[tuple[str, int], tuple[int, int]] = {}
_retiring: dict[tuple[str, int], int] = {}
_publishing: dict[tuple[str, int], int] = {}
_deferred: set[tuple[str, int]] = set()
_lock = threading.Lock()


def _owner_key(repo_slug: str, issue_number: int) -> tuple[str, int]:
    """The one shape every registry here is keyed by."""
    return (repo_slug, int(issue_number))


def _settled(key: tuple[str, int]) -> None:
    """Drop one latched reading with its scope, moment, and memo, and count the drop.

    They go together or the record contradicts itself, so this is the one
    spelling of a settlement and every caller holds the lock across it. The
    caller that postpones one holds it across the release that discharges it
    too: released and settled apart, a poll latching in between would have its
    fresh reading erased by a drop taken for the one before it, and the
    generation would move twice for a single settlement -- which is exactly
    how a receipt already on the thread stops suppressing the next post.
    """
    _observed.discard(key)
    _scopes.pop(key, None)
    _since.pop(key, None)
    _receipted.pop(key, None)
    _settlements[key] = _settlements.get(key, 0) + 1


def _ends(key: tuple[str, int], cycle_id: int, repo_id: int | None) -> bool:
    """Whether the close held under `key` ends this cycle; the caller holds the lock.

    A close scoped to a cycle ends that one. One no read has scoped ends it
    only where, with the repository's id, the claim notes say no other poller
    has held the issue since the moment the latch was read at -- and is scoped
    to it from then on. Spelled once, so a barrier that has to decide under
    this lock answers exactly as one that takes it.
    """
    if key not in _observed:
        return False
    read_at = _since.get(key)
    if key not in _scopes and None not in {repo_id, read_at} and (
        _claim_notes.undisturbed_since(repo_id, key[1], read_at)
    ):
        _scopes[key] = int(cycle_id)
    return _scopes.get(key) == int(cycle_id)
