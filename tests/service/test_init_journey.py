# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""An empty home set up by script -- `set-token`, `configure`, `init` -- then `init` again."""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from tests.service import (
    check_test_support as _github,
    configure_test_support as _configure,
    init_test_support as _support,
)
from tests.service.service_test_support import add_remote
from tests.support.checkouts import committed_checkout

_FAKE_SYSTEMD = "fake-systemd"
_ANSWERS = "answers.json"
_COMMANDS = "commands.jsonl"
_RUN_TIMEOUT_SECONDS = 120
_TOKEN = "stand-in-api"

# Rebinds the copy's `run_command` to the fake: the module looks the name up
# when it calls it, so every adapter in it reaches the fake too.
_FAKE_RUN_COMMAND = f'''

def run_command(argv, timeout=_TIMEOUT_SECONDS):
    """Answer from the test's table beside this package, recording the command."""
    import json
    from pathlib import Path

    fake = Path(__file__).resolve().parents[2] / "{_FAKE_SYSTEMD}"
    with (fake / "{_COMMANDS}").open("a", encoding="utf-8") as commands:
        commands.write(json.dumps(list(argv)) + "\\n")
    answers = json.loads((fake / "{_ANSWERS}").read_text(encoding="utf-8"))
    return Completed(*answers.get(" ".join(argv), (0, "", "")))
'''

# The command line as a launch form runs it, failing if that loaded the
# configuration in the process that was asked.
_COMMAND_LINE = """
import sys
from orchestrator.cli import main

status = main(sys.argv[1:])
if "orchestrator.config" in sys.modules:
    sys.exit(sys.argv[1] + " imported orchestrator.config")
sys.exit(status)
"""


def _expected_unit(search_path: str) -> str:
    """The unit for the interpreter the commands run under and ``search_path``."""
    interpreter = sys.executable.replace("%", "%%")
    return _support.UNIT_TEXT.format(
        interpreter=f'"{interpreter}"',
        environment=f'"PATH={search_path}"',
    )


class _InstalledSystemd:
    """The table the copy's fake systemd answers from, and the commands it recorded."""

    def __init__(self, directory: Path) -> None:
        self._answers = directory / _ANSWERS
        self._commands = directory / _COMMANDS

    def answer(self, *answered: tuple[tuple[str, ...], object]) -> None:
        """Answer each command named as given, and every other as a success; forget what ran."""
        table = {" ".join(command): list(answer) for command, answer in answered}
        self._answers.write_text(json.dumps(table), encoding=_support.ENCODING)
        self._commands.unlink(missing_ok=True)

    def commands(self) -> list[tuple[str, ...]]:
        """Each command the fake was asked, in order."""
        if not self._commands.exists():
            return []
        recorded = self._commands.read_text(encoding=_support.ENCODING)
        return [tuple(json.loads(line)) for line in recorded.splitlines()]


