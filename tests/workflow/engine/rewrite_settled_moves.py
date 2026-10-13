# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What another road does under issue #7's settled evidence while a readiness primitive reads or writes it.

Each is handed the settled case (`rewrite_captured_test_support.SettledEvidenceCase`):
the issue's requirements edited, a later report about the landed head settled
and handed a reviewer, another command configured, a record written over the
pinned comment as it stands, a newer transaction recorded beside the evidence,
or the evidence retired by another road's own write. `raced_past` makes one of
them just behind one call of a client step, inside the window a primitive
opens between a reading and what it does behind it.
"""
from __future__ import annotations

from functools import partial
from unittest.mock import patch

from orchestrator import config
from orchestrator.workflow.engine import (
    verification_record_state as _record_state,
    verification_records as _records,
    verification_settlement_state as _settlement,
)
from tests.workflow.engine import (
    verification_evidence_test_support as support,
    verification_record_test_support as record_support,
    verification_report_fixture as report,
)
from tests.workflow.interleaving import _RacesPastTheCall


def edits_the_requirements(case) -> None:
    """Edit the issue's body, as its author would."""
    case.issue.body = "Also cover a base that moved twice."


def reviews_again(case) -> None:
    """Settle report 3 of the landed head and hand a reviewer it, over the comment as it stands."""
    case.rereads()
    report.settles_report(case, 3, report.LATER_REPORT_TEXT, head=case.head)
    case.gh.write_pinned_state(case.issue, case.state)


def reconfigures(case) -> None:
    """Configure another command for the rest of the case."""
    case.enterContext(patch.object(config, "VERIFY_COMMANDS", ("echo another",)))


def writes_over(case, key: str, written) -> None:
    """Another road's write of `key` over the pinned comment as it stands."""
    state = case.gh.read_pinned_state(case.issue)
    state.set(key, written)
    case.gh.write_pinned_state(case.issue, state)


def records_a_newer_one(case, *, abandoned: bool = False) -> _records.PendingEvidence:
    """Another road's newer transaction for the head, recorded beside the settled evidence; that transaction.

    `abandoned` retires it into history in the same write, its revision spent
    past the settled evidence with nothing pending beside it.
    """
    state = case.gh.read_pinned_state(case.issue)
    newer = _record_state.mint_pending_evidence(
        state, support.ISSUE_NUMBER, case.settled.binding, (record_support.ran(),),
    )
    case.assertTrue(_record_state.record_pending_evidence(state, newer))
    if abandoned:
        case.assertTrue(_settlement.retire_pending_evidence(state, newer))
    case.gh.write_pinned_state(case.issue, state)
    return newer


def retires_it(case) -> None:
    """Another road's invalidation of the settled evidence, over the comment as it stands."""
    state = case.gh.read_pinned_state(case.issue)
    case.assertTrue(_settlement.retire_current_evidence(state))
    case.gh.write_pinned_state(case.issue, state)


def raced_past(case, step: str, move, nth: int = 1):
    """The client's `step` patched to make `move` once, just behind its `nth` call."""
    racing = _RacesPastTheCall(getattr(case.gh, step), nth, partial(move, case))
    return patch.object(case.gh, step, racing)
