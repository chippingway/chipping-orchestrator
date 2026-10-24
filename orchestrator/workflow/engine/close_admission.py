# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Refuse close observation, recovery, and cleanup over a pinned record admission refused.

The close owners outside the ordinary stage guard -- the receipt a poll, a
refused submit, or a pass's exit posts, the probe deciding whether a reading
is still owed, a contender's tie to a cycle, the closed-owner sweep, and the
check that an ending is over -- each decide on a record read under the
issue's writer claim. One admission refuses (`github.pinned_state`) reads
back empty, which is what an owner no cycle ever touched reads as, so each of
them asks this before deciding anything off it.

A refused record is answered as a read that established nothing: it names no
cycle, and says neither that one is owed nor that nothing is, so the reading
is kept in this process's latch and nothing is written -- no receipt, mark,
adoption, label, terminal, or artifact cleanup -- whatever the latch, a
retirement in flight, or a scope this process holds says about it. The one
trace is a local line naming the repository, the issue, and the version found.
"""
from __future__ import annotations

import logging

from orchestrator.github.pinned_state import PinnedState

log = logging.getLogger("orchestrator.workflow")


def refuses(state: PinnedState, withheld: str) -> bool:
    """Whether `state` is a record admission refused, said locally where it is.

    `withheld` is what the caller does not do over it, for the line that says
    so. A comment that is not authenticated state at all is no record, and
    reads as supported: an issue with no pin is not refused here.
    """
    if state.supported:
        return False
    log.warning(
        "repo=%s issue=#%s pinned comment #%s is %s (found schema_version %r, supported %s: %s); "
        "%s, and leaving the issue, its thread, and its artifacts as they stand",
        state.repo_slug, state.issue_number, state.comment_id, state.admission_status.value,
        state.found_version, state.supported_version, state.refusal_reason, withheld,
    )
    return True
