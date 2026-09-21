# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The reviewer round a fix pays for, whether it is pushed or held.

`review_round` is what `MAX_REVIEW_ROUNDS` counts, and every route through the
fix loop advances it on exactly one event: a head the reviewer has not seen
reaching the pull request. Landed, the push is that event. HELD, the gate has
sent the candidate to the adjudication -- the commit is on the branch, and the
head the reviewer rejected is superseded either way, whether that adjudication
ends in a settlement publishing the commit from there or in the park an
oversized `single` waits for a human on -- so the round is spent just the same.

Either form is handed to the gate rather than applied on the way out. The
hold's last act is the relabel, and a caller that counted afterwards would
lose the count to any crash in that window -- nothing goes back for it, since
a settlement publishes the accepted commit itself and the resumed route finds
nothing left to push. A landed push has the same window one step over:
past the write that records it, the approval and the generation are both gone,
so nothing is left on the comment for a later tick to count a round from.

So the value is read ONCE, before the push, and carried from there. The routes
re-apply that same frozen pair once the call returns, which is a no-op where
the gate already wrote it and the count where a push nothing could name never
reached that write. Re-reading the counter instead would count one round
twice.

One road spends nothing at all: the publication a drift park still owes, where
`in_review` already reset the budget for it. That reset IS the round accounting
of a requirements edit on an approved pull request, and the publication the
edit produced is what the delayed road is finishing -- so counting it again
would charge the same edit twice, once against the approval it invalidated and
once against the budget it earned.
"""
from __future__ import annotations

from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.engine import (
    report_delivery as _report_delivery,
    report_delivery_state as _delivery_state,
    report_record_state as _record_state,
)
from orchestrator.workflow.stages.implementing import (
    late_gate_models as _late_gate_models,
)
from orchestrator.workflow.stages.validating import state as _state


def _next_review_round(state: PinnedState) -> int:
    """The value this counter takes next, spent by a hold or by a push."""
    return int(state.get(_state._REVIEW_ROUND) or 0) + 1


def _spends_next_round(state: PinnedState) -> _late_gate_models._Spends:
    """The round this route lands on, frozen for the gate to close."""
    return _late_gate_models._Spends(fields=(
        (_state._REVIEW_ROUND, _next_review_round(state)),
    ))


def _spends_for_an_owed_publication(state: PinnedState) -> _late_gate_models._Spends:
    """The round a publication a drift park still owes lands on.

    Nothing, where an `in_review` requirements edit already reset the budget
    for exactly this publication: the approval it invalidated is what that
    reset paid for, and the reviewer it hands the work to is owed the full
    count the edit earned rather than that count less the tick it took a
    human to answer the park.

    Nothing either where an owed report's own RECORD carries the round. A
    fixing round that finished on a report froze its bookmarks and its round
    onto that record precisely so the write completing the publication is the
    only thing that spends them -- so a publication counting a round here
    would count the same one twice, and count it a tick before the report it
    belongs to is anywhere.

    The RECORD is asked rather than the debt, because the two part company:
    the drift resume beside this one records a report carrying no bookkeeping
    at all, since its own disposition bumps the round -- and where that push
    failed, the publication a park still owes is the only road left to count
    it. Read off the debt, that reviewer would be handed a head no round was
    ever spent on. Both records, since the debt passes from the delivered one
    to the transaction it becomes and the frozen pairs travel with it.

    The ordinary next round otherwise, which is every debt this stage's own
    roads left: a drift resume that committed without a report parked before
    anything was pushed, so the head the reply finally publishes is one no
    reviewer has read and no round has been spent on.
    """
    if state.get(_report_delivery.OWED_ROUND_RESET):
        return _late_gate_models._SPENDS_NOTHING
    recorded = (
        _delivery_state.read_delivered_report(state)
        or _record_state.read_pending_report(state)
    )
    if recorded is not None and recorded.spends:
        return _late_gate_models._SPENDS_NOTHING
    return _spends_next_round(state)


def _bump_review_round(
    state: PinnedState, owed: _late_gate_models._Spends,
) -> None:
    """Count the round a fix that reached the pull request has spent.

    Applied from the pair the caller froze rather than re-read, so a gate that
    already wrote it beside its receipt is agreed with rather than counted
    past.
    """
    _late_gate_models._spend(state, owed)
