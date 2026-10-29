# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""An approval over verification evidence that settled on the pull request, as an issue set in review carries it.

The ready ping is taken only over current passing evidence proved again at the
ping, whichever route qualified the head, so a case set in review stands in
the world production leaves there: the report the pull request's delivery
published, a reviewer handed it that returned and approved, and that
reviewer's declared run -- every configured `VERIFY_COMMANDS` command, or the
suite where none are, each exiting 0 -- published on the pull request as a
verification artifact and settled as the current evidence, with the
approval's claim naming it. Every record is written by its own producer, in
the current format, and added to what the case seeded rather than written
through the client, so the tick's own count of writes stays the tick's.

The evidence answers for the head the pull request stands on when it is
seeded, bound to the full tree `TREE` -- the one every commit in the hermetic
checkout reads as -- so a tick proves it over a checkout on this host
(`CHECKOUT`) and a branch fetched standing on that head.
"""
from __future__ import annotations

from orchestrator import config
from orchestrator.github import verification_artifacts as _artifacts
from orchestrator.github.verification_evidence import EvidenceSource, VerifiedCommand
from orchestrator.workflow.engine import (
    comments as _comments,
    report_settlement_state as _report_settlement,
    review_subjects as _review_subjects,
    verification_proof as _proof,
    verification_record_state as _record_state,
    verification_records as _records,
    verification_settlement_state as _settlement,
)
from orchestrator.workflow.stages.validating import (
    approved_evidence as _approved_evidence,
    review_claims as _claims,
    review_verdicts as _verdicts,
)
from orchestrator.workflow.state import WorkflowLabel
from tests.support.fakes import FakeComment, FakeUser
from tests.workflow import published_reports as _published_reports, verdict_values as _verdict_values
from tests.workflow.repo_values import _FAKE_TREE_SHA, EXISTING_CHECKOUT

# The checkout on this host the evidence is proved over, and the full tree every
# commit in it reads as.
CHECKOUT = EXISTING_CHECKOUT

TREE = _FAKE_TREE_SHA

# The stamps the final-docs pass behind an approval leaves -- its verdict, and
# the receipt and lease of a commit it published and still owes the completion
# of -- which the approval itself retires: a case that seeded them is set after
# that pass.
_DOCS_STAMPS = ("docs_checked_sha", "docs_verdict", "docs_settled_sha", "docs_settled_lease")


def proving(github, issue) -> dict:
    """The run options a tick proves the evidence under: the checkout on this host, the branch where the PR stands."""
    head = github.pulls[github.pinned_data(issue.number)["pr_number"]].head.sha
    return {"issue_checkout": CHECKOUT, "fetched_branch_tip": head}


def passing_run() -> tuple[VerifiedCommand, ...]:
    """The reviewer's declared run: every configured command, or the suite where none are, each exiting 0."""
    return tuple(
        VerifiedCommand(command, 0, _verdict_values.REVIEWER_SUITE_OUTPUT)
        for command in tuple(config.VERIFY_COMMANDS) or (_verdict_values.REVIEWER_SUITE,)
    )


def verifies_the_approval(github, issue, commands: tuple[VerifiedCommand, ...] | None = None) -> None:
    """Leave the approval of the report the pull request carries resting on settled evidence of `commands`.

    The reviewer's passing run by default (`passing_run`). The report and the
    review are what `published_reports.approves_the_report` leaves; the
    evidence is minted past every revision the issue has spent, bound to the
    reviewer's subject and the head that report is about, its artifact posted
    on the pull request under this client's login, and settled as the
    reconciliation settles it -- the artifact's comment entered in the ledger
    of this orchestrator's own -- with the approval's claim naming it whole.
    Docs stamps the case seeded are the final-docs pass behind that approval,
    so they stand over it as that pass leaves them.
    """
    documented = _documented(github, issue)
    _published_reports.approves_the_report(github, issue)
    state = github.read_pinned_state(issue)
    ran = passing_run() if commands is None else commands
    pending = _record_state.mint_pending_evidence(state, issue.number, _binding(state), ran)
    if not _record_state.record_pending_evidence(state, pending):
        raise AssertionError("the pinned comment would not record the approval's evidence")
    settled = settles(github, state, pending, WorkflowLabel.VALIDATING)
    _approved_evidence.records(settled, claim_on(pending))
    settled.state_data.update(documented)
    github._pinned[issue.number].state_data.update(settled.state_data)


def _documented(github, issue) -> dict:
    """The docs stamps the case seeded, which the final-docs pass behind the approval leaves standing over it."""
    seeded = github.pinned_data(issue.number)
    return {stamp: seeded[stamp] for stamp in _DOCS_STAMPS if seeded.get(stamp) is not None}


def settles(github, state, pending: _records.PendingEvidence, settled_under: WorkflowLabel):
    """`state` with `pending`, the transaction it records, settled under `settled_under`, as the reconciliation does.

    Its artifact posted on the pull request it names under this client's
    login, and the settlement composed as the reconciliation composes it --
    whatever was current superseded into history -- with the artifact's
    comment entered in the ledger of this orchestrator's own.
    """
    pull = github.pulls[pending.binding.target.publication.pr_number]
    posted = FakeComment(
        id=github._next_comment_id(pull),
        body=_artifacts.render_verification_artifact(pending.artifact),
        user=FakeUser(github._bot_login),
    )
    pull.issue_comments.append(posted)
    settled = _settlement.settled_state(state, pending, posted.id, settled_under)
    _comments._track_orchestrator_comment(settled, posted.id)
    return settled


def _binding(state) -> _records.EvidenceBinding:
    """What the approving reviewer's run is evidence about, as a returned reviewer's declaration binds it.

    The publication is the settled report's own, at the head and requirements
    the reviewer was handed, and the subject is the one that reviewer's return
    recorded.
    """
    report = _report_settlement.read_current_report(state)
    returned = state.get(_review_subjects.RETURNED_SUBJECT)
    if report is None or _review_subjects.ReviewSubject.identity_recorded_in(returned) is None:
        raise AssertionError("no settled report and review are recorded for the evidence to answer for")
    publication = report.subject
    return _records.EvidenceBinding(
        target=_records.EvidenceTarget(publication=publication, subject=returned),
        source=EvidenceSource.REVIEWER_REPORTED,
        tested_sha=publication.source_sha,
        tested_tree=TREE,
        context_revision=_proof.configured_context_revision(),
    )


def claim_on(pending: _records.PendingEvidence) -> _verdicts.EvidenceClaim:
    """The approval's claim on the evidence `pending` settles as, named whole."""
    return _verdicts.EvidenceClaim(
        use=_verdicts.EvidenceUse.PUBLISHED,
        receipt=pending.receipt,
        revision=pending.revision,
        digest=pending.content_revision,
        passed=pending.passed,
        covers=_claims.covers_the_configuration(pending.commands),
    )
