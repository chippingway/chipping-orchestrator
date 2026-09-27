# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Whether an approval relies on verification evidence that passed and is current.

An approval reaches the approval arc -- the verify gate, the approval record,
the squash -- only when the evidence it relies on passed and is the evidence
the pull request carries now. Either way it relies on it, that is one question:
the claim has to name this issue's CURRENT evidence exactly -- the same
receipt, revision, and digest -- and that evidence has to prove current again
(`verification_proof.current_evidence_verdict`): still the latest revision
spent, its handoff and artifact standing, and the whole binding about this very
subject. The proof is taken over the state in hand, which carries the returned
subject this round recorded -- the one a reviewer's evidence answers for -- and
the launch's, which evidence this orchestrator executed answers for.

Commands the reviewer ran therefore count only once their transaction has
SETTLED: posted on the pull request and made current by the reconciliation.
Recorded is not enough. A transaction still owed is a publication that stood
down -- a hold never reaches here, since it ends the tick with the verdict
waiting -- and an approval over evidence nobody could publish would carry the
pull request to `documenting` with nothing on it saying anything ran. A reuse
is held to the same record, since it is only as good as the evidence it names.

Anything short of that refuses the approval, with the reason the park is worded
from (`review_parks`); a proof that could not be read holds instead, for the
next tick to ask again.
"""
from __future__ import annotations

from github.Issue import Issue

from orchestrator.config import models as _config_models
from orchestrator.github.client import GitHubClient
from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.engine import (
    verification_proof as _proof,
    verification_record_state as _record_state,
    verification_settlement_state as _settlement,
)
from orchestrator.workflow.stages.validating import review_claims as _claims, review_verdicts as _verdicts

_FAILED = "a command its verification lists did not exit 0"

_UNPUBLISHED = "its verification evidence could not be published on the pull request"

_REUSE_MOVED = "the evidence it relies on is no longer this issue's current evidence"


def approval_refusal(
    gh: GitHubClient,
    spec: _config_models.RepoSpec,
    issue: Issue,
    state: PinnedState,
    claim: _verdicts.EvidenceClaim | None,
) -> str | None:
    """Why an approval relying on `claim` may not be acted on; "" where it may, None to hold."""
    if claim is None:
        return _claims.NO_DECLARATION
    if not claim.passed:
        return _FAILED
    current = _settlement.read_current_evidence(state)
    if current is None or (
        current.receipt, current.revision, current.content_revision,
    ) != (claim.receipt, claim.revision, claim.digest):
        return _unsettled_refusal(state, claim)
    proved = _proof.current_evidence_verdict(_proof.ProofReading(gh, spec, issue, state))
    if proved.holds:
        return None
    return "" if proved.proved else f"{_REUSE_MOVED}: {proved.refusal}"


def _unsettled_refusal(state: PinnedState, claim: _verdicts.EvidenceClaim) -> str:
    """Why a claim naming no current evidence refuses the approval.

    A published claim whose transaction is still the one owed is evidence
    that never reached the pull request; anything else is evidence that did
    and has since been superseded or retired.
    """
    pending = _record_state.read_pending_evidence(state)
    owed = pending is not None and pending.receipt == claim.receipt
    if claim.use is _verdicts.EvidenceUse.PUBLISHED and owed:
        return _UNPUBLISHED
    return _REUSE_MOVED
