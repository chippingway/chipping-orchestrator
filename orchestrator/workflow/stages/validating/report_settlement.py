# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""A recorded developer report, bound to its publication and settled.

A report a requirements-drift resume recorded is bound to the publication the
code-publication receipt names -- once the code is out, or at once for a report
that needed none -- and settled through the same reconciliation every dispatch
runs, whose evidence proves the pull request, the checkout, the remote and the
receipt again. The binding is taken only where the checkout is standing on the
commit that receipt names: a report bound to any other commit would describe
work the pull request does not carry. So a delivery a LATER publication carried
out -- a failed push the transient recovery retried, a candidate an
adjudication settled -- is bound here too, on the first tick that can prove it.

Everything the binding and the settlement decide on is read again by number
first: the pull request, its description -- which says whether a report
verified on that very body would cost the pull request its closing reference
and attribution -- and the issue itself. The issue in hand was fetched before
the resumed run, so a title or body edited while the agent was out exists only
on the fresh object, and the reconciliation proves the requirements on that one
before it posts anything.

The drift callers ask this once their own bookkeeping is written, and the
review hold in `report_hold` asks it for a delivery an earlier tick left. A
refusal no retry changes parks here, once, under `report_undeliverable`.
"""
from __future__ import annotations

import logging

from github.Issue import Issue

from orchestrator import config
from orchestrator.config import models as _config_models
from orchestrator.git.verification import probes as _verification_probes
from orchestrator.git.worktrees import creation as _worktree_creation, naming as _naming
from orchestrator.github import client as _client, pinned_state as _pinned_state
from orchestrator.workflow.engine import (
    report_binding as _report_binding,
    report_delivery as _report_delivery,
    report_delivery_state as _delivery_state,
    report_locations as _report_locations,
    report_transaction as _report_transaction,
)
from orchestrator.workflow.stages.implementing import (
    dev_pr as _dev_pr,
    late_publication_state as _late_publication_state,
)
from orchestrator.workflow.state import WorkflowLabel

log = logging.getLogger("orchestrator.workflow")

_PR_NUMBER = "pr_number"

_UNDELIVERED_PARK = (
    "{mentions} the developer report this issue owes PR #{pr} cannot be "
    "delivered as things stand: {detail}. Review is held rather than run over "
    "a pull request that does not carry the report of the work under review, "
    "and nothing was discarded. Reply and the orchestrator resumes the "
    "session; the report it writes then is the one that gets published, and "
    "it needs no new commit to deliver it."
)

_UNPUBLISHED = (
    "no publication of this pull request's is recorded for it to go onto"
)

_MOVED_CHECKOUT = (
    "the checkout is not standing on the commit the pull request was last "
    "published at"
)


def _settles_the_report(
    gh: _client.GitHubClient,
    spec: _config_models.RepoSpec,
    issue: Issue,
    state: _pinned_state.PinnedState,
    label: WorkflowLabel,
) -> None:
    """Bind the delivered report to the last publication and settle it.

    Settled through the reconciliation rather than posted here, so the report
    goes out on the same evidence a later tick's retry would demand -- and over
    the issue read AGAIN where it was bound. A transaction it holds or stands
    down on is still owed, which is what the review hold reads; nothing here
    decides the caller's route.
    """
    if not _delivery_state.carries_delivered_report(state):
        return
    fresh = _binds_the_delivery(gh, spec, issue, state)
    if fresh is not None:
        _report_transaction._reconciles_pending_report(
            gh, spec, fresh, label, state,
        )


def _binds_the_delivery(
    gh: _client.GitHubClient,
    spec: _config_models.RepoSpec,
    issue: Issue,
    state: _pinned_state.PinnedState,
) -> Issue | None:
    """Bind the delivered report to the publication the receipt names.

    The issue read afresh where the report is bound, None where it is not.
    The checkout is resolved as the reviewer resolves it, recreated where it
    is gone, and has to be standing on the receipt's commit: the report
    describes the work the run left in that checkout, so a checkout anywhere
    else makes it a report about some other commit. A reading nobody could
    take holds for the next tick; a definite refusal parks, since no retry
    here changes it.
    """
    commit = _receipt_commit(state)
    if not commit:
        _parks(gh, issue, state, _UNPUBLISHED)
        return None
    head = _verification_probes._head_sha(_worktree_creation._ensure_worktree(
        spec, issue.number,
        branch=_naming._resolve_branch_name(state, spec, issue.number),
    ))
    if not head:
        return None
    if head != commit:
        _parks(gh, issue, state, _MOVED_CHECKOUT)
        return None
    reading = _publication_reading(gh, spec, issue, state, commit)
    if reading is None:
        return None
    published, fresh = reading
    _report_binding.binds_the_delivery(gh, issue, state, published)
    return None if _delivery_state.carries_delivered_report(state) else fresh


def _receipt_commit(state: _pinned_state.PinnedState) -> str:
    """The commit the code-publication receipt names on this pull request, or "".

    Both halves, since a receipt naming another pull request vouches for
    nothing here -- and a pull request neither side can name is no match.
    """
    number = _late_publication_state._published_pull_request(state)
    if not number or number != _late_publication_state._recorded_pull_request(state):
        return ""
    return _late_publication_state._published_commit(state)


def _publication_reading(
    gh: _client.GitHubClient,
    spec: _config_models.RepoSpec,
    issue: Issue,
    state: _pinned_state.PinnedState,
    commit: str,
) -> tuple | None:
    """The publication and the issue, both read again, or None where one would not.

    One boundary for every read, because each is a request -- the description
    is a lazy read of the object the lookup hands back, and a qualified
    closing reference needs this repository named -- and a binding decided on
    any of them half-read would be decided on what nobody saw.
    """
    try:
        return _read_publication(gh, spec, issue, state, commit)
    except Exception:
        log.exception(
            "issue=#%d could not read its pull request, its description, or "
            "the issue again to bind its developer report; holding for the "
            "next tick", issue.number,
        )
        return None


def _read_publication(
    gh: _client.GitHubClient,
    spec: _config_models.RepoSpec,
    issue: Issue,
    state: _pinned_state.PinnedState,
    commit: str,
) -> tuple:
    """Take the whole reading, raising where one request fails.

    The binding is told whether the DESCRIPTION still closes this issue and
    names the session, since a report verified on that very body would cost
    the pull request both, and nothing here rewrites a description.
    """
    pull_request = gh.get_pr(_late_publication_state._published_pull_request(state))
    return _report_binding.ReportPublication(
        pull_request, spec.slug,
        _naming._resolve_branch_name(state, spec, issue.number), commit,
        describes_the_issue=_report_locations.describes_the_issue(
            pull_request, issue.number, _dev_pr._dev_pr_attribution(state),
            gh.repo_slug,
        ),
    ), gh.get_issue(issue.number)


def _parks(
    gh: _client.GitHubClient,
    issue: Issue,
    state: _pinned_state.PinnedState,
    detail: str,
) -> None:
    """Park a report no retry here can deliver, once, for a human."""
    log.warning(
        "issue=#%d cannot deliver the developer report it owes: %s",
        issue.number, detail,
    )
    _report_delivery.parks_an_undeliverable_report(
        gh, issue, state, _UNDELIVERED_PARK.format(
            mentions=config.HITL_MENTIONS, pr=state.get(_PR_NUMBER),
            detail=detail,
        ),
    )
