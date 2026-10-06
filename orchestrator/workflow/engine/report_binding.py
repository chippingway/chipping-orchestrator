# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Binding a delivered report to the publication it reached, and publishing it.

Reached once the push has landed and a pull request carries it -- the first
moment the report's subject exists: one repository, pull request, branch and
commit. The delivery is exchanged for the transaction in ONE write, made before
anything is posted, so a process dying in between comes back to a record naming
exactly what it was doing: a delivery dropped alone loses the report, and one
kept beside its transaction is a second report. That write is this domain's
guarded commit (`report_commits`): decided on the report records the tick read
and on the pull request, branch and code-publication receipt it records, owning
only the two it swaps, its transaction held to its room on the very
candidate the commit sends, and landing beside every field another road wrote
meanwhile. Nothing is posted on a binding that did not land, and a binding the
commit refused writes nothing behind it either: the tick's state is withheld
from every later whole-state write, so the stage that called in cannot put back
the records the refusal kept.

Binding and publishing are separate steps, both asked on every tick that gets
here: a publication whose post GitHub refused comes back with the transaction
already bound, and a retry only has to establish that it is about the
publication in hand -- the same pull request, branch and commit.

What cannot be bound is never DISCARDED: the delivery stands, so the debt keeps
the handoff withheld. A comment too full is reported at ERROR and retried, and
so is a comment that would not read, was replaced, or moved under the records
the binding was decided on. A binding sent and never confirmed is retried the
same way, nothing behind it written this tick: where it landed, the next tick
finds the transaction rather than the delivery and publishes it, binding
nothing again. A record nobody can read, a
verification on another pull request, and one on the very description this
publication needs are refusals no later tick answers differently, so the issue
parks once with the record intact. That last one is
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
    report_commits as _commits,
    report_delivery as _delivery,
    report_delivery_state as _delivery_state,
    report_evidence as _evidence,
    report_locations as _locations,
    report_publishing as _publishing,
    report_record_state as _record_state,
    report_records as _records,
)
from orchestrator.workflow.engine.pinned_commit_models import CommitOutcome, CommitRefusal, CommitStatus
from orchestrator.workflow.engine.report_record_room import CommentOverflow
from orchestrator.workflow.engine.report_replay_guards import refuses_the_record

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

