# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Where the running package sits, and where an installed one keeps its setup.

``PACKAGE_ROOT`` is the directory the running ``orchestrator`` package was
imported from. ``is_source_checkout`` tells this project's own source checkout
-- an ordinary clone, a linked worktree, or an editable install of either, all
of which run the package from inside the checkout -- apart from an installed
distribution, whose package root is an environment's ``site-packages``. It is
proved at that root alone: a ``pyproject.toml`` naming this project there, and
git opening that root as the top of a checkout, as ``checkouts`` asks it. So
neither an unrelated repository enclosing an installed environment nor the
directory a run was launched from can stand in for one, and an installed
package launched from inside some checkout of this project is still installed.

An installed package keeps its settings in ``~/.config/chipping-orchestrator``,
the ``.env`` there being the one file the configuration loads for it, and a
setup points its ``LOG_DIR`` at ``~/.local/state/chipping-orchestrator/logs``.
Both are read off the home directory at call time, so a caller that runs with
another ``HOME`` gets that home's paths. A source checkout reads its own
``.env`` instead, so a command that writes the installed one would set up a
file the package running it never reads, and one that checks what an installed
service reads would check another file: ``source_checkout_refusal`` is the
message every such command refuses with.

Nothing here imports from the package but ``checkouts``. A setup reads these
on a host with no configuration, and ``orchestrator.config`` reads them back
to choose the ``.env`` it loads and whether the developer fallback is offered.
"""
from __future__ import annotations

import tomllib
from pathlib import Path

from orchestrator.service.checkouts import checkout_problem

# `orchestrator/service/` is two levels beneath the root the package sits in.
PACKAGE_ROOT = Path(__file__).resolve().parents[2]

_PROJECT_NAME = "chipping-orchestrator"

# Relative to the home directory, beside the `~/.config/<owner>/<repo>/token`
# files rather than inside any checkout or environment the package runs from.
_SETTINGS_DIR = Path(".config", _PROJECT_NAME)
_LOG_DIR = Path(".local", "state", _PROJECT_NAME, "logs")


def _names_this_project(root: Path) -> bool:
    """Whether ``root/pyproject.toml`` declares this distribution."""
    try:
        manifest = tomllib.loads(
            (root / "pyproject.toml").read_text(encoding="utf-8"),
        )
    except (OSError, UnicodeDecodeError, tomllib.TOMLDecodeError):
        return False
    project = manifest.get("project")
    return isinstance(project, dict) and project.get("name") == _PROJECT_NAME


def is_source_checkout(package_root: Path) -> bool:
    """Whether the package runs from this project's own source checkout."""
    # The manifest is read first: an installed root has none, and is then
    # answered without starting git.
    return (
        _names_this_project(package_root)
        and checkout_problem(package_root) is None
    )


def settings_dir() -> Path:
    """The directory an installed package's ``.env`` sits in."""
    return Path.home() / _SETTINGS_DIR


def settings_file() -> Path:
    """The ``.env`` an installed package loads its settings from."""
    return settings_dir() / ".env"


def log_dir() -> Path:
    """The log directory a setup gives an installed package."""
    return Path.home() / _LOG_DIR


def source_checkout_refusal(command: str, package_root: Path = PACKAGE_ROOT) -> str | None:
    """Why ``command`` refuses to run from ``package_root``, or ``None``.

    Only a source checkout is refused. It reads the ``.env`` at its own root,
    so the message sends the developer to the checkout's own setup guide and
    restart wrapper rather than to the installed file the command writes or
    checks.
    """
    if not is_source_checkout(package_root):
        return None
    installed = settings_file()
    own = package_root / ".env"
    guide = package_root / "docs" / "development.md"
    wrapper = package_root / "run.sh"
    return (
        f"chipping-orchestrator {command} is for an installed package, but this "
        f"one runs from the source checkout at {package_root}, which reads {own} "
        f"rather than {installed}; set the checkout up as {guide} describes and "
        f"launch it with {wrapper}"
    )
