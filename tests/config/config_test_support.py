# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Focused setup helpers for configuration parsing tests."""

from __future__ import annotations

import os
import sys
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from types import ModuleType
from unittest.mock import patch

from orchestrator.config import _dotenv
from tests.config import config_reload_helpers as _reload, config_test_values as _config_cases
from tests.support.git import _run_git

_AGENT_DEFAULTS = (
    (_config_cases._DEV_AGENT_ENV, _config_cases._CLAUDE),
    (_config_cases._REVIEW_AGENT_ENV, _config_cases._CODEX),
)


def make_checkout(root: Path, project_name: str = "chipping-orchestrator") -> Path:
    """Make ``root`` a git checkout whose ``pyproject.toml`` names a project."""
    root.mkdir(parents=True, exist_ok=True)
    (root / "pyproject.toml").write_text(f'[project]\nname = "{project_name}"\n')
    _run_git("init", "-q", "-b", "main", cwd=root)
    return root


@contextmanager
def target_checkout() -> Iterator[str]:
    """A temporary git checkout, the kind of directory a target has to be."""
    with tempfile.TemporaryDirectory() as td:
        make_checkout(Path(td))
        yield td


def only_repo_spec(specs):
    if len(specs) != 1:
        raise AssertionError(f"expected one repo spec, got {len(specs)}")
    return specs[0]


def exit_with_config_error(message: str) -> None:
    sys.exit(message)


class ConfigErrorRecorder:
    def __init__(self, errors: list[str]) -> None:
        self._errors = errors

    def __call__(self, message: str) -> None:
        self._errors.append(message)
        sys.exit(message)


def _apply_agent_specs(config: ModuleType) -> None:
    for role, default in _AGENT_DEFAULTS:
        backend, arguments = config._parse_agent_spec(
            role,
            os.environ.get(role, default),
        )
        setattr(config, role, backend)
        setattr(config, f"{role}_ARGS", arguments)


def load_config_from_dotenv(
    dotenv_body: str,
    *,
    extra_environment: dict[str, str] | None = None,
) -> ModuleType:
    """Load a detached config module against one temporary dotenv file."""
    # `PATH` is kept so the source-checkout proof can find git.
    environment = {
        "PATH": os.environ.get("PATH", os.defpath),
        _config_cases._SKIP_DOTENV_ENV: _config_cases._ENABLED_ENV,
        _config_cases._TOKEN_FILE_ENV: _config_cases._MISSING_TOKEN_PATH,
    }
    if extra_environment:
        environment.update(extra_environment)
    config = _reload.load_config(environment)
    with tempfile.TemporaryDirectory() as temp_root:
        # A source checkout, so its own `.env` is the file the loader picks.
        make_checkout(Path(temp_root))
        Path(temp_root, ".env").write_text(dotenv_body)
        with patch.dict(os.environ, environment, clear=True):
            os.environ.pop(_config_cases._SKIP_DOTENV_ENV, None)
            for key in _config_cases._DOTENV_OWNED_KEYS:
                os.environ.pop(key, None)
            # The `.env` loader is named on its owner and handed the root to
            # read it from, so what the detached module resolved at import does
            # not decide what this body loads.
            _dotenv.load_dotenv(
                Path(temp_root), os.environ, config._config_warning,
            )
            _apply_agent_specs(config)
    return config
