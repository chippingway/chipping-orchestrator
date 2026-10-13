# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What the built artifacts carry beyond the modules: the packaged `.env` templates.

An editable install reads the templates straight out of the checkout, so no
check run against one can tell whether the build backend packaged them, and
the files are dotfiles, which a package glob or an ignore rule can drop without
a sound. Only the artifacts themselves answer, so this builds both the way CI
does, into temporary storage, and reads each template back out of each.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import tarfile
import unittest
import zipfile
from pathlib import Path
from tempfile import TemporaryDirectory

from orchestrator.service.templates import template_text

_REPO_ROOT = Path(__file__).resolve().parents[2]
_ENCODING = "utf-8"

# Named here rather than read off the owner, so a template dropped from the
# owner's inventory is still a file this check expects to find packaged.
_TEMPLATES = (".env.example", ".env.example.advanced")
_TEMPLATE_DIRECTORY = "orchestrator/service"
_SDIST_SUFFIX = ".tar.gz"

# Poetry builds with the backend from its own environment, so the build needs
# nothing beyond the tool CI installs it with and nothing from the network.
_POETRY = "poetry"
_BUILD_TIMEOUT_SECONDS = 300
# An activated environment would override the checkout's own `.venv/`, which
# is why every manual Poetry command in this repository clears both markers.
_ACTIVATION_MARKERS = frozenset(("VIRTUAL_ENV", "CONDA_PREFIX"))


def _build(output: Path) -> subprocess.CompletedProcess[str]:
    """Build the wheel and the sdist from the checkout into `output`."""
    environment = {
        key: setting
        for key, setting in os.environ.items()
        if key not in _ACTIVATION_MARKERS
    }
    return subprocess.run(
        (_POETRY, "build", "--output", str(output)),
        cwd=_REPO_ROOT,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
        timeout=_BUILD_TIMEOUT_SECONDS,
    )


def _artifact(output: Path, pattern: str) -> Path:
    """The single artifact the build left under `output` matching `pattern`."""
    found = sorted(output.glob(pattern))
    if len(found) != 1:
        raise AssertionError(f"expected one {pattern} artifact, found {found}")
    return found[0]


def _wheel_text(wheel: Path, name: str) -> str:
    """The template a wheel installs, read from the archive itself."""
    with zipfile.ZipFile(wheel) as archive:
        return archive.read(f"{_TEMPLATE_DIRECTORY}/{name}").decode(_ENCODING)


def _sdist_text(sdist: Path, name: str) -> str:
    """The template a source archive carries under its top-level directory."""
    top = sdist.name.removesuffix(_SDIST_SUFFIX)
    with tarfile.open(sdist) as archive:
        member = archive.extractfile(f"{top}/{_TEMPLATE_DIRECTORY}/{name}")
        if member is None:
            raise AssertionError(f"{name} is not a regular file in {sdist.name}")
        return member.read().decode(_ENCODING)


@unittest.skipIf(shutil.which(_POETRY) is None, "poetry is not on PATH, so no distribution can be built")
class BuiltDistributionTest(unittest.TestCase):
    """Both artifacts `poetry build` makes carry the text the owner reads."""

    def test_both_artifacts_carry_the_templates(self) -> None:
        output = Path(self.enterContext(TemporaryDirectory()))
        completed = _build(output)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        wheel = _artifact(output, "*.whl")
        sdist = _artifact(output, f"*{_SDIST_SUFFIX}")
        for name in _TEMPLATES:
            with self.subTest(template=name):
                self.assertEqual(_wheel_text(wheel, name), template_text(name))
                self.assertEqual(_sdist_text(sdist, name), template_text(name))


if __name__ == "__main__":
    unittest.main()
