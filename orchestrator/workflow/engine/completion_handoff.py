# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Hand a captured completion's report to the existing delivery transaction, in one commit.

The report a capture holds has to end up owned by the transaction that
publishes reports, and it may have only one durable owner at a time: two full
copies are two reports the next tick could publish, and a comment carrying both
is one the report's own binding and settlement may then have no room for. So
the transfer is the delivery's own recording (`report_delivery.records_the_report`)
with the capture's handoff among what its road retires: the delivered report
is minted from the outcome the capture kept (`report_minting.minted_report`),
under the route, requirements, delivered input and round settlement its road
froze, and the very commit that records it rewrites the capture as HANDED_OFF
-- no report, the delivery's receipt and revision, and the branch and source
commit it is about. A write GitHub never confirmed leaves both or neither. It
is decided on the capture, the cycle, and every record the road's handoff was
frozen over, as well as on everything a recording is decided on and on what
the caller's road decides its own recording on -- the start of the launch a
change request owed, which its launch writes and so no handoff froze, and the
subject that request was reviewed over, which a recovery reads again before
finishing it -- and lands beside every field another road wrote; nothing the
caller staged rides it but what its road names to retire with the report.
What the caller's road is decided on is held to the caller's own reading of
the comment, as a recording with no capture is, before the transfer reads the
comment afresh: a record another road moved or damaged between the caller's
decision and that read refuses the transfer rather than landing beside it.

The transfer asks first over the comment read afresh and admitted
(`completion_commits`), so a transfer asked again finds the handoff it
already landed, a lost response included, and records nothing a second time:
it answers STANDING with every field a transfer writes (`TRANSFERRED`) laid
onto the caller as the comment carries it, so a caller that confirms a handoff
holds the delivery it confirmed.
A capture another invocation's, retired, absent or damaged is never
transferred, nor is one whose frozen handoff another road has moved since:
what that capture answered is no longer what the comment carries. A
verification this orchestrator cannot hold against its own repository earns no
delivered report, and is refused as unrecordable. That refusal, and every one
the recording gives behind it, is answered over the comment read again behind
that repository read, so a caller whose reading another road moved during it is
withheld. Every refusal of the
recording's own -- a report its reader refuses, a comment with no room for the
delivery, its binding, or its settlement, each measured over the very
candidate the commit sends with every terminator escaped -- is answered as it
was given, and nothing parks: what to do with a capture that cannot be handed
on is its recovery's to decide, and the capture still holds the report. Room
reserved when the capture was taken is no promise of room now: another road
may have filled the comment since, and the transfer is measured afresh.

A capture taken beside a handoff whose delivery still waits unbound carries
that handoff (`carried`): its transfer supersedes the delivery, so the later
capture may replace the handoff, and the delivery stays held to the commit
the carried one names until then.

