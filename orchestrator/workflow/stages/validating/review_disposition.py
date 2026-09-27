# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What a returned reviewer's verdict is worth, in the order it has to be settled.

A verdict is acted on only while the whole subject the reviewer was handed --
head, requirements, and report -- still stands. A verdict of a subject that
moved while the reviewer ran is about work that is not there: an approval
would hand it on, and a change request would pay a developer to answer a
review of words the pull request no longer carries. The run is recorded over
whatever settled meanwhile, and the next tick's reviewer is handed the subject
as it stands, or refused.

A verdict of the subject that stands is persisted first, before anything is
published or acted on (`review_verdicts`): the round, verdict, subject, the
feedback a change request hands on, and the evidence the verdict relies on go
down in ONE write beside everything the returned run staged -- its usage,
session, and returned subject, and the reply it settled -- with the
reviewer-reported transaction its commands were minted as recorded in that
same write (`review_claims`). From there nothing asks the reviewer again. A
post of the evidence that GitHub refuses or never confirms is retried by the
dispatcher's own reconciliation (`verification_transaction`), and every step
behind it is finished from the persisted verdict by `review_resume` -- so a
retry reruns no reviewer, folds no usage twice, spends no round, and launches a
developer only where the change request it finishes was never handed to one.

The evidence is published before the verdict is acted on, on the tick it
returns, and a publication that holds ends that tick with the verdict waiting.
Anything else the publication answers lets the verdict go on: the transaction
is recorded and owed to the pull request until the reconciliation settles or
retires it, and a subject that moved is answered by the approval's own
re-checks rather than here.

A change request stands without evidence -- a reviewer may find a bug without
running anything -- and goes to the developer as it always has. An approval
does not: it reaches the approval arc only on evidence that passed, and parks
for a human otherwise (`unverified_approvals`).

Every disposition drops the verdict in the write it makes: the change request
in the relabel to `workflow:fixing` ahead of the developer, the approval arc in
whichever write its road makes, and the park in its own. A disposition that
ends its tick writing nothing leaves the verdict for the next tick to finish.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, replace

from github.Issue import Issue

from orchestrator.config import models as _config_models
from orchestrator.git.worktrees import naming as _naming
from orchestrator.github.client import GitHubClient
from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.engine import (
    verification_record_state as _record_state,
    verification_records as _records,
    verification_transaction as _transaction,
)
from orchestrator.workflow.stages.implementing import late_records as _late_records
from orchestrator.workflow.stages.validating import (
    approval as _approval,
    models as _models,
    requested_changes as _requested_changes,
    review_claims as _claims,
    review_coverage as _review_coverage,
    review_verdicts as _verdicts,
    unverified_approvals as _unverified,
)
from orchestrator.workflow.state import WorkflowLabel

log = logging.getLogger("orchestrator.workflow")

_UNRECORDED = (
    "its verification evidence could not be recorded on the pinned comment, "
    "which has no room for it"
)


@dataclass(frozen=True)
class VerdictInHand:
    """A verdict and the evidence it relies on, ready to be acted on.

    `refusal` says why a declaration earned no evidence, for the park an
    approval without any takes; "" where it earned some or was never asked.
    `pending` is the transaction a published claim names where this tick
    recorded it, which is the one tick that publishes it before acting.
    """

    decision: _models._ReviewerDecision
    claim: _verdicts.EvidenceClaim | None = None
    refusal: str = ""
    pending: _records.PendingEvidence | None = None