class ScriptedSetupTest(unittest.TestCase):
    """A home with nothing in it, set up by the scripted commands, then given `init` again.

    Each command is a fresh interpreter of a copy of the package laid out the
    way a wheel installs it, launched from an unrelated directory with a pipe
    on standard input, the home, alice, git, the default agents, and the
    clone's remote naming acme/api. GitHub lets the token read acme/api, the
    user manager answers, linger is off, and the service is not running.

    The setup ends with the unit installed and enabled and the service not
    started. Run again over it, with linger on and the service running, `init`
    rewrites the unit alone: every other file in the home is byte for byte as
    the setup wrote it, and the service is told to restart rather than
    restarted. Each full check proves the token from the interpreter it
    starts, so GitHub is asked once by `set-token` and once by each `init`.
    """

    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        scratch = Path(cls.enterClassContext(tempfile.TemporaryDirectory())).resolve()
        cls._site_packages = scratch / "site-packages"
        cls._fake_github = _github.install_with_fake_github(cls._site_packages)
        adapters = cls._site_packages / "orchestrator" / "service" / "systemd.py"
        with adapters.open("a", encoding=_support.ENCODING) as module:
            module.write(_FAKE_RUN_COMMAND)
        cls._fake_systemd = cls._site_packages / _FAKE_SYSTEMD
        cls._fake_systemd.mkdir()

    def setUp(self) -> None:
        root = Path(self.enterContext(tempfile.TemporaryDirectory())).resolve()
        self.home = root / "home"
        self.home.mkdir()
        self._launch = root / "launch"
        self._launch.mkdir()
        tools = root / "tools"
        _configure.install_agents(tools, _configure.CLAUDE, _configure.CODEX)
        (tools / "git").symlink_to(shutil.which("git"))
        self._clone = committed_checkout(root / "src" / "api")
        add_remote(self._clone, _configure.ORIGIN, _configure.ACME_URL, _configure.TRUNK)
        self.search_path = str(tools)
        self.github = _github.FakeGitHub(self._fake_github)
        self.github.answer({_configure.ACME: (_github.OK, {})})
        self.systemd = _InstalledSystemd(self._fake_systemd)
        self.systemd.answer(
            (_support.SHOW_LINGER, _support.NOT_LINGERING),
            (_support.IS_ACTIVE, _support.INACTIVE),
        )
        self.unit_file = self.home / _support.UNIT_DIR / _support.UNIT

    def run_command(self, *arguments: str, stdin: str = "") -> subprocess.CompletedProcess[str]:
        """Run ``chipping-orchestrator`` with ``arguments``, failing the test unless it exits 0."""
        environment = {
            "PYTHONPATH": str(self._site_packages),
            "HOME": str(self.home),
            "USER": _support.USER,
            "PATH": self.search_path,
            **_configure.HERMETIC_GIT,
        }
        completed = subprocess.run(
            (sys.executable, "-c", _COMMAND_LINE, *arguments),
            input=stdin,
            cwd=self._launch,
            env=environment,
            capture_output=True,
            text=True,
            check=False,
            timeout=_RUN_TIMEOUT_SECONDS,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        return completed

    def install_by_script(self) -> None:
        """Run the scripted setup on the empty home, and find the service installed by it.

        The token goes first, then the `.env`, then ``init``, which asks the
        user manager and logind exactly what a first install does.
        """
        self.assertEqual(list(self.home.iterdir()), [])
        self.run_command("set-token", _configure.ACME, stdin=f"{_TOKEN}\n")
        self.run_command("configure", "--clone", str(self._clone), "--authors", _configure.AUTHOR)
        self.run_command("init")
        self.assert_unit_installed()
        self.assertEqual(
            tuple(self.systemd.commands()),
            tuple(command for command in _support.FIRST_INSTALL if command != _support.CHECKED),
        )

    def assert_unit_installed(self) -> None:
        """The unit holds the interpreter the commands ran under and the shell's `PATH`."""
        written = self.unit_file.read_text(encoding=_support.ENCODING)
        self.assertEqual(written, _expected_unit(self.search_path))

    def setup_files(self) -> dict[Path, bytes]:
        """Every file in the home but the unit, by path, with what it holds."""
        return {
            path: path.read_bytes()
            for path in sorted(self.home.rglob("*"))
            if path.is_file() and path != self.unit_file
        }

    def test_init_again_refreshes_only_the_unit(self) -> None:
        self.install_by_script()
        written = self.setup_files()
        self.systemd.answer(
            (_support.SHOW_LINGER, _support.LINGERING),
            (_support.IS_ACTIVE, _support.ACTIVE),
        )

        again = self.run_command("init")

        self.assertEqual(self.setup_files(), written)
        self.assert_unit_installed()
        self.assertEqual(self.systemd.commands(), [
            _support.PROBE,
            _support.RELOAD,
            _support.ENABLE,
            _support.SHOW_LINGER,
            _support.IS_ACTIVE,
        ])
        self.assertIn("systemctl --user restart chipping-orchestrator.service", again.stdout)
        self.assertEqual(again.stderr, "")
        repository = (_github.repository_url(_configure.ACME), _TOKEN)
        self.assertEqual(self.github.requests(), [repository, repository, repository])


if __name__ == "__main__":
    unittest.main()