The room that transfer will need is reserved when the capture is taken
(`admits_the_capture`), over the very comment the capture leaves: that
comment with the capture handed off and the delivered report recorded, at the
widest revision and receipt its minting could give it, measured by the
delivery's own writer -- which reserves the code-publication receipt, the
binding, and the settlement behind it. A capture whose transfer would not fit
is refused before it is taken, so no captured report is held where it could
never be handed on. Every one of those comments, the capture's own first, is
measured with each terminator escaped, never as the writer falls back to
rendering a payload past the ceiling unescaped: a record accepted only on
that rendering is one whose comment shows the rest of the record as issue
text.
"""
from __future__ import annotations

from dataclasses import dataclass, replace

from github.Issue import Issue

from orchestrator.agents.models import AgentInvocation
from orchestrator.github import client as _client, pinned_state as _pinned_state
from orchestrator.workflow.engine import (
    completion_commits as _commits,
    completion_records as _records,
    completion_spelling as _spelling,
    completion_state as _state,
    report_commits as _report_commits,
    report_delivery as _delivery,
    report_delivery_state as _delivery_state,
    report_minting as _minting,
)
from orchestrator.workflow.engine.completion_frozen import frozen_over_the_comment, moved_since
from orchestrator.workflow.engine.pinned_commit_models import CommitOutcome, CommitStatus
from orchestrator.workflow.engine.report_record_room import (
    CommentOverflow,
    LaterWrites,
    MeasuredWrite,
    RecordingRefusal,
)
from orchestrator.workflow.engine.report_record_state import carries_pending_report
from orchestrator.workflow.engine.report_record_values import MAX_RECORDED_NUMBER
from orchestrator.workflow.engine.report_records import (
    CURRENT_REPORT,
    REPORT_HANDOFF,
    DeliveredReport,
    HandedRun,
)

# Every field a transfer writes or the report it hands on lives in: the
# capture, every report record, and the park and debt flags a recording
# retires. A handoff confirmed by its read-back lays each of them back onto
# the caller as the comment carries it, whatever happened to them since.
TRANSFERRED = (
    _records.DEVELOPER_COMPLETION, *_delivery.REPORT_DEBT, _delivery.UNREPORTED_WORK, CURRENT_REPORT, REPORT_HANDOFF,
)


def transfer(
    gh: _client.GitHubClient,
    issue: Issue,
    state: _pinned_state.PinnedState,
    invocation: AgentInvocation,
    answering: HandedRun | None = None,
) -> _commits.CheckpointOutcome:
    """Record `invocation`'s captured report as the issue's delivered report, handing the capture off with it.

    `answering` is the caller's own run as its recording is handed one, where
    it names one: what its road retires with the report (`HandedRun.retires`)
    -- a change request it answers -- written in the same commit, and what
    that road's every write recording the report is decided on beside the
    capture (`HandedRun.decided_on`) -- the start of the launch that request
    owed, say -- as the caller last read the comment. The route, requirements,
    round settlement, and delivered input
    are the capture's own. LANDED and STANDING both leave the capture
    HANDED_OFF: the delivery owns the report, and what the transfer wrote,
    what it retires included, is laid onto `state` as the comment carries it.
    """
    commit = _commits.CompletionCommit(gh, issue, state, invocation)
    fresh = commit.fresh()
    if isinstance(fresh, _commits.CheckpointOutcome):
        return fresh
    captured = _state.read(fresh)
    if isinstance(captured, _records.CompletionCapture) and captured.invocation == invocation:
        return _Transfer(commit, captured, fresh).lands(answering or _handed_run(captured))
    if captured is None or captured.invocation != invocation:
        return commit.refused(_commits.CheckpointRefusal.ABSENT)
    if captured.stage is _records.CaptureStage.HANDED_OFF:
        retired = () if answering is None else dict(answering.retires)
        return commit.standing(fresh, captured.stage, (*TRANSFERRED, *retired))
    return commit.refused(_commits.CheckpointRefusal.RETIRED)


def confirmed(
    commit: _commits.CompletionCommit, fresh: _pinned_state.PinnedState, stage: _records.CaptureStage | None,
) -> _commits.CheckpointOutcome:
    """A standing answer for a capture `fresh` carries at `stage`, laid back onto the caller as the comment's.

    Past PENDING the report is the delivery's or the transaction's, so every
    field a transfer writes is laid back beside the capture: a caller that
    read the capture before its transfer then holds the report's owner, and
    its own whole-state write behind the answer keeps it rather than putting
    back a record without it.
    """
    if stage in {_records.CaptureStage.HANDED_OFF, _records.CaptureStage.RETIRED}:
        return commit.standing(fresh, stage, TRANSFERRED)
    return commit.standing(fresh, stage)


def carried(
    fresh: _pinned_state.PinnedState, captured: _records.CompletionCapture | _records.ResolvedCapture | None,
) -> _records.ResolvedCapture | None:
    """The handoff `captured` stands for, where a later record carries it over `fresh`; else None.

    That is the HANDED_OFF capture `captured` is, or the one a pending or
    retired capture already carries, still owed only to the delivery it
    became, standing unbound under its receipt beside no transaction at all:
    a later capture's own transfer supersedes that delivery, so the later
    capture may replace the record as long as it carries the handoff -- to
    hold the delivery to the commit it is about meanwhile -- and a capture
    invalidated before its transfer retires still carrying it
    (`completion_checkpoint.retire`). A handoff owed to a transaction, or
    beside a claim nobody can read, is carried by nothing.
    """
    handoff = getattr(captured, "standing_handoff", None)
    if not _state.source_owed(fresh, handoff) or carries_pending_report(fresh):
        return None
    delivered = _delivery_state.read_delivered_report(fresh)
    return handoff if delivered is not None and delivered.receipt == handoff.receipt else None


def admits_the_capture(
    candidate: _pinned_state.PinnedState, captured: _records.CompletionCapture, issue_number: int,
) -> RecordingRefusal | None:
    """Why the comment `candidate` is could not carry `captured`, or its transfer and what follows it; or None.

    `candidate` carries the pending capture, and is measured first, escaped
    in full. The transfer then replaces the capture with the handed-off one
    and records the delivery at the widest revision and receipt its minting
    could give it, which the delivery's own writer measures, escaped in full
    too, with the publication receipt, the binding, and the settlement each
    reserves.
    """
    rendered = len(_pinned_state.pinned_state_body(candidate.state_data, escaped_in_full=True))
    if rendered > _pinned_state.MAX_PINNED_BODY:
        return CommentOverflow(
            write=MeasuredWrite.RECORD, later=LaterWrites(), size=rendered, limit=_pinned_state.MAX_PINNED_BODY,
        )
    delivered = _minting.minted_report(
        issue_number, candidate, _minting.outcome_fields(captured.outcome), _handed_run(captured),
    )
    widest = replace(
        delivered,
        receipt=_minting.RECEIPT.format(issue=issue_number, revision=MAX_RECORDED_NUMBER),
        report_revision=MAX_RECORDED_NUMBER,
    )
    world = _pinned_state.PinnedState(state_data=dict(candidate.state_data))
    world.set(_records.DEVELOPER_COMPLETION, _spelling.spelled(_handed_off(captured, widest)))
    return _delivery_state.stage_delivered_report(world, widest, escaped_in_full=True)


@dataclass(frozen=True)
class _Transfer:
    """One pending capture, the comment it was read afresh from, and the commit it is bound by."""

    commit: _commits.CompletionCommit
    captured: _records.CompletionCapture
    fresh: _pinned_state.PinnedState

    def lands(self, answering: HandedRun) -> _commits.CheckpointOutcome:
        """Record the delivery the capture's outcome mints, the capture handed off in the same commit.

        Refused, with nothing sent, where a record the road's handoff was
        frozen over has moved since, where a record `answering` is decided on
        reads otherwise afresh than the caller last read it, and where the
        outcome earns no delivered report. `answering` is the caller's run,
        retiring and decided on what it names. The recording below is guarded
        over the fresh reading, so what the caller decided its run on is held
        to the caller's own reading first -- the comment as its state was last
        read or written (`completion_frozen.frozen_over_the_comment`), as a
        recording with no capture is guarded -- and a record another road moved
        between the caller's decision and this read refuses the transfer
        rather than landing beside it.
        """
        moved = moved_since(self.fresh, self.captured.handoff.frozen) or moved_since(
            self.fresh, frozen_over_the_comment(self.commit.state, answering.decided_on),
        )
        if moved:
            return self.commit.refused(_commits.CheckpointRefusal.HANDOFF_MOVED, moved)
        carried = _minting.carried_by_outcome(self.commit.gh, self.captured.outcome)
        if carried is None:
            return self.commit.refused(_commits.CheckpointRefusal.UNRECORDABLE, reread=True)
        delivered = _minting.minted_report(
            self.commit.issue.number, self.fresh, carried, _handed_run(self.captured),
        )
        return self.records(delivered, self.handed(delivered, answering))

    def handed(self, delivered: DeliveredReport, answering: HandedRun) -> HandedRun:
        """The run the recording is handed: the road's, retiring what `answering` does and the capture with the report.

        Decided on the capture, the cycle, every record the road's handoff was
        frozen over, and what `answering` is decided on.
        """
        handed_off = _spelling.spelled(_handed_off(self.captured, delivered))
        frozen = (field for field, _digest in self.captured.handoff.frozen)
        return replace(
            _handed_run(self.captured),
            retires=(*answering.retires, (_records.DEVELOPER_COMPLETION, handed_off)),
            decided_on=frozenset((*_commits.DECIDED_ON, *frozen, *answering.decided_on)),
        )

    def records(self, delivered: DeliveredReport, handed: HandedRun) -> _commits.CheckpointOutcome:
        """Land `delivered` through the delivery's own recording over the fresh comment, and say what it came to.

        Every refusal here is reached behind the repository read a
        verification's minting makes, and reads the comment again: the
        recording's own refusal of the record before its commit as much as
        the commit's.
        """
        # The recording lands over a copy of the fresh reading, so what it
        # moved is told from that reading when it is laid onto the caller.
        reading = _pinned_state.PinnedState(
            comment_id=self.fresh.comment_id, state_data=dict(self.fresh.state_data),
        )
        recording = _report_commits.ReportCommit(self.commit.gh, self.commit.issue, reading)
        refusal = _delivery.records_the_report(recording, delivered, handed, escaped_in_full=True)
        if refusal is None:
            return self.commit.took(self.fresh, recording.state, _records.CaptureStage.HANDED_OFF)
        if isinstance(refusal, CommitOutcome) and refusal.status is CommitStatus.UNCONFIRMED:
            return self.commit.unconfirmed()
        if recording.state.withheld:
            self.commit.state.withheld = True
        if isinstance(refusal, CommitOutcome):
            return self.commit.refused(refusal.refusal, refusal.fields, reread=True)
        return self.commit.refused(refusal, reread=True)


def _handed_run(captured: _records.CompletionCapture) -> HandedRun:
    """The run the capture's road froze, as the delivery's recording is handed one."""
    handoff = captured.handoff
    return HandedRun(
        route=handoff.origin,
        requirements_revision=handoff.requirements_revision,
        spends=handoff.spends,
        watermarks=handoff.watermarks,
    )


def _handed_off(captured: _records.CompletionCapture, delivered: DeliveredReport) -> _records.ResolvedCapture:
    """What `captured` is rewritten as once `delivered` owns its report."""
    return _records.ResolvedCapture(
        invocation=captured.invocation,
        stage=_records.CaptureStage.HANDED_OFF,
        receipt=delivered.receipt,
        report_revision=delivered.report_revision,
        branch=captured.run.branch,
        source_sha=captured.run.source_sha,
    )
