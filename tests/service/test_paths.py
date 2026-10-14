# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Where the running package sits, and the paths and refusal a setup reads off it."""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from orchestrator.service import paths
from tests.support.checkouts import committed_checkout, make_checkout
from tests.support.git import _run_git
from tests.support.installed_package import installed_copy

_RUN_TIMEOUT_SECONDS = 60

# Where an installed package keeps its settings and logs, under a home.
_SETTINGS = Path(".config", "chipping-orchestrator")
_LOGS = Path(".local", "state", "chipping-orchestrator", "logs")

# What a launched package reports about itself: where it sits, whether that is
# a source checkout, the refusal a setup command gives there, and the
# installed paths under the home it runs with.
_REPORT = """
import json
from orchestrator.service import paths
print(json.dumps({
    "root": str(paths.PACKAGE_ROOT),
    "source": paths.is_source_checkout(paths.PACKAGE_ROOT),
    "refusal": paths.source_checkout_refusal("configure"),
    "settings": str(paths.settings_file()),
    "logs": str(paths.log_dir()),
}))
"""


def _source_checkouts(scratch: Path) -> dict[str, Path]:
    """An ordinary clone of this project and a worktree linked to it."""
    clone = committed_checkout(scratch / "clone")
    _run_git("worktree", "add", "-q", str(scratch / "linked"), cwd=clone)
    return {"clone": clone, "linked worktree": scratch / "linked"}


def _installed_layouts(scratch: Path) -> dict[str, Path]:
    """Roots that carry part of a checkout's shape but are not one."""
    unpacked = make_checkout(scratch / "unpacked")
    shutil.rmtree(unpacked / ".git")
    dangling = Path(shutil.copytree(unpacked, scratch / "dangling"))
    (dangling / ".git").write_text("gitdir: ../missing\n")
    site_packages = make_checkout(scratch / "enclosing") / ".venv" / "site-packages"
    site_packages.mkdir(parents=True)
    return {
        "manifest without git metadata": unpacked,
        "dangling worktree pointer": dangling,
        "another project": make_checkout(scratch / "other", "another-project"),
        "site-packages inside a checkout": site_packages,
    }


def _refusal_names(root: Path) -> tuple[str, ...]:
    """What a source checkout's refusal has to name: the command, the
    checkout's own `.env`, its setup guide, and its restart wrapper."""
    return (
        "chipping-orchestrator add-repo",
        str(root / ".env"),
        str(root / "docs" / "development.md"),
        str(root / "run.sh"),
    )


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

    def setUp(self) -> None:
        self._scratch = Path(self.enterContext(tempfile.TemporaryDirectory())).resolve()

    def test_this_project_s_checkouts_are_source(self) -> None:
        self.assertTrue(paths.is_source_checkout(paths.PACKAGE_ROOT), paths.PACKAGE_ROOT)
        for case, root in _source_checkouts(self._scratch).items():
            with self.subTest(case=case):
                self.assertTrue(paths.is_source_checkout(root))

    def test_other_layouts_are_installed(self) -> None:
        for case, root in _installed_layouts(self._scratch).items():
            with self.subTest(case=case):
                self.assertFalse(paths.is_source_checkout(root))

    def test_setup_refuses_a_source_checkout_only(self) -> None:
        # The refusal sends the developer to the checkout's own guide and
        # restart wrapper, naming the `.env` it reads instead.
        for case, root in _source_checkouts(self._scratch).items():
            with self.subTest(case=case):
                refusal = paths.source_checkout_refusal("add-repo", root) or ""
                for name in _refusal_names(root):
                    self.assertIn(name, refusal)
        for case, root in _installed_layouts(self._scratch).items():
            with self.subTest(case=case):
                self.assertIsNone(paths.source_checkout_refusal("add-repo", root))


class LaunchedLayoutTest(unittest.TestCase):
    """The layout is the running package's, wherever it was launched from.

    Each launch is a fresh interpreter with an empty home and no `REPOS`, the
    state a first setup starts in. The installed copy sits in a
    `site-packages` inside a checkout of this project and is launched from
    that checkout's root, with the launch directory kept off the import path
    the way a console script keeps it: it is still installed. This checkout's
    own package, launched from an unrelated directory, is still source.
    """

    def setUp(self) -> None:
        self._scratch = Path(self.enterContext(tempfile.TemporaryDirectory())).resolve()
        self._home = self._scratch / "home"
        self._home.mkdir()

    def test_installed_launch_inside_a_checkout(self) -> None:
        checkout = committed_checkout(self._scratch / "checkout")
        site_packages = installed_copy(checkout / ".venv" / "site-packages")

        report = self._launch(site_packages, cwd=checkout)

        self.assertEqual(report, {
            "root": str(site_packages),
            "source": False,
            "refusal": None,
            "settings": str(self._home / _SETTINGS / ".env"),
            "logs": str(self._home / _LOGS),
        })

    def test_source_launch_elsewhere(self) -> None:
        launch = self._scratch / "launch"
        launch.mkdir()

        report = self._launch(paths.PACKAGE_ROOT, cwd=launch)

        self.assertEqual(report["root"], str(paths.PACKAGE_ROOT))
        self.assertTrue(report["source"])
        self.assertIn(str(paths.PACKAGE_ROOT / "run.sh"), report["refusal"])

    def _launch(self, import_root: Path, *, cwd: Path) -> dict:
        # `-P` keeps the launch directory off `sys.path`, as a console script
        # does, so the package imported is the one on `PYTHONPATH`.
        completed = subprocess.run(
            (sys.executable, "-P", "-c", _REPORT),
            cwd=cwd,
            env={
                "HOME": str(self._home),
                "PATH": os.environ.get("PATH", os.defpath),
                "PYTHONPATH": str(import_root),
            },
            capture_output=True,
            text=True,
            check=False,
            timeout=_RUN_TIMEOUT_SECONDS,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        return json.loads(completed.stdout)


if __name__ == "__main__":
    unittest.main()
