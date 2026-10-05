# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""A host configured through `REPOS` alone, with one token file per repository.

Shared by the configuration, GitHub-client, git-transport, and worktree-path
tests that prove what each configured repository resolves on its own: no
`REPO`, `TARGET_REPO_ROOT`, or `WORKTREES_DIR`, no process `GITHUB_TOKEN`, and
no `ORCHESTRATOR_TOKEN_FILE`. Every target is a real checkout under one clones
directory, and every token sits at `<home>/.config/<owner>/<name>/token`.
"""
from __future__ import annotations

import importlib
import os
import tempfile
from collections.abc import Iterator, Mapping
from contextlib import AbstractContextManager, contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from unittest.mock import patch

from orchestrator.config import environment
from tests.support.git import _run_git

# Settings the process environment must not carry while a host is in force,
# so only the per-repository token files and `REPOS` can answer.
_HOST_OWNED_SETTINGS = frozenset((
    "REPO",
    "REPOS",
    "TARGET_REPO_ROOT",
    "WORKTREES_DIR",
    "GITHUB_TOKEN",
    "ORCHESTRATOR_TOKEN_FILE",
))
_HOME = "home"
_CLONES = "clones"


@dataclass(frozen=True)
class ReposHost:
    """The home, the clones directory, and the `REPOS` value naming them."""

    home: Path
    clones: Path
    repos: str

    def settings(self) -> dict[str, str]:
        """The two settings a REPOS-only launch carries: its home and REPOS."""
        return {"HOME": str(self.home), "REPOS": self.repos}

    def patched_process(self) -> AbstractContextManager[Any]:
        """The live process environment with this home and no host setting."""
        kept = {
            key: env_value
            for key, env_value in os.environ.items()
            if key not in _HOST_OWNED_SETTINGS
        }
        kept["HOME"] = str(self.home)
        return patch.dict(os.environ, kept, clear=True)

    def resolve(self) -> dict[str, Any]:
        """Run the settings resolver against this host with no `.env` read."""
        config = importlib.import_module("orchestrator.config")
        with self.patched_process():
            return environment._SettingsResolver(
                {**os.environ, **self.settings(), "ORCHESTRATOR_SKIP_DOTENV": "1"},
                config.REPO_ROOT,
                config._config_error,
                config._config_warning,
            ).resolve()


def _lay_out_repository(root: Path, slug: str, token: str) -> str:
    """Write one slug's token file and checkout, and return its REPOS entry."""
    token_file = root / _HOME / ".config" / slug / "token"
    token_file.parent.mkdir(parents=True)
    token_file.write_text(f"{token}\n")
    target = root / _CLONES / slug.replace("/", "__")
    target.mkdir(parents=True)
    _run_git("init", "-q", cwd=target)
    return f"{slug}|{target}|main"


@contextmanager
def repos_only_host(tokens: Mapping[str, str]) -> Iterator[ReposHost]:
    """Lay out one checkout and one token file per slug, in mapping order."""
    with tempfile.TemporaryDirectory() as scratch:
        # Resolved, so the worktree root derived from a target compares equal
        # wherever the temporary directory sits behind a symlink.
        root = Path(scratch).resolve()
        yield ReposHost(
            home=root / _HOME,
            clones=root / _CLONES,
            repos=";".join(
                _lay_out_repository(root, slug, token)
                for slug, token in tokens.items()
            ),
        )
