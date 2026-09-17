# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Binding a delivered report to the publication it reached, and publishing it.

Reached once the push has landed and a pull request carries it, which is the
first moment the missing half of the record exists: a report is about one
repository, one pull request, one branch and one commit, and until the code is
out none of those is anything but a guess. So the binding happens here and
nowhere earlier -- and it happens before the report is posted, so a process that
dies between the two comes back to a transaction naming exactly what it was
doing rather than to a comment nothing recorded.

The two records are exchanged in ONE write. A delivery dropped without the
transaction beside it loses a finished run's report; a transaction recorded
beside the delivery it came from is a second report the next tick would publish.
And the write goes to GitHub before the post, because the whole value of the
record is that it outlives this process.

Publishing is asked of every tick that gets here, not only of the one that
bound the record. A publication whose post GitHub refused comes back with the
transaction already bound, and the only thing a retry has to establish is that
the transaction is about the publication in hand -- the same pull request, the
same branch, the same commit. So the two steps are separate: one binds what was
delivered, the other posts what this publication owes, and the ordinary tick
does both in a row.

What cannot be bound is never DISCARDED. The delivered record stands whatever
happens here, so the report a run wrote survives every refusal -- and because
it stands, the publication that reads the debt behind this owner withholds the
handoff, and the work waits rather than reaching review with no report.

Which refusal it was decides whether anybody is told. A comment too full is
given back by the routes a report still owed lets run, so it is reported at
ERROR and retried on the next tick, in the place that had just proved this
publication. Everything else -- a record nobody can read, a verification
asserting a report on another pull request -- is a report no later tick could
deliver either, so the issue is parked once with the record intact and a reply
resumes the developer that can write it again.

Publication itself is the engine's, unchanged: the post is scoped by the
transaction's receipt, so a retry finds what an earlier attempt landed instead
of repeating it, and only a reading that proves the report is there settles
anything. What this owner adds is that it is attempted on the very tick the code
went out, over a world the caller has just proved for itself -- the push it
made, the pull request it read, the receipt it recorded -- rather than a poll
later through the reconciliation that would otherwise have to prove all of it
again.

One term of that world is NOT the caller's to vouch for, and it is read here
before anything is posted: the requirements the run was handed. Every other term
is a fact this tick established, but the issue the caller holds was fetched
before its developer ran, and a human editing it during that run -- or during
the push and the pull request after it -- leaves a report answering
requirements the issue no longer has. So the issue is read AGAIN, and a report
whose requirements have moved is left owed rather than published and handed on:
the drift resume behind this owner is what answers an edit, and the report it
buys is the one that belongs on the pull request.

A publication that does not settle leaves the transaction owed, which is what
the caller reads to decide whether its work may be handed on. The reconciliation
ahead of the next handler finishes what this tick could not, and nothing is
published twice on the way: the post is scoped by the receipt this record
froze, and the pull request it names is the one the code already reached.
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
    report_publishing as _publishing,
    report_record_state as _record_state,
    report_records as _records,
)

log = logging.getLogger("orchestrator.workflow")

# Why a delivered record cannot be bound when nothing can read it, in the words
# the notice quotes. This owner's own judgement rather than the record owner's,
# since what refused is the read rather than the write.
_UNREADABLE_DELIVERY = "the record of what the run reported cannot be read"

_UNBINDABLE_PARK = (
    "{mentions} this issue's code is published on PR #{pr}, and the developer "
    "report recorded for it cannot be bound to that publication: {detail}. "
    "Nothing was discarded -- the report is still on the pinned comment under "
    "`developer_report_delivery`, and the branch and the pull request stand "
    "exactly as they are. The work is held here rather than handed to review, "
    "because a reviewer sent to this pull request would be reading an "
    "implementation whose report nothing on it carries. Reply and the "
    "orchestrator resumes the session, which can write the report again as "
    "the report text itself; clearing `developer_report_delivery` drops the "
    "report this workflow is holding for."
)


@dataclass(frozen=True)
class ReportPublication:
    """Where a delivered report's code landed, as the caller proved it.

    Everything the run could not supply, taken from the publication that has
    just happened rather than read again: the repository it went to, the pull
    request object the caller proved, the branch the push named, and the
    commit it sent. Re-derived instead of carried, each of them is a second
    reading of something that can move -- and a report bound to one world and
    published into another is the window the whole record exists to close.

    The pull request travels as the object rather than as its number, because
    the publication that follows the binding is made onto it: fetching one
    again would be a second moment, and a pull request proved open by the
    first can be closed by the time the second answers.
    """

    pull_request: Any
    repo_slug: str
    branch: str
    commit: str


