# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Mint the identity of each actual agent process invocation, and read the cycle it binds to.

The identity names the record the process belongs to -- repository, issue, and
the pinned comment its charge was written on -- the workflow cycle that record
was on, and the charge itself.

A request's fingerprint names the logical round a charge is recognized by
across ticks and is the same for every attempt at it, and a CLI session id is
optional and shared by every resume of one conversation, so neither tells apart
two processes started for an identical request. The tracked spawn mints one
identity per process instead (`agents.models.AgentInvocation`), over the
durable reading its charge was started on, and stamps it on the result that
process returns; usage accounting is keyed by it (`usage_checkpoint`).

Nothing is written here: the charge's own start is the durable record the
ordinal stands on. That start is taken once per charge and only ever over a
`reserved` one, so no two processes are started under one charge, and the count
it carries is never refunded or reused -- a restart keeps it -- which is what
orders an issue's invocations across ticks and cycles.
"""
from __future__ import annotations

import secrets

from orchestrator.agents.models import AgentInvocation
from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.engine import run_ledger_values as _run_ledger_values
from orchestrator.workflow.late_split import keys as _late_keys, payloads as _late_payloads

# The random half of an identity, in bytes; spelled as twice as many hex digits.
NONCE_BYTES = 8


def cycle_of(state: PinnedState) -> int | None:
    """The workflow cycle a pinned record is on: its late cycle identity, 0 where it names none, None where damaged.

    A restart rewrites the comment in place under a freshly minted cycle, so
    the comment id alone cannot tell the cycle an invocation ran in from the
    one the record has moved on to. Only an absent field is no cycle -- the
    late writer leaves an unset identity out rather than spelling it -- so a
    present one that is no positive whole number is damage, never the absent
    cycle 0.
    """
    if not state.carries(_late_keys.CYCLE_ID):
        return 0
    return _late_payloads.as_identity(state.get(_late_keys.CYCLE_ID))


def minted(started: PinnedState, issue_number: int) -> AgentInvocation:
    """The identity of the one process about to be started over `started`, the reading its charge was started on.

    The repository is the one that reading was taken under, the comment the
    one the start was written on, and the ordinal the lifetime count its charge
    stands at -- the larger of the two meters, as every reader of that count
    takes it.
    """
    return AgentInvocation(
        repo=started.repo_slug or "",
        issue=issue_number,
        comment=started.comment_id,
        cycle=cycle_of(started),
        ordinal=_run_ledger_values._runs_used(started),
        nonce=secrets.token_hex(NONCE_BYTES),
    )
