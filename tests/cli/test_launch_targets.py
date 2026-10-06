# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What a launch targets, and that one refused for its targets touches nothing.

Each launch is a real process started the way `python -m orchestrator` starts,
from this checkout, with an audit hook that stops it on its first DNS lookup or
socket connect: a polling run and a maintenance pass both begin by connecting
to GitHub, before any label bootstrap, poll, or artifact is touched, so a run
the hook never fires in did none of them. Subprocesses are not stopped, since
reading the configuration asks git about every target. The installed form
imports a copy of the package from a `site-packages` of its own, which is the
layout a wheel installs; the source form imports this checkout.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from types import MappingProxyType
from typing import NamedTuple

from tests.support.git import (
    _append_git_config,
    _claim_work_tree,
    _foreign_owner_settings,
    _run_git,
)
from tests.support.installed_package import installed_copy

_REPO_ROOT = Path(__file__).resolve().parents[2]
_LAUNCH_TIMEOUT_SECONDS = 60
_SIDE_EFFECT_EXIT = 97
_SIDE_EFFECT = "side effect:"
_PACKAGE_PARENT_ENV = "LAUNCH_TARGET_PACKAGE_PARENT"
# Run as `python -P -c`, so neither the launch directory nor the script's own
# makes a package importable: only the directory the script puts first on
# `sys.path` decides which one runs. It travels in a variable of its own rather
# than `PYTHONPATH`, whose `:` separator a parent path here contains.
_GUARDED_LAUNCH = f"""
import os, runpy, sys

sys.path.insert(0, os.environ.pop("{_PACKAGE_PARENT_ENV}"))

def _stop_at_side_effect(event, _args):
    if event in ("socket.getaddrinfo", "socket.connect"):
        os.write(2, "{_SIDE_EFFECT} {{0}}\\n".format(event).encode())
        os._exit({_SIDE_EFFECT_EXIT})

sys.addaudithook(_stop_at_side_effect)
runpy.run_module("orchestrator", run_name="__main__", alter_sys=True)
"""
# Settings the operator's environment must not carry into a launch, so only
# the ones each case names decide what it targets.
_REPOS = "REPOS"
_LAUNCH_OWNED = frozenset((
    _REPOS,
    "REPO",
    "TARGET_REPO_ROOT",
    "WORKTREES_DIR",
    "LOG_DIR",
    "ORCHESTRATOR_TOKEN_FILE",
    "PYTHONPATH",
))
_ONCE = ("--once",)
_MAINTENANCE = ("--cleanup-terminal-artifacts",)
_REPOS_REQUIRED = "orchestrator: REPOS is unset, and an installed package has no default target"
_UNOPENABLE = "has git metadata git cannot open"
# Configs appended to a fresh clone's own that git will not open a checkout
# under: one making it bare, a line git cannot parse, and a repository format
# this git predates.
_UNOPENABLE_CONFIGS = MappingProxyType({
    "bare": "[core]\n\tbare = true\n",
    "malformed": "[core\n",
    "future": "[core]\n\trepositoryformatversion = 2\n",
})
# What each of those clones, and one whose HEAD is corrupted, is refused for.
_PROBLEMS = MappingProxyType({
    "corrupt": _UNOPENABLE,
    "bare": "is a bare repository",
    "malformed": _UNOPENABLE,
    "future": _UNOPENABLE,
})


class _Refused(NamedTuple):
    """A launch refused for its targets, and what each line of its error starts with."""

    case: str
    package_parent: Path
    settings: dict[str, str]
    refusals: tuple[str, ...]
    args: tuple[str, ...] = _ONCE


def _unusable_checkouts(scratch: Path) -> dict[Path, str]:
    """Clones git will not open as a checkout, each beside what it is refused for."""
    for name in _PROBLEMS:
        _run_git("init", str(scratch / name), cwd=scratch)
    (scratch / "corrupt" / ".git" / "HEAD").write_text("not a ref\n")
    for broken, config_text in _UNOPENABLE_CONFIGS.items():
        _append_git_config(scratch / broken, config_text)
    return {scratch / checkout: problem for checkout, problem in _PROBLEMS.items()}


def _launch(
    package_parent: Path,
    scratch: Path,
    settings: dict[str, str],
    args: tuple[str, ...] = _ONCE,
) -> subprocess.CompletedProcess:
    """Launch the package found under `package_parent` with `settings`."""
    launch_environment = {
        name: env_value
        for name, env_value in os.environ.items()
        if name not in _LAUNCH_OWNED
    }
    launch_environment.update({
        _PACKAGE_PARENT_ENV: str(package_parent),
        "ORCHESTRATOR_SKIP_DOTENV": "1",
        "ALLOWED_ISSUE_AUTHORS": "operator",
        "GITHUB_TOKEN": "ghp-launch-target-test",
        "WORKTREES_DIR": str(scratch / "worktrees"),
        "LOG_DIR": str(scratch / "logs"),
        **settings,
    })
    return subprocess.run(
        [sys.executable, "-P", "-c", _GUARDED_LAUNCH, *args],
        cwd=_REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
        timeout=_LAUNCH_TIMEOUT_SECONDS,
        env=launch_environment,
    )


