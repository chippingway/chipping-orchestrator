# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""One repository's questions in an onboarding: its clone, its name, its branch, and its token.

Each question offers what the answers before it imply as its default, and
holds its answer to the validator ``configure`` and ``add-repo`` hold the same
field to, so a refusal prints their words and the question is asked again:

- the clone: ``validate_clone``, and a path a ``REPOS`` entry can carry. The
  first repository's clone defaults to the current directory where that is
  the top of a checkout; a further one has no default;
- the repository: ``validate_repository``, refused where an earlier
  repository of the same onboarding already named it -- compared as GitHub
  compares names, without regard to case -- and then the remote
  ``clone_defaults.github_remote`` chooses for it, as ``configure`` and
  ``add-repo`` do, so one the clone has no remote for is refused here with
  that derivation's message rather than after the last question. It
  defaults to the repository the clone's GitHub remote names;
- the branch: ``validate_branch``, and a name the entry can carry, defaulting
  to ``clone_defaults.default_branch``: that remote's default branch, else
  the one checked out;
- the token: through ``token_questions``, which keeps one already stored.

A default the clone does not imply is not offered, so its question waits for
an answer. Nothing here writes anything.
"""
from __future__ import annotations

import os
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from functools import partial
from pathlib import Path
from typing import TextIO

from orchestrator.service.clone_defaults import default_branch, github_remote
from orchestrator.service.questions import ask_until
from orchestrator.service.repos_entry import writable_field
from orchestrator.service.token_questions import ask_token
from orchestrator.service.validation import FieldError, validate_branch, validate_clone, validate_repository

# How many questions a repository is asked, numbered among the onboarding's
# own for the first one.
_FIRST = 6
_FURTHER = 4

_CHOSEN = "{0} is already among the repositories given above; give another one"


@dataclass(frozen=True)
class RepositoryAnswers:
    """What one repository was answered with, and the token to save for it.

    ``token`` is ``None`` where the repository's token file was kept, and
    ``owner`` the login the token belongs to, where GitHub said.
    """

    clone: Path
    repository: str
    base_branch: str
    token: str | None
    owner: str | None


def ask_repository(stdin: TextIO, shell: Mapping[str, str], chosen: Sequence[str]) -> RepositoryAnswers:
    """Ask for one repository at ``stdin``, after the ``chosen`` ones.

    With none chosen it is the first repository, numbered among the
    onboarding's questions and offered the current directory as its clone.
    An exported ``GITHUB_TOKEN`` in ``shell`` is offered as its token.
    """
    total = _FURTHER if chosen else _FIRST
    clone, remote, repository = _located(stdin, total, chosen)
    base_branch = ask_until(
        stdin,
        f"[3/{total}] Branch pull requests target",
        _branch,
        _offered(partial(default_branch, clone, remote)),
    )
    return RepositoryAnswers(
        clone,
        repository,
        base_branch,
        *ask_token(f"[4/{total}] GitHub token for {repository}", repository, shell.get("GITHUB_TOKEN")),
    )


def _located(stdin: TextIO, total: int, chosen: Sequence[str]) -> tuple[Path, str, str]:
    """The clone asked for, the remote its repository is reached through, and that repository."""
    clone = ask_until(
        stdin,
        f"[1/{total}] Local clone of the repository to manage",
        _clone,
        None if chosen else _offered(partial(validate_clone, os.curdir)),
    )
    remote, repository = ask_until(
        stdin,
        f"[2/{total}] GitHub repository (owner/name)",
        partial(_repository, clone=clone, chosen=chosen),
        _offered(lambda: github_remote(clone)[1]),
    )
    return clone, remote, repository


def _clone(answer: str) -> Path:
    """The checkout ``answer`` names, refused where an entry cannot carry its path."""
    clone = validate_clone(answer)
    writable_field(str(clone))
    return clone


def _repository(answer: str, *, clone: Path, chosen: Sequence[str]) -> tuple[str, str]:
    """The remote of ``clone`` that reaches the repository ``answer`` names, and that repository."""
    repository = validate_repository(answer)
    if repository.lower() in {named.lower() for named in chosen}:
        raise FieldError(_CHOSEN.format(repository))
    remote, _ = github_remote(clone, repository=repository)
    return writable_field(remote), repository


def _branch(answer: str) -> str:
    """The branch ``answer`` names, refused where an entry cannot carry it."""
    return writable_field(validate_branch(answer))


def _offered(derive: Callable[[], object]) -> str | None:
    """What ``derive`` reads as a default, or none where it refuses to."""
    try:
        return str(derive())
    except FieldError:
        return None
