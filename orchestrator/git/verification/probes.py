# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""HEAD, tree identity, committed-object, and committed-path probes.

Reads use the git command owner's hardened, non-interactive envelope. Commit
comparisons take established object IDs from the caller so they describe one
candidate even if a branch moves between reads. Loose and hidden worktree paths
are read by the status owner, including its index-suppression checks.
"""
from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

from orchestrator.git import commands as _commands

_IGNORE_SUBMODULES_NONE = "--ignore-submodules=none"

# What every read of a path here asks for. Git's default output quotes a name
# with anything unusual in it and separates records by newline, so a path can
# arrive escaped, or split across what reads as two entries. NUL-delimited it
# arrives as the bytes it is.
_NUL_DELIMITED = "-z"

# What `-z` separates those records with, spelled once: every read here splits
# on it, and a typo would read one record as a whole report.
_NUL_SEPARATOR = "\0"

# What a tree entry has to be for a caller asking whether a document is at a
# path: the two modes git gives a regular file, and the object type that goes
# with them. A symlink (`120000`) and a gitlink (`160000`) are entries at the
# same path that are not the file anybody would read there.
_BLOB_TYPE = "blob"

_REGULAR_FILE_MODES = frozenset(("100644", "100755"))


def _head_sha(worktree: Path) -> str:
    """HEAD commit SHA of the worktree, or '' if it cannot be read.

    Used by the validating handler to detect whether a dev-fix codex run
    produced a new commit. _has_new_commits compares against origin/<base>,
    which is already true throughout validating, so we need an absolute SHA
    snapshot instead.
    """
    head_result = _commands._git("rev-parse", "HEAD", cwd=worktree)
    if head_result.returncode != 0:
        return ""
    return (head_result.stdout or "").strip()


def _tree_sha(worktree: Path, revision: str = "HEAD") -> str:
    """Tree SHA of `revision` in `worktree`, or '' if it cannot be read.

    Used by local verification to record full tree identity and prove tree
    stability across commands.
    """
    if not revision:
        return ""
    target = f"{revision}^{{tree}}"
    tree_result = _commands._git("rev-parse", "--verify", target, cwd=worktree)
    if tree_result.returncode != 0:
        return ""
    return (tree_result.stdout or "").strip()


def _head_on_branch(worktree: Path, branch: str) -> bool:
    """True when this checkout's HEAD IS `branch` rather than a bare commit.

    The question a caller has to answer before it publishes a commit by SHA to
    `refs/heads/<branch>`. A commit made on a detached HEAD -- or on some other
    ref -- is a real commit in a real tree, and every reading of what it
    changed comes back the same, so nothing else here can tell the two apart.
    What differs is the branch: it stays where it was, and everything after the
    push reads it. The records name a commit the local ref does not carry, the
    relabel guard downstream convicts that stale tip of being unreviewed work,
    and a checkout rebuilt from it comes back without the plan.

    Answered from `symbolic-ref` rather than by comparing SHAs, because the two
    are different facts: a branch that happens to point at the same commit is
    not a HEAD that will move with it, and the next commit an agent makes
    detached would separate them again with nothing here having changed.

    Hardened for the reason every probe here is, and false on any failure --
    including a detached HEAD, which is exactly what a non-zero exit means for
    this command. A caller that cannot prove HEAD is the branch must proceed as
    though it is not.
    """
    ref_result = _commands._git_hardened(
        "symbolic-ref", "--quiet", "HEAD", cwd=worktree,
    )
    if ref_result.returncode != 0:
        return False
    return (ref_result.stdout or "").strip() == f"refs/heads/{branch}"


def _revision_contains_path(
    worktree: Path, revision: str, path: str,
) -> bool:
    """True when `revision`'s tree carries `path` as a regular file.

    Asked beside the base-relative diff because that diff cannot tell writing
    a path from deleting one: a commit that removes a file the base branch
    already carried changes exactly that path and nothing else, which a caller
    checking only the changed-path set would read as the artifact it asked
    for. Reading the object out of the commit is what separates the two.

    The MODE is part of the question, not decoration, because the caller is
    asking whether a document is there. Git stores three other things at a
    path: a symlink (`120000`, whose blob is a target string, so the artifact a
    reviewer opens is whatever it points at -- possibly outside the
    repository), a gitlink (`160000`, a commit id for a submodule nobody here
    fetches), and a directory. All three exist at the path and none is the
    plan, so "the object resolves" is the wrong test; both regular modes are
    accepted, since an executable bit on a Markdown file is odd rather than a
    different kind of artifact.

    The commit is named rather than left as `HEAD` for the same reason the
    diff below names it: a caller that decides by inspecting a commit and then
    publishes THAT commit must have inspected the one it publishes, and `HEAD`
    is a moving name -- an agent, another tick, or an operator can move it
    between two `git` invocations.

    Hardened for the reason every probe here is, and false on any failure --
    a caller that publishes on this must be told "no" when the tree cannot be
    read at all. `-z` for the reason the diff uses it: an unusual byte in the
    path would otherwise come back quoted and match nothing.
    """
    entry_result = _commands._git_hardened(
        "ls-tree", _NUL_DELIMITED, "--full-tree", revision, "--", path,
        cwd=worktree,
    )
    if entry_result.returncode != 0:
        return False
    # Each record is `<mode> SP <type> SP <object> TAB <path>`, and one path was
    # asked about: anything but a single record answers about something else,
    # and no record at all is the path being absent.
    records = [
        record for record in (entry_result.stdout or "").split(_NUL_SEPARATOR) if record
    ]
    if len(records) != 1:
        return False
    fields = records[0].split("\t", 1)[0].split()
    if len(fields) < 2:
        return False
    return fields[1] == _BLOB_TYPE and fields[0] in _REGULAR_FILE_MODES


def _commit_present(
    worktree: Path,
    revision: str,
    env_extra: Mapping[str, str] | None = None,
) -> bool:
    """True when `revision` names a commit this repository can actually read.

    The question a caller has to ask before it RECORDS an object id, and the
    reason it cannot be skipped is the failure mode of the read below: a diff
    naming a commit git cannot resolve fails, and a failed read answers "no
    paths", which is what a branch that changes nothing also answers. An id
    pinned while it was absent therefore turns a branch carrying exactly the
    permitted path into a branch that reads as carrying none -- silently, and
    for as long as the record stands.

    It is a real question because the ends of that diff come from different
    places. A base id read off the remote is the remote's current answer, and
    this clone last fetched at some earlier point; the commit it names may
    simply not be here yet. A caller told so can bring it in and pin an id its
    own diff will resolve.

    `^{commit}` is part of the question rather than decoration: a tag or a tree
    at that id is not something the diff can measure from, so peeling is what
    makes a positive answer mean what the caller needs it to.

    Hardened for the reason every probe here is, and false on any failure --
    including the failure to run git at all, since a caller that cannot prove
    the object is here must proceed as though it is not.

    `env_extra` is here for the caller whose "here" is narrower than this
    repository's own. A clone made with a filter keeps a promisor remote, and
    git answers an id it is missing by fetching it rather than by failing --
    so an object that is not in this store still comes back present, having
    just been brought in over the network. A caller bringing the object in
    ITSELF wants that read left alone; one that has to say whether the store
    already held it states so here, and the pins it passes are the ones the
    rest of its reading is taken under.
    """
    object_result = _commands._git_hardened(
        "cat-file", "-e", f"{revision}^{{commit}}",
        cwd=worktree,
        env_extra=env_extra,
    )
    return object_result.returncode == 0


def _commit_contains(worktree: Path, ancestor: str, revision: str) -> bool:
    """True when `revision`'s history contains `ancestor`.

    The question a caller has to ask before it OVERWRITES a ref: publishing a
    commit over a tip that commit does not descend from deletes whatever was on
    that tip, and no lease can help -- a lease only proves the ref has not moved
    since it was read, not that what is there survives the push. Asked of the
    two object ids the caller established (the tip something else is on, and the
    commit being published), this is the fast-forward test, and refusing on it
    is what keeps a publication from taking history away.

    An ancestor this repository does not have answers False, because git cannot
    resolve it and a commit here plainly does not contain a commit this host has
    never seen. That is the right answer for the caller either way: it is a tip
    somebody produced elsewhere, so the push would discard it.

    Hardened for the reason every probe here is, and false on any failure --
    exit status 1 is git's "no", and anything else is a read that established
    nothing, which a caller about to overwrite a ref must treat as "no" too.
    """
    ancestry_result = _commands._git_hardened(
        "merge-base", "--is-ancestor", ancestor, revision, cwd=worktree,
    )
    return ancestry_result.returncode == 0


def _committed_paths_since(
    worktree: Path, base_sha: str, revision: str,
) -> list[str]:
    """Paths `revision` changes against the commit `base_sha` names.

    The counterpart to `_worktree_dirty_files` for work that is already
    committed, and the probe a caller with exactly one permitted path needs:
    the discussion stage publishes a branch only when the whole of it against
    the base is the plan file it asked for, which a commit count cannot answer.

    BOTH ends are object ids the caller established, and neither is a ref this
    host can rewrite. The commit, because the caller that reads this is the
    caller that then pushes: a reading of `HEAD` and a push of the SHA it
    captured a moment earlier are answers about two different commits the
    instant anything moves the branch between them. The base, because
    `refs/remotes/<remote>/<base>` lives in the object store the agent's
    worktree shares -- an agent that commits code, repoints that ref at its own
    commit, and then commits the permitted path would otherwise be measured
    against its own work and read as having changed only that path.

    Three-dot, so a base that moved on since the branch forked is not read as
    work this branch did. `--no-renames`, so a file moved onto the permitted
    path is reported as the deletion and the addition it is rather than as a
    single rename landing exactly where the caller was looking. `-z`, because
    the caller compares paths literally and git's default output quotes and
    escapes unusual bytes -- a quoted path would never match the one the agent
    was promised.

    `--ignore-submodules=none` for the reason the status read spells its own
    flags out: `diff.ignoreSubmodules=all` in the worktree's `.git/config` is
    agent-writable, and a caller that permits exactly one path would otherwise
    be told nothing about a gitlink the commit moved.

    Naming both ends by object id is only worth something because the hardened
    envelope turns object replacement off. `refs/replace/<oid>` and the graft
    file both make git serve one commit under another's name, and both are
    writable from the worktree -- an id that can be re-pointed is a name, not
    an identity, and this probe would be measuring against whatever the agent
    put behind it.

    Hardened for the reason the dirty probe is: every call site is a worktree
    the agent can write to, so a planted `core.fsmonitor` or alias would
    otherwise run with the orchestrator's environment attached. A failed read
    answers "no paths", which reads downstream as nothing publishable -- a
    probe that cannot say what a branch carries must never be the reason it is
    pushed.
    """
    diff_result = _commands._git_hardened(
        "diff", "--name-only", "--no-renames", _NUL_DELIMITED,
        _IGNORE_SUBMODULES_NONE,
        f"{base_sha}...{revision}",
        cwd=worktree,
    )
    if diff_result.returncode != 0:
        return []
    return [path for path in (diff_result.stdout or "").split(_NUL_SEPARATOR) if path]
