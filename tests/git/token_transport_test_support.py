# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Repo specs and hardening assertions shared by the token-bearing git tests."""

from __future__ import annotations

import os
from pathlib import Path

from orchestrator.config import models as _config_models

SUBPROCESS_RUN = "subprocess.run"
TOKEN_RESOLVER = "_resolve_github_token"
MAIN_BRANCH = "main"
TEMP_ROOT = Path("/tmp")
WORKTREE = Path("/tmp/orchestrator-test-worktree")
AUTH_URL_PREFIX = "https://x-access-token@github.com/"

REPOSITORY_SLUG = "acme/widgets"
PRIVATE_REPO_SLUG = "geserdugarov/lance-private"
CACHE_BRANCH = "cache-branch"

FAKE_TOKEN = "fake-token-xyz"
SECRET_TOKEN = "super-secret-token"

# The `-c` overrides that keep an agent-writable `.git/config` from executing
# code or rewriting transport while the token-bearing fetch runs.
HARDENING_OVERRIDES = (
    "core.hooksPath=/dev/null",
    "credential.helper=",
    "core.fsmonitor=",
)


def _spec(
    repo_slug: str = REPOSITORY_SLUG,
    *,
    base_branch: str = MAIN_BRANCH,
    remote_name: str = "origin",
) -> _config_models.RepoSpec:
    return _config_models.RepoSpec(
        slug=repo_slug,
        target_root=Path("/tmp/orchestrator-test-target-root"),
        base_branch=base_branch,
        remote_name=remote_name,
    )


def _assert_token_stayed_out_of_argv(test_case, argv, token: str) -> None:
    for argument in argv:
        test_case.assertNotIn(token, str(argument))


def _assert_hardened_fetch(test_case, run_recorder, token: str) -> None:
    """Assert the recorded fetch carries the whole token-bearing envelope."""
    environment = run_recorder.env
    test_case.assertIn("GIT_ASKPASS", environment)
    test_case.assertEqual(environment.get("GIT_TOKEN"), token)
    # Global/system git config detached so url rewrites planted in
    # `~/.gitconfig` cannot redirect the fetch.
    test_case.assertEqual(environment.get("GIT_CONFIG_GLOBAL"), os.devnull)
    test_case.assertEqual(environment.get("GIT_CONFIG_SYSTEM"), os.devnull)
    arguments = run_recorder.args
    # The token would surface in /proc/<pid>/cmdline if it reached argv.
    _assert_token_stayed_out_of_argv(test_case, arguments, token)
    for override in HARDENING_OVERRIDES:
        test_case.assertIn(override, arguments)
    test_case.assertTrue(
        any(
            isinstance(candidate, str) and candidate.startswith(AUTH_URL_PREFIX)
            for candidate in arguments
        ),
        f"expected x-access-token auth URL in argv, got {arguments!r}",
    )
