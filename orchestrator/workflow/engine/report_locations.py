# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Which places on a pull request this issue's reports claim as their own.

A report can live in a pull request's DESCRIPTION, the one place this workflow
also edits for its own reasons: a pull request opened elsewhere gets the closing
reference and the attribution put above what it says. The two meet on the pull
request a developer verified a report on, and changing that body by a single
character -- even keeping every word -- moves it off the digest the
verification recorded, so the transaction stays owed and the work never leaves
this stage.

So the claim is asked BEFORE any such edit, of every record that can hold one:
the report a run delivered, the transaction it was bound into, and the report a
pull request is recorded as carrying. A record nobody can read is asked too, for
whatever place it still names. A report in a COMMENT is out of reach of a body
edit, and nothing here edits a comment.

The settled record's other claim read here is WHICH publication its report is
about: a settlement is never cleared, so an older commit's report reads as well
as the newest one's. It stays a claim, for the caller to re-read.

Preserving a description is not free, and the second reading here is what its
caller owes the work: a body left alone because a report lives in it can be one
that closes nothing when it merges and names no session -- a publication a human
can still fix before it is handed on, and a merged pull request that left its
issue open after.
"""
from __future__ import annotations

import re
from typing import Any

from orchestrator.github import pinned_state as _pinned_state
from orchestrator.github.pull_request_reports import ReportLocation
from orchestrator.workflow.engine import (
    report_delivery_state as _delivery_state,
    report_record_fields as _fields,
    report_record_state as _record_state,
    report_records as _records,
    report_replay_guards as _replay_guards,
    report_settlement_state as _settlement,
)

# Every spelling GitHub closes an issue on, as it documents them: one of the
# keywords, then the issue -- bare, or qualified `owner/repository#N`. Read
# here rather than compared against the line this workflow writes, because what
# is being asked is whether the MERGE will close the issue.
_CLOSES_THE_ISSUE = re.compile(
    r"\b(?:close[sd]?|fix(?:e[sd])?|resolve[sd]?)\b\s*:?\s*"
    r"(?P<repo>[\w.-]+/[\w.-]+)?#(?P<issue>[0-9]+)\b",
    re.IGNORECASE,
)

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

    Two things, and a pull request this stage may not edit has to carry
    both. The CLOSING reference is what makes merging the pull request end the
    issue, and GitHub honours it in the description and nowhere else -- no
    comment, however worded, closes anything. The ATTRIBUTION is what says
    whose implementation the branch is, and it is what every later reuse reads
    to tell this stage's own pull request from one somebody else opened.

    The reference is read for every spelling GitHub accepts rather than for
    the one this stage writes: a human who wrote `Fixes #12`, or `Fixes
    owner/repository#12` naming this repository, has done exactly what is being
    asked for. A reference qualified with another repository closes that
    repository's issue, not this one.

    A body nobody could read says nothing, which is the answer that holds the
    work back rather than letting it past -- what is being decided is whether
    a description may be left as it stands, and an unread one cannot show that
    it may.
    """
    body = getattr(pull_request, "body", None)
    if not isinstance(body, str):
        return False
    closing = _CLOSES_THE_ISSUE.finditer(body)
    return attribution in body and any(
        int(reference["issue"]) == issue_number
        and (reference["repo"] or repo_slug).lower() == repo_slug.lower()
        for reference in closing
    )


def costs_the_description(
    record: Any, pr_number: int, describes_the_issue: bool,
) -> bool:
    """Whether keeping this report would leave that publication unnamed.

    The two readings above asked as the one question their caller has. A
    report anywhere but this pull request's description costs it nothing, and
    a description that already closes the issue and names the session is one
    nothing was going to edit anyway -- so the collision is exactly a
    verification on a body that says neither.

    Whether it SAYS them is the caller's reading rather than one taken here,
    because the caller is the owner of what a description of its own would
    have said.
    """
    return (
        _names_the_description(getattr(record, "location", None), pr_number)
        and not describes_the_issue
    )


def _names_the_description(
    location: ReportLocation | None, pr_number: int,
) -> bool:
    """Whether one location is this pull request's description.

    A location with a comment id names a comment, and no absence of one is a
    description: the `null` a writer spells there is, which is exactly what
    the readers above hand back. A record with no location -- a publication
    whose comment does not exist yet -- names nothing.
    """
    if location is None or location.comment_id is not None:
        return False
    return location.pr_number == pr_number
