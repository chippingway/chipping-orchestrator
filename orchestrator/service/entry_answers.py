# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The ``REPOS`` entry a setup command's answers make, each refusal naming its option.

``configure`` and ``add-repo`` both take a clone and, unless an answer gives
them, read the rest of its entry off it through ``clone_defaults``: the
repository, its remote, and the branch pull requests target. ``add-repo`` can
also be told the remote and a parallel limit. ``answered_entry`` holds every
answer given to its field's validator before the clone is read, so a refused
answer is never mistaken for a clone that cannot be read, and then refuses the
clone and the base branch where the entry cannot carry them -- a branch read
off the clone included, since another ``--base-branch`` replaces it.

Each refusal names the option the answer was given as, in front of the
validator's own words, so a command line prints what a prompt asking for the
same field prints, only with the option in front. ``checked`` is that naming
for one answer, for a command to name one of its own the same way.

Nothing here imports ``orchestrator.config``: an entry is made on a host where
importing it would exit.
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace

from orchestrator.service.clone_defaults import clone_entry
from orchestrator.service.repos_entry import (
    RepositoryEntry,
    validate_parallel_limit,
    validate_remote,
    writable_field,
)
from orchestrator.service.validation import (
    FieldError,
    validate_branch,
    validate_clone,
    validate_repository,
)


def checked[Valid](
    option: str,
    validator: Callable[..., Valid],
    answer: str | None,
    *context: str,
) -> Valid | None:
    """What ``validator`` makes of ``answer``, a refusal naming ``option``.

    An answer not given stays ``None``, for the caller to default.
    """
    if answer is None:
        return None
    try:
        return validator(answer, *context)
    except FieldError as refused:
        raise FieldError(f"{option}: {refused}") from refused


def answered_entry(
    clone: str,
    repo: str | None = None,
    base_branch: str | None = None,
    *,
    remote: str | None = None,
    parallel: str | None = None,
) -> RepositoryEntry:
    """The entry ``clone`` makes with the answers given, every other field read off it.

    The names are the options the answers were given as.
    """
    chosen_clone = checked("--clone", validate_clone, clone)
    chosen = {
        "repository": checked("--repo", validate_repository, repo),
        "base_branch": checked("--base-branch", validate_branch, base_branch),
        "remote": checked("--remote", validate_remote, remote),
    }
    parallel_limit = checked("--parallel", validate_parallel_limit, parallel)
    entry = clone_entry(chosen_clone, **chosen)
    checked("--clone", writable_field, str(entry.clone))
    checked("--base-branch", writable_field, entry.base_branch)
    return replace(entry, parallel_limit=parallel_limit)
