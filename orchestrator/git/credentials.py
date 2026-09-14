# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The per-repository token and the askpass session every git call spends it in.

The lookup, the askpass script, the detached environment, and the record built
from them sit on one owner because they are one decision about a secret: which
repository's token to read, how git is handed it, and how long the file that
prints it lives. A caller resolves a token here and opens a session around it,
and what it gets back is the shape a token-bearing call is spawned from -- a
URL naming the `x-access-token` username and nothing else, an environment
where the token sits as `$GIT_TOKEN` for the askpass script to print, and the
token itself, which the caller reads back to redact its own stderr. Nothing
here puts it in an argv, and that is the guarantee: `/proc/<pid>/cmdline` is
world-readable and the environment of another user's process is not.

The script lives for exactly the `with` block that opened the session --
written into a private temporary directory, owner-only because /tmp is not,
and removed on exit, so nothing that prints the token outlives the operation
it was written for.

Resolution is per repository rather than per process: a deployment serving
several slugs keeps one token file each, and a call authenticates with the one
belonging to the repo it names.

Three callers and no others: the two transports -- `branch_transport` and
`ref_transport` -- and the namespace listing in `ref_discovery`, each importing
this module directly. Nothing republishes these names, so a test intercepting
the session targets the owner that defines it.
"""
from __future__ import annotations

import logging
import os
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

from orchestrator.config import credentials as _config_credentials, models as _config_models, settings as config
from orchestrator.git import commands

# The channel is named for the git-plumbing domain rather than for this
# module's path: operators filter the rendered `orchestrator.git_plumbing`
# prefix and attach handlers to it, so a token this owner could not resolve
# reports where their filters already point.
log = logging.getLogger("orchestrator.git_plumbing")

_ASKPASS_MODE = 0o700

# What a token is replaced by wherever a caller reports a call's own output.
# Spelled once here rather than at each of them because the guarantee is one
# and belongs to the owner of the secret: nothing this package logs or hands
# back carries the credential it authenticated with.
_REDACTED = "***"


@dataclass(frozen=True)
class _GitAuthSession:
    """Token-bearing subprocess inputs scoped to one askpass directory."""

    token: str
    auth_url: str
    env: dict[str, str]


def _scrubbed(reported: str, token: str) -> str:
    """The output of a token-bearing call with the token taken out of it.

    Spent on the stderr every token-bearing caller logs a refusal with, and
    once more on the stderr a ref read hands back for somebody else to report.
    Neither is a place a credential may reach, and a call is not required to
    have leaked one for the scrub to be worth taking -- the URL git is handed
    names only the `x-access-token` username, so a token in that output is a
    route nobody predicted rather than a route anybody meant.
    """
    return (reported or "").replace(token, _REDACTED)


def _resolved_git_token(spec: _config_models.RepoSpec, operation: str) -> str | None:
    """Resolve a per-repository token and log an operation-specific error."""
    token = _config_credentials.resolve_github_token(spec.slug)
    if token:
        return token
    log.error(
        "GITHUB_TOKEN missing for %s; cannot %s", spec.slug, operation,
    )
    return None


def _git_auth_env(
    askpass: Path, token: str, *, include_identity: bool,
) -> dict[str, str]:
    """Build the detached environment for one token-bearing git command."""
    auth_env = {
        **os.environ,
        **commands._GIT_NO_PROMPT_ENV,
        "GIT_ASKPASS": str(askpass),
        "GIT_TOKEN": token,
        "GIT_CONFIG_GLOBAL": os.devnull,
        "GIT_CONFIG_SYSTEM": os.devnull,
        "GIT_CONFIG_NOSYSTEM": "1",
    }
    if include_identity:
        auth_env.update(
            {
                "GIT_AUTHOR_NAME": config.AGENT_GIT_NAME,
                "GIT_AUTHOR_EMAIL": config.AGENT_GIT_EMAIL,
                "GIT_COMMITTER_NAME": config.AGENT_GIT_NAME,
                "GIT_COMMITTER_EMAIL": config.AGENT_GIT_EMAIL,
            },
        )
    return auth_env


@contextmanager
def _git_auth_session(
    spec: _config_models.RepoSpec, token: str, *, include_identity: bool = False,
) -> Iterator[_GitAuthSession]:
    """Keep a hardened askpass script alive for one authenticated operation."""
    with tempfile.TemporaryDirectory(prefix="orch-askpass-") as temp_dir:
        askpass = Path(temp_dir) / "askpass.sh"
        askpass.write_text('#!/bin/sh\nprintf %s "$GIT_TOKEN"\n')
        askpass.chmod(_ASKPASS_MODE)
        yield _GitAuthSession(
            token=token,
            auth_url=f"https://x-access-token@github.com/{spec.slug}.git",
            env=_git_auth_env(
                askpass, token, include_identity=include_identity,
            ),
        )
