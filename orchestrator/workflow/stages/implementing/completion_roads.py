# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What a report-producing implementing road freezes before its launch, and the capture an attempt on it earns.

Three implementing roads end on a developer report: the first implementation
(`spawn`), a human reply resuming it (`drift_preflight`), and an operator's
`/orchestrator continue` retrying it (`continue_command`). Each freezes its
road before the launch (`CompletionRoad`) -- the route, the label its report
is recorded under, the requirements the run is handed, the input its prompt
delivers, and the checkout it runs in -- because none of that can be told
afterwards from what the run left: the thread may have moved on, and the
checkout is the run's own output.

The shared coordinator (`execution`) asks the road about every actual
attempt as it returns, behind the attempt's own accounting, quota retirement,
and live-pause reading (`captures`): an attempt the outcome owner and the
road's contract take is captured whole, as the issue's pending
`developer_completion`, before anything can discard it -- a live hold, a
lost write, a restart. That includes an ordinary unpaused return: the
disposition behind it hands the capture on to the report delivery
(`captured_report`), so the one copy of the report has one owner at a time.
A failed poisoned-session attempt or an incomplete Antigravity exit earns
none, and its accounting stands alone; an eligible continuation is captured
on the road it continues, with its own prompt and the command that ran it.
The capture moves nothing else, so a held return still writes nothing a
pause withholds, and a capture sent and never confirmed -- or answered over
a comment that moved -- holds the tick as a pause does, since the report
could otherwise be recorded twice.

What each road delivered is frozen as its settlement would apply it. The
first implementation quotes the whole thread, bounded, and records the
stretch it quoted (`thread_delivery`); where it answers an edit no session
saw, the settlement of that edit rides with it. A reply resume settles the
reply batch it was handed, and a retry consumes the bare commands it
answered -- and, handing no requirements, answers the baseline the issue
records, so an edit beside the command is never the report's revision
unseen. A documentation pass, a conflict resolution, and every other
resume freeze no road, so the coordinator captures nothing for them merely
because they run through it -- save the two a reviewer's change request
hands its developer through, the fixing stage's resume answering a pull
request's human feedback, every requirements-drift resume and the replies
that remain its continuation, the validating stage's resume asking for
the fresh report a head this orchestrator rewrote is owed, and the developer
revision a human's guidance buys under a late adjudication, whose callers
freeze a road of this same shape (`validating/fix_road`, `fixing/resume_road`,
`fixing/feedback_road`, `drift_road`, `validating/refresh_road`,
`decomposition/late_revision_road`) -- the refresh asking more of a return's
checkout than a report (`CompletionRoad.source`).

The two implementing routes are also the initial implementation request and
its ordinary continuations, so a road is what decides who is asked for a task
snapshot: the coordinator hands every attempt the prompt its road asks with
(`asked`) and every return to its road (`received`), and only the first
implementation's road and an implementing resume's append the request, record
anything, or take the attachment out of the reply the workflow reads
(`task_snapshots`). The observation is bound to what the attempt's
conversation was handed -- for a retry's fresh conversation, the read it was
re-grounded on, and for a later attempt resuming it, that same grounding
(`task_snapshot_grounding`) -- is analytics alone, raises nothing, and is read
by nothing here, so it changes no capture.
"""
from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass
from pathlib import Path

from github.Issue import Issue

from orchestrator.agents.models import AgentResult
from orchestrator.git.verification import probes as _probes
from orchestrator.github import client as _client, pinned_state as _pinned_state
from orchestrator.workflow.engine import (
    comments as _comments,
    completion_checkpoint as _checkpoint,
    completion_records as _records,
    completion_routes as _routes,
    content_hash as _content_hash,
    prompt_delivery as _prompt_delivery,
    task_snapshots as _task_snapshots,
    thread_delivery as _thread_delivery,
)
from orchestrator.workflow.stages.implementing import resume_batch as _resume_batch, session_read as _session_read
from orchestrator.workflow.state import WorkflowLabel

log = logging.getLogger("orchestrator.workflow")

_IMPLEMENTING = WorkflowLabel.IMPLEMENTING


@dataclass(frozen=True)
class RoadCheckout:
    """The checkout a road's run is launched in: its path, the branch it is on, and its head as the launch begins."""

    worktree: Path
    branch: str
    before_sha: str


