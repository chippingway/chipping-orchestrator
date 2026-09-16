# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Everything a report transaction has to prove before it may complete.

Nothing here is inferred from an absence. A transaction completes only when this
owner has PROVED, on the tick that completes it, that the checkout is readable
and clean and standing on the commit the report is about, that the pull request
the record names is open in this repository on this branch and carries that
commit, that the code-publication receipt vouches for that commit having reached
that pull request, and that the requirements the run was handed are still the
requirements the issue has.

A missing read is never one of those. "Nobody could say" and "it is so" are
different answers, and only one of them may be acted on -- which is why the
readings that failed come back as their own verdict rather than folded into the
refusals beside them.

The groups are asked cheapest first, so a transaction that was never going to
complete this tick spends as little of GitHub's budget as it can: the checkout
costs no request at all, the remote reading costs one fetch, the pull request
costs one API call, and the requirements hash costs the comment walk the drift
owner already makes.
"""
from __future__ import annotations

from github.Issue import Issue

from orchestrator.config import models as _config_models
from orchestrator.github.client import GitHubClient
from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.engine import (
    comments as _comments,
    content_hash as _content_hash,
    report_checkout_evidence as _checkout,
    report_evidence_models as _evidence_models,
    report_publication_evidence as _publication,
    report_records as _records,
    report_remote_evidence as _remote,
)


def evidence_for(
    gh: GitHubClient,
    spec: _config_models.RepoSpec,
    issue: Issue,
    state: PinnedState,
    pending: _records.PendingReport,
) -> _evidence_models.ReportEvidence:
    """Prove -- or refuse -- everything one transaction needs to complete.

    The pull request is read FIRST, and that order is a correctness rule rather
    than a cost preference. This guard runs ahead of every stage handler, and
    the terminal that drains a merged or closed pull request runs INSIDE one --
    so any answer this owner gives before it has looked at the pull request is
    an answer that can hold the tick in front of that terminal. A merge whose
    branch GitHub auto-deleted is the case that bites: the fetch the remote
    reading takes fails, the tick holds, and an issue whose work is finished
    never reaches the handler that would finalize it. Asked first, a pull
    request that has ended retires the transaction and the stage runs.

    The local readings follow, cheapest of the rest first, and the proved pull
    request is what comes back on success, because the caller publishes against
    it rather than fetching one of its own: two fetches are two moments, and a
    pull request somebody closes between them would be proved open and written
    to closed.
    """
    found = _publication.publication_verdict(gh, pending)
    if not found.proved:
        return found
    refused = _checkout.checkout_verdict(spec, issue, pending)
    if refused is not None:
        return refused
    adrift = _remote.remote_verdict(spec, issue, pending)
    if adrift is not None:
        return adrift
    receipted = _publication.receipt_verdict(state, pending)
    if receipted is not None:
        return receipted
    edited = _requirements_verdict(issue, state, pending)
    return found if edited is None else edited


def _requirements_verdict(
    issue: Issue, state: PinnedState, pending: _records.PendingReport,
) -> _evidence_models.ReportEvidence | None:
    """Refuse a report whose requirements have moved under it, or None.

    The revision recorded is the one the developer run was actually handed, so
    a mismatch here says the issue was edited while the publication was
    outstanding -- and publishing now would put a report answering the old
    requirements onto the pull request while stamping it with the revision it
    was written against.

    Deferred rather than held, because the route that ANSWERS an edit is the
    drift resume behind this owner. Held, the issue would sit forever on a
    transaction nothing was allowed to reach and supersede.
    """
    current = _content_hash._compute_user_content_hash(
        issue, _comments._orchestrator_ids(state),
    )
    if current == pending.subject.requirements_revision:
        return None
    return _evidence_models.ReportEvidence(
        _evidence_models.ReportEvidenceVerdict.DEFER,
        "the issue requirements moved since the run that wrote the report",
    )
