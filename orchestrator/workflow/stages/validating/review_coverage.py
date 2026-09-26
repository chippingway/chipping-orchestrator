# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Whether an approval still covers the subject that stands when it is acted on.

A reviewer is handed a subject -- the pull request, the head it stands on, the
requirements revision, and the developer report -- and an approval is of that
subject and nothing else. Every one of them can move between the spawn and the
moment the approval is acted on, and the head is the one thing the stamps an
approval leaves behind are keyed on. So an approval is held to the subject
standing NOW wherever it is about to be relied on.

When the reviewer returns, and again once its approval is verified, the
report records on the pinned comment are asked first (`review_comment`): a
report settling on the same head while the reviewer ran is a subject the
records in hand cannot see, and refuses the verdict. Only where they stand is
the whole subject resolved again the way `review_report` resolved it before
the spawn -- over the issue read afresh -- and has to equal the one handed
over. Later, the approval is held to the
report recorded as current -- the pinned records have to agree it is the one
approved, and the report is read at its location once more, since no pinned
record sees a human editing or deleting the comment in place -- to the
requirements, over the issue read afresh, which have to be the revision the
approval was given as well as the one the drift baseline holds, since an edit
landing after either was taken is requirements nobody reviewed -- and to the
head, over the pull request read afresh, which has to be the commit the move
is owed over, since a push landing meanwhile is a commit nobody approved
(`_approval_holds`). The squash tail asks it before moving the label past the
reviewer, whether an approval or the recovery of a squash an earlier tick did
not finish sent it there; the settled handoff asks it before moving a label
that tail left owed; and `in_review` asks it before the approval may stand
behind a ready ping.

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
from orchestrator.workflow.late_split import payloads as _payloads
from orchestrator.workflow.stages.validating import review_report as _review_report

log = logging.getLogger("orchestrator.workflow")

# The requirements baseline the drift check holds an issue to.
_USER_CONTENT_HASH = "user_content_hash"

_PR_NUMBER = "pr_number"


def _subject_still_stands(
    gh: GitHubClient,
    issue: Issue,
    state: PinnedState,
    subject: _review_subjects.ReviewSubject,
) -> bool:
    """Whether a verdict that just came back is of the subject standing now.

    Asked once `review_comment` has found the report records where they were.
    The whole subject is resolved again, exactly as it was before the spawn,
    and has to equal the one the reviewer was handed: the pull request, the
    head it stands on, the requirements over an issue read afresh, and the
    report -- revision, digest, location, and words. The reviewer ran for
    minutes, and a push, an edit of the issue, or a human editing or removing
    the report in that time is a subject nobody reviewed. A reading nobody
    could take is no proof either. Nothing is parked here: the next tick
    resolves the subject for a reviewer of its own, and refuses it there if it
    has to.
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


def _approval_stands(gh: GitHubClient, state: PinnedState) -> bool | None:
    """Whether the recorded approval still covers the report the pull request carries.

    Asked by whoever would act on an approval after the round that earned it.
    The pinned records first -- `review_subjects.approval_covers_current`,
    and then the pair a settlement writes in one write, held to each other
    exactly as a reviewer spawn holds them (`review_report._settled_refusal`):
    a current report its handoff does not describe is one of the two replaced
    by something other than a settlement, and neither says which revision is
    the latest -- and then the report itself at its location, which those
    records cannot see a human editing or deleting in place. True where all of
    it agrees, and where there is no report at all to read. False where the
    records refuse the approval or each other, or the location reads ABSENT
    or CHANGED. None where the reading could not be taken.
    """
    if not _review_subjects.approval_covers_current(state):
        return False
    current = _settlement.read_current_report(state)
    if current is None:
        return True
    if _review_report._settled_refusal(
        state, current, _payloads.as_identity(state.get(_PR_NUMBER)),
    ):
        return False
    presence = _settled_reading.still_carries(gh, state, current)
    if presence is _pr_reports.ReportPresence.UNCONFIRMED:
        return None
    return presence is _pr_reports.ReportPresence.PRESENT


def _approval_holds(
    gh: GitHubClient, issue: Issue, state: PinnedState, head: str | None,
) -> bool | None:
    """Whether the recorded approval covers the report, requirements, and head standing now.

    Asked by every road about to move an approval on: `_approval_stands`
    first, then `_requirements_stand` over the issue read afresh, and then
    `_head_stands` over the pull request read afresh, which has to stand on
    `head` -- the commit the move is owed over. False where any has moved,
    None where any could not be read.
    """
    covered = _approval_stands(gh, state)
    if not covered:
        return covered
    fresh = _requirements_stand(gh, issue, state)
    if not fresh:
        return fresh
    return _head_stands(gh, issue, state, head)


def _requirements_stand(
    gh: GitHubClient, issue: Issue, state: PinnedState,
) -> bool | None:
    """Whether the issue, read afresh, carries the requirements the approval was given.

    The revision the recorded approval names, and the one the drift baseline
    holds, both: the drift check that measured the baseline ran requests ago
    -- before a squash, before the mergeability reads ahead of a ready ping --
    and an edit landing since is requirements nobody has been handed, let
    alone reviewed, while a baseline that has moved on to the edited issue
    since the approval -- a developer resumed on the edit, a reply settled --
    says nothing about what the reviewer read. An approval nothing recorded
    names no revision, and is held to the baseline alone. None where the issue
    could not be read again, which is no proof either way.
    """
    fresh = _fresh_requirements(gh, issue, state)
    if fresh is None:
        return None
    approved = fresh
    if state.carries(_review_subjects.APPROVED_SUBJECT):
        approved = _review_subjects.ReviewSubject.requirements_recorded_in(
            state.get(_review_subjects.APPROVED_SUBJECT),
        )
    if fresh == state.get(_USER_CONTENT_HASH) and fresh == approved:
        return True
    log.info(
        "issue=#%d requirements moved past the approval it holds; not acting "
        "on that approval this tick", issue.number,
    )
    return False


def _head_stands(
    gh: GitHubClient, issue: Issue, state: PinnedState, head: str | None,
) -> bool | None:
    """Whether the pull request, read afresh, still stands on `head`.

    `head` is the commit an approval's move is owed over: the one a squash
    published, the one a settled handoff recorded, or the one a ready ping
    names. A push landing while the reads before it were taken is a commit
    nobody approved, and moved past it would hand that commit on as reviewed.
    An issue with no pull request has nothing that could have moved, and the
    move is owed as recorded; a commit nobody named, or a pull request nobody
    could read, vouches for nothing, and the answer is None.

    The head is read inside the guard with the lookup, because a fetched pull
    request is lazy and the request that can fail is that attribute read.
    """
    pr_number = _payloads.as_identity(state.get(_PR_NUMBER))
    if pr_number is None:
        return True
    if not head:
        return None
    try:
        standing = gh.get_pr(pr_number).head.sha
    except Exception:
        log.exception(
            "issue=#%d could not read PR #%d again to see where it stands "
            "before acting on its approval", issue.number, pr_number,
        )
        return None
    if standing == head:
        return True
    log.info(
        "issue=#%d PR #%d stands on %s, not %s its approval's move is owed "
        "over; not acting on that approval this tick",
        issue.number, pr_number, standing, head,
    )
    return False


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
