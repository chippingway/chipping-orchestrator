# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The reads an artifact has to survive before it can be reclaimed.

Nine questions: whether a checkout is carrying anything loose, whether it is
hiding anything besides, whether it is the checkout this issue's own creator
made, whether anything has touched it lately, what its branch is on, what its
HEAD is on, which branches some tree of the clone is standing on, what the
remote says a branch is at, and whether the base the remote named already
contains a given tip. What the answers are spent on is ``eligibility``'s and
``maintenance``'s subject; what they ARE is this module's.

Loose and hidden are two questions because git treats them as two. Untracked
and modified paths are what it calls dirty and what `worktree remove` refuses
over; a path the ignore rules hide is neither, so a tree carrying nothing else
reports clean and comes down without a word. What is under those rules is
still somebody's -- an `.env`, a key, a build root somebody is mid-way through
-- and a caller whose next move is deleting the directory has to be told about
it even though a caller about to publish would rightly pass it over.

A checkout's HEAD is asked about beside the branches because it is a tip in
its own right. A linked worktree keeps a HEAD and a reflog no branch has to
back, so a branch deleted out from under one leaves the checkout holding a
commit nothing else names -- and a reclaim that only ever asked about branches
would take it.

The two questions about the remote are put to the remote. A
`refs/remotes/<remote>/<branch>` looks like the remote's answer and is a local
ref in the object store every per-issue worktree shares, so an agent that
repoints `refs/remotes/<remote>/<base>` at its own tip makes an unpublished
branch read as already merged -- and a reclaim measuring against it would
delete the only copy of that work. `branch_transport._remote_branch_tip` asks
over the authenticated transport instead, which is the one answer nothing on
this host can rewrite. It is a read on both sides, so a verdict still leaves
no state behind it anywhere.

Every local read is hardened, for the reason every read of these paths is: the
per-issue checkout is a tree an agent writes in and it shares a clone with
the repository these probes run in, so a planted `core.hooksPath`,
`core.fsmonitor`, or replacement object runs on an ordinary `rev-parse` too.
The clone-side reads take the lock the worktree mutations serialize under, so
a reading cannot land between a `worktree add` and the ref it creates; the
checkout-side ones do not, because what they inspect is one tree rather than
the ref store everybody shares.

