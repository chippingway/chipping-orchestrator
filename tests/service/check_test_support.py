# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What the `check` tests share: an installed package with a fake GitHub, and a host to check.

`check` resolves the settings and makes its GitHub calls in an interpreter of
its own, whose environment holds `HOME`, `USER`, and `PATH` alone, so a fake
patched into this process would never be asked there. The installed copy
carries it instead: `token_probe.http_get`, the seam a test stands a fake
GitHub in for, is rebound at the end of the copy's own module to one that
answers from a table beside the package and records each request beside it,
which every process importing the copy reads. Each command runs from that copy
in a fresh interpreter, launched from an unrelated directory, so neither this
checkout's `.env` nor anything an earlier import resolved stands in for what
the command reads.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from tests.service.configure_test_support import CLAUDE, CODEX, install_agents
from tests.support.checkouts import make_checkout
from tests.support.installed_package import installed_copy

API = "acme/api"
WEB = "acme/web"
# What each repository's token file holds: a stand-in only the fake GitHub
# accepts.
API_STAND_IN = "stand-in-api"
WEB_STAND_IN = "stand-in-web"
OK = 200
ENCODING = "utf-8"
LOCAL = "--local"
# The refusal every launch makes on an allowlist that names nobody.
ALLOWLIST_REFUSAL = (
    "ALLOWED_ISSUE_AUTHORS must contain at least one GitHub login. Configure it "
    "before starting the orchestrator, for example: ALLOWED_ISSUE_AUTHORS=alice,bob"
)

_GITHUB_API = "https://api.github.com"
_FAKE_GITHUB = "fake-github"
_ANSWERS = "answers.json"
_REQUESTS = "requests.jsonl"
_RUN_TIMEOUT_SECONDS = 120

# Rebinds the copy's `http_get` to the fake: the module looks the name up when
# it calls it, so its own probes reach the fake too.
_FAKE_HTTP_GET = f'''

def http_get(url, token):
    """Answer from the test's table beside this package, recording the request."""
    import json
    from pathlib import Path

    fake = Path(__file__).resolve().parents[2] / "{_FAKE_GITHUB}"
    with (fake / "{_REQUESTS}").open("a", encoding="{ENCODING}") as requests:
        requests.write(json.dumps([url, token]) + "\\n")
    answers = json.loads((fake / "{_ANSWERS}").read_text(encoding="{ENCODING}"))
    status, document = answers[url.removeprefix(API_ROOT)]
    return status, json.dumps(document).encode()
'''

# The command line as a launch form runs it, failing if that loaded the
# configuration in the process that was asked.
_COMMAND_LINE = """
import sys
from orchestrator.cli import main

status = main(sys.argv[1:])
if "orchestrator.config" in sys.modules:
    sys.exit("check imported orchestrator.config")
sys.exit(status)
"""


def install_with_fake_github(site_packages: Path) -> Path:
    """Copy the package into ``site_packages``, its GitHub the fake; return the fake's directory."""
    installed_copy(site_packages)
    probe = site_packages / "orchestrator" / "service" / "token_probe.py"
    with probe.open("a", encoding=ENCODING) as module:
        module.write(_FAKE_HTTP_GET)
    fake = site_packages / _FAKE_GITHUB
    fake.mkdir()
    return fake


def repository_url(repository: str) -> str:
    """The URL GitHub is asked for ``repository`` at."""
    return f"{_GITHUB_API}/repos/{repository}"


class FakeGitHub:
    """The table the copy's fake answers from, and the requests it recorded."""

    def __init__(self, directory: Path) -> None:
        self._answers = directory / _ANSWERS
        self._requests = directory / _REQUESTS
        self.answer({})
        self._requests.unlink(missing_ok=True)

    def answer(
        self,
        answers: dict[str, tuple[int, object]],
        *,
        owner: str | None = None,
    ) -> None:
        """Answer each repository named with its status and document, and no other.

        With an ``owner``, whose token it is is answered too: that login.
        """
        table = {f"/repos/{repository}": answer for repository, answer in answers.items()}
        if owner is not None:
            table["/user"] = (OK, {"login": owner})
        self._answers.write_text(json.dumps(table), encoding=ENCODING)

    def answer_reachable(self) -> None:
        """Let each repository's token read it."""
        self.answer({API: (OK, {}), WEB: (OK, {})})

    def requests(self) -> list[tuple[str, str]]:
        """Each request sent, as its URL and the token it carried."""
        if not self._requests.exists():
            return []
        return [
            tuple(json.loads(line))
            for line in self._requests.read_text(encoding=ENCODING).splitlines()
        ]


