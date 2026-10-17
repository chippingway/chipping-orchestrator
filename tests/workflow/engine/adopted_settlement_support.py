# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Another road settling issue #7's captured run just as a finish posts it, and what it leaves beside that settlement.

Each is handed the captured-run case (`rewrite_verification_recovery_support.CapturedRunCase`)
and the run its finish recorded, and made just behind the post of that run's
artifact: the settlement alone over the artifact just posted
(`settles_the_run`), left unwritten for a caller to move more beside it, or
written with the records beside it out of step -- a newer transaction
recorded and retired, spending a revision past the run
(`spends_a_revision_past`), or the handoff that names the run dropped
(`drops_the_handoff`). The evidence phase and the whole coordinator are both
asked over these.
"""
from __future__ import annotations

from orchestrator.workflow.engine import (
    verification_carries as _carries,
    verification_record_state as _record_state,
    verification_records as _records,
    verification_settlement_state as _settlement,
)
from tests.workflow.engine import (
    rewrite_finish_git_support as git_support,
    rewrite_verification_recovery_support as support,
)


def settles_the_run(case: support.CapturedRunCase, captured):
    """Settle `captured` over the artifact just posted, as another road would; the comment it left, unwritten."""
    state = case.gh.read_pinned_state(case.issue)
    posted = case.pull_request.issue_comments[-1]
    settled_comment = _settlement.settled_state(state, captured, posted.id, git_support.REVIEWING)
    case.assertIsNotNone(settled_comment)
    return settled_comment


def spends_a_revision_past(case: support.CapturedRunCase, captured) -> None:
    """Settle `captured`, then record a newer transaction and retire it, raising the floor past the run."""
    state = settles_the_run(case, captured)
    newer = _record_state.mint_pending_evidence(state, git_support.ISSUE, case.source.binding, captured.commands)
    case.assertTrue(_record_state.record_pending_evidence(state, newer))
    case.assertTrue(_carries.abandons(state, newer))
    case.gh.write_pinned_state(case.issue, state)


def drops_the_handoff(case: support.CapturedRunCase, captured) -> None:
    """Settle `captured`, then drop the handoff that names it."""
    state = settles_the_run(case, captured)
    state.set(_records.EVIDENCE_HANDOFF, None)
    case.gh.write_pinned_state(case.issue, state)
