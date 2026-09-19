# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The reviewer, held while this issue still owes its pull request a report.

A review of work whose report nothing on the pull request carries is the review
the report contract exists to prevent, so the validating handler asks this last
before its spawn. The hold settles what it can first -- a delivery a later
publication carried out is bound and settled through `report_settlement` -- and
parks for a human where no retry can: a report written against requirements the
issue no longer has, one no publication here can carry, one standing over a
checkout that carries loose work, one the thread has moved out of reach --
edited, removed, or written by an author this deployment does not trust -- and
a debt no record describes at all, a run that committed and wrote no report. A reply resumes the session through the
drift route, and the report it writes then supersedes the one that could not be
delivered.
"""
from __future__ import annotations

import logging

from github.Issue import Issue

from orchestrator.config import models as _config_models
from orchestrator.git.verification import status as _worktree_status
from orchestrator.git.worktrees import creation as _worktree_creation, naming as _naming
from orchestrator.github.client import GitHubClient
from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.engine import (
    report_delivery as _report_delivery,
    report_delivery_state as _delivery_state,
    report_evidence as _report_evidence,
    report_record_state as _record_state,
)
from orchestrator.workflow.stages.validating import (
    drift_reports as _drift_reports,
    report_settlement as _settlement,
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
    carrying loose work, and a report on the thread somebody has edited,
    removed, or written untrusted. Both are content a human owns, so the
    reconciliation stands down on them for as long as they stand, and held
    silently they would suppress every later reviewer with nobody told.
    """
    if not _report_delivery.owes_a_report(state):
        return False
    refusal = _refusal_before_settling(state)
    if refusal:
        _settlement._parks(gh, issue, state, refusal)
        return True
    _settlement._settles_the_report(gh, spec, issue, state, WorkflowLabel.VALIDATING)
    if not _report_delivery.owes_a_report(state):
        return False
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

    The checkout first, since it costs no request, and then the thread. Both
    are content a human owns, which the reconciliation stands down on rather
    than holding -- so a report the reviewer waits behind needs somebody told.
    """
    if _carries_loose_work(spec, issue, state):
        return _LOOSE_CHECKOUT
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


def _carries_loose_work(
    spec: _config_models.RepoSpec, issue: Issue, state: PinnedState,
) -> bool:
    """Whether the checkout a still-owed report stands on names loose paths.

    Only paths git actually named: a status nobody could read holds rather
    than parks, since the next tick is as likely to read it.
    """
    tree = _worktree_status._worktree_status(_worktree_creation._ensure_worktree(
        spec, issue.number,
        branch=_naming._resolve_branch_name(state, spec, issue.number),
    ))
    return bool(tree.readable and tree.paths)
