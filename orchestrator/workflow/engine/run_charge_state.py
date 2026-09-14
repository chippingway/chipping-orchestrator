# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Fresh pinned reads and durable state writes at the agent-launch charge boundary.

A failed or unreadable record refuses the launch. Only fields changed by this
charge are merged back into the caller state, preserving its staged changes."""
from __future__ import annotations

import logging
from dataclasses import dataclass

from github.Issue import Issue

from orchestrator.github.client import GitHubClient
from orchestrator.github.pinned_state import PinnedState

log = logging.getLogger("orchestrator.workflow")


# Absence, as a value the merge below can compare against. `None` is a field a
# pinned state legitimately carries, so it cannot stand for one that is not
# there.
_UNSET = object()


@dataclass(frozen=True)
class AgentRunBudget:
    """What a launch has to name for its charge to be askable at all.

    Two objects rather than one, because they answer different halves and
    neither substitutes for the other. The `issue` is what a charge is written
    on, what a park is taken against, and what a notice is said to. The
    `state` is the caller's own in-memory object, which the charge is merged
    back into so the write that dispositions the run at the end of it does not
    hand the issue back the count of one that never launched.
    """

    issue: Issue
    state: PinnedState


def _durable_state(gh: GitHubClient, issue: Issue) -> PinnedState | None:
    """The pinned state a charge may be written onto, or nothing.

    Two readings are refused rather than charged. A request that failed leaves
    no count to charge against at all. A pinned comment that would not parse
    reads back empty, which is indistinguishable from an issue that has spent
    nothing -- so a charge taken on it would both hand the issue a fresh
    lifetime and overwrite whatever the comment was still holding. Neither is
    worth a spawn: an agent run is minutes of somebody's compute, and the poll
    comes back.
    """
    try:
        durable = gh.read_pinned_state(issue)
    except Exception:
        log.exception(
            "issue=#%d could not be read for the agent-run charge its next "
            "launch owes; invoking nothing this tick",
            issue.number,
        )
        return None
    if not durable.parsed:
        log.error(
            "issue=#%d carries a pinned comment that will not parse; invoking "
            "nothing rather than charging an agent run against a count no "
            "read produced",
            issue.number,
        )
        return None
    return durable


def _persist(
    gh: GitHubClient,
    budget: AgentRunBudget,
    durable: PinnedState,
    recorded: dict,
) -> bool:
    """Take one staged phase of the charge durably, and hand it to the caller.

    `recorded` is what the durable state carried before the phase was staged
    on it, so the whole of one phase goes out in one write and the count and
    the launch it was taken for are never on the issue apart. What the caller
    learns is only what this write actually landed: a refused request leaves
    the issue exactly as it was, so nothing is merged and the caller's own
    state goes on describing a charge nobody took.
    """
    try:
        gh.write_pinned_state(budget.issue, durable)
    except Exception:
        log.exception(
            "issue=#%d could not record the agent run its next launch is "
            "charged; invoking nothing rather than spawning a run the ledger "
            "would never see",
            budget.issue.number,
        )
        return False
    _merge_circuit_fields(recorded, durable, budget.state)
    return True


def _merge_circuit_fields(
    recorded: dict, durable: PinnedState, state: PinnedState,
) -> None:
    """Carry this owner's own writes onto the state the caller still holds.

    Scoped by what actually changed between the durable read and the durable
    write, which is the only definition of "this owner's fields" that stays
    true as the park beside it grows a field. Everything else the durable
    state carries is left alone: the caller's copy may hold a staged edit of
    the same field, and this is not the write that decides it.

    Without this the caller's own write at the end of the run would put the
    charge back the way its read found it -- the issue would have paid for the
    run and be handed the count of an issue that never launched one.

    The pinned comment's identity travels with them where the caller has none.
    An issue whose state was created by this write is one the caller would
    otherwise pin a second comment for.
    """
    for key in set(recorded) | set(durable.data):
        written = durable.data.get(key, _UNSET)
        if written == recorded.get(key, _UNSET):
            continue
        if written is _UNSET:
            state.data.pop(key, None)
        else:
            state.set(key, written)
    if state.comment_id is None:
        state.comment_id = durable.comment_id
