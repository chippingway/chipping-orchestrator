# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The two ways a proved transaction finishes, and the one write that settles it.

A PUBLISH posts the report it carries and is idempotent by construction: the
post is scoped by the transaction's receipt, so a retry finds whatever an
earlier attempt landed instead of repeating it -- including the attempt whose
response never came back, which GitHub may well have accepted. Only a reading
that says the report is PRESENT settles anything.

A VERIFY posts nothing. It re-reads the exact location the developer named and
requires the text still to hash to the revision it was verified at, which is
what a human editing that report between the run and this tick moves it off. The
author is asked as well: the location is somebody else's comment, and this
workflow trusts content by author everywhere else it reads a thread -- so a
report at a trusted location is verified and the identical text posted by
anybody else is not.

What a refusal short of PRESENT is OWED is the same split the evidence beside
this makes, and for the same reason. A read nobody could take stops the tick,
because nothing was learned and the next one is as likely to succeed. Every
other reading is a definite answer about content a human owns -- a report that
is gone, one edited off the revision it was verified at, one whose author this
deployment does not trust -- and each of those STANDS DOWN, so the routes
behind this guard run while the transaction stays owed. Held instead, an issue
whose report somebody edited would sit in front of every one of those routes
for the rest of its life. Either way nothing is published twice and no handoff
is written.

The settlement is ONE write. The current report, the handoff receipt, the
watermarks the run consumed, the bookkeeping its route owed, and the drop of the
pending record all land together, because every split between them is a window
a crash turns into a second report, a lost round, or feedback answered twice.

