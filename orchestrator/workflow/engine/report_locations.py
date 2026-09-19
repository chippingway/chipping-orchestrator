# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Which places on a pull request this issue's reports claim as their own.

A report can live in a pull request's DESCRIPTION, the one place a publication
also needs something of -- and even an edit keeping every word moves a verified
description off its digest. So the claim is asked of every record that can hold
one, a record nobody can read included, before anybody is told what to do with
that description; a report in a comment is out of a body edit's reach. The
second reading is what the description must say before the work is handed on
-- a closing reference and the session -- and the third is which publication a
SETTLED report is about, a claim its caller re-reads.

`report_binding` and the implementing stage's `pr_description` ask the first
two, and no stage calls either of them yet: the publication keeps reading and
writing a description as it does until its integration stands on these answers.
"""
from __future__ import annotations

import re
from typing import Any

from orchestrator.github import pinned_state as _pinned_state
from orchestrator.github.pull_request_reports import ReportLocation
from orchestrator.workflow.engine import (
    report_delivery_state as _delivery_state,
    report_prose as _prose,
    report_record_fields as _fields,
    report_record_state as _record_state,
    report_records as _records,
    report_replay_guards as _replay_guards,
    report_settlement_state as _settlement,
)

# Every spelling GitHub closes an issue on, as it documents them: one of the
# keywords, then the issue -- bare, or qualified `owner/repository#N`. Read
# here rather than compared against the line this workflow writes, because what
# is being asked is whether the MERGE will close the issue. Only spaces and
# tabs part the keyword from the issue: a no-break space is no space to GitHub,
# and neither is the end of a line.
_CLOSES_THE_ISSUE = re.compile(
    r"\b(?:close[sd]?|fix(?:e[sd])?|resolve[sd]?)\b[ \t]*:?[ \t]*"
    r"(?P<repo>[\w.-]+/[\w.-]+)?#(?P<issue>[0-9]+)\b",
    re.IGNORECASE,
)

# What a number is compared without. As digits, never as a number: a
# description may hold more of them than Python will convert, and one that long
# names no issue.
_LEADING_ZERO = "0"

# Every record a report's location can be claimed by, beside the reader that
# types it.
_CLAIMING_RECORDS = (
    (_records.DELIVERED_REPORT, _delivery_state.read_delivered_report),
    (_records.PENDING_REPORT, _record_state.read_pending_report),
    (_records.CURRENT_REPORT, _settlement.read_current_report),
)


def claims_the_description(
    state: _pinned_state.PinnedState, pr_number: int,
) -> bool:
    """Whether a report of this issue's is the description of `pr_number`.

    All three records, since the claim outlives each of them separately. A
    record nobody can read claims this description unless the place it still
    names is readably elsewhere: the roads that park such a record run after
    the edit this answers, so read as no claim it is a description changed
    before anything says the record was damaged. False for an issue carrying
    none of them, and for every report that lives in a comment.
    """
    return _dangles_on(state, pr_number) or any(
        _claims(state.get(key), reader(state), pr_number)
        for key, reader in _CLAIMING_RECORDS
    )


def _dangles_on(state: _pinned_state.PinnedState, pr_number: int) -> bool:
    """Whether a settled pair missing its current report may name this PR.

    A settled key holding `null`, or a handoff whose current report is gone,
    is damage rather than an absence -- nothing clears a settlement -- so the
    report it settled may be this pull request's description. Only a handoff
    that readably names another pull request says it is not.
    """
    if state.get(_records.CURRENT_REPORT) is not None:
        return False
    if not _settlement.carries_settled_record(state):
        return False
    handoff = _settlement.read_handoff(state)
    return handoff is None or handoff.pr_number == pr_number


def _claims(recorded: Any, record: Any, pr_number: int) -> bool:
    """Whether one record, typed or not, may be this pull request's description.

    The typed record answers wherever it reads. Where it does not, the raw
    location is read on its own, since that half can survive damage to the
    rest; and a record that names no readable place at all may name this one.
    """
    if recorded is None:
        return False
    if record is not None:
        return _names_the_description(record.location, pr_number)
    if not isinstance(recorded, dict):
        return True
    location = _fields.location_from(recorded)
    return location is None or _names_the_description(location, pr_number)


def settled_publication(
    state: _pinned_state.PinnedState,
    repo_slug: str,
    pr_number: int,
    branch: str,
    source_sha: str,
) -> _records.CurrentReport | None:
    """The settled report about this commit on this pull request, or None.

    Both settled records, agreeing with each other -- they are written in one
    write, so a pair naming two publications is one nothing here wrote -- and
    naming this repository, pull request, branch and commit. What comes back
    is a CLAIM, not a reading: the report may have been edited or deleted
    since, so a caller about to hand the work on re-reads it first. None
    wherever either record cannot be read, which holds the work.
    """
    current = _settlement.read_current_report(state)
    handoff = _settlement.read_handoff(state)
    if current is None or handoff is None:
        return None
    if _replay_guards.companions_disagree(current, handoff):
        return None
    subject = current.subject
    settled = (
        subject.repo_slug, subject.pr_number, subject.branch, subject.source_sha,
    )
    publication = (repo_slug, pr_number, branch, source_sha)
    return current if settled == publication else None


def describes_the_issue(
    pull_request: Any, issue_number: int, attribution: str, repo_slug: str,
) -> bool:
    """Whether a description still says what a publication needs it to say.

    The CLOSING reference, which GitHub honours in the description and
    nowhere else, and the ATTRIBUTION every later reuse reads back. Any
    spelling GitHub accepts counts -- `Fixes #12`, or `Fixes owner/repo#12`
    naming this repository -- outside literal code, which GitHub does not act
    on; one naming another repository does not. A reference is ASCII from end
    to end: matched without case, a pattern takes a long s for an `s` and a
    Kelvin sign for a `k`, which GitHub does not. An unread body says nothing,
    which holds the work back.
    """
    body = getattr(pull_request, "body", None)
    if not isinstance(body, str):
        return False
    found = _CLOSES_THE_ISSUE.finditer(_prose.outside_code(body))
    closing = (reference for reference in found if reference.group().isascii())
    return attribution in body and any(
        reference["issue"].lstrip(_LEADING_ZERO) == str(issue_number)
        and (reference["repo"] or repo_slug).lower() == repo_slug.lower()
        for reference in closing
    )


def costs_the_description(
    record: Any, pr_number: int, describes_the_issue: bool,
) -> bool:
    """Whether keeping this report would leave that publication unnamed.

    Exactly a verification on this pull request's description when that
    body -- as the caller read it -- does not close the issue and name the
    session.
    """
    return (
        _names_the_description(getattr(record, "location", None), pr_number)
        and not describes_the_issue
    )


def _names_the_description(
    location: ReportLocation | None, pr_number: int,
) -> bool:
    """Whether one location is this pull request's description.

    A comment id names a comment; a record with no location names nothing.
    """
    if location is None or location.comment_id is not None:
        return False
    return location.pr_number == pr_number
