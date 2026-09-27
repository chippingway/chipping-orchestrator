# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What a returned reviewer's verdict is worth, in the order it has to be settled.

No live reviewer round hands its result here yet: the round still acts on its
`VERDICT:` line alone. The recovery that finishes a verdict this service
persisted is live (`review_resume`), and answers only a record already there.

A verdict is acted on only while the whole subject the reviewer was handed --
head, requirements, and report -- still stands. A verdict of a subject that
moved while the reviewer ran is about work that is not there: an approval
would hand it on, and a change request would pay a developer to answer a
review of words the pull request no longer carries. The run is recorded over
whatever settled meanwhile -- the pinned comment read again once the subject
has been resolved, since that resolution is requests of its own -- and the next
tick's reviewer is handed the subject as it stands, or refused.

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
A verdict the comment has no room to persist -- or whose reviewer-reported
transaction it has no room for -- is not acted on at all: it parks under
`reviewer_unrecorded` (`review_parks`), since a disposition nothing durable
backs is one a second reviewer would answer again, and evidence dropped for
room would leave what the reviewer reported, a failed check included, off the
pull request.

Once the publication's requests are over, the subject is held to what stands
again (`review_coverage._verdict_still_stands`): a later report settling on the
same head while the artifact was posted is on the pinned comment and nowhere in
hand, and a verdict acted on over it would post feedback about, and launch a
developer on, words the pull request no longer carries. A change request's
handoff holds it again around its own feedback post (`review_handoffs`), and a
refused approval before it parks, so a push or a later report that landed
meanwhile drops the verdict for a fresh reviewer rather than parking it for a
human.

The evidence is published before the verdict is acted on, on the tick it
returns, and neither verdict is acted on until it is: a publication that holds
or stands down ends the tick with the verdict waiting and the transaction owed,
for the reconciliation ahead of a later tick to publish, and a transaction that
can never settle -- retired, or bound to a verification context that has since
moved -- drops the verdict for a fresh reviewer instead of waiting forever.

A change request stands without evidence -- a reviewer may find a bug without
running anything -- and goes to the developer as it always has. An approval
does not: it reaches the approval arc only once the evidence it relies on is
settled, passing, and proved current (`unverified_approvals`), and parks for a
human otherwise -- while its subject still stands.

Every disposition retires the verdict in the write it makes: the approval arc
in whichever write its road makes, and each park in its own. A change request
keeps it, marked as handed with the agent-run count the developer's launch
will charge past, in a write ahead of the relabel to `workflow:fixing`, and
the writes after that launch drop it -- so a tick that dies anywhere between
that write and the launch leaves the feedback to hand over (`review_resume`)
rather than a round to spend on a second reviewer. A disposition that ends its tick writing
nothing leaves the verdict for the next tick to finish.
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
    verification_records as _records,
    verification_transaction as _transaction,
)
from orchestrator.workflow.stages.implementing import late_records as _late_records
from orchestrator.workflow.stages.validating import (
    approval as _approval,
    models as _models,
    review_claims as _claims,
    review_coverage as _review_coverage,
    review_handoffs as _handoffs,
    review_parks as _parks,
    review_verdicts as _verdicts,
    unverified_approvals as _unverified,
)
from orchestrator.workflow.state import WorkflowLabel

log = logging.getLogger("orchestrator.workflow")

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
    """Persist a returned reviewer's verdict, publish its evidence, and act on it.

    The subject check is requests of its own, long enough for another road to
    settle a later report the state in hand does not carry, so the comment is
    read again against what the run was resolved over before anything is
    written, carrying whatever moved: a write composed over the older records
    would put them back over the newer, and the verdict it persists would be
    handed on as though nothing had. A comment that will not read writes
    nothing.
    """
    run = decision.run
    stands = _review_coverage._verdict_still_stands(gh, issue, state, run.subject, run.resolved_over)
    if stands is None:
        return
    if run.report_moved or not stands:
        gh.write_pinned_state(issue, state)
        return
    in_hand = _persists(state, decision, _claims.claimed_evidence(issue, state, run))
    if in_hand is None:
        log.warning(
            "issue=#%d has no room on its pinned comment to persist its "
            "reviewer's verdict and evidence; parking rather than acting on "
            "them", issue.number,
        )
        _parks.parks_unrecorded(gh, issue, state, run)
        return
    gh.write_pinned_state(issue, state)
    if _publication_holds(gh, spec, issue, state, in_hand):
        log.info(
            "issue=#%d holds its reviewer's verdict until the verification "
            "evidence it declared is confirmed on PR #%s", issue.number, run.pr_number,
        )
        return
    if in_hand.pending is not None and not _still_stands(gh, issue, state, run):
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
    """Carry out a persisted verdict once the evidence it declared is published."""
    if _waits_on_its_evidence(gh, issue, state, in_hand.claim):
        return
    decision = in_hand.decision
    if decision.verdict == _verdicts.CHANGES_REQUESTED:
        _handoffs.hands_the_request_over(gh, spec, issue, state, decision)
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
        # A push, an edit, or a later report since the verdict was last held
        # to its subject refuses the evidence as surely as a failed check, but
        # it is a review of work nobody is asking about: a fresh reviewer
        # answers that without anybody's reply, so only a verdict of the
        # subject standing parks.
        if _still_stands(gh, issue, state, decision.run):
            _parks.parks_unverified(gh, issue, state, decision.run, refusal)
    else:
        _verdicts.drops_the_verdict(state)
        _approval._finalize_validating_approval(
            _late_records._gate(gh, spec, issue, state, decision.run.wt),
            decision.run,
            _naming._resolve_branch_name(state, spec, issue.number),
        )


