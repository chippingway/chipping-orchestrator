# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The reviewer, held while this issue still owes its pull request a report.

A review of work whose report nothing on the pull request carries is the review
the report contract exists to prevent, so the validating handler asks this last
before its spawn. The hold settles what it can first -- a delivery a later
publication carried out is bound and settled through `report_settlement` -- and
parks for a human where no retry can: a report written against requirements the
issue no longer has, one no publication here can carry, one standing over a
checkout that carries loose work or has moved off the commit it is about, one
the thread has moved out of reach -- edited, removed, or written by an author
this deployment does not trust -- and a debt no record describes at all, a run
that committed and wrote no report. A reply resumes the session through the
drift route, and the report it writes then supersedes the one that could not be
delivered.

Once nothing is owed there, a head this orchestrator rewrote holds the reviewer
too (`report_rewrite_debt`): the pull request stands on a commit the settled
report is not about, and the reviewer road behind would park for that. Where
the debt explains exactly that gap, the review is held without a park, since the
report owed is for a commit this orchestrator made; a report settled about the
head the pull request stands on pays the debt here, and the reviewer runs. A
claim nobody can read, or a head it does not explain, holds nothing here and
leaves the reviewer road's own rules to answer the report it finds.
"""
from __future__ import annotations

import logging
from pathlib import Path

from github.Issue import Issue

from orchestrator.config import models as _config_models
from orchestrator.git.verification import probes as _verification_probes, status as _worktree_status
from orchestrator.git.worktrees import creation as _worktree_creation, naming as _naming
from orchestrator.github.client import GitHubClient
from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.engine import (
    report_delivery as _report_delivery,
    report_delivery_state as _delivery_state,
    report_evidence as _report_evidence,
    report_record_state as _record_state,
    report_rewrite_debt as _rewrite_debt,
)
from orchestrator.workflow.stages.validating import (
    drift_reports as _drift_reports,
    report_settlement as _settlement,
    review_report as _review_report,
)
from orchestrator.workflow.state import WorkflowLabel

log = logging.getLogger("orchestrator.workflow")

_USER_CONTENT_HASH = "user_content_hash"

_MOVED_REQUIREMENTS = (
    "the issue's requirements have moved since the run that wrote it"
)

_UNRECORDED = (
    "no report of the work it carries is recorded -- the session that "
    "committed it wrote none"
)

_UNSETTLEABLE = (
    "the report it went out as was edited, removed, or written by an author "
    "this deployment does not trust"
)

_LOOSE_CHECKOUT = (
    "the checkout it stands on carries uncommitted work the pull request "
    "does not"
)

_MOVED_CHECKOUT = (
    "the checkout has moved off the commit the report is about"
)


def _report_holds_the_review(
    gh: GitHubClient,
    spec: _config_models.RepoSpec,
    issue: Issue,
    state: PinnedState,
) -> bool:
    """Hold the reviewer while this issue still owes its pull request a report.

    A debt no record describes -- a run that committed and wrote no report,
    whose park a later reply answered without writing one either -- parks
    again: nothing here can publish a report nobody wrote.

    Asked after the drift check, so the baseline on the comment is the issue's
    current requirements: a record written against any other revision is one
    no retry settles -- the reconciliation defers it for good -- and it parks
    for the report the session writes again. Everything else is settled as far
    as this tick can take it, and what is still owed then is held -- or parked,
    where nothing the reconciliation can do will settle it: a checkout
    carrying loose work, a checkout that has moved off the commit the report
    is about, and a report on the thread somebody has edited, removed, or
    written untrusted. Each is a condition this stage cannot undo, so the
    reconciliation stands down on it for as long as it stands, and held
    silently they would suppress every later reviewer with nobody told.

    A report no longer owed leaves the question of a rewritten head, asked
    last because a report this tick settled may be the one that pays it.
    """
    if not _report_delivery.owes_a_report(state):
        return _rewrite_holds_the_review(gh, issue, state)
    refusal = _refusal_before_settling(state)
    if refusal:
        _settlement._parks(gh, issue, state, refusal)
        return True
    _settlement._settles_the_report(gh, spec, issue, state, WorkflowLabel.VALIDATING)
    if not _report_delivery.owes_a_report(state):
        return _rewrite_holds_the_review(gh, issue, state)
    refusal = _refusal_after_settling(gh, spec, issue, state)
    if refusal:
        _settlement._parks(gh, issue, state, refusal)
        return True
    log.info(
        "issue=#%d still owes its pull request a developer report; holding "
        "the review until it is confirmed", issue.number,
    )
    return True


def _refusal_before_settling(state: PinnedState) -> str:
    """Why the report still owed can never settle as it stands, or "".

    A debt no record describes, first. Then the requirements the report next
    to be published was written against: the delivery where there is one,
    since binding it replaces any transaction, and the transaction otherwise.
    A record nobody can read answers "" here, and is parked by the owner that
    reads it.
    """
    if _drift_reports._owes_an_unrecorded_report(state):
        return _UNRECORDED
    if _delivery_state.carries_delivered_report(state):
        delivered = _delivery_state.read_delivered_report(state)
        written_against = None if delivered is None else delivered.requirements_revision
    else:
        pending = _record_state.read_pending_report(state)
        written_against = None if pending is None else pending.subject.requirements_revision
    if written_against is None or written_against == state.get(_USER_CONTENT_HASH):
        return ""
    return _MOVED_REQUIREMENTS


def _refusal_after_settling(
    gh: GitHubClient,
    spec: _config_models.RepoSpec,
    issue: Issue,
    state: PinnedState,
) -> str:
    """Why a report the settlement left owed will never settle, or "".

    The checkout first, since it costs no request, and then the thread. Every
    one of them is something the reconciliation stands down on rather than
    holding -- so a report the reviewer waits behind needs somebody told.
    """
    refusal = _checkout_refusal(spec, issue, state)
    if refusal:
        return refusal
    return _UNSETTLEABLE if _refuses_for_good(gh, issue, state) else ""


def _refuses_for_good(
    gh: GitHubClient, issue: Issue, state: PinnedState,
) -> bool:
    """Whether the thread has moved the owed transaction out of reach for good.

    The reading the implementing handoff takes before it parks, asked here
    for the same reason: our comment under this receipt no longer rendering
    as the report, or a verified location gone, changed, or written by an
    author this deployment does not trust, is content a human owns. The
    reconciliation stands down on it rather than holding -- correctly, since
    the routes behind it must run -- so nothing else would ever say so, and
    the reviewer would be suppressed for the life of the issue in silence.

    A pull request nobody could read is not one of those: it holds, since
    the next tick is as likely to read it.
    """
    pending = _record_state.read_pending_report(state)
    if pending is None:
        return False
    try:
        pull_request = gh.get_pr(pending.subject.pr_number)
    except Exception:
        log.exception(
            "issue=#%d could not read PR #%d to say whether the report it "
            "owes can still settle; holding for the next tick",
            issue.number, pending.subject.pr_number,
        )
        return False
    return _report_evidence.refuses_for_good(gh, pending, pull_request)


def _checkout_refusal(
    spec: _config_models.RepoSpec, issue: Issue, state: PinnedState,
) -> str:
    """Why the checkout a still-owed report stands on can never carry it, or "".

    One resolution and one reading for both answers, because they are one
    question asked of one worktree and the evidence the reconciliation takes
    asks them in this order too.

    Loose work first, and only paths git actually named: a status nobody could
    read holds rather than parks, since the next tick is as likely to read it.

    Then the HEAD, which is the refusal a clean checkout can still be sitting
    on. The evidence behind the reconciliation holds a bound transaction to
    the commit its subject names -- a checkout anywhere else describes other
    work -- and stands DOWN on a mismatch rather than holding, so the routes
    behind it keep running. On this stage there are no such routes while the
    report is owed: the reviewer is the only thing behind the hold, and it is
    exactly what the hold is stopping. Left unsaid, every later tick would
    settle nothing, spawn nobody, and tell nobody.
    """
    worktree = _worktree_creation._ensure_worktree(
        spec, issue.number,
        branch=_naming._resolve_branch_name(state, spec, issue.number),
    )
    tree = _worktree_status._worktree_status(worktree)
    if not tree.readable:
        return ""
    if tree.paths:
        return _LOOSE_CHECKOUT
    return _moved_off_the_commit(worktree, state)


def _moved_off_the_commit(worktree: Path, state: PinnedState) -> str:
    """Why a clean checkout cannot vouch for a bound transaction, or "".

    Asked of the TRANSACTION alone, since it is the record that names a
    commit: a delivery still waiting to be bound names none, and the binding
    that gives it one refuses a moved checkout where it stands.

    A head nobody could read is no mismatch: it holds, as the same reading
    does behind the reconciliation, since the next tick is as likely to read
    it.
    """
    pending = _record_state.read_pending_report(state)
    if pending is None:
        return ""
    head = _verification_probes._head_sha(worktree)
    if not head or head == pending.subject.source_sha:
        return ""
    return _MOVED_CHECKOUT


def _rewrite_holds_the_review(
    gh: GitHubClient, issue: Issue, state: PinnedState,
) -> bool:
    """Hold the reviewer over a head this orchestrator rewrote and no report is about yet.

    The pull request's head is read the way the reviewer's subject reads it,
    and a head nobody could read holds, since the next tick is as likely to
    read it. A report settled about that head pays the debt whatever the
    claim names, and the write that drops it goes out before the reviewer
    road, so no road behind it reads the paid claim back. A readable claim
    that explains the gap between the settled report and that head holds the
    review without a park. Anything else -- a claim nobody can read, another
    pull request or branch, a head somebody else pushed, a settled report of
    neither head -- holds nothing here: the reviewer road holds the report it
    finds to the head, and parks for one that is not about it.
    """
    if not _rewrite_debt.carries_rewrite_debt(state):
        return False
    pr_number = _rewrite_debt.pinned_pull_request(state)
    head = _review_report._pull_request_head(gh, issue, pr_number)
    if head is None:
        return True
    if _rewrite_debt.pays_the_debt(state, head):
        _rewrite_debt.drops_rewrite_debt(state)
        gh.write_pinned_state(issue, state)
        log.info(
            "issue=#%d settled a report of PR #%s's head %s; its rewrite's "
            "report debt is paid", issue.number, pr_number, head[:8],
        )
        return False
    debt = _rewrite_debt.read_rewrite_debt(state)
    if debt is None or not debt.explains(state, head):
        return False
    log.info(
        "issue=#%d PR #%s stands on %s, which this orchestrator rewrote from "
        "%s; holding the review until a report of it settles",
        issue.number, pr_number, head[:8], debt.previous_head[:8],
    )
    return True
