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

The evidence also has to be the repository's own verification: every
configured `VERIFY_COMMANDS` command among its commands, exactly as configured,
exiting 0 (`review_claims.covers_the_configuration`). A reviewer that ran
something else, however green, did not run what the repository requires of a
change, so an approval resting on it parks like one resting on nothing.

The claim's own `passed` and `covers` are the verdict's copy of what the
evidence said when the reviewer returned, and a copy is never what an approval
rests on: they refuse the approval early where they already say no, and
otherwise the evidence answers for itself. Its pass flag is the one the proof
holds to the artifact, and its commands are the artifact's, re-read at the
comment it settled as and held to the record again as the proof held it -- a
record whose flags say more than the pull request shows is no approval.

Commands the reviewer ran therefore count only once their transaction has
SETTLED: posted on the pull request and made current by the reconciliation.
Recorded is not enough. A transaction still owed is a publication that stood
down -- a hold never reaches here, since it ends the tick with the verdict
waiting -- and an approval over evidence nobody could publish would carry the
pull request to `documenting` with nothing on it saying anything ran. A reuse
is held to the same record, since it is only as good as the evidence it names.

Anything short of that refuses the approval, with the reason the park is worded
from (`review_parks`), and an approval it proves reaches the approval arc
(`approves`, `approval`); a proof that could not be read holds instead, for the
next tick to ask again. Last, the pinned comment is read again: evidence
another road recorded or settled while all of that was read is carried onto
the state in hand, so no write behind this puts the older records back, and
refuses the approval, which no longer rests on the current evidence.
"""
from __future__ import annotations

from github.Issue import Issue

from orchestrator import config
from orchestrator.config import models as _config_models
from orchestrator.git.worktrees import naming as _naming
from orchestrator.github.client import GitHubClient
from orchestrator.github.pinned_state import PinnedState
from orchestrator.github.pull_request_reports import ReportPresence
from orchestrator.workflow.engine import (
    verification_current as _current,
    verification_proof as _proof,
    verification_record_state as _record_state,
    verification_records as _records,
    verification_settlement_state as _settlement,
)
from orchestrator.workflow.stages.validating import (
    approval as _approval,
    models as _models,
    review_claims as _claims,
    review_comment as _review_comment,
    review_verdicts as _verdicts,
)

_FAILED = "a command its verification lists did not exit 0"

# Why an approval relying on no claim at all is refused. Which of the refusals
# its declaration earned -- nothing declared, another commit named, a run that
# did not complete -- is the returning tick's to say: the waiting record keeps
# no copy, so a later tick names only what is true of all of them.
_NO_EVIDENCE = "nothing it declared earned verification evidence"

_UNCOVERED = (
    "its verification does not include, exactly as configured and exiting 0, "
    "every command `VERIFY_COMMANDS` requires"
)

_UNPUBLISHED = "its verification evidence could not be published on the pull request"

_REUSE_MOVED = "the evidence it relies on is no longer this issue's current evidence"

_ARTIFACT_MOVED = "its artifact is gone or no longer the one that settled"

_EVIDENCE_MOVED = "the report or evidence records on the pinned comment moved while it was proved"


def approves(gate, run: _models._ReviewerRun, claim: _verdicts.EvidenceClaim | None) -> str | None:
    """Hand an approval relying on `claim` to the approval arc where its evidence proves valid; why not where not.

    As `approval_refusal` answers: "" where the approval arc took it, over
    the gate built on `run`'s checkout, None where the proof could not be
    read, and otherwise the refusal the caller parks the approval for.
    """
    refusal = approval_refusal(gate.gh, gate.spec, gate.issue, gate.state, claim)
    if refusal == "":
        branch = _naming._resolve_branch_name(gate.state, gate.spec, gate.issue.number)
        _approval._finalize_validating_approval(gate, run, branch)
    return refusal


def approval_refusal(
    gh: GitHubClient,
    spec: _config_models.RepoSpec,
    issue: Issue,
    state: PinnedState,
    claim: _verdicts.EvidenceClaim | None,
) -> str | None:
    """Why an approval relying on `claim` may not be acted on; "" where it may, None to hold."""
    refusal = _claimed_refusal(claim)
    if refusal or claim is None:
        return refusal
    current = _settlement.read_current_evidence(state)
    if current is None or (
        current.receipt, current.revision, current.content_revision,
    ) != (claim.receipt, claim.revision, claim.digest):
        return _unsettled_refusal(state, claim)
    proved = _proof.current_evidence_verdict(_proof.ProofReading(gh, spec, issue, state))
    if proved.holds:
        return None
    if not proved.proved:
        return f"{_REUSE_MOVED}: {proved.refusal}"
    refusal = _evidence_refusal(gh, proved.pull_request, current)
    return _held_to_the_comment(gh, issue, state) if refusal == "" else refusal


def _evidence_refusal(
    gh: GitHubClient, pull_request, current: _records.CurrentEvidence,
) -> str | None:
    """Why the settled evidence itself refuses the approval; "" where it may stand, None to hold.

    Read off the artifact on `pull_request`, the one the proof just proved,
    rather than off the claim: the pass flag the proof holds to it, and the
    commands it carries for the configuration's coverage.
    """
    presence, found = gh.reread_verification_artifact(pull_request, current.comment_id)
    if presence is ReportPresence.UNCONFIRMED:
        return None
    if presence is not ReportPresence.PRESENT or not _current._is_the_settled_artifact(found, current):
        return f"{_REUSE_MOVED}: {_ARTIFACT_MOVED}"
    if not current.passed:
        return _FAILED
    return "" if _claims.covers_the_configuration(found.commands) else _uncovered()


def _held_to_the_comment(gh: GitHubClient, issue: Issue, state: PinnedState) -> str | None:
    """Whether the comment still carries the evidence records the approval was proved over; None unread.

    The proof and the artifact's reread are requests long enough for another
    road to record or settle other evidence, which is on the comment and
    nowhere in hand -- and the approval arc writes the state in hand, which
    would put the older records back over it. So the comment is read again,
    and whatever it changed is carried onto the state in hand
    (`review_comment._records_stand`); report, verdict, or evidence records
    among it refuse the approval, which no longer rests on this issue's
    current evidence.
    """
    read = dict(state.data)
    stood = _review_comment._records_stand(gh, issue, state, read, persisted=True)
    if stood is None:
        return None
    moved = not stood or _review_comment._moved(state.data, read, _review_comment._EVIDENCE_RECORDS)
    return f"{_REUSE_MOVED}: {_EVIDENCE_MOVED}" if moved else ""


def _claimed_refusal(claim: _verdicts.EvidenceClaim | None) -> str:
    """Why the claim alone -- before anything is read -- refuses the approval, or ""."""
    if claim is None:
        return _NO_EVIDENCE
    if not claim.passed:
        return _FAILED
    if not claim.covers:
        return _uncovered()
    return ""


def _uncovered() -> str:
    """Why evidence missing a configured command refuses the approval, naming what is required."""
    listed = ", ".join(f"`{command}`" for command in config.VERIFY_COMMANDS)
    return f"{_UNCOVERED}: {listed}"


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
