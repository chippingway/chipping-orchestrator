# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Binding a delivered report to the publication it reached, and publishing it.

Reached once the push has landed and a pull request carries it -- the first
moment the report's subject exists: one repository, pull request, branch and
commit. The delivery is exchanged for the transaction in ONE write, made before
anything is posted, so a process dying in between comes back to a record naming
exactly what it was doing: a delivery dropped alone loses the report, and one
kept beside its transaction is a second report.

Binding and publishing are separate steps, both asked on every tick that gets
here: a publication whose post GitHub refused comes back with the transaction
already bound, and a retry only has to establish that it is about the
publication in hand -- the same pull request, branch and commit.

What cannot be bound is never DISCARDED: the delivery stands, so the debt keeps
the handoff withheld. A comment too full is reported at ERROR and retried. A
record nobody can read, a verification on another pull request, and one on the
very description this publication needs are refusals no later tick answers
differently, so the issue parks once with the record intact. That last one is
the collision: nothing here rewrites a description, a report's least of all,
and one left alone may close nothing -- so the work is held until a human names
it and the resumed session's report supersedes the one that lived there.

Publication itself is the engine's: scoped by the receipt so a retry finds what
landed, and settled only on a reading that proves the report is there. The one
term the caller cannot vouch for, the requirements, is read afresh first, and a
report whose requirements moved is left owed for the drift resume. A transaction
that does not settle stays owed, which is what the caller reads before handing
the work on; the reconciliation ahead of the next handler finishes it.

The implementing stage's publication is the caller of both steps, once its push
has reached a pull request. The requirements-drift disposition on an open pull
request binds alone and leaves the publishing to the reconciliation, whose
evidence proves the checkout, the remote and the receipt again -- the binding
there can follow a push some earlier tick made, not only its own.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from github.Issue import Issue

from orchestrator import config
from orchestrator.github import client as _client, pinned_state as _pinned_state
from orchestrator.workflow.engine import (
    report_delivery as _delivery,
    report_delivery_state as _delivery_state,
    report_evidence as _evidence,
    report_locations as _locations,
    report_publishing as _publishing,
    report_record_state as _record_state,
    report_records as _records,
    report_replay_guards as _replay,
)

log = logging.getLogger("orchestrator.workflow")

# Why a delivered record cannot be bound when nothing can read it, in the words
# the notice quotes. This owner's own judgement rather than the record owner's,
# since what refused is the read rather than the write.
_UNREADABLE_DELIVERY = "the record of what the run reported cannot be read"

# Why a report on a description cannot be delivered there, in the words the
# notice quotes.
_NEEDED_DESCRIPTION = (
    "it is the pull request's own description, which carries no reference "
    "closing this issue and no line naming the session that wrote the branch "
    "-- and this orchestrator rewrites no description, since GitHub offers no "
    "way to write one that cannot overwrite an edit saved a moment earlier; "
    "add those two lines to it yourself before you reply"
)

_UNBINDABLE_PARK = (
    "{mentions} this issue's code is published on PR #{pr}, and the developer "
    "report recorded for it cannot be bound to that publication: {detail}. "
    "Nothing was discarded -- the report is still on the pinned comment under "
    "`developer_report_delivery`, and the branch and the pull request stand "
    "exactly as they are. The work is held here rather than handed to review, "
    "because a reviewer sent to this pull request would be reading an "
    "implementation whose report nothing on it carries. Reply and the "
    "orchestrator resumes the session, which can write the report again as "
    "the report text itself, and that report is the one that gets published."
)


@dataclass(frozen=True)
class ReportPublication:
    """Where a delivered report's code landed, as the caller proved it.

    The repository, the pull request object, the branch and the commit, taken
    from the publication that has just happened rather than read again: a
    second reading of any of them can differ, and the pull request travels as
    the object the report is then posted onto. `describes_the_issue` is the
    caller's fresh reading of its DESCRIPTION -- whether it closes this issue
    and names the session -- which decides the one report this workflow
    cannot both keep and manage: one verified on that same body.
    """

    pull_request: Any
    repo_slug: str
    branch: str
    commit: str
    describes_the_issue: bool = True


def binds_and_publishes(
    gh: _client.GitHubClient,
    issue: Issue,
    state: _pinned_state.PinnedState,
    published: ReportPublication,
) -> None:
    """Bind the report this issue delivered to this publication, and publish it.

    Two steps, because a publication that bound its report and failed to post
    it comes back with no delivery and a transaction still owed. Nothing to do
    at all on an issue that delivered no report.
    """
    if _delivery_state.carries_delivered_report(state):
        binds_the_delivery(gh, issue, state, published)
    _publishes_what_is_owed(gh, issue, state, published)


