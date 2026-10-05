# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Which targets a start selects: `REPOS`, or a source checkout's developer fallback."""

import contextlib
import os
import shutil
import tempfile
import unittest
from pathlib import Path
from typing import Any
from unittest.mock import patch

from orchestrator.config import environment
from tests.config import config_test_support as _support, config_test_values as _config_cases
from tests.support.git import _claim_work_tree

_TARGET_ROOT_ENV = "TARGET_REPO_ROOT"
_REPO_SPECS = "REPO_SPECS"
_REPOS_REQUIRED = "orchestrator: REPOS is unset, and an installed package has no default target"


def _resolve(package_root: Path, settings: dict[str, str]) -> dict[str, Any]:
    """Resolve `settings` the way a package whose root is `package_root` does.

    No `.env` is read and no token file is either, so only `settings` decide.
    """
    with patch.dict(os.environ, {
        _config_cases._TOKEN_FILE_ENV: _config_cases._MISSING_TOKEN_PATH,
    }):
        return environment._SettingsResolver(
            {_config_cases._SKIP_DOTENV_ENV: _config_cases._ENABLED_ENV, **settings},
            package_root,
            _support.exit_with_config_error,
            _support.exit_with_config_error,
        ).resolve()


def _refusal(package_root: Path, settings: dict[str, str]) -> str:
    """The configuration error resolving `settings` from `package_root` aborts on."""
    try:
        _resolve(package_root, settings)
    except SystemExit as error:
        return str(error)
    raise AssertionError("resolving the settings did not abort")


class InstalledTargetSelectionTest(unittest.TestCase):
    """Only a source checkout of this project falls back to developer targets.

    An installed package -- here a `site-packages` inside a checkout of this
    project, launched from that checkout -- has no target but the ones `REPOS`
    names: unset or blank, it aborts whatever `REPO` and `TARGET_REPO_ROOT`
    say, and neither the package's location, the repository around it, nor
    the launch directory stands in. Set, `REPOS` alone decides. A package
    running from its own checkout keeps the developer fallback; a root that
    only a repository around it names as its work tree is not such a checkout.
    """

    def setUp(self) -> None:
        scratch = Path(self.enterContext(tempfile.TemporaryDirectory()))
        self._source = _support.make_checkout(scratch / "enclosing")
        self._site_packages = self._source / ".venv" / "lib" / "site-packages"
        self._site_packages.mkdir(parents=True)
        self._developer_root = _support.make_checkout(scratch / "developer")
        self._developer = {
            "REPO": _config_cases._LEGACY_REPO,
            _TARGET_ROOT_ENV: str(self._developer_root),
        }
        self.enterContext(contextlib.chdir(self._source))

    def test_installed_package_requires_repos(self) -> None:
        for repos in ({}, {_config_cases._REPOS_ENV: ""}, {_config_cases._REPOS_ENV: _config_cases._BLANK_ENV}):
            with self.subTest(repos=repos):
                refusal = _refusal(self._site_packages, {**self._developer, **repos})

                self.assertTrue(refusal.startswith(_REPOS_REQUIRED), refusal)

    def test_installed_package_targets_repos_alone(self) -> None:
        with _support.target_checkout() as target:
            resolved = _resolve(self._site_packages, {
                **self._developer,
                _config_cases._REPOS_ENV: f"{_config_cases._ALPHA_REPO}|{target}|main",
            })

            spec = _support.only_repo_spec(resolved[_REPO_SPECS])
            self.assertEqual(spec.slug, _config_cases._ALPHA_REPO)
            self.assertEqual(spec.target_root, Path(target))

    def test_source_checkout_keeps_developer_fallback(self) -> None:
        for settings, expected_root in (
            ({}, self._source),
            (self._developer, self._developer_root),
        ):
            with self.subTest(target=expected_root.name):
                resolved = _resolve(self._source, settings)

                self.assertEqual(
                    _support.only_repo_spec(resolved[_REPO_SPECS]).target_root,
                    expected_root,
                )

    def test_continued_config_line_keeps_the_fallback(self) -> None:
        # Git reads `bare = fal` continued past a backslash (`\x5c`) onto `se`
        # as false, so a checkout whose config spells it so is still a source
        # checkout, and still the developer target it falls back to.
        with (self._source / ".git" / "config").open("a", encoding="utf-8") as config:
            config.write("[core]\n\tbare = fal\x5c\nse\n")
        resolved = _resolve(self._source, {})

        self.assertEqual(
            _support.only_repo_spec(resolved[_REPO_SPECS]).target_root, self._source,
        )

    def test_claimed_package_root_stays_installed(self) -> None:
        # A manifest naming this project, and a repository around the root --
        # under a path holding the `:` a discovery ceiling list splits on --
        # whose core.worktree names it: the root still has no `.git` of its
        # own, so it is installed and needs `REPOS`.
        root = _claim_work_tree(self._source.parent / "claims:env", "site-packages")
        root.mkdir()
        shutil.copy(self._source / "pyproject.toml", root)
        refusal = _refusal(root, self._developer)

        self.assertTrue(refusal.startswith(_REPOS_REQUIRED), refusal)

    def test_line_breaks_stay_in_a_source_root(self) -> None:
        # A source root whose path holds a line break is still the checkout
        # git names, so it keeps its developer fallback to itself.
        for name in _config_cases._LINE_BREAKING_NAMES:
            with self.subTest(name=name):
                source = _support.make_checkout(self._source.parent / name)
                resolved = _resolve(source, {})

                self.assertEqual(
                    _support.only_repo_spec(resolved[_REPO_SPECS]).target_root, source,
                )
