# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""GitHub credential resolution tests."""

import io
import os
import tempfile
import unittest
from contextlib import redirect_stderr
from pathlib import Path
from types import MappingProxyType
from unittest.mock import patch

from orchestrator.config import credentials
from tests.config import config_reload_helpers as _reload
from tests.support.repos_host import repos_only_host

_REPO_SLUG = "owner/repo"
_TOKEN_ENV = "GITHUB_TOKEN"
_TOKEN_FILE_ENV = "ORCHESTRATOR_TOKEN_FILE"
_FILE_TOKEN = "file-token"
_CONFIG_DIR = ".config"
_TOKEN_FILE = "token"
_ALPHA_TOKENS = MappingProxyType({"alpha/one": "ghp-alpha-file-token"})
_TWO_REPOSITORY_TOKENS = MappingProxyType({
    "alpha/one": "ghp-alpha-file-token",
    "beta/two": "ghp-beta-file-token",
})


def _write_token(token_file: Path, token: str) -> None:
    token_file.parent.mkdir(parents=True, exist_ok=True)
    token_file.write_text(token)


class ResolveGithubTokenTest(unittest.TestCase):
    """The GitHub token is never read from the repository checkout: the
    process environment wins, and the only fallback is a token file outside
    REPO_ROOT -- `~/.config/<owner>/<repo>/token` derived from the repo slug,
    or whatever ORCHESTRATOR_TOKEN_FILE names. A token file that cannot be
    read degrades to "no token" so the caller keeps its own failure handling.
    """

    def test_process_environment_token_wins(self) -> None:
        with tempfile.TemporaryDirectory() as home:
            home_path = Path(home)
            _write_token(
                home_path / _CONFIG_DIR / _REPO_SLUG / _TOKEN_FILE,
                _FILE_TOKEN,
            )
            with (
                patch.dict(os.environ, {_TOKEN_ENV: "  env-token  "}, clear=True),
                patch.object(Path, "home", return_value=home_path),
            ):
                resolved = credentials.resolve_github_token(_REPO_SLUG)
        self.assertEqual(resolved, "env-token")

    def test_slug_derived_token_file_is_the_fallback(self) -> None:
        # The default path is derived from the repository's slug and lives
        # outside REPO_ROOT, which is what keeps the token out of reach of an
        # agent that can read the orchestrator checkout.
        with tempfile.TemporaryDirectory() as home:
            home_path = Path(home)
            _write_token(
                home_path / _CONFIG_DIR / _REPO_SLUG / _TOKEN_FILE,
                f"{_FILE_TOKEN}\n",
            )
            with (
                patch.dict(os.environ, {}, clear=True),
                patch.object(Path, "home", return_value=home_path),
            ):
                resolved = credentials.resolve_github_token(_REPO_SLUG)
        self.assertEqual(resolved, _FILE_TOKEN)

    def test_token_file_override_is_honored(self) -> None:
        with tempfile.TemporaryDirectory() as token_dir:
            token_file = Path(token_dir) / _TOKEN_FILE
            _write_token(token_file, f" {_FILE_TOKEN} ")
            environment = {_TOKEN_FILE_ENV: str(token_file)}
            with patch.dict(os.environ, environment, clear=True):
                resolved = credentials.resolve_github_token(_REPO_SLUG)
        self.assertEqual(resolved, _FILE_TOKEN)

    def test_missing_token_file_resolves_to_no_token(self) -> None:
        # A host that has not been provisioned yet is a normal state, so the
        # absent file stays silent; the caller reports the missing token.
        errors = io.StringIO()
        with tempfile.TemporaryDirectory() as token_dir:
            environment = {_TOKEN_FILE_ENV: str(Path(token_dir) / _TOKEN_FILE)}
            with patch.dict(os.environ, environment, clear=True), redirect_stderr(errors):
                resolved = credentials.resolve_github_token(_REPO_SLUG)
        self.assertEqual(resolved, "")
        self.assertEqual(errors.getvalue(), "")

    def test_unreadable_token_file_warns(self) -> None:
        errors = io.StringIO()
        with tempfile.TemporaryDirectory() as token_dir:
            # A directory where the token file belongs stands in for any
            # unreadable path: it fails with an OSError that is not a
            # missing file, which is the branch that has to warn.
            with patch.dict(os.environ, {_TOKEN_FILE_ENV: token_dir}, clear=True), redirect_stderr(errors):
                resolved = credentials.resolve_github_token(_REPO_SLUG)
            self.assertIn(token_dir, errors.getvalue())
        self.assertEqual(resolved, "")
        self.assertIn("could not read token file", errors.getvalue())


class ConfiguredRepositoryTokensTest(unittest.TestCase):
    """Each `REPOS` entry resolves its own token file at startup.

    With no `REPO`, `TARGET_REPO_ROOT`, process token, or token-file override,
    every selected repository's `~/.config/<owner>/<name>/token` answers for
    it alone -- for one entry and for several -- and the configured token set
    the redactor masks holds each of them. A process token or an
    `ORCHESTRATOR_TOKEN_FILE` still wins, and answers for every entry alike.
    """

    def test_each_entry_resolves_its_own_token_file(self) -> None:
        for tokens in (_ALPHA_TOKENS, _TWO_REPOSITORY_TOKENS):
            with self.subTest(repositories=len(tokens)), repos_only_host(tokens) as host:
                config = _reload.load_config(
                    host.settings(), token_file_override=False,
                )
                with host.patched_process():
                    resolved = {
                        spec.slug: config._resolve_github_token(spec.slug)
                        for spec in config.default_repo_specs()
                    }
                self.assertEqual(resolved, dict(tokens))
                self.assertEqual(config.GITHUB_TOKENS, tuple(tokens.values()))

    def test_process_token_and_override_win_for_all(self) -> None:
        with repos_only_host(_TWO_REPOSITORY_TOKENS) as host:
            override_file = host.home / "override-token"
            override_file.write_text(f"{_FILE_TOKEN}\n")
            precedence_cases = (
                ({_TOKEN_ENV: "env-token"}, "env-token"),
                ({_TOKEN_FILE_ENV: str(override_file)}, _FILE_TOKEN),
            )
            for override, expected in precedence_cases:
                with self.subTest(override=next(iter(override))):
                    self.assertEqual(
                        _reload.load_config(
                            {**host.settings(), **override},
                            token_file_override=False,
                        ).GITHUB_TOKENS,
                        (expected,),
                    )