def binds_and_publishes(
    gh: _client.GitHubClient,
    issue: Issue,
    state: _pinned_state.PinnedState,
    published: ReportPublication,
) -> None:
    """Bind the report this issue delivered to this publication, and publish it.

    Two steps rather than one, because the second is owed on ticks the first
    has nothing to do on. A publication that has already bound its report and
    failed to post it comes back here with no delivery and a transaction still
    outstanding -- and that transaction is about THIS publication, which is the
    one thing a retry needs to know before it may post.

    Nothing to do at all on every issue that delivered no report: a recovery, a
    run that came back with a question, a build older than the record.
    """
    if _delivery_state.carries_delivered_report(state):
        _binds_the_delivery(gh, issue, state, published)
    _publishes_what_is_owed(gh, issue, state, published)


def _binds_the_delivery(
    gh: _client.GitHubClient,
    issue: Issue,
    state: _pinned_state.PinnedState,
    published: ReportPublication,
) -> None:
    """Turn the report a run delivered into the transaction it goes out as.

    The write goes out before anything is posted, because the whole value of
    the record is that it outlives this process.

    Nothing is dropped on a refusal, whichever refusal it is: the delivered
    record is what the run left and the only copy of it there is. What differs
    is who is told. A comment that cannot carry the transaction is freed by
    the routes a report still owed lets run, so it is reported and left for
    the next tick. A record nobody can read, and a verification asserting a
    report on another pull request, are refusals no later tick would answer
    differently -- so the issue is parked once, with the record intact, for
    the human who can decide between a fresh report and none.
    """
    delivered = _delivery_state.read_delivered_report(state)
    if delivered is None:
        log.error(
            "issue=#%d records a developer report this build cannot read; "
            "holding its publication for a human", issue.number,
        )
        _parks_the_debt(gh, issue, state, published, _UNREADABLE_DELIVERY)
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

    Worded here rather than by the park's own owner because what a human needs
    to know is where the WORK stands, and on this road it is already out: the
    branch is on the remote and a pull request carries it, so the notice says
    so and says that nothing of the report was thrown away either.
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

    The record is read back off the pinned state rather than carried over from
    the binding, so what is published is what a later tick would recover --
    the same reading, off the same comment, that the reconciliation ahead of
    every handler takes. It is also what makes the retry work: a transaction
    bound by an earlier tick reads back here exactly as one bound a line ago.

    Held to this publication, and that is what keeps a retry honest. A
    transaction naming some other pull request, branch or commit is not this
    publication's to post -- what would prove it is the world the
    reconciliation reads for itself, and posting it here would put a report
    about work somewhere else onto the thread this tick happens to hold.

    Onto the pull request this tick already read. The evidence the
    reconciliation takes is about a world it has not seen: it re-reads the
    pull request, the checkout and the remote because everything it knows came
    off a record. Here the push has just landed, the pull request was read as
    part of making it, and the receipt naming both is on the comment -- so
    what that evidence would prove is what this tick has just done.

    The REQUIREMENTS are proved again before any of it, and they are the one
    term of this publication the caller cannot vouch for. It pushed the commit,
    read the pull request and wrote the receipt this tick, so each of those is
    a fact rather than a reading -- but the issue it holds was fetched before
    its developer ran, and an edit landing during that run, or during the push
    and the pull request after it, leaves this report answering requirements
    the issue no longer has. Published anyway it would be stamped with the
    revision its run was handed and handed straight to a reviewer as current.
    Left owed instead, the drift resume answers the edit and the report it buys
    is the one that belongs there -- and the handoff is withheld meanwhile,
    because the transaction is still outstanding.

    Whether the tick stops is not this owner's answer and is not asked for.
    What the caller decides on is the record: a transaction that settled is
    gone from the pinned state, and one that did not is still there for the
    handoff to refuse on and for the next tick to finish.
    """
    pending = _record_state.read_pending_report(state)
    if pending is None or not _names_this_publication(pending, published):
        return
    edited = _evidence.fresh_requirements_verdict(gh, issue, state, pending)
    if edited is not None:
        log.info(
            "issue=#%d is not publishing developer report revision %d onto "
            "PR #%s: %s; leaving it owed for the route that answers an edit",
            issue.number, pending.report_revision,
            _publication_number(published), edited.refusal,
        )
        return
    _publishing.finishes(gh, issue, state, pending, published.pull_request)


def _names_this_publication(
    pending: _records.PendingReport, published: ReportPublication,
) -> bool:
    """Whether an outstanding transaction is about the publication in hand.

    Every member of the subject the publication settles, because each of them
    is a way the two can be different work: another pull request is another
    thread, another branch is another ref, another commit is another state of
    the code the report describes, and another repository is somebody else's
    entirely.

    The requirements revision is deliberately not asked. It belongs to the run
    that wrote the report rather than to the publication, so a transaction
    bound on an earlier tick carries the revision that run was handed -- which
    is exactly what a later tick has no way to reconstruct and no business
    comparing.
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
