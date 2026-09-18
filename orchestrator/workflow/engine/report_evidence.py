# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Everything a report transaction has to prove before it may complete.

Nothing here is inferred from an absence. A transaction completes only when this
owner has PROVED, on the tick that completes it, that the pull request the record
names is open in this repository on this branch and STANDING on the commit the
report is about, that the checkout is readable and clean and standing on that
same commit, that the remote branch is in sync with it, that the
code-publication receipt vouches for that commit having reached that pull
request, and that the requirements the run was handed are still the requirements
the issue has.

A missing read is never one of those. "Nobody could say" and "it is so" are
different answers, and only one of them may be acted on -- which is why the
readings that failed come back as their own verdict rather than folded into the
refusals beside them, and why every reading here answers with one: a request
that raised would otherwise leave this guard by an exception rather than by a
verdict, through the dispatcher and out of the tick.

The PULL REQUEST is asked first, and that order is a correctness rule rather than
a cost preference. This is meant to run ahead of every stage handler, and the
terminal that drains a merged or closed pull request runs inside one -- so any
refusal taken before the pull request has been looked at can hold the tick in
front of that terminal. A merge whose branch GitHub auto-deleted is the case that
bites: the fetch the remote reading takes fails, the tick holds, and an issue
whose work is finished never reaches the handler that would finalize it.

That reading is taken through an entry point of its own rather than inside the
composition, because a caller has refusals of its own -- over the RECORDS rather
than over the world -- and every one of them has to stand behind the same answer.
A record nobody can act on parks the issue, and parked ahead of the pull request
a transaction owed to work that has already merged would park instead of
retiring, holding the terminal behind it for good.

The local readings follow, cheapest of the rest first, so a transaction that was
never going to complete this tick spends as little as it can: the checkout costs
no request at all, the remote reading costs one fetch, and the requirements hash
costs the comment walk the drift owner already makes.

