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
fence, say, or more of it than the one comment an artifact is published as
holds -- earns nothing, since evidence that cannot be shown as written is not
evidence anybody can check.

A reuse names the current evidence the reviewer was handed, and the reading has
already held the named revision to that evidence's digest; what it earns is a
claim on that record exactly, receipt, revision, and digest, and on nothing
else -- a reviewer handed no evidence has nothing it may reuse, so a reuse it
declares anyway is stale. Whoever relies on the claim later proves that
evidence current again first.

Either claim also says whether its commands cover the repository's own
verification: every configured `VERIFY_COMMANDS` command, exactly as
configured, exiting 0 (`covers_the_configuration`). An approval requires it --
a reviewer that ran something else, however green, did not run what the
repository requires. `claim_standing` says where a claim's evidence stands on
the comment: settled as the current evidence, still owed to the pull request,
or lost to a retirement, a later transaction, or a verification context that
has moved since -- which the proof refuses whether the evidence settled or not.

Anything else earns nothing, and says why in words written for a human:
a run that did not complete cleanly, a missing or malformed declaration, one
about another commit or another evidence revision, or a tree that would not
read. A change request stands without evidence; an approval does not.

Nothing is written here: the transaction is minted, not recorded, because its
record has to be measured beside the verdict it is persisted with
(`review_verdicts.records_the_verdict`). No live reviewer round asks for a
claim yet; only the disposition service does, where it persists a returned
verdict (`review_disposition`), which nothing reaches yet. Where a claim's
evidence stands is asked by that service as it finishes a waiting verdict, by
the change-request handoff behind it (`review_handoffs`), and by the recovery
of a record an issue already carries (`review_resume`), the one road reaching
that service yet.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from enum import StrEnum
from types import MappingProxyType

from github.Issue import Issue

from orchestrator import config
from orchestrator.github import verification_artifacts as _artifacts, verification_evidence as _evidence
from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.engine import (
    report_settlement_state as _report_settlement,
    review_verification as _review_verification,
    review_verification_models as _verification_models,
    verification_proof as _proof,
    verification_record_state as _record_state,
    verification_records as _records,
    verification_settlement_state as _settlement,
    verification_world as _world,
)
from orchestrator.workflow.stages.validating import models as _models, review_verdicts as _verdicts

_Refusal = _verification_models._VerificationRefusal

_INCOMPLETE = "the reviewer run did not complete cleanly, so nothing it declared is evidence"

# Why a completed run that declared nothing earns no evidence.
NO_DECLARATION = "it declared no verification"

# What each refusal the declaration's reader answers with tells a human.
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
    "(output inside a code fence, more of it than one comment holds, or text UTF-8 cannot carry, for example)"
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

    @classmethod
    def published(
        cls, pending: _records.PendingEvidence, commands: tuple[_evidence.VerifiedCommand, ...],
    ) -> ClaimedEvidence:
        """The claim minted transaction `pending` earns, or the refusal where its artifact cannot be published.

        The whole artifact is rendered, as the transaction's own writer renders
        it, rather than each command alone: every transcript can be
        publishable and the artifact carrying them still be more than one
        comment holds. The rendering digests the evidence too, which is where
        text UTF-8 cannot carry -- a lone surrogate a reviewer's JSON decodes
        to -- raises rather than anywhere a later tick would meet it.
        """
        try:
            _artifacts.render_verification_artifact(pending.artifact)
        except (_evidence.ArtifactRefusedError, UnicodeEncodeError):
            return cls(refusal=_UNPUBLISHABLE)
        return cls(
            _verdicts.EvidenceClaim(
                use=_verdicts.EvidenceUse.PUBLISHED,
                receipt=pending.receipt,
                revision=pending.revision,
                digest=pending.content_revision,
                passed=pending.passed,
                covers=covers_the_configuration(commands),
            ),
            pending,
        )


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
            covers=covers_the_configuration(handed.artifact.commands),
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
    return ClaimedEvidence.published(pending, commands)


def covers_the_configuration(commands: tuple[_evidence.VerifiedCommand, ...]) -> bool:
    """Whether every configured verification command is among `commands`, as configured, exiting 0.

    Exactly as configured, because the configuration is what the repository
    requires of a change and a reviewer is told to run each command as
    listed: a command that merely passed says nothing about the ones that
    were required. An empty configuration requires nothing further.
    """
    passing = {ran.command for ran in commands if ran.exit_status == 0}
    return all(command in passing for command in config.VERIFY_COMMANDS)


class ClaimStanding(StrEnum):
    """Where the evidence a claim names stands on the pinned comment now.

    SETTLED is the current evidence, exactly the one named, under the
    configured context. OWED is the transaction still waiting to be published,
    under the configured context. LOST is anything else: retired, superseded
    -- a later revision spent, whether or not it has settled yet -- or
    recorded under a verification context that has since moved, none of which
    can settle or be relied on.
    """

    SETTLED = "settled"
    OWED = "owed"
    LOST = "lost"


def claim_standing(state: PinnedState, claim: _verdicts.EvidenceClaim) -> ClaimStanding:
    """Whether `claim`'s evidence settled, is still owed, or will never settle.

    Either record has to name the claim whole -- receipt, revision, and digest
    -- since a record sharing only a receipt is not the evidence the verdict
    relied on, and has to be bound under the configured verification context:
    the proof refuses evidence recorded under one that has moved since,
    whether it settled or not. And the claim's revision has to be the latest
    this issue has spent: a later transaction, recorded and not yet settled,
    already supersedes the evidence still reading as current, as the proof and
    the reconciliation both hold -- and so does a spent revision nobody can
    read.
    """
    latest = _record_state._latest_revision(state)
    if latest is None or latest > claim.revision:
        return ClaimStanding.LOST
    named = (claim.receipt, claim.revision, claim.digest, _proof.configured_context_revision())
    for standing, record in (
        (ClaimStanding.SETTLED, _settlement.read_current_evidence(state)),
        (ClaimStanding.OWED, _record_state.read_pending_evidence(state)),
    ):
        if record is not None and (
            record.receipt, record.revision, record.content_revision, record.binding.context_revision,
        ) == named:
            return standing
    return ClaimStanding.LOST


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
