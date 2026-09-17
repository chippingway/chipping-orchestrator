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

What cannot be bound is DROPPED rather than carried. A record nobody can read,
or one the transaction's own writer refuses, describes a publication no later
tick could make either -- so holding the implementation behind it would strand
finished, pushed work on a text. The code is published, the log says what was
lost, and the issue moves on.

Publication itself is the engine's, unchanged: the post is scoped by the
transaction's receipt, so a retry finds what an earlier attempt landed instead
of repeating it, and only a reading that proves the report is there settles
anything. What this owner adds is that it is attempted on the very tick the code
went out, over a world the caller has just proved for itself -- the push it
made, the pull request it read, the receipt it recorded -- rather than a poll
later through the reconciliation that would otherwise have to prove all of it
again.

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

from orchestrator.github import client as _client, pinned_state as _pinned_state
from orchestrator.workflow.engine import (
    report_delivery_state as _delivery_state,
    report_publishing as _publishing,
    report_record_state as _record_state,
    report_records as _records,
)

log = logging.getLogger("orchestrator.workflow")


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

    A record nobody can read is dropped here rather than parked. What a park
    would be asking for is a report to publish, and this one is gone whatever
    a human does to the comment: the run that wrote it ended long before this
    tick. So is one the transaction's own writer refuses -- a text past what
    the comment can hold, a verification naming another pull request -- which
    is a publication no later tick could make either.

    The write goes out before anything is posted, because the whole value of
    the record is that it outlives this process.
    """
    delivered = _delivery_state.read_delivered_report(state)
    if delivered is None:
        log.error(
            "issue=#%d delivered a developer report this build cannot read; "
            "dropping it and publishing its code without one", issue.number,
        )
        _drops_the_delivery(gh, issue, state)
        return
    if not _delivery_state.binds_delivered_report(
        state, delivered, _records.ReportSubject(
            repo_slug=published.repo_slug,
            pr_number=getattr(published.pull_request, "number", 0) or 0,
            branch=published.branch,
            source_sha=published.commit,
            requirements_revision=delivered.requirements_revision,
        ),
    ):
        log.error(
            "issue=#%d cannot bind developer report revision %d to the pull "
            "request its code reached; dropping the report",
            issue.number, delivered.report_revision,
        )
        _drops_the_delivery(gh, issue, state)
        return
    gh.write_pinned_state(issue, state)


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

    Whether the tick stops is not this owner's answer and is not asked for.
    What the caller decides on is the record: a transaction that settled is
    gone from the pinned state, and one that did not is still there for the
    handoff to refuse on and for the next tick to finish.
    """
    pending = _record_state.read_pending_report(state)
    if pending is None or not _names_this_publication(pending, published):
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
        subject.pr_number == (getattr(published.pull_request, "number", 0) or 0)
        and subject.repo_slug == published.repo_slug
        and subject.branch == published.branch
        and subject.source_sha == published.commit
    )


def _drops_the_delivery(
    gh: _client.GitHubClient, issue: Issue, state: _pinned_state.PinnedState,
) -> None:
    """Give up on a delivered report, durably, so nothing waits on it again.

    Written rather than staged, because what it settles is the question the
    caller asks next: whether this issue still owes a report. Left in memory,
    a tick that died before the caller's own write would come back to the same
    unusable record and drop it again on every poll.
    """
    _delivery_state.clear_delivered_report(state)
    gh.write_pinned_state(issue, state)
