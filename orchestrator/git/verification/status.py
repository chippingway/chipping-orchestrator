# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Hardened reads of loose, ignored, and suppressed worktree paths.

Porcelain records retain NUL framing so unusual filenames and rename sources
survive intact. An index entry hidden by skip-worktree or assume-unchanged
makes the reading unproven; ignored paths are a separate, bounded teardown gate.
"""
from __future__ import annotations

from dataclasses import dataclass
from itertools import islice
from pathlib import Path

from orchestrator.git import commands as _commands

# What the two working-tree reads have to say for themselves, because the
# worktree's own `.git/config` is agent-writable and answers otherwise:
# `status.showUntrackedFiles=no` hides untracked paths from a status that asks
# for defaults, and `diff.ignoreSubmodules=all` hides a moved gitlink from a
# diff that does.
_UNTRACKED_ALL = "--untracked-files=all"

# Status records are NUL-delimited and include dirty submodule worktrees.
_NUL_DELIMITED = "-z"
_NUL_SEPARATOR = "\0"
_IGNORE_SUBMODULES_NONE = "--ignore-submodules=none"

# What has `status` report the paths its ignore rules hide, how each of those
# is spelled in the report, and the untracked mode they are asked for beside.
#
# The mode is stated for two reasons at once. `status.showUntrackedFiles=no`
# in the repository the checkouts share stops the untracked walk, and this
# half of the report is what that walk turned up and then classified -- so
# asked for defaults it comes back empty over any number of hidden files. And
# `all` is what expands an ignored DIRECTORY into every file beneath it, so a
# tree carrying a dependency root would answer with a hundred thousand paths
# where `normal` answers with the root. Stating `normal` overrides the knob
# and keeps the collapse.
_IGNORED_ENTRIES = "--ignored"

_IGNORED_STATUS = "!! "

_UNTRACKED_NORMAL = "--untracked-files=normal"

# How many hidden paths are carried back. The caller's question is whether the
# tree is holding anything at all, and its answer is a refusal naming what an
# operator has to go and look at -- so what is past a handful is weight in a
# log line rather than information, however the collapse above went.
_IGNORED_LIMIT = 10

# What keeps a READ from writing. `git status` refreshes the index as it goes
# and writes the refreshed stat data back, which is a change to the repository
# made by a probe that was only asked a question -- and one that takes
# `index.lock` while it does it, so a status taken beside a running agent can
# fail on a lock neither of them needed. Every caller here is deciding whether
# to publish or to reclaim, and none of them is entitled to leave a mark on
# the tree it is deciding about.
_NO_OPTIONAL_LOCKS = "--no-optional-locks"

# What porcelain's two status columns say when an entry came from somewhere
# else. Under `-z` the path it came FROM is its own record, following the one
# naming where it is now -- so a reader that did not expect the pair would take
# a bare path for a status line and cut three bytes off the front of it.
_RENAMED_STATUS = frozenset(("R", "C"))

# What `git ls-files -v` tags an index entry with when git has been told to
# stop comparing it against the working tree: `S` for skip-worktree, and a
# LOWERCASE tag of any letter for assume-unchanged.
_SKIP_WORKTREE_TAG = "S"


@dataclass(frozen=True)
class _WorktreeStatus:
    """What `git status` said about a worktree, or that it could not say.

    `readable` is False when the read established nothing about the tree, and
    it is a separate field rather than an empty path list because the two mean
    opposite things to a caller that must not push over unproven state. The
    command failing is one way; an index entry git was told to stop comparing
    is the other, and that one also comes back in `paths` -- it is a thing to
    refuse on as well as a reason the rest cannot be called clean.
    """

    readable: bool
    paths: tuple[str, ...] = ()

    @property
    def is_clean(self) -> bool:
        """Whether this reading PROVED the tree is carrying nothing loose.

        What a caller whose next step is a push has to ask, and it is asked
        rather than truth-tested on `paths` for the reason the field beside
        them exists: a read that established nothing names no paths, which is
        what a tree with nothing in it names too. Only a reading that happened
        AND named nothing is a clean tree; everything else is a refusal,
        whichever half of it failed.
        """
        return self.readable and not self.paths


def _worktree_status(worktree: Path) -> _WorktreeStatus:
    """Read the worktree's modified and untracked paths, failure included.

    Hardened unconditionally: `git status --porcelain` refreshes the index,
    which spawns a configured `core.fsmonitor` helper -- and the agent can
    plant one in the worktree's `.git/config` or in `~/.gitconfig` (same OS
    user), so a plain probe would execute it with the orchestrator's process
    environment (ambient secrets) attached. Every call site is an
    agent-writable worktree, so there is no trusted caller that would want
    the unhardened form. Detaching global/system config also drops a global
    `core.excludesFile` from the untracked filter; the repo's own tracked
    `.gitignore` still applies, which is the intended trust boundary.

    Detaching does NOT reach the worktree's own `.git/config`, which the agent
    can write and which carries knobs that decide what `status` reports at all.
    `status.showUntrackedFiles=no` is the sharp one: set there, a probe reading
    defaults sees a clean tree over any number of untracked files. So what the
    report includes is stated on the command line, where local config cannot
    answer for it -- and so is HOW, since the default output quotes an unusual
    path and joins a rename onto one line, which is enough for a file named
    ` -> ` to read as rename syntax and leave the tree looking clean.

    WHICH tree it reports on is stated there too, and for a knob no override
    reaches. `core.worktree` in the per-worktree config (`config.worktree`,
    which an agent enables by writing `extensions.worktreeConfig` into the repo
    it shares) points discovery at another directory entirely, and a `-c
    core.worktree=` on the command line does not win against it -- so a probe
    that let git discover its own tree would report on a clean shadow checkout
    while the real one carried the agent's edits. `--work-tree` is what says
    otherwise, and it is the reason this answer is about the directory the
    caller named rather than the one the repository was talked into.

    Optional locks are off, which is what makes this a read. A `status` left
    to itself refreshes the index and writes the new stat data back, so a
    probe asking what a tree holds would modify the repository it is asking
    about -- and would contend for `index.lock` with whatever else is running
    in a tree an agent owns. Nothing about the answer changes; only whether
    taking it leaves a trace.

    Neither the envelope nor the flags above say anything about the index
    CONTENTS, which is where the last way out lives: `assume-unchanged` and
    `skip-worktree` are bits on an index entry rather than config, so nothing
    above reaches them, and either one has `status` skip the comparison and
    report a modified tracked file as clean.
    Those entries come back as paths AND withhold `readable`, because they are
    both things at once -- something the caller must refuse on, and a tree
    nothing here can call empty.
    """
    status_result = _commands._git_hardened(
        _commands._work_tree_arg(worktree),
        _NO_OPTIONAL_LOCKS,
        "status", "--porcelain", _NUL_DELIMITED,
        _UNTRACKED_ALL, _IGNORE_SUBMODULES_NONE,
        cwd=worktree,
    )
    if status_result.returncode != 0:
        return _WorktreeStatus(readable=False)
    suppressed = _suppressed_index_paths(worktree)
    if suppressed is None:
        return _WorktreeStatus(readable=False)
    reported = _reported_paths(status_result.stdout or "")
    if suppressed:
        return _WorktreeStatus(
            readable=False,
            paths=tuple(dict.fromkeys(reported + list(suppressed))),
        )
    return _WorktreeStatus(readable=True, paths=tuple(reported))


def _ignored_paths(worktree: Path) -> tuple[str, ...] | None:
    """What this tree carries that its own ignore rules hide, or None.

    Bounded and collapsed rather than exhaustive: a whole directory the rules
    cover comes back as the directory, and no more than a handful of entries
    come back at all. A caller deciding whether to delete a tree asks whether
    there is anything there and wants to be able to say what -- neither of
    which a hundred thousand paths answers better than ten.

    The one thing `_worktree_status` cannot report, and it is left out of that
    answer rather than folded into it because the two are spent differently: a
    caller deciding whether to publish is right to pass over ignored output,
    and a caller deciding whether to DELETE a tree is not. Git draws the same
    line -- `worktree remove` refuses a tree with untracked or modified files
    and takes an ignored one without a word -- so this is the read that stands
    between a reclamation and somebody's `.env`.

    `None` is the read that established nothing, kept apart from the empty
    answer for the reason every probe here keeps them apart: only an empty
    list proves the tree is hiding nothing, and a caller that read a failure
    as one would delete on the strength of a question nobody put.

    The same envelope as the status read above, and for the same reasons: the
    tree is named on the command line so per-worktree `core.worktree` cannot
    point the read at another one, optional locks are off so asking leaves no
    trace, and the report is NUL-delimited so a path cannot arrive quoted or
    joined. What the detached global config drops here is a global
    `core.excludesFile`, which costs nothing: a path hidden only by that file
    is not hidden from the untracked read beside this one, so between the two
    of them nothing on disk goes unreported.

    The untracked mode is stated here even though nothing untracked is read
    off the answer, and it is the load-bearing flag: `--ignored` reports what
    that walk turned up and then classified, so the local
    `status.showUntrackedFiles=no` an agent can write into the repository the
    checkouts share empties this report along with the other half. Asked for
    defaults, a tree holding an ignored secret answers that it holds nothing,
    which is the one answer that gets it deleted.

    `normal` rather than `all`, because `all` is what stops the collapse: a
    dependency root or a build tree would come back as every file beneath it,
    which is a report nobody reads and a walk this probe should never make.
    What comes back is bounded on top of that, since the answer is spent on a
    yes-or-no and a line naming what to look at.
    """
    listed = _commands._git_hardened(
        _commands._work_tree_arg(worktree),
        _NO_OPTIONAL_LOCKS,
        "status", "--porcelain", _NUL_DELIMITED,
        _IGNORED_ENTRIES, _UNTRACKED_NORMAL, _IGNORE_SUBMODULES_NONE,
        cwd=worktree,
    )
    if listed.returncode != 0:
        return None
    return tuple(islice(
        (
            record[len(_IGNORED_STATUS):]
            for record in (listed.stdout or "").split(_NUL_SEPARATOR)
            if record.startswith(_IGNORED_STATUS)
        ),
        _IGNORED_LIMIT,
    ))


def _reported_paths(status_stdout: str) -> list[str]:
    """Every path a NUL-delimited porcelain-v1 report names, in its own order.

    `-z` rather than the default line format, because the default is lossy in
    exactly the direction that costs something here. It quotes a path with
    anything unusual in it and spells a rename `<to> -> <from>` on one line, so
    an untracked file named ` -> ` comes back as `?? " -> "`: read as a rename,
    what follows the arrow is a lone quote, which is nothing once the quoting
    is undone -- and a tree holding that file reports clean, with a plan sitting
    beside it published as though the round had left nothing loose. Under `-z`
    nothing is quoted and nothing is joined, so there is nothing to guess at.

    The rename's source record is the one thing the loop carries state for: it
    is a bare path with no status columns in front of it, and taken for a
    status line it would lose its first three bytes. Both halves are reported,
    since a caller permitting exactly one path is entitled to know that a file
    left another one behind.
    """
    paths: list[str] = []
    renamed_from = False
    for record in status_stdout.split(_NUL_SEPARATOR):
        if renamed_from:
            renamed_from = False
            paths.append(record)
        elif len(record) > 3 and record[2] == " ":
            renamed_from = bool(_RENAMED_STATUS & set(record[:2]))
            paths.append(record[3:])
    return [path for path in paths if path]


def _suppressed_index_paths(worktree: Path) -> tuple[str, ...] | None:
    """Index entries git has been told not to compare, or None if unreadable.

    The one way a clean status can be arranged without config and without
    touching the file it is about. `git update-index --assume-unchanged` and
    `--skip-worktree` set bits on the index entry, which every `status` honors
    and no envelope can drop: the entry is reported as matching whatever is on
    disk, so a tracked file the agent rewrote comes back clean and the branch
    reads as publishable.

    An empty answer is the only one that proves nothing is suppressed, so the
    read failing is not it -- None says so, and the caller withholds `readable`
    rather than reading a list it could not take as "none set". The paths it
    does return are named so a refusal can quote them: what an operator has to
    clear is a bit on a specific entry, and "something in the index" would send
    them looking through the whole of it.

    Bound to the same tree and hardened for the same reasons as the status read
    beside it, since it answers half of the same question.
    """
    listed = _commands._git_hardened(
        _commands._work_tree_arg(worktree),
        "ls-files", "-v", _NUL_DELIMITED, "--full-name",
        cwd=worktree,
    )
    if listed.returncode != 0:
        return None
    # `-v -z` writes one `<tag> <path>` record per entry, NUL-terminated, and
    # `--full-name` with `-z` leaves the path unquoted -- so the first space is
    # the separator whatever the path itself contains.
    suppressed = []
    for record in (listed.stdout or "").split(_NUL_SEPARATOR):
        tag, _, path = record.partition(" ")
        if len(tag) == 1 and path and (
            tag == _SKIP_WORKTREE_TAG or tag.islower()
        ):
            suppressed.append(path)
    return tuple(suppressed)


def _worktree_dirty_files(worktree: Path) -> list[str]:
    """Paths git considers modified or untracked in the worktree.

    Used to refuse opening a PR when codex committed only part of its work and
    left other modifications behind -- the push would publish an incomplete
    branch. The orchestrator's own scratch (codex's `-o` file) lives outside
    the worktree (a per-spawn tempfile in `codex.run_codex`), so it never
    surfaces here regardless of the target repo's .gitignore.

    An unreadable worktree answers with no paths, which every caller here
    reads as "nothing to refuse on". That is the right shape for a refusal
    that fires on what git DID name; a caller whose next step is a push has to
    prove the opposite and asks `_worktree_status` instead.

    An index entry git has been told to stop comparing is the exception, and it
    comes back as a path: the status read cannot see the change under it, so a
    caller refusing on what git named would be told there is nothing to refuse
    on -- which is the whole point of setting the bit.
    """
    return list(_worktree_status(worktree).paths)
