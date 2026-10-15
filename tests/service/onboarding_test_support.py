# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What the onboarding tests share: an empty home, two clones, agents, and `init` run at a terminal.

`init` runs in process, as `terminal_test_support` types the case's answers
at it, with GitHub the fake that knows each repository's token as alice's,
systemd the fake the `init` tests answer from, and the check a stand-in that
records that it ran and finds nothing.
"""
from __future__ import annotations

import os
import tempfile
import unittest
from contextlib import chdir
from pathlib import Path
from unittest.mock import patch

from orchestrator.service import checks, systemd, token_probe
from tests.service import (
    configure_test_support as _configure,
    init_test_support as _init,
    terminal_test_support as _terminal,
)
from tests.service.service_test_support import add_remote
from tests.support.checkouts import committed_checkout

API = "acme/api"
WEB = "acme/web"
TRUNK = "trunk"
MAIN = "main"
AUTHOR = "alice"
API_TOKEN = "ghp_api_token"
WEB_TOKEN = "ghp_web_token"
SETTINGS_FILE = _configure.SETTINGS_FILE
UNIT_FILE = _init.UNIT_DIR / _init.UNIT
API_TOKEN_FILE = _init.TOKEN_FILE
# Enter at each question after a repository's token: the authors, the people
# to mention, the agents, another repository, and writing the setup.
AFTER_TOKEN = ("", "", "", "", "")
WEB_TOKEN_FILE = Path(".config", WEB, "token")


def read(path: Path) -> str:
    """What the file at ``path`` holds."""
    return path.read_text(encoding=_configure.ENCODING)


def beneath(message: str) -> str:
    """``message`` as it is printed beneath the question whose answer it refuses."""
    return f"      {message}\n"


def _clone(root: Path, url: str, default_branch: str) -> str:
    """A committed clone at ``root`` whose `origin` is ``url``, recording ``default_branch``."""
    clone = committed_checkout(root)
    add_remote(clone, "origin", url, default_branch)
    return str(clone)


class OnboardingCase(unittest.TestCase):
    """An empty home, clones of acme/api and acme/web, and the default agents on a PATH of their own.

    The api clone's `origin` records `trunk` as its default branch, and the
    web clone's `main`; each clone is held as the path typed to name it. The
    shell exports no token, the current directory is no checkout, the
    package is answered for as an installed one, and GitHub knows each
    repository's token as alice's.
    """

    def setUp(self) -> None:
        self._scratch = Path(self.enterContext(tempfile.TemporaryDirectory())).resolve()
        self.home = self._scratch / "home"
        self.home.mkdir()
        hermetic = {"HOME": str(self.home), **_configure.HERMETIC_GIT}
        self.enterContext(patch.dict(os.environ, hermetic))
        os.environ.pop("GITHUB_TOKEN", None)
        self.api = _clone(self._scratch / "api", "https://github.com/acme/api.git", TRUNK)
        self.web = _clone(self._scratch / "web", "git@github.com:acme/web.git", MAIN)
        self.shell = {"HOME": str(self.home), "USER": AUTHOR}
        self.install_agents(_configure.CLAUDE, _configure.CODEX)
        self._fake_host()

    def install_agents(self, *agents: str) -> None:
        """Give the shell a ``PATH`` holding exactly ``agents``."""
        directory = Path(tempfile.mkdtemp(dir=self._scratch))
        _configure.install_agents(directory, *agents)
        self.shell["PATH"] = str(directory)

    def run_init(self, *answers: str) -> _terminal.Run:
        """Run ``init`` at a terminal typed ``answers``, one line each."""
        return _terminal.typed_init(self.shell, self._scratch, answers)

    def onboarded(self, *answers: str) -> str:
        """The transcript of an ``init`` typed ``answers``, once it is found to have succeeded."""
        run = self.run_init(*answers)
        self.assertEqual((run.status, run.stderr), (0, ""), run.transcript)
        return run.transcript

    def refused(self, *answers: str) -> str:
        """What an ``init`` typed ``answers`` refused with, once the home is found as empty as it began."""
        run = self.run_init(*answers)
        self.assertEqual(run.status, 1, run.transcript)
        self.assertEqual(list(self.home.iterdir()), [], run.transcript)
        return run.stderr.removesuffix("\n")

    def _fake_host(self) -> None:
        """Stand GitHub, systemd, and the check in for the case, from a directory that is no checkout."""
        elsewhere = self._scratch / "elsewhere"
        elsewhere.mkdir()
        self.enterContext(chdir(elsewhere))
        self.github = _terminal.TokenGitHub({API_TOKEN: AUTHOR, WEB_TOKEN: AUTHOR})
        self.enterContext(patch.object(token_probe, "http_get", self.github))
        self.timeline: list[tuple[str, ...]] = []
        self.enterContext(patch.object(systemd, "run_command", _init.FakeSystemd(self.timeline)))
        self.enterContext(patch.object(checks, "problems", self._check))

    def _check(self, shell: object, *, reach_github: bool) -> list[str]:
        """Record that the check ran, and find nothing."""
        self.timeline.append(_init.CHECKED)
        return []
