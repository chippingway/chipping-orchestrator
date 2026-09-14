# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Refresh and anchor a checkout whose contribution the caller has already proved.

The target-root lock covers refresh, target validation, and branch movement.
A live PR must still name the caller's expected head on the remote; only a caller
that establishes the PR is over may ask for a freshly fetched base. Creation
uses the same fetch helper when it restores a missing local branch.
"""
from __future__ import annotations

import logging

from orchestrator import config
from orchestrator.git import branch_transport, commands, locks
from orchestrator.git.worktrees import paths

log = logging.getLogger("orchestrator.worktree_lifecycle")


def _fetch_for_restore(
    spec: config.RepoSpec, issue_number: int, branch: str,
) -> bool:
    """Fetch one ref a checkout may be restored from, saying so when it fails.

    Neither of these fetches gates the restore -- the ref checks below decide --
    but a silent failure is what turns a network blip into a checkout rebuilt
    from the wrong place, so it is logged where an operator reading the tick can
    see it beside the decision it feeds.
    """
    fetch_result = branch_transport._authed_target_fetch(spec, branch)
    if fetch_result.returncode != 0:
        log.warning(
            "issue=#%d fetch of %s failed while restoring the checkout: %s",
            issue_number, branch, (fetch_result.stderr or "").strip(),
        )
    return fetch_result.returncode == 0


def _anchor_pr_worktree(
    spec: config.RepoSpec, issue_number: int, *, branch: str, head_sha: str,
) -> str | None:
    """Bring the per-issue branch, and its checkout, onto a PR's own head.

    For the one handoff where the remote is ahead of everything local for a
    reason nothing here can see: a human edited the design on the plan PR the
    `discussion` stage opened, or merged the base into that branch to make it
    mergeable, while the checkout the conversation ran in still sits on the
    commit this orchestrator published. Left there, the developer builds on a
    plan the humans have moved past, and the push that follows sends a tip that
    does not contain the head they reviewed at the branch that head is on --
    where the lease, measured against a remote ref this branch simply does not
    descend from, is the only thing between an amendment and being overwritten.

    Only for a caller that has already established the checkout is clean and
    sitting exactly where it certified. The reuse paths above must never do
    this: what they keep is unpushed local work, and a reset there would destroy
    the very commits the reuse exists to preserve.

    Returns the SHA the branch now sits at, which is what the caller records as
    the tip the work that follows starts from -- the reviewed head normally, and
    the base when that head is gone along with its branch. None means nothing
    moved and nothing could be established, and the caller must not treat the
    handoff as taken: the checkout is still on a commit the reviewers have moved
    past, and a push from it would take their work with it.

    `head_sha` is what the caller read off GitHub before this ran, so it is
    checked against the remote here rather than taken on trust. A head the
    humans pushed in between is exactly the state this exists to protect, and it
    arrives looking like success -- the fetch brings their commit, and the one
    the caller named still resolves underneath it.

    An EMPTY `head_sha` asks for the base outright, and it is how a caller says
    the pull request is over: a merged plan is in the base along with everything
    else that landed while it was open, so leaving the checkout on the commit
    that merged would start the developer behind the branch they are building
    for.
    """
    with locks._target_root_lock(spec.target_root):
        _fetch_for_restore(spec, issue_number, branch)
        target = _anchor_target(spec, issue_number, branch, head_sha)
        if target is None:
            return None
        if not _move_branch_onto(spec, issue_number, branch, target):
            return None
        return target


def _anchor_target(
    spec: config.RepoSpec, issue_number: int, branch: str, head_sha: str,
) -> str | None:
    """The commit the branch has to end up on, or None when nothing says which.

    A caller that names no head at all has said the pull request is finished,
    and the base is the answer without the remote being asked about the branch
    at all -- though the base itself still has to be brought forward before it
    can stand in for what merged.

    Otherwise the remote decides, and it is asked FIRST rather than only when
    something is missing locally. `head_sha` was read off GitHub a moment ago,
    and the humans can push to that branch in the moment between: the fetch
    above then brings their commit and leaves the reviewed one resolving
    perfectly well underneath it as an ancestor, so "the object is here" would
    anchor the branch on a head the pull request has already moved past. The
    developer would build on it, and the push that follows takes a lease read
    live off the remote -- so it matches the commit nobody here has seen and
    overwrites it. Only a remote still ON that head says the reading the caller
    made is still the reading that holds.

    A branch the remote no longer has does NOT fall back to the base once a
    head is named, and this is the difference between the two ways a pull
    request ends. The caller that knows the design landed says so by naming no
    head at all, and only that caller gets the base. A named head with the
    branch gone is a pull request somebody closed and cleaned up after -- what
    it carried went with the branch, and it is nowhere in the base -- so
    anchoring there would retire the plan records and start the developer from
    a base the plan was never in. Nothing was established, and the caller is
    told so.

    That is the same answer a branch the remote has MOVED, one it could not be
    asked about, and a head it still names that this host could not fetch all
    get: no ref may be moved on the strength of any of them, so the handoff
    waits and the next tick reads the pull request again.
    """
    if not head_sha:
        return _base_anchor(spec, issue_number, branch)
    remote_tip = branch_transport._remote_branch_tip(
        spec, spec.target_root, branch,
    )
    if remote_tip != head_sha:
        log.warning(
            "issue=#%d cannot anchor %s on %s: the remote %s",
            issue_number, branch, head_sha,
            _unanchorable_branch_reading(remote_tip),
        )
        return None
    if not _resolved_commit(spec, f"{head_sha}^{{commit}}"):
        log.warning(
            "issue=#%d cannot anchor %s on %s: the remote is still on that "
            "commit but this host could not fetch it",
            issue_number, branch, head_sha,
        )
        return None
    return head_sha


def _unanchorable_branch_reading(remote_tip: str | None) -> str:
    """Say which of the three the remote gave, since the remedy differs.

    A branch that moved is a head to re-read next tick; one the remote could
    not be asked about is a reading to take again; one it no longer has at all
    is a pull request somebody closed and deleted the branch of, which no tick
    will ever resolve on its own -- and an operator reading this is the only
    thing that can.
    """
    if remote_tip is None:
        return "could not be asked about the branch"
    if not remote_tip:
        return (
            "no longer has that branch at all, so what it carried is not in "
            "the base and there is nothing to anchor on"
        )
    return f"has moved that branch on to {remote_tip}"


def _base_anchor(
    spec: config.RepoSpec, issue_number: int, branch: str,
) -> str | None:
    """The base tip, freshly fetched, as the commit a finished PR ends on.

    Fetched here rather than trusted, and the fetch DECIDES, because this is the
    answer for a branch whose own pull request is over: what the developer
    starts from has to be the base as it stands now, not as it stood when this
    clone last looked. A remote-tracking ref outlives the fetch that wrote it,
    so one a failure left behind resolves perfectly well and names the base from
    before the merge -- which for a plan that just landed is the one base the
    plan is not in. Anchored there, the handoff retires the plan records and
    spawns the developer without the artifact its humans approved, on a checkout
    that never carried it.

    A refresh that did not run therefore establishes nothing, and the caller is
    told so rather than handed a commit: the handoff stays pending, the checkout
    stays where it is, and the next tick fetches again.
    """
    if not _fetch_for_restore(spec, issue_number, spec.base_branch):
        log.warning(
            "issue=#%d cannot anchor %s on the base: its refresh failed, so "
            "%s/%s names the base only as this clone last saw it",
            issue_number, branch, spec.remote_name, spec.base_branch,
        )
        return None
    base_ref = f"refs/remotes/{spec.remote_name}/{spec.base_branch}"
    log.info(
        "issue=#%d anchoring %s on %s: its pull request is over, so what it "
        "carried is in the base", issue_number, branch, base_ref,
    )
    return _resolved_commit(spec, base_ref) or None


def _resolved_commit(spec: config.RepoSpec, revision: str) -> str:
    """The SHA a revision names in the parent clone, or '' when it names none."""
    resolved = commands._git_hardened(
        "rev-parse", "--verify", "--quiet", revision, cwd=spec.target_root,
    )
    if resolved.returncode != 0:
        return ""
    return (resolved.stdout or "").strip()


def _move_branch_onto(
    spec: config.RepoSpec, issue_number: int, branch: str, head_sha: str,
) -> bool:
    """Move the branch to `head_sha`, taking its checkout with it.

    A checkout on disk is reset rather than the ref rewritten under it: moving
    the ref alone would leave the tree it belongs to a commit behind, so the
    difference would read as uncommitted local edits and the next probe would
    call the tree dirty. Only a branch with no worktree of its own is moved as
    a ref.

    Both go through the hardened envelope, like every other reset in this
    repository, because both run over a repository an agent has had. The
    checkout is its own writable tree, and a linked worktree can write the
    common repo it shares -- so `core.fsmonitor` on the index refresh a reset
    performs, a `reference-transaction` hook on the ref update either one makes,
    and a planted replacement object behind the SHA being moved onto are all
    reachable from here, and would otherwise run with this process's
    environment attached.

    The reset also NAMES the tree it is aimed at, because that is the one thing
    the envelope cannot override. `core.worktree` in the per-worktree config --
    which an agent enables by writing `extensions.worktreeConfig` into the repo
    its checkout shares -- points every path operation at another directory,
    and a `-c` on the command line does not win against it. Left to discovery,
    the reset reports success and moves the ref while writing the reviewed
    commit's files into whatever directory it was pointed at: the issue's
    checkout stays on the plan it had, the caller records a baseline the tree
    does not match, and somebody else's files are overwritten on the way past.
    """
    worktree = paths._worktree_path(spec, issue_number)
    if worktree.exists():
        moved = commands._git_hardened(
            commands._work_tree_arg(worktree),
            "reset", "--hard", head_sha, cwd=worktree,
        )
    else:
        moved = commands._git_hardened(
            "update-ref", f"refs/heads/{branch}", head_sha,
            cwd=spec.target_root,
        )
    if moved.returncode != 0:
        log.warning(
            "issue=#%d could not put %s on %s: %s",
            issue_number, branch, head_sha, (moved.stderr or "").strip(),
        )
        return False
    log.info(
        "issue=#%d anchored %s on the reviewed head %s",
        issue_number, branch, head_sha,
    )
    return True

