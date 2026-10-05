# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Focused configuration behavior tests."""

import os
import tempfile
import unittest
from pathlib import Path

from orchestrator.config import environment
from orchestrator.config._dotenv import load_dotenv, strip_dotenv_quotes
from tests.config import config_test_support as _support, config_test_values as _config_cases
from tests.support.repos_host import repos_only_host

_POLL_INTERVAL_ENV = "POLL_INTERVAL"
_HITL_HANDLE_ENV = "HITL_HANDLE"
_USER_DOTENV_PARTS = (".config", "chipping-orchestrator", ".env")


def _user_dotenv(home: Path) -> Path:
    user_dotenv = home.joinpath(*_USER_DOTENV_PARTS)
    user_dotenv.parent.mkdir(parents=True, exist_ok=True)
    return user_dotenv


class DotenvQuoteStrippingTest(unittest.TestCase):
    """Ensure dotenv parsing removes only one matched outer quote pair."""

    def test_keeps_inner_quote_pairs(self) -> None:
        # Inner double quotes and the command's trailing single quote are
        # payload, rather than an outer pair around the entire value.
        raw = "codex -m gpt-5.5 -c 'model_reasoning_effort=\"xhigh\"'"
        self.assertEqual(strip_dotenv_quotes(raw), raw)

    def test_unwraps_matched_outer_pair(self) -> None:
        # Operator-written `KEY="value with spaces"` -- a single matched
        # outer pair IS unwrapped so existing dotenv conventions keep
        # working.
        self.assertEqual(
            strip_dotenv_quotes('"value with spaces"'),
            "value with spaces",
        )
        self.assertEqual(
            strip_dotenv_quotes("'single quoted'"),
            "single quoted",
        )

    def test_keeps_mismatched_outer_pair(self) -> None:
        # A `"...'` mismatch is more likely a typo than a quoting
        # convention; leaving it intact surfaces the problem at the
        # downstream parser instead of silently corrupting the value.
        self.assertEqual(strip_dotenv_quotes("\"mismatched'"), "\"mismatched'")

    def test_quoted_codex_spec_round_trips(self) -> None:
        # The exact spec shape advertised in .env.example.advanced and
        # the issue body must parse cleanly when supplied through .env,
        # not just when injected directly into os.environ.
        body = "DEV_AGENT=codex -m gpt-5.5 -c 'model_reasoning_effort=\"xhigh\"'\n"
        config = _support.load_config_from_dotenv(body)
        self.assertEqual(config.DEV_AGENT, _config_cases._CODEX)
        self.assertEqual(
            config.DEV_AGENT_ARGS,
            (_config_cases._MODEL_FLAG, "gpt-5.5", "-c", 'model_reasoning_effort="xhigh"'),
        )

    def test_outer_double_quoted_value_unwraps(self) -> None:
        # Backward-compat for operators who wrap their values in outer
        # double quotes (a common dotenv convention).
        body = 'REVIEW_AGENT="claude --model claude-opus-4-7"\n'
        config = _support.load_config_from_dotenv(body)
        self.assertEqual(config.REVIEW_AGENT, _config_cases._CLAUDE)
        self.assertEqual(
            config.REVIEW_AGENT_ARGS,
            ("--model", "claude-opus-4-7"),
        )


class DotenvLocationTest(unittest.TestCase):
    """One `.env` is read, chosen by the layout the package runs from.

    A source checkout reads the `.env` at its own root and nothing else: a
    user-location file changes none of its settings, and a checkout without a
    `.env` loads none. Any other root is an installed layout, which reads
    `~/.config/chipping-orchestrator/.env` -- refusing secret keys there too --
    and never a `.env` beside the package. That file's directory is never a
    target: the repositories and the worktree root resolve from the `REPOS`
    it carries.
    """

    def test_source_checkout_reads_only_its_own(self) -> None:
        for expected in ({_POLL_INTERVAL_ENV: "11"}, {}):
            with (
                self.subTest(checkout_dotenv=bool(expected)),
                repos_only_host({}) as host,
                tempfile.TemporaryDirectory() as checkout,
            ):
                _support.make_checkout(Path(checkout))
                if expected:
                    Path(checkout, ".env").write_text(f"{_POLL_INTERVAL_ENV}=11\n")
                _user_dotenv(host.home).write_text(
                    f"{_POLL_INTERVAL_ENV}=22\n{_HITL_HANDLE_ENV}=user-location\n",
                )
                loaded: dict[str, str] = {}
                with host.patched_process():
                    load_dotenv(Path(checkout), loaded, self.fail)
                self.assertEqual(loaded, expected)

    def test_installed_layout_reads_user_location(self) -> None:
        warnings: list[str] = []
        with repos_only_host({}) as host, tempfile.TemporaryDirectory() as site_packages:
            Path(site_packages, ".env").write_text(
                f"{_POLL_INTERVAL_ENV}=33\n{_HITL_HANDLE_ENV}=beside-the-package\n",
            )
            user_dotenv = _user_dotenv(host.home)
            user_dotenv.write_text(
                f"{_POLL_INTERVAL_ENV}=22\nGITHUB_TOKEN=ghp_userlocationtoken\n",
            )
            loaded: dict[str, str] = {}
            with host.patched_process():
                load_dotenv(Path(site_packages), loaded, warnings.append)

        self.assertEqual(loaded, {_POLL_INTERVAL_ENV: "22"})
        self.assertEqual(len(warnings), 1)
        self.assertIn(f"ignoring GITHUB_TOKEN in {user_dotenv}", warnings[0])

    def test_user_location_is_never_a_target(self) -> None:
        alpha_token = {_config_cases._ALPHA_REPO: "ghp-alpha-file-token"}
        with repos_only_host(alpha_token) as host, tempfile.TemporaryDirectory() as site_packages:
            _user_dotenv(host.home).write_text(f"{_config_cases._REPOS_ENV}={host.repos}\n")
            with host.patched_process():
                os.environ.pop(_config_cases._SKIP_DOTENV_ENV, None)
                resolved = environment._SettingsResolver(
                    dict(os.environ),
                    Path(site_packages),
                    _support.exit_with_config_error,
                    self.fail,
                ).resolve()

            self.assertEqual(
                _support.only_repo_spec(resolved["REPO_SPECS"]).target_root,
                host.clones / "alpha__one",
            )
            self.assertEqual(resolved["WORKTREES_DIR"], host.clones / "wt-orchestrator")
