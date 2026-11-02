# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The room a decomposer manifest correction needs on its pinned comment.

Two measurements, each of a candidate built over what the comment carries and
rendered with every terminator escaped against `MAX_PINNED_BODY`, as the
widest a write over it could be:

- `resolves`: the attempt at its widest resolution -- exhausted beside a
  correction charged at the highest number a record holds, under a floor as
  high. Arming asks this (`correction_checkpoint`): an attempt armed with no
  room to resolve could never be recorded as spent or retired.
- `launches`: that, beside the ledger its one launch leaves behind it -- a
  charge reserved under a fingerprint as wide as any and started at the count
  the launch is owed at, both staged by the run ledger's own writers
  (`run_ledger`), and the receipt the launch's accounting takes
  (`usage_receipts`). Admission asks this before it grants the launch
  (`correction_standing`): the circuit's charge and start, and the checkpoint's
  receipt, land ahead of anything recording what the correction answered, so a
  launch they would leave no room for is a process whose answer nothing could
  record. Where the one charge since the source already stands `reserved`
  (`reserved_since`), that charge is the launch's own to start -- the circuit
  starts it rather than charging again -- so only its start is staged: measured
  as a second charge, a reservation taken right at the limit would read as no
  room for its own start. A reservation one past the source that is another
  launch's is charged over by the circuit, and the count that leaves no longer
  rules the correction's start out (`correction_standing`), so no process is
  started over that measurement either. The usage counters the accounting adds
  to are not measured: what they grow by is the run's to report, and an
  exhaustion they leave no room for still leaves the launch's start on the
  ledger, granting nothing.
"""
from __future__ import annotations

import copy
import dataclasses

from orchestrator.github.pinned_state import MAX_PINNED_BODY, PinnedState, pinned_state_body
from orchestrator.workflow.engine import (
    report_record_values as _record_values,
    run_ledger as _run_ledger,
    run_ledger_models as _run_ledger_models,
    run_ledger_values as _run_ledger_values,
    usage_receipts as _usage_receipts,
)
from orchestrator.workflow.late_split import formats as _formats
from orchestrator.workflow.stages.decomposition import correction_records as _records, state as _state

# The widest number a record holds, which every widest spelling is measured at.
_CEILING = _record_values.MAX_RECORDED_NUMBER

# A launch fingerprint as wide as any: every one is one digest's hex digits.
_WIDEST_FINGERPRINT = "f" * max(_formats.DIGEST_LENGTHS)


def resolves(state_data: dict, attempt: _records.CorrectionAttempt) -> bool:
    """Whether a comment otherwise carrying `state_data` has room for `attempt` at its widest resolution."""
    candidate = PinnedState(state_data=copy.deepcopy(state_data))
    return _fits(candidate, attempt)


def launches(state_data: dict, attempt: _records.CorrectionAttempt) -> bool:
    """Whether it has room for that resolution beside the charge, start, and receipt `attempt`'s launch leaves."""
    candidate = PinnedState(state_data=copy.deepcopy(state_data))
    if not reserved_since(candidate, attempt.owed_at):
        _run_ledger._reserve_run(candidate, _WIDEST_FINGERPRINT)
    _run_ledger._start_reserved_run(candidate, attempt.owed_at)
    receipts = _usage_receipts.read(candidate)
    if receipts is not None:
        widest = dataclasses.replace(attempt.source.invocation, ordinal=_CEILING)
        candidate.set(_usage_receipts.RECEIPTS, receipts.taking(widest).spelled())
    return _fits(candidate, attempt)


def reserved_since(reading: PinnedState, owed_at: int) -> bool:
    """Whether the one charge taken since the source's, at `owed_at`, stands `reserved`, unstarted.

    The charge the circuit honors across a crash for the launch it was taken
    for, which it starts rather than paying again: no start of that launch, and
    the one charge its room is measured by.
    """
    one_past = _run_ledger_values._runs_used_strictly(reading) == owed_at + 1
    return one_past and _run_ledger_values._reservation(reading) is _run_ledger_models.RunPhase.RESERVED


def _fits(candidate: PinnedState, attempt: _records.CorrectionAttempt) -> bool:
    """Whether `candidate`, carrying `attempt` at its widest resolution, renders within one comment."""
    widest = dataclasses.replace(attempt.source.invocation, ordinal=_CEILING)
    resolved = attempt.resolved(_records.CorrectionStage.EXHAUSTED, _CEILING, widest)
    candidate.set(_state._DECOMPOSER_CORRECTION, resolved.spelled())
    return len(pinned_state_body(candidate.state_data, escaped_in_full=True)) <= MAX_PINNED_BODY