@dataclass(frozen=True)
class Attempt:
    """One actual attempt the coordinator made: what it returned, and what it ran as.

    `command` is the full developer command it ran under, `prompt` the text
    it was handed, and `resumed` the conversation the coordinated run
    resumed -- None where it opened a fresh one, a continuation of that one
    included.
    """

    agent_result: AgentResult
    command: str
    prompt: str
    resumed: str | None


@dataclass(frozen=True)
class CompletionRoad:
    """What one report-producing road froze before its launch, and the checkout it launched in.

    `fresh_requirements` is what a FRESH session's prompt on this road is
    re-grounded with, where that is not the handoff's own: a retry hands a
    resumed conversation nothing, while a replacement session's preamble
    quotes the issue as it now reads. Only the task snapshot of an attempt
    that opened a fresh conversation is bound to it; the capture and the
    report keep the handoff's.
    """

    handoff: _records.CompletionHandoff
    checkout: RoadCheckout
    fresh_requirements: str | None = None

    def captures(
        self, gh: _client.GitHubClient, issue: Issue, state: _pinned_state.PinnedState, attempt: Attempt,
    ) -> bool:
        """Capture `attempt`'s return where it earns one; whether the tick is held for that capture.

        Asked after the attempt's accounting and live-pause reading, so the
        hold that reading decided stands whatever a later fetch sees. An
        attempt that earns no capture is left to its accounting and costs no
        read; one that does is captured at the head its road reads it as
        having left (`source`), beside the conversation the tick still pins as
        it returns -- what the launch itself left of the pin, which a recovery
        repeats. Held where the capture left the state withheld -- sent and
        never confirmed, or answered over a comment that moved -- and never
        otherwise: a capture refused for its report or for room records
        nothing, so the disposition's own recording answers that report as it
        always has.
        """
        handoff = self.handoff
        eligible = _routes.eligible_outcome(
            attempt.agent_result, handoff.route, handoff.origin, handed=bool(handoff.frozen),
        )
        if not isinstance(eligible, _routes.CapturedOutcome):
            return False
        source = self.source(attempt.agent_result)
        if source is None:
            return False
        completion = _checkpoint.captured(attempt.agent_result, handoff, _records.CompletionRun(
            command=attempt.command,
            prompt_revision=hashlib.sha256(attempt.prompt.encode()).hexdigest(),
            worktree=str(self.checkout.worktree),
            branch=self.checkout.branch,
            before_sha=self.checkout.before_sha,
            source_sha=source,
            resumed=attempt.resumed,
            pinned=_session_read._pinned_session_id(state),
        ))
        if isinstance(completion, _records.CompletionCapture):
            outcome = _checkpoint.capture(gh, issue, state, completion)
            log.info(
                "issue=#%d capturing the completion of agent invocation %d/%s on the %s road came to %s",
                issue.number, completion.invocation.ordinal, completion.invocation.nonce,
                handoff.route, outcome.status.value,
            )
        return state.withheld

    def asked(self, prompt: str) -> str:
        """The prompt an attempt on this road is handed: `prompt`, with the task snapshot request where it asks one.

        The first implementation's road and an implementing resume's ask it,
        every attempt on them alike (`task_snapshots`).
        """
        return _task_snapshots.asked(self.handoff, prompt)

    def received(self, attempt: Attempt, state: _pinned_state.PinnedState) -> None:
        """Receive an attempt's return on this road, where the road asks a task snapshot (`task_snapshots`).

        Asked of every attempt as it returns, ahead of anything that reads
        it: a genuine return's snapshot goes to analytics, bound to what the
        attempt's conversation was handed -- `fresh_requirements` where the
        coordinated run opened a fresh conversation and the road holds one,
        what a resumed conversation was grounded on where the pinned record
        still says (`task_snapshot_grounding`), the handoff's otherwise -- and
        the result's message is left as the workflow reads it, its attachment
        taken out. The recording raises nothing, and no disposition, capture,
        or accounting reads it back.
        """
        _task_snapshots.receive(self.handoff, attempt.agent_result, state, attempt.resumed, self.fresh_requirements)

    def source(self, agent_result: AgentResult) -> str | None:
        """The head `agent_result`'s report is about, read off the checkout as it returns; None where none qualifies.

        Every road here takes the head the run left, whatever it is, and
        leaves what that head means to its own disposition. A road whose
        contract asks more of the checkout a run returns over answers None
        where that was not met, so the return earns no capture
        (`validating/refresh_road`).
        """
        return _probes._head_sha(self.checkout.worktree)


