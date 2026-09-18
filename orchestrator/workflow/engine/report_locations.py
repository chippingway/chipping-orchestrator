# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Which places on a pull request this issue's reports claim as their own.

A report can live in a pull request's DESCRIPTION, and that is the one place
this workflow also writes for reasons that have nothing to do with reports: a
pull request opened elsewhere -- an operator's, or the `discussion` stage's plan
sitting on the very ref the dev commits went to -- gets the closing reference and
the attribution put above what it says, so it names the implementation now
pushed onto it. Those two meet on exactly one pull request: the one a developer
verified a report on, whose description says so and whose body that edit would
change.

Change it by a single character and the report is lost to this workflow, even
with every word kept: a verification records the digest of what it read, never
the words, so the location's content has moved, the verification refuses, the
transaction stays owed, and the work never leaves this stage.

So the claim is asked BEFORE any such edit, of every record that can hold
one: the report a run delivered, the transaction it was bound into, and the
report a pull request is already recorded as carrying. Any of the three naming
this pull request's description means the description is a report's, and the
caller leaves it exactly as it stands. A record nobody can read is asked too,
for whatever place it still names, because the edit is the one step here that
cannot be taken back.

Only the description. A report in a COMMENT is not something a body edit can
touch, and nothing here ever edits a comment.

The settled record makes one more claim this owner reads: WHICH publication
the report on a pull request is about. A settlement is never cleared, so an
older commit's report reads as well as the newest one's -- and the recovery
that republishes a commit because its report already went out has to be told
the difference, or a newer commit goes out under a report about an older one.
It is only a claim: whether the report still reads there is the recovery's to
re-read before it hands anything on.

Preserving one is not free, and the second reading here is what its caller owes
the work. A description is also where a pull request says which issue it closes
and whose implementation it carries, and the edit this withholds is what
usually puts both there -- so a body left alone because a report lives in it can
be one that closes nothing when it merges and names no session at all. Asked
before the work is handed on, that is a publication a human can still fix; asked
after, it is a merged pull request that left its issue open.
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
# keywords, then the issue this publication is for. Read here rather than
# compared against the line this workflow writes, because what is being asked
# is whether the MERGE will close the issue -- a human's own wording does.
_CLOSES_THE_ISSUE = re.compile(
    r"\b(?:close[sd]?|fix(?:e[sd])?|resolve[sd]?)\b\s*:?\s*#(?P<issue>[0-9]+)\b",
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

    All three records, because the claim outlives each of them separately. A
    delivered report holds one before its publication exists, the transaction
    bound from it holds the same one until it settles, and the settled record
    holds it for as long as that report is what the pull request carries --
    and an edit is just as destructive at any of those moments.

    A record nobody can read is asked for the place it still names, and it
    claims this description unless that place is readably somewhere else. The
    roads that act on such a record park it -- the binding a delivery, the
    reconciliation a transaction -- but both come AFTER the reuse this answers,
    so a damaged record read as no claim is a description destroyed before
    anything says the record was damaged, and nothing can put the text back.

    False for the ordinary issue carrying none of them, and for every report
    that lives in a comment: a body edit cannot reach one.
    """
    return any(
        _claims(state.get(key), reader(state), pr_number)
        for key, reader in _CLAIMING_RECORDS
    )


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
    source_sha: str,
) -> _records.CurrentReport | None:
    """The settled report about this commit on this pull request, or None.

    Both settled records, and they have to agree with each other: they are
    written in one write off one transaction, so a pair naming two different
    publications is one nothing here wrote. Then the subject has to name the
    very publication the caller holds -- this repository, this pull request,
    this commit. A report on the same pull request about an earlier commit
    describes work that has since moved on, and one about this commit on
    another pull request is somewhere a reviewer of this one will not look.

    What comes back is a CLAIM about the pull request, not a reading of it:
    the report it names may have been edited or deleted since it settled, so
    a caller about to hand the work on re-reads it there before trusting it.
    None wherever either record cannot be read, which is the answer that holds
    the work for a report rather than letting it past undescribed.
    """
    current = _settlement.read_current_report(state)
    handoff = _settlement.read_handoff(state)
    if current is None or handoff is None:
        return None
    if _replay_guards.companions_disagree(current, handoff):
        return None
    subject = current.subject
    settled = (subject.repo_slug, subject.pr_number, subject.source_sha)
    return current if settled == (repo_slug, pr_number, source_sha) else None


def describes_the_issue(
    pull_request: Any, issue_number: int, attribution: str,
) -> bool:
    """Whether a description still says what a publication needs it to say.

    Two things, and a pull request this stage may not edit has to carry
    both. The CLOSING reference is what makes merging the pull request end the
    issue, and GitHub honours it in the description and nowhere else -- no
    comment, however worded, closes anything. The ATTRIBUTION is what says
    whose implementation the branch is, and it is what every later reuse reads
    to tell this stage's own pull request from one somebody else opened.

    The reference is read for every spelling GitHub accepts rather than for
    the one this stage writes: a human who wrote `Fixes #12` has done exactly
    what is being asked for, and refusing it would ask them to write it again
    in this orchestrator's words.

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
        int(reference["issue"]) == issue_number for reference in closing
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