The requirements reading is offered on its own too, over an issue read again,
for the callers that made the publication or settle it; and `refuses_for_good`
says, posting nothing, whether an owed transaction can ever settle as it stands.
"""
from __future__ import annotations

import logging
from typing import Any

from github.Issue import Issue

from orchestrator.config import models as _config_models
from orchestrator.github import comments as _trust, developer_reports as _reports
from orchestrator.github.client import GitHubClient
from orchestrator.github.pinned_state import PinnedState
from orchestrator.github.pull_request_reports import ReportPresence
from orchestrator.workflow.engine import (
    comments as _comments,
    content_hash as _content_hash,
    report_checkout_evidence as _checkout,
    report_evidence_models as _evidence_models,
    report_publication_evidence as _publication,
    report_records as _records,
    report_remote_evidence as _remote,
)

log = logging.getLogger("orchestrator.workflow")


def publication_for(
    gh: GitHubClient, pending: _records.PendingReport,
) -> _evidence_models.ReportEvidence:
    """Take the pull-request reading, which every other one stands behind.

    Split out of the composition below because a caller has a decision to make
    on it alone before the rest is worth paying for: a pull request that has
    ENDED retires the transaction, and that answer has to reach the caller
    ahead of every refusal it could otherwise take -- including the refusals it
    takes over its own records rather than over the world. The terminal that
    drains a merged or closed pull request runs INSIDE a stage handler, which
    is behind this guard, so anything answered before this reading can hold the
    tick in front of that terminal for good.

    The proved pull request travels on the verdict and is handed back to
    `evidence_for`, so the world this licenses is the world it was read in: two
    fetches are two moments, and a pull request somebody closes between them
    would be proved open and written to closed.
    """
    return _publication.publication_verdict(gh, pending)


def evidence_for(
    spec: _config_models.RepoSpec,
    issue: Issue,
    state: PinnedState,
    pending: _records.PendingReport,
    found: _evidence_models.ReportEvidence,
) -> _evidence_models.ReportEvidence:
    """Prove -- or refuse -- everything else one transaction needs to complete.

    `found` is the pull-request reading the caller already took, handed back
    rather than re-read: it is the only reading here that cannot be repeated
    without changing what is being proved, and it is also the one the caller
    had to see first.

    A refusal on it short-circuits the rest, so the local readings are only
    ever taken behind a pull request that is open, ours, on the recorded
    branch, and standing on the recorded commit.

    The local readings follow, cheapest of the rest first, and the proved pull
    request is what comes back on success, because a caller publishes against
    it rather than fetching one of its own.
    """
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


def fresh_requirements_verdict(
    gh: GitHubClient,
    issue: Issue,
    state: PinnedState,
    pending: _records.PendingReport | _records.CurrentReport,
) -> _evidence_models.ReportEvidence | None:
    """Refuse a report the issue has moved under since the run, or None.

    The same reading as the composition's, over an issue read AGAIN: the one
    in hand was fetched before the developer ran, so an edit during the run or
    the publication after it is invisible there. A fetch that failed HOLDS,
    since nobody could say the issue is unchanged. A settled report is asked
    the same question by a recovery, over the subject it froze.
    """
    try:
        fresh = gh.get_issue(issue.number)
    except Exception:
        log.exception(
            "issue=#%d could not be re-read to say whether its requirements "
            "have moved since the run that wrote its developer report",
            issue.number,
        )
        return _evidence_models.ReportEvidence(
            _evidence_models.ReportEvidenceVerdict.HOLD,
            "the issue could not be re-read for its requirements",
        )
    return _requirements_verdict(fresh, state, pending)


def _requirements_verdict(
    issue: Issue,
    state: PinnedState,
    pending: _records.PendingReport | _records.CurrentReport,
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

    The READING is the other way round, and it is the reason this is not a bare
    comparison. Computing the revision walks the issue's comments, which is a
    request like every other reading here -- and one that raised would
    otherwise leave this guard by an exception rather than by a verdict,
    through the dispatcher and out of the tick. An edit nobody could look for
    is not an issue whose requirements are unchanged, so it holds, exactly as
    every other missing read on this road does.
    """
    try:
        current = _content_hash._compute_user_content_hash(
            issue, _comments._orchestrator_ids(state),
        )
    except Exception:
        log.exception(
            "issue=#%d could not be read to say whether its requirements have "
            "moved since the run that wrote its developer report; holding the "
            "tick", issue.number,
        )
        return _evidence_models.ReportEvidence(
            _evidence_models.ReportEvidenceVerdict.HOLD,
            "the issue's own requirements could not be read",
        )
    if current == pending.subject.requirements_revision:
        return None
    return _evidence_models.ReportEvidence(
        _evidence_models.ReportEvidenceVerdict.DEFER,
        "the issue requirements moved since the run that wrote the report",
    )


def refuses_for_good(
    gh: GitHubClient, pending: _records.PendingReport, pull_request: Any,
) -> bool:
    """Whether an owed transaction can never settle as the thread stands.

    Our comment under a publication's receipt no longer rendering as the
    report, or a verified location gone, changed or untrusted: content a human
    owns, which no retry settles. A reading nobody could take is not one.
    """
    if pending.mode is _records.ReportMode.PUBLISH:
        return _published_reading(gh, pending, pull_request) is ReportPresence.CHANGED
    lookup = gh.reread_report_location(
        pending.location, content_sha256=pending.content_revision,
    )
    if lookup.presence is not ReportPresence.PRESENT:
        return lookup.presence in {ReportPresence.ABSENT, ReportPresence.CHANGED}
    try:
        return not _trust.is_trusted_author(getattr(lookup.found, "user", None))
    except Exception:
        log.exception("the author of a verified developer report would not read")
        return False


def _published_reading(
    gh: GitHubClient, pending: _records.PendingReport, pull_request: Any,
) -> ReportPresence:
    """What the thread holds under a publication's receipt, posting nothing."""
    try:
        report = _reports.DeveloperReport(
            pr_number=pending.subject.pr_number,
            source_sha=pending.subject.source_sha,
            requirements_revision=pending.subject.requirements_revision,
            report_revision=pending.report_revision,
            receipt=pending.receipt,
            text=pending.report,
        )
    except _reports.ReportRefusedError:
        return ReportPresence.UNCONFIRMED
    return gh.find_developer_report(pull_request, report).presence
