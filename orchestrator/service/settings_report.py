# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What keeps the settings this process resolves from running the service.

``checks`` runs ``report`` in a fresh interpreter started in the service's
environment and its home, so the settings are read there as the service's own
process reads them: the installed ``.env``, over ``HOME``, ``USER``, and the
captured ``PATH`` alone. It never runs in the process that asked, since
importing ``orchestrator.config`` resolves the settings against the importing
process's environment and exits on an invalid one -- which is why the import
waits for the call.

Each problem is one line, found in this order:

- The package runs from its own source checkout, which reads the ``.env`` at
  its root rather than the installed one: the refusal every setup command
  gives it, and nothing else. It is answered here, under the service's
  environment, by the same call the configuration makes to choose the ``.env``
  it loads, so no git setting the asking shell exports can tell the two apart.
- The settings do not resolve: the configuration's own diagnostic, a line for
  each line of it, so every target that is not a checkout is named at once.
  Nothing else is known then, so nothing else is checked.
- The author allowlist names nobody: the refusal every launch makes.
- A repository has no token, naming the file it would be read from, or that
  file cannot be read, with the error reading it raised. With
  ``REACH_GITHUB``, a repository GitHub does not let its token read, asked
  through ``token_probe`` with one read-only call per repository from this
  process, which reaches GitHub through the network settings the service has.
- An agent a role runs cannot be launched: the binary is the one
  ``CLAUDE_BIN``, ``CODEX_BIN``, or ``AGY_BIN`` names for the backend each
  role's spec starts with. A bare name has to be an executable on ``PATH``,
  and an absolute path an executable there. A relative path holding a
  directory is refused outright: each agent is started in its issue's
  worktree, which is where such a path would be read from.

The report is a JSON list of the problem lines on standard output, and
nothing else is written there, so no token leaves this process. What the
configuration warns about on standard error as it loads goes to ``checks``,
which holds it back: an unreadable token file it warns about is reported here
as the one problem it is, and a warning that stops nothing is not a problem.
"""
from __future__ import annotations

import importlib
import json
import os
import shutil
import sys
from collections.abc import Callable
from pathlib import Path
from types import MappingProxyType, ModuleType

from orchestrator.service import paths
from orchestrator.service.token_probe import ProbeError, reach_repository

COMMAND = "check"

# The argument asking for the GitHub calls as well as the local checks.
REACH_GITHUB = "--reach-github"

_SETTINGS = "orchestrator.config"

_ROLES = ("DEV_AGENT", "REVIEW_AGENT", "DECOMPOSE_AGENT")

# The setting naming the executable each backend runs as.
_EXECUTABLES = MappingProxyType({
    "claude": "CLAUDE_BIN",
    "codex": "CODEX_BIN",
    "agy": "AGY_BIN",
})

_TOKEN_FILE_SETTING = "ORCHESTRATOR_TOKEN_FILE"


def report(arguments: list[str]) -> None:
    """Write what keeps the service from running to standard output, as JSON."""
    refusal = paths.source_checkout_refusal(COMMAND)
    found = _problems(reach_github=REACH_GITHUB in arguments) if refusal is None else [refusal]
    json.dump(found, sys.stdout)


def _problems(*, reach_github: bool) -> list[str]:
    """Every problem with the settings this process resolves, a line each."""
    unresolved = _stopped(importlib.import_module, _SETTINGS)
    if unresolved:
        return unresolved
    from orchestrator.runtime import startup

    config = importlib.import_module(_SETTINGS)
    found = _stopped(startup.require_issue_authors)
    for spec in config.default_repo_specs():
        found.extend(_repository_problems(config, spec.slug, reach_github=reach_github))
    found.extend(_agent_problems(config))
    return found


def _stopped(step: Callable[..., object], *arguments: str) -> list[str]:
    """What stops ``step`` the way a start is stopped, a line each, if anything does."""
    # A value the resolver cannot parse, or a `.env` it cannot read, stops it
    # with the error itself rather than with a diagnostic of its own.
    try:
        step(*arguments)
    except SystemExit as refused:
        return str(refused).splitlines() or [f"orchestrator: the start was refused (exit status {refused.code})"]
    except (OSError, ValueError) as error:
        return [f"orchestrator: the settings cannot be read ({error})"]
    return []


def _repository_problems(config: ModuleType, slug: str, *, reach_github: bool) -> list[str]:
    """What is wrong with ``slug``'s token: none found, or GitHub refusing it when asked."""
    token = config.credentials.resolve_github_token(slug)
    if not token:
        return [_tokenless(slug, config.credentials.token_file(slug))]
    if reach_github:
        try:
            reach_repository(token, slug)
        except ProbeError as refused:
            return [f"{slug}: {refused}"]
    return []


def _tokenless(slug: str, path: Path) -> str:
    """Why ``slug`` has no token in ``path``: the file is missing or empty, or unreadable."""
    overridden = _TOKEN_FILE_SETTING in os.environ
    named = f"{path}, the file {_TOKEN_FILE_SETTING} names" if overridden else str(path)
    try:
        path.read_bytes()
    except OSError as error:
        if not isinstance(error, FileNotFoundError):
            return f"{slug}: {named} cannot be read ({error})"
    advice = "" if overridden else f"; store one with chipping-orchestrator set-token {slug}"
    return f"{slug}: no GitHub token in {named}{advice}"


def _agent_problems(config: ModuleType) -> list[str]:
    """Each agent binary a role runs that cannot be launched.

    A binary is named once, with every role that runs it.
    """
    runs: dict[str, list[str]] = {}
    for role in _ROLES:
        runs.setdefault(_EXECUTABLES[getattr(config, role)], []).append(role)
    return [
        problem
        for setting, roles in runs.items()
        for problem in _unlaunchable(setting, getattr(config, setting), roles)
    ]


def _unlaunchable(setting: str, binary: str, roles: list[str]) -> list[str]:
    """Why ``binary``, which ``setting`` names for ``roles``, cannot be launched, if it cannot."""
    named = ", ".join(roles)
    if os.path.dirname(binary) and not os.path.isabs(binary):
        return [(
            f"{named}: {setting} {binary!r} is a relative path, which each agent would read from its "
            "own worktree; give an absolute path, or a name on the service's PATH"
        )]
    if shutil.which(binary) is None:
        return [f"{named}: {setting} {binary!r} is not an executable on the service's PATH"]
    return []