def implementation_road(
    state: _pinned_state.PinnedState,
    delivered: _prompt_delivery.PromptDeliverySnapshot,
    checkout: RoadCheckout,
) -> CompletionRoad:
    """The first implementation's road, frozen over the thread `delivered` is the prompt's record of.

    Its delivered input is the stretch that prompt quoted, and -- where the
    requirements it was handed are not the baseline the issue records, an
    edit no session saw that this spawn answers -- the settlement of that
    edit (`drift._settle_edit_on_the_spawn`).
    """
    revision = delivered.requirements_revision or ""
    owed = revision != state.get(_prompt_delivery.PINNED_USER_CONTENT_HASH)
    return CompletionRoad(_records.CompletionHandoff(
        route=_routes.CompletionRoute.IMPLEMENTATION,
        origin=_IMPLEMENTING,
        requirements_revision=revision,
        watermarks=delivered.consumed_pairs(state) if owed else (),
        delivered=_thread_delivery.DeliveredThread.quoted(delivered).recorded(),
    ), checkout)


def reply_road(issue: Issue, batch: _resume_batch._ReplyBatch, checkout: RoadCheckout) -> CompletionRoad:
    """A human reply's resume, frozen over the one read its batch was cut from: it settles the batch it delivers."""
    return CompletionRoad(_records.CompletionHandoff(
        route=_routes.CompletionRoute.RESUME,
        origin=_IMPLEMENTING,
        requirements_revision=_requirements(issue, batch),
        watermarks=batch.delivery.consumed_pairs(batch.state),
    ), checkout)


def retry_road(issue: Issue, batch: _resume_batch._ReplyBatch, checkout: RoadCheckout) -> CompletionRoad:
    """An operator's `/orchestrator continue` retry, frozen over its batch: it consumes the commands it answered.

    A retry hands the developer no requirements: a resumed conversation reads
    its own transcript, and the baseline the issue records is what that
    conversation was last handed -- the very revision the run's report is
    stamped with where no capture holds it. So that baseline is the road's
    requirements, and an edit beside the command stays owed to the drift
    road rather than becoming the report's revision unseen; a held return
    beside such an edit is past what the issue now asks for when recovered.

    A retry that opens a fresh conversation -- no session left to resume,
    or a poisoned one replaced -- re-grounds it on the batch's own read of
    the issue, an edit beside the command included, so the task snapshot of
    such an attempt is bound to that read's fingerprint instead.
    """
    consumed = max(seen.id for seen in batch.comments)
    baseline = batch.state.get(_prompt_delivery.PINNED_USER_CONTENT_HASH)
    return CompletionRoad(_records.CompletionHandoff(
        route=_routes.CompletionRoute.RESUME,
        origin=_IMPLEMENTING,
        requirements_revision=baseline if isinstance(baseline, str) else "",
        watermarks=((_prompt_delivery.PINNED_LAST_ACTION_COMMENT_ID, consumed),),
    ), checkout, fresh_requirements=_requirements(issue, batch))


def _requirements(issue: Issue, batch: _resume_batch._ReplyBatch) -> str:
    """The requirements the batch's one read fingerprints, as a developer prompt's read of the whole thread would.

    The admission of the capture reads the thread whole and compares that
    fingerprint (`completion_admission`), so a reply landing after this read
    is an edit the capture is no longer the answer to.
    """
    ours = _comments._orchestrator_ids(batch.state)
    return _content_hash._compute_user_content_hash(issue, ours, comments=list(batch.read))
