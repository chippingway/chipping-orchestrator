# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Credential and virtualenv filtering and git identity for agent subprocesses."""
from __future__ import annotations

import os

from orchestrator import config

_FORBIDDEN_AGENT_ENV = frozenset((
    "GITHUB_TOKEN",
    "GH_TOKEN",
    "GITHUB_PAT",
    "GH_ENTERPRISE_TOKEN",
    "GITHUB_ENTERPRISE_TOKEN",
    "GIT_TOKEN",
    "GH_HOST",
))
# Worktree commands must not use any inherited virtualenv or its executables.
# Conda's activation markers stay with its PATH entries for Conda-based targets.
_INHERITED_ENVIRONMENT_MARKERS = frozenset((
    "VIRTUAL_ENV",
))
_AGENT_WRITE_CREDENTIAL_LOCATORS = frozenset((
    "SSH_AUTH_SOCK",
    "SSH_ASKPASS",
    "GIT_ASKPASS",
    "GIT_SSH_COMMAND",
))
_AGENT_SECRET_SUFFIXES = (
    "_TOKEN",
    "_KEY",
    "_SECRET",
    "_PASSWORD",
    "_PAT",
    "_CREDENTIAL",
    "_TOKEN_FILE",
    "_KEY_FILE",
    "_SECRET_FILE",
    "_PASSWORD_FILE",
    "_CREDENTIAL_FILE",
    "_CREDENTIALS",
    "_CREDENTIALS_FILE",
)
_AGENT_SECRET_BARE_NAMES = frozenset((
    "TOKEN",
    "KEY",
    "SECRET",
    "PASSWORD",
    "PAT",
    "CREDENTIAL",
    "TOKEN_FILE",
    "CREDENTIALS",
    "CREDENTIALS_FILE",
))
_AGENT_PROVIDER_AUTH_ALLOWLIST = frozenset((
    "ANTHROPIC_API_KEY",
    "ANTHROPIC_AUTH_TOKEN",
    "CLAUDE_CODE_OAUTH_TOKEN",
    "OPENAI_API_KEY",
))


def is_secret_shaped(env_name: str) -> bool:
    """Return whether an environment name looks credential-bearing."""
    normalized_name = env_name.upper()
    if normalized_name in _AGENT_SECRET_BARE_NAMES:
        return True
    return any(
        normalized_name.endswith(secret_suffix)
        for secret_suffix in _AGENT_SECRET_SUFFIXES
    )


def _env_key_allowed(
    env_key: str,
    *,
    allow_provider_auth: bool,
) -> bool:
    if env_key in _FORBIDDEN_AGENT_ENV or env_key in _INHERITED_ENVIRONMENT_MARKERS:
        return False
    if env_key in _AGENT_WRITE_CREDENTIAL_LOCATORS:
        return False
    if not is_secret_shaped(env_key):
        return True
    return allow_provider_auth and env_key in _AGENT_PROVIDER_AUTH_ALLOWLIST


def filter_agent_env(
    environ: dict[str, str],
    *,
    allow_provider_auth: bool = True,
) -> dict[str, str]:
    """Remove write credentials, secrets, and inherited virtualenv activation."""
    filtered_env = {
        env_key: env_value
        for env_key, env_value in environ.items()
        if _env_key_allowed(
            env_key,
            allow_provider_auth=allow_provider_auth,
        )
    }
    virtualenv = environ.get("VIRTUAL_ENV")
    if virtualenv and "PATH" in filtered_env:
        filtered_env["PATH"] = _without_virtualenv_bin(filtered_env["PATH"], virtualenv)
    return filtered_env


def _without_virtualenv_bin(search_path: str, virtualenv: str) -> str:
    """Preserve PATH order while removing the inherited virtualenv's bin entries."""
    virtualenv_bin = os.path.normpath(os.path.join(virtualenv, "bin"))
    return os.pathsep.join(
        path_entry
        for path_entry in search_path.split(os.pathsep)
        if os.path.normpath(path_entry) != virtualenv_bin
    )


def agent_env(extra_env: dict[str, str] | None) -> dict[str, str]:
    """Build the filtered agent environment with orchestrator git identity."""
    environ = filter_agent_env(dict(os.environ))
    environ["GIT_AUTHOR_NAME"] = config.AGENT_GIT_NAME
    environ["GIT_AUTHOR_EMAIL"] = config.AGENT_GIT_EMAIL
    environ["GIT_COMMITTER_NAME"] = config.AGENT_GIT_NAME
    environ["GIT_COMMITTER_EMAIL"] = config.AGENT_GIT_EMAIL
    if extra_env:
        environ.update(extra_env)
    return environ
