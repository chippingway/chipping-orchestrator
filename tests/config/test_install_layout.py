# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The source-checkout and installed layouts the configuration tells apart."""

import importlib
import shutil
import tempfile
import unittest
from pathlib import Path

from orchestrator.config import layout
from tests.config import config_test_support as _support
from tests.support.git import _run_git

_MANIFEST = "pyproject.toml"


def _source_checkouts(scratch: Path) -> dict[str, Path]:
    """An ordinary clone of this project and a worktree linked to it."""
    clone = _support.make_checkout(scratch / "clone")
    _run_git("add", _MANIFEST, cwd=clone)
    _run_git("commit", "-q", "-m", "init", cwd=clone)
    _run_git("worktree", "add", "-q", str(scratch / "linked"), cwd=clone)
    return {"clone": clone, "linked worktree": scratch / "linked"}


def _installed_layouts(scratch: Path) -> dict[str, Path]:
    """Roots that carry part of a checkout's shape but are not one."""
    unpacked = _support.make_checkout(scratch / "unpacked")
    shutil.rmtree(unpacked / ".git")
    dangling = Path(shutil.copytree(unpacked, scratch / "dangling"))
    (dangling / ".git").write_text("gitdir: ../missing\n")
    site_packages = _support.make_checkout(scratch / "enclosing") / ".venv" / "site-packages"
    site_packages.mkdir(parents=True)
    return {
        "manifest without git metadata": unpacked,
        "dangling worktree pointer": dangling,
        "another project": _support.make_checkout(scratch / "other", "another-project"),
        "site-packages inside a checkout": site_packages,
    }


class SourceCheckoutTest(unittest.TestCase):
    """Only this project's own checkout, proved at its root, is a source one.

    An ordinary clone and a linked worktree -- whose `.git` is a file naming
    its git directory -- both are, and so is the root the running package was
    imported from, an editable install of this checkout. A source tree with no
    git metadata, a root whose worktree pointer leads nowhere, a checkout of
    another project, and an installed environment sitting inside some
    checkout of this one are not: the proof is read at the package root
    itself, never from a directory around it.
    """

    def test_this_project_s_checkouts_are_source(self) -> None:
        running_root = importlib.import_module("orchestrator.config").REPO_ROOT
        self.assertTrue(layout.is_source_checkout(running_root), running_root)
        with tempfile.TemporaryDirectory() as td:
            for case, root in _source_checkouts(Path(td).resolve()).items():
                with self.subTest(case=case):
                    self.assertTrue(layout.is_source_checkout(root))

    def test_other_layouts_are_installed(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            for case, root in _installed_layouts(Path(td).resolve()).items():
                with self.subTest(case=case):
                    self.assertFalse(layout.is_source_checkout(root))
