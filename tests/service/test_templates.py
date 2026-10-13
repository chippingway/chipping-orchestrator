# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The packaged `.env` templates, read the way the operations guide reads them."""
from __future__ import annotations

import os
import shlex
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from orchestrator import __version__
from orchestrator.service.templates import TEMPLATES, template_text
from tests.support.installed_package import installed_copy

_REPO_ROOT = Path(__file__).resolve().parents[2]
_OPERATIONS_GUIDE = _REPO_ROOT / "docs" / "configuration" / "operations.md"
_SAVING_SECTION = "#### Save the installed version's templates\n"
_ENCODING = "utf-8"
_RUN_TIMEOUT_SECONDS = 60


def _documented_save() -> str:
    """Read the Python program the guide's saving block runs, so it cannot drift."""
    guide = _OPERATIONS_GUIDE.read_text(encoding=_ENCODING)
    section = guide.split(_SAVING_SECTION, 1)[1]
    fenced = section.split("```sh\n", 1)[1]
    arguments = shlex.split(fenced.split("```", 1)[0])
    return arguments[arguments.index("-c") + 1]


class DocumentedSaveTest(unittest.TestCase):
    """The guide's saving step reads both templates where nothing is configured.

    The package is copied outside any checkout, the way a wheel installs it,
    and run from an unrelated directory with an empty home: no `.env` and no
    `REPOS`, the state a first setup starts in and one where importing the
    configuration exits. Every run is a fresh interpreter, so nothing an
    earlier import resolved can stand in for what the step itself loads.
    """

    def setUp(self) -> None:
        root = Path(self.enterContext(tempfile.TemporaryDirectory())).resolve()
        installed = installed_copy(root / "site-packages")
        self._launch = root / "launch"
        self._launch.mkdir()
        (root / "home").mkdir()
        self._saved = root / "releases" / f"v{__version__}"
        self._environment = {
            "HOME": str(root / "home"),
            "PATH": os.environ.get("PATH", os.defpath),
            "PYTHONPATH": str(installed),
        }

    def test_saves_the_templates_unconfigured(self) -> None:
        settings = self._run("import orchestrator.config")
        self.assertEqual(settings.returncode, 1, "the environment must hold no configuration")
        self.assertIn("REPOS", settings.stderr)

        completed = self._run(_documented_save(), __version__, str(self._saved))

        self.assertEqual(completed.returncode, 0, completed.stderr)
        saved = sorted(path.name for path in self._saved.iterdir())
        self.assertEqual(saved, sorted(TEMPLATES))
        for name in TEMPLATES:
            with self.subTest(template=name):
                copy = self._saved / name
                self.assertEqual(copy.read_text(encoding=_ENCODING), template_text(name))

    def test_refuses_another_version(self) -> None:
        completed = self._run(_documented_save(), "0.0.0", str(self._saved))

        self.assertNotEqual(completed.returncode, 0)
        self.assertIn(__version__, completed.stderr)
        self.assertFalse(self._saved.exists())

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


class TemplateNameTest(unittest.TestCase):
    """Only the two templates answer; the package's other files are not setups."""

    def test_other_names_are_refused(self) -> None:
        for name in ("__init__.py", "templates.py", ".env"):
            with self.subTest(name=name), self.assertRaises(ValueError):
                template_text(name)


if __name__ == "__main__":
    unittest.main()