It is taken last, after the requirements are read once more off GitHub: a post
or a re-read is long enough for a human to edit the issue under it. Each
settlement records which road made it, which is what `report_settled_reading`
holds a later re-read of that report to.
"""
from __future__ import annotations

import logging
from typing import Any

from github.Issue import Issue

from orchestrator.github import (
    comments as _trust,
    developer_reports as _reports,
    labels as _labels,
    pull_request_reports as _pr_reports,
)
from orchestrator.github.client import GitHubClient
from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.engine import (
    comments as _comments,
    report_consumed_values as _consumed,
    report_delivery as _delivery,
    report_evidence as _evidence,
    report_record_state as _record_state,
    report_records as _records,
    report_settlement_state as _settlement,
)

log = logging.getLogger("orchestrator.workflow")

_PARK_REASON = "park_reason"

_AWAITING_HUMAN = "awaiting_human"


def finishes(
    gh: GitHubClient,
    issue: Issue,
    state: PinnedState,
    pending: _records.PendingReport,
    pull_request: Any,
) -> bool:
    """Finish a proved transaction the way its own mode says it finishes.

    One entry point for both roads, so the caller that proved the world hands
    it on without re-deciding which kind of transaction it holds: the mode is
    recorded, and reading it twice is how the two halves come to disagree about
    which report a record is for.

    One entry point is also where the ROOM is proved, once, ahead of either.
    The record was accepted against a comment that has moved on since: this
    guard stands a transaction down rather than holding it, so the routes
    behind it run, and a park, a retry notice, a ledger entry or an advanced
    watermark all write to this same comment. What the record reserved can be
    spent by work entitled to spend it, and the settlement is then past what
    GitHub will take.

    Asked here rather than at the write, because the two refusals cost
    different things. Here nothing has happened -- the report is unposted, the
    comment untouched, the transaction still owed. At the write the report is
    already on the pull request and the record still claims it, and every
    retry fails in the same place for the rest of the issue's life.

    Stood down rather than held, for the reason every structural refusal on
    this road stands down: what gives the room back is a route BEHIND this
    guard -- a park cleared, a frozen pair settled, a bookmark closed -- so
    holding would stop the only work that could clear the condition. Reported
    at ERROR, because a comment this full is an operator's to know about
    whether or not the routes below free it.
    """
    settled = _record_state.settled_payload(state, pending)
    if settled is None or not _record_state.fits_the_comment(settled):
        log.error(
            "issue=#%d cannot settle developer report revision %d on PR #%d "
            "without writing a pinned comment past what GitHub accepts; "
            "standing down with the report unpublished and still owed",
            issue.number, pending.report_revision, pending.subject.pr_number,
        )
        return False
    if pending.mode is _records.ReportMode.PUBLISH:
        return publishes_the_report(gh, issue, state, pending, pull_request)
    return verifies_the_report(gh, issue, state, pending)


def publishes_the_report(
    gh: GitHubClient,
    issue: Issue,
    state: PinnedState,
    pending: _records.PendingReport,
    pull_request: Any,
) -> bool:
    """Post the report this transaction carries, and settle it if it lands.

    True holds the tick. A post GitHub did not confirm is exactly that -- the
    comment may be there and only a later read can say -- so nothing is settled
    and nothing is posted twice: the next tick's reading is scoped by this
    receipt and finds the comment if it landed.

    A report the published format refuses is held and reported loudly rather
    than retried quietly. The record's own reader holds a text to the same
    bounds, so reaching this is a record that was written by something else.

    A confirmed post whose comment id nobody could read holds too. This road
    publishes a COMMENT, and a location with no comment id is the pull
    request's description -- a different place, holding somebody else's text.
    Recorded that way it would be a false "exact" location for every later
    reread, so the id is required and the next tick finds the landed comment by
    its receipt.

    Every OTHER reading stands down and lets the tick carry on. Only
    `UNCONFIRMED` is a reading nobody could take; a comment of ours under this
    receipt that no longer renders as the report is an edited one, which is a
    definite answer and a structural refusal -- so it defers to the routes
    behind this guard rather than stopping the tick in front of them forever.
    Nothing is posted a second time either way: the post is scoped by the
    receipt, and a reading that is not ABSENT never reaches one.
    """
    try:
        lookup = _comments._publish_developer_report(
            gh, pull_request, state, _reports.DeveloperReport(
                pr_number=pending.subject.pr_number,
                source_sha=pending.subject.source_sha,
                requirements_revision=pending.subject.requirements_revision,
                report_revision=pending.report_revision,
                receipt=pending.receipt,
                text=pending.report,
            ),
        )
    except _reports.ReportRefusedError:
        log.exception(
            "issue=#%d records a developer report this format will not "
            "publish; holding the tick", issue.number,
        )
        return True
    if lookup.presence is not _pr_reports.ReportPresence.PRESENT:
        return _refuses_the_reading(
            lookup.presence,
            "issue=#%d cannot settle developer report revision %d on PR #%d "
            "(%s)",
            issue.number, pending.report_revision,
            pending.subject.pr_number, lookup.presence.value,
        )
    posted = lookup.landed_id
    if posted is None:
        log.warning(
            "issue=#%d published developer report revision %d on PR #%d and "
            "could not read the comment it landed as; holding the tick",
            issue.number, pending.report_revision, pending.subject.pr_number,
        )
        return True
    return settles(gh, issue, state, pending, _records.CurrentReport(
        subject=pending.subject,
        report_revision=pending.report_revision,
        content_revision=_reports.content_digest(pending.report),
        location=_pr_reports.ReportLocation(
            pr_number=pending.subject.pr_number, comment_id=posted,
        ),
        mode=_records.ReportMode.PUBLISH,
    ))


def verifies_the_report(
    gh: GitHubClient,
    issue: Issue,
    state: PinnedState,
    pending: _records.PendingReport,
) -> bool:
    """Re-read the report this transaction asserts, and settle it if it holds.

    The developer's assertion proves nothing on its own, which is why this
    reads the location afresh rather than trusting the record: a report that is
    gone, that never hashed to the revision claimed, or that a human has edited
    since is not the report anybody verified. The next tick asks again either
    way, so a human repairing the report settles it without another developer
    run.

    Which of those STOPS the tick is the split that matters. A read nobody
    could take holds, because nothing was learned and the condition usually
    clears on its own. A report that is gone, one whose content has moved off
    the revision verified, and one at a location this deployment does not trust
    the author of are definite answers about a location a human owns -- so each
    of them stands down, and the routes behind this guard run while the
    transaction stays owed. Held instead, an issue whose report somebody edited
    would sit in front of every one of those routes for good.

    The AUTHOR is read under a boundary of its own for that same split. It is
    two lazy reads deep, so a read that failed is not an author this
    deployment refuses -- it is nobody saying, and it holds with the content
    read it stands beside rather than standing down on an answer nobody gave.
    """
    lookup = gh.reread_report_location(
        pending.location, content_sha256=pending.content_revision,
    )
    if lookup.presence is not _pr_reports.ReportPresence.PRESENT:
        return _refuses_the_reading(
            lookup.presence,
            "issue=#%d cannot verify the developer report at %s (%s)",
            issue.number, pending.location, lookup.presence.value,
        )
    trusted = _trusts_the_author(lookup.found)
    if trusted is None:
        log.warning(
            "issue=#%d could not read who wrote the developer report at %s; "
            "holding the tick", issue.number, pending.location,
        )
        return True
    if not trusted:
        log.info(
            "issue=#%d names a developer report at %s written by an author "
            "this deployment does not trust; standing down",
            issue.number, pending.location,
        )
        return False
    return settles(gh, issue, state, pending, _records.CurrentReport(
        subject=pending.subject,
        report_revision=pending.report_revision,
        content_revision=pending.content_revision,
        location=pending.location,
        mode=_records.ReportMode.VERIFY,
    ))


def _trusts_the_author(found: Any) -> bool | None:
    """Whether this deployment trusts who wrote the report, or None if unread.

    The author is two lazy reads deep -- the `user` off the comment, and the
    login off that -- so on a worker that has not completed the object either
    is a request that can fail. Left outside a boundary they leave this guard
    by an exception rather than by an answer, which is the one thing no
    reading on this road may do.

    None is that failure and it is NOT "untrusted". An author this deployment
    refuses is a definite answer about a location a human owns and stands
    down; an author nobody could read is a reading that did not happen, and
    the caller holds on it exactly as it holds on the content read beside it.
    """
    try:
        return _trust.is_trusted_author(getattr(found, "user", None))
    except Exception:
        log.exception("the author of a verified developer report would not read")
        return None


def _refuses_the_reading(
    presence: _pr_reports.ReportPresence, refusal: str, *details: Any,
) -> bool:
    """Say whether one reading short of PRESENT stops the tick, and log it.

    The whole of the difference is whether the reading HAPPENED. `UNCONFIRMED`
    is the one that did not -- a thread GitHub would not serve, a post whose
    response never arrived -- and it is warned about and held, since nothing
    was learned and the comment may well be there.

    Every other presence is a definite answer about content a human owns, and
    each of them stands down onto the routes behind this guard: the transaction
    stays owed, the tick carries on, and a repaired report settles on a later
    one. Logged at INFO for that reason -- it is ordinary progress refused, not
    a failure.
    """
    if presence is _pr_reports.ReportPresence.UNCONFIRMED:
        log.warning(f"{refusal}; holding the tick", *details)
        return True
    log.info(f"{refusal}; standing down", *details)
    return False


def _settles_what_was_owed(
    state: PinnedState, pending: _records.PendingReport,
) -> None:
    """Apply everything a finished transaction owed besides its two records.

    The watermarks over the input the run consumed, the round or bookmarks its
    route closes, the drop of the record itself, and the debt that record left
    -- all of it on the caller's composed copy, so the one write that installs
    the settled records installs these too. Split off into a write of their
    own, a crash between the two leaves the report published and the round
    unspent, or the feedback it answered still reading as unread.

    Then the DEBT, and the park it was announced under. The debt first, since
    every reader behind it -- the review hold, the stale-approval hand-back,
    the resume that reads a reply as the report it asked for -- asks the flag
    rather than the record, and left standing it outlives the transaction that
    explains it. The fresh review budget an
    `in_review` edit reset goes with it, for the same reason: it describes a
    publication this write has just ended.

    The PARK only where it is this owner's. A report nothing could deliver is
    parked under one reason, and a human answering it repairs the condition
    rather than replying -- an edited comment restored, a checkout cleaned --
    so the settlement that follows is the only thing that will ever say the
    wait is over. Any other reason belongs to whoever took it, and a human
    waiting on a question is still waiting.

    Each field is written only where it says something, because a null this
    comment did not already carry is bytes the record reserved nothing for:
    the ceiling is measured before a transaction is accepted, and a
    settlement that grows the comment is one the measurement did not model.

    NOTHING of the debt is retired while this issue records work nobody has
    described. A
    report recorded over the branch as it stands retires that flag as it is
    recorded, so a flag still standing here says the transaction just settled
    was written before those commits existed -- it is a true account of an
    earlier head, and the head the branch is on now is still owed one of its
    own. Retired anyway, the debt, the park asking for that report, and the
    budget its publication is owed would all come off together, and the next
    reply would publish those commits under a report that never saw them. What
    the transaction itself owed is applied either way: those pairs are this
    run's own bookkeeping, and an undescribed head beside them is a debt about
    a later commit rather than a reason to answer this one twice.
    """
    _consumed.advance_consumed(state, pending.watermarks)
    _consumed.close_bookkeeping(state, pending.spends)
    _record_state.clear_pending_report(state)
    if state.get(_delivery.UNREPORTED_WORK):
        return
    for owing in (_delivery.OWED_REPORT, _delivery.OWED_ROUND_RESET):
        if state.get(owing):
            state.set(owing, None)
    if state.get(_PARK_REASON) != _delivery.UNDELIVERABLE_REPORT:
        return
    state.set(_PARK_REASON, None)
    state.set(_AWAITING_HUMAN, False)


def settles(
    gh: GitHubClient,
    issue: Issue,
    state: PinnedState,
    pending: _records.PendingReport,
    current: _records.CurrentReport,
) -> bool:
    """Record one current report and one completed handoff, in one write.

    Everything the transaction owed lands here together: what the pull request
    now carries, the receipt saying THIS transaction finished, the watermarks
    over the input the run actually consumed, the round or bookmarks its route
    closes, and the drop of the record itself. Split across two writes, a crash
    between them leaves the report published and the transaction still
    outstanding -- which the next tick would settle again, spending a second
    round over feedback that was already answered.

    Composed whole before any of it is installed, because the atomicity has to
    hold against a refusal as well as against a crash. Both settled writers
    refuse what their own readers would not hand back, and a settlement
    half-applied is the loss the record exists to prevent arrived at from the
    other side: the pending record dropped beside a published report that
    nothing records the pull request as carrying. Built on a copy, a refusal
    leaves the caller's state exactly as it was found and nothing reaches
    GitHub at all.

    Reaching that refusal is a record this build did not write. `record_
    pending_report` measures this very write before it accepts a transaction,
    and every value here but the digest and the comment id is the record's own,
    already read back once -- so it is reported loudly and the tick is held in
    front of a human rather than retried quietly forever.

    False on a settlement that landed, because the transaction is finished and
    the tick belongs to whatever runs behind it.

    The requirements are proved again first, over an issue read afresh, since
    an edit can land inside the post or the re-read. Refused, nothing is
    written and the transaction stays owed, which withholds the handoff for the
    drift resume to answer; a re-read nobody could take holds the tick.

    The DEBT the record left goes with it, and the park it was announced
    under: this is the moment the pull request carries the report, so anything
    still saying one is owed is saying it about a report that is delivered.

    The handoff also records the workflow label the issue is carrying as this
    lands, and nothing reconstructs that afterwards. A route whose bookkeeping
    includes a hand-back its own stage has to make needs it: this write can be
    the reconciliation's, ahead of any handler, so the stage that road belongs
    to may not be the stage that is running.

    That label is read off the issue this owner reads AFRESH, never off the
    copy in hand: that one was fetched before the developer ran, so a human who
    has relabelled since is invisible there -- and a settlement stamped with a
    label the issue has left claims a stage was standing behind it, which the
    route that hands a round back on that claim then spends over feedback
    nobody read. It is the same fetch the requirements are proved over, because
    two fetches would be two answers to one question.

    It is read FAIL-CLOSED beyond that, which is the answer that costs least
    here: the labels are a lazy read and may fail like any request, and a
    settlement that raised out of that line would leave the report published
    and the transaction still outstanding. Every reader holds a missing label
    to the stricter answer, so the cost of the absence is a hand-back left for
    the route that can prove it rather than one taken on a guess.
    """
    fresh, edited = _evidence.fresh_issue_reading(gh, issue, state, pending)
    if edited is not None:
        log.info(
            "issue=#%d is not settling developer report revision %d on PR #%d: "
            "%s; leaving it owed",
            issue.number, pending.report_revision, pending.subject.pr_number,
            edited.refusal,
        )
        return edited.holds
    settled = PinnedState(state_data=dict(state.data))
    # Read off the issue this owner just re-read, never off the copy in hand:
    # that one was fetched before the developer ran, so a human who relabelled
    # since is invisible there. Fail-closed beyond that, which is the answer
    # that costs least: the labels are a lazy read and may fail like any
    # request, and a settlement that raised out of this line would leave the
    # report published and the transaction still outstanding. Readers hold a
    # missing label to the stricter answer, so the cost of the absence is a
    # hand-back left for the route that can prove it rather than one taken on
    # a guess.
    try:
        under = _labels.workflow_label(fresh)
    except Exception:
        log.exception(
            "issue=#%d could not read the workflow label its developer report "
            "settled under; recording the settlement without one", issue.number,
        )
        under = None
    stored = _settlement.record_current_report(settled, current) and (
        _settlement.record_handoff(settled, _records.ReportHandoff(
            receipt=pending.receipt,
            pr_number=pending.subject.pr_number,
            report_revision=pending.report_revision,
            source_sha=pending.subject.source_sha,
            settled_under=under,
        ))
    )
    if not stored:
        log.error(
            "issue=#%d published developer report revision %d on PR #%d and "
            "settles into a record this build will not store; holding the "
            "tick with the transaction still owed",
            issue.number, pending.report_revision, pending.subject.pr_number,
        )
        return True
    _settles_what_was_owed(settled, pending)
    state.data = settled.data
    gh.write_pinned_state(issue, state)
    log.info(
        "issue=#%d settled developer report revision %d on PR #%d",
        issue.number, pending.report_revision, pending.subject.pr_number,
    )
    return False
