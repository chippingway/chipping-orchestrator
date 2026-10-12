# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Persist the parks an auto-rebase attempt ends in, and the rollback behind them.

Every refresh-time failure parks for a human the same way
(`_park_auto_rebase_failure`), and every road that has to put the checkout
back onto the anchor before it parks goes through one tail
(`_reset_clear_and_park`), which drops the attempt and the records the reset
abandoned only where the reset itself landed -- staging first whatever a
recovery context says it owes over that reset
(`_AutoRebaseRecoveryContext.settles_over_a_reset`), so it rides the same
write; the workflow's recovery hands one on every road. The notice that park
posts says what the reset and the clean behind it came to, and the drop as what
the park's own write makes durable (`_reset_outcome`), so a caller describes
only why it parks. A recovery park
that keeps the attempt instead -- that tail behind a reset that did not land,
and the parks that never reset -- asks the recovery context first whether it
may go on (`_proves_before_the_park`), so a transaction the workflow captured
for the landed head, or evidence it settled for it, is proved again before the
record a human's reply brings back is left standing. Every park a recovery
takes is recorded as the recovery records one (`_parks_the_recovery`): over
the comment read afresh, through the park the workflow hands its contexts,
so nothing another road wrote while the notice went out is put back. The
finish of a rewrite that landed is the workflow's (`workflow/engine/rewrite_finish.py`),
whichever road reached it, and so is the tail an interrupted finish leaves
behind its evidence -- the announcement, the relabel, and the retirement --
which none of these parks takes: a park that keeps the attempt keeps it for
the reply that brings that finish back, with what the attempt still owes.
"""
from __future__ import annotations

import subprocess
from types import MappingProxyType

from github.Issue import Issue

from orchestrator.git import commands
from orchestrator.git.base_sync import attempts
from orchestrator.git.base_sync.models import (
    _AutoRebaseContext,
    _AutoRebaseRecoveryContext,
)
from orchestrator.git.base_sync.state import (
    _AUTO_REBASE_PARK_REASONS,
    _ERROR_SNIPPET_LEN,
    _PARK_REASON,
    log,
)
from orchestrator.github.client import GitHubClient
from orchestrator.github.pinned_state import PinnedState

# The drop is said as what the park's write will make durable, since the notice
# goes out ahead of that write and cannot see whether it lands.
_RESET = (
    "Local HEAD has been reset to `{sha}`, where the branch stood before the rebase{cleaned}; `git reflog` "
    "still has whatever the reset left behind. The attempt, with every record the reset abandoned, is dropped "
    "by the pinned-state write that records this park, and still stands until that write lands."
)

_UNRESET = (
    "The reset this park takes did not land: `git reset --hard {sha}` failed (`{error}`), so local HEAD was "
    "not moved{cleaned}, and this park keeps the attempt -- its anchor `{sha}` among it -- with every record it "
    "carries. Inspect the worktree's git state before replying."
)

# What the clean behind the reset came to, beside the reset that landed or did not.
_CLEANED = MappingProxyType({
    (True, True): ", and untracked files were cleaned",
    (True, False): ", but `git clean -fd` failed, so untracked files may remain",
    (False, True): ", though untracked files were cleaned",
    (False, False): ", and `git clean -fd` failed too",
})


def _park_auto_rebase_failure(
    gh: GitHubClient,
    issue: Issue,
    state: PinnedState,
    *,
    message: str,
    reason: str,
) -> None:
    """Park an issue awaiting human for an auto-rebase failure.

    Wraps `_park_awaiting_human` so every refresh-time failure mode
    parks identically: `awaiting_human=True`, the HITL message lands
    on the issue thread (NOT the PR -- the resume-on-human-reply
    scan reads from the issue), `last_action_comment_id` is ratcheted
    forward by `_park_awaiting_human`, and the durable
    `park_reason` is re-set after the helper clears it by contract.
    `gh.write_pinned_state` is called here so the caller can return
    immediately.

    `reason` must be one of `_AUTO_REBASE_PARK_REASONS` -- the refresh
    recovery branch keys off the same set to decide whether a new
    human comment on this issue is the "retry now" signal.
    """
    # Lazy import: the guard owner sits in the workflow layer above this
    # package, and that layer imports this package at module load time, so
    # binding it here at module load would be circular.
    from orchestrator.workflow.engine import guards as _guards
    assert reason in _AUTO_REBASE_PARK_REASONS, (
        f"_park_auto_rebase_failure called with reason={reason!r}, "
        f"which is not in _AUTO_REBASE_PARK_REASONS"
    )
    _guards._park_awaiting_human(gh, issue, state, message, reason=reason)
    state.set(_PARK_REASON, reason)
    gh.write_pinned_state(issue, state)


def _reset_clear_and_park(
    context: _AutoRebaseContext | _AutoRebaseRecoveryContext,
    reset_sha: str,
    *,
    message: str,
    reason: str,
    clean: bool = False,
) -> None:
    """Restore the worktree to `reset_sha`, drop the recovery anchor, and park.

    The shared tail of every auto-rebase park path: a rebase / push /
    recovery step could not safely finalize, so HEAD is hard-reset back
    to a known SHA (the pre-rebase anchor = the last-known remote PR
    head) so the same-tick stage handler dispatch never reads a local
    HEAD the PR may not carry, the crash-recovery anchor is cleared (the
    reset put HEAD back at it, so a follow-up tick would only hit the
    "HEAD == anchor" no-op case), and the issue is parked awaiting human.
    `clean=True` also runs `git clean -fd` after the reset to discard the
    untracked leftovers a dirty rebase produced (recoverable via
    `git reflog`).

    A failed reset / clean is logged but does not abort the park: the
    `awaiting_human` flag is what short-circuits the same-tick handlers,
    and it still lands even if the worktree is left on an unexpected SHA
    for the operator to inspect. The park's notice is the caller's
    `message` -- why it parks -- followed by what actually happened
    (`_reset_outcome`): the reset and the drop behind it, or a reset that
    did not land and the attempt kept, never a reset that did not happen.

    What the park DROPS is held to that reset landing, and every record it
    would drop is held to it alike. The size gate measures a rebased head
    before it is pushed and, at or under the ceiling, records it as a commit
    still owed a publication -- and a reset that landed puts the branch back
    on the pre-rebase SHA, so that commit is not on this branch any more and
    only the reflog still has it. Left standing there, it is a debt nothing
    can pay and everything trips over: the pre-tick base refresh freezes this
    branch out of the sync for as long as the issue lives, and the
    reconciliation ahead of every handler stops the tick for a publication
    that is never coming. An approval whose commit was abandoned is
    superseded, which has always been one of the three things that drops one
    -- so the owner doing the abandoning is the one that drops it. The whole
    attempt goes with it for the same reason: the reset put HEAD back on the
    anchor, so a follow-up tick would find the branch exactly where the
    attempt started and have nothing to recover.

    A reset that FAILED abandoned nothing, and what the comment carries is the
    only account of where the checkout may be standing: the anchor the branch
    would go back to, the replay the attempt recorded making and the
    publication it made it for, the approved commit, the head its push is
    pinned to, and the route bookkeeping that push closes. Dropped there, the
    next tick has no anchor to bring the recovery back with and no id to ask
    for the candidate by -- it measures whatever the worktree turns out to be,
    while the permission the reset could not undo is left with nothing naming
    the attempt it belongs to. So nothing is dropped: the reset is proved
    first, and every record follows it rather than the intent.

    The permission a transfer granted goes in the same write and for the same
    reason: a rebase of a commit an authorized settlement accepted may be licensed to
    carry that verdict over, and the reset puts the branch back onto the
    commit the exemption never left. The exemption itself needs no repair --
    the grant moved nothing -- so what is left over is a claim about a push
    that will never happen, for an object no branch has any more. Only an
    outstanding record this build can read back whole is dropped, which is the
    rollback's own rule wherever a rewrite is undone.

    A recovery's attempt may also stand guard over a record the workflow made
    about the head the reset takes the checkout off -- a verification
    transaction a finish captured for a landed head, or evidence one settled
    for it -- so the recovery is asked to settle it on the same state first
    (`_releases_over_the_reset`): it rides this one write with the attempt's
    drop, or neither lands -- and where the recovery answers that it cannot
    be settled, settled evidence with no room left for its history entry,
    nothing is dropped or parked: the attempt is kept guarding it, as a reset
    that failed keeps it, and the next tick asks again. That write is the
    recovery's own park (`_parks_the_recovery`), landed over the comment read
    afresh, so a report or evidence record another road wrote while the
    notice went out is kept beside it rather than put back.
    """
    reset = commands._git_hardened(
        "reset", "--hard", reset_sha, cwd=context.worktree,
    )
    restored = reset.returncode == 0
    if not restored:
        log.error(
            "issue=#%d auto-rebase recovery: reset --hard to %s failed: "
            "%s; the awaiting_human park still short-circuits same-tick "
            "handler dispatch but operator inspection of HEAD is needed",
            context.issue.number,
            reset_sha[:8],
            (reset.stderr or "").strip(),
        )
    cleaned = None
    if clean:
        cleaning = commands._git_hardened("clean", "-fd", cwd=context.worktree)
        cleaned = cleaning.returncode == 0
        if not cleaned:
            log.error(
                "issue=#%d auto-rebase recovery: `git clean -fd` after "
                "the reset failed: %s",
                context.issue.number, (cleaning.stderr or "").strip(),
            )
    if restored:
        parks = _releases_over_the_reset(context, reset_sha)
    else:
        parks = _proves_before_the_park(context)
    if not parks:
        return
    _parks_the_recovery(
        context,
        message=f"{message}\n\n{_reset_outcome(reset_sha, reset, cleaned)}",
        reason=reason,
    )


def _parks_the_recovery(
    context: _AutoRebaseContext | _AutoRebaseRecoveryContext,
    *,
    message: str,
    reason: str,
) -> None:
    """Park `context`'s issue as `_park_auto_rebase_failure` parks it, recorded as its recovery records a park.

    The park's record lands behind its notice, a request after the tick read
    the comment -- long enough for another road to settle and review a later
    report, or move an evidence record. A recovery context the workflow built
    carries the park that lands over the comment read afresh instead, keeping
    whatever another road wrote meanwhile
    (`_AutoRebaseRecoveryContext.lands_a_park`): over a landed reset, the
    evidence a finish captured or settled for the head is retired in the very
    write that drops the attempt (`_releases_over_the_reset`), and that write
    puts back no report the evidence was superseded by. A context with none --
    a refresh's own -- writes the state whole.
    """
    lands = context.lands_a_park if isinstance(context, _AutoRebaseRecoveryContext) else None
    if lands is None:
        _park_auto_rebase_failure(context.gh, context.issue, context.state, message=message, reason=reason)
        return
    assert reason in _AUTO_REBASE_PARK_REASONS, (
        f"_parks_the_recovery called with reason={reason!r}, which is not in _AUTO_REBASE_PARK_REASONS"
    )
    lands(context, message, reason)


def _reset_outcome(reset_sha: str, reset: subprocess.CompletedProcess, cleaned: bool | None) -> str:
    """What the park's notice says the reset to `reset_sha` came to, beside the clean behind it where one ran.

    `reset` is what git answered the reset: what it printed on a reset that
    did not land is quoted. A reset that landed is the attempt dropped with what it
    abandoned -- by the park's own write, which the notice goes out ahead of,
    so the notice says that write drops them rather than that they are gone;
    one that did not land is the attempt kept whole, since records follow the
    reset rather than the intent, and a write that fails keeps it as well.
    """
    restored = reset.returncode == 0
    said = "" if cleaned is None else _CLEANED[restored, cleaned]
    short = reset_sha[:8]
    if restored:
        return _RESET.format(sha=short, cleaned=said)
    error = (reset.stderr or "").strip()[:_ERROR_SNIPPET_LEN]
    return _UNRESET.format(sha=short, error=error, cleaned=said)


def _proves_before_the_park(context: _AutoRebaseContext | _AutoRebaseRecoveryContext) -> bool:
    """Whether a recovery park that keeps the attempt may go on, once the workflow proved what it captured.

    Every such park leaves the whole record standing for a human's reply to
    bring the recovery back to, and a verification transaction the workflow
    captured for the landed head stands with it, as does evidence a finish
    already settled for it. So the workflow proves them again first
    (`_AutoRebaseRecoveryContext.proves_before_a_park`), and abandons the one
    or invalidates the other where anything it rests on moved, before the park
    and not behind the reply -- by which time what moved may be back. False is a
    movement it read and could not record: nothing is parked, the anchor still
    holds every handler, and the next tick's recovery asks again. A refresh's
    own context, ahead of any recovery, has captured nothing to prove.
    """
    proves = context.proves_before_a_park if isinstance(context, _AutoRebaseRecoveryContext) else None
    if proves is None or proves(context):
        return True
    log.warning(
        "issue=#%d auto-rebase recovery: holding rather than parking, since the verification evidence "
        "captured or settled for the landed head could not be retired over what moved under it",
        context.issue.number,
    )
    return False


def _releases_over_the_reset(context: _AutoRebaseContext | _AutoRebaseRecoveryContext, reset_sha: str) -> bool:
    """Drop the attempt a landed reset abandoned, and what the reset took the branch off; whether it was dropped.

    A recovery's attempt can carry a record the workflow made about the head
    the reset just took the checkout off -- a verification transaction a
    finish captured for it, which the attempt is the only thing keeping
    anyone from settling, or evidence a finish settled for it, which the reset
    moved under. The recovery's answer to it is staged first on the state the
    park writes (`_AutoRebaseRecoveryContext.settles_over_a_reset`), so it
    lands in the park's one write beside the attempt's release, or neither
    does, and a dropped attempt never leaves it behind. False where the
    recovery answers that the record cannot go with the release -- settled
    evidence the comment has no room to retire into history -- logged: the
    attempt keeps guarding it, nothing is dropped or parked, and the next
    tick's recovery asks again.
    """
    settles = context.settles_over_a_reset if isinstance(context, _AutoRebaseRecoveryContext) else None
    if settles is not None and not settles():
        log.warning(
            "issue=#%d auto-rebase recovery: the reset landed, but the verification evidence settled for the head "
            "it took the checkout off could not be retired with the attempt; keeping the attempt and holding "
            "rather than parking",
            context.issue.number,
        )
        return False
    attempts._clears_the_attempt(context.state)
    _forgets_the_reset(context, reset_sha)
    return True


def _forgets_the_reset(
    context: _AutoRebaseContext | _AutoRebaseRecoveryContext,
    reset_sha: str,
) -> None:
    """Drop what a landed reset just took the branch off, in memory.

    Both records name a commit only the reflog still has once the branch is
    back on the pre-rebase anchor: the approval says a push is owed for it,
    and a transfer's permission says what that push may carry a human's
    verdict over. Neither has anything left to be paid by, and both are staged
    rather than written so the park's own write is what makes the drop
    durable.
    """
    # Lazily bound for the reason the guard owner is: the size gate sits in
    # the workflow layer above this package, and binding it at module load
    # would make every git-side import pay for the stage tree.
    from orchestrator.workflow.stages.implementing import (
        late_approval_reading as _late_approval_reading,
        late_approval_state as _late_approval_state,
        late_records,
        late_transfer,
    )
    if _late_approval_reading._approved_commit(context.state) != reset_sha:
        _late_approval_state._forget_approval(context.state)
    late_transfer._abandoned_authorization(
        late_records._gate(
            context.gh, context.spec, context.issue, context.state,
            context.worktree,
        ),
        reset_sha,
    )
