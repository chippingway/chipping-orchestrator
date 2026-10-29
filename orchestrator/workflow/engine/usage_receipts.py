# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Which agent invocations an issue's usage meter already covers: the bounded receipt ledger.

One pinned field, `issue_usage_receipts`, written in the same commit as the
increment it receipts (`usage_checkpoint`) and spelled
`{"floor": <count>, "recent": [[<ordinal>, "<nonce>"], ...]}`. An invocation is
covered where its ordinal and nonce are one of the `recent` pairs, or its
ordinal is at or below `floor`. The ordinal is the lifetime charge the process
was started under, which orders an issue's invocations and is never reused
(`invocations`), so the floor needs no list behind it.

Bounded by retirement: past `RETAINED_RECEIPTS` pairs, taking another retires
the lowest-ordinal ones and raises the floor to the highest ordinal retired. A
retired invocation is still covered, so a retry, a lost response, or a later
settlement of it adds nothing however many receipts came after. What a
retirement costs is the other direction: an invocation never accounted while
the floor passed it can no longer be, which is an undercount and never a second
count.

Read strictly. Absent is an issue that accounted nothing; anything else this
build would not write -- `null`, a flag or a negative for a count, a nonce of
another shape, pairs out of order, at or below the floor, or past the bound --
is damaged, answered None, and neither counted on nor written over.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from orchestrator.agents.models import AgentInvocation
from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.engine import invocations as _invocations, run_ledger_values as _run_ledger_values

RECEIPTS = "issue_usage_receipts"

# How many receipts the ledger keeps before retiring the oldest under its floor.
RETAINED_RECEIPTS = 16

_FLOOR = "floor"
_RECENT = "recent"
_NONCE_DIGITS = 2 * _invocations.NONCE_BYTES
_NONCE = re.compile(f"[0-9a-f]{{{_NONCE_DIGITS}}}")

# One receipt: the invocation's ordinal, and its nonce.
_Receipt = tuple[int, str]


@dataclass(frozen=True)
class UsageReceipts:
    """One issue's receipt ledger: the floor every retired receipt is under, and the receipts kept above it."""

    floor: int = 0
    recent: tuple[_Receipt, ...] = ()

    def covers(self, invocation: AgentInvocation) -> bool:
        """Whether `invocation`'s usage is already this issue's: receipted, or at or under the floor."""
        if invocation.ordinal <= self.floor:
            return True
        return (invocation.ordinal, invocation.nonce) in self.recent

    def taking(self, invocation: AgentInvocation) -> UsageReceipts:
        """This ledger with `invocation` receipted, retiring the lowest ordinals past the bound under the floor."""
        receipts = sorted({*self.recent, (invocation.ordinal, invocation.nonce)})
        retired = [receipt[0] for receipt in receipts[:-RETAINED_RECEIPTS]]
        floor = max((self.floor, *retired))
        kept = tuple(receipt for receipt in receipts if receipt[0] > floor)
        return UsageReceipts(floor, kept)

    def spelled(self) -> dict[str, Any]:
        """The ledger as the pinned comment carries it."""
        return {_FLOOR: self.floor, _RECENT: [list(receipt) for receipt in self.recent]}


def read(state: PinnedState) -> UsageReceipts | None:
    """The receipt ledger `state` carries: empty where it carries none, None where it is damaged."""
    if not state.carries(RECEIPTS):
        return UsageReceipts()
    raw = state.get(RECEIPTS)
    if not isinstance(raw, dict) or set(raw) != {_FLOOR, _RECENT}:
        return None
    floor = _run_ledger_values._counted(raw[_FLOOR])
    receipts = _receipts(raw[_RECENT])
    if floor is None or receipts is None:
        return None
    if any(ordinal <= floor for ordinal, _nonce in receipts):
        return None
    return UsageReceipts(floor, receipts)


def _receipts(raw: Any) -> tuple[_Receipt, ...] | None:
    """The kept receipts as this ledger writes them -- distinct, in order, and within the bound -- or None."""
    if not isinstance(raw, list) or len(raw) > RETAINED_RECEIPTS:
        return None
    receipts = tuple(_receipt(entry) for entry in raw)
    if None in receipts or list(receipts) != sorted(set(receipts)):
        return None
    return receipts


def _receipt(entry: Any) -> _Receipt | None:
    """One receipt as this ledger writes it -- a count and a nonce of the minted shape -- or None."""
    if not isinstance(entry, list) or len(entry) != 2:
        return None
    ordinal, nonce = entry
    if _run_ledger_values._counted(ordinal) is None or not isinstance(nonce, str):
        return None
    return (ordinal, nonce) if _NONCE.fullmatch(nonce) else None