Every read is also tri-state, and that is the whole point of the module. The
caller's next step is deleting a branch and a directory, so "this artifact
carries nothing" and "nobody could say what this artifact carries" must not
arrive as one answer -- the first is what reclaims, and a failed read wearing
its clothes is how a probe that never ran becomes the reason work was thrown
away.
"""
from __future__ import annotations

import logging
import subprocess
from collections.abc import Iterable
from pathlib import Path

from orchestrator import config
from orchestrator.git import branch_transport, commands, locks
from orchestrator.git.verification import status as _worktree_status
from orchestrator.git.worktrees import naming as _naming, probes
from orchestrator.git.worktrees.models import BranchTip, ProbeAnswer

# The channel is named for the worktree-lifecycle domain rather than for this
# module's path: operators filter the rendered `orchestrator.worktree_lifecycle`
# prefix and attach handlers to it, so a read that could not be taken reports
# where their filters already point.
log = logging.getLogger("orchestrator.worktree_lifecycle")

# The exit status git answers a question with when the answer is no, as
# opposed to the ones that mean it could not answer at all. `rev-parse
# --verify --quiet` and `merge-base --is-ancestor` both spell their negative
# this way, and both spell an unreadable repository 128.
_GIT_NEGATIVE = 1

_LOCAL_REF_PREFIX = "refs/heads/"

# What every tip read asks for: the object id, or silence and an exit status
# that says which kind of no this is. Without `--quiet` a ref that does not
# resolve is a complaint on stderr and exit 128, which is the status a
# repository that would not open answers with -- and the two must not arrive
# as one.
_VERIFY_QUIETLY = ("--verify", "--quiet")

_HEAD = "HEAD"

# The two files a checkout's own git directory carries that git writes when
# somebody works in that tree: the index every `add`, `commit`, and refreshed
# `status` rewrites, and the reflog every move of its HEAD appends to.
_INDEX = "index"

_HEAD_REFLOG = "logs/HEAD"

# How `worktree list --porcelain` spells the branch a worktree is on. A
# detached one carries no such line at all.
_WORKTREE_BRANCH = "branch "

# The line that opens each worktree's record in the same listing, and the
# directory inside a clone's git directory holding one entry per linked
# worktree. The two are counted against each other, because the listing drops
# an entry whose backlink is missing and says nothing about having done so.
_WORKTREE_RECORD = "worktree "

_WORKTREE_ADMIN = "worktrees"


def _hardened_read(
    root: Path, *args: str,
) -> subprocess.CompletedProcess | None:
    """Run one hardened read in `root`, or report that it never ran.

    `None` is the reading that did not happen -- a git that could not be
    spawned, a `root` the host will not run a process in -- as against the
    non-zero result a caller reads off a command that did. Both fail closed
    downstream, but only one of them says anything about the artifact, so
    they are not folded together here.
    """
    try:
        return commands._git_hardened(*args, cwd=root)
    except OSError as spawn_error:
        log.warning("could not run a git read in %s: %s", root, spawn_error)
        return None


def _clone_read(
    spec: config.RepoSpec, *args: str,
) -> subprocess.CompletedProcess | None:
    """The same read against the clone, under the lock its refs move behind.

    Every mutation of this clone's worktrees and branches serializes on that
    lock, so a ref read taken outside it can land between a `worktree add`
    and the branch it creates -- and answer that a branch this orchestrator
    is in the middle of publishing does not exist. The lock is re-entrant, so
    a caller already holding it pays nothing for asking again.
    """
    with locks._target_root_lock(spec.target_root):
        return _hardened_read(spec.target_root, *args)


def _resolved_tip(
    resolved: subprocess.CompletedProcess | None, subject: str,
) -> BranchTip:
    """What one `rev-parse --verify --quiet` established, in three answers.

    `--verify --quiet` is what makes them separable: git exits 0 with the
    object id on stdout, 1 with nothing when what was named does not resolve,
    and 128 when the repository itself would not answer. A caller that only
    tested for a non-zero exit would read the last as the second and reclaim
    an artifact on the strength of a repository it could not open.

    Every caller here names a ref in full or names `HEAD`, so a branch named
    like an option cannot be read as one and a branch sharing a tag's name
    cannot be resolved to the tag instead. An exit of 0 with nothing on stdout
    is not a reading either -- nothing here produces it, which is exactly why
    it is answered as the failure it would be.
    """
    if resolved is None:
        return BranchTip(answer=ProbeAnswer.UNREADABLE)
    if resolved.returncode == _GIT_NEGATIVE:
        return BranchTip(answer=ProbeAnswer.REFUTED)
    tip_sha = (resolved.stdout or "").strip()
    if resolved.returncode != 0 or not tip_sha:
        log.debug(
            "could not resolve %s: %s",
            subject, (resolved.stderr or "").strip(),
        )
        return BranchTip(answer=ProbeAnswer.UNREADABLE)
    return BranchTip(answer=ProbeAnswer.CONFIRMED, sha=tip_sha)


def _local_branch_tip(spec: config.RepoSpec, branch: str) -> BranchTip:
    """The commit one local branch in this clone stands on.

    The commit rather than a count of what the branch is ahead by, because
    everything the caller asks next is asked about an object id: whether the
    base contains it, whether the remote is standing on it, whether a pull
    request was made of it. A count answers none of those and cannot be
    compared against anything a pull request reports.

    `REFUTED` is the branch not being there. The scan named it a moment
    earlier, so between the two reads it was deleted -- by a human, by
    another tick's teardown -- which leaves nothing to reclaim rather than
    something to protect.
    """
    ref = f"{_LOCAL_REF_PREFIX}{branch}"
    return _resolved_tip(
        _clone_read(spec, "rev-parse", *_VERIFY_QUIETLY, ref),
        f"{ref} in {spec.target_root}",
    )


def _checkout_tip(worktree: Path) -> BranchTip:
    """The commit this checkout's HEAD stands on.

    What removing the checkout would take with it. A linked worktree keeps a
    HEAD and a reflog of its own, and when no ref points at the commit HEAD
    names -- a branch deleted out from under a live checkout, which git
    permits through `update-ref` -- those two are the only things keeping that
    commit reachable. The removal takes both.

    `REFUTED` is a HEAD that names no commit, which is that exact state: the
    symbolic ref is still there and still spells this issue's branch, so every
    reading of WHOSE checkout it is comes back the same, and only resolving it
    says that what it holds cannot be named. `UNREADABLE` is the read that
    could not say either way. Both leave a caller nothing to prove the commit
    with, which is not the same as proving there is nothing to lose.
    """
    return _resolved_tip(
        _hardened_read(worktree, "rev-parse", *_VERIFY_QUIETLY, _HEAD),
        f"HEAD in {worktree}",
    )


def _published_tip(spec: config.RepoSpec, branch: str) -> BranchTip:
    """What the REMOTE says one branch is at, ignoring every local ref.

    The evidence a reclaim is entitled to lean on, and the reason it is not
    read off `refs/remotes/<remote>/<branch>`: that ref is local, it lives in
    the object store every per-issue worktree shares, and an agent can point
    it wherever it likes. Asked of the mirror, a branch that was never pushed
    anywhere reads as one the remote agrees with, and a base repointed onto an
    agent's own tip reads as a base that carries its work.

    Its three answers are the transport's own, mapped: `None` is a read that
    established nothing -- no token, a repository whose config could hijack
    the transport, an unreachable remote -- and the empty string is the remote
    answering that it does not carry this branch. That second one is the
    ordinary terminal shape rather than a problem: a merged pull request's
    head branch is deleted there.

    The clone is named as the tree the read runs in, so the transport-config
    refusal in front of it inspects the repository this classification is
    about rather than a per-issue checkout that may already be gone.

    The transport answers with `None` for the failures it recognizes and
    raises for the ones underneath them -- a git that cannot be spawned, a
    clone that has been removed since the scan named it, an askpass script
    the host would not let this process write. Those are the same answer to
    this caller, and the boundary is here rather than left to the caller
    because a probe whose contract is three answers must not have a fourth:
    an exception out of a classification takes down every other candidate in
    the pass along with this one.
    """
    try:
        published = branch_transport._remote_branch_tip(
            spec, spec.target_root, branch,
        )
    except Exception:
        log.warning(
            "could not ask the remote what %r is at from %s",
            branch, spec.target_root, exc_info=True,
        )
        return BranchTip(answer=ProbeAnswer.UNREADABLE)
    if published is None:
        return BranchTip(answer=ProbeAnswer.UNREADABLE)
    if not published:
        return BranchTip(answer=ProbeAnswer.REFUTED)
    return BranchTip(answer=ProbeAnswer.CONFIRMED, sha=published)


def _base_contains(
    spec: config.RepoSpec, base: BranchTip, revision: str,
) -> ProbeAnswer:
    """Whether the base the remote named already carries `revision`.

    The proof that an artifact's commits are not lost by deleting it: a tip
    the base contains is work that has already landed, whatever route it took
    to get there. BOTH ends are things the caller established -- the base from
    the remote itself, the tip from the artifact that is about to go -- so
    nothing an agent can write decides the answer. Naming
    `refs/remotes/<remote>/<base>` here instead would hand that decision back
    to the object store the agent shares.

    A base the remote would not answer for, and one it says does not exist,
    arrive where a comparison that could not be taken arrives: there is
    nothing to measure against, so nothing about the revision is established.
    That is decided here rather than by each caller, so no caller can reach
    the comparison holding a base nobody named.

    The comparison itself is local, and it is sound there: ancestry between
    two object ids is content-addressed, and the hardened envelope turns off
    the two ways a repository can be told to serve one commit under another's
    name.

    `REFUTED` is git's own no. Anything else -- a base commit this clone has
    not fetched, a revision it cannot resolve, a repository that would not
    open -- is `UNREADABLE`, since none of them establishes that the base
    carries the commit and none of them establishes that it does not.
    """
    if base.answer is not ProbeAnswer.CONFIRMED:
        return ProbeAnswer.UNREADABLE
    contained = _clone_read(
        spec, "merge-base", "--is-ancestor", revision, base.sha,
    )
    if contained is None:
        return ProbeAnswer.UNREADABLE
    if contained.returncode == 0:
        return ProbeAnswer.CONFIRMED
    if contained.returncode == _GIT_NEGATIVE:
        return ProbeAnswer.REFUTED
    log.debug(
        "could not measure %s against %s in %s: %s",
        revision, base.sha, spec.target_root, (contained.stderr or "").strip(),
    )
    return ProbeAnswer.UNREADABLE


def _clean_worktree(worktree: Path) -> ProbeAnswer:
    """Whether this checkout PROVED it is carrying nothing loose.

    Read through the verification probe rather than a `status` of its own,
    because that owner is where the ways a clean answer can be arranged are
    already handled: the tree is named on the command line so per-worktree
    `core.worktree` cannot redirect the read, untracked files and submodules
    are asked for explicitly so local config cannot hide them, the report is
    NUL-delimited so a path cannot be read as rename syntax, and the index is
    asked whether it has been told to stop comparing entries at all.

    Its `readable` flag is what separates the two negatives here. A tree
    whose status could not be taken -- and a tree whose index carries a
    suppressed entry, which that owner reports the same way -- is
    `UNREADABLE`, never `REFUTED`: nothing was established about what the
    checkout holds, and a reclamation that read it as merely dirty would go
    on to say so as though somebody had looked.

    A checkout the read cannot reach is answered the same way rather than
    raised over, and the boundary is total because the ways it fails are not
    all of one kind. The scan named the directory some moments earlier and an
    agent owns what is under it, so by now the path can be gone -- which fails
    the spawn with an `OSError` -- or be a symlink loop, which fails in the
    `Path.resolve` behind the `--work-tree` argument and fails as a
    `RuntimeError` on Python 3.12 while merely coming back unchanged on 3.13.
    A probe whose contract is three answers may not have a fourth: an
    exception out of one candidate's tree ends the pass for every other
    candidate in it, which is the one way an unreadable checkout can cost more
    than the artifact it is about.
    """
    try:
        status = _worktree_status._worktree_status(worktree)
    except Exception:
        log.warning(
            "the checkout %s could not be reached", worktree, exc_info=True,
        )
        return ProbeAnswer.UNREADABLE
    if not status.readable:
        log.debug("the checkout %s would not report its status", worktree)
        return ProbeAnswer.UNREADABLE
    if status.paths:
        return ProbeAnswer.REFUTED
    return ProbeAnswer.CONFIRMED


def _nothing_ignored(worktree: Path) -> ProbeAnswer:
    """Whether this checkout PROVED it is hiding nothing under its own rules.

    The half of "carrying nothing" that `_clean_worktree` does not answer, and
    the one that only a caller about to delete the tree has to ask. A file the
    repository's ignore rules cover is invisible to every status a publication
    takes and to git's own refusal to remove a dirty worktree, so without this
    the whole proof that a checkout may go rests on a reading that was never
    about those files.

    `REFUTED` names them rather than merely counting them, in the log: what an
    operator does about a retention here is look at what is there and decide,
    and "something is hidden in that tree" sends them through the whole of it.

    Total and tri-state like the read beside it, and for the same reasons. The
    scan named the directory some moments earlier and an agent owns what is
    under it, so the path can be gone by now or be a symlink loop -- and a
    probe whose contract is three answers may not have a fourth.
    """
    try:
        hidden = _worktree_status._ignored_paths(worktree)
    except Exception:
        log.warning(
            "the checkout %s could not be reached", worktree, exc_info=True,
        )
        return ProbeAnswer.UNREADABLE
    if hidden is None:
        log.debug("the checkout %s would not report what it hides", worktree)
        return ProbeAnswer.UNREADABLE
    if hidden:
        log.info(
            "the checkout %s is hiding %s under its own ignore rules",
            worktree, ", ".join(hidden),
        )
        return ProbeAnswer.REFUTED
    return ProbeAnswer.CONFIRMED


def _checkout_git_dir(worktree: Path) -> Path | None:
    """The git directory this checkout keeps for itself, or None.

    Its OWN, not the store it shares: a linked worktree has a directory under
    the parent's `worktrees/` holding the HEAD, the index, and the reflog that
    belong to that tree alone. Those are the files git writes when somebody
    works in it, which is what makes them the evidence the read below is after
    -- the shared store would answer the same for every checkout of the clone.

    Answered absolutely, so a caller does not have to know which directory it
    is relative to; `None` when git would not say, which the caller spends as
    a reading that established nothing rather than as a tree nobody has been
    near.
    """
    located = _hardened_read(worktree, "rev-parse", "--absolute-git-dir")
    if located is None or located.returncode != 0:
        return None
    git_dir = (located.stdout or "").strip()
    return Path(git_dir) if git_dir else None


def _last_touched(paths_touched: Iterable[Path]) -> float | None:
    """The newest modification time among some paths, or None if one refused.

    A path that is not there contributes nothing rather than failing the read:
    the reflog is absent wherever `core.logAllRefUpdates` is off, and its
    absence says nothing at all about when the tree was last worked in. Any
    OTHER refusal answers `None`, since a reading that could not be taken must
    not come back as the oldest timestamp it managed to collect.
    """
    newest = None
    for path in paths_touched:
        try:
            touched = path.lstat().st_mtime
        except FileNotFoundError:
            continue
        except OSError as read_error:
            log.debug("could not read when %s was touched: %s", path, read_error)
            return None
        newest = touched if newest is None else max(newest, touched)
    return newest


def _registered_worktrees(spec: config.RepoSpec) -> int | None:
    """How many linked worktrees this clone keeps administrative entries for.

    The count the listing beside this is checked against. Every linked worktree
    git knows about has a directory of its own under the clone's
    `worktrees/`, and that directory is what survives when the backlink inside
    it does not -- which is exactly the state `worktree list` passes over in
    silence.

    Zero where the clone has never had one, which is an established answer: a
    repository with no `worktrees/` directory has no linked worktrees. `None`
    for every other refusal, since a count nobody could take must not arrive as
    agreement with whatever the listing said.
    """
    common_dir = probes._checkout_clone(spec.target_root)
    if common_dir is None:
        return None
    try:
        return len(list((common_dir / _WORKTREE_ADMIN).iterdir()))
    except FileNotFoundError:
        return 0
    except OSError as read_error:
        log.debug(
            "could not read the worktree entries of %s: %s",
            spec.target_root, read_error,
        )
        return None


def _checked_out_branches(spec: config.RepoSpec) -> frozenset[str] | None:
    """Every branch a worktree of this clone still has checked out, or None.

    The one thing `update-ref -d` gives up in exchange for its commit pin.
    `branch -D` refuses to delete a branch a worktree is on, and the plumbing
    form does it without a word -- leaving that tree holding a HEAD that names
    a ref nothing resolves. So a caller deleting through the plumbing has to
    ask this question itself, and it has to ask the clone rather than reason
    from the candidate: a worktree an operator added by hand to look at a
    finished branch is on it just as squarely as one this orchestrator made,
    and no scan of the per-issue paths would ever name it.

    A listing that exits zero is not on its own the whole answer, which is why
    it is counted against the clone's own administrative entries. `worktree
    list` drops a linked worktree whose backlink file is missing -- silently,
    with nothing on stderr and a zero exit -- while that worktree goes on
    working and goes on holding its branch. A caller spending the short answer
    would delete the ref under it, which is the very thing this read exists to
    prevent, so anything the two readings cannot account for between them is
    answered as no reading at all.

    Both are taken under one hold of the lock every mutation of this clone
    serializes on, so the listing and the count describe one moment rather than
    two either side of a `worktree add`.

    The names come back stripped of `refs/heads/`, which is how every
    derivation in ``paths`` spells a branch, so a caller compares against them
    without either side adjusting. A detached worktree names no branch and
    contributes nothing.
    """
    with locks._target_root_lock(spec.target_root):
        listed = _hardened_read(
            spec.target_root, "worktree", "list", "--porcelain",
        )
        registered = _registered_worktrees(spec)
    if listed is None or listed.returncode != 0:
        log.debug(
            "could not list the worktrees of %s: %s",
            spec.target_root,
            None if listed is None else (listed.stderr or "").strip(),
        )
        return None
    reported = (listed.stdout or "").splitlines()
    if not _all_worktrees_accounted(spec, reported, registered):
        return None
    on_branch = f"{_WORKTREE_BRANCH}{_LOCAL_REF_PREFIX}"
    return frozenset(
        line[len(on_branch):]
        for line in reported
        if line.startswith(on_branch)
    )


def _all_worktrees_accounted(
    spec: config.RepoSpec, reported: list[str], registered: int | None,
) -> bool:
    """Whether the listing named every worktree this clone has an entry for.

    One line per worktree opens each record, and the clone's own is the first
    of them -- so a healthy listing names exactly one more worktree than there
    are linked entries. Anything else is a worktree git declined to report
    while its directory is still there, and this read may not answer for a
    clone it could only see part of.
    """
    if registered is None:
        log.warning(
            "could not count the worktrees registered in %s; taking the "
            "listing as unread rather than as the part of it that answered",
            spec.target_root,
        )
        return False
    named = sum(
        1 for line in reported if line.startswith(_WORKTREE_RECORD)
    )
    if named == registered + 1:
        return True
    log.warning(
        "%s registers %d linked worktrees and listed %d; taking the listing "
        "as unread rather than deleting a branch one of them may be on",
        spec.target_root, registered, named - 1,
    )
    return False


def _quiet_checkout(worktree: Path, since: float) -> ProbeAnswer:
    """Whether this checkout PROVED nothing has touched it since `since`.

    The restraint a caller about to delete a tree owes an operator who may
    still be standing in it. Every other read here asks what the checkout
    HOLDS; this one asks when it was last disturbed, which is the only
    question that separates an issue that finished months ago from one whose
    agent stopped a minute before the pass ran.

    Three timestamps, because no one of them sees the whole of it. The
    directory's own answers for an entry created, renamed, or removed at the
    top of the tree -- a clone, a build root, a file dropped in by hand -- and
    for nothing else: editing a tracked file deeper in leaves it exactly where
    it was, and so does committing that edit. What git writes on a commit is
    the checkout's OWN index and its own reflog, both under the per-worktree
    git directory, so those two are what say a tree was being worked in a
    moment ago even though everything in it is now clean and committed.

    `since` is a wall-clock instant the caller decided, so what counts as
    lately is the pass's policy rather than this module's. `REFUTED` is a tree
    touched after it -- an established fact about the checkout -- and
    `UNREADABLE` is a host that would not say: a path gone since the scan named
    it answers that way too, because a caller may not read "the tree I was
    about to delete cannot be found" as proof that deleting it costs nothing.
    A checkout whose git directory could not be located is the same answer, for
    the same reason: without it, the only timestamp left is the one a commit
    does not move.
    """
    git_dir = _checkout_git_dir(worktree)
    if git_dir is None:
        log.debug("could not locate the git directory of %s", worktree)
        return ProbeAnswer.UNREADABLE
    touched = _last_touched((
        worktree, git_dir / _INDEX, git_dir / _HEAD_REFLOG,
    ))
    if touched is None:
        return ProbeAnswer.UNREADABLE
    if touched > since:
        return ProbeAnswer.REFUTED
    return ProbeAnswer.CONFIRMED


def _shared_repository(spec: config.RepoSpec, worktree: Path) -> ProbeAnswer:
    """Whether this checkout is a worktree of the configured clone.

    A directory sitting at the path this issue's checkout belongs at is not
    the checkout: an agent can run `git init` in it, an operator can park an
    unrelated clone there, and a reclaim that read the path as the identity
    would take a repository this orchestrator never created. What answers is
    the store the two share -- a linked worktree keeps its own git directory
    and registers it under the parent's, so the common directory is the one
    spelling that comes back equal for a checkout and the clone that made it.
    """
    checkout_dir = probes._checkout_clone(worktree)
    clone_dir = probes._checkout_clone(spec.target_root)
    if checkout_dir is None or clone_dir is None:
        return ProbeAnswer.UNREADABLE
    if checkout_dir != clone_dir:
        return ProbeAnswer.REFUTED
    return ProbeAnswer.CONFIRMED


def _head_ref(worktree: Path) -> tuple[ProbeAnswer, str]:
    """Whether this checkout's HEAD is on a branch, and which one.

    The pair rather than either half alone, because one read answers two
    questions its callers ask separately: whether the tree belongs to this
    issue at all, and -- once it does -- which branch to ask the remote and
    GitHub about the commit under it. A caller that only ever got the verdict
    would have to read HEAD a second time to learn the name.

    A detached HEAD is `REFUTED` rather than unreadable: `symbolic-ref
    --quiet` spells it as the plain no it is, and every checkout the issue
    creators make is on a branch. What made it detached is somebody else's
    doing, and a commit sitting on no branch is exactly the work a reclaim
    must not take.

    The name comes back stripped of `refs/heads/`, which is how every
    derivation in ``paths`` spells a branch, so it can be compared against
    them and handed to a lookup without either side adjusting it.
    """
    head = _hardened_read(worktree, "symbolic-ref", "--quiet", _HEAD)
    if head is None:
        return ProbeAnswer.UNREADABLE, ""
    if head.returncode == _GIT_NEGATIVE:
        return ProbeAnswer.REFUTED, ""
    named = (head.stdout or "").strip()
    if head.returncode != 0 or not named.startswith(_LOCAL_REF_PREFIX):
        log.debug(
            "could not read the HEAD of %s: %s",
            worktree, (head.stderr or "").strip(),
        )
        return ProbeAnswer.UNREADABLE, ""
    return ProbeAnswer.CONFIRMED, named[len(_LOCAL_REF_PREFIX):]


def _head_is_own_branch(
    spec: config.RepoSpec, issue_number: int, worktree: Path,
) -> ProbeAnswer:
    """Whether this checkout's HEAD is on a branch this issue publishes under.

    The half of the identity that says the tree belongs to this issue rather
    than to whatever was checked out into it afterwards. Both names one issue
    can be published under are accepted, since a checkout made before slug
    namespacing landed is still on the flat one.
    """
    answer, branch = _head_ref(worktree)
    if answer is not ProbeAnswer.CONFIRMED:
        return answer
    if branch not in _naming._issue_branch_names(spec, issue_number):
        return ProbeAnswer.REFUTED
    return ProbeAnswer.CONFIRMED


def _checkout_identity(
    spec: config.RepoSpec, issue_number: int, worktree: Path,
) -> ProbeAnswer:
    """Whether this checkout is the one this issue's own creator made.

    Both halves have to hold and neither implies the other: a worktree of the
    configured clone can be sitting on any branch in it, and a HEAD naming
    this issue's branch can belong to a repository somebody else made. The
    repository is asked first, because a HEAD read against a tree that is not
    ours answers about a ref store this classification is not entitled to
    reason about.
    """
    shared = _shared_repository(spec, worktree)
    if shared is not ProbeAnswer.CONFIRMED:
        return shared
    return _head_is_own_branch(spec, issue_number, worktree)