def binds_the_delivery(
    gh: _client.GitHubClient,
    issue: Issue,
    state: _pinned_state.PinnedState,
    published: ReportPublication,
) -> None:
    """Turn the report a run delivered into the transaction it goes out as.

    Written before anything is posted. Nothing is dropped on a refusal: a
    comment too full is reported and left for the next tick, and every other
    refusal parks once with the record intact, for a human to answer.

    Public for the caller that publishes through the reconciliation instead of
    through the post below: which commit it binds to is its to prove first.
    """
    delivered = _delivery_state.read_delivered_report(state)
    if delivered is None:
        log.error(
            "issue=#%d records a developer report this build cannot read; "
            "holding its publication for a human", issue.number,
        )
        _parks_the_debt(gh, issue, state, published, _UNREADABLE_DELIVERY)
        return
    if _locations.costs_the_description(
        delivered, _publication_number(published), published.describes_the_issue,
    ):
        log.error(
            "issue=#%d verified its developer report on the description of PR "
            "#%s, which this implementation needs for its closing reference "
            "and attribution; holding for a human",
            issue.number, _publication_number(published),
        )
        _parks_the_debt(gh, issue, state, published, _NEEDED_DESCRIPTION)
        return
    refusal = _delivery_state.binds_delivered_report(
        state, delivered, _records.ReportSubject(
            repo_slug=published.repo_slug,
            pr_number=_publication_number(published),
            branch=published.branch,
            source_sha=published.commit,
            requirements_revision=delivered.requirements_revision,
        ),
    )
    if not refusal:
        gh.write_pinned_state(issue, state)
        return
    if refusal == _delivery_state.CROWDED_COMMENT:
        log.error(
            "issue=#%d cannot bind developer report revision %d to PR #%s "
            "without writing a pinned comment past what GitHub accepts; "
            "leaving the report recorded and the work unhanded-on",
            issue.number, delivered.report_revision,
            _publication_number(published),
        )
        return
    log.error(
        "issue=#%d cannot bind developer report revision %d to the pull "
        "request its code reached (%s); holding for a human",
        issue.number, delivered.report_revision, refusal,
    )
    _parks_the_debt(gh, issue, state, published, refusal)


def _parks_the_debt(
    gh: _client.GitHubClient,
    issue: Issue,
    state: _pinned_state.PinnedState,
    published: ReportPublication,
    detail: str,
) -> None:
    """Hold a published implementation whose report cannot be delivered.

    Worded here because on this road the work is already out, and the notice
    says so, and that nothing of the report was thrown away either.
    """
    _delivery.parks_an_undeliverable_report(
        gh, issue, state, _UNBINDABLE_PARK.format(
            mentions=config.HITL_MENTIONS,
            pr=_publication_number(published),
            detail=detail,
        ),
    )


def _publishes_what_is_owed(
    gh: _client.GitHubClient,
    issue: Issue,
    state: _pinned_state.PinnedState,
    published: ReportPublication,
) -> None:
    """Publish the transaction THIS publication owes, if it owes one.

    Read back off the pinned state, so a transaction bound by an earlier tick
    reads exactly as one bound a line ago, and held to this publication: one
    naming another pull request, branch or commit is the reconciliation's to
    prove. Posted onto the pull request this tick already read, since the push
    and the receipt are facts it just established.

    Two things are asked first. The settled pair beside it, as the
    reconciliation asks it: a settlement writes over that pair, so one nobody
    can read, one that contradicts itself, or a newer one is left owed for the
    reconciliation to park. And the REQUIREMENTS, over the issue read afresh --
    the one term the caller cannot vouch for, since an edit during the run or
    the push leaves the report answering requirements the issue no longer has;
    it is left owed for the drift resume, and a re-read that failed likewise.

    What the caller decides on is the record: a transaction that did not settle
    is still there for the handoff to refuse on and the next tick to finish.
    """
    pending = _record_state.read_pending_report(state)
    if pending is None or not _names_this_publication(pending, published):
        return
    refused = _replay.refuses_the_record(state, pending)
    if refused:
        log.error(
            "issue=#%d is not publishing developer report revision %d onto "
            "PR #%s: %s; leaving it owed for the reconciliation to hold",
            issue.number, pending.report_revision,
            pending.subject.pr_number, refused,
        )
        return
    edited = _evidence.fresh_requirements_verdict(gh, issue, state, pending)
    if edited is not None:
        log.info(
            "issue=#%d is not publishing developer report revision %d onto "
            "PR #%s: %s; leaving it owed",
            issue.number, pending.report_revision,
            _publication_number(published), edited.refusal,
        )
        return
    _publishing.finishes(gh, issue, state, pending, published.pull_request)


def _names_this_publication(
    pending: _records.PendingReport, published: ReportPublication,
) -> bool:
    """Whether an outstanding transaction is about the publication in hand.

    Every member of the subject the publication settles, each a way the two
    can be different work. Not the requirements revision, which belongs to the
    run that wrote the report rather than to the publication.
    """
    subject = pending.subject
    return (
        subject.pr_number == _publication_number(published)
        and subject.repo_slug == published.repo_slug
        and subject.branch == published.branch
        and subject.source_sha == published.commit
    )


def _publication_number(published: ReportPublication) -> int:
    """The pull request this publication reached, or 0 where none reads.

    Read through one helper because four callers ask it -- the subject a
    binding names, two diagnostics, and the comparison that keeps a retry on
    its own publication -- and because the read is guarded: the number comes
    off an object GitHub handed back, and 0 is the answer every reader here
    refuses on rather than one anything is written under.
    """
    return getattr(published.pull_request, "number", 0) or 0
