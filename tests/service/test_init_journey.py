# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""An empty home set up by script or by onboarding, then `init` again or the service managed."""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from orchestrator.service.systemd import Completed
from tests.service import (
    check_test_support as _github,
    configure_test_support as _configure,
    init_test_support as _support,
    lifecycle_test_support as _lifecycle,
)
from tests.service.service_test_support import add_remote
from tests.support.checkouts import committed_checkout

_FAKE_SYSTEMD = "fake-systemd"
_ANSWERS = "answers.json"
_COMMANDS = "commands.jsonl"
_RUN_TIMEOUT_SECONDS = 120
_TOKEN = "stand-in-api"
_INIT = "init"
# Enter at each question after the first repository's token: the authors,
# the people to mention, the agents, another repository, and writing.
_AFTER_TOKEN = ("", "", "", "", "")
_WEB = "acme/web"
_WEB_TOKEN = "stand-in-web"

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


# Run in front of the command line, standing a terminal typed what the test
# pipes in for standard input, the hidden prompt reading its next line.
_AT_A_TERMINAL = r"""
import getpass
import io
import sys


class Terminal(io.StringIO):
    def isatty(self):
        return True


sys.stdin = Terminal(sys.stdin.read())


def hidden(prompt=""):
    sys.stdout.write(prompt + "\n")
    line = sys.stdin.readline()
    if not line:
        raise EOFError
    return line.removesuffix("\n")


getpass.getpass = hidden
"""


def _typed(*answers: str) -> str:
    """What a terminal is typed to give ``answers``, a line each."""
    return "".join(f"{answer}\n" for answer in answers)


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


