# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What `check` reports when the service would not run, one line per problem."""
from __future__ import annotations

import errno
import os
from pathlib import Path
from unittest.mock import patch

from orchestrator.service import paths
from tests.service import check_test_support as _support
from tests.service.configure_test_support import CLAUDE, CODEX, install_agents
from tests.support.checkouts import make_checkout
from tests.support.installed_package import installed_copy

_NOT_FOUND = 404
_TOKEN_FILE_SETTING = "ORCHESTRATOR_TOKEN_FILE"
_REPOS = "REPOS"
_REPOSITORIES = (_support.API, _support.WEB)
_CLAUDE_MISSING = "DEV_AGENT, DECOMPOSE_AGENT: CLAUDE_BIN 'claude' is not an executable on the service's PATH"
_CODEX_MISSING = "REVIEW_AGENT: CODEX_BIN 'codex' is not an executable on the service's PATH"
_REPOS_REQUIRED = (
    "orchestrator: REPOS is unset, and an installed package has no default "
    "target; set REPOS to one or more 'owner/name|target_root|base_branch' "
    "entries separated by ';'. REPO and TARGET_REPO_ROOT are developer "
    "settings, read only when the orchestrator runs from its own source "
    "checkout"
)


def _no_token(repository: str, path: Path) -> str:
    """The line a repository whose token file holds no token is reported with."""
    return (
        f"{repository}: no GitHub token in {path}; store one with "
        f"chipping-orchestrator set-token {repository}"
    )


class ShellOverridesTest(_support.CheckCase):
    """Nothing the shell exports but HOME, USER, and PATH reaches the check."""

    def test_exported_values_cannot_rescue_it(self) -> None:
        shell_token = self.root / "shell-token"
        shell_token.write_text("tok-shell\n", encoding=_support.ENCODING)
        self.settings["ALLOWED_ISSUE_AUTHORS"] = ""
        for repository in _REPOSITORIES:
            self.token_path(repository).unlink()
        self.set_path()

        checked = self.run_check(
            GITHUB_TOKEN="tok-shell",
            ALLOWED_ISSUE_AUTHORS="alice",
            ORCHESTRATOR_TOKEN_FILE=str(shell_token),
            CLAUDE_BIN=str(self.agents / CLAUDE),
            CODEX_BIN=str(self.agents / CODEX),
        )

        self.assert_refused(
            checked,
            _support.ALLOWLIST_REFUSAL,
            *(_no_token(listed, self.token_path(listed)) for listed in _REPOSITORIES),
            _CLAUDE_MISSING,
            _CODEX_MISSING,
        )
        self.assertEqual(self.github.requests(), [])

    def test_exported_repos_and_opt_out_dropped(self) -> None:
        # Two fields: the entry the service reads from `.env` is malformed,
        # while the one exported, read with `.env` skipped, would pass.
        clone = self.root / "api"
        malformed = f"{_support.API}|{clone}"
        self.settings[_REPOS] = malformed

        checked = self.run_check(ORCHESTRATOR_SKIP_DOTENV="1", REPOS=f"{malformed}|main")

        self.assert_refused(checked, (
            "orchestrator: REPOS entry #1 is malformed (expected "
            "'owner/name|target_root|base_branch' with optional '|remote_name' "
            f"and '|parallel_limit'): {malformed!r}"
        ))


class SettingsProblemsTest(_support.CheckCase):
    """Settings that do not resolve are reported as a start reports them, and nothing after."""

    def test_malformed_settings_reported_alone(self) -> None:
        resolvable = dict(self.settings)
        for setting, written, diagnostic in (
            (
                "WORKFLOW_TRANSITION_GUARD",
                "sometimes",
                (
                    "orchestrator: WORKFLOW_TRANSITION_GUARD='sometimes' is invalid; "
                    "expected one of: off, warn, enforce"
                ),
            ),
            (
                "POLL_INTERVAL",
                "often",
                (
                    "orchestrator: the settings cannot be read "
                    "(invalid literal for int() with base 10: 'often')"
                ),
            ),
            (_REPOS, "", _REPOS_REQUIRED),
        ):
            with self.subTest(setting=setting):
                self.settings = {**resolvable, setting: written}

                self.assert_refused(self.run_check(), diagnostic)
                self.assertEqual(self.github.requests(), [])

    def test_every_unusable_target_is_named(self) -> None:
        targets = {repository: self.root / "gone" / repository for repository in _REPOSITORIES}
        self.settings[_REPOS] = ";".join(
            f"{repository}|{target}|main" for repository, target in targets.items()
        )

        checked = self.run_check()

        self.assert_refused(checked, *(
            (
                f"orchestrator: REPOS target {target} for {repository!r} does not exist; "
                f"point it at a local clone or linked worktree of {repository}"
            )
            for repository, target in targets.items()
        ))
        self.assertEqual(self.github.requests(), [])


