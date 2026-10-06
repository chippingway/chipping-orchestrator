# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The one guarded commit a finished developer report settles in, and its measurement before the post.

A settlement is decided on the strength of what the tick read: which
transaction is outstanding, which report and which handoff the comment last
recorded, the publication the evidence proved, and the debt and park a settled
report retires. Written whole from the tick's state, it would put back every
field another road moved in the minutes the post or the re-read took -- an
evidence record, a verdict, a usage total, a watermark -- and nothing on the
comment would say so. So it lands through this domain's guarded commit
(`report_commits`) over the comment read afresh.

It owns exactly what a finished transaction writes, all of it in one commit:
the current report and the handoff, the drop of the pending record, the
watermarks the run consumed and the route bookkeeping its record froze, the
fixing mark that bookkeeping raises or retires, the debt, and the
undeliverable-report park where that park is this domain's. It is decided on
every report record, the handoff, the debt and the park it may retire, the work
no report describes, and the publication the evidence was proved against
(`ReportWrite.on_the_publication`): another road that moved any of them since
the tick read them refuses it, and so does one that moved a field it writes
some other way. Every other field is the fresh reading's -- another domain's
evidence or verdict, a usage total -- and a watermark, the usage totals and the
ledger of this orchestrator's comments keep both roads' moves.

