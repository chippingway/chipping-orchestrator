# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What a returned-verdict case reads back off the in-memory client, and the records it seeds.

What the issue has spent, the artifacts and reviewer feedback on the pull
request, and -- the two things a case seeds rather than reads -- evidence an
earlier round left current for the subject the next reviewer is handed, and a
verdict an earlier tick left waiting over it, for the world
`review_verdict_test_support` builds.
"""
from __future__ import annotations

from dataclasses import replace
from functools import partial

from orchestrator.github import verification_artifacts as _artifacts, verification_evidence as _evidence
from orchestrator.workflow.engine import (
    report_settlement_state as _report_settlement,
    verification_proof as _proof,
    verification_record_state as _record_state,
    verification_records as _records,
)
from orchestrator.workflow.stages.validating import models as _models, review_verdicts as _verdicts
from tests.workflow.stages.validating import review_verdict_test_support as _world

# What the issue has spent: runs charged, usage folded, rounds.
_SPENT = ("agent_runs_used", "issue_agent_runs", "issue_total_tokens", "review_round")

_RETURNED_SUBJECT = "review_returned_subject"

# What the reviewer's feedback post says about itself.
FEEDBACK_NOTICE = "requested changes"


def spent(case) -> tuple:
    """What `case`'s issue has spent so far, in `_SPENT` order."""
    pinned = case.pinned()
    return tuple(pinned.get(key) for key in _SPENT)


def artifacts(case) -> list:
    """Every verification artifact on `case`'s pull request, oldest first."""
    readings = (
        _artifacts.verification_artifact_from_comment(posted, bot_login=case.github._bot_login)
        for posted in case.pull_request.issue_comments
    )
    return [found for found in readings if found is not None]


def current_report_revision(case) -> int:
    """The revision of the developer report `case`'s pinned comment records as current."""
    return _report_settlement.read_current_report(case.github.read_pinned_state(case.issue)).report_revision


def current_evidence_revision(case) -> int:
    """The revision of the verification evidence `case`'s pinned comment records as current."""
    return case.pinned()["verification_evidence_current"]["revision"]


def feedback_posts(case) -> list[str]:
    """Every reviewer-feedback comment posted on `case`'s pull request."""
    return [body for _, body in case.github.posted_pr_comments if FEEDBACK_NOTICE in body]


def settles_evidence(
    case, *, command: str = _world.SUITE, exit_status: int = 0,
) -> _records.PendingEvidence:
    """Settle one run of `command` for the subject `case`'s next reviewer is handed; the transaction.

    As an earlier round leaves it: a reviewer handed that subject returned over
    it, and its declared run was recorded and made current by the dispatcher's
    own reconciliation.
    """
    state = case.github.read_pinned_state(case.issue)
    subject = case.handed(state).subject
    state.set(_RETURNED_SUBJECT, subject.recorded())
    report = _report_settlement.read_current_report(state)
    binding = _records.EvidenceBinding(
        target=_records.EvidenceTarget(
            publication=replace(report.subject, requirements_revision=subject.requirements_revision),
            subject=subject.recorded(),
        ),
        source=_evidence.EvidenceSource.REVIEWER_REPORTED,
        tested_sha=_world.HEAD,
        tested_tree=_world.TREE,
        context_revision=_proof.configured_context_revision(),
    )
    pending = _record_state.mint_pending_evidence(
        state, _world.ISSUE, binding, (_evidence.VerifiedCommand(command, exit_status, _world.SUITE_OUTPUT),),
    )
    _record_state.record_pending_evidence(state, pending)
    case.github.write_pinned_state(case.issue, state)
    case._run(partial(_world.reconciles, case), run_agent=[])
    return pending


def seeds_a_verdict(
    case, settled: _records.PendingEvidence, verdict: str = _verdicts.APPROVED, *, reused: bool = False,
) -> None:
    """Leave waiting `verdict` of the standing subject, whose claim names `settled` and says it passed and covers.

    The claim is the transaction's own publication, or a reuse of it where
    `reused` says so.

    Whatever the evidence itself shows: the record a tick finishes a verdict
    from, written as nothing but the reviewer's own copy of what it relied on,
    and returned by a reviewer handed that subject -- a change request with
    the feedback the world's reviewer asks for.
    """
    state = case.github.read_pinned_state(case.issue)
    claim = _verdicts.EvidenceClaim(
        use=_verdicts.EvidenceUse.REUSED if reused else _verdicts.EvidenceUse.PUBLISHED,
        receipt=settled.receipt,
        revision=settled.revision,
        digest=settled.content_revision,
        passed=True,
        covers=True,
    )
    feedback = _world.REQUESTED if verdict == _verdicts.CHANGES_REQUESTED else ""
    run = _world.returned_run(case, state, f"{feedback}\n\nVERDICT: {verdict.upper()}")
    returned = _verdicts.ReturnedVerdict(0, verdict, run.subject.recorded(), feedback, claim)
    state.set(_verdicts.RETURNED_VERDICT, returned.recorded())
    case.github.write_pinned_state(case.issue, state)
    case.decision = _models._ReviewerDecision(run, verdict, feedback)
