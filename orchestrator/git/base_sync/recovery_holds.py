# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Hold, and answer, an auto-rebase anchor the ordinary recovery cannot reach.

That road starts from a head it can read, over a checkout the refresh walked.
A checkout whose base lag cannot be counted names a commit nothing here can
read, so the refresh takes the fail-closed abort over it directly. And a tick
the refresh never reached leaves the anchor for the dispatcher, which asks
here whether that holds the stage handler back and what a held tick is owed:
a missing checkout restored where the refresh drives the label, and the
refresh's own ineligible answer where it does not.

The hold reads the refusals it releases for off their own owners -- the
hard-skip off `refresh_selection`, the late claims off `frozen` -- so it and
the walk it waits on cannot come to disagree about either.
"""
from __future__ import annotations

from pathlib import Path

from github.Issue import Issue

from orchestrator.git.base_sync import (
    attempt_records as _attempt_records,
    frozen as _frozen,
    refresh_selection as _refresh_selection,
    replay_cleanup as _replay_cleanup,
    replay_publication_parks as _replay_publication_parks,
    snapshot,
)
from orchestrator.git.base_sync.models import (
    _AutoRebaseContext,
    _AutoRebaseRecoveryContext,
)
from orchestrator.git.base_sync.state import (
    _AUTO_REBASE_PARK_REASONS,
    _AWAITING_HUMAN,
    _PARK_REASON,
    _PENDING_PUSH_SHA,
    _PR_REFRESH_DETOUR_LABELS,
    log,
)
from orchestrator.git.verification import probes as _probes
from orchestrator.git.worktrees import (
    creation as _worktree_creation,
    naming as _worktree_naming,
    paths as _worktree_paths,
)
from orchestrator.github.pinned_state import PinnedState

# Why a checkout the base lag could not even be counted over is not one a
# recovery may read, in the terms the abort's own notice is built around.
_UNREADABLE_CHECKOUT = (
    "the checkout's HEAD could not be compared against the base branch -- the "
    "commit it names is missing or unreadable in this worktree -- so nothing "
    "the interrupted rebase left behind could be read back and verified."
)


def _recovery_holds_dispatch(
    issue: Issue,
    label: str | None,
    state: PinnedState,
    worktree: Path,
) -> bool:
    """Whether an unfinished auto-rebase attempt holds this issue's handler.

    The anchor is the refresh's to answer, and the refresh answers it ahead of
    every handler -- but only on a tick that REACHES it. A base fetch that
    failed, a pull request that would not read, an issue that would not fetch:
    each returns before the recovery runs and leaves the anchor exactly where
    it was. The handler behind the dispatcher then runs over a checkout
    standing on a replay no push has published -- a reviewer spawned on
    `validating`, a developer resumed on `fixing`, a decomposer spawned over a
    measured generation -- which is precisely the agent an interrupted rebase
    must not cost. So the dispatcher defers while the anchor stands.

    Every label the refresh does NOT drive is held, whatever else stands: a
    read-only conversation stage, a decided commit, and a generation an
    adjudication is still deciding included. What the refresh would answer
    there reads no pull request and fetches nothing, so the dispatcher takes
    that road itself rather than waiting on a walk that may never come -- a
    clear, or the stranded park, and over a checkout that is not on disk the
    park -- and there is nothing for a release to wait out.

    On a label the refresh DOES drive, one shape is released, because it is
    ended by an owner ahead of every stage handler and a hold over it would
    never end: a late claim the dispatcher's own reconciliation answers -- a
    frozen pair, an approved push -- which freezes the refresh out, sits
    behind this question, and asks it again once it has run. Every other
    record or park the refresh freezes on is a handler's to end and holds, a
    park some stage left included: its handler takes it down on a reply and
    runs straight on into the agent the park was holding back, so the refresh
    answers the anchor under it instead, with the recovery alone. A checkout
    that is not on disk is held and restored for the next refresh to walk,
    and one whose HEAD names a commit nothing can read is held until the
    refresh has answered it with its reset and park.

    An operator's hard-skip releases on every label, since no handler runs
    under one. Asked of the label the dispatcher resolved rather than read
    again, so the handler this holds back and the stage this reads are one.
    """
    if not state.get(_PENDING_PUSH_SHA) or _refresh_selection._hard_skipped(
        issue, int(issue.number),
    ):
        return False
    if label not in _PR_REFRESH_DETOUR_LABELS:
        return True
    if _frozen._late_claims(state):
        return False
    if not worktree.is_dir():
        return True
    return _refresh_reaches(worktree, int(issue.number), state)


def _refresh_reaches(
    worktree: Path, issue_number: int, state: PinnedState,
) -> bool:
    """Whether the hold waits on the refresh for a checkout that is on disk.

    Asked last, because it is the only question in the hold that costs git.

    A HEAD that reads as a commit this store holds is the ordinary case, and
    it waits. So does one that does not, until the refresh has ANSWERED it:
    the base lag over such a checkout cannot be counted, and the refresh takes
    that as its cue to reset and park -- but a refresh that never reached the
    checkout, its base fetch having failed, has answered nothing, and a
    handler let through then would run over an anchor no road has read. Only
    the park that answer writes releases the hold, since past it the reply
    that retries is the refresh's own and every stage handler stands down on
    it anyway.

    The HEAD is proved to be a commit rather than read as a name, because a
    ref pointed at an object this store does not hold still names one -- and
    it is exactly that checkout whose lag the refresh cannot count.
    """
    head = _probes._head_sha(worktree)
    if head and _probes._commit_present(worktree, head):
        return True
    if state.get(_AWAITING_HUMAN) and (
        state.get(_PARK_REASON) in _AUTO_REBASE_PARK_REASONS
    ):
        return False
    log.warning(
        "issue=#%d carries an auto-rebase anchor over a checkout at %s whose "
        "HEAD %r is not a commit this store can read, and no refresh has "
        "parked it yet; holding its handler for the refresh to answer",
        issue_number, worktree, head,
    )
    return True


def _answers_an_unreadable_checkout(
    context: _AutoRebaseContext, consumed_comment_id: int | None,
) -> bool:
    """Reset and park an anchor over a checkout whose HEAD cannot be read.

    The one state no recovery road can classify, because every one of them
    starts from a head it can read. The refresh counts the lag before any of
    them runs, and a count that fails over a pinned anchor is a checkout
    naming a commit this store does not hold -- a half-arrived fetch, a store
    pruned under a crashed tick, a ref somebody pointed at nothing. Left
    alone, the anchor stands for good: the refresh stops before the recovery
    every tick, and the dispatcher defers to a recovery that never comes.

    So it takes the fail-closed abort every unverifiable reading takes: the
    branch goes back onto the anchor, which is the head the pull request
    carries, and a human is asked. Records follow the reset rather than the
    intent -- a reset git refuses drops none of them, so the tick after a
    repair still has the anchor to come back with.
    """
    return snapshot._abort_recovery_unverified(
        _AutoRebaseRecoveryContext(
            gh=context.gh,
            spec=context.spec,
            issue=context.issue,
            state=context.state,
            worktree=context.worktree,
            pr_number=context.pr_number,
            label=context.label,
            pending_pre_rebase_sha=str(context.pending_pre_rebase_sha),
            pending_rewrite=_attempt_records._pending_rewrite(context.state),
            unparking_consumed_max=consumed_comment_id,
        ),
        _UNREADABLE_CHECKOUT,
    )


def _answers_a_held_anchor(gh, spec, issue, state, label) -> None:
    """What an anchor the dispatcher holds a handler back for is owed.

    Where the refresh drives the label, the refresh is what answers it, and
    the one thing it can be missing is a checkout to walk: only the checkouts
    that exist are walked, so one that is not on disk is brought back and
    nothing else, and the next refresh classifies the anchor over whatever the
    local branch still names.

    Where it does not, what the refresh would answer is the ineligible road,
    which reads no pull request and fetches nothing -- so it is taken here
    rather than left for a walk that may never come: a failed base fetch
    returns before any, and a read-only stage or a decided commit is skipped
    without one. Over a checkout on disk it is that road exactly, a clear or
    the stranded park. With no checkout there is no head to read, which that
    road parks on too. The park is taken once, with every record kept: a
    human who puts the label back and replies sends the issue down the
    recovery, and one who reconciles the record by hand ends the hold with it.
    """
    worktree = _worktree_paths._worktree_path(spec, issue.number)
    if label in _PR_REFRESH_DETOUR_LABELS:
        if not worktree.is_dir():
            _restores_the_checkout(spec, issue.number, state)
        return
    context = _AutoRebaseRecoveryContext(
        gh=gh,
        spec=spec,
        issue=issue,
        state=state,
        worktree=worktree,
        pr_number=int(state.get("pr_number") or 0),
        label=str(label or ""),
        pending_pre_rebase_sha=str(state.get(_PENDING_PUSH_SHA)),
        pending_rewrite=_attempt_records._pending_rewrite(state),
    )
    if worktree.is_dir():
        _replay_cleanup._answers_an_ineligible_label(context)
    else:
        _replay_publication_parks._park_stranded_recovery(context)


def _restores_the_checkout(spec, issue_number: int, state) -> None:
    """Bring back the checkout an unanswered anchor names, and nothing else.

    The stage handler that would recreate it rebuilds it onto whatever the
    local branch still names, which for an interrupted rebase is the
    unpublished replay, and then hands that to an agent. Restored here
    instead, nothing runs behind the restore: the tick stays held, and the
    next refresh walks the checkout and classifies the anchor over it.

    Restored from the pull request's own branch, the way every other checkout
    onto a publication is, so a local ref that survived the checkout is what
    comes back and a missing one is rebuilt from the remote. A restore that
    fails is logged rather than raised: the dispatcher still holds the tick,
    and the next one tries again.
    """
    try:
        _worktree_creation._ensure_pr_worktree(
            spec, issue_number,
            branch=_worktree_naming._resolve_branch_name(
                state, spec, issue_number,
            ),
        )
    except Exception:  # noqa: BLE001 - a checkout that will not restore stays held and is retried next tick
        log.exception(
            "issue=#%d could not restore the checkout its auto-rebase anchor "
            "names; the dispatcher still holds its handler and retries next "
            "tick",
            issue_number,
        )
