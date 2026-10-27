# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The approval record a case set past the reviewer's approval carries, in the current format.

Every road that acts on an approval holds it to its own record: the subject it
covers, read whole (`review_subjects.approval_covers_current`), and the
requirements it was given, which the drift baseline has to still hold
(`stages/in_review/state.approval_covers_requirements`). An issue carrying no
such record is one every such road hands back for a review, so a case about
what happens past the approval seeds it here. A case whose road spends the
approval past the squash needs the evidence its claim names as well, which
`verified_approvals.verifies_the_approval` records over a settled report.
"""
from __future__ import annotations

from orchestrator.github.pull_request_reports import ReportLocation
from orchestrator.workflow.engine import content_hash as _content_hash, review_subjects as _review_subjects
from orchestrator.workflow.stages.validating import (
    approved_evidence as _approved_evidence,
    review_verdicts as _verdicts,
)
from tests.support.fakes import DEFAULT_PR_HEAD_SHA
from tests.workflow.repo_values import DIGEST_LENGTH

# A requirements revision no reading of a case's thread reproduces: the one an
# approval was given before an edit the case is about.
STALE_REQUIREMENTS = "5" * DIGEST_LENGTH

# The claim an approval records on the evidence it was proved over, read
# whole: a receipt spelled as the first revision's, its nonce half a whole
# digest's hex digits, and a passing run that covers the configuration.
_CLAIM = _verdicts.EvidenceClaim(
    use=_verdicts.EvidenceUse.PUBLISHED,
    receipt="issue-1-verification-1-{nonce}".format(nonce="0" * (DIGEST_LENGTH // 2)),
    revision=1,
    digest=STALE_REQUIREMENTS,
    passed=True,
    covers=True,
)


def approved(pr_number: int, *, head: str = DEFAULT_PR_HEAD_SHA, requirements: str = "") -> dict:
    """The records an approval of `head` on PR `pr_number`, given `requirements`, leaves, as pinned-state fields.

    The subject names no report, which agrees with an issue on which none has
    settled; one that settles later is a report the approval was not given.
    Beside it goes the claim on the evidence the approval was proved over,
    read whole, as every approval records one; that no current evidence
    answers to it is for a road that proves the evidence -- the documenting
    opening, the readiness proof -- to refuse, which a case reaching one seeds
    for itself.
    """
    subject = _review_subjects.ReviewSubject(
        pr_number=pr_number, commit=head, requirements_revision=requirements,
    )
    return {
        _review_subjects.APPROVED_SUBJECT: subject.recorded(),
        _approved_evidence.APPROVED_EVIDENCE: _CLAIM.recorded(),
    }


def approved_in_review(
    issue, pr_number: int, *, head: str = DEFAULT_PR_HEAD_SHA, baseline: str = "", orchestrator_ids=(),
) -> dict:
    """The drift baseline and the approval given it that an issue in review carries, as pinned-state fields.

    `baseline` is the requirements revision the approval was given -- a stale
    one, for a case about an edit landing since -- or, by default, the thread
    as it reads now, which is what the drift check would record: over the
    `orchestrator_ids` the case records as this orchestrator's own comments.
    """
    revision = baseline or _content_hash._compute_user_content_hash(issue, set(orchestrator_ids))
    return {
        "user_content_hash": revision,
        **approved(pr_number, head=head, requirements=revision),
    }


def approves_again(github, issue) -> None:
    """Record, through `review_subjects.record_approved`, a later approval of the subject the comment's approval covers.

    What a fresh reviewer approving the same subject leaves -- the head-keyed
    stamps the earlier approval's docs pass and ping left retired -- written
    through the client, as the approval arc writes it.
    """
    state = github.read_pinned_state(issue)
    recorded = state.get(_review_subjects.APPROVED_SUBJECT)
    report = None
    if recorded["report_revision"] is not None:
        report = _review_subjects.ReviewReport(
            text="",
            report_revision=recorded["report_revision"],
            content_revision=recorded["report_content"],
            source_sha=recorded["sha"],
            requirements_revision=recorded["requirements"],
            location=ReportLocation(pr_number=recorded["pr"]),
        )
    _review_subjects.record_approved(state, _review_subjects.ReviewSubject(
        pr_number=recorded["pr"],
        commit=recorded["sha"],
        requirements_revision=recorded["requirements"],
        report=report,
    ))
    github.write_pinned_state(issue, state)
