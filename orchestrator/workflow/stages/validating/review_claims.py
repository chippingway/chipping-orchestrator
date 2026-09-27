# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The verification evidence a returned reviewer's declaration earns its verdict.

A reviewer declares its verification in its own markers beside the verdict,
and `review_verification` reads that declaration strictly, out of a run that
completed, against what the reviewer was handed: the head under review and the
revision of the current evidence its prompt quoted, if any. What the reading
earns is decided here, and it is one of three things.

Commands the reviewer ran become a reviewer-reported transaction, minted past
every revision the issue has spent and bound to exactly what the reviewer was
handed: the pull request, branch, and repository the settled report was
published to, the reviewed head and the requirements it was handed, the review
subject as the returned reviewer's record spells it (which is the record the
proof holds reviewer-reported evidence to), the reviewed head as the tested
commit with the full tree this repository reads for it, and the configured
verification context. The commands are carried exactly as the reviewer stated
them; one this format cannot publish verbatim -- quoted output behind a code
fence, say -- earns nothing, since evidence that cannot be shown as written is
not evidence anybody can check.

A reuse names the current evidence the reviewer was handed, and the reading has
already held the named revision to that evidence's digest; what it earns is a
claim on that record exactly, which the disposition proves current again before
an approval relies on it.

Anything else earns nothing, with the reason a human reading the park is told:
a run that did not complete cleanly, a missing or malformed declaration, one
about another commit or another evidence revision, or a tree that would not
read. A change request stands without evidence; an approval does not.

Nothing is written here: the transaction is minted, not recorded, because its
record has to be measured beside the verdict it is persisted with
(`review_disposition`).
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from types import MappingProxyType

from github.Issue import Issue

from orchestrator.github import verification_evidence as _evidence
from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.engine import (
    report_settlement_state as _report_settlement,
    review_verification as _review_verification,
    review_verification_models as _verification_models,
    verification_proof as _proof,
    verification_record_state as _record_state,
    verification_records as _records,
    verification_world as _world,
)
from orchestrator.workflow.stages.validating import models as _models, review_verdicts as _verdicts

_Refusal = _verification_models._VerificationRefusal

_INCOMPLETE = "the reviewer run did not complete cleanly, so nothing it declared is evidence"

# What an approval whose run declared nothing -- or whose declaration a later
# tick cannot say anything more about -- is refused for.
NO_DECLARATION = "it declared no verification"

# What each refusal the declaration's reader answers with tells the human
# reading the park.
_REFUSED = MappingProxyType({
    _Refusal.NOT_INVOKED: _INCOMPLETE,
    _Refusal.INTERRUPTED: _INCOMPLETE,
    _Refusal.TIMED_OUT: _INCOMPLETE,
    _Refusal.PROVIDER_FAILURE: _INCOMPLETE,
    _Refusal.NONZERO_EXIT: _INCOMPLETE,
    _Refusal.MISSING: NO_DECLARATION,
    _Refusal.MALFORMED: "its verification declaration is malformed",
    _Refusal.STALE: (
        "its verification declaration names another commit, or other "
        "evidence than the current revision it was handed"
    ),
})

_UNBOUND = (
    "the reviewed commit's tree or the settled report it answers for could "
    "not be read, so its commands could not be bound as evidence"
)

_UNPUBLISHABLE = (
    "a command or its quoted output cannot be published verbatim as evidence "
    "(output inside a code fence, for example)"
)

_UNMINTED = "the verification revisions this issue has spent could not be read"


@dataclass(frozen=True)
class ClaimedEvidence:
    """What one declaration earned: a claim, the transaction behind it, or why none.

    `pending` is the transaction a PUBLISHED claim names, minted and not yet
    recorded; None for a reuse and for a refusal.
    """

    claim: _verdicts.EvidenceClaim | None = None
    pending: _records.PendingEvidence | None = None
    refusal: str = ""


def claimed_evidence(
    issue: Issue, state: PinnedState, reviewer_run: _models._ReviewerRun,
) -> ClaimedEvidence:
    """The evidence `reviewer_run`'s declaration earns, minted where it ran commands."""
    outcome = _review_verification._verification_outcome_of_run(
        reviewer_run.agent_result, reviewer_run.verification_subject,
    )
    if isinstance(outcome, _verification_models._FreshVerification):
        return _fresh_evidence(issue, state, reviewer_run, outcome)
    handed = reviewer_run.evidence
    if isinstance(outcome, _verification_models._ReusedVerification) and handed is not None:
        current = handed.current
        return ClaimedEvidence(_verdicts.EvidenceClaim(
            use=_verdicts.EvidenceUse.REUSED,
            receipt=current.receipt,
            revision=current.revision,
            digest=current.content_revision,
            passed=current.passed,
        ))
    return ClaimedEvidence(refusal=_REFUSED.get(outcome, _REFUSED[_Refusal.STALE]))


def _fresh_evidence(
    issue: Issue,
    state: PinnedState,
    reviewer_run: _models._ReviewerRun,
    outcome: _verification_models._FreshVerification,
) -> ClaimedEvidence:
    """The transaction the commands a reviewer ran are minted as, or why none."""
    binding = _binding(state, reviewer_run)
    if binding is None:
        return ClaimedEvidence(refusal=_UNBOUND)
    try:
        commands = tuple(
            _evidence.VerifiedCommand(
                command=ran.command, exit_status=ran.exit_status, output=ran.output,
            )
            for ran in outcome.commands
        )
    except _evidence.ArtifactRefusedError:
        return ClaimedEvidence(refusal=_UNPUBLISHABLE)
    pending = _record_state.mint_pending_evidence(state, issue.number, binding, commands)
    if pending is None:
        return ClaimedEvidence(refusal=_UNMINTED)
    return ClaimedEvidence(
        _verdicts.EvidenceClaim(
            use=_verdicts.EvidenceUse.PUBLISHED,
            receipt=pending.receipt,
            revision=pending.revision,
            digest=pending.content_revision,
            passed=pending.passed,
        ),
        pending,
    )


def _binding(
    state: PinnedState, reviewer_run: _models._ReviewerRun,
) -> _records.EvidenceBinding | None:
    """What the reviewer's commands are evidence about, or None where it cannot be read.

    The publication is the settled report's own, moved to the head and the
    requirements the reviewer was handed: the report the subject names was
    published to that repository, pull request, and branch, and the proof
    reads the pull request through that same subject.
    """
    current = _report_settlement.read_current_report(state)
    subject = reviewer_run.subject
    tree = _world.tree_of(reviewer_run.wt, subject.commit)
    if current is None or not tree:
        return None
    publication = replace(
        current.subject,
        source_sha=subject.commit,
        requirements_revision=subject.requirements_revision,
    )
    return _records.EvidenceBinding(
        target=_records.EvidenceTarget(publication=publication, subject=subject.recorded()),
        source=_evidence.EvidenceSource.REVIEWER_REPORTED,
        tested_sha=subject.commit,
        tested_tree=tree,
        context_revision=_proof.configured_context_revision(),
    )
