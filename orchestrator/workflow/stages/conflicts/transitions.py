# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The two shapes every state-changing exit of this stage shares.

A park is never just a comment: `_park_awaiting_human` mutates the in-memory
pinned state, so the `write_pinned_state` that persists it has to follow on the
same tick or the HITL flag is lost and the next tick re-runs the rebase. This
stage has eleven park sites, which is exactly why the pair lives on one owner
rather than being repeated at each.

A pushed round is the same argument at a larger size: reset `review_round`
because rebasing rewrote the SHAs the reviewer approved, bump `conflict_round`
so the cap can still fire, stamp when it resolved, emit the audit event, flip
the label, and write once. Five exits earn that tail -- the recovered push, the
clean base rebase, the agent resolution, the drift resume, and the no-op flip
(which shares only the counter half, having resolved nothing) -- and the audit
event's `outcome` is what lets a tail of the JSONL sink tell them apart without
re-reading the code.
"""
from __future__ import annotations

import logging

from orchestrator.config import settings as config
from orchestrator.git.measurement import commits as _measurement_commits
from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.engine import guards as _guards, usage as _usage
from orchestrator.workflow.late_split import (
    formats as _formats,
    payloads as _payloads,
)
from orchestrator.workflow.stages.conflicts import models as _models, state as _state
from orchestrator.workflow.stages.implementing import (
    late_records as _late_records,
)
from orchestrator.workflow.state import WorkflowLabel

log = logging.getLogger("orchestrator.workflow")


# The revision a checkout's own head is named by.
_HEAD = "HEAD"


def _park_conflict(
    ctx: _models._ConflictContext, message: str, *, reason: str,
    once: bool = False,
) -> None:
    """Park awaiting human and persist pinned state.

    Every `resolving_conflict` park pairs `_park_awaiting_human` with the
    matching `write_pinned_state`; routing them through here keeps the two
    from drifting apart across the handler's many exits.

    The reason is recorded durably as well as emitted, because two decisions
    past the park are made on it: whether the tick that finds it standing
    waits for a human or retries the reading that failed, and whether a
    refusal re-taken on a later tick is the SAME refusal.

    `once` answers the second. A refusal a tick can re-take every poll -- a
    ref nothing resolves, a branch that stays diverged -- would put a fresh
    notice on the thread each tick and bury the one an operator has to act on.
    So it is said once, and "once" means once per REASON rather than once per
    park: an issue parked on an agent's question that then becomes diverged is
    being told something new, and telling it is the whole point. Only the
    identical refusal standing again is silent, and there the flags are
    already what a park is, so the state write is all that is owed.

    A transient refusal taken over a park somebody OWES AN ANSWER TO is the
    other silence, and it answers the first decision. Recorded, the reason
    would be the one the next tick reads, and a reading that comes back is
    what clears a transient park -- so a fetch that failed for one poll while
    an agent's question stood unanswered would hand the tick after it a branch
    that reads as nobody waiting, and it would rebase, push, count the round
    and hand a `validating` reviewer work the human was asked about. The park
    already standing is the one that governs; the reading is retried under it
    every tick regardless, and it is not announced again because the notice an
    operator has to act on is the one already on the thread.
    """
    if _says_nothing_new(ctx.state, reason, once=once):
        ctx.gh.write_pinned_state(ctx.issue, ctx.state)
        return
    _guards._park_awaiting_human(ctx.gh, ctx.issue, ctx.state, message, reason=reason)
    # `_park_awaiting_human` clears the durable field on purpose, so every
    # caller that needs one re-sets it. This stage needs one on all of them.
    ctx.state.set(_state._PARK_REASON, reason)
    ctx.gh.write_pinned_state(ctx.issue, ctx.state)


def _says_nothing_new(
    state: PinnedState, reason: str, *, once: bool,
) -> bool:
    """Whether this refusal adds nothing to the park already standing.

    Two shapes, and in both the flags are already what a park is, so all the
    caller still owes is the durable write.

    The identical refusal re-taken, which `once` asks for: what clears one of
    these is a reading rather than a reply, so every tick after it takes it
    again.

    And a transient refusal over a park a human owes an answer to, where
    recording it would REPLACE the standing reason with one the next tick
    reads as retryable -- the awaiting-human resume would be skipped and the
    rebase behind it would run while the question is still open.
    """
    if once and state.get(_state._PARK_REASON) == reason:
        return True
    return reason in _state._TRANSIENT_PARKS and _waits_on_a_human(state)


def _waits_on_a_human(state: PinnedState) -> bool:
    """Whether this issue is parked on something only a person can answer.

    The awaiting-human flag alone does not say it: every refusal this stage
    takes sets it, including the ones that name a reading that DID NOT HAPPEN
    and so name nothing a reply could address. Those are told apart by the
    durable reason, which is why both readers -- the resume that would consume
    a tick on a reply, and the park that would otherwise overwrite the reason
    they turn on -- ask this one predicate rather than spelling it twice.
    """
    if not state.get(_state._AWAITING_HUMAN):
        return False
    return state.get(_state._PARK_REASON) not in _state._TRANSIENT_PARKS


def _park_unreadable_head(ctx: _models._ConflictContext) -> None:
    """Stop a round whose checkout could not name the head it begins at.

    Shared by the two seams that read that head: the rebase, which leases the
    push its clean exit makes against it, and the body-edit resume, whose
    publication leases against it too. It is not bookkeeping either of them
    could go on without. The size gate reads "no head" as a caller that
    established none, and pins the push to whatever the pull request is
    standing on when IT looks -- which is after the rebase, or after an agent
    that was out for minutes. A commit somebody else landed in that window
    becomes the lease and is force-overwritten by work never proved against
    it.

    Refused before either runs, so nothing is rebased, no agent is spawned
    over a checkout nobody could read, and neither caller has consumed
    anything it would have to put back.
    """
    spec = ctx.spec
    log.error(
        "issue=#%d resolving_conflict: could not read the head its worktree "
        "stands on; refusing to rebase or resume over a checkout nobody read",
        ctx.issue.number,
    )
    _park_conflict(
        ctx,
        f"{config.HITL_MENTIONS} nothing could read the commit this issue's "
        f"worktree stands on, so `git rebase {spec.remote_name}/"
        f"{spec.base_branch}` was not run and no dev session was resumed. "
        "That commit is the head every exit of this round leases its "
        "force-push against, and a push with no lease behind it adopts "
        "whatever the pull request has moved to and overwrites it. Nothing "
        "was pushed and nothing was discarded. Repair the checkout and the "
        "next tick rebases it again.",
        reason=_state._REASON_UNREADABLE_HEAD,
        # Said once: this refusal is retried by every tick after it, since
        # what clears it is the reading itself rather than a reply.
        once=True,
    )


def _park_unreadable_worktree(ctx: _models._ConflictContext) -> None:
    """Stop a tick whose checkout could not say what it is carrying.

    A status that established nothing names no paths, and so does a tree with
    nothing in it -- so every probe that reports paths alone reads the first
    as the second. What hangs off that answer is whether the commit about to
    be published is the whole of what the worktree holds: taken as clean, a
    checkout carrying uncommitted edits is pushed as a SHA that silently omits
    them, and the reviewer behind it runs on a tree the pull request does not
    have.

    The size gate proves the tree for itself before it freezes an entry, but
    that proof is part of the MEASUREMENT: an install running `DECOMPOSE=off`
    never freezes one, so the push goes out and the later proof can park but
    cannot take it back. So the reading is required here, ahead of the effect,
    on every road that publishes from this checkout or resumes an agent over
    it.
    """
    log.error(
        "issue=#%d resolving_conflict: could not read what its worktree is "
        "carrying; refusing to publish from or resume over a checkout whose "
        "status nobody read",
        ctx.issue.number,
    )
    _park_conflict(
        ctx,
        f"{config.HITL_MENTIONS} nothing could read what this issue's "
        "worktree is carrying, so nothing was pushed from it and no dev "
        "session was resumed over it. A reading that established nothing "
        "names no paths, which is exactly what a clean tree names too -- and "
        "taken as clean, a checkout with uncommitted edits is published as a "
        "commit that silently omits them. Nothing was pushed and nothing was "
        "discarded. Repair the checkout so its status reads, and the next "
        "tick carries on.",
        reason=_state._REASON_UNREADABLE_WORKTREE,
        # Said once: a later tick's own status read is what clears this, so
        # every tick after this one retries it.
        once=True,
    )


def _emit_conflict_round_incremented(
    ctx: _models._ConflictContext,
    *,
    pr_number: int,
    new_round: int,
    outcome: str,
    sha: str | None = None,
) -> None:
    """Record a `conflict_round` audit event when the counter ticks.

    Centralizes the bookkeeping so every increment site -- ahead-of-remote
    push recovery, up-to-date no-op flip, clean base-rebase push, agent-
    resolved conflict push, drift-pushed bounce -- emits the same shape.
    `outcome` distinguishes the increment cause so a tail of the JSONL sink
    can attribute rounds without re-reading the surrounding code.
    """
    ctx.gh.emit_event(
        _state._CONFLICT_ROUND,
        issue_number=ctx.issue.number,
        stage="resolving_conflict",
        pr_number=int(pr_number),
        sha=sha or None,
        action="incremented",
        conflict_round=int(new_round),
        outcome=outcome,
        review_round=int(ctx.state.get(_state._REVIEW_ROUND) or 0),
        retry_count=ctx.state.get("retry_count"),
    )


def _hand_resolved_round_to_validating(
    ctx: _models._ConflictContext,
    conflict_round: int,
    pr_number,
    *,
    outcome: str,
    sha: str | None,
) -> None:
    """Record a pushed conflict-resolution round and hand back to `validating`.

    Resets `review_round` (rebasing rewrites SHAs, so validation must
    re-approve the rebased branch), bumps `conflict_round`, stamps
    `last_conflict_resolved_at`, emits the `conflict_round` audit event, flips
    the label, and persists pinned state. Shared by every pushed-diff exit --
    recovered push, clean base rebase, agent resolution, and the drift resume.
    Docs do not run here: the single docs pass is deferred to the post-approval
    handoff to `documenting` in `_handle_validating`.
    """
    ctx.state.set(_state._REVIEW_ROUND, 0)
    ctx.state.set(_state._CONFLICT_ROUND, conflict_round + 1)
    ctx.state.set("last_conflict_resolved_at", _usage._now_iso())
    _left_unparked(ctx)
    _forget_settled_round(ctx)
    _emit_conflict_round_incremented(
        ctx,
        pr_number=int(pr_number),
        new_round=conflict_round + 1,
        outcome=outcome,
        sha=sha,
    )
    ctx.gh.set_workflow_label(ctx.issue, WorkflowLabel.VALIDATING)
    ctx.gh.write_pinned_state(ctx.issue, ctx.state)


def _settles_the_held_round(outcome: str, sha: str | None):
    """The round a hold owes this stage, named for the gate to write it down.

    A hold ends the tick: the resolution is committed, the issue is on
    `workflow:decomposing`, and the tail above never runs. But the round IS
    resolved -- an authorized settlement publishes the accepted commit from
    the adjudication -- and the resumed tick could not work out which of the
    four content updates it was: the branch it comes back to already carries
    its base, which is the no-op flip's own reading and the one exit that
    resolves nothing and stamps no `last_conflict_resolved_at`.

    So the pair is handed to the gate and written inside its routed write,
    ahead of the relabel, and the resumed tick finishes the ORIGINAL outcome
    from it rather than re-deriving a wrong one.
    """
    return _late_records._Spends(fields=(
        (_state._SETTLED_OUTCOME, outcome),
        (_state._SETTLED_SHA, sha or ""),
    ))


def _settled_round_owed(state: PinnedState) -> tuple[str, str]:
    """The round a settlement published and this stage has still to count.

    The pair a receipt is only a receipt with: an outcome saying which of this
    stage's content updates it was, and a whole object id naming the head it
    produced. Either one missing is no receipt at all -- a hand edit, an older
    write, a field that would not type -- and nothing can finish a round it
    cannot name either end of, so the reader below refuses it and the ordinary
    road clears it by reaching a tail of its own.

    Asked by the finisher and by every road that would start a fresh resume --
    the body edit at the door of the handler, the human reply at the door of
    the rebase -- off one parse so none of them can disagree about what is
    outstanding. A resume that commits while a round is owed hands the gate a
    receipt of its own, and the single slot they all write into holds one
    round, not two: pushed, the owed round is cleared without ever being
    counted; held, the gate writes over it.
    """
    settled = _payloads.as_hex(
        state.get(_state._SETTLED_SHA), _formats.COMMIT_LENGTHS,
    )
    outcome = state.get(_state._SETTLED_OUTCOME)
    if not outcome or not settled:
        return ("", "")
    return (str(outcome), settled)


def _finished_settled_round(
    ctx: _models._ConflictContext,
    sync: _models._WorktreeSync,
    conflict_round: int,
    pr_number,
) -> bool:
    """Finish a resolution the size gate held and an adjudication published.

    The receipt is the whole of what this tick knows about a round it did not
    run: the resolution was reached, committed, and read by a human as one
    coherent change, and the settlement put it on the pull request. What is
    left is the tail above, with the outcome the round actually had.

    `sync.ahead` is what says the commit reached the remote, and it is asked
    because the receipt cannot: a verdict that parked, or a human who moved
    the label by hand, leaves the same receipt over a commit still on disk
    only. Ahead of the remote the receipt stands and the recovered-commit push
    below carries it through the gate, which is the one road that measures it
    again -- and the tail clears the receipt wherever it finally runs.

    In sync is not the same claim as CARRYING it. A replacement host rebuilds
    the checkout from a pull request that has moved on, and what it gets is a
    branch level with its remote and standing on somebody else's head -- so
    the head the receipt names is proved against the checkout rather than
    inferred from the counters.

    BEHIND the remote is refused for the opposite reason, and it is not the
    round that fails there but the handoff. A remote standing on a descendant
    of the settled commit does carry it, so the round really did land -- but
    the tail hands `validating` this CHECKOUT, and the reviewer spawned behind
    it reuses the worktree as it finds it rather than fast-forwarding to the
    tip. Waved through, the round is counted correctly and a human is then
    shown a verdict taken over the commit the pull request has already moved
    past. So the receipt keeps standing and the divergence guard behind this
    asks a human to reconcile the branch, which is the one thing that makes
    the handoff safe again; the same reading settles the round on the tick
    after that.

    Ahead of every resume, and that ordering is the point. A body edit or a
    human reply that commits records a receipt of its own into the one slot
    this one is waiting in, and the park that let the reply in is no exception
    -- the tick that parked is exactly the tick that could not settle the
    round.

    Fail closed on every other reading. A receipt whose head is not a whole
    object id is not one a checkout can be compared to, and a head this host
    cannot peel is not one anything may be compared against -- both leave the
    receipt exactly where it is for a tick that can prove it.
    """
    outcome, settled = _settled_round_owed(ctx.state)
    if not outcome or pr_number is None:
        return False
    # In sync, both ways. Ahead of the remote the commit may never have
    # reached it; behind, it did and this checkout is no longer what the pull
    # request carries, which is the head the handoff would hand a reviewer.
    if sync.ahead > 0 or sync.behind > 0:
        return False
    if not _standing_on(ctx, sync.worktree, settled):
        return False
    _hand_resolved_round_to_validating(
        ctx, conflict_round, pr_number, outcome=outcome, sha=settled,
    )
    return True


def _standing_on(
    ctx: _models._ConflictContext, worktree, settled: str,
) -> bool:
    """Whether this checkout is the commit a settled receipt names.

    Proved rather than read, because everything past it is a claim about one
    object id: a revision this host cannot peel is not a head that matches
    anything, and a host that never had the commit answers exactly that.
    """
    proved = _measurement_commits._prove_candidate_commit(worktree, _HEAD)
    if proved.is_frozen and proved.sha == settled:
        return True
    log.error(
        "issue=#%d stands on %s rather than the settled resolution %s; "
        "leaving the receipt for a tick that can prove it",
        ctx.issue.number, proved.sha or "an unreadable head", settled,
    )
    return False


def _left_unparked(ctx: _models._ConflictContext) -> None:
    """Drop the park a round handed on to `validating` runs out from under.

    Every road that reaches the tail with an agent behind it has already
    cleared the flags -- the dev resume does it, because it is reacting to a
    human -- and the one road that does not is the settled round, which is
    reached on an issue parked by the very reading it has just taken
    successfully. Left set, `validating` is handed an issue that reads as
    waiting on somebody nobody is waiting for.
    """
    ctx.state.set(_state._AWAITING_HUMAN, False)
    ctx.state.set(_state._PARK_REASON, None)


def _forget_settled_round(ctx: _models._ConflictContext) -> None:
    """Drop a receipt the round it was owed for has now been paid on.

    Cleared by the tail rather than by the reader above, so a recovered-commit
    push that publishes a held resolution on its own -- reaching the tail
    under its own outcome -- leaves nothing behind for a later tick to finish
    a second time.
    """
    ctx.state.set(_state._SETTLED_OUTCOME, None)
    ctx.state.set(_state._SETTLED_SHA, None)
