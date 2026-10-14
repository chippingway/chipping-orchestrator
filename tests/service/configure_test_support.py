# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What the `configure` tests share: a home to write into, agents, and a clone."""
from __future__ import annotations

import os
import stat
import tempfile
import unittest
from pathlib import Path
from types import MappingProxyType
from unittest.mock import patch

from orchestrator.service.configure import ConfigureAnswers, ConfigureRefusal, configure
from orchestrator.service.templates import BASIC_TEMPLATE, template_text
from tests.service.service_test_support import add_remote
from tests.support.checkouts import committed_checkout

ACME = "acme/api"
ACME_URL = "https://github.com/acme/api.git"
ORIGIN = "origin"
TRUNK = "trunk"
CLAUDE = "claude"
CODEX = "codex"
AUTHOR = "alice"
ENCODING = "utf-8"
PRIVATE_DIRECTORY = 0o700
PRIVATE_FILE = 0o600
SETTINGS_FILE = Path(".config", "chipping-orchestrator", ".env")
LOG_DIR = Path(".local", "state", "chipping-orchestrator", "logs")
# Exported where `configure` runs, and never to be found in what it writes.
TOKEN = "ghp_exported_token"
HERMETIC_GIT = MappingProxyType({
    "GIT_CONFIG_GLOBAL": os.devnull,
    "GIT_CONFIG_SYSTEM": os.devnull,
})

# The settings `configure` sets on the template's own lines.
_SET_KEYS = frozenset((
    "REPOS", "HITL_HANDLE", "ALLOWED_ISSUE_AUTHORS", "DEV_AGENT", "REVIEW_AGENT", "DECOMPOSE_AGENT",
))
_TEMPLATE_LINES = tuple(template_text(BASIC_TEMPLATE).splitlines(keepends=True))
_TEMPLATE_LENGTH = len(_TEMPLATE_LINES)


def mode(path: Path) -> int:
    """The permission bits of ``path``."""
    return stat.S_IMODE(path.stat().st_mode)


def install_agents(directory: Path, *agents: str) -> None:
    """Put an executable named for each agent in ``directory``."""
    directory.mkdir(exist_ok=True)
    for agent in agents:
        executable = directory / agent
        executable.write_text("#!/bin/sh\n")
        executable.chmod(stat.S_IRWXU)


def existing_refusal(settings_file: Path) -> str:
    """The words ``configure`` refuses a ``.env`` already in its way with."""
    return (
        f"{settings_file} already exists, and configure never overwrites it; "
        "edit that file, or move it aside to write a new one"
    )


class ConfigureCase(unittest.TestCase):
    """An empty home, the default agents on a PATH of their own, and a clone.

    The clone's `origin` points at acme/api and records `trunk` as its
    default branch, and git runs detached from the host's own config. The
    package is answered for as an installed one, its root no checkout, and
    a token is exported.
    """

    def setUp(self) -> None:
        self._scratch = Path(self.enterContext(tempfile.TemporaryDirectory())).resolve()
        self._home = self._scratch / "home"
        self._home.mkdir()
        self.enterContext(patch.dict(os.environ, {
            "HOME": str(self._home),
            "GITHUB_TOKEN": TOKEN,
            **HERMETIC_GIT,
        }))
        self._bin = self._scratch / "bin"
        install_agents(self._bin, CLAUDE, CODEX)
        self._clone = committed_checkout(self._scratch / "clone")
        add_remote(self._clone, ORIGIN, ACME_URL, TRUNK)
        self._package_root = self._scratch
        self._settings_file = self._home / SETTINGS_FILE
        self._log_dir = self._home / LOG_DIR
        self._log_line = f"LOG_DIR={self._log_dir}\n"

    def _configure(self, **answers: str) -> Path:
        """Run the core with the clone and one author unless ``answers`` say otherwise."""
        chosen = ConfigureAnswers(**{"clone": str(self._clone), "authors": AUTHOR, **answers})
        return configure(chosen, search_path=str(self._bin), package_root=self._package_root)

    def _refused(self, **answers: str) -> str:
        """The words ``configure`` refuses ``answers`` with, other than a field's."""
        try:
            self._configure(**answers)
        except ConfigureRefusal as refused:
            return str(refused)
        raise AssertionError(f"configure wrote {self._settings_file} for {answers!r}")

    def _set_lines(self) -> tuple[str, ...]:
        """The lines the written `.env` sets, once every other line is found kept.

        The template's lines come back in order, each as it was but the live
        line of each setting `configure` sets; a blank line and `LOG_DIR`
        follow them.
        """
        text = self._settings_file.read_text(encoding=ENCODING)
        written = text.splitlines(keepends=True)
        self.assertEqual(written[_TEMPLATE_LENGTH:], ["\n", self._log_line])
        set_lines = []
        for before, after in zip(_TEMPLATE_LINES, written, strict=False):
            if before.partition("=")[0] in _SET_KEYS:
                set_lines.append(after.removesuffix("\n"))
            else:
                self.assertEqual(after, before)
        return tuple(set_lines)
