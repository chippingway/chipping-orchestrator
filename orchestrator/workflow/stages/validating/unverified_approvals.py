# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Whether an approval relies on valid verification evidence, and the park where it does not.

An approval reaches the approval arc -- the verify gate, the approval record,
the squash -- only when the evidence it relies on passed and is still what it
claims to be. Commands the reviewer ran on the reviewed head qualify once every
one exited 0 and they were recorded as a transaction, which the dispatcher owes
the pull request from then on. A reuse qualifies only while the evidence it
names is still this issue's CURRENT evidence -- the same receipt, revision, and
digest -- and proves current again (`verification_proof.current_evidence_verdict`):
still the latest revision spent, its handoff and artifact standing, and the
whole binding about this very subject. The proof is taken over the state in
hand, which carries the returned subject this round recorded -- the one a
reviewer's evidence answers for -- and the launch's, which evidence this
orchestrator executed answers for.

Anything short of that is a purported approval. It parks for a human under
`reviewer_unverified`, naming what was missing, and never reaches the arc; a
bare `/orchestrator continue` on the park buys a fresh reviewer, which is who
owes the evidence, while a reply with words in it is requirements the report
never saw and reaches the developer first, as on every reviewer-side park. A
reuse whose proof could not be read holds instead, for the next tick to ask
again.
"""
from __future__ import annotations

from github.Issue import Issue

from orchestrator import config
from orchestrator.config import models as _config_models
from orchestrator.github.client import GitHubClient
from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.engine import (
    guards as _guards,
    verification_proof as _proof,
    verification_settlement_state as _settlement,
)
from orchestrator.workflow.stages.validating import (
    models as _models,
    review_claims as _claims,
    review_verdicts as _verdicts,
    state as _state,
)

_FAILED = "a command its verification lists did not exit 0"

_REUSE_MOVED = "the evidence it reused is no longer this issue's current evidence"

_LAST_REVIEW_SESSION_ID = "last_review_session_id"


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
    if claim.use is _verdicts.EvidenceUse.PUBLISHED:
        return ""
    return _reuse_refusal(gh, spec, issue, state, claim)


def _reuse_refusal(
    gh: GitHubClient,
    spec: _config_models.RepoSpec,
    issue: Issue,
    state: PinnedState,
    claim: _verdicts.EvidenceClaim,
) -> str | None:
    """Why the current evidence a reuse names no longer vouches for it; "" where it does, None to hold."""
    current = _settlement.read_current_evidence(state)
    if current is None or (
        current.receipt, current.revision, current.content_revision,
    ) != (claim.receipt, claim.revision, claim.digest):
        return _REUSE_MOVED
    proved = _proof.current_evidence_verdict(_proof.ProofReading(gh, spec, issue, state))
    if proved.holds:
        return None
    return "" if proved.proved else f"{_REUSE_MOVED}: {proved.refusal}"


def parks_unverified(
    gh: GitHubClient,
    issue: Issue,
    state: PinnedState,
    run: _models._ReviewerRun,
    refusal: str,
) -> None:
    """Park an approval that relies on no valid evidence, dropping the verdict it left."""
    _verdicts.drops_the_verdict(state)
    _guards._park_awaiting_human(
        gh,
        issue,
        state,
        f"{config.HITL_MENTIONS} the reviewer approved without the verification "
        f"evidence an approval requires: {refusal}. The approval was not acted "
        "on; reply `/orchestrator continue` to run a fresh reviewer.",
        reason=_state._REASON_REVIEWER_UNVERIFIED,
        agent_role="reviewer",
        session_id=state.get(_LAST_REVIEW_SESSION_ID),
        review_round=run.round_n,
        retry_count=_guards._safe_int(state.get("retry_count")),
        pr_number=_guards._safe_int(run.pr_number),
        bounded=True,
    )
    # Re-set behind the guard, which clears whatever reason it found: the
    # awaiting-human branch reads it to hand the reply to a fresh reviewer.
    state.set(_state._PARK_REASON, _state._REASON_REVIEWER_UNVERIFIED)
    gh.write_pinned_state(issue, state)
