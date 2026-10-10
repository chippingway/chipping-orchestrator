# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Conflict-round receipts and the validated handoff to review.

A held resolution records its outcome and exact head for a later tick.
Recovery proves that head before incrementing the round, clearing its park
and receipt, and moving the issue to validation. A round that rewrote the
pull request's head records the report debt it leaves first, on the tick that
pushed and on the one a crash sent back to finish it alike. The count is
made durable ahead of the relabel (`handoff`), so a move a crash cut short is
made by the next tick without the round being counted twice.
"""
from __future__ import annotations

from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.engine import usage as _usage
from orchestrator.workflow.late_split import (
    formats as _formats,
    payloads as _payloads,
)
from orchestrator.workflow.stages.conflicts import (
    handoff as _handoff,
    models as _models,
    parks as _conflict_parks,
    report_debt as _report_debt,
    resume_records as _resume_records,
    state as _state,
)
from orchestrator.workflow.stages.implementing import (
    late_gate_models as _late_gate_models,
)

# What the three rounds that REWRITE the pull request's head are recorded as,
# in the audit event and in the receipt a hold leaves for the tick that
# resumes behind it: a clean replay of the branch onto its base, a replay the
# dev finished by resolving its conflicts, and commits an earlier tick made and
# never pushed. Each moves the pull request onto a head no developer report is
# about -- the conflict prompt asks for none, and nothing on the recovery road
# can say whether the commits it finds ever had one -- so each owes the report
# debt. A body edit's round is not one: its commit is the developer's own
# answer to the change, and the report describing it is the one its resume
# returned, recorded ahead of the push (`resume_reports`).
_BASE_REBASED_CLEAN = "base_rebased_clean"

_AGENT_RESOLVED = "agent_resolved"

_RECOVERED_PUSH = "recovered_push"

_REWRITES = frozenset((_BASE_REBASED_CLEAN, _AGENT_RESOLVED, _RECOVERED_PUSH))


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
    `last_conflict_resolved_at`, persists pinned state, emits the
    `conflict_round` audit event, and flips the label -- in that order,
    through `handoff`, so the count is durable before the move it pays for
    and the event that reports it, a move that did not land is made by the
    next tick rather than counted again, and a count write that did not land
    leaves nothing reported for the tick that counts it again to repeat.
    Shared by every pushed-diff exit --
    recovered push, clean base rebase, agent resolution, and the drift resume
    -- and by the settled round a hold or a crash left for a later tick.
    Docs do not run here: the single docs pass is deferred to the post-approval
    handoff to `documenting` in `_handle_validating`.

    A round that rewrote the head records its report debt before any of that,
    durably and ahead of the relabel (`report_debt`): the label is what hands
    the head to the reviewer road, which would otherwise park for the report
    of a commit this stage made. A debt the pinned comment has no room for
    holds the whole tail -- nothing counted, nothing relabelled -- behind the
    park that records why, and the settled round the push's own write left
    brings the next tick back to try again.
    """
    if outcome in _REWRITES and not _report_debt._records_the_rewrite(ctx, sha or ""):
        return
    _counts_the_round(ctx, conflict_round)
    _conflict_parks._left_unparked(ctx)
    _handoff._writes_the_count(ctx, sha)
    _emit_conflict_round_incremented(
        ctx,
        pr_number=int(pr_number),
        new_round=conflict_round + 1,
        outcome=outcome,
        sha=sha,
    )
    _handoff._moves_on(ctx)


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
    return _late_gate_models._Spends(fields=(
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
    left is the tail above, with the outcome the round actually had -- the
    report debt a rewrite owes included, read off the code-publication receipt
    the push that published it left. That is also the road a tick takes back
    after a process ended between its own push and its hand to `validating`:
    the push's write carries this receipt too, so the debt is not lost with
    the tail that never ran.

    A recovered push that preceded a rebase leaves no receipt, since it
    finished no round, but its write names the head it published, and the
    debt that head is owed is recorded here first -- ahead of every resume
    and rebase, against the head the pull request was just fetched on. One
    the pinned comment has no room for ends the tick behind its park, since
    nothing past it may run over a head that owes a debt nobody wrote down.

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

    A round already counted whose move to `validating` never landed is asked
    first of all: it owes the label and nothing else, so nothing behind it may
    count it again or start a new attempt over the head it handed on.
    """
    if _handoff._makes_the_owed_move(ctx, sync) or not _report_debt._records_the_owed_preamble(
        ctx, sync.fetched_tip,
    ):
        return True
    outcome, settled = _settled_round_owed(ctx.state)
    if not outcome or pr_number is None:
        return False
    # In sync, both ways. Ahead of the remote the commit may never have
    # reached it; behind, it did and this checkout is no longer what the pull
    # request carries, which is the head the handoff would hand a reviewer.
    if sync.ahead > 0 or sync.behind > 0:
        return False
    if not _handoff._standing_on(ctx, sync.worktree, settled):
        return False
    _hand_resolved_round_to_validating(
        ctx, conflict_round, pr_number, outcome=outcome, sha=settled,
    )
    return True


def _counts_the_round(ctx: _models._ConflictContext, conflict_round: int) -> None:
    """Stage what a paid round leaves: its count, and no receipt still owing it.

    `review_round` resets, since rebasing rewrites SHAs and validation must
    re-approve the rebased branch; `conflict_round` is bumped and
    `last_conflict_resolved_at` stamped.

    The receipt is dropped here, by the tail rather than by the reader above,
    so a recovered-commit push that publishes a held resolution on its own --
    reaching the tail under its own outcome -- leaves nothing behind for a
    later tick to finish a second time. So is the publication a body edit's
    resume recorded with its report (`resume_records`), whichever road pushed
    it -- unless that report is still unbound. Then the record stays, since it
    is what refuses a commit the checkout gains before the binding, should the
    relabel behind this write not land.
    """
    ctx.state.set(_state._REVIEW_ROUND, 0)
    ctx.state.set(_state._CONFLICT_ROUND, conflict_round + 1)
    ctx.state.set("last_conflict_resolved_at", _usage._now_iso())
    ctx.state.set(_state._SETTLED_OUTCOME, None)
    ctx.state.set(_state._SETTLED_SHA, None)
    _resume_records._forgets_the_candidate(ctx.state)
