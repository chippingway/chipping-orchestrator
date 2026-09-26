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

A report that reads intact is still refused where it is STALE against the
subject it would be handed with: written about another commit than the one the
pull request stands on -- a rebase, a squash, a push nobody reported -- or
against requirements the issue has moved past, which is the rule the hold
already holds an owed report to. Both are asked of the drift baseline and the
head rather than of the reviewer's own read, because that read also carries the
reply that bought a retried or granted round, which is no requirement a
developer answers; any other change to the thread is a drift the check ahead of
this has already resumed the developer on. An `ACK:` that answered an edit
leaves the report written against the requirements before it, and is refused
the same way: the reply to the park it earns is the developer's chance to say
what the report says now.

The requirements the reviewer is handed are its own read, taken after the drift
check -- so a criterion landing in between reaches the reviewer beside a report
that never saw it. That read has to be the revision the round was due to hand
over: the baseline the drift check measured, or, on a round a reply bought, the
thread through that reply, which is the reviewer's to read. Anything written
after it is held: nothing is parked, the note that the round is owed is
dropped -- so the drift check stops standing down for it -- and the tick's
state is written, and the next tick's drift check resumes the developer on the
new words before any reviewer is handed the report. A round a deferral left
owed, over an edit nobody delivered, is held on the same terms, since that edit
is exactly the change the report never saw.

Every hold writes what the tick staged before it: a park the awaiting branch
cleared into this round, and a cap grant with the notice already announcing
it, would otherwise be answered again on every poll the hold lasts.

A pull request with no report recorded at all is refused on the same terms,
since a reviewer handed none would be judging work nobody has described and a
silent hold would wait on a report no road is writing: the park records the
debt, so the reply resumes the developer for one. That is every pull request
opened before reports were published, and any road that delivered code without
a report.

The subject is resolved from the state the tick read when it began, so the
pinned comment is read once more before anything is decided, and has to carry
the report records that state carries (`review_comment`): a later report
settled in between is there and nowhere in hand. Where it does not, or will not
read, the tick ends with nothing handed over and nothing written, since any
write would put the replaced report back; the next tick resolves the later
one. That reading is handed on with the subject, and it is what the verdict's
return measures the comment against.

The reading itself posts nothing and parks nothing, so `review_coverage` takes
it again once an approval comes back and wherever an approval is later acted
on, and holds that approval to the subject standing then.
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
from orchestrator.workflow.stages.validating import (
    report_settlement as _report_settlement,
    review_comment as _review_comment,
    state as _validating_state,
)

log = logging.getLogger("orchestrator.workflow")

_UNREPORTED = (
    "no developer report is recorded for it, so a reviewer would be judging "
    "work nobody has described"
)

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

_MOVED_COMMIT = (
    "the report this issue last settled is about commit `{reported}`, and the "
    "pull request now stands on `{head}`"
)

_MOVED_REQUIREMENTS = (
    "the report this issue last settled was written against requirements the "
    "issue has since moved past"
)

_USER_CONTENT_HASH = "user_content_hash"

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
) -> _review_comment._ResolvedSubject | None:
    """The subject this round's reviewer is handed, or None where it is not.

    None is a tick this owner ended: a refusal it parked, or a reading it
    could not take and holds for the next tick. A subject read whole is held
    to the staleness rules here and nowhere else, since they are about handing
    a report to a reviewer; a subject read again once the reviewer returns is
    held to equality with this one instead. Nothing is decided or written
    until the pinned comment is read and agrees with the state the subject was
    resolved from -- see `review_comment`.
    """
    subject, refusal = _reads_the_subject(
        gh, issue, state, pr_number, delivered.requirements_revision or "",
    )
    resolved_over = _review_comment._resolved_over(gh, issue, state)
    if resolved_over is None:
        return None
    if subject is not None and _outran_the_drift_check(state, subject):
        log.info(
            "issue=#%d thread moved past what its reviewer was due to be "
            "handed; holding for the drift road", issue.number,
        )
        _validating_state._discharges_the_owed_round(state)
        subject = None
    elif subject is not None:
        refusal = _stale_refusal(state, subject)
    if refusal:
        _report_settlement._parks(gh, issue, state, refusal)
        return None
    if subject is None:
        log.info(
            "issue=#%d holding the review for the next tick", issue.number,
        )
        gh.write_pinned_state(issue, state)
        return None
    return _review_comment._ResolvedSubject(subject, resolved_over)


def _reads_the_subject(
    gh: GitHubClient,
    issue: Issue,
    state: PinnedState,
    pr_number,
    requirements: str,
) -> tuple[_review_subjects.ReviewSubject | None, str]:
    """The subject as it stands, or why none may be handed, posting nothing.

    `(subject, "")` where one is handed, `(None, refusal)` where the settled
    report is refused for good, and `(None, "")` where a reading could not be
    taken. The pull request's head is read first, since a subject names the
    commit the pull request carries and a head nobody could read is none.
    """
    number = _payloads.as_identity(pr_number)
    commit = _pull_request_head(gh, issue, number)
    if commit is None:
        return None, ""
    if not _settlement.carries_settled_record(state):
        return None, _UNREPORTED
    report, refusal = _settled_report(gh, state, number)
    if report is None:
        return None, refusal
    return _review_subjects.ReviewSubject(
        pr_number=number,
        commit=commit,
        requirements_revision=requirements,
        report=report,
    ), ""


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
            "is handed", issue.number, number,
        )
        return None
    return head or ""


def _settled_report(
    gh: GitHubClient, state: PinnedState, number: int | None,
) -> tuple[_review_subjects.ReviewReport | None, str]:
    """The complete settled report re-read, or why none is handed.

    The pinned pair is judged before anything is requested, then the location
    is read. A refusal answers `(None, refusal)` and an unreadable location
    `(None, "")`.
    """
    current = _settlement.read_current_report(state)
    refusal = _settled_refusal(state, current, number)
    if refusal:
        return None, refusal
    presence, text = _settled_reading.carried_text(gh, state, current)
    if presence is not _pr_reports.ReportPresence.PRESENT:
        return None, _REFUSED.get(presence, "")
    return _review_subjects.ReviewReport(
        text=text,
        report_revision=current.report_revision,
        content_revision=current.content_revision,
        source_sha=current.subject.source_sha,
        requirements_revision=current.subject.requirements_revision,
        location=current.location,
    ), ""


def _outran_the_drift_check(
    state: PinnedState, subject: _review_subjects.ReviewSubject,
) -> bool:
    """Whether a reviewer would be handed requirements newer than it was due.

    Due the drift baseline, or the thread through the reply that bought the
    round where one did and said how far it reached. Only where there is a
    report the newer words could be missing from.
    """
    if subject.report is None:
        return False
    due = state.get(_USER_CONTENT_HASH)
    through = state.get(_validating_state._ROUND_BOUGHT_THROUGH)
    owed = state.get(_validating_state._REVIEWER_OWES_A_ROUND)
    if owed == _validating_state._ROUND_BOUGHT_BY_A_REPLY and through:
        due = through
    return subject.requirements_revision != due


def _stale_refusal(
    state: PinnedState, subject: _review_subjects.ReviewSubject,
) -> str:
    """Why a report read intact is too old to hand this reviewer, or "".

    Against the head the pull request stands on, and against the requirements
    baseline the drift check holds the issue to.
    """
    report = subject.report
    if report is None:
        return ""
    if report.source_sha != subject.commit:
        return _MOVED_COMMIT.format(reported=report.source_sha, head=subject.commit)
    if report.requirements_revision != state.get(_USER_CONTENT_HASH):
        return _MOVED_REQUIREMENTS
    return ""


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
