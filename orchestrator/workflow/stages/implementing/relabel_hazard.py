# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What a relabeled issue is carrying that no conversation stage vouched for.

Which way a relabel out of `question` or `discussion` goes is decided by the
worktree and the branch, never by the park reason alone. A misbehaving run can
park having committed or dirtied the per-issue branch, and dropping the park
would let the fresh-spawn path's recovered-worktree shortcut push that work as
a dev implementation. The branch is checked even when the worktree is gone,
because a safe teardown (or an operator) can remove the directory while the
local branch survives carrying those commits -- `_ensure_worktree` would
restore it and the shortcut would ship them.

The checkout is read for its own HEAD for the mirror-image reason. A commit does
not have to be on a branch anybody here names: an agent that committed while
detached leaves every ref where it was and the plan sitting in the tree, which
is exactly what the creators keep and the shortcut pushes. So the branch reads
answer for the refs and the HEAD read answers for the checkout, and an
unreadable HEAD counts against it -- proving a tree carries nothing cannot rest
on a probe that did not run.

Whether a tip either read finds is one anybody here vouched for is
`relabel_evidence`'s question. What is assembled here is the finding: every
reading that convicts, reported together, because an operator fixing what the
refusal names wants all of it the first time.
"""
from __future__ import annotations

from dataclasses import dataclass

from github.Issue import Issue

from orchestrator import config
from orchestrator.git.verification import probes as _verification_probes, status as _worktree_status
from orchestrator.git.worktrees import (
    naming as _naming,
    paths as _worktree_paths,
    recovery as _worktree_recovery,
)
from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.stages.discussion.state import (
    _PUBLISHING_SHA,
    _ROUND_BRANCH,
    _ROUND_SHA,
)
from orchestrator.workflow.stages.implementing import (
    relabel_evidence as _evidence,
)
from orchestrator.workflow.stages.implementing.plan_reading import _ReviewedPlan


@dataclass(frozen=True)
class _ReadOnlyRelabelHazard:
    branch: str
    trigger: str


def _uncertified_commits(
    spec: config.RepoSpec,
    issue: Issue,
    state: PinnedState,
    reviewed: _ReviewedPlan,
) -> str | None:
    """The per-issue branch carrying commits the conversation stage did not vouch for.

    Ahead-of-base is the question wherever the discussion stage recorded no
    anchor, because for those parks a branch ahead of base is exactly the
    violation.

    Where an anchor exists it is asked FIRST and on its own terms, because
    ahead-of-base cannot stand in for it in either direction. A branch reset
    all the way to base is no longer ahead of base, yet on a PR-backed issue
    that reset threw away the commits the round was certified against -- so
    the cheap answer would clear a `discussion_commits` park whose violation
    nobody resolved. The recorded ref is therefore compared to what
    `relabel_evidence` vouches for whatever its relation to base is.

    A recorded ref that no longer exists is not a mismatch: there is nothing
    local left to attribute, and a PR-backed checkout is rebuilt from the PR
    head, which never carried this stage's work. That is the same reading
    `_branch_tip_sha` gives its other caller. Commits on any OTHER candidate
    branch still convict, so a round that committed on the sibling ref of a
    legacy-pinned branch is not let through by its anchor.
    """
    unpushed = _worktree_recovery._branch_has_unpushed_commits(spec, issue.number)
    round_branch = state.get(_ROUND_BRANCH)
    round_sha = state.get(_ROUND_SHA)
    if not round_sha or not round_branch:
        return unpushed
    anchored = str(round_branch)
    tip = _worktree_recovery._branch_tip_sha(spec, anchored)
    if tip and _evidence._tip_is_uncertified(
        state, reviewed, tip, unpushed == anchored,
    ):
        return anchored
    if unpushed is None or unpushed == anchored:
        return None
    return unpushed


def _read_only_relabel_hazard(
    spec: config.RepoSpec,
    issue: Issue,
    state: PinnedState,
    reviewed: _ReviewedPlan,
) -> _ReadOnlyRelabelHazard | None:
    unpushed = _uncertified_commits(spec, issue, state, reviewed)
    triggers = _unfinished_publication_triggers(state) + _checkout_triggers(
        spec, issue.number, state, reviewed,
    )
    if unpushed:
        triggers += (
            f"unreviewed commits on the per-issue branch `{unpushed}`",
        )
    if not triggers:
        return None
    branch = unpushed or _naming._resolve_branch_name(
        state, spec, issue.number,
    )
    return _ReadOnlyRelabelHazard(
        branch=branch, trigger=" AND ".join(triggers),
    )


def _unfinished_publication_triggers(state: PinnedState) -> tuple[str, ...]:
    """The publication this stage began and never finished, if there is one.

    Refused on the record alone, because the record is the only thing that
    survives every way this can look locally. The marker is written before the
    push, so by the time a tick dies past it the branch may be on the remote
    with a pull request open against it -- and nothing here can say whether it
    is. A checkout that is gone reads as clean, a local ref that never existed
    reads as nothing to attribute, and a branch an operator reset reads as
    certified: on a fresh clone all three are true at once, and the guard would
    hand the whole thing over having proved nothing.

    What follows such a handover is the sharpest version of what this guard
    exists to stop. The developer builds from base, the publication that opens
    the PR is gone, and the push takes a lease read live off the remote -- so it
    force-pushes over the published plan, adopts the pull request already open
    on that branch, and rewrites its body to close the issue on merge.

    The way out is not a reset: it is the label that owns the unfinished half.
    The `discussion` stage's own recovery restores the checkout from the PR
    head, adopts the PR that is already open, and records it -- and only once
    that has happened (or the operator has reset the marker away there) is
    there anything here to hand over.
    """
    in_flight = state.get(_PUBLISHING_SHA)
    if not in_flight:
        return ()
    handover = (
        f"`{in_flight}` mid-publication -- possibly already pushed, with a "
        "pull request open against it"
    )
    return (handover,)


def _checkout_triggers(
    spec: config.RepoSpec,
    issue_number: int,
    state: PinnedState,
    reviewed: _ReviewedPlan,
) -> tuple[str, ...]:
    """What the retained checkout itself is carrying, if anything.

    The branch reads answer for named refs, and a checkout does not have to be
    on one. An agent that committed while detached -- or onto a ref nothing
    here looks at -- leaves `refs/heads/<branch>` sitting exactly where the
    round opened it while the tree in front of the developer is its commit. The
    creators keep such a checkout as it stands, and the recovered-work shortcut
    pushes whatever `HEAD` is, so the tip this guard has to prove is the
    checkout's own and not just its branch's.

    An unreadable HEAD is a finding of the same kind, and so is a tree `git
    status` could not report on -- the list form of that read maps its own
    failure to "no paths", which is the answer a clean tree gives. Neither is a
    clean checkout; both are probes that never answered, and a guard whose whole
    job is to PROVE the tree carries nothing this stage wrote may not rest on
    one. What follows an unproven clean reading is the destructive half: the
    creators force-remove a checkout with nothing unpushed on it, so the tree an
    operator was parked to look at would be gone before anyone read it.

    Both readings are reported, and so is a dirty tree beside them, because an
    operator fixing what the refusal names wants all of it the first time.
    """
    worktree = _worktree_paths._worktree_path(spec, issue_number)
    if not worktree.exists():
        return ()
    triggers: list[str] = []
    head = _verification_probes._head_sha(worktree)
    if not head:
        triggers.append("a per-issue worktree whose HEAD could not be read")
    elif not _evidence._checkout_certified(
        spec, worktree, head, state, reviewed,
    ):
        triggers.append(f"a per-issue worktree sitting on `{head}`")
    tree_status = _worktree_status._worktree_status(worktree)
    if not tree_status.readable:
        triggers.append(
            "a per-issue worktree whose state could not be read "
            "(`git status` failed)",
        )
    elif tree_status.paths:
        triggers.append("dirty edits in the per-issue worktree")
    return tuple(triggers)
