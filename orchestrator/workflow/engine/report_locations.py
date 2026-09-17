# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Which places on a pull request this issue's reports claim as their own.

A report can live in a pull request's DESCRIPTION, and that is the one place
this workflow also writes for reasons that have nothing to do with reports: a
pull request opened elsewhere -- an operator's, or the `discussion` stage's plan
sitting on the very ref the dev commits went to -- is re-bodied so it names the
implementation now pushed onto it. Those two meet on exactly one pull request:
the one a developer verified a report on, whose description says so and whose
body that rewrite would replace.

Replace it and everything is lost at once. The report itself is gone, and with
it whatever a human wrote around it; the verification that follows reads a
location whose content has moved and refuses, so the transaction stays owed and
the work never leaves this stage; and nothing can put the text back, because the
only copy was the one on GitHub -- a verification records the digest of what it
read, never the words.

So the claim is asked BEFORE any such rewrite, of every record that can hold
one: the report a run delivered, the transaction it was bound into, and the
report a pull request is already recorded as carrying. Any of the three naming
this pull request's description means the description is a report's, and the
caller leaves it exactly as it stands.

Only the description. A report in a COMMENT is not something a body rewrite can
touch, and nothing here ever edits a comment.

Preserving one is not free, and the second reading here is what its caller owes
the work. A description is also where a pull request says which issue it closes
and whose implementation it carries, and the rewrite this preserves is what
usually puts both there -- so a body left alone because a report lives in it can
be one that closes nothing when it merges and names no session at all. Asked
before the work is handed on, that is a publication a human can still fix; asked
after, it is a merged pull request that left its issue open.
"""
from __future__ import annotations

import re
from typing import Any

from orchestrator.github import pinned_state as _pinned_state
from orchestrator.workflow.engine import (
    report_delivery_state as _delivery_state,
    report_record_state as _record_state,
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


def claims_the_description(
    state: _pinned_state.PinnedState, pr_number: int,
) -> bool:
    """Whether a report of this issue's is the description of `pr_number`.

    All three records, because the claim outlives each of them separately. A
    delivered report holds one before its publication exists, the transaction
    bound from it holds the same one until it settles, and the settled record
    holds it for as long as that report is what the pull request carries --
    and a rewrite is just as destructive at any of those moments.

    A record nobody can read claims nothing here, which is the same answer
    every reader in this domain gives it -- and the roads that act on such a
    record answer for it where they can say something about it: the binding
    parks a delivery it cannot read, and the reconciliation parks a
    transaction it cannot.

    False for the ordinary issue carrying none of them, and for every report
    that lives in a comment: a body rewrite cannot reach one.
    """
    claimed = (
        _delivery_state.read_delivered_report(state),
        _record_state.read_pending_report(state),
        _settlement.read_current_report(state),
    )
    return any(
        _is_the_description(record, pr_number)
        for record in claimed if record is not None
    )


def describes_the_issue(
    pull_request: Any, issue_number: int, attribution: str,
) -> bool:
    """Whether a description still says what a publication needs it to say.

    Two things, and a pull request this stage may not rewrite has to carry
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
    nothing was going to rewrite anyway -- so the collision is exactly a
    verification on a body that says neither.

    Whether it SAYS them is the caller's reading rather than one taken here,
    because the caller is the owner of what a description of its own would
    have said.
    """
    return _is_the_description(record, pr_number) and not describes_the_issue


def _is_the_description(record: Any, pr_number: int) -> bool:
    """Whether one record names this pull request's description.

    The location is read off whatever record is handed over, since the three
    spell it identically and only one of them makes it mandatory. A location
    with a comment id names a comment, and no absence of one is a description:
    the `null` a writer spells there is, which is exactly what the readers
    above hand back.
    """
    location = getattr(record, "location", None)
    if location is None or location.comment_id is not None:
        return False
    return location.pr_number == pr_number
