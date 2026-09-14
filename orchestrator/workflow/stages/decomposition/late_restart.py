# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The fresh attempt an operator authorizes once a cancelled cycle has ended.

A cancellation is irreversible within its cycle, so nothing gets that cycle
back and the only way into ordinary work is a new one. The authorization for
it is a GESTURE rather than a state: a settled cancellation hands its owner
`rejected`, an issue wearing that is inert everywhere, and taking it off is a
label write GitHub grants only to a repository's own people. So the handshake
is the operator reopening the issue and removing the label, and this owner is
what that removal turns into.

**What proves it is the pinned comment, and nothing on the issue's surface.**
An unlabeled issue is all the surface shows, and three different things wear
that same nothing: an operator who took `rejected` off, a human who stripped a
workflow label while the cleanup was still running, and an ending whose
terminal write GitHub refused. So the record has to say three things -- the
cycle was cancelled, it owes nothing, and its `rejected` is proved to be ON
the issue. The last is the proof half of the ending's two-phase terminal
record, and what it is not is an attempt: the decision to write the label goes
down before the write, and only a label that actually landed makes the removal
of one mean anything.

An unlabeled issue whose record says anything else is not this owner's
business, and it is not ordinary work either: a cancellation still owing the
remote a branch, a ref, a child receipt, or a held pull request belongs to the
cleanup until it does not, and one whose terminal is unproved is owed that
terminal first. Every one of those is refused by the guard beside this one
rather than let through, because the pickup path behind them greets an issue
as new and mints a SECOND pinned comment -- shadowed by the first from the
moment it is written, while the finished workflow in that first one goes on
deciding. A rejection from anywhere else in the workflow is refused there for
the same reason, and stays exactly as inert as it was.

"Owes nothing" is one question over two readings, asked of the cancellation
owner so this guard and that one cannot disagree. A pull request this
generation names and cannot prove it held is a record only a human can repair,
carried on no ledger and reported only by the ending; a child receipt and an
untypeable consumer ledger are obligations only the domain's settled-ledger
answer counts. Either reading alone would let a restart erase a hold, or reach
its retirement and be refused there with the marker already down.

**The gesture is the authorization, which is why the author allowlist is not
asked.** `ALLOWED_ISSUE_AUTHORS` guards the one path a stranger reaches on
their own -- an unlabeled issue picked up automatically -- and what it
protects is agent budget on a public repository. Nobody reaches THIS path by
filing an issue: it takes a pinned comment only this orchestrator writes, and
a label removal only a repository's own people may make. The fresh attempt is
therefore authorized by whoever made that gesture rather than by whoever filed
the issue, so an outsider's issue an operator has decided to restart is
restarted.

**It is a transaction over the one pinned comment, and the order is what makes
it safe to repeat.** The marker goes down first -- the cycle this restart
intends, the cycle it succeeds, and the label it means to apply -- because a
tick that died between the write and the effects has to resume THAT cycle
rather than mint a second one and say so twice. Then the two external effects:
the notice, suppressed by its own cycle-scoped marker on the thread, and the
target label, skipped only where this orchestrator is the one already wearing
it on the issue. Only once both have reconciled is the marker retired, and
retiring is what projects the fresh cycle.

**The label write is also the separator between cycles.** The ending beside
this one has one last-resort proof for a terminal no pass recorded -- the
newest workflow label THIS orchestrator applied -- and what makes that answer
belong to the cycle asking is that a restart always leaves a later application
of its own after the `rejected` it was authorized by. A target somebody else
put on the issue in the meantime is therefore not accepted as that
application: GitHub records no event for a label already present, so the name
comes off and goes back on rather than being written over.

Which label is applied is the CURRENT `DECOMPOSE` setting's answer at the
moment the marker is written -- `workflow:decomposing` while decomposition is
on, `workflow:implementing` when the switch is off -- and it is then the
marker's answer, not the switch's. A restart half-applied under one setting
and resumed under the other finishes the label it announced, because the
notice on the thread already told a human where the issue was going.

**The projection is a whitelist, not a list of deletions.** What survives is
what is true about the ISSUE rather than about the attempt: the pinned
comment's own identity, the bounded ids of the comments this orchestrator
posted, the cumulative usage the issue has already paid for, and the identity
the fresh cycle is joined to its predecessor by. Everything else goes -- every
session, the pull request and branch, the children and the dependency graph,
the snapshot, the whole previous generation and its cancellation, the parks,
the drift baseline, the counters, and the timestamps -- and the lineage and
generation go back to zero, because a restarted issue is a fresh attempt with
room to split rather than a cancelled one wearing a new number. Listing what
to drop instead would leave every key a later stage adds behind by default,
which is how a fresh cycle inherits a park nobody set or a branch nobody
pushed.

