# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""GitHub token lookup outside the repository checkout, and secret redaction.

Redaction lives beside the token resolver because the two answer one
question -- which strings in this process are credentials -- and because it
belongs below every consumer that needs it: agent-stderr diagnostics, verify
output, and the analytics trajectory sink all mask secrets, and reaching a
workflow-layer helper for that would point the dependency edge upwards.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

_SECRET_KEY_SUFFIXES = ("_TOKEN", "_KEY", "_SECRET", "_PASSWORD", "_PAT", "_CREDENTIAL")

_SECRET_KEY_NAMES = frozenset((
    "GITHUB_TOKEN", "GH_TOKEN", "GITHUB_PAT",
    "TOKEN", "KEY", "SECRET", "PASSWORD", "PAT", "CREDENTIAL",
))

_REDACT_MIN_VALUE_LEN = 8


def resolve_github_token(repo_slug: str) -> str:
    """Resolve a token from process env or the per-repository token file."""
    environment_token = os.environ.get("GITHUB_TOKEN", "").strip()
    if environment_token:
        return environment_token
    default_path = Path.home() / ".config" / repo_slug / "token"
    token_file = Path(
        os.environ.get("ORCHESTRATOR_TOKEN_FILE", str(default_path)),
    )
    try:
        return token_file.read_text().strip()
    except FileNotFoundError:
        return ""
    except OSError as error:
        sys.stderr.write(
            f"orchestrator: could not read token file {token_file}: {error}\n",
        )
        return ""


def is_secret_environment_value(key: str, env_value: str) -> bool:
    """Whether an environment entry is shaped like a usable secret."""
    if not env_value or len(env_value) < _REDACT_MIN_VALUE_LEN:
        return False
    upper_key = key.upper()
    return upper_key in _SECRET_KEY_NAMES or any(
        upper_key.endswith(suffix) for suffix in _SECRET_KEY_SUFFIXES
    )


def redact_environment_secrets(text: str) -> str:
    """Replace every secret-shaped process environment value."""
    redacted = text
    for key, env_value in os.environ.items():
        if is_secret_environment_value(key, env_value):
            redacted = redacted.replace(env_value, "***")
    return redacted


def redact_configured_github_token(text: str) -> str:
    """Redact the PAT even when it came from a token file, not the env."""
    # The resolved token is read off `orchestrator.config.settings` at call time, not
    # bound at import: this leaf is imported while that module is still
    # building its namespace, and the setting stays an independently
    # patchable module attribute that a settings reload rebinds.
    from orchestrator.config import settings as config

    token = config.GITHUB_TOKEN
    if token and len(token) >= _REDACT_MIN_VALUE_LEN:
        return text.replace(token, "***")
    return text


def redact_secrets(text: str) -> str:
    """Replace values of secret-shaped env vars in `text` with `***`.

    Called before any stderr is surfaced to GitHub or the log so a
    prompt-injected agent that echoes its own provider key cannot exfiltrate
    it via a park comment. Snapshot of os.environ at call time, so a key
    that was unset between subprocess spawn and the post is no longer
    redacted -- acceptable since it also no longer leaks anything reachable
    from the agent.
    """
    if not text:
        return text
    # GITHUB_TOKEN may have been resolved from ORCHESTRATOR_TOKEN_FILE (or
    # the default ~/.config/<repo>/token path) rather than the process env,
    # in which case the environment scan never sees it. The explicit token
    # pass also covers git/gh stderr that quotes a file-backed credential.
    return redact_configured_github_token(redact_environment_secrets(text))
