# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The handoff an issue `ready` found unchanged takes to implementation, behind the checkpoint licensing it.

Three things ride it, and each has always been what this label writes: the
pickup comment an issue that has none is announced with, its id as the anchor
the validating handoff seeds its watermark past, and `last_action_comment_id`
ratcheted past every comment on the thread -- the consumption that keeps
decomposing-era feedback the implementer reads at spawn from being replayed as
fresh pull-request feedback later. Beside them goes the baseline the drift
check staged on a first encounter, or over the observed reading it confirmed,
so what the issue is handed on over is the reading it was compared on.

What is consumed is exactly what was compared. The ratchet is taken off one
reading of the thread (`ready_readings.thread`), read last of all ahead of the
checkpoint -- behind the pickup and every other request the handoff makes --
and the requirements are compared again on that same reading, with the title
and body of the issue fetched again behind it (`ready_readings.fresh`) rather
than the object the tick was dispatched with: a trusted comment or an edit
that landed while the pickup was announced is drift, handed back to the
decision for the reroute rather than consumed and implemented, and a comment
that lands after that reading is not consumed at all, so the implementing
stage meets it as an edit. Every other fetch ahead of a handoff effect is
compared the same way (`ready_readings.compared`): the one ahead of the
pickup, so a title or body edited while the decision read the thread is
rerouted with no pickup announced, and the one ahead of the relabel, so one
edited while the checkpoint landed is rerouted over the handoff that landed --
its pickup and consumed reading recorded -- rather than implemented. The
issue that last fetch answered is the one the relabel is made on.

The order is the crash contract: prepare, announce, read, land, relabel,
launch. The handoff is landed as one guarded commit over the reading the tick
last confirmed (`report_commits.ReportCommit`), owning those fields and
decided on the records the ready decision read -- the baseline, the observed
reading, the parent link, the reroute marker, and the pickup anchor -- so a
record a human moved since the claimed read refuses it with nothing put back.
Where a pickup is owed the commit is prepared first, with its anchor, the
watermark, and the notice's ledger entry reserved at their widest, so a
comment that would not take it -- unreadable, replaced, moved, or full -- is
announced nothing. An issue that pinned no comment at all has nothing a
guarded commit could land over, since the strict edit never creates one: its
preparation is a fresh reading that still finds no pin, and so is the reading
taken right before its first record is created by the whole-state writer
(`lands`), stamped version 1 -- a pin any other hand posted meanwhile, one
admission refuses above all, holds the handoff with nothing created beside it
-- and that record is read back as the issue's own, with the rest of the
checkpoint, before the relabel. The relabel and the implementing run go out
only behind a write GitHub confirmed, and only while the record, read back
behind it, still carries it in every field the decision rested on -- one a
human edited since, a child's baseline taken off above all, is left on `ready`
for the next tick to decide on, since the implementer's own reading would take
a missing baseline as its first one. Refused or never confirmed, nothing is
relabelled, consumed, or launched, the tick's state is withheld from every
whole-state write behind it, and the next tick reads what landed. The issue is
fetched again (`ready_readings.fresh`) ahead of the pickup, behind the reading
the checkpoint consumes, ahead of the relabel, and behind it ahead of the
launch, and a `paused` or `backlog` an operator applied meanwhile -- or a
relabel back to `workflow:blocked` -- stops the handoff there. Behind the
relabel the issue is the implementing stage's, so the fetch ahead of the launch
asks for a hold alone: that stage's own drift check reads an edit made from
there on.

