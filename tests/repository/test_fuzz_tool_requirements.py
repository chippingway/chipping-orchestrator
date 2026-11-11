# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The hashed requirements the fuzzing image installs its tooling from.

Poetry, which `.clusterfuzzlite/Dockerfile` bootstraps into an environment of
its own, and the PyInstaller and coverage.py `build.sh` adds to the checkout's
environment are outside `poetry.lock`. Each is installed from a requirements
file under `.clusterfuzzlite/` that pins it and every package it needs to one
version and lists the SHA-256 of every artifact pip may accept for each, and
every pip install the image and the build run reads such a file with
`--require-hashes`, which refuses a package the file leaves unpinned and an
artifact it does not hash. Nothing this suite runs builds the image, so what
each file declares is held as text.
"""
from __future__ import annotations

import re
import tomllib
import unittest
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
_ENCODING = "utf-8"
_DOCKERFILE = ".clusterfuzzlite/Dockerfile"
_BUILD = ".clusterfuzzlite/build.sh"
_POETRY = ".clusterfuzzlite/poetry-requirements.txt"
_PYINSTALLER = ".clusterfuzzlite/pyinstaller-requirements.txt"
_COVERAGE = ".clusterfuzzlite/coverage-requirements.txt"
# Where the image copies the Poetry requirements, ahead of the checkout.
_BOOTSTRAP = "/opt/poetry-requirements.txt"
# Each requirements file, and the tool it is there to install.
_TOOLS = ((_POETRY, "poetry"), (_PYINSTALLER, "pyinstaller"), (_COVERAGE, "coverage"))
# Each file that installs tooling, and the requirements its installs read, in order.
_INSTALLS = ((_DOCKERFILE, (_BOOTSTRAP,)), (_BUILD, (_PYINSTALLER, _COVERAGE)))
# The lock groups `build.sh` syncs into the environment the build tools join.
_SYNCED_GROUPS = frozenset(("main", "fuzz"))

_COMMENT = re.compile(r"(?m)^[ \t]*#.*\n")
_CONTINUATION = re.compile(r"\\\n\s*")
# A pip install that refuses what its requirements file does not hash, and that file.
_HASHED_INSTALL = re.compile(r"-m pip install (?:--[\w-]+ +)*--require-hashes +(?:--[\w-]+ +)*-r (\S+)")
# One requirement as Poetry exports it: an exact pin, the markers it applies
# under, and the SHA-256 of every artifact pip may accept for it.
_PINNED = re.compile(r"(?P<name>[\w.-]+)==(?P<version>[^\s;]+)(?: ;(?:(?! --).)+)?(?: --hash=sha256:[0-9a-f]{64})+")
_COVERAGE_ONLY = re.compile(r'(?ms)^if \[\[ "\$SANITIZER" == coverage \]\]; then$(.*?)^fi$')


def _commands(relative: str) -> str:
    """The file's uncommented lines, each backslash-continued one joined to the next."""
    uncommented = _COMMENT.sub("", (_ROOT / relative).read_text(encoding=_ENCODING))
    return _CONTINUATION.sub(" ", uncommented)


def _entries(relative: str) -> list[str]:
    """The requirements in a file, one each, its whitespace collapsed."""
    lines = _commands(relative).splitlines()
    return [" ".join(line.split()) for line in lines if line.strip()]


def _versions(relative: str) -> dict[str, str]:
    """The version each pinned requirement in a file names, by project name."""
    pinned = filter(None, map(_PINNED.fullmatch, _entries(relative)))
    return {match["name"]: match["version"] for match in pinned}


def _locked(names: set[str]) -> dict[str, str]:
    """The version `poetry.lock` pins each of `names` at that `build.sh` syncs."""
    lock = tomllib.loads((_ROOT / "poetry.lock").read_text(encoding=_ENCODING))
    versions = {}
    for package in lock["package"]:
        if package["name"] in names and _SYNCED_GROUPS.intersection(package["groups"]):
            versions[package["name"]] = package["version"]
    return versions


class FuzzToolRequirementsTest(unittest.TestCase):
    def test_every_requirement_is_pinned_and_hashed(self) -> None:
        for relative, tool in _TOOLS:
            with self.subTest(requirements=relative):
                self.assertIn(tool, _versions(relative))
                for entry in _entries(relative):
                    self.assertIsNotNone(_PINNED.fullmatch(entry), entry)

    def test_every_install_requires_hashes(self) -> None:
        for source, read_from in _INSTALLS:
            commands = _commands(source)
            with self.subTest(source=source):
                self.assertEqual(commands.count("pip install"), len(read_from))
                self.assertEqual(tuple(_HASHED_INSTALL.findall(commands)), read_from)

    def test_bootstrap_is_copied_in_before_poetry(self) -> None:
        dockerfile = _commands(_DOCKERFILE)
        copied = dockerfile.index(f"COPY {_POETRY} {_BOOTSTRAP}\n")
        installed = dockerfile.index(f"-r {_BOOTSTRAP}")
        self.assertLess(copied, installed)
        self.assertLess(installed, dockerfile.index("COPY . $SRC/"))

    def test_coverage_builds_alone_add_coverage(self) -> None:
        build = _commands(_BUILD)
        branch = _COVERAGE_ONLY.search(build).group(1)
        self.assertEqual(_HASHED_INSTALL.findall(branch), [_COVERAGE])
        # Its sdist builds against the setuptools PyInstaller's hashed set put
        # in, never one an isolated build fetches unhashed.
        self.assertIn("--no-build-isolation", branch)
        self.assertIn("setuptools", _versions(_PYINSTALLER))
        synced = build.index('"$poetry" sync --only main,fuzz')
        self.assertLess(synced, build.index(f"-r {_PYINSTALLER}"))

    def test_build_tools_leave_locked_packages_alone(self) -> None:
        tools = {**_versions(_PYINSTALLER), **_versions(_COVERAGE)}
        locked = _locked(set(tools))
        self.assertEqual({name: tools[name] for name in locked}, locked)


if __name__ == "__main__":
    unittest.main()
