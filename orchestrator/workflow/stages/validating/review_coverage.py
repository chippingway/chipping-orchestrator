# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Whether an approval still covers the subject that stands when it is acted on.

A reviewer is handed a subject -- the pull request, the head it stands on, the
requirements revision, and the developer report -- and an approval is of that
subject and nothing else. Every one of them can move between the spawn and the
moment the approval is acted on, and the head is the one thing the stamps an
approval leaves behind are keyed on. So an approval is held to the subject
standing NOW wherever it is about to be relied on.

When the reviewer returns, the whole subject is resolved again the way
`review_report` resolved it before the spawn -- over the issue read afresh --
and has to equal the one handed over. Later, once the pinned records already
agree that the report recorded as current is the one approved, the report is
read at its location once more, since no pinned record sees a human editing or
deleting the comment in place: the settled squash handoff on this stage asks
it before moving the label past the reviewer, and `in_review` asks it before
the approval may stand behind a ready ping.

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
    report_settled_reading as _settled_reading,
    report_settlement_state as _settlement,
    review_subjects as _review_subjects,
)
from orchestrator.workflow.stages.validating import review_report as _review_report

log = logging.getLogger("orchestrator.workflow")


def _approval_still_covers(
    gh: GitHubClient,
    issue: Issue,
    state: PinnedState,
    subject: _review_subjects.ReviewSubject,
) -> bool:
    """Whether an approval that just came back is of the subject standing now.

    The whole subject is resolved again, exactly as it was before the spawn,
    and has to equal the one the reviewer was handed: the pull request, the
    head it stands on, the requirements over an issue read afresh, and the
    report -- revision, digest, location, and words. The reviewer ran for
    minutes, and a push, an edit of the issue, or a human editing or removing
    the report in that time is a subject nobody reviewed, whether or not the
    reviewer was handed a report at all. A reading nobody could take is no
    proof either. Nothing is parked here: the next tick resolves the subject
    for a reviewer of its own, and refuses it there if it has to.
    """
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


def _approved_report_stands(gh: GitHubClient, state: PinnedState) -> bool | None:
    """Whether the report the recorded approval covered still reads as settled.

    Asked by whoever would act on an approval after the round that earned it
    -- the settled squash handoff here, and `in_review` -- once the pinned
    records agree, since those records cannot see a human editing or deleting
    the report comment in place. True where it still reads, and where there is
    nothing to read: no approval recorded, one the pinned records already
    refuse, or an approval of no report. False where it reads ABSENT or
    CHANGED. None where the reading could not be taken.
    """
    if not state.carries(_review_subjects.APPROVED_SUBJECT):
        return True
    if not _review_subjects.approval_covers_current(state):
        return True
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