A pickup is posted at most once. A handoff whose write landed with its answer
lost reads its own anchor back on the next tick and posts nothing; one whose
write never landed -- refused after the post, or a process that died between
the two -- left the comment on the thread with no anchor naming it, so the
decision's reading is asked for this orchestrator's own pickup sentence before
another is posted, and the one found is anchored instead.
"""
from __future__ import annotations

import logging

from github.Issue import Issue

from orchestrator.config import models as _config_models
from orchestrator.github.client import GitHubClient
from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.engine import (
    comments as _comments,
    drift as _drift,
    pinned_commit_models as _commit_models,
    record_admission as _record_admission,
    report_commits as _commits,
    report_record_values as _record_values,
    usage as _usage,
)
from orchestrator.workflow.stages.decomposition import ready_readings as _readings, state as _state
from orchestrator.workflow.stages.implementing import handler as _implementing
from orchestrator.workflow.state import WorkflowLabel

log = logging.getLogger("orchestrator.workflow")

_PICKUP_COMMENT_ID = "pickup_comment_id"

PICKUP_NOTICE = ":robot: orchestrator picking this up; starting implementation."

# What the ready decision reads before it hands an issue on or reroutes it: the
# baseline and the observed reading compared against, the parent link that
# says whether a missing one may stand in, and the reroute a crash may have
# left owed. Each has to read as the claimed reading did for either to land.
DECIDED_ON = frozenset((
    _drift._USER_CONTENT_HASH,
    _drift._OBSERVED_USER_CONTENT_HASH,
    _state._PARENT_NUMBER,
    _state._READY_REROUTE,
))

# The handoff: the baseline it lands, the pickup anchor and stamp, the ratchet,
# and the ledger entry its notice adds -- decided on the pickup anchor as well,
# which says whether a pickup is owed at all.
_HANDING_OFF = _commits.ReportWrite(
    owned=frozenset((
        _drift._USER_CONTENT_HASH,
        _PICKUP_COMMENT_ID,
        _state._CREATED_AT,
        _state._LAST_ACTION_COMMENT_ID,
        _comments._ORCH_COMMENT_IDS,
    )),
    decided_on=DECIDED_ON | {_PICKUP_COMMENT_ID},
)

# A record read with no field of it held to the tick's own: one asked only
# which comment it is.
_NO_FIELDS: frozenset = frozenset()

# What a guarded commit comes to that lets the handoff go on past it.
_GOES_ON = frozenset((_commit_models.CommitStatus.PREPARED, _commit_models.CommitStatus.COMMITTED))


def hands_off(
    gh: GitHubClient, spec: _config_models.RepoSpec, issue: Issue, state: PinnedState, comments: list,
) -> str | None:
    """Announce, consume, and land the handoff staged on `state`, then relabel and run the implementer.

    `state` is the claimed reading the ready decision found unchanged, with
    whatever baseline that decision staged on it, and `comments` the thread
    reading it compared. Answers the fingerprint of requirements that moved
    -- by the issue fetched ahead of the pickup, by the reading the checkpoint
    consumes and the issue fetched behind it, or by the issue fetched ahead of
    the relabel -- for the decision to reroute on, and None where the issue was
    handed on or the handoff stopped. The issue fetched last is the one
    relabelled and handed to the implementer.
    """
    commit = _commits.ReportCommit(gh, issue, state)
    if state.get(_PICKUP_COMMENT_ID) is None:
        current, moved = _picks_up(gh, issue, commit, comments)
        if current is None:
            return moved
    consumed = _readings.thread(gh, issue, state)
    if consumed is None:
        return None
    current, moved = _readings.compared(gh, issue, state, consumed)
    if current is None:
        return moved
    return _starts(gh, spec, issue, commit, consumed)


def lands(issue: Issue, commit: _commits.ReportCommit, write: _commits.ReportWrite, named: str) -> bool:
    """Land the state `commit` holds as `write`, the ready decision's `named` write; whether it stands confirmed.

    An issue that pinned no comment has nothing a guarded commit could land
    over, since the strict edit never creates one: its first record is the
    genuine new pin, created by the whole-state writer, which stamps it
    version 1 and raises over a record admission refuses rather than post one
    beside it. That writer creates a pin wherever its caller names none, so
    the record is read again right before it (`_pinned_as`): a pin another
    hand posted since holds the decision with nothing created beside it, and
    the next tick decides on that record.

    A write that landed is confirmed only once the issue's record, read back
    behind it, is the comment it wrote and still spells every field `write`
    is decided on as the tick holds it -- the baseline and the reroute marker
    among them. A first pin some other pin landing in between shadows is no
    record anything rests on, since every reader takes the pin ahead of it;
    a record a human edited since the write -- a child's baseline taken off
    above all -- is not the one the decision landed. Either withholds the
    tick's state, and nothing the write licenses is made: no relabel, notice,
    or launch. Anything but a write that landed stops the decision there too.
    """
    state = commit.state
    if state.comment_id is not None:
        if stops(issue, state, commit.lands(state, write), named):
            return False
    elif not _pinned_as(issue, commit, None):
        return False
    elif not _record_admission.written(commit.gh, issue, state):
        state.withheld = True
        log.warning("issue=#%d its ready %s pinned nothing; going no further", issue.number, named)
        return False
    return _pinned_as(issue, commit, state.comment_id, write.decided_on)


def stops(issue: Issue, state: PinnedState, outcome: _commit_models.CommitOutcome, write: str) -> bool:
    """Whether `outcome`, of the ready decision's `write`, stops it: anything but a candidate measured or landed.

    Logged, with the tick's state withheld from every whole-state write
    behind it: a refusal wrote nothing, and an answer that was lost may or
    may not have landed, which only a later reading can say.
    """
    if outcome.status in _GOES_ON:
        return False
    state.withheld = True
    log.warning(
        "issue=#%d its ready %s came back %s; going no further, with the pinned comment left as it stands "
        "for the next tick to read",
        issue.number, write, (outcome.refusal or outcome.status).value,
    )
    return True


def _picks_up(
    gh: GitHubClient, issue: Issue, commit: _commits.ReportCommit, comments: list,
) -> tuple[Issue | None, str | None]:
    """Anchor the pickup the handoff announces, found on `comments` or posted now; what `ready_readings.compared` says.

    The issue, where the handoff goes on; otherwise None, beside the
    fingerprint the requirements moved to where they moved. Posted only once
    the handoff it is announced for is prepared over the record as it stands
    (`_prepared`), and only over the issue fetched right ahead of it standing
    unheld and reading as the decision compared it: a title or body edited
    while the decision's thread was read, or while the preparation ran, is
    rerouted with no pickup announced. A pickup this orchestrator already
    posted is anchored rather than posted twice.
    """
    state = commit.state
    if not state.get(_state._CREATED_AT):
        state.set(_state._CREATED_AT, _usage._now_iso())
    found = _readings.found(gh, state, comments, PICKUP_NOTICE)
    compared = (issue, None)
    if found is None:
        reserved = commit.staging()
        reserved.set(_PICKUP_COMMENT_ID, _record_values.MAX_RECORDED_NUMBER)
        if not _prepared(issue, commit, reserved):
            return None, None
        compared = _readings.compared(gh, issue, state, comments)
        if compared[0] is None:
            return compared
        found = getattr(_comments._post_issue_comment(gh, issue, state, PICKUP_NOTICE), "id", None)
    else:
        _comments._track_orchestrator_comment(state, found)
    if found is not None:
        state.set(_PICKUP_COMMENT_ID, int(found))
    return compared


def _starts(
    gh: GitHubClient, spec: _config_models.RepoSpec, issue: Issue, commit: _commits.ReportCommit, consumed: list,
) -> str | None:
    """Consume `consumed`, land the handoff, then relabel and run the implementer, the issue fetched again at each.

    Answers the fingerprint the requirements moved to where the issue fetched
    ahead of the relabel reads changed, and None otherwise.
    `last_action_comment_id` moves past every comment on `consumed`, never
    below where it stands: nothing there is a reply to anything. That hands
    nobody the thread and records no delivery: only what the implementer's
    bounded prompt records as quoted (`thread_delivery`) counts as answered
    feedback. The relabel goes behind a write `lands` confirmed
    by reading the record back: a record a human edited since -- a child's
    baseline taken off it above all -- would otherwise reach the implementer,
    whose own reading takes a missing baseline as the first one, so the issue
    stays on `ready` for the next tick to decide on that record. The issue is
    fetched again last, right ahead of the relabel and with no request
    between them, and the relabel is made on that very object: a hold applied
    while the read-back ran stops it there, and no relabel made on labels
    read before it can write the hold away. That fetch is compared too
    (`ready_readings.compared`): a title or body edited while the checkpoint
    landed is handed back for the decision to reroute over the handoff that
    landed, with nothing relabelled to `implementing` or launched. The launch
    goes behind a hold read again after the relabel, on the issue that last
    reading fetched; from the relabel on, the issue is the implementing
    stage's, whose own drift check reads any edit made later.
    """
    state = commit.state
    latest = max((posted.id for posted in consumed), default=None)
    prior = state.get(_state._LAST_ACTION_COMMENT_ID)
    if isinstance(prior, int) and isinstance(latest, int):
        latest = max(latest, prior)
    if isinstance(latest, int):
        state.set(_state._LAST_ACTION_COMMENT_ID, latest)
    if not lands(issue, commit, _HANDING_OFF, "handoff"):
        return None
    current, moved = _readings.compared(gh, issue, state, consumed)
    if current is None:
        return moved
    gh.set_workflow_label(current, WorkflowLabel.IMPLEMENTING)
    current = _readings.fresh(gh, issue)
    if current is not None:
        _implementing._handle_implementing(gh, spec, current)
    return None


def _prepared(issue: Issue, commit: _commits.ReportCommit, reserved: PinnedState) -> bool:
    """Whether the handoff `reserved` stages would land over the record as it stands; nothing is written.

    Over a pinned comment, the guarded commit's own preparation. Over an
    issue that pinned none, a fresh reading that still finds none: a record
    another hand pinned since, and one admission refuses above all, is one
    the first pin may not be created beside, so the pickup it would announce
    is never posted -- and the tick's state is withheld from any whole-state
    write that would land on that record.
    """
    state = commit.state
    if state.comment_id is not None:
        return not stops(issue, state, commit.prepares(reserved, _HANDING_OFF, notice=True), "handoff's preparation")
    return _pinned_as(issue, commit, None)


def _pinned_as(
    issue: Issue, commit: _commits.ReportCommit, expected: int | None, fields: frozenset = _NO_FIELDS,
) -> bool:
    """Whether the issue's record, read now, is the comment `expected` names, spelling `fields` as the tick holds them.

    None names no pin at all. Asked of an issue that pinned nothing when its
    handler read it -- ahead of its pickup and of its first pin -- and of
    every checkpoint the decision landed, a first pin included, with the
    fields that write is decided on (`lands`). A pin another hand posted since
    -- one admission refuses above all -- is one the first may not be created
    beside, and the record every reader takes ahead of a first pin created
    after it; a record whose decided fields a human edited since the
    checkpoint is not the one the decision handed on. Anything else withholds
    the tick's state.
    """
    try:
        fresh = commit.gh.read_pinned_state(issue)
    except Exception:
        log.exception("issue=#%d could not read its pinned comment ahead of a ready effect", issue.number)
        fresh = None
    held = commit.state.data
    if fresh is not None and fresh.supported and fresh.comment_id == expected and all(
        _commit_models.spelled(fresh.data, field) == _commit_models.spelled(held, field) for field in fields
    ):
        return True
    commit.state.withheld = True
    if fresh is None or not _record_admission.refuses(issue, fresh, "going no further"):
        log.warning(
            "issue=#%d reads another pinned record than its ready decision expects; going no further", issue.number,
        )
    return False
