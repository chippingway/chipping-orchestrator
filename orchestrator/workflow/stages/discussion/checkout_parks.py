# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The endings that report on the per-issue checkout rather than on a plan.

What every park here has in common is that the tree is the subject: it holds
work nothing may run over, or it would not answer at all. None of them touches
the round anchor, because a commit is precisely when that number has to
survive -- it is the only recorded point that separates what an agent wrote
from what the branch already carried, so it is both the reset target these
parks quote and what the implementing relabel guard measures the branch
against once the operator has reset.

The two dirty parks are distinct on purpose even though both quote the same
bounded path list. One is the agent leaving work loose where the only thing it
may write is a committed plan; the other is a checkout that arrived already
holding work, which no agent of this tick touched -- and the operator's next
move differs, so the reason has to say which happened rather than leaving them
to guess from the tree. A checkout `git status` could not report on at all is a
third answer to the same question and carries its own reason for the same
reason: an empty path list is what a clean tree gives, so an operator reading
the dirty one would go looking for changes that were never named.
"""
from __future__ import annotations

from orchestrator import config
from orchestrator.git.verification import status as _worktree_status
from orchestrator.workflow.stages.discussion import (
    models as _models,
    park_messages as _park_messages,
    parks as _parks,
    state as _state,
)


def _park_dirty_discussion(
    run: _models._DiscussionRun, dirty_files: tuple[str, ...],
) -> None:
    _parks._park_discussion(
        run,
        f"{config.HITL_MENTIONS} discussion agent left "
        f"{len(dirty_files)} uncommitted change(s), but the only thing this "
        "stage publishes is the agreed plan, committed on its own. Reset the "
        "worktree before resuming."
        f"\n\n{_park_messages._paths_markdown(dirty_files)}",
        reason=_state._DISCUSSION_DIRTY,
    )


def _park_stranded_worktree(
    run: _models._DiscussionRun, stranded: _worktree_status._WorktreeStatus,
) -> None:
    """Park on a checkout no round may open over, instead of recreating it.

    Preparing the checkout would force-remove a dirty tree that carries no
    commits, so this park runs INSTEAD of the round: the changes an earlier
    round died holding are the only record of what it was doing, and an
    operator has to see them before anything overwrites them.

    A checkout that could not be read lands here for the sharper version of
    the same reason, under its own reason code -- either probe failing is that
    answer, since a `git status` that could not run and a `HEAD` that would not
    resolve leave the same nothing behind. The destructive step behind this
    question does not wait to be told twice, so recreating on a probe that
    never answered would delete the very tree an operator needs to look at to
    find out why it failed. There is no path list to quote and no tip to reset
    to, which is exactly what the message has to say instead.
    """
    if not stranded.readable:
        _parks._park_discussion(
            run,
            f"{config.HITL_MENTIONS} the per-issue worktree could not be read "
            "(`git status` or `HEAD` failed), so nothing here can show it is "
            "empty or say where it is -- and opening a discussion round would "
            "recreate the checkout over whatever is in it. No agent was "
            "spawned and the tree was left exactly as it is. Inspect it (a "
            "corrupt index or a half-removed directory reads this way) and "
            "repair or remove it before this issue is picked up again.",
            reason=_state._DISCUSSION_UNREADABLE,
        )
        return
    _parks._park_discussion(
        run,
        f"{config.HITL_MENTIONS} the per-issue worktree already holds "
        f"{len(stranded.paths)} uncommitted change(s) from an earlier run that "
        "did not finish. Opening a discussion round would recreate the "
        "checkout and destroy them, so no agent was spawned. Inspect the "
        "worktree and reset it before this issue is picked up again."
        f"\n\n{_park_messages._paths_markdown(stranded.paths)}",
        reason=_state._DISCUSSION_STRANDED,
    )


def _park_unreadable_round(run: _models._DiscussionRun) -> None:
    """Report a finished round whose checkout will not say what it did.

    `HEAD` is one end of every comparison this stage classifies a round by, and
    a read that failed makes all of them unanswerable at once: whether the
    agent committed, whether what it committed is the plan, and whether the
    tree beside it is clean. The one thing that must not follow is a
    publication, because empty compares unequal to the SHA the round opened on
    -- so the "yes, it committed" answer is exactly the one a failed read
    produces, and the commit the branch already carried would go out under this
    round's session.

    Nothing is reset and nothing is recreated: what the round did is still in
    the tree, and the tree is what an operator has to look at to find out why
    git could not be asked about it.
    """
    _parks._park_discussion(
        run,
        f"{config.HITL_MENTIONS} the discussion round finished, but `HEAD` "
        "could not be read in the per-issue worktree afterwards -- so nothing "
        "here can say whether it committed, and nothing was published or "
        "recorded on the strength of a reading that did not happen. The "
        "worktree was left exactly as the round left it. Inspect it (a corrupt "
        "index or a half-removed directory reads this way) and repair or "
        "remove it before this issue is picked up again.",
        reason=_state._DISCUSSION_UNREADABLE,
    )


def _park_foreign_commit(run: _models._DiscussionRun) -> None:
    """Report a commit on the branch that no round of this stage made.

    The counterpart to the recovered-commit park `publication_parks` owns, and
    the difference is who wrote what is there. That one names a plan a round of
    this stage left unreported; this one is for a tip that moved while no round
    was in flight -- another stage's agent under its own park, or a hand-made
    commit on the branch -- so nothing here can say what it is, and it is
    certainly not a design this conversation agreed to. That is why it reports
    the tree rather than reading the artifact: there is no publication to
    refuse, only a checkout nobody may open a round on.

    It runs INSTEAD of a round for the same reason every commit park does: the
    checkout would be recreated over it. And it says so on the thread, because
    an issue whose stage has quietly stopped opening rounds looks exactly like
    one waiting for an answer.
    """
    _parks._park_discussion(
        run,
        f"{config.HITL_MENTIONS} the per-issue worktree carries commits made "
        "since the last discussion round opened, and no round of this stage "
        "was running when they appeared -- so they are not a design agreed on "
        "this thread, and nothing was published. No agent was spawned and "
        f"nothing was overwritten. {_park_messages._reset_target(run)}",
        reason=_state._DISCUSSION_COMMITS,
    )


def _park_blocked_resume(
    run: _models._DiscussionRun, stranded: _worktree_status._WorktreeStatus,
) -> None:
    """Report a reply that cannot be answered until the checkout is restored.

    A park this stage wrote earlier said "reset the worktree"; this one is for
    the case where none did -- the last round ended cleanly, and the tree was
    dirtied or committed to afterwards. Without it a human who answers the
    frontier gets silence, since the guard that refuses to open a round on such
    a tree has nothing on the thread to point them at.

    The reason it lands under is one of the three the operator's next move
    differs between, chosen by which probe found the violation, so the pinned
    record still says whether there are commits to reset off, edits to clean,
    or a checkout that could not be read at all. That last one comes with no
    reset target on purpose: the read that would have named one is the thing
    that failed, and quoting the anchor would tell an operator to run a command
    over a tree nobody has established anything about. All of them are why this
    park is written once: the reason it leaves IS a repair request, so the tick
    after it holds quietly rather than repeating itself. The reply is left
    unconsumed either way, so answering it again is not something the human has
    to think to do.

    A commit that IS the agreed plan never reaches here: the reply publishes it
    instead, which is what keeps a tick that died between opening the plan PR
    and recording it from telling an operator to reset away the commit that PR
    is open against.
    """
    if not stranded.readable:
        _parks._park_discussion(
            run,
            f"{config.HITL_MENTIONS} your reply is noted, but the per-issue "
            "worktree could not be read (`git status` or `HEAD` failed), so "
            "nothing here can show it is still the checkout this discussion "
            "was left on. No round was opened on it and nothing was "
            "overwritten. Inspect it (a corrupt index or a half-removed "
            "directory reads this way) and repair or remove it; your reply "
            "stays unread until then, and the discussion continues from it on "
            "its own once the tree reads again.",
            reason=_state._DISCUSSION_UNREADABLE,
        )
        return
    if stranded.paths:
        found = f"it is holding {len(stranded.paths)} uncommitted change(s)"
        reason = _state._DISCUSSION_DIRTY
        listing = f"\n\n{_park_messages._paths_markdown(stranded.paths)}"
    else:
        found = "it carries commits made since that round opened"
        reason = _state._DISCUSSION_COMMITS
        listing = ""
    _parks._park_discussion(
        run,
        f"{config.HITL_MENTIONS} your reply is noted, but the per-issue "
        "worktree is no longer the checkout this discussion was left on "
        f"({found}), so no round was opened on it and nothing was overwritten."
        f" {_park_messages._reset_target(run)} Your reply stays unread until "
        f"then, and the discussion continues from it on its own once the tree "
        f"is back.{listing}",
        reason=reason,
    )
