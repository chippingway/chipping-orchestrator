# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Shared process-local state behind close observations and publication holds.

Every registry is protected by the same lock. Settlement advances the owner
generation and clears its observation and receipt memo together; callers hold
the lock so those changes remain atomic with their own gate decisions."""
from __future__ import annotations

import threading

# Closes observed and not yet settled; the ones whose durable receipt is on the
# thread, against the generation it was posted for; the owners a receipt is
# being posted for right now; how many readings of each owner a pass has
# actually settled; and the owners whose thread has been asked about an
# inherited receipt; and the cycle a worker is retiring off each record right
# now. Module-level and lock-guarded, like the running-process registry the
# agent runner keeps: the writer is the polling thread and the readers are
# workers, so the record has to outlive both.
_observed: set[tuple[str, int]] = set()
_receipted: dict[tuple[str, int], int] = {}
_posting: set[tuple[str, int]] = set()
_settlements: dict[tuple[str, int], int] = {}
_scanned: set[tuple[str, int]] = set()
_retiring: dict[tuple[str, int], int] = {}
_publishing: dict[tuple[str, int], int] = {}
_deferred: set[tuple[str, int]] = set()
_lock = threading.Lock()


def _owner_key(repo_slug: str, issue_number: int) -> tuple[str, int]:
    """The one shape every registry here is keyed by."""
    return (repo_slug, int(issue_number))


def _settled(key: tuple[str, int]) -> None:
    """Drop one latched reading, its memo and the generation it was counted at.

    The three go together or the record contradicts itself, so this is the one
    spelling of a settlement and every caller holds the lock across it. The
    caller that postpones one holds it across the release that discharges it
    too: released and settled apart, a poll latching in between would have its
    fresh reading erased by a drop taken for the one before it, and the
    generation would move twice for a single settlement -- which is exactly
    how a receipt already on the thread stops suppressing the next post.
    """
    _observed.discard(key)
    _receipted.pop(key, None)
    _settlements[key] = _settlements.get(key, 0) + 1
