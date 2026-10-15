# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The ``REPOS`` entry a clone implies, read off its GitHub remote.

A setup given only a clone reads the rest of its entry off the clone itself:
the repository a remote's URL names on GitHub, that remote's name, and the
branch pull requests target. That branch is the remote's default branch as the
clone recorded it -- ``refs/remotes/<remote>/HEAD``, which a ``git clone``
sets -- or, where the clone recorded none, the branch it has checked out.
Nothing is fetched, so the answer costs no network and no credential.

The remote is ``origin`` when it points at GitHub, and otherwise the only
remote that does, which the entry then records under its own name. A
repository the caller already chose narrows that to the remotes naming it;
where none does, an ``origin`` whose URL names no GitHub repository at all --
a host alias out of the SSH config, say -- is taken to be it, while one naming
another repository is not. A remote the caller named is used as named, its
URL supplying the repository unless the caller gave that too, in which case
the two have to agree wherever the URL says anything.

``clone_entry`` is the whole entry. Its two derivations are callable alone,
for a setup that asks for each field in turn and offers what the clone implies
as the default: ``github_remote`` chooses the remote and the repository it
stands for, and ``default_branch`` reads that remote's branch.

The URLs are read through ``git remote get-url``, so an ``insteadOf`` rewrite
applies before ``remote_urls`` reads them. Git runs through
``checkouts.ask_git``, pointed at the clone alone, so nothing here imports the
configuration.
"""
from __future__ import annotations

import os
import subprocess
from pathlib import Path

from orchestrator.service.checkouts import ask_git
from orchestrator.service.remote_urls import repository_from_url
from orchestrator.service.repos_entry import DEFAULT_REMOTE, RepositoryEntry
from orchestrator.service.validation import FieldError

_BRANCHES = "refs/heads/"

# Each remote's name, mapped to the GitHub repository its URL names, if any.
_Remotes = dict[str, str | None]


def _ask(clone: Path, *arguments: str) -> str:
    """What git prints for ``arguments`` in ``clone``; nothing when it fails."""
    try:
        answer = ask_git(clone, *arguments)
    except (OSError, subprocess.SubprocessError) as error:
        raise FieldError(f"{clone} cannot be inspected ({error})") from error
    return os.fsdecode(answer.stdout).strip() if answer.returncode == 0 else ""


def _candidates(remotes: _Remotes, repository: str | None) -> list[str]:
    """The remotes pointing at ``repository`` on GitHub, or at any repository there."""
    # GitHub reads an owner and a name without regard to case.
    on_github = {name: found.lower() for name, found in remotes.items() if found}
    if repository is None:
        return list(on_github)
    wanted = repository.lower()
    return [name for name, found in on_github.items() if found == wanted]


def _chosen_remote(clone: Path, remotes: _Remotes, repository: str | None) -> str:
    """The remote an entry records when the caller named none."""
    candidates = _candidates(remotes, repository)
    if DEFAULT_REMOTE in candidates:
        return DEFAULT_REMOTE
    if len(candidates) == 1:
        return candidates[0]
    if candidates:
        listed = ", ".join(candidates)
        raise FieldError(
            f"remotes {listed} of {clone} all point at GitHub and none is "
            "origin; say which repository or remote to use",
        )
    unread_origin = DEFAULT_REMOTE in remotes and remotes[DEFAULT_REMOTE] is None
    if repository is not None and unread_origin:
        return DEFAULT_REMOTE
    wanted = repository or "a repository"
    raise FieldError(
        f"no remote of {clone} points at {wanted} on GitHub; add one, or say "
        "which repository and remote to use",
    )


def _remote_repository(
    clone: Path,
    remotes: _Remotes,
    remote: str,
    repository: str | None,
) -> str:
    """The repository ``remote`` stands for, agreeing with any already chosen."""
    if remote not in remotes:
        raise FieldError(f"{clone} has no remote named {remote!r}")
    found = remotes[remote]
    if found is None:
        if repository is None:
            raise FieldError(
                f"remote {remote!r} of {clone} does not point at a GitHub "
                "repository; give the repository as owner/name",
            )
        return repository
    if repository is not None and found.lower() != repository.lower():
        raise FieldError(
            f"remote {remote!r} of {clone} points at {found} on GitHub, not {repository}",
        )
    return repository or found


def github_remote(
    clone: Path,
    *,
    repository: str | None = None,
    remote: str | None = None,
) -> tuple[str, str]:
    """The remote an entry for ``clone`` records, and the repository it stands for.

    ``clone`` has passed ``validation.validate_clone``, and a ``repository``
    given here its own validator.
    """
    remotes: _Remotes = {
        name: repository_from_url(_ask(clone, "remote", "get-url", name))
        for name in _ask(clone, "remote").split()
    }
    chosen = remote or _chosen_remote(clone, remotes, repository)
    return chosen, _remote_repository(clone, remotes, chosen, repository)


def default_branch(clone: Path, remote: str) -> str:
    """``remote``'s recorded default branch, else the one checked out."""
    remote_branches = f"refs/remotes/{remote}/"
    recorded = _ask(clone, "symbolic-ref", "--quiet", f"{remote_branches}HEAD")
    if recorded.startswith(remote_branches):
        return recorded.removeprefix(remote_branches)
    current = _ask(clone, "symbolic-ref", "--quiet", "HEAD")
    if current.startswith(_BRANCHES):
        return current.removeprefix(_BRANCHES)
    raise FieldError(
        f"{clone} records no default branch for {remote} and has no branch "
        "checked out; give the branch pull requests target",
    )


def clone_entry(
    clone: Path,
    *,
    repository: str | None = None,
    remote: str | None = None,
    base_branch: str | None = None,
) -> RepositoryEntry:
    """The entry ``clone`` implies, keeping each field the caller already chose.

    ``clone`` has passed ``validation.validate_clone``, and a ``repository``
    given here its own validator. A field the caller chose is not derived at
    all, so a clone with a detached ``HEAD`` still answers for a caller that
    names the base branch.
    """
    chosen, found = github_remote(clone, repository=repository, remote=remote)
    return RepositoryEntry(
        repository=found,
        clone=clone,
        base_branch=base_branch or default_branch(clone, chosen),
        remote=chosen,
    )