**A control label defers the whole of it.** `backlog` and `paused` park an
issue outside the state machine, and every step here is a write somebody
asked not to happen. Nothing is half-done meanwhile: the issue is held where
it is, and the restart is entered again on the tick the label comes off.
"""
from __future__ import annotations

import logging
from dataclasses import replace
from typing import Any

from github.Issue import Issue

from orchestrator.config import models as _config_models, settings as config
from orchestrator.github import (
    client as _client,
    comments as _github_comments,
    issues as _issues,
    labels as _labels,
    pinned_state as _pinned_state,
)
from orchestrator.workflow.engine import (
    comments as _comments,
    run_ledger as _run_ledger,
)
from orchestrator.workflow.late_split import (
    endings as _endings,
    events as _events,
    lineage as _lineage,
    restart as _restart,
    state as _late_state,
    telemetry as _telemetry,
)
from orchestrator.workflow.late_split.models import (
    LateFailure,
    LateGeneration,
    LatePhase,
)
from orchestrator.workflow.stages.decomposition import (
    late_cancellation as _late_cancellation,
)
from orchestrator.workflow.state import WorkflowLabel, stage_name

log = logging.getLogger("orchestrator.workflow")

# Stamped on the notice one restart leaves on the issue thread. Scoped to the
# cycle the restart MINTS, because that is the episode the notice announces: a
# second restart of the same issue is a different cycle and owes its own
# sentence, and an unscoped marker would read the first one's notice as the
# second's. An HTML comment, so it is invisible in the rendered thread.
_RESTART_MARKER = (
    "<!--orchestrator-late-restart:issue={issue}:cycle={cycle}-->"
)

_RESTART_NOTICE = (
    ":arrows_counterclockwise: **Restarting.** `rejected` was removed from "
    "this issue, which is what authorizes a fresh attempt after late-split "
    "cycle {predecessor} was cancelled. Cycle {cycle} starts from nothing on "
    "`{label}`.\n\nThe cancelled cycle carries over no session, pull request, "
    "branch, child issue, snapshot, or measurement -- what is kept is this "
    "thread and what the issue has already spent.\n\n{marker}"
)

# What survives the projection. Each is a fact about the ISSUE rather than
# about the attempt that just ended, and the group is a whitelist so a key a
# later stage adds is dropped by a restart rather than inherited by one.
#
# The pinned comment's own id is deliberately not here: it is not a field at
# all. The projection rewrites the payload of the comment it was read from, so
# the fresh cycle goes back into the comment every reader already knows.
_RETAINED_KEYS = (
    # The bounded id list every "is this comment ours" reading is taken
    # against. Comments are append-only, so the thread a restarted issue wakes
    # up on is the one the cancelled cycle left -- and a drift baseline or a
    # validating handoff that could no longer recognize the orchestrator's own
    # comments would read them as a human's.
    "orchestrator_comment_ids",
    # What the issue has already cost. These counters are cumulative per ISSUE
    # by construction -- the receipt a terminal posts reports what the whole
    # issue spent, not what one cycle did -- so zeroing them would under-report
    # every attempt after the first.
    "issue_agent_runs",
    "issue_total_tokens",
    "issue_total_cost_usd",
    "issue_cost_sources",
    # What the issue may spend and what it has spent of it, named by the
    # ledger owner rather than copied here, so a field that group grows is
    # kept by this projection without a second edit. A lifetime ceiling a
    # restart handed back would be no lifetime ceiling at all -- a cancelled
    # cycle would be the way to buy another one -- and the allowance travels
    # beside the count for the same reason the receipt's counters do: dropping
    # the ceiling an issue was granted while keeping its spend parks it on the
    # first run of the fresh cycle.
    *_run_ledger.PROJECTED_KEYS,
)


def _restarts(
    gh: _client.GitHubClient,
    spec: _config_models.RepoSpec,
    issue: Issue,
    label: str | None,
    state: _pinned_state.PinnedState,
) -> bool:
    """Whether this dispatch is one cancelled cycle's restart and nothing else.

    Asked by the dispatcher ahead of the refusal a cancelled cycle otherwise
    earns, because the two would answer the same issue differently in the
    window between the marker and the retirement. A restart applies its target
    label BEFORE it retires the marker, so a tick that crashed in between
    finds an issue wearing `workflow:decomposing` over a record that still
    says cancelled -- and the refusal beside this one would hand that issue
    `rejected` again, undoing the very authorization it is halfway through
    honoring.

    True means the issue was this owner's this tick and reaches no stage
    handler. The transaction below writes the label and the fresh cycle; the
    next tick dispatches the issue on them like any other.

    False is every issue that is not a restart, which is nearly all of them --
    the answer costs the record read the dispatcher had already taken and no
    request at all.
    """
    generation = _late_state.read_late_generation(state)
    if not _restartable(issue, state, label, generation):
        return False
    if _deferred(spec, issue):
        return True
    log.warning(
        "repo=%s issue=#%s carries an authorized restart of its cancelled "
        "cycle %d (%s was taken off); starting a fresh cycle rather than "
        "dispatching it",
        spec.slug, issue.number, generation.cycle_id, WorkflowLabel.REJECTED,
    )
    begun = _begun(gh, issue, state, _identified(issue, state, generation))
    if _applied(gh, issue, state, begun):
        _retired(gh, issue, state, begun)
    return True


def _identified(
    issue: Issue, state: _pinned_state.PinnedState, generation: LateGeneration,
) -> LateGeneration:
    """This cycle carrying the identity every record of it is correlated by.

    Two of the four identities a record is joined on are re-derived before
    anything is written, and neither is the cycle: that one is the record's
    own, it is what the marker is minted from, and it is the one thing a
    restart may not invent.

    The current issue is THIS issue, always. The pinned comment was read off
    it, so a field naming another one is damage rather than a reading about
    somebody else's issue -- and honoring it would carry that number into the
    projection and into both sinks, filing a fresh cycle and its telemetry
    under an issue this pass is not about.

    The root is kept where the record is this issue's own and re-derived
    otherwise, which is both repairs at once. A record that could not name its
    own issue is one whose remaining lineage claims nothing vouches for; a
    root of no issue at all is a record the telemetry contract refuses
    outright, so the restart would run to completion and say nothing about
    itself on either sink. What it is re-derived from is the ancestry beside
    it -- a fact about the split this issue was CUT from rather than about the
    cycle it ran -- and an owner with no ancestry is the root of its own
    lineage. That is the same chain a cancellation rebuilds a dropped identity
    from.
    """
    ancestry = _lineage.read_late_ancestry(state)
    own_root = (
        generation.root_issue
        if generation.current_issue == issue.number
        else 0
    )
    return replace(
        generation,
        current_issue=issue.number,
        root_issue=own_root or ancestry.root_issue or issue.number,
    )


def _restartable(
    issue: Issue,
    state: _pinned_state.PinnedState,
    label: str | None,
    generation: LateGeneration,
) -> bool:
    """Whether this issue's own record authorizes a fresh cycle right now.

    The cycle has to exist and to be one a close already ended, and then three
    things have to be true of it.

    It has to owe nothing, which is `_unsettled` on the cancellation owner --
    one question over two readings, because neither contains the other. What
    the ending lists counts a pull request this generation names and cannot
    show it ever held, an obligation no ledger entry carries and only a
    human can repair; projecting the fresh cycle over one would delete the
    last thing on the issue pointing at a pull request this orchestrator left
    marked and open. What the domain's settled-ledger answer adds is a child
    receipt and a consumer ledger this binary could not type, and a restart
    that reached its retirement over one of those would be refused there with
    the marker already down and the label already applied. Asking the
    cancellation owner rather than restating its rule is what keeps the two
    guards exactly complementary: the tick that stops here is the tick that
    guard runs its ending on, and no state falls between them.

    The terminal has to be PROVED applied, which the record says and the label
    cannot. `rejected` is what an operator removes to authorize a fresh cycle,
    and an issue they took it off is indistinguishable on its surface from one
    whose workflow label a human stripped while the cleanup was still running,
    and from one whose terminal write GitHub refused. None of those three got
    `rejected`, and restarting any of them would start a cycle on a gesture
    nobody made. So it is the PROOF half of the terminal record that answers
    here -- the receipt a pass writes for a `rejected` it can see on the issue
    -- and not the decision half, which is only an attempt.

    And the gesture itself is read off the issue: an OPEN issue wearing no
    workflow label at all is one an operator reopened and took that terminal
    off, which is the only way a stamped cycle loses it. A closed one is the
    cleanup sweep's, whatever its record says.

    A marker already standing answers the gesture and the stamp for itself,
    whatever label the issue now wears. It is a record only this owner writes,
    and only after both were proved, so an issue carrying one is a restart
    this orchestrator began and owes the rest of.
    """
    if _issues.issue_is_closed(issue):
        return False
    if not generation.is_present or not generation.cancelled:
        return False
    if _late_cancellation._unsettled(generation):
        return False
    if generation.restart_pending:
        return True
    proved = _endings.terminal_confirmed(state, generation.cycle_id)
    return label is None and proved


def _deferred(spec: _config_models.RepoSpec, issue: Issue) -> bool:
    """Whether a control label says now is not the time to restart.

    `backlog` and `paused` park an issue outside the state machine, and every
    step of a restart is a write: a comment, a label, and a pinned comment
    projected onto a cycle that will then spawn an agent. Nothing here has to
    happen before the label comes off -- the authorization is durable on the
    issue's own surface, since the operator's removal of `rejected` is not
    something a later tick can lose.
    """
    skip_label = _labels.hard_skip_control_label(issue)
    if skip_label is None:
        return False
    log.info(
        "repo=%s issue=#%s has %r over an authorized restart; the fresh "
        "cycle waits for the label to come off",
        spec.slug, issue.number, skip_label,
    )
    return True


def _begun(
    gh: _client.GitHubClient,
    issue: Issue,
    state: _pinned_state.PinnedState,
    generation: LateGeneration,
) -> LateGeneration:
    """Make the cycle this restart intends durable before anything acts on it.

    Create-or-keep, and the keeping is the whole point: a marker this owner
    could have written already IS this restart, so a tick re-entering after a
    crash resumes that cycle rather than minting a second one and posting a
    second notice. A record whose marker could not have been written here --
    a pending cycle no audit line was ever issued for, a predecessor naming
    ancestry nothing wrote -- is re-minted from the cycle in hand, which costs
    one notice rather than a fabricated lineage.

    The boundary moves with it. `restarting` is what says this record is
    mid-transaction rather than merely cancelled, and it is safe to write over
    the cancellation's own `cancelling` precisely because nothing is owed: the
    boundary a reclamation reads is kept beside the stamp, and a restart is
    reachable only from a cycle with nothing left to reclaim.

    The record of it rides the write that made the marker true rather than
    every visit that reads it back, so a restart held by a label GitHub keeps
    refusing is one `late_restart` rather than one per tick.
    """
    begun = _restart.begin_restart(
        generation, target=str(_selected_target()),
    )
    if begun == generation:
        return generation
    begun = begun.at_phase(LatePhase.RESTARTING)
    _persisted(gh, issue, state, begun)
    _telemetry.emit_late_event(
        gh,
        _events.LateEvent(
            family=_events.LateEventFamily.RESTART,
            restart_step=_events.LateRestartStep.PENDING,
        ),
        begun,
        stage=stage_name(gh.workflow_label(issue)),
    )
    return begun


def _selected_target() -> WorkflowLabel:
    """The state the current `DECOMPOSE` setting puts a restarted issue in.

    The same choice an unlabeled issue's first pickup makes, and made here
    rather than by reaching that path: pickup mints a pinned comment of its
    own, greets the issue as new, and asks the author allowlist -- none of
    which is what a restart is.
    """
    if config.DECOMPOSE:
        return WorkflowLabel.DECOMPOSING
    return WorkflowLabel.IMPLEMENTING


def _applied(
    gh: _client.GitHubClient,
    issue: Issue,
    state: _pinned_state.PinnedState,
    generation: LateGeneration,
) -> bool:
    """Carry out both external halves of the restart, or say one did not.

    The notice comes before the label so a human watching the issue reads why
    it moved before they see it move, and both are idempotent, so the pass a
    failure keeps bringing back costs only the half that is actually still
    owed.

    A refusal from either is reported and returned rather than raised: the
    marker is durable by now, so the next visit resumes exactly here, and the
    only thing missing is an effect GitHub declined. Retiring over it would
    project the fresh cycle onto an issue that was never told and never
    relabelled -- an issue nothing would ever dispatch, since a workflow with
    no label on it is one the next tick greets as new.
    """
    try:
        _effects(gh, issue, state, generation)
    except Exception:
        log.exception(
            "issue=#%d could not be restarted onto %r this visit; the marker "
            "stands and the next one resumes at whichever half is still owed",
            issue.number, generation.restart_target,
        )
        _telemetry.emit_late_event(
            gh,
            _events.LateEvent(
                family=_events.LateEventFamily.FAILURE,
                failure=LateFailure.RESTART_FAILED,
            ),
            generation,
            stage=stage_name(gh.workflow_label(issue)),
        )
        return False
    return True


def _effects(
    gh: _client.GitHubClient,
    issue: Issue,
    state: _pinned_state.PinnedState,
    generation: LateGeneration,
) -> None:
    """The two external halves, in the order a human reads them.

    Both take the target off the RECORD rather than off the setting, so a
    restart begun under one `DECOMPOSE` value and resumed under the other
    finishes the label its own notice already announced.
    """
    target = generation.restart_target
    _announced(gh, issue, state, generation, target)
    _relabelled(gh, issue, target)


def _announced(
    gh: _client.GitHubClient,
    issue: Issue,
    state: _pinned_state.PinnedState,
    generation: LateGeneration,
    target: str,
) -> None:
    """Say once, on the thread, which cycle this issue is starting over as.

    Proved from the thread rather than from a record, because the comment and
    the write that would record it cannot be made one operation: a crash
    between them would say it twice. The marker is scoped to the cycle being
    minted, so a later restart of the same issue still gets its own sentence.

    A notice a PREVIOUS pass posted is adopted rather than merely recognized,
    and that is the whole reason this reads the comment rather than a boolean.
    Posting tracks the id on the in-memory record alone; the write that would
    make it durable is the retirement two steps below, so a pass whose relabel
    or retirement then failed left the id nowhere at all -- and the marker
    suppresses the repost that would have tracked it again. The bounded id
    ledger is what every later "is this comment ours" reading is taken
    against, and the projection keeps exactly that list, so a fresh cycle
    would otherwise wake up unable to recognize the comment announcing it.
    """
    marker = _restart_marker(issue.number, generation.restart_cycle_id)
    said = _notice_on_the_thread(gh, issue, marker)
    if said is None:
        _comments._post_issue_comment(gh, issue, state, _RESTART_NOTICE.format(
            predecessor=generation.restart_predecessor,
            cycle=generation.restart_cycle_id,
            label=target,
            marker=marker,
        ))
        return
    _tracked(state, said)


def _tracked(state: _pinned_state.PinnedState, said: Any) -> None:
    """Put a notice an earlier pass posted back on the bounded id ledger.

    Guarded on the ledger it is joining, because the tracker appends: a pass
    that adopted the same notice and then failed at the label again would
    otherwise spend one of the ledger's bounded slots per visit, evicting the
    ids of real comments to record one id repeatedly.
    """
    said_id = getattr(said, "id", None)
    if said_id is None:
        return
    if int(said_id) in _comments._orchestrator_ids(state):
        return
    _comments._track_orchestrator_comment(state, int(said_id))


def _relabelled(gh: _client.GitHubClient, issue: Issue, target: str) -> None:
    """Put the issue in the state the marker named, as this workflow's write.

    Written GUARDED, because it is a transition the graph declares: the
    unlabeled state a restart is entered from names both labels a restart may
    apply, which is exactly the edge an operator's removal of `rejected`
    opens.

    An issue already wearing the target is left alone where THIS orchestrator
    is the one that applied it -- a re-set costs a write and a second
    `stage_enter` on a state the issue never re-entered, and that is exactly
    the state a crash between the label and the retirement leaves behind.

    Where somebody else applied it, the label is not what this write is for.
    A restart's own application is the bot-authored event that separates one
    cycle's terminal from the next's, and the ending beside this owner reads
    the newest such application as its last-resort proof that a `rejected` it
    has no record of ever landed. A cycle minted over a hand-applied target
    leaves the PREVIOUS cycle's `rejected` standing as the newest, so the next
    unlabeled cancellation would adopt a terminal it never reached and restart
    on a removal nobody made. The name is therefore re-applied rather than
    accepted, and the label history is asked ONLY here -- a paginated walk,
    reached on the one pass that finds the target already in place.
    """
    if gh.workflow_label(issue) != target:
        gh.set_workflow_label(issue, target)
        return
    if gh.last_workflow_label_applied(issue) == target:
        return
    _reapplied(gh, issue, target)


def _reapplied(gh: _client.GitHubClient, issue: Issue, target: str) -> None:
    """Make a target somebody else applied this orchestrator's own write.

    Cleared and set rather than set again, because what is missing is the
    EVENT rather than the label: GitHub records an application only for a name
    that arrives, so writing the one already there would separate nothing.

    Nothing is lost in the window between the two writes. The marker is
    durable and answers the authorization for itself, so a tick that dies with
    the issue unlabeled re-enters this restart and applies the target from the
    ordinary side. A history that could not be read falls here too, for the
    same reason every other reading of it fails closed: one pair of label
    writes is what an answer nothing could establish costs.
    """
    log.warning(
        "issue=#%d already wears %r, and this orchestrator is not what "
        "applied it; putting the label back as its own write, so the fresh "
        "cycle is separated from its predecessor's terminal",
        issue.number, target,
    )
    gh.set_workflow_label(issue, None)
    gh.set_workflow_label(issue, target)


def _retired(
    gh: _client.GitHubClient,
    issue: Issue,
    state: _pinned_state.PinnedState,
    generation: LateGeneration,
) -> None:
    """Retire the marker, leaving the fresh cycle the restart was for.

    Last, and only once both effects have reconciled, because this write is
    what takes the record out of every reading that brought the tick back
    here: the marker is gone, the cancellation is gone, and the issue is an
    ordinary one on an ordinary label from the next tick.

    What it projects is the domain's own answer -- the cycle minted, the issue
    and root it belongs to, and the cycle it succeeds -- laid over a pinned
    comment stripped back to what is true about the issue rather than about
    the attempt.

    Where the issue now IS comes off the marker rather than off the issue. The
    label was applied a moment ago and a client's cached labels survive the
    write that changes them, so reading it back here would say the state the
    issue was in BEFORE the restart -- which for the ordinary entry is no
    state at all, putting `None` in the line an operator reads and in the
    `stage` both sinks file the reconciled record under. The marker named the
    target before either effect ran and is the same value the write carried.
    """
    target = generation.restart_target
    fresh = _restart.retire_restart(generation)
    _projected(state, fresh)
    gh.write_pinned_state(issue, state)
    log.warning(
        "issue=#%d is restarted as late-split cycle %d after cycle %s; every "
        "record of that cycle is dropped and the issue starts over on %r",
        issue.number,
        fresh.cycle_id,
        fresh.restart_predecessor,
        target,
    )
    _telemetry.emit_late_event(
        gh,
        _events.LateEvent(
            family=_events.LateEventFamily.RESTART,
            restart_step=_events.LateRestartStep.RECONCILED,
        ),
        fresh,
        stage=stage_name(target),
    )


def _projected(
    state: _pinned_state.PinnedState, fresh: LateGeneration,
) -> None:
    """Rewrite this pinned comment as the fresh cycle's whole durable state.

    A whitelist rather than a list of drops. Every stage shares this comment
    and each adds keys of its own, so a projection that named what to delete
    would carry whatever the deleting was not written for -- a park nobody
    set, a pull request nobody opened, a watermark over a thread the fresh
    cycle has not read. What is kept is named instead, and the identity of the
    comment itself is kept by rewriting the payload in place rather than by
    minting a second one no reader would find.
    """
    kept = {
        key: state.data[key] for key in _RETAINED_KEYS if key in state.data
    }
    state.data.clear()
    state.data.update(kept)
    _late_state.write_late_generation(state, fresh)


def _restart_marker(issue_number: int, cycle_id: Any) -> str:
    """The receipt one restart's notice on the thread is stamped with."""
    return _RESTART_MARKER.format(issue=issue_number, cycle=cycle_id)


def _notice_on_the_thread(
    gh: _client.GitHubClient, issue: Issue, marker: str,
) -> Any | None:
    """This restart's own notice where the thread already carries it.

    The comment rather than the fact of it, because an adopted notice owes the
    ledger its id. Both halves of "ours" are still required of it -- the
    cycle-scoped marker and the author -- so a marker anybody can paste
    silences nothing and adopts nothing.

    Walked whole rather than from a watermark: the projection behind this
    drops every watermark the cancelled cycle kept, and a restart resumed
    after one landed would be reading from a mark that is no longer there.
    """
    bot_login = getattr(gh, "_bot_login", None)
    for posted in gh.comments_after(issue, None):
        if _github_comments.carries_own_marker(
            (posted,), marker, bot_login=bot_login,
        ):
            return posted
    return None


def _persisted(
    gh: _client.GitHubClient,
    issue: Issue,
    state: _pinned_state.PinnedState,
    generation: LateGeneration,
) -> None:
    """Make one step of this transaction durable before the next one acts."""
    _late_state.write_late_generation(state, generation)
    gh.write_pinned_state(issue, state)
