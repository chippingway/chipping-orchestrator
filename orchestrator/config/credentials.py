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
from collections.abc import Iterable
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


def resolve_github_tokens(repo_slugs: Iterable[str]) -> tuple[str, ...]:
    """Every distinct token the given repositories resolve to, in their order.

    Each slug goes through `resolve_github_token`, so a process token or an
    `ORCHESTRATOR_TOKEN_FILE` still answers for all of them and otherwise each
    repository's own token file answers for it. A repository with no token
    adds nothing: its client and its git transport report that themselves.
    """
    return tuple(dict.fromkeys(
        token for token in map(resolve_github_token, repo_slugs) if token
    ))


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


def redact_configured_github_tokens(text: str) -> str:
    """Redact every configured repository's PAT, file-backed ones included."""
    # The resolved tokens are read off `orchestrator.config` at call time, not
    # bound at import: this leaf is imported while that module is still
    # building its namespace, and the setting stays an independently
    # patchable module attribute that a settings reload rebinds.
    from orchestrator import config

    redacted = text
    for token in config.GITHUB_TOKENS:
        if len(token) >= _REDACT_MIN_VALUE_LEN:
            redacted = redacted.replace(token, "***")
    return redacted


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
    # A repository's token may have been resolved from ORCHESTRATOR_TOKEN_FILE
    # (or its default ~/.config/<owner>/<repo>/token path) rather than the
    # process env, in which case the environment scan never sees it. The
    # explicit token pass also covers git/gh stderr that quotes a file-backed
    # credential.
    return redact_configured_github_tokens(redact_environment_secrets(text))
