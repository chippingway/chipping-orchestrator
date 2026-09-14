# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Ledger snapshots, reservation correlation, and refusal reasons for budget events.

Unlimited allowances remain explicit in the payload. An unreadable stage cannot
undo an already-durable extension or prevent its budget record from being emitted."""
from __future__ import annotations

import logging
from typing import Any

from github.Issue import Issue

from orchestrator.github.client import GitHubClient
from orchestrator.workflow.engine import run_budget_models as _run_budget_models
from orchestrator.workflow.engine.run_ledger_models import AgentRunLedger
from orchestrator.workflow.state import stage_name

log = logging.getLogger("orchestrator.workflow")


# How much of a launch fingerprint a reservation id carries. Long enough that
# two launch shapes on one issue cannot collide in practice, short enough to
# stay a correlation label rather than a second identity of its own.
FINGERPRINT_HEAD_LENGTH = 12

# What `remaining` says under an allowance that bounds nothing. A word rather
# than a number, because every number a reader could be handed there is one
# they could compare against zero -- and rather than an absent field, because
# a record missing the count is one a consumer cannot tell from a writer that
# dropped it.
REMAINING_UNLIMITED = "unlimited"


def _label_stage(gh: GitHubClient, issue: Issue) -> str | None:
    """Where the issue is standing, or nothing where that could not be read.

    The one field on this stream that costs a request to build, and so the one
    that can fail before either write is attempted. It is asked on the far
    side of a durable grant -- the park is already down and the tick is on its
    way to the stage its label names -- so an exception out of here would not
    merely cost the record, it would break a tick that had already changed
    the issue. That is the failure the guards around the two writes exist to
    prevent, and a read on the way to them has to ride one too.

    A failed read costs the stage and not the record. `stage` is optional in
    both envelopes and a phase with no stage is still countable, while a
    transition nothing recorded is one an operator can never count -- and this
    one has already happened.
    """
    try:
        return stage_name(gh.workflow_label(issue))
    except Exception:
        log.exception(
            "issue=#%s: the stage an agent-run budget extension happened at "
            "could not be read; recording the transition without one",
            getattr(issue, "number", "?"),
        )
        return None


def _ledger_fields(
    phase: _run_budget_models.BudgetPhase, ledger: AgentRunLedger,
) -> dict[str, Any]:
    """The whole budget reading one transition was taken on.

    Every phase carries all of it. A record that reported only the field that
    moved would be one an operator has to join against a setting that may have
    changed since, and the join is not available offline -- which is the whole
    reason the audit copy exists.

    `remaining` is on every record too, including the ones an unlimited
    allowance leaves no count for -- what it carries there is the word rather
    than a number or nothing at all.
    """
    return {
        "phase": phase,
        "configured": ledger.configured,
        "allowance": ledger.allowance,
        "used": ledger.used,
        "remaining": _remaining(ledger),
    }


def _remaining(ledger: AgentRunLedger) -> int | str:
    """What is left of the allowance, said out loud on every record.

    An unlimited ceiling has no count left under it, and the two ways of
    reporting that as a number both mislead: zero reads as an issue that has
    stopped, and any positive figure reads as one about to. Dropping the field
    instead is worse still -- a consumer cannot tell a record that means
    "unbounded" from one a writer, an envelope, or a replay lost the count
    from, and the whole point of the audit copy is answering offline.

    So the field is always there and the unbounded case spells itself.
    `remaining` is therefore an integer or `REMAINING_UNLIMITED`, and a query
    that casts it filters or coalesces that word rather than assuming a
    number.
    """
    if ledger.remaining is None:
        return REMAINING_UNLIMITED
    return ledger.remaining


def _reservation_id(launch: _run_budget_models.AgentRunLaunch, ledger: AgentRunLedger) -> str:
    """The one charge this record is about, as a single joinable label.

    The launch shape alone cannot be it. A fingerprint is deliberately stable
    across ticks -- that is exactly what lets a reservation an earlier tick
    left standing be recognized and reused -- so the same shape is charged
    again every time a launch that already reached `started` comes back, and
    two unrelated charges would carry one id.

    What tells them apart is the count the charge moved. It goes up by one per
    charge and never comes down, so it is the charge's own sequence number on
    this issue: `<launch>-<used>` names one charge, names it the same from
    both phases of it -- the count does not move between them, and a reused
    reservation reports the count its own charge wrote -- and never names two.
    With the envelope's repo and issue around it, that is a key a consumer can
    join `reserved` to `started` on.
    """
    head = launch.fingerprint[:FINGERPRINT_HEAD_LENGTH]
    return f"{head}-{ledger.used}"


def _exhaustion_reason(ledger: AgentRunLedger) -> _run_budget_models.ExhaustionReason:
    """Which of the two ways this allowance ran out.

    Past the ceiling rather than at it is a reading nothing about this issue's
    own runs explains: the count only ever goes up and the allowance is read
    live, so an issue above its ceiling is one the ceiling came down on.
    """
    if ledger.used > ledger.allowance:
        return _run_budget_models.ExhaustionReason.ALLOWANCE_EXCEEDED
    return _run_budget_models.ExhaustionReason.ALLOWANCE_SPENT
