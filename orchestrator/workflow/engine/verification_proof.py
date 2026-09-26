# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Everything a piece of verification evidence has to prove before it is current.

Nothing here is inferred from an absence, for the reason a developer report's
evidence is not: evidence becomes current only when this owner has PROVED, on
the tick that settles it, that the pull request it names is open in this
repository on the recorded branch and standing on the head the evidence is
written for; that the branch and this checkout stand there too; that the
tested commit, the target head, and the review subject's head are commits this
repository reads with the one tree the run recorded; that the verification
context the commands ran under is the one configured now; that the review
subject is about the developer report the pull request carries, with no report
transaction still owed; and that the issue's requirements are still the ones
the evidence was bound to.

The pull request is read first, through the report domain's own reading, and
every other reading stands behind it: an ENDED pull request retires the
transaction, and nothing short of that reading may stand in front of it. The
rest follow cheapest first -- the context and the pinned subject cost nothing,
the branch and the objects cost one fetch, and the requirements cost the
comment walk the drift owner already makes.

The verdicts are the report transaction's own (`report_evidence_models`), and
they mean the same here. HOLD is a reading nobody could take. DEFER is a
structural refusal that a route behind the reconciliation clears -- a push, a
drift resume, a fresh reviewer, fresh evidence superseding this -- so the tick
carries on. ENDED retires. PROVED carries the pull request it was proved
against, since a publication made against another reading would reopen the
window this evidence exists to close.

`configured_context_revision` is the context both witnesses are held to: the
configured `VERIFY_COMMANDS` and `VERIFY_TIMEOUT`, minted by the verify
runner's own model. A reviewer runs what it runs, but what the repository
REQUIRES verification to be is that configuration, so evidence recorded under
another one -- including an empty one -- is not current once it moves.
"""
from __future__ import annotations

from github.Issue import Issue

from orchestrator import config
from orchestrator.config import models as _config_models
from orchestrator.git.verification import models as _verify_models
from orchestrator.github.client import GitHubClient
from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.engine import (
    report_evidence_models as _evidence_models,
    report_publication_evidence as _publication,
    verification_records as _records,
    verification_settlement_state as _settlement,
    verification_subject as _subject,
    verification_world as _world,
)


def configured_context_revision() -> str:
    """The verification context configured now, as the verify runner mints it."""
    return _verify_models._context_revision(
        tuple(config.VERIFY_COMMANDS), config.VERIFY_TIMEOUT,
    )


def evidence_verdict(
    gh: GitHubClient,
    spec: _config_models.RepoSpec,
    issue: Issue,
    state: PinnedState,
    binding: _records.EvidenceBinding,
) -> _evidence_models.ReportEvidence:
    """Prove -- or refuse -- that `binding` is evidence for the world as it stands."""
    found = _publication.subject_verdict(gh, binding.target.publication)
    return rest_verdict(spec, issue, state, binding, found)


def rest_verdict(
    spec: _config_models.RepoSpec,
    issue: Issue,
    state: PinnedState,
    binding: _records.EvidenceBinding,
    found: _evidence_models.ReportEvidence,
) -> _evidence_models.ReportEvidence:
    """Everything behind the pull-request reading `found`, which is handed back.

    `found` is the one reading that cannot be repeated without changing what
    is being proved, so a caller that had to see it first hands it on here and
    the proved pull request is what comes back on success.
    """
    if not found.proved:
        return found
    refused = _context_verdict(binding) or _subject.subject_verdict(state, binding.target)
    if refused is None:
        refused = _world.world_verdict(spec, issue, binding)
    if refused is None:
        refused = _subject.requirements_verdict(
            issue, state, binding.target.publication.requirements_revision,
        )
    return found if refused is None else refused


def current_evidence_verdict(
    gh: GitHubClient,
    spec: _config_models.RepoSpec,
    issue: Issue,
    state: PinnedState,
) -> _evidence_models.ReportEvidence:
    """Prove the current evidence still stands for the world, or refuse it.

    For a reader about to rely on the current record -- a reviewer handed it,
    a readiness decision -- rather than for the reconciliation that settled
    it: a head, a context, a report, or requirements can each move after the
    settlement, and the record alone cannot see any of them. An issue with no
    current evidence defers, since nothing on this road can produce some.
    """
    current = _settlement.read_current_evidence(state)
    if current is None:
        return _evidence_models.ReportEvidence(
            _evidence_models.ReportEvidenceVerdict.DEFER,
            "this issue records no current verification evidence",
        )
    return evidence_verdict(gh, spec, issue, state, current.binding)


def _context_verdict(
    binding: _records.EvidenceBinding,
) -> _evidence_models.ReportEvidence | None:
    """Refuse evidence recorded under another verification context, or None."""
    if binding.context_revision == configured_context_revision():
        return None
    return _evidence_models.ReportEvidence(
        _evidence_models.ReportEvidenceVerdict.DEFER,
        "the verification configuration moved since the evidence was recorded",
    )
