# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""One validator per setup field, shared by every command that asks for one.

Each validator takes an answer as it was typed -- an option's value or a line
read at a prompt -- and returns the value a setup writes, or raises
``FieldError`` with the whole diagnostic as its text. A command line and an
interactive prompt therefore print the same words for the same answer, the
command naming the option in front of them and the prompt asking again under
them.

- The clone is the top of a git checkout, as ``checkouts`` reads one: the
  check the configuration holds every target to, so a clone that passes here
  passes there too.
- The repository is written ``owner/name``, in the characters GitHub allows in
  each, which also keeps it whole inside a ``REPOS`` entry and keeps the
  ``~/.config/<owner>/<name>`` its token is kept under inside ``~/.config``.
- The base branch is a name git allows for a branch, as
  ``git check-ref-format --branch`` reads one; whether a ``REPOS`` entry can
  carry it is the entry's own check, made as ``repos_entry`` writes it.
- A login list names at least one GitHub login, split on commas with a leading
  ``@`` dropped and repeats kept once, the way the configuration reads
  ``ALLOWED_ISSUE_AUTHORS`` and ``HITL_HANDLE`` back.
- An agent is one of the backends the configuration accepts, and an
  executable of that name is on the ``PATH`` the caller supplies -- the
  service's own, which is not necessarily the shell's.

The two optional fields of a ``REPOS`` entry, its remote and its parallel
limit, are validated beside the entry they belong to, in ``repos_entry``.

Nothing here imports ``orchestrator.config``: a first setup validates its
answers on a host where importing it would exit.
"""
from __future__ import annotations

import errno
import os
import re
import shutil
from pathlib import Path

from orchestrator.service.checkouts import checkout_problem

AGENTS = ("claude", "codex", "agy")
_AGENT_CHOICES = ", ".join(AGENTS)

# GitHub's alphabets: an account is letters, digits, and hyphens, an app's bot
# account carries a `[bot]` suffix, and a repository adds `.` and `_` -- but
# is never `.` or `..`, which would make the name a step out of the directory
# a path built from the repository names.
_LOGIN = re.compile(r"[A-Za-z0-9-]+(?:\[bot\])?")
_REPOSITORY = re.compile(r"[A-Za-z0-9-]+/(?!\.\.?\Z)[A-Za-z0-9._-]+")

# What git refuses in a branch name, rule by rule from git-check-ref-format(1)
# for the name under `refs/heads/`, and the leading `-` `--branch` adds.
_NOT_IN_BRANCH = re.compile(
    r"""
    [\x00-\x20\x7f~^:?*\[\\]  # a control character, a space, ~ ^ : ? * [, or a backslash
    | \.\. | @\{ | //            # a `..`, a `@{`, or an empty component
    | (?:^|/)\.                  # a component beginning with `.`
    | \.lock(?:/|$)              # a component ending in `.lock`
    | ^[-/] | [./]$              # a leading `-` or `/`, a trailing `.` or `/`
    """,
    re.VERBOSE,
)
# Names git reads as `HEAD` itself rather than as a branch.
_NOT_BRANCHES = frozenset(("@", "HEAD"))

_CLONE_ADVICE = "give the top of a local clone or linked worktree"
_BRANCH_ADVICE = "name the branch pull requests target, such as main"


class FieldError(ValueError):
    """An answer its field's validator refused; the text says why."""


def _absolute(raw: str) -> Path:
    """The absolute path ``raw`` names, walked the way the filesystem walks it.

    A leading ``~`` is expanded, and only a path still relative after that is
    taken from the current directory: an absolute one never asks for it, so a
    launch from a directory since removed still names its checkout. A ``..``
    steps to the parent of wherever the path so far really leads, as the
    kernel does, rather than back over the name before it: a ``link/..``
    beside a symlink into another directory is that directory's parent, not
    the link's. Like the kernel, it steps out only of a directory that is
    there, so a missing name or a file before it raises the ``OSError`` the
    lookup would. Every symlink no ``..`` steps out of stays as spelled.
    """
    spelled = Path(raw).expanduser()
    if not spelled.is_absolute():
        spelled = Path.cwd() / spelled
    walked = Path(spelled.anchor)
    for part in spelled.parts[1:]:
        if part != "..":
            walked /= part
            continue
        real = Path(os.path.realpath(walked, strict=True))
        if not real.is_dir():
            raise NotADirectoryError(errno.ENOTDIR, os.strerror(errno.ENOTDIR), str(walked))
        walked = real.parent
    return walked


def validate_clone(raw: str) -> Path:
    """The absolute path of the checkout ``raw`` names.

    A leading ``~`` is expanded, since a prompt hands the answer over without
    a shell, and a relative path is taken from the current directory. The
    path holds no ``..`` and keeps its symlinks as spelled wherever that names
    the same directory, which is how a ``REPOS`` entry names it: whatever
    later reads the entry, lexically or not, reaches this checkout.
    """
    typed = raw.strip()
    if not typed:
        raise FieldError(f"no clone was given; {_CLONE_ADVICE}")
    # `~user` naming no account, or a relative path under a current directory
    # that is gone, is an answer to refuse rather than a crash.
    try:
        clone = _absolute(typed)
    except (OSError, RuntimeError) as error:
        raise FieldError(f"{typed!r} cannot be read as a path ({error}); {_CLONE_ADVICE}") from error
    problem = checkout_problem(clone)
    if problem is not None:
        raise FieldError(f"{clone} {problem}; {_CLONE_ADVICE} of the repository")
    return clone


def validate_repository(raw: str) -> str:
    """The ``owner/name`` ``raw`` writes, without surrounding blanks."""
    repository = raw.strip()
    if _REPOSITORY.fullmatch(repository) is None:
        raise FieldError(
            f"repository {raw!r} is not written owner/name; give a GitHub "
            "owner and repository name joined by one '/', such as acme/api",
        )
    return repository


def validate_branch(raw: str) -> str:
    """The branch ``raw`` names, without surrounding blanks."""
    branch = raw.strip()
    if not branch:
        raise FieldError(f"no branch was given; {_BRANCH_ADVICE}")
    if branch in _NOT_BRANCHES or _NOT_IN_BRANCH.search(branch) is not None:
        raise FieldError(f"{branch!r} is not a name git allows for a branch; {_BRANCH_ADVICE}")
    return branch


def validate_logins(raw: str) -> tuple[str, ...]:
    """The GitHub logins ``raw`` lists, in order and each once."""
    # Each part as the configuration reads it: blanks and a leading `@` dropped.
    unmarked = (part.strip().lstrip("@") for part in raw.split(","))
    named = map(str.strip, unmarked)
    logins = tuple(dict.fromkeys(login for login in named if login))
    if not logins:
        raise FieldError(
            f"{raw!r} names no GitHub login; give at least one, separated by commas",
        )
    for login in logins:
        if _LOGIN.fullmatch(login) is None:
            raise FieldError(
                f"{login!r} is not a GitHub login; separate logins with commas",
            )
    return logins


def validate_agent(raw: str, search_path: str) -> str:
    """The agent ``raw`` names, once its executable is on ``search_path``."""
    agent = raw.strip()
    if agent not in AGENTS:
        raise FieldError(
            f"agent {raw!r} is not one the orchestrator runs; expected one of "
            f"{_AGENT_CHOICES}",
        )
    if shutil.which(agent, path=search_path) is None:
        raise FieldError(
            f"agent {agent!r} has no executable on PATH; install its CLI or "
            "add the directory holding it to PATH",
        )
    return agent
