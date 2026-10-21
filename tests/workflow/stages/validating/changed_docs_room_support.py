# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""A pinned comment filled to just the room a docs pass's hand-back leaves, as a human's notes on it might.

The walk is the changed-docs journey's (`changed_docs_journey_support`) cut
short where the hand-back's write died, so the next dispatch hands the docs
commit back from the receipt the gate left. What room that hand-back needs is
measured here by staging it -- through the hand-back's own staging, on a copy
of the comment -- short of the one write a case is about, and the comment is
then padded so that write is exactly what does or does not fit.
"""
from __future__ import annotations

import copy

from orchestrator.github.pinned_state import MAX_PINNED_BODY, PinnedState, pinned_state_body
from orchestrator.workflow.engine import (
    review_subjects as _review_subjects,
    verification_records as _evidence_records,
    verification_settlement_state as _evidence_settlement,
)
from orchestrator.workflow.stages.documenting import handback as _handback, handoff as _handoff, models as _models
from tests.workflow.repo_values import _TEST_SPEC
from tests.workflow.stages.validating.changed_docs_journey_support import DOCS_HEAD

# The field a human fills a pinned comment with.
FILLER = "operator_note"


def fills_with_the_approval_kept(case) -> None:
    """Fill the comment so the hand-back, its approval kept and its evidence not retired, is exactly at the limit.

    Only the approval written null first leaves the retirement room, so a
    hand-back that measured the retirement before clearing it would find none.
    """
    staged = _staged_short_of_the_retirement(case)
    staged.set(_review_subjects.APPROVED_SUBJECT, case.pinned()[_review_subjects.APPROVED_SUBJECT])
    _fills(case, staged, short_by=0)


def fills_up_to_the_retirement(case) -> None:
    """Fill the comment so the hand-back fits, its approval written null, one byte short of retiring the evidence."""
    staged = _staged_short_of_the_retirement(case)
    retired = PinnedState(state_data=copy.deepcopy(staged.data))
    _evidence_settlement.retire_current_evidence(retired)
    before = len(pinned_state_body(staged.data))
    grown = len(pinned_state_body(retired.data)) - before
    _fills(case, staged, short_by=grown - 1)


def makes_room(case) -> None:
    """Take the filler back off the issue's pinned comment, as a human making room does."""
    state = case.github.read_pinned_state(case.issue)
    state.data.pop(FILLER)
    case.github.write_pinned_state(case.issue, state)


def _staged_short_of_the_retirement(case) -> PinnedState:
    """The hand-back of `DOCS_HEAD`, staged on a copy of the comment through its own staging, its evidence kept."""
    staged = PinnedState(state_data=copy.deepcopy(case.pinned()))
    context = _models._DocumentingContext(
        case.github, _TEST_SPEC, case.issue, staged, staged.get("branch"), staged.get("pr_number"),
    )
    rewrite = _handback._published_docs_rewrite(context, DOCS_HEAD)
    _handoff._stamp_docs_verdict(staged, DOCS_HEAD, None)
    current = staged.get(_evidence_records.CURRENT_EVIDENCE)
    staged.set(_evidence_records.CURRENT_EVIDENCE, None)
    _handback._stages_the_handback(context, DOCS_HEAD, rewrite)
    staged.set(_evidence_records.CURRENT_EVIDENCE, current)
    return staged


def _fills(case, staged: PinnedState, short_by: int) -> None:
    """Pad the issue's pinned comment so `staged`, carrying the same filler, comes to `short_by` under the limit."""
    staged.set(FILLER, "")
    padding = MAX_PINNED_BODY - short_by - len(pinned_state_body(staged.data))
    state = case.github.read_pinned_state(case.issue)
    state.set(FILLER, "x" * padding)
    case.github.write_pinned_state(case.issue, state)