class RepositoryProblemsTest(_support.CheckCase):
    """A repository the service holds no usable token for is named."""

    def test_missing_tokens_name_the_file_read(self) -> None:
        shared = self.root / "shared-token"
        for token_file_setting, expected in (
            (None, [_no_token(repository, self.token_path(repository)) for repository in _REPOSITORIES]),
            (str(shared), [
                f"{repository}: no GitHub token in {shared}, the file {_TOKEN_FILE_SETTING} names"
                for repository in _REPOSITORIES
            ]),
        ):
            with self.subTest(token_file_setting=token_file_setting):
                for repository in _REPOSITORIES:
                    self.token_path(repository).unlink(missing_ok=True)
                if token_file_setting is not None:
                    self.settings[_TOKEN_FILE_SETTING] = token_file_setting

                self.assert_refused(self.run_check(), *expected)
                self.assertEqual(self.github.requests(), [])

    def test_refused_token_found_by_full_check(self) -> None:
        self.github.answer({
            _support.API: (_support.OK, {}),
            _support.WEB: (_NOT_FOUND, {"message": "Not Found"}),
        })
        stand_ins = (_support.API_STAND_IN, _support.WEB_STAND_IN)
        asked = [
            (_support.repository_url(repository), stand_in)
            for repository, stand_in in zip(_REPOSITORIES, stand_ins, strict=True)
        ]

        checked = self.run_check()

        self.assert_refused(checked, (
            f"{_support.WEB}: the token cannot read {_support.WEB}; check the name, and "
            "that the token is granted access to it (GitHub answered 404: Not Found)"
        ))
        self.assertEqual(self.github.requests(), asked)
        self.assertEqual(self.run_check(_support.LOCAL).returncode, 0)
        self.assertEqual(self.github.requests(), asked)

    def test_unreadable_token_file_is_one_line(self) -> None:
        # A directory where the file belongs fails to read with an error that
        # is not a missing file, as an unreadable one does, whoever runs it.
        unreadable = self.token_path(_support.API)
        unreadable.unlink()
        unreadable.mkdir()
        try:
            unreadable.read_bytes()
        except OSError as error:
            reading = str(error)

        checked = self.run_check(_support.LOCAL)

        self.assert_refused(checked, f"{_support.API}: {unreadable} cannot be read ({reading})")


class AgentProblemsTest(_support.CheckCase):
    """Each agent binary a role runs has to be an executable on the service's PATH."""

    def test_missing_binary_named_once_per_setting(self) -> None:
        self.set_path()

        checked = self.run_check(_support.LOCAL)

        self.assert_refused(checked, _CLAUDE_MISSING, _CODEX_MISSING)

    def test_dotenv_binaries_and_specs_are_used(self) -> None:
        elsewhere = self.root / "elsewhere"
        install_agents(elsewhere, "agy-cli", "codex-cli")
        self.settings.update({
            "DEV_AGENT": "agy --model fast",
            "REVIEW_AGENT": CODEX,
            "DECOMPOSE_AGENT": CODEX,
            "AGY_BIN": str(elsewhere / "agy-cli"),
            "CODEX_BIN": str(elsewhere / "codex-cli"),
        })
        self.set_path()

        checked = self.run_check(_support.LOCAL)

        self.assertEqual((checked.returncode, checked.stderr), (0, ""))

    def test_only_absolute_path_entries_count(self) -> None:
        # Relative to the service's home, where its process runs, an empty
        # entry and `bin` would both find the agents.
        user_bin = self.home / "bin"
        install_agents(self.home, CLAUDE, CODEX)
        install_agents(user_bin, CLAUDE, CODEX)
        self.set_path("", "bin")

        self.assert_refused(self.run_check(_support.LOCAL), _CLAUDE_MISSING, _CODEX_MISSING)
        self.set_path(str(user_bin))
        self.assertEqual(self.run_check(_support.LOCAL).returncode, 0)

    def test_relative_binary_path_refused(self) -> None:
        # Found from the service's home, but each agent is started in its
        # issue's worktree, which is where the path would be read from.
        relative = "./relative-tools/claude"
        install_agents(self.home / "relative-tools", CLAUDE)
        self.settings["CLAUDE_BIN"] = relative

        checked = self.run_check(_support.LOCAL)

        self.assert_refused(checked, (
            f"DEV_AGENT, DECOMPOSE_AGENT: CLAUDE_BIN {relative!r} is a relative path, which each "
            "agent would read from its own worktree; give an absolute path, or a name on the "
            "service's PATH"
        ))


class SourceCheckoutTest(_support.CheckCase):
    """A package running from its own source checkout checks nothing an installed service reads."""

    def test_source_checkout_refused(self) -> None:
        # The checkout's own `.env` would pass, while the installed one the
        # service reads names no author. A git setting the shell exports keeps
        # git from opening the checkout there, but not in the service's
        # environment, where the checkout is told apart.
        checkout = installed_copy(make_checkout(self.root / "checkout"))
        self.write_settings(checkout / ".env")
        self.settings["ALLOWED_ISSUE_AUTHORS"] = ""
        with patch.dict(os.environ, {"HOME": str(self.home)}):
            refusal = str(paths.source_checkout_refusal("check", checkout))
        for exported in (
            {},
            {"GIT_CONFIG_COUNT": "invalid"},
            {"GIT_CONFIG_PARAMETERS": "'unterminated"},
            {"GIT_CONFIG_COUNT": "1", "GIT_CONFIG_KEY_0": "core.worktree", "GIT_CONFIG_VALUE_0": str(self.home)},
        ):
            with self.subTest(exported=exported):
                checked = self.run_check(_support.LOCAL, PYTHONPATH=str(checkout), **exported)

                self.assert_refused(checked, refusal)


class UnreportedCheckTest(_support.CheckCase):
    """A check that cannot report what it found says so, in one line, instead of passing."""

    def test_missing_service_home_reported(self) -> None:
        gone = self.root / "gone"
        missing = FileNotFoundError(errno.ENOENT, os.strerror(errno.ENOENT), str(gone))

        checked = self.run_check(_support.LOCAL, HOME=str(gone))

        self.assert_refused(
            checked,
            f"the settings cannot be checked from the service's working directory {gone}: {missing}",
        )

    def test_stopped_interpreter_reported(self) -> None:
        # GitHub's table answers for neither repository, so the fake raises in
        # the interpreter that asks it, which writes a traceback that is held
        # back but for its last line.
        checked = self.run_check()

        self.assert_refused(checked, (
            "the settings check stopped before it reported (exit status 1): "
            f"KeyError: '/repos/{_support.API}'"
        ))