class _ScriptedSetupCase(unittest.TestCase):
    """A home with nothing in it, set up by the scripted commands.

    Each command is a fresh interpreter of a copy of the package laid out the
    way a wheel installs it, launched from an unrelated directory with a pipe
    -- or a terminal typed what the pipe carries -- on standard input, the
    home, alice, git, the default agents, and the clone's remote naming
    acme/api, and failing if it imported the configuration. GitHub lets the token read acme/api, the user manager
    answers, linger is off, and the service is not running. The setup ends
    with the unit installed and enabled and the service not started.
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

    def run_command(
        self,
        *arguments: str,
        stdin: str = "",
        terminal: bool = False,
    ) -> subprocess.CompletedProcess[str]:
        """Run ``chipping-orchestrator`` with ``arguments``, failing the test unless it exits 0.

        With ``terminal``, standard input is a terminal typed ``stdin``.
        """
        environment = {
            "PYTHONPATH": str(self._site_packages),
            "HOME": str(self.home),
            "USER": _support.USER,
            "PATH": self.search_path,
            **_configure.HERMETIC_GIT,
        }
        program = f"{_AT_A_TERMINAL}{_COMMAND_LINE}" if terminal else _COMMAND_LINE
        completed = subprocess.run(
            (sys.executable, "-c", program, *arguments),
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
        self.run_command(_INIT)
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

    def empty_home(self) -> dict[Path, bytes]:
        """Every file in the home, unit included, as it was before the home was emptied.

        The user manager and logind answer as they did for the first install,
        and forget what they were asked.
        """
        written = {**self.setup_files(), self.unit_file: self.unit_file.read_bytes()}
        shutil.rmtree(self.home)
        self.home.mkdir()
        self.systemd.answer(
            (_support.SHOW_LINGER, _support.NOT_LINGERING),
            (_support.IS_ACTIVE, _support.INACTIVE),
        )
        return written



class ScriptedSetupTest(_ScriptedSetupCase):
    """The scripted setup given `init` again.

    Run over it, with linger on and the service running, `init` rewrites the
    unit alone: every other file in the home is byte for byte as the setup
    wrote it, and the service is told to restart rather than restarted. Each
    full check proves the token from the interpreter it starts, so GitHub is
    asked once by `set-token` and once by each `init`.
    """

    def test_init_again_refreshes_only_the_unit(self) -> None:
        self.install_by_script()
        written = self.setup_files()
        self.systemd.answer(
            (_support.SHOW_LINGER, _support.LINGERING),
            (_support.IS_ACTIVE, _support.ACTIVE),
        )

        again = self.run_command(_INIT)

        self.assertEqual(self.setup_files(), written)
        self.assert_unit_installed()
        self.assertEqual(self.systemd.commands(), [
            _support.PROBE,
            _support.RELOAD,
            _support.ENABLE,
            _support.SHOW_LINGER,
            _support.IS_ACTIVE,
        ])
        self.assertIn("restart it to run the unit just written: chipping-orchestrator restart", again.stdout)
        self.assertEqual(again.stderr, "")
        repository = (_github.repository_url(_configure.ACME), _TOKEN)
        self.assertEqual(self.github.requests(), [repository, repository, repository])



class OnboardingJourneyTest(_ScriptedSetupCase):
    """Onboarding at a terminal, on the same empty home, writes what the scripted setup wrote.

    The answers are each clone and each token, every other question taking
    its default: the repository and branch off the clone, the token owner as
    the author, the authors as the people to mention, and the default agents.
    The `.env`, the token files, and the unit are byte for byte the scripted
    setup's, for one repository as for two, and `init` asks systemd what a
    first install asks. Run again at a terminal, `init` asks nothing and
    rewrites the unit alone.
    """

    def setUp(self) -> None:
        super().setUp()
        self._web = committed_checkout(self._clone.parent / "web")
        add_remote(self._web, _configure.ORIGIN, "https://github.com/acme/web.git", "main")
        self.github.answer(
            {_configure.ACME: (_github.OK, {}), _WEB: (_github.OK, {})},
            owner=_configure.AUTHOR,
        )

    def test_one_repository(self) -> None:
        self.install_by_script()
        scripted = self.empty_home()

        onboarded = self.run_command(
            _INIT,
            stdin=_typed(str(self._clone), "", "", _TOKEN, *_AFTER_TOKEN),
            terminal=True,
        )

        self.assertEqual(
            tuple(self.systemd.commands()),
            tuple(command for command in _support.FIRST_INSTALL if command != _support.CHECKED),
        )
        self.assertIn("Saved the token for acme/api", onboarded.stdout)
        self.assertEqual(self.empty_home(), scripted)

    def test_two_repositories(self) -> None:
        self.run_command("set-token", _configure.ACME, stdin=f"{_TOKEN}\n")
        self.run_command("set-token", _WEB, stdin=f"{_WEB_TOKEN}\n")
        self.run_command("configure", "--clone", str(self._clone), "--authors", _configure.AUTHOR)
        self.run_command("add-repo", "--clone", str(self._web))
        self.run_command(_INIT)
        scripted = self.empty_home()

        self.run_command(
            _INIT,
            stdin=_typed(
                str(self._clone), "", "", _TOKEN, "", "", "",
                "y", str(self._web), "", "", _WEB_TOKEN,
                "", "",
            ),
            terminal=True,
        )
        written = self.setup_files()
        again = self.run_command(_INIT, terminal=True)

        self.assertNotIn("No configuration", again.stdout)
        self.assertEqual(self.setup_files(), written)
        self.assertEqual(self.empty_home(), scripted)


class ManagedServiceTest(_ScriptedSetupCase):
    """The service the scripted setup installed, shown, stopped, and removed.

    None of the three imports the configuration, and the removal deletes the
    unit alone.
    """

    def test_lifecycle_reads_no_configuration(self) -> None:
        self.install_by_script()
        written = self.setup_files()
        self.systemd.answer((_lifecycle.IS_FAILED, Completed(1, "inactive\n", "")))

        shown = self.run_command("status")
        self.run_command("stop")
        removed = self.run_command("remove")

        self.assertIn(f"Unit: {self.unit_file}\n", shown.stdout)
        self.assertEqual(self.systemd.commands(), [
            _support.PROBE,
            _lifecycle.STATUS,
            _support.PROBE,
            _lifecycle.STOP,
            _support.PROBE,
            _lifecycle.STOP,
            _lifecycle.DISABLE,
            _support.RELOAD,
            _lifecycle.IS_FAILED,
        ])
        self.assertIn("Kept, since remove deletes nothing else", removed.stdout)
        self.assertFalse(self.unit_file.exists())
        self.assertEqual(self.setup_files(), written)


if __name__ == "__main__":
    unittest.main()
