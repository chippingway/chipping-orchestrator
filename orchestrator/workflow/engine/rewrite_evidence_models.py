# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What the evidence policy of a landed automatic base rewrite decided, and what it decided on.

Five routes rather than a pass and a fail, because what the finish owes the
landed head differs for each and a caller that could not tell them apart would
either route a head over a claim nobody proved or strand it behind evidence
nobody can produce:

- FRESH is a passing run of the configured `VERIFY_COMMANDS` on the rewritten
  head itself, bound as orchestrator-executed evidence of it
  (`verification_local_runs`): the commands that ran, their exit statuses, and
  their outputs, exactly as the runner recorded them.
- CARRIED is the current evidence carried onto the rewritten head on a proved
  equivalence (`verification_carry_forward`): the tested commit and tree kept,
  the rewritten head its target, and the source receipt its transcript was
  copied from.
- REVIEWER records no local evidence at all: nothing ran -- an empty
  configuration, or a target binding not yet available -- or what ran binds
  nothing. The fresh reviewer the head is routed to owes the evidence through
  its own declaration, which is the road an empty configuration has always
  taken; nothing here says any check passed.
- FAILED is the configured commands run on the rewritten head and not
  passing. The run is kept whole, so the failing command, its status, and its
  output stay what a park quotes.
- MOVED is a result something it is bound to moved under while the commands
  ran -- a head, the requirements, the report or the review subject, the
  configuration -- a run whose own baseline was another commit, tree, or
  context than the one planned for it, or one nobody could read again after.
  It is eligible for nothing, whatever it said, and the run is kept only for
  the log.

Beside the route, `invalidates` says the rewrite moved the full tree or the
verification context the current evidence was taken under, so that evidence
no longer answers for the pull request on any route: it goes into history as
INVALIDATED with its whole binding (`stages`), never relabelled as a run on
the new head. Equivalence is what spares it, and only a carry then supersedes
it.

Data and the one staging it implies, nothing that writes. The policy that
decides it is `rewrite_evidence`.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from orchestrator.git.verification.models import VerifyResult
from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.engine import (
    verification_carry_forward as _carry_forward,
    verification_local_runs as _local_runs,
    verification_settlement_state as _settlement,
)
from orchestrator.workflow.engine.report_evidence_models import ReportEvidence


class RewriteEvidenceRoute(StrEnum):
    """Which evidence the landed head of an automatic base rewrite is routed with."""

    FRESH = "fresh"
    CARRIED = "carried"
    REVIEWER = "reviewer"
    FAILED = "failed"
    MOVED = "moved"


@dataclass(frozen=True)
class RewriteEvidence:
    """One evidence decision for a landed rewrite.

    `refusal` is why no evidence is recorded -- on REVIEWER, the binding
    unavailable, the configuration empty, or a run that binds nothing; on
    MOVED, what moved or could not be read again -- in the proof's own
    verdicts, so a reading nobody could take still HOLDS. `run` is the run
    made of the rewritten head, None where nothing ran. `fresh` is what a
    FRESH run binds and `carry` what a CARRIED decision licenses.
    """

    route: RewriteEvidenceRoute
    invalidates: bool = False
    refusal: ReportEvidence | None = None
    run: VerifyResult | None = None
    fresh: _local_runs.LocalRunEvidence | None = None
    carry: _carry_forward.CarryForward | None = None

    @property
    def reason(self) -> str:
        """The sentence `refusal` refuses with, or "" where nothing was refused."""
        return "" if self.refusal is None else self.refusal.refusal

    def stages(self, state: PinnedState) -> bool:
        """Retire the current evidence into history where this decision invalidates it; whether it moved.

        Through the settlement owner's own retirement, so the record keeps its
        whole binding and the comment's room is measured; False, with the
        state untouched, where nothing is invalidated. The caller writes.
        """
        return self.invalidates and _settlement.retire_current_evidence(state)
