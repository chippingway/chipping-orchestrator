# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Non-secret ``.env`` parsing and loading.

Split from the resolver in ``environment`` so the loader stays a small leaf:
``environment`` imports ``load_dotenv`` (and the shared truthy-value set) from
here, never the reverse. Secret keys are refused because the implementer agent
can read this file.

Which one file is read follows the layout ``layout.is_source_checkout``
proves. A source checkout reads the ``.env`` at its own root, the file
``run.sh`` reads too, and nothing else: one without that file loads none. Any
other layout is an installed package, which reads the user location
``~/.config/chipping-orchestrator/.env`` and never a ``.env`` beside the
package, since that root is an environment's ``site-packages``. The file's
directory is only where settings come from: no target repository or worktree
root is ever derived from it.
"""
from __future__ import annotations

from collections.abc import Callable, MutableMapping
from pathlib import Path

from orchestrator.config.layout import is_source_checkout

_SECRET_KEYS = frozenset((
    "GITHUB_TOKEN",
    "GH_TOKEN",
    "GITHUB_PAT",
    "GH_ENTERPRISE_TOKEN",
    "GITHUB_ENTERPRISE_TOKEN",
    "GIT_TOKEN",
))
_TRUE_VALUES = frozenset(("1", "true", "on", "yes"))

# Relative to the home directory, beside the `~/.config/<owner>/<repo>/token`
# files rather than inside any checkout or environment the package runs from.
_USER_DOTENV = Path(".config", "chipping-orchestrator", ".env")


def strip_dotenv_quotes(dotenv_value: str) -> str:
    """Strip one matched outer quote pair while preserving inner quotes."""
    stripped_value = dotenv_value.strip()
    if len(stripped_value) < 2:
        return stripped_value
    quote = stripped_value[0]
    if quote in ('"', "'") and stripped_value[-1] == quote:
        return stripped_value[1:-1]
    return stripped_value


def _load_entry(
    raw_line: str,
    env_path: Path,
    environ: MutableMapping[str, str],
    config_warning: Callable[[str], None],
) -> None:
    """Load one ``.env`` line, warning on and skipping secret keys."""
    line = raw_line.strip()
    if not line or line.startswith("#"):
        return
    raw_key, _sep, raw_value = line.partition("=")
    key = raw_key.strip()
    if key in _SECRET_KEYS:
        config_warning(
            f"orchestrator: ignoring {key} in {env_path}; the implementer "
            "agent can read this file. Move the token to "
            "~/.config/<owner>/<repo>/token (one per configured repository) "
            f"or export {key} before launching.",
        )
        return
    environ.setdefault(key, strip_dotenv_quotes(raw_value))


def dotenv_path(repo_root: Path) -> Path:
    """The one ``.env`` to read: a source checkout's own, else the user's."""
    if is_source_checkout(repo_root):
        return repo_root / ".env"
    return Path.home() / _USER_DOTENV


def load_dotenv(
    repo_root: Path,
    environ: MutableMapping[str, str],
    config_warning: Callable[[str], None],
) -> None:
    """Load safe entries from the selected ``.env`` into ``environ``."""
    if environ.get("ORCHESTRATOR_SKIP_DOTENV", "").strip().lower() in _TRUE_VALUES:
        return
    env_path = dotenv_path(repo_root)
    if not env_path.exists():
        return
    for raw_line in env_path.read_text().splitlines():
        _load_entry(raw_line, env_path, environ, config_warning)
