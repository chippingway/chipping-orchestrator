# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The developer report a reviewer is handed, resolved and re-read first.

A reviewer judges the work by the diff AND by the report of it, and it is
handed that report rather than left to find one: a reviewer fetching the pull
request picks whichever report it happens to read, and the recent-comment
excerpt its prompt quotes is bounded and covers the issue thread alone. So the
report the pinned comment records as current is read afresh from the exact
location the settlement recorded, held to its digest, and quoted whole.

The hold in `report_hold` has already answered every report this issue still
OWES, so what is resolved here is the one it last settled, and that one can
only be refused. Unreadable on the pinned comment, settled about another pull
request, out of step with the handoff that settled it, gone from where it was
recorded, or edited, cut short, or rewritten under an author this deployment
does not trust since -- each is a subject no reviewer may be run over, and
none of them is one a retry settles. So each parks under `report_undeliverable`
with the debt recorded, and the reply resumes the developer, whose report is
then published and reviewed. A reading nobody could take -- the pull request,
the location, the author -- holds the tick for the next one instead.

An issue that has never settled a report is reviewed with none, which is every
pull request opened before reports were published.

The same re-reading is taken again once an APPROVAL comes back, since the
reviewer ran for minutes and a human may have edited the report meanwhile. An
approval of words the pull request no longer carries is not acted on: the tick
records the run and ends, and the next one resolves the report as it now
stands.
"""
from __future__ import annotations

import logging
from types import MappingProxyType

from github.Issue import Issue

from orchestrator.github import pull_request_reports as _pr_reports
from orchestrator.github.client import GitHubClient
from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.engine import (
    prompt_delivery as _delivery,
    report_records as _records,
    report_settled_reading as _settled_reading,
    report_settlement_state as _settlement,
    review_subjects as _review_subjects,
)
from orchestrator.workflow.late_split import payloads as _payloads
from orchestrator.workflow.stages.validating import report_settlement as _report_settlement

log = logging.getLogger("orchestrator.workflow")

_UNREADABLE = (
    "the report this pull request is recorded as carrying is written on the "
    "pinned comment in a shape this orchestrator cannot read"
)

_MOVED = (
    "the report this issue last settled is about PR #{settled}, not the pull "
    "request under review"
)

_STALE = (
    "the report this issue records as current disagrees with the handoff that "
    "settled it, so neither says which revision is the latest"
)

_MISSING = (
    "the report this issue last settled is no longer at the location it was "
    "recorded at"
)

_EDITED = (
    "the report this issue last settled was edited, cut short, or rewritten "
    "under an author this deployment does not trust since it was recorded, so "
    "it is no longer the revision a reviewer may be handed"
)

# What each reading short of PRESENT refuses the review for. UNCONFIRMED is
# absent on purpose: a reading nobody could take holds instead.
_REFUSED = MappingProxyType({
    _pr_reports.ReportPresence.ABSENT: _MISSING,
    _pr_reports.ReportPresence.CHANGED: _EDITED,
})


def _resolves_the_subject(
    gh: GitHubClient,
    issue: Issue,
    state: PinnedState,
    pr_number,
    delivered: _delivery.PromptDeliverySnapshot,
) -> _review_subjects.ReviewSubject | None:
    """The subject this round's reviewer is handed, or None where it is not.

    None is a tick this owner ended: a refusal it parked, or a reading it
    could not take and holds for the next tick. The pull request's head is
    read first, since a subject names the commit the pull request carries and
    a head nobody could read is none.
    """
    number = _payloads.as_identity(pr_number)
    commit = _pull_request_head(gh, issue, number)
    if commit is None:
        return None
    report = None
    if _settlement.carries_settled_record(state):
        report = _settled_report(gh, issue, state, number)
        if report is None:
            return None
    return _review_subjects.ReviewSubject(
        pr_number=number,
        commit=commit,
        requirements_revision=delivered.requirements_revision or "",
        report=report,
    )


def _approval_still_covers(
    gh: GitHubClient,
    issue: Issue,
    state: PinnedState,
    subject: _review_subjects.ReviewSubject,
) -> bool:
    """Whether an approval that just came back is still about the report here.

    Nothing on the pinned comment moves while the reviewer runs, so what can
    have moved is the location: a human editing or deleting the report the
    reviewer was handed. It is re-read, and the words it holds now have to be
    the words the reviewer read. A subject with no report has nothing to
    re-read. A reading nobody could take is no proof either, and the approval
    it would have licensed waits for a reviewer who can be shown one.
    """
    if subject.report is None:
        return True
    current = _settlement.read_current_report(state)
    if current is not None:
        presence, text = _settled_reading.carried_text(gh, state, current)
        if presence is _pr_reports.ReportPresence.PRESENT and text == subject.report.text:
            return True
    log.warning(
        "issue=#%d reviewer approved developer report revision %d, which PR "
        "#%s no longer carries as it was handed; not acting on the approval",
        issue.number, subject.report.report_revision, subject.pr_number,
    )
    return False


def _pull_request_head(
    gh: GitHubClient, issue: Issue, number: int | None,
) -> str | None:
    """The commit the pull request stands on, "" with none, None unread.

    The head is read inside the guard with the lookup, because a fetched pull
    request is lazy and the request that can fail is that attribute read.
    """
    if number is None:
        return ""
    try:
        head = gh.get_pr(number).head.sha
    except Exception:
        log.exception(
            "issue=#%d could not read PR #%d to name the commit its reviewer "
            "is handed; holding the review for the next tick",
            issue.number, number,
        )
        return None
    return head or ""


def _settled_report(
    gh: GitHubClient, issue: Issue, state: PinnedState, number: int | None,
) -> _review_subjects.ReviewReport | None:
    """The complete settled report, re-read, or None where none is handed.

    The pinned pair is judged before anything is requested, then the location
    is read. A refusal parks here and an unreadable location holds, and both
    answer None.
    """
    current = _settlement.read_current_report(state)
    refusal = _settled_refusal(state, current, number)
    if refusal:
        _report_settlement._parks(gh, issue, state, refusal)
        return None
    presence, text = _settled_reading.carried_text(gh, state, current)
    if presence is _pr_reports.ReportPresence.PRESENT:
        return _review_subjects.ReviewReport(
            text=text,
            report_revision=current.report_revision,
            content_revision=current.content_revision,
            source_sha=current.subject.source_sha,
            requirements_revision=current.subject.requirements_revision,
            location=current.location,
        )
    refused = _REFUSED.get(presence)
    if refused:
        _report_settlement._parks(gh, issue, state, refused)
    else:
        log.info(
            "issue=#%d could not re-read developer report revision %d on PR "
            "#%d; holding the review for the next tick",
            issue.number, current.report_revision, current.subject.pr_number,
        )
    return None


def _settled_refusal(
    state: PinnedState,
    current: _records.CurrentReport | None,
    number: int | None,
) -> str:
    """Why the settled pair can hand no reviewer a report, or "".

    The pair is written in one write, so a current report its handoff does not
    describe -- another revision, another pull request, another commit -- is
    one of them replaced by something other than a settlement.
    """
    if current is None:
        return _UNREADABLE
    if current.subject.pr_number != number:
        return _MOVED.format(settled=current.subject.pr_number)
    handoff = _settlement.read_handoff(state)
    if handoff is None or (
        handoff.pr_number, handoff.report_revision, handoff.source_sha,
    ) != (
        current.subject.pr_number, current.report_revision,
        current.subject.source_sha,
    ):
        return _STALE
    return ""
