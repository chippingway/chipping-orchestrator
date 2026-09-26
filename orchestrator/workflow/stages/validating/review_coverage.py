# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Whether an approval still covers the subject that stands when it is acted on.

A reviewer is handed a subject -- the pull request, the head it stands on, the
requirements revision, and the developer report -- and an approval is of that
subject and nothing else. Every one of them can move between the spawn and the
moment the approval is acted on, and the head is the one thing the stamps an
approval leaves behind are keyed on. So an approval is held to the subject
standing NOW wherever it is about to be relied on.

When the reviewer returns, the pinned comment is read again first: the
settlement the tick carries in hand is the one it read before the spawn, and a
report settling on the same head while the reviewer ran is a subject that
record cannot see. A report record the comment moved meanwhile refuses the
verdict, and everything that write moved is carried onto the state in hand, so
the write that records the run lays itself over the newer settlement instead
of putting the one the reviewer was handed back as current. Only then is the
whole subject resolved again the way `review_report` resolved it before the
spawn -- over the issue read afresh -- and has to equal the one handed over.
Later, the approval is held to the
report recorded as current -- the pinned records have to agree it is the one
approved, and the report is read at its location once more, since no pinned
record sees a human editing or deleting the comment in place. The squash tail
asks it before moving the label past the reviewer, whether an approval or the
recovery of a squash an earlier tick did not finish sent it there; the settled
handoff asks it before moving a label that tail left owed; and `in_review` asks
it before the approval may stand behind a ready ping.

Nothing here parks or posts. What a refusal owes is the next reviewer
round's to decide, and that round resolves the subject for itself.
"""
from __future__ import annotations

import logging

from github.Issue import Issue

from orchestrator.github import pull_request_reports as _pr_reports
from orchestrator.github.client import GitHubClient
from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.engine import (
    prompt_context as _prompt_context,
    report_records as _records,
    report_settled_reading as _settled_reading,
    report_settlement_state as _settlement,
    review_subjects as _review_subjects,
    run_charge_state as _run_charge_state,
)
from orchestrator.workflow.stages.validating import review_report as _review_report

log = logging.getLogger("orchestrator.workflow")

# Every record a developer report's transaction moves on the pinned comment:
# one in flight, the delivery it binds, and the settled pair a settlement
# replaces.
_REPORT_RECORDS = (
    _records.PENDING_REPORT,
    _records.DELIVERED_REPORT,
    _records.CURRENT_REPORT,
    _records.REPORT_HANDOFF,
)


def _subject_still_stands(
    gh: GitHubClient,
    issue: Issue,
    state: PinnedState,
    subject: _review_subjects.ReviewSubject,
    spawned_over: dict,
) -> bool:
    """Whether a verdict that just came back is of the subject standing now.

    `spawned_over` is the pinned comment as it was read before the reviewer
    spawned. It is read again first, since a report that settled while the
    reviewer ran is recorded there and nowhere in the state in hand -- see
    `_settled_while_it_ran`. Then the whole subject is resolved again,
    exactly as it was before the spawn, and has to equal the one the
    reviewer was handed: the pull request, the head it stands on, the
    requirements over an issue read afresh, and the report -- revision,
    digest, location, and words. The reviewer ran for minutes, and a push, an
    edit of the issue, or a human editing or removing the report in that time
    is a subject nobody reviewed. A reading nobody could take is no proof
    either. Nothing is parked here: the next tick resolves the subject for a
    reviewer of its own, and refuses it there if it has to.
    """
    if _settled_while_it_ran(gh, issue, state, spawned_over):
        return False
    requirements = _fresh_requirements(gh, issue, state)
    standing = None
    if requirements is not None:
        standing, _ = _review_report._reads_the_subject(
            gh, issue, state, subject.pr_number, requirements,
        )
    if standing == subject:
        return True
    log.warning(
        "issue=#%d reviewer approved a subject PR #%s no longer stands on as "
        "it was handed; not acting on the approval", issue.number,
        subject.pr_number,
    )
    return False


def _settled_while_it_ran(
    gh: GitHubClient, issue: Issue, state: PinnedState, spawned_over: dict,
) -> bool:
    """Whether the pinned comment moved a report record since the spawn.

    Read off the comment itself, since the state in hand was read before the
    reviewer ran and a settlement landing meanwhile -- a later revision on
    the very head the reviewer approved -- is invisible there: its current
    report still reads, at its own location, exactly as it was handed. Moved,
    everything the comment changed since `spawned_over` is carried onto
    `state`, which is what the write recording this run then lays itself
    over; written from the copy in hand, that write would put the report the
    reviewer was handed back as current over the one that replaced it. A
    comment that will not read or will not parse is no proof the records
    stand, and carries nothing: a record read back empty is no settlement to
    keep.
    """
    try:
        durable = gh.read_pinned_state(issue)
    except Exception:
        log.exception(
            "issue=#%d could not read its pinned comment again to see whether "
            "a report settled while the reviewer ran; not acting on the "
            "verdict", issue.number,
        )
        return True
    if durable.parsed and all(
        durable.data.get(record) == spawned_over.get(record)
        for record in _REPORT_RECORDS
    ):
        return False
    if durable.parsed:
        _run_charge_state._merge_circuit_fields(spawned_over, durable, state)
    log.warning(
        "issue=#%d its developer report records moved on the pinned comment "
        "while the reviewer ran; keeping them and not acting on the verdict",
        issue.number,
    )
    return True


def _approval_stands(gh: GitHubClient, state: PinnedState) -> bool | None:
    """Whether the recorded approval still covers the report the pull request carries.

    Asked by whoever would act on an approval after the round that earned it.
    The pinned records first -- `review_subjects.approval_covers_current` --
    and then the report itself at its location, which those records cannot
    see a human editing or deleting in place. True where both agree, and
    where there is no report at all to read. False where the records refuse
    the approval or the location reads ABSENT or CHANGED. None where the
    reading could not be taken.
    """
    if not _review_subjects.approval_covers_current(state):
        return False
    current = _settlement.read_current_report(state)
    if current is None:
        return True
    presence = _settled_reading.still_carries(gh, state, current)
    if presence is _pr_reports.ReportPresence.UNCONFIRMED:
        return None
    return presence is _pr_reports.ReportPresence.PRESENT


def _fresh_requirements(
    gh: GitHubClient, issue: Issue, state: PinnedState,
) -> str | None:
    """The requirements revision of the issue read afresh, or None unread.

    Fingerprinted by the same read a reviewer's prompt is built from, so it is
    comparable with the revision the subject was handed; the issue in hand was
    fetched before the reviewer ran and cannot show an edit made meanwhile.
    """
    try:
        return _prompt_context._delivered_thread(
            gh, gh.get_issue(issue.number), state,
        ).requirements_revision or ""
    except Exception:
        log.exception(
            "issue=#%d could not read the issue again to compare the subject "
            "its reviewer approved", issue.number,
        )
        return None
