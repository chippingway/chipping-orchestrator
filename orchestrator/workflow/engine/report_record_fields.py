# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The two groups every report record shares, read and written one way.

A pending transaction and the current report it settles into both name the same
subject and both name a place on a pull request, so the spelling lives here
rather than in each round trip. Two owners spelling one group is how the pending
record comes to carry a field the settled one drops, and a reader of the second
would then answer for a record the first could still write.

Both are read fail-closed and all-or-nothing. A subject short of any member is
not a weaker binding, it is no binding: a completion proves the repository, the
pull request, the branch, the commit and the requirements revision TOGETHER, and
a group missing one of them would have that proof silently skipped. A
location is exact in both halves for the same reason -- a comment id alone names
a comment anywhere in the repository -- so a comment id recorded and unreadable
is damage rather than a quiet fallback to the description, which is a different
place holding somebody else's text. Its ABSENCE is damage on the same grounds:
the writer below puts the field on every location it records, so a location
without one was truncated, and only the `null` that writer spells for a
description is a description.
"""
from __future__ import annotations

from typing import Any

from orchestrator.github.pull_request_reports import ReportLocation
from orchestrator.workflow.engine import (
    report_record_values as _record_values,
    report_records as _records,
)
from orchestrator.workflow.late_split import formats as _formats, payloads as _payloads

_REPO = "repo"

_PR = "pr"

_BRANCH = "branch"

_SHA = "sha"

_REQUIREMENTS = "requirements"

_LOCATION_PR = "location_pr"

_LOCATION_COMMENT = "location_comment"


def subject_from(recorded: dict) -> _records.ReportSubject | None:
    """Return the subject one record names, or None unless it names a whole one.

    Every member or nothing. What the subject exists for is to be proved again
    on a tick that has no run behind it, and a proof that skipped whichever
    member failed to read would pass a transaction bound to a pull request
    nobody checked, on a branch nobody resolved, over a commit nobody named.
    """
    repo_slug = _record_values.as_slug(recorded.get(_REPO))
    branch = _record_values.as_branch(recorded.get(_BRANCH))
    pr_number = _record_values.as_recorded_number(recorded.get(_PR))
    source_sha = _payloads.as_hex(recorded.get(_SHA), _formats.COMMIT_LENGTHS)
    requirements = _payloads.as_hex(
        recorded.get(_REQUIREMENTS), _formats.DIGEST_LENGTHS,
    )
    if not repo_slug or not branch or not pr_number:
        return None
    if not source_sha or not requirements:
        return None
    return _records.ReportSubject(
        repo_slug=repo_slug,
        pr_number=pr_number,
        branch=branch,
        source_sha=source_sha,
        requirements_revision=requirements,
    )


def subject_fields(subject: _records.ReportSubject) -> dict[str, Any]:
    """Return the pinned fields one subject is recorded as."""
    return {
        _REPO: subject.repo_slug,
        _PR: subject.pr_number,
        _BRANCH: subject.branch,
        _SHA: subject.source_sha,
        _REQUIREMENTS: subject.requirements_revision,
    }


def location_from(recorded: dict) -> ReportLocation | None:
    """Return the exact place one record names, or None unless it names one.

    The `null` this writer spells is the description, which is a real location.
    Anything else in that field has to be an identity: recorded and unreadable,
    it is a record claiming one place and able to name another, and answering
    with the description would reread a body nobody verified.

    A field that is not there at all is damage rather than a description, for
    the reason the pair groups beside it are: the writer puts it on every
    location it records, so its absence is a truncation -- and read as the
    description, a verification would reread the pull request's own body
    instead of the comment whose content it hashed.
    """
    pr_number = _record_values.as_recorded_number(recorded.get(_LOCATION_PR))
    if not pr_number or _LOCATION_COMMENT not in recorded:
        return None
    if recorded[_LOCATION_COMMENT] is None:
        return ReportLocation(pr_number=pr_number)
    comment_id = _record_values.as_recorded_number(recorded[_LOCATION_COMMENT])
    if not comment_id:
        return None
    return ReportLocation(pr_number=pr_number, comment_id=comment_id)


def location_fields(location: ReportLocation) -> dict[str, Any]:
    """Return the pinned fields one location is recorded as."""
    return {
        _LOCATION_PR: location.pr_number,
        _LOCATION_COMMENT: location.comment_id,
    }