# What a binding writes: the delivery it drops and the transaction it records
# in its place, decided on every report record -- the delivery it exchanges,
# the transaction it replaces, and the settled pair whose room it is measured
# beside -- and on the pinned fields the publication it is bound to is resolved
# from (`ReportWrite.on_the_publication`).
_BINDING = _commits.ReportWrite(
    owned=frozenset((_records.DELIVERED_REPORT, _records.PENDING_REPORT)),
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

    @property
    def number(self) -> int:
        """The pull request this publication reached, or 0 where none reads.

        Read through one property because the subject a binding names, its
        diagnostics, and the comparison that keeps a retry on its own
        publication all ask it -- and because the read is guarded: the number
        comes off an object GitHub handed back, and 0 is the answer every
        reader here refuses on rather than one anything is written under.
        """
        return getattr(self.pull_request, "number", 0) or 0

    def carries(self, pending: _records.PendingReport) -> bool:
        """Whether an outstanding transaction is about this publication.

        Every member of the subject the publication settles, each a way the
        two can be different work. Not the requirements revision, which
        belongs to the run that wrote the report rather than to the
        publication.
        """
        subject = pending.subject
        return (
            subject.pr_number == self.number
            and subject.repo_slug == self.repo_slug
            and subject.branch == self.branch
            and subject.source_sha == self.commit
        )


def binds_and_publishes(
    gh: _client.GitHubClient,
    issue: Issue,
    state: _pinned_state.PinnedState,
    published: ReportPublication,
) -> None:
    """Bind the report this issue delivered to this publication, and publish it.

    Two steps, because a publication that bound its report and failed to post
    it comes back with no delivery and a transaction still owed. Nothing to do
    at all on an issue that delivered no report -- and nothing is posted on one
    whose delivery this call did not bind, since the binding is what the
    publication is made on the strength of.
    """
    if _delivery_state.carries_delivered_report(state) and not binds_the_delivery(
        gh, issue, state, published,
    ):
        return
    _publishes_what_is_owed(gh, issue, state, published)


def binds_the_delivery(
    gh: _client.GitHubClient,
    issue: Issue,
    state: _pinned_state.PinnedState,
    published: ReportPublication,
) -> bool:
    """Turn the report a run delivered into the transaction it goes out as; True where it landed.

    Written before anything is posted, as this domain's guarded commit
    (`report_commits`): decided on the report records the tick read, the
    delivery exchanged among them, and on the pull request, branch and
    code-publication receipt the comment records -- the fields the publication
    in hand was resolved from, so one another road repointed since binds
    nothing -- and owning only the two records it swaps.
    Nothing is dropped on a refusal: a comment too full -- the tick's, or the
    one the fresh reading finds -- is reported and left for the next tick, and
    every other refusal of the record parks once with the record intact, for a
    human to answer. A comment that would not read, was replaced, or moved
    under those records is left to the next tick to bind afresh, parking
    nothing and writing nothing -- `state` is left as it was and withheld
    from every later whole-state write; so is a binding sent and never
    confirmed, which, where it landed, the next tick publishes without
    binding again. Whether this comment has room for the transaction is
    asked of the candidate the commit sends, never of `state`: room another
    road gave back since the tick read the comment is room. Every park here
    is decided on the publication as well, so a refusal judged against a
    publication another road has since repointed posts and parks nothing.

    Public for the caller that publishes through the reconciliation instead of
    through the post below: which commit it binds to is its to prove first,
    and False is a binding it may not publish on.
    """
    commit = _commits.ReportCommit(gh, issue, state)
    delivered = _delivery_state.read_delivered_report(state)
    if delivered is None:
        log.error(
            "issue=#%d records a developer report this build cannot read; "
            "holding its publication for a human", issue.number,
        )
        _parks_the_debt(commit, published, _UNREADABLE_DELIVERY)
        return False
    if _locations.costs_the_description(
        delivered, published.number, published.describes_the_issue,
    ):
        log.error(
            "issue=#%d verified its developer report on the description of PR "
            "#%s, which this implementation needs for its closing reference "
            "and attribution; holding for a human",
            issue.number, published.number,
        )
        _parks_the_debt(commit, published, _NEEDED_DESCRIPTION)
        return False
    # What no comment's room changes is asked here, of the delivery alone: that
    # it is the report the comment carries, bound to the requirements it froze,
    # into a transaction some comment could hold. The room of THIS comment is
    # asked of the candidate the commit sends -- space another road gave back
    # since the tick read it is room, and space it took is not.
    alone = _pinned_state.PinnedState(state_data={
        _records.DELIVERED_REPORT: state.get(_records.DELIVERED_REPORT),
    })
    refusal = _delivery_state.binds_delivered_report(
        alone, delivered, _records.ReportSubject(
            repo_slug=published.repo_slug,
            pr_number=published.number,
            branch=published.branch,
            source_sha=published.commit,
            requirements_revision=delivered.requirements_revision,
        ),
    ) or _lands_the_binding(commit, alone, delivered)
    if refusal == _delivery_state.CROWDED_COMMENT:
        log.error(
            "issue=#%d cannot bind developer report revision %d to PR #%s "
            "without writing a pinned comment past what GitHub accepts; "
            "leaving the report recorded and the work unhanded-on",
            issue.number, delivered.report_revision, published.number,
        )
    elif refusal:
        log.error(
            "issue=#%d cannot bind developer report revision %d to the pull "
            "request its code reached (%s); holding for a human",
            issue.number, delivered.report_revision, refusal,
        )
        _parks_the_debt(commit, published, refusal)
    return refusal == ""


def _lands_the_binding(
    commit: _commits.ReportCommit,
    bound: _pinned_state.PinnedState,
    delivered: _records.DeliveredReport,
) -> str | None:
    """Land over the tick's state the exchange `bound` made of the delivery alone; "" where it landed.

    The transaction is asked of the room of the very candidate the commit
    sends, by its own writer, so a comment another road filled since the tick
    read it is the crowded comment, and one it gave room back to is not; a
    candidate the comment cannot hold at all is crowded too. None is the
    commit's own answer -- logged here, and nothing for a human: the next tick
    binds over whatever the comment then carries. Any other answer is what
    stopped it.
    """
    pending = _record_state.read_pending_report(bound)
    staged = commit.staging()
    _delivery_state.clear_delivered_report(staged)
    staged.set(_records.PENDING_REPORT, bound.get(_records.PENDING_REPORT))
    landed = commit.lands(staged, _BINDING.on_the_publication().admitting(
        lambda fresh: _record_state.stage_pending_report(fresh, pending),
    ))
    if isinstance(landed, CommentOverflow) or (
        isinstance(landed, CommitOutcome) and landed.refusal is CommitRefusal.OVERFLOW
    ):
        return _delivery_state.CROWDED_COMMENT
    if not isinstance(landed, CommitOutcome):
        return _delivery_state.UNBINDABLE_RECORD
    if landed.status is CommitStatus.COMMITTED:
        return ""
    log.error(
        "issue=#%d did not land the binding of developer report revision %d "
        "(%s); posting nothing, for a later tick to settle from what the "
        "comment carries", commit.issue.number, delivered.report_revision,
        (landed.refusal or landed.status).value,
    )
    return None


def _parks_the_debt(
    commit: _commits.ReportCommit,
    published: ReportPublication,
    detail: str,
) -> None:
    """Hold a published implementation whose report cannot be delivered.

    Worded here because on this road the work is already out, and the notice
    says so, and that nothing of the report was thrown away either. Taken
    through the guarded commit, so the park lands beside whatever another road
    wrote since the tick read the comment -- and decided on the publication as
    well as on the report records, since every refusal it announces was judged
    against `published`: a comment another road has since pointed at another
    pull request or receipt gets no notice and no park.
    """
    _delivery.parks_the_debt(
        commit, commit.staging(), _UNBINDABLE_PARK.format(
            mentions=config.HITL_MENTIONS,
            pr=published.number,
            detail=detail,
        ),
        parking=_delivery.PARKING.on_the_publication(),
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
    That re-read is a request over the comment the binding just landed, so the
    comment is asked once more behind it (`ReportCommit.withholds`): one another
    road wrote meanwhile withholds the tick's state, and the caller's whole-state
    write behind this puts nothing back over that road's write.

    What the caller decides on is the record: a transaction that did not settle
    is still there for the handoff to refuse on and the next tick to finish.
    """
    pending = _record_state.read_pending_report(state)
    if pending is None or not published.carries(pending):
        return
    refused = refuses_the_record(state, pending)
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
            published.number, edited.refusal,
        )
        _commits.ReportCommit(gh, issue, state).withholds()
        return
    _publishing.finishes(gh, issue, state, pending, published.pull_request)
