# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Token resolution, the detached environment, and the askpass session."""

from __future__ import annotations

import os
import stat
import subprocess
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from orchestrator import config
from orchestrator.git import credentials
from tests.git.token_transport_test_support import (
    FAKE_TOKEN,
    REPOSITORY_SLUG,
    TOKEN_RESOLVER,
    _spec,
)

ASKPASS_KEY = "GIT_ASKPASS"
ASKPASS_MODE = 0o700
COMMITTER_NAME_KEY = "GIT_COMMITTER_NAME"
FETCH_OPERATION = "fetch"
INHERITED_COMMITTER = "operator-identity"
PLUMBING_LOGGER = "orchestrator.git_plumbing"


def _auth_env(*, include_identity: bool) -> dict[str, str]:
    return credentials._git_auth_env(
        Path("/tmp/askpass.sh"), FAKE_TOKEN, include_identity=include_identity,
    )


class RefusalChannelTest(unittest.TestCase):
    """A token this owner cannot resolve reaches the operator's channel.

    Operators filter on the rendered `orchestrator.git_plumbing` prefix and
    attach handlers to that logger, so the one refusal this owner emits has to
    render under that name rather than a package-derived one -- the same name
    the transport above it reports under.
    """

    def test_logger_keeps_its_operator_facing_name(self) -> None:
        self.assertEqual(credentials.log.name, PLUMBING_LOGGER)


class ResolvedTokenTest(unittest.TestCase):
    """The per-repository lookup names the misconfigured repo when it fails."""

    def test_returns_the_slug_token(self) -> None:
        resolver = MagicMock(return_value=FAKE_TOKEN)

        with patch.object(config, TOKEN_RESOLVER, resolver):
            token = credentials._resolved_git_token(
                _spec(REPOSITORY_SLUG), FETCH_OPERATION,
            )

        self.assertEqual(token, FAKE_TOKEN)
        resolver.assert_called_once_with(REPOSITORY_SLUG)

    def test_logs_slug_and_operation(self) -> None:
        # A multi-repo deployment missing one token file needs both the repo
        # and the blocked operation in the log to know which file to drop.
        with (
            patch.object(config, TOKEN_RESOLVER, return_value=""),
            self.assertLogs(credentials.log, level="ERROR") as logs,
        ):
            token = credentials._resolved_git_token(
                _spec(REPOSITORY_SLUG), FETCH_OPERATION,
            )
            self.assertIsNone(token)
            self.assertIn(REPOSITORY_SLUG, logs.output[0])
            self.assertIn(FETCH_OPERATION, logs.output[0])


class GitAuthEnvironmentTest(unittest.TestCase):
    """The detached environment carries the token and drops inherited config."""

    def test_detaches_global_and_system_config(self) -> None:
        auth_env = _auth_env(include_identity=False)

        self.assertEqual(auth_env["GIT_TOKEN"], FAKE_TOKEN)
        self.assertEqual(auth_env["GIT_CONFIG_GLOBAL"], os.devnull)
        self.assertEqual(auth_env["GIT_CONFIG_SYSTEM"], os.devnull)
        self.assertEqual(auth_env["GIT_CONFIG_NOSYSTEM"], "1")
        self.assertEqual(auth_env["GIT_TERMINAL_PROMPT"], "0")

    def test_identity_is_opt_in(self) -> None:
        # Detaching global config also strips `user.name` / `user.email`, so
        # the operations that replay commits ask for the agent identity; the
        # rest leave whatever the orchestrator process inherited in place.
        with patch.dict(os.environ, {COMMITTER_NAME_KEY: INHERITED_COMMITTER}):
            inherited = _auth_env(include_identity=False)
            overridden = _auth_env(include_identity=True)

        self.assertEqual(inherited[COMMITTER_NAME_KEY], INHERITED_COMMITTER)
        self.assertEqual(overridden[COMMITTER_NAME_KEY], config.AGENT_GIT_NAME)


class GitAuthSessionTest(unittest.TestCase):
    """The askpass script hands the token over without ever entering argv."""

    def test_askpass_prints_the_env_token(self) -> None:
        with credentials._git_auth_session(_spec(), FAKE_TOKEN) as session:
            printed = subprocess.run(
                [session.env[ASKPASS_KEY]],
                capture_output=True,
                text=True,
                env={"GIT_TOKEN": session.token},
                check=True,
            )

        self.assertEqual(printed.stdout, FAKE_TOKEN)

    def test_askpass_is_owner_only_and_transient(self) -> None:
        # The script sits in a world-readable /tmp for the length of one
        # operation, so it stays owner-only and is removed on exit.
        with credentials._git_auth_session(_spec(), FAKE_TOKEN) as session:
            askpass = Path(session.env[ASKPASS_KEY])
            mode = stat.S_IMODE(askpass.stat().st_mode)

        self.assertEqual(mode, ASKPASS_MODE)
        self.assertFalse(askpass.exists())

    def test_auth_url_carries_only_the_username(self) -> None:
        with credentials._git_auth_session(
            _spec(REPOSITORY_SLUG), FAKE_TOKEN,
        ) as session:
            auth_url = session.auth_url

        self.assertEqual(
            auth_url,
            f"https://x-access-token@github.com/{REPOSITORY_SLUG}.git",
        )
        self.assertNotIn(FAKE_TOKEN, auth_url)


if __name__ == "__main__":
    unittest.main()