def disposes_of_the_verdict(
    gh: GitHubClient,
    spec: _config_models.RepoSpec,
    issue: Issue,
    state: PinnedState,
    decision: _models._ReviewerDecision,
) -> None:
    """Persist a returned reviewer's verdict, publish its evidence, and act on it."""
    run = decision.run
    if run.report_moved or not _review_coverage._subject_still_stands(
        gh, issue, state, run.subject,
    ):
        gh.write_pinned_state(issue, state)
        return
    in_hand, persisted = _persists(
        issue, state, decision, _claims.claimed_evidence(issue, state, run),
    )
    gh.write_pinned_state(issue, state)
    if _publication_holds(gh, spec, issue, state, in_hand) and persisted:
        log.info(
            "issue=#%d holds its reviewer's verdict until the verification "
            "evidence it declared is confirmed on PR #%s", issue.number, run.pr_number,
        )
        return
    # What this tick wrote -- the verdict, and the settlement behind it -- is
    # what every later re-read of the comment is measured against, as the
    # launch's write was: measured against the comment the subject was
    # resolved over, this round's own records would read as another road's
    # and be carried back over the verdict the disposition drops.
    rewritten = replace(run, resolved_over=dict(state.data))
    acts_on_the_verdict(gh, spec, issue, state, replace(
        in_hand, decision=replace(decision, run=rewritten),
    ))


def acts_on_the_verdict(
    gh: GitHubClient,
    spec: _config_models.RepoSpec,
    issue: Issue,
    state: PinnedState,
    in_hand: VerdictInHand,
) -> None:
    """Carry out a persisted verdict whose evidence no longer owes a post this tick."""
    decision = in_hand.decision
    if decision.verdict == _verdicts.CHANGES_REQUESTED:
        _verdicts.drops_the_verdict(state)
        _requested_changes._handle_validating_changes_requested(
            gh, spec, issue, state, decision,
        )
        return
    refusal = in_hand.refusal or _unverified.approval_refusal(
        gh, spec, issue, state, in_hand.claim,
    )
    if refusal is None:
        log.info(
            "issue=#%d could not confirm the evidence its reviewer reused; "
            "holding the approval for the next tick", issue.number,
        )
    elif refusal:
        _unverified.parks_unverified(gh, issue, state, decision.run, refusal)
    else:
        _verdicts.drops_the_verdict(state)
        _approval._finalize_validating_approval(
            _late_records._gate(gh, spec, issue, state, decision.run.wt),
            decision.run,
            _naming._resolve_branch_name(state, spec, issue.number),
        )


def _persists(
    issue: Issue,
    state: PinnedState,
    decision: _models._ReviewerDecision,
    claimed: _claims.ClaimedEvidence,
) -> tuple[VerdictInHand, bool]:
    """Stage the verdict and the transaction it claims, measured together.

    The verdict goes first so the transaction is measured beside it: its
    settlement lands while the verdict is still waiting. A transaction the
    comment has no room for is not recorded and the verdict relies on no
    evidence. A verdict with no room goes unrecorded, which the second answer
    says: nothing would finish it on a later tick, so it is acted on this one
    whatever its publication answers.
    """
    feedback = decision.feedback if decision.verdict == _verdicts.CHANGES_REQUESTED else ""
    returned = _verdicts.ReturnedVerdict(
        round_n=decision.run.round_n,
        verdict=decision.verdict,
        subject=decision.run.subject.recorded(),
        feedback=feedback,
        evidence=claimed.claim,
    )
    staged = _verdicts.records_the_verdict(state, returned)
    if not staged:
        log.warning(
            "issue=#%d has no room on its pinned comment to persist its "
            "reviewer's verdict; acting on it without one", issue.number,
        )
    pending = claimed.pending
    if pending is None or _record_state.record_pending_evidence(state, pending):
        return VerdictInHand(decision, claimed.claim, claimed.refusal, pending), staged
    if staged:
        _verdicts.records_the_verdict(state, replace(returned, evidence=None))
    return VerdictInHand(decision, refusal=_UNRECORDED), staged


def _publication_holds(
    gh: GitHubClient,
    spec: _config_models.RepoSpec,
    issue: Issue,
    state: PinnedState,
    in_hand: VerdictInHand,
) -> bool:
    """Publish the transaction this tick recorded, through the dispatcher's own reconciliation.

    True where that reconciliation holds the tick over a reading nobody could
    take; False where it settled the evidence, retired it, stood down with it
    still owed, or there was nothing to publish.
    """
    if in_hand.claim is None or in_hand.pending is None:
        return False
    return _transaction._reconciles_pending_evidence(
        gh, spec, issue, WorkflowLabel.VALIDATING, state,
    )