The same commit is PREPARED before anything is posted (`prepares`), staged
with everything a settlement owes besides its two records, and held through
the guard to the measurement the record was accepted under
(`report_record_state.settled_payload`), asked of that very candidate: the two
records at their widest -- the digest and comment id nobody knows until the
post answers, and the longest label the issue can carry when the commit lands
-- the ledger entry the post adds, and the reviewer round and fixing hand-back
the settled report is followed by. A comment another road filled since the
tick read it, or one whose records moved, posts nothing. The commit asks every
prerequisite and owned field again over a reading taken behind the post and the
re-reads (`lands`), since those are long enough for any of it to move, and holds
its final candidate to the same room, its two records measured as they land: a
comment another road filled while the report was posted refuses it with the
pending record kept, rather than taking the room the reviewer round or the
fixing hand-back behind it needs.
"""
from __future__ import annotations

import logging
from functools import partial

from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.engine import (
    report_commits as _commits,
    report_consumed_values as _consumed,
    report_delivery as _delivery,
    report_record_state as _record_state,
    report_records as _records,
    report_settlement_state as _settlement,
)
from orchestrator.workflow.engine.pinned_commit_models import CommitOutcome, CommitStatus

log = logging.getLogger("orchestrator.workflow")

_PARK_REASON = "park_reason"

_AWAITING_HUMAN = "awaiting_human"

# What every settlement writes, beside the pairs its own record froze: the two
# settled records, the drop of the pending one, the fixing mark it replaces,
# the debt, and the undeliverable-report park where that park is this domain's.
_SETTLES = frozenset((
    _records.CURRENT_REPORT, _records.REPORT_HANDOFF, _records.PENDING_REPORT,
    _records.SETTLED_ROUND, _delivery.OWED_REPORT, _delivery.OWED_ROUND_RESET,
    _PARK_REASON, _AWAITING_HUMAN,
))

# What a settlement is decided on, beside the publication: every report record,
# the handoff a replay is recognized by, and the debt, the park and the work no
# report describes that decide what it retires.
_DECIDED_ON = _commits.REPORT_RECORDS | {
    _records.REPORT_HANDOFF, _delivery.OWED_REPORT, _delivery.OWED_ROUND_RESET,
    _delivery.UNREPORTED_WORK, _PARK_REASON,
}

# What the measurement answers for a settlement it cannot build, or one that
# leaves no room for the writes behind it.
_CROWDED = "the settlement and the writes behind it do not fit the comment"


def prepares(commit: _commits.ReportCommit, pending: _records.PendingReport) -> bool:
    """Whether `pending`'s settlement would land over the comment as it stands, posting nothing either way.

    Asked before the report is posted or verified, where a refusal still costs
    nothing: the report is unposted, the comment untouched, the transaction
    still owed. A refusal withholds the tick's state wherever the comment is
    not, or may not be, the one the tick read (`report_commits`); one for room
    alone over the comment the tick read leaves it to be written, since the
    roads behind a report still owed are what give that room back.
    """
    staged = commit.staging()
    _settles_what_was_owed(staged, pending)
    measured = _settling(pending).admitting(partial(_follows, pending))
    prepared = commit.prepares(staged, measured)
    if prepared.status is CommitStatus.PREPARED:
        return True
    if prepared.refusal in _commits._ROOM:
        log.error(
            "issue=#%d cannot settle developer report revision %d on PR #%d "
            "without writing a pinned comment past what GitHub accepts; "
            "posting nothing with the report still owed",
            commit.issue.number, pending.report_revision, pending.subject.pr_number,
        )
        return False
    log.warning(
        "issue=#%d cannot settle developer report revision %d on PR #%d over "
        "its pinned comment as it stands (%s); posting nothing with the report "
        "still owed", commit.issue.number, pending.report_revision,
        pending.subject.pr_number, prepared.refusal.value,
    )
    return False


def lands(
    commit: _commits.ReportCommit,
    pending: _records.PendingReport,
    handoff: _records.ReportHandoff,
    current: _records.CurrentReport,
) -> bool:
    """Settle `pending` as `current` and `handoff` in one guarded commit; True holds the tick.

    A settlement whose own records this build will not store is refused before
    anything is read or written, and holds the tick in front of a human. The
    commit is held to the room every write behind it needs, measured over the
    very candidate it sends with these two records as they land (`_follows`):
    the post is long enough for another road to fill the comment, and a
    settlement that still fits there but leaves the reviewer round or the
    fixing hand-back no room strands the round it settles. Refused for that,
    nothing is written and the pending record stays owed.

    False is a settlement that landed: only that is laid over the tick's state.
    A commit that did not land leaves the transaction owed and holds the tick
    wherever it withholds the tick's state -- the comment moved, or may have
    (`report_commits`); one refused for room over the comment the tick read
    stands down, for the routes behind to give the room back.
    """
    staged = commit.staging()
    stored = _settlement.record_current_report(staged, current) and (
        _settlement.record_handoff(staged, handoff)
    )
    if not stored:
        log.error(
            "issue=#%d published developer report revision %d on PR #%d and "
            "settles into a record this build will not store; holding the "
            "tick with the transaction still owed",
            commit.issue.number, pending.report_revision, pending.subject.pr_number,
        )
        return True
    _settles_what_was_owed(staged, pending)
    landed = commit.lands(staged, _settling(pending).admitting(
        partial(_follows, pending, current=current, handoff=handoff),
    ))
    if isinstance(landed, CommitOutcome) and landed.status is CommitStatus.COMMITTED:
        log.info(
            "issue=#%d settled developer report revision %d on PR #%d",
            commit.issue.number, pending.report_revision, pending.subject.pr_number,
        )
        return False
    # The check's own refusal comes back as it answered; the commit's as its outcome.
    refused = (landed.refusal or landed.status).value if isinstance(landed, CommitOutcome) else landed
    log.error(
        "issue=#%d published developer report revision %d on PR #%d and did "
        "not settle it over its pinned comment (%s); leaving it owed",
        commit.issue.number, pending.report_revision, pending.subject.pr_number,
        refused,
    )
    return commit.state.withheld


def _settling(pending: _records.PendingReport) -> _commits.ReportWrite:
    """The write that settles `pending`: what every settlement owns, and the pairs this record froze."""
    frozen = {field for field, _ in (*pending.watermarks, *pending.spends)}
    return _commits.ReportWrite(
        owned=_SETTLES | frozen, decided_on=_DECIDED_ON,
    ).on_the_publication()


def _follows(
    pending: _records.PendingReport,
    candidate: PinnedState,
    current: _records.CurrentReport | None = None,
    handoff: _records.ReportHandoff | None = None,
) -> str | None:
    """None where `candidate` holds the settlement and every write behind it; why not, otherwise.

    Measured by the one measurement the record was accepted under, over the
    candidate the commit would send, so what moves that measurement moves
    this: before the post with the settled records at their widest, and at the
    commit with `current` and `handoff` as they land.
    """
    settled = _record_state.settled_payload(candidate, pending, current, handoff)
    if settled is not None and _record_state.fits_the_comment(settled):
        return None
    return _CROWDED


def _settles_what_was_owed(
    state: PinnedState, pending: _records.PendingReport,
) -> None:
    """Apply everything a finished transaction owed besides its two records.

    The watermarks over the input the run consumed, the round or bookmarks its
    route closes, the drop of the record itself, and the debt that record left
    -- all of it on the staged copy, so the one commit that installs the
    settled records installs these too. Split off into a write of their own, a
    crash between the two leaves the report published and the round unspent,
    or the feedback it answered still reading as unread.

    Then the DEBT, and the park it was announced under. The debt first, since
    every reader behind it -- the review hold, the
    stale-approval hand-back, the resume that reads a reply as the report it
    asked for -- asks the flag rather than the record, and left standing it
    outlives the transaction that explains it. The fresh review budget an
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

    NOTHING is retired while this issue records work nobody has described. A
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
    # The settled-round mark is REPLACED by this write, never merely left:
    # retired first and re-raised below wherever this record's own spends carry
    # it. It says that the transaction the handoff beside it describes was a
    # fixing round's, and the two have to be one fact -- a mark an EARLIER
    # settlement raised somewhere that stage was not behind would otherwise
    # survive, and a later settlement of any route's would hand it a handoff
    # recorded under `workflow:fixing` to be correlated against. Read that way,
    # a manual relabel back onto `fixing` is bounced straight to the reviewer
    # with the feedback it was moved there to answer never scanned. Both
    # spellings cost the comment the same and no key is added where none was,
    # so the reservation that replays the record's own pairs still bounds this.
    if state.get(_records.SETTLED_ROUND) is not None:
        state.set(_records.SETTLED_ROUND, None)
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
