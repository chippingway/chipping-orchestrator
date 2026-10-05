# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Whether a directory is the top of a git checkout, as git itself reads it.

A checkout is a directory git opens as the top of a working tree from the
``.git`` it carries itself: an ordinary clone's ``.git`` directory, or a linked
worktree's ``.git`` file naming its git directory. Whether git opens one turns
on more than the files a reader can list -- the ``gitdir:`` format, a ``HEAD``
naming a ref or a commit, a config git can parse, continued lines and all, a
repository format and extensions this git supports, and a ``core.bare`` that
leaves a working tree -- and those rules move with git's version. So the
answer is git's own: one read-only ``git rev-parse`` run in the directory,
under the operator's environment the way the git layer runs a plain command.

Git is first handed that directory's own ``.git`` with ``--git-dir`` rather
than left to discover a repository, and every variable that would point it at
another one is removed. A repository around the directory -- even one whose
``core.worktree`` names it -- is therefore never asked, so it cannot stand in
for a ``.git`` that is missing or one git refuses. A directory with no ``.git``
is asked only whether it is itself a bare repository, which tells the two
refusals apart.

Naming the repository that way also skips the one check git makes only when it
discovers one: that the checkout belongs to the user running it, or that
``safe.directory`` trusts it. Every git command the orchestrator later runs in
a target discovers it from there, so a checkout that passes is then asked once
more the same way, from inside. With its own ``.git`` already proved whole,
that discovery stops at it rather than walking up, and what it can refuse is
the ownership git would refuse every later command on.

``layout`` proves a source checkout with this, and ``repositories`` holds every
configured target to it. Running git as a program imports nothing from
``orchestrator.git``, which keeps the package below the git layer.
"""
from __future__ import annotations

import os
import subprocess
from pathlib import Path

_PROBE = ("rev-parse", "--is-bare-repository", "--show-toplevel")
_DISCOVERY = ("rev-parse", "--show-toplevel")
# What `_PROBE` prints ahead of the work tree's path: each value on a line of
# its own, the path written raw, so a path may itself hold a line break.
_BARE_ANSWER = b"true\n"
_WORK_TREE_ANSWER = b"false\n"
_PROBE_TIMEOUT_SECONDS = 30
_BARE_REPOSITORY = "is a bare repository, which has no working tree"

# The variables that tell git which repository or work tree to use: the subset
# of `git rev-parse --local-env-vars` that locates a repository, its work
# tree, or its object store. Each probe names its repository itself, by
# `--git-dir` or by where it runs, and none of these may move it.
_REPOSITORY_LOCATING_ENV = frozenset((
    "GIT_DIR",
    "GIT_WORK_TREE",
    "GIT_IMPLICIT_WORK_TREE",
    "GIT_COMMON_DIR",
    "GIT_INDEX_FILE",
    "GIT_OBJECT_DIRECTORY",
    "GIT_ALTERNATE_OBJECT_DIRECTORIES",
    "GIT_NAMESPACE",
    "GIT_PREFIX",
))


def _ask_git(real_root: Path, *arguments: str) -> subprocess.CompletedProcess[bytes]:
    """Git with ``arguments``, run in ``real_root`` and pointed nowhere else.

    Its output stays bytes: decoding text folds a carriage return into a line
    end, and the path git prints is compared as git wrote it.
    """
    probe_environment = {
        name: env_value
        for name, env_value in os.environ.items()
        if name not in _REPOSITORY_LOCATING_ENV
    }
    probe_environment["GIT_TERMINAL_PROMPT"] = "0"
    return subprocess.run(
        ("git", *arguments),
        cwd=real_root,
        capture_output=True,
        env=probe_environment,
        check=False,
        timeout=_PROBE_TIMEOUT_SECONDS,
    )


def _first_line(answer: subprocess.CompletedProcess[bytes]) -> str:
    """The first thing git said on stderr, or its exit status when silent."""
    for line in os.fsdecode(answer.stderr).splitlines():
        if line.strip():
            return line.strip()
    return f"git exited with status {answer.returncode}"


def _without_dot_git(real_root: Path) -> str:
    """Why a directory with no ``.git`` of its own is not a checkout.

    Git is asked about the directory as a repository in its own right, so a
    bare clone is named for what it is rather than as a plain directory.
    """
    answer = _ask_git(real_root, f"--git-dir={real_root}", *_PROBE)
    if answer.stdout.startswith(_BARE_ANSWER):
        return _BARE_REPOSITORY
    return "has no .git of its own, so it is not the top of a git checkout"


def _verdict(real_root: Path, answer: subprocess.CompletedProcess[bytes]) -> str | None:
    """What git's answer about ``real_root``'s own ``.git`` says, if anything.

    Git prints whether the repository is bare, then the top of its working
    tree; a bare one fails on the second, after answering the first. The path
    is matched byte for byte against the one asked about, line breaks and all.
    """
    answered = answer.returncode == 0
    top_answer = b"".join((_WORK_TREE_ANSWER, os.fsencode(real_root), b"\n"))
    if answered and answer.stdout == top_answer:
        return None
    if answer.stdout.startswith(_BARE_ANSWER):
        return _BARE_REPOSITORY
    if answered:
        work_tree = os.fsdecode(answer.stdout.removeprefix(_WORK_TREE_ANSWER)).removesuffix("\n")
        return f"has a .git whose working tree is {work_tree!r}, not this directory"
    reason = _first_line(answer)
    return f"has git metadata git cannot open ({reason})"


def _ownership_problem(real_root: Path) -> str | None:
    """Whether git, discovering the checkout from inside it, refuses to open it.

    Called only once ``real_root``'s own ``.git`` has passed, so discovery
    stops there; a refusal is git declining a checkout another user owns.
    """
    answer = _ask_git(real_root, *_DISCOVERY)
    if answer.returncode == 0:
        return None
    reason = _first_line(answer)
    return f"is a checkout git refuses to open from inside it ({reason})"


def _problem(root: Path) -> str | None:
    """What keeps ``root`` from being a checkout, if anything."""
    if not root.is_dir():
        return "is not a directory" if root.exists() else "does not exist"
    real_root = Path(os.path.realpath(root))
    dot_git = real_root / ".git"
    if not dot_git.exists():
        return _without_dot_git(real_root)
    problem = _verdict(real_root, _ask_git(real_root, f"--git-dir={dot_git}", *_PROBE))
    if problem is None:
        problem = _ownership_problem(real_root)
    return problem


def checkout_problem(root: Path) -> str | None:
    """What keeps ``root`` from being a checkout, or ``None`` when it is one.

    The answer completes a sentence about ``root`` -- ``does not exist``,
    ``is a bare repository, ...`` -- so a caller names the path and the
    setting it came from in front of it.
    """
    try:
        return _problem(root)
    except (OSError, subprocess.SubprocessError) as error:
        return f"cannot be inspected ({error})"