class CheckCase(unittest.TestCase):
    """A host set up for two repositories, checked as an installed package.

    Each repository has a clone and a token file, the default agents sit in a
    directory of their own, and git in another, so the shell's `PATH` names
    nothing the host's own `PATH` holds. The `.env` lists both repositories
    and one author, and GitHub answers for neither until a test says how
    through ``github``.
    """

    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        scratch = Path(cls.enterClassContext(tempfile.TemporaryDirectory())).resolve()
        cls._site_packages = scratch / "site-packages"
        cls._fake = install_with_fake_github(cls._site_packages)

    def setUp(self) -> None:
        self.root = Path(self.enterContext(tempfile.TemporaryDirectory())).resolve()
        self.home = self.root / "home"
        self.home.mkdir()
        self.agents = self.root / "agents"
        install_agents(self.agents, CLAUDE, CODEX)
        self._tools = self.root / "tools"
        self._tools.mkdir()
        (self._tools / "git").symlink_to(shutil.which("git"))
        self._launch = self.root / "launch"
        self._launch.mkdir()
        self.shell = {"HOME": str(self.home), "USER": "alice"}
        self.set_path(str(self.agents))
        self.settings = {
            "REPOS": ";".join((
                f"{API}|{make_checkout(self.root / 'api')}|main",
                f"{WEB}|{make_checkout(self.root / 'web')}|main",
            )),
            "ALLOWED_ISSUE_AUTHORS": "alice",
        }
        for repository, stand_in in ((API, API_STAND_IN), (WEB, WEB_STAND_IN)):
            path = self.token_path(repository)
            path.parent.mkdir(parents=True)
            path.write_text(f"{stand_in}\n", encoding=ENCODING)
        self.github = FakeGitHub(self._fake)

    def set_path(self, *entries: str) -> None:
        """Give the shell a ``PATH`` of git's directory and then ``entries``."""
        tools = str(self._tools)
        self.shell["PATH"] = os.pathsep.join((tools, *entries))

    def token_path(self, repository: str) -> Path:
        """Where the service reads ``repository``'s token from."""
        return self.home / ".config" / repository / "token"

    def run_check(self, *arguments: str, **exported: str) -> subprocess.CompletedProcess[str]:
        """Run ``check`` with ``arguments`` from the case's shell, ``exported`` added to it.

        The case's settings are written to the installed `.env` first. The
        package runs from the case's installed copy unless ``exported`` names
        another ``PYTHONPATH``.
        """
        self.write_settings(self.home / ".config" / "chipping-orchestrator" / ".env")
        environment = {"PYTHONPATH": str(self._site_packages), **self.shell, **exported}
        return subprocess.run(
            (sys.executable, "-c", _COMMAND_LINE, "check", *arguments),
            cwd=self._launch,
            env=environment,
            capture_output=True,
            text=True,
            check=False,
            timeout=_RUN_TIMEOUT_SECONDS,
        )

    def write_settings(self, path: Path) -> None:
        """Write the case's settings to ``path`` as a `.env`, a line each."""
        path.parent.mkdir(parents=True, exist_ok=True)
        lines = (f"{key}={setting}\n" for key, setting in self.settings.items())
        path.write_text("".join(lines), encoding=ENCODING)

    def assert_refused(self, checked: subprocess.CompletedProcess[str], *problems: str) -> None:
        """``checked`` exited 1 with exactly ``problems`` on stderr, a line each."""
        self.assertEqual(
            (checked.returncode, checked.stdout, checked.stderr.splitlines()),
            (1, "", list(problems)),
        )