def _waits_on_its_evidence(
    gh: GitHubClient,
    issue: Issue,
    state: PinnedState,
    claim: _verdicts.EvidenceClaim | None,
) -> bool:
    """Whether the verdict ends this tick on the evidence it declared rather than being acted on.

    Commands the reviewer ran are waited for, whichever the verdict: a change
    request handed to a developer moves the head, and an approval squashes
    it, and either leaves a transaction about the old head that can never
    settle. So a transaction still owed -- a publication that stood down --
    holds the verdict, written nowhere, for the reconciliation ahead of the
    next tick to publish and the tick behind it to finish. One that can never
    settle -- retired, or recorded under a verification context that has since
    moved -- drops the verdict instead, for a fresh reviewer, rather than
    waiting on it forever.
    """
    if claim is None or claim.use is not _verdicts.EvidenceUse.PUBLISHED:
        return False
    standing = _claims.claim_standing(state, claim)
    if standing is _claims.ClaimStanding.SETTLED:
        return False
    if standing is _claims.ClaimStanding.OWED:
        log.info(
            "issue=#%d holds its reviewer's verdict until the verification "
            "evidence it declared is published", issue.number,
        )
        return True
    log.info(
        "issue=#%d drops its reviewer's verdict: the verification evidence it "
        "declared can no longer be published", issue.number,
    )
    _verdicts.drops_the_verdict(state)
    gh.write_pinned_state(issue, state)
    return True


def _still_stands(
    gh: GitHubClient,
    issue: Issue,
    state: PinnedState,
    run: _models._ReviewerRun,
) -> bool:
    """Whether the verdict's subject still stands, dropping the verdict where it moved.

    Asked behind requests long enough to move it: its evidence's publication,
    where this tick published something, and whatever an approval's refusal
    was read over before that refusal parks. A later report settling, or a
    push, meanwhile is a subject nobody reviewed: a change request acted on
    over it would post feedback about words the pull request no longer
    carries and launch a developer on it, and a refused approval would park
    for a human over a review nobody needs. Such a verdict is dropped in a
    write composed over what the comment carries now, for the next tick's
    reviewer; a comment that will not read writes nothing, and the verdict
    waits for the next tick to resolve again.
    """
    stands = _review_coverage._verdict_still_stands(gh, issue, state, run.subject)
    if stands is False:
        log.info(
            "issue=#%d the subject its reviewer's verdict is about moved "
            "before it was acted on; dropping the verdict", issue.number,
        )
        _verdicts.drops_the_verdict(state)
        gh.write_pinned_state(issue, state)
    return bool(stands)


def _persists(
    state: PinnedState,
    decision: _models._ReviewerDecision,
    claimed: _claims.ClaimedEvidence,
) -> VerdictInHand | None:
    """Stage the verdict and the transaction it claims, measured together; None where they cannot be.

    The transaction is measured beside the verdict at its handoff
    (`review_verdicts.records_the_verdict`): its settlement lands while the
    verdict is still waiting, and a change request's handoff behind both. None
    where the comment has no room for the verdict, or for the transaction the
    reviewer's commands were minted as: acted on with nothing durable behind
    it, the verdict would be answered again by a second reviewer the moment
    the tick died, and acted on without its transaction, what the reviewer
    reported -- a failed check included -- would never reach the pull request.
    """
    feedback = decision.feedback if decision.verdict == _verdicts.CHANGES_REQUESTED else ""
    returned = _verdicts.ReturnedVerdict(
        round_n=decision.run.round_n,
        verdict=decision.verdict,
        subject=decision.run.subject.recorded(),
        feedback=feedback,
        evidence=claimed.claim,
    )
    if not _verdicts.records_the_verdict(state, returned, claimed.pending):
        return None
    return VerdictInHand(decision, claimed.claim, claimed.refusal, claimed.pending)


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
