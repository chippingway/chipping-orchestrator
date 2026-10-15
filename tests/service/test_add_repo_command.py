# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""`add-repo` on the command line of an installed package, with systemd faked."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import unittest

from orchestrator.service.repos_entry import validate_parallel_limit
from tests.service import add_repo_test_support as _add_repo, configure_test_support as _support
from tests.service.service_test_support import refusal
from tests.support.installed_package import installed_copy

_RUN_TIMEOUT_SECONDS = 60
_REPORT = "report.json"
_PARALLEL = "--parallel"
_IS_ACTIVE = "systemctl --user is-active chipping-orchestrator.service"
_RESTART = (
    "chipping-orchestrator.service is running with the repositories it "
    "started with; restart it to manage acme/web too: chipping-orchestrator restart\n"
)

# A clean interpreter runs the command through `cli.main`, every systemd call
# answered by a stand-in exiting with the status the test gives, then reports
# the calls and whether it loaded the configuration to a file of its own, so
# the command's own output is all stdout and stderr hold, and exits with the
# command's status.
_DRIVER = """
import json
import sys

from orchestrator.service import systemd

asked = []


def answer(argv, timeout=0):
    asked.append(" ".join(argv))
    return systemd.Completed(int(sys.argv[2]), "", "")


systemd.run_command = answer
from orchestrator import cli

status = cli.main(sys.argv[3:])
with open(sys.argv[1], "w", encoding="utf-8") as report:
    json.dump({"asked": asked, "configured": "orchestrator.config" in sys.modules}, report)
sys.exit(status)
"""

# What the configuration resolves from the `.env` the command wrote.
_READ_CONFIGURATION = """
from orchestrator import config

for spec in config.default_repo_specs():
    print(spec.slug, spec.target_root, spec.base_branch, spec.remote_name, spec.parallel_limit)
"""


class AddRepoCommandTest(_add_repo.AddRepoCase):
    """`add-repo` launched from an installed package, the user manager answering as each test says.

    The package is a copy laid out the way a wheel installs it, launched from
    an unrelated directory with the case's home and its agents first on the
    PATH; each launch is a fresh interpreter.
    """

    def setUp(self) -> None:
        super().setUp()
        self._launch = self._scratch / "launch"
        self._launch.mkdir()
        inherited = os.environ.get("PATH", os.defpath)
        self._environment = {
            "HOME": str(self._home),
            "PATH": os.pathsep.join((str(self._bin), inherited)),
            "PYTHONPATH": str(installed_copy(self._scratch / "site-packages")),
            **_support.HERMETIC_GIT,
        }

    def test_restart_is_advised_only_while_running(self) -> None:
        """`systemctl is-active` exits 0 for an active unit and 3 for an inactive one."""
        added = f"Added {self._web_entry()} to REPOS in {self._settings_file}\n"
        for active, advice in ((0, _RESTART), (3, "")):
            with self.subTest(active=active):
                self._write_settings(self._configured)

                ran, report = self._add_repo(active)

                self.assertEqual(
                    (ran.returncode, ran.stdout, ran.stderr),
                    (0, f"{added}{advice}", ""),
                )
                self.assertEqual(report, {"asked": [_IS_ACTIVE], "configured": False})

    def test_the_configuration_reads_the_entry_back(self) -> None:
        """Added to a `REPOS` quoted with blanks inside its quotes, which the configuration reads all the same."""
        written = f"REPOS={self._api_entry}\n"
        quoted = f'REPOS="  {self._api_entry}  "\n'
        self._write_settings(self._configured.replace(written, quoted, 1))

        added = self._add_repo(0, _PARALLEL, "2")[0]
        read = self._run(_READ_CONFIGURATION)

        self.assertEqual((added.returncode, added.stderr), (0, ""))
        self.assertEqual(
            self._settings(),
            self._with_web(_add_repo.MAIN, _support.ORIGIN, "2"),
        )
        self.assertEqual((read.returncode, read.stderr), (0, ""))
        self.assertEqual(read.stdout.splitlines(), [
            f"{_support.ACME} {self._clone} {_support.TRUNK} {_support.ORIGIN} 1",
            f"{_add_repo.WEB} {self._web} {_add_repo.MAIN} {_support.ORIGIN} 2",
        ])

    def test_a_refusal_asks_systemd_nothing(self) -> None:
        ran, report = self._add_repo(0, _PARALLEL, "0")

        expected = f"{_PARALLEL}: {refusal(validate_parallel_limit, '0')}\n"
        self.assertEqual(
            (ran.returncode, ran.stdout, ran.stderr),
            (1, "", expected),
        )
        self.assertEqual(report, {"asked": [], "configured": False})
        self.assertEqual(self._settings(), self._configured)

    def _add_repo(self, active: int, *options: str) -> tuple[subprocess.CompletedProcess[str], object]:
        """Run `add-repo` for the web clone with ``options``, `is-active` exiting ``active``."""
        report_file = self._scratch / _REPORT
        command_line = ("add-repo", "--clone", str(self._web), *options)
        ran = self._run(_DRIVER, str(report_file), str(active), *command_line)
        return ran, json.loads(report_file.read_text(encoding=_support.ENCODING))

    def _run(self, program: str, *arguments: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            (sys.executable, "-c", program, *arguments),
            cwd=self._launch,
            env=self._environment,
            capture_output=True,
            text=True,
            check=False,
            timeout=_RUN_TIMEOUT_SECONDS,
        )


if __name__ == "__main__":
    unittest.main()
