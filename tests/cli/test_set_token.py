# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What the `set-token` command line answers, and what it costs to run."""
from __future__ import annotations

import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from orchestrator import cli
from orchestrator.service import token_probe

_REPO_ROOT = Path(__file__).resolve().parents[2]
_TOKEN = "github_pat_11ABCDEFG0123456789_abcdefghijklmnop"
_REPOSITORY = "acme/api"
_REPOSITORY_URL = f"{token_probe.API_ROOT}/repos/{_REPOSITORY}"
_SET_TOKEN = "set-token"
_LAUNCH_TIMEOUT_SECONDS = 60
_REPORT = "report.json"
_UNQUOTED_REFUSAL = (
    ": error: this set-token command line is not printed back, in case it holds "
    "the token: set-token takes OWNER/NAME alone, and reads the token from "
    "standard input, piped in, redirected from a file, or typed at the prompt"
)

# Each place a token can be put on a command line naming set-token, and each
# refusal argparse would quote it in: a further argument; an unknown option's
# separate or attached value, after the repository or before it; a value
# handed to a flag that takes none, whole or abbreviated; and the same in
# front of the command, through an unknown option, `--version`, and the
# hidden twins of the `run` flags; and the token standing in for the command.
_TOKEN_ARGUMENTS = (
    (_SET_TOKEN, _REPOSITORY, _TOKEN),
    (_SET_TOKEN, _REPOSITORY, "--token", _TOKEN),
    (_SET_TOKEN, _REPOSITORY, f"--token={_TOKEN}"),
    (_SET_TOKEN, f"--token={_TOKEN}", _REPOSITORY),
    (_SET_TOKEN, _REPOSITORY, f"--help={_TOKEN}"),
    (_SET_TOKEN, f"--he={_TOKEN}", _REPOSITORY),
    ("--token", _TOKEN, _SET_TOKEN, _REPOSITORY),
    (f"--version={_TOKEN}", _SET_TOKEN, _REPOSITORY),
    ("--log-level", _TOKEN, _SET_TOKEN, _REPOSITORY),
    (f"--once={_TOKEN}", _SET_TOKEN, _REPOSITORY),
    (_TOKEN, _SET_TOKEN),
)

# A clean interpreter runs the command through `cli.main` with GitHub answered
# by a stand-in, then reports what the run asked GitHub and which owners it
# loaded. The report goes to a file of its own, so the command's own output
# is all that reaches stdout and stderr.
_DRIVER = """
import json
import sys

from orchestrator.service import token_probe

requests = []


def answer(url, token):
    requests.append([url, token])
    return 200, b"{}"


token_probe.http_get = answer
from orchestrator import cli

status = cli.main(["set-token", "acme/api"])
with open(sys.argv[1], "w", encoding="utf-8") as report:
    json.dump({"status": status, "requests": requests, "loaded": sorted(sys.modules)}, report)
"""

# The owners that resolve the configuration as they are imported, or that sit
# on top of it: a first setup runs where loading any of them would exit.
_CONFIGURED_OWNERS = ("orchestrator.config", "orchestrator.github")


def _launch(home: Path) -> subprocess.CompletedProcess[str]:
    """Run the driver under ``home``, the token piped in and nothing configured."""
    return subprocess.run(
        (sys.executable, "-c", _DRIVER, str(home / _REPORT)),
        input=f"{_TOKEN}\n",
        cwd=_REPO_ROOT,
        env={"HOME": str(home), "PATH": os.environ.get("PATH", os.defpath)},
        capture_output=True,
        text=True,
        check=False,
        timeout=_LAUNCH_TIMEOUT_SECONDS,
    )


class TokenArgumentTest(unittest.TestCase):
    """A command line naming `set-token` that the parser refuses, for whatever
    reason and in whichever parser, is a usage error that prints back none of
    what it was given -- only the usage and the form the command takes --
    before standard input is read, GitHub is asked, or anything is written.
    Every other command still names an argument it does not know.
    """

    def test_a_token_argument_is_refused_unrepeated(self) -> None:
        for argv in _TOKEN_ARGUMENTS:
            with self.subTest(argv=argv):
                stdin = io.StringIO(f"{_TOKEN}\n")
                stdout = io.StringIO()
                stderr = io.StringIO()
                refused = self.assertRaises(SystemExit)
                with (
                    refused,
                    patch.object(token_probe, "http_get", side_effect=AssertionError("GitHub was asked")),
                    patch.object(sys, "stdin", stdin),
                    patch.object(sys, "stdout", stdout),
                    patch.object(sys, "stderr", stderr),
                ):
                    cli.main(list(argv))

                self.assertEqual(refused.exception.code, 2)
                self.assertNotIn(_TOKEN, stderr.getvalue())
                self.assertTrue(stderr.getvalue().endswith(f"{_UNQUOTED_REFUSAL}\n"), stderr.getvalue())
                self.assertEqual(stdout.getvalue(), "")
                self.assertEqual(stdin.tell(), 0)

    def test_other_commands_name_unknown_arguments(self) -> None:
        stderr = io.StringIO()
        refused = self.assertRaises(SystemExit)
        with refused, patch.object(sys, "stderr", stderr):
            cli.main(["run", "--bogus"])

        self.assertEqual(refused.exception.code, 2)
        self.assertEqual(
            stderr.getvalue().splitlines()[-1],
            "chipping-orchestrator: error: unrecognized arguments: --bogus",
        )


class UnconfiguredSetTokenTest(unittest.TestCase):
    """Run in a fresh interpreter on an empty home with nothing configured,
    `set-token` reads the piped token, proves it with one call for the
    repository, and writes its token file -- and loads neither the
    configuration nor the GitHub client, so it runs before any `.env` exists.
    """

    def test_set_token_needs_no_configuration(self) -> None:
        home = Path(self.enterContext(tempfile.TemporaryDirectory()))

        completed = _launch(home)

        self.assertEqual(completed.returncode, 0, completed.stderr)
        report = json.loads((home / _REPORT).read_text(encoding="utf-8"))
        self.assertEqual(report["status"], 0, completed.stderr)
        self.assertEqual(report["requests"], [[_REPOSITORY_URL, _TOKEN]])
        config = home / ".config"
        self.assertEqual((config / _REPOSITORY / "token").read_text(), f"{_TOKEN}\n")
        self.assertFalse((config / "chipping-orchestrator").exists())
        self.assertEqual(
            [name for name in report["loaded"] if name.startswith(_CONFIGURED_OWNERS)],
            [],
        )
        self.assertNotIn(_TOKEN, completed.stdout + completed.stderr)

if __name__ == "__main__":
    unittest.main()
