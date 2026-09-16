# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The two ways a proved transaction finishes, and the one write that settles it.

A PUBLISH posts the report it carries and is idempotent by construction: the
post is scoped by the transaction's receipt, so a retry finds whatever an
earlier attempt landed instead of repeating it -- including the attempt whose
response never came back, which GitHub may well have accepted. Only a reading
that says the report is PRESENT settles anything; everything else holds the tick
and is asked again, since a post nobody could confirm is not a report anybody
can prove is there.

A VERIFY posts nothing. It re-reads the exact location the developer named and
requires the text still to hash to the revision it was verified at, which is
what a human editing that report between the run and this tick moves it off. The
author is asked as well: the location is somebody else's comment, and this
workflow trusts content by author everywhere else it reads a thread -- so a
report at a trusted location is verified and the identical text posted by
anybody else is not.

The settlement is ONE write. The current report, the handoff receipt, the
watermarks the run consumed, the bookkeeping its route owed, and the drop of the
pending record all land together, because every split between them is a window
a crash turns into a second report, a lost round, or feedback answered twice.
"""
from __future__ import annotations

import logging
from typing import Any

from github.Issue import Issue

from orchestrator.github import (
    comments as _trust,
    developer_reports as _reports,
    pull_request_reports as _pr_reports,
)
from orchestrator.github.client import GitHubClient
from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.engine import (
    comments as _comments,
    report_consumed_values as _consumed,
    report_record_state as _record_state,
    report_records as _records,
    report_settlement_state as _settlement,
)

log = logging.getLogger("orchestrator.workflow")


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
        log.warning(
            "issue=#%d could not confirm developer report revision %d on "
            "PR #%d (%s); holding the tick",
            issue.number, pending.report_revision,
            pending.subject.pr_number, lookup.presence.value,
        )
        return True
    posted = getattr(lookup.found, "id", None)
    if not isinstance(posted, int) or isinstance(posted, bool):
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
    since is not the report anybody verified. Each of those holds the tick, so
    the next one asks again and a human repairing the report is enough to
    settle it without another developer run.
    """
    lookup = gh.reread_report_location(
        pending.location, content_sha256=pending.content_revision,
    )
    if lookup.presence is not _pr_reports.ReportPresence.PRESENT:
        log.warning(
            "issue=#%d could not verify the developer report at %s (%s); "
            "holding the tick",
            issue.number, pending.location, lookup.presence.value,
        )
        return True
    if not _trust.is_trusted_author(getattr(lookup.found, "user", None)):
        log.warning(
            "issue=#%d names a developer report at %s written by an author "
            "this deployment does not trust; holding the tick",
            issue.number, pending.location,
        )
        return True
    return settles(gh, issue, state, pending, _records.CurrentReport(
        subject=pending.subject,
        report_revision=pending.report_revision,
        content_revision=pending.content_revision,
        location=pending.location,
    ))


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
    """
    settled = PinnedState(state_data=dict(state.data))
    recorded = _settlement.record_current_report(settled, current)
    handed = _settlement.record_handoff(settled, _records.ReportHandoff(
        receipt=pending.receipt,
        pr_number=pending.subject.pr_number,
        report_revision=pending.report_revision,
        source_sha=pending.subject.source_sha,
    ))
    if not recorded or not handed:
        log.error(
            "issue=#%d published developer report revision %d on PR #%d and "
            "settles into a record this build will not store; holding the "
            "tick with the transaction still owed",
            issue.number, pending.report_revision, pending.subject.pr_number,
        )
        return True
    _consumed.advance_consumed(settled, pending.watermarks)
    _consumed.close_bookkeeping(settled, pending.spends)
    _record_state.clear_pending_report(settled)
    state.data = settled.data
    gh.write_pinned_state(issue, state)
    log.info(
        "issue=#%d settled developer report revision %d on PR #%d",
        issue.number, pending.report_revision, pending.subject.pr_number,
    )
    return False