class LaunchTargetTest(unittest.TestCase):
    """An installed package refuses to start without `REPOS`, even launched
    from a checkout of this project with `REPO` and `TARGET_REPO_ROOT` naming
    it, and any launch refuses a target that is not a checkout -- a plain
    directory, or a clone git will not open as one: a corrupted HEAD, a config
    making it bare, a config line git cannot parse, or a repository format git
    does not support. A refusal exits with status 1 on the error alone, before
    any side effect, in the maintenance mode as in the polling one. A
    repository around an installed package does not make it a source checkout,
    even one whose core.worktree names the package root beside a manifest
    naming this project. The control: given checkouts to target, both forms
    start and reach their first side effect.
    """

    def setUp(self) -> None:
        self._scratch = Path(self.enterContext(TemporaryDirectory()))
        self._site_packages = installed_copy(self._scratch / "site-packages")
        self._claimed = installed_copy(
            _claim_work_tree(self._scratch / "claims:env", "site-packages"),
        )
        shutil.copy(_REPO_ROOT / "pyproject.toml", self._claimed)
        self._plain = self._scratch / "plain"
        self._plain.mkdir()
        self._unusable = _unusable_checkouts(self._scratch)

    def test_refused_launches_touch_nothing(self) -> None:
        for refused in self._refused_launches():
            with self.subTest(case=refused.case):
                self._assert_refused(refused)

    def test_another_users_checkout_touches_nothing(self) -> None:
        # Git declines a checkout another user owns from inside it, as it
        # will decline every command the run would go on to start there.
        foreign = _foreign_owner_settings(self._scratch)
        if foreign is None:
            self.skipTest("this git cannot be made to read a checkout as another user's")
        self._assert_refused(_Refused(
            "installed with another user's checkout",
            self._site_packages,
            {**foreign, _REPOS: f"owner/foreign|{_REPO_ROOT}|main"},
            ((
                f"orchestrator: REPOS target {_REPO_ROOT} for 'owner/foreign' "
                "is a checkout git refuses to open from inside it ("
            ),),
        ))

    def test_checkout_targets_start_the_run(self) -> None:
        for case, package_parent, settings in (
            ("installed with REPOS", self._site_packages, {_REPOS: f"owner/good|{_REPO_ROOT}|main"}),
            ("source with the developer fallback", _REPO_ROOT, {}),
        ):
            with self.subTest(case=case):
                launched = _launch(package_parent, self._scratch, settings)

                self.assertEqual(launched.returncode, _SIDE_EFFECT_EXIT, launched.stderr)
                self.assertIn(_SIDE_EFFECT, launched.stderr)

    def _refused_launches(self) -> list[_Refused]:
        developer = {"REPO": "owner/developer", "TARGET_REPO_ROOT": str(_REPO_ROOT)}
        unusable = {_REPOS: ";".join((
            f"owner/good|{_REPO_ROOT}|main",
            f"owner/plain|{self._plain}|main",
            *(f"owner/{checkout.name}|{checkout}|main" for checkout in self._unusable),
        ))}
        refusals = (
            f"orchestrator: REPOS target {self._plain} for 'owner/plain'",
            *(
                f"orchestrator: REPOS target {checkout} for 'owner/{checkout.name}' {problem}"
                for checkout, problem in self._unusable.items()
            ),
        )
        return [
            _Refused("installed without REPOS", self._site_packages, developer, (_REPOS_REQUIRED,)),
            _Refused(
                "installed in a repository claiming it, without REPOS",
                self._claimed,
                {},
                (_REPOS_REQUIRED,),
            ),
            _Refused(
                "installed maintenance without REPOS",
                self._site_packages,
                developer,
                (_REPOS_REQUIRED,),
                _MAINTENANCE,
            ),
            _Refused("installed with unusable checkouts", self._site_packages, unusable, refusals),
            _Refused(
                "installed maintenance with unusable checkouts",
                self._site_packages,
                unusable,
                refusals,
                _MAINTENANCE,
            ),
            _Refused(
                "source with a plain developer target",
                _REPO_ROOT,
                {"TARGET_REPO_ROOT": str(self._plain)},
                (f"orchestrator: TARGET_REPO_ROOT target {self._plain}",),
            ),
        ]

    def _assert_refused(self, refused: _Refused) -> None:
        launched = _launch(refused.package_parent, self._scratch, refused.settings, refused.args)

        lines = launched.stderr.splitlines()
        self.assertEqual(launched.returncode, 1, launched.stderr)
        self.assertEqual(len(lines), len(refused.refusals), launched.stderr)
        for line, refusal in zip(lines, refused.refusals, strict=True):
            self.assertTrue(line.startswith(refusal), launched.stderr)
        self.assertEqual(launched.stdout, "")
