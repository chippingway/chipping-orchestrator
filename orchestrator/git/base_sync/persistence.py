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
for the landed head is proved again before the record a human's reply brings
back is left standing.

Every park's record lands as the attempt's checkpoint
(`checkpoints._lands_the_checkpoint`). The recovery runs under the issue's writer
claim, taken before the issue and its pinned comment are read and held until
the route ends (`workflow/engine/base_refresh.py`, and the dispatcher's anchor
hold under its dispatch claim), so no other orchestrator writer moves the
comment between the tick's reading and the park, and the tick's own earlier
writes are checkpoints that reading moves on with. The record is decided on the
attempt and its evidence as that reading spells them: one refused, one whose
answer was lost, and one over an attempt or evidence record that moved without
this road all leave the comment as it stands, logged, for the next tick to read.
The tail's hard reset is decided on the same records and moves the checkout
ahead of every write, so it is made only once the comment, read afresh, still
spells them as the tick last confirmed them
(`checkpoints._still_owns_the_attempt`), and nothing is reset, cleaned, or
parked where it does not.
The finish of a rewrite that landed is the workflow's
(`workflow/engine/rewrite_finish.py`), whichever road reached it.
"""
from __future__ import annotations

import subprocess
from types import MappingProxyType

from github.Issue import Issue

from orchestrator.git import commands
from orchestrator.git.base_sync import attempts, checkpoints
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
    The record is landed here so the caller can return immediately, as the
    attempt's checkpoint (`checkpoints._lands_the_checkpoint`): over the reading
    the tick last confirmed, with everything the tick staged for the park
    riding it, and decided on the attempt and its evidence as that reading
    spells them. One that moved without this road, a write refused, and an
    answer lost are logged with nothing put back over the comment, and the
    next tick reads whether the park stands.

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
    checkpoints._lands_the_checkpoint(gh, issue, state, "recording its park")


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
    transaction a finish captured for a landed head -- so the recovery is
    asked to settle it on the same state first (`_releases_over_the_reset`):
    it rides this one write with the attempt's drop, or neither lands.

    The reset is decided on the attempt -- its anchor is what the checkout
    goes back to -- and it moves the checkout ahead of every write behind it,
    so the comment is asked first whether it still spells the attempt and its
    evidence as the tick last confirmed them (`_resets`). One that does not
    has nothing reset, cleaned, or parked: the tail goes no further, and the
    record stands as the comment carries it for the next tick to read.
    """
    reset = _resets(context, reset_sha)
    if reset is None:
        return
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
    if not reset.returncode:
        _releases_over_the_reset(context, reset_sha)
    elif not _proves_before_the_park(context):
        return
    _park_auto_rebase_failure(
        context.gh,
        context.issue,
        context.state,
        message=f"{message}\n\n{_reset_outcome(reset_sha, reset, cleaned)}",
        reason=reason,
    )


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
    captured for the landed head stands with it. So the workflow proves it
    again first (`_AutoRebaseRecoveryContext.proves_before_a_park`), and
    abandons it where anything it rests on moved, before the park and not
    behind the reply, by which time what moved may be back. False is a
    movement it read and could not record: nothing is parked, the anchor still
    holds every handler, and the next tick's recovery asks again. A refresh's
    own context, ahead of any recovery, has captured nothing to prove.
    """
    proves = context.proves_before_a_park if isinstance(context, _AutoRebaseRecoveryContext) else None
    if proves is None or proves(context):
        return True
    log.warning(
        "issue=#%d auto-rebase recovery: holding rather than parking, since the verification evidence "
        "captured for the landed head could not be retired over what moved under it",
        context.issue.number,
    )
    return False


def _releases_over_the_reset(context: _AutoRebaseContext | _AutoRebaseRecoveryContext, reset_sha: str) -> None:
    """Drop the attempt a landed reset abandoned, and what the reset took the branch off.

    A recovery's attempt can carry a record the workflow made about the head
    the reset just took the checkout off -- a verification transaction a
    finish captured for it, which the attempt is the only thing keeping
    anyone from settling. The recovery's answer to it is staged first on the
    state the park writes (`_AutoRebaseRecoveryContext.settles_over_a_reset`),
    so it lands in the park's one write beside the attempt's release, or
    neither does, and a dropped attempt never leaves it behind.

    The drop of what the reset took the branch off is staged, not written, so
    the park's own write makes it durable: the approval and a transfer's
    permission both name a commit only the reflog still has once the branch is
    back on the pre-rebase anchor -- a push owed for it, and what that push
    may carry a human's verdict over -- and neither has anything left to be
    paid by.
    """
    settles = context.settles_over_a_reset if isinstance(context, _AutoRebaseRecoveryContext) else None
    if settles is not None:
        settles()
    attempts._clears_the_attempt(context.state)
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


def _resets(
    context: _AutoRebaseContext | _AutoRebaseRecoveryContext, reset_sha: str,
) -> subprocess.CompletedProcess | None:
    """Hard-reset `context`'s checkout to `reset_sha`; git's answer, logged where it failed.

    None, with nothing reset, where the comment no longer spells the attempt
    and its evidence as the tick last confirmed them
    (`checkpoints._still_owns_the_attempt`).
    """
    if not checkpoints._still_owns_the_attempt(context.gh, context.issue, context.state, "resetting the checkout"):
        return None
    reset = commands._git_hardened("reset", "--hard", reset_sha, cwd=context.worktree)
    if reset.returncode:
        log.error(
            "issue=#%d auto-rebase recovery: reset --hard to %s failed: "
            "%s; the awaiting_human park still short-circuits same-tick "
            "handler dispatch but operator inspection of HEAD is needed",
            context.issue.number, reset_sha[:8], (reset.stderr or "").strip(),
        )
    return reset
