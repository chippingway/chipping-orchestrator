# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Hardened authenticated push owned by the branch transport."""

from __future__ import annotations

import contextlib
import unittest
from unittest.mock import MagicMock, patch

from orchestrator import config
from orchestrator.git import branch_transport
from tests.git.token_transport_test_support import (
    FAKE_TOKEN,
    REPOSITORY_SLUG,
    SUBPROCESS_RUN,
    TOKEN_RESOLVER,
    WORKTREE,
    _spec,
)
from tests.git.transport_helpers import (
    _temp_git_repo_with_local_config,
    _TokenResolver,
)

ISSUE_BRANCH = "orchestrator/issue-5"
ISSUE_REF = f"refs/heads/{ISSUE_BRANCH}"
FRESH_BRANCH = "orchestrator/issue-9"
ERROR_LEVEL = "ERROR"
GIT_FAILURE_EXIT_CODE = 128
HTTP_PROXY_KEY = "http.proxy"
LEAKY_STDERR = (
    f"fatal: unable to access 'https://x-access-token:{FAKE_TOKEN}@github.com'"
)
OBSERVED_SHA = "87b2bc94b03a1729ef8b8145836d0959f433600e"
PINNED_SHA = "deadbeefcafef00ddeadbeefcafef00ddeadbeef"
REWRITE_HIT = "url.https://evil.example.com/.insteadof https://github.com/\n"


def _git_result(
    *,
    returncode: int = 0,
    stdout: str = "",
    stderr: str = "",
) -> MagicMock:
    return MagicMock(returncode=returncode, stdout=stdout, stderr=stderr)


def _transport_failure() -> MagicMock:
    """Return a failed git run whose stderr carries the PAT git echoed back."""
    return _git_result(
        returncode=GIT_FAILURE_EXIT_CODE, stderr=LEAKY_STDERR,
    )


def _assert_token_scrubbed(test_case, log_output: list) -> None:
    """Assert the failure log carries the redaction rather than the PAT."""
    test_case.assertNotIn(FAKE_TOKEN, log_output[0])
    test_case.assertIn("***", log_output[0])


@contextlib.contextmanager
def _patched_push(run_results: list):
    """Serve one result per subprocess: transport probe, ls-remote, push."""
    run_mock = MagicMock(side_effect=run_results)
    with (
        patch.object(config, TOKEN_RESOLVER, return_value=FAKE_TOKEN),
        patch(SUBPROCESS_RUN, run_mock),
    ):
        yield run_mock


class PushBranchLeaseTest(unittest.TestCase):
    """`_push_branch` handles the divergence cases that bit issue-5.

    A self-restart can leave the local worktree on a different SHA than the
    one already pushed (e.g. codex `resume=False` rerun produced equivalent
    work with new committer dates). A plain push then fails non-fast-forward
    and parks the issue. The function uses ls-remote + --force-with-lease so
    the retry succeeds, and the lease still blocks unobserved updates.
    """

    def test_existing_remote_branch_uses_observed_sha(self) -> None:
        with _patched_push(
            [
                _git_result(),
                _git_result(stdout=f"{OBSERVED_SHA}\t{ISSUE_REF}\n"),
                _git_result(),
            ]
        ) as run_mock:
            ok = branch_transport._push_branch(_spec(), WORKTREE, ISSUE_BRANCH)
            self.assertTrue(ok)
            push_cmd = run_mock.call_args_list[2].args[0]
            self.assertIn("push", push_cmd)
            self.assertIn(
                f"--force-with-lease={ISSUE_REF}:{OBSERVED_SHA}",
                push_cmd,
            )
            self.assertIn(f"HEAD:{ISSUE_REF}", push_cmd)

    def test_missing_remote_branch_uses_empty_lease(self) -> None:
        # First push ever for this branch -- ls-remote returns nothing, the
        # lease becomes "expect ref to not exist" so a concurrent create still
        # fails the lease.
        with _patched_push(
            [
                _git_result(),
                _git_result(stdout=""),
                _git_result(),
            ]
        ) as run_mock:
            ok = branch_transport._push_branch(_spec(), WORKTREE, FRESH_BRANCH)
            self.assertTrue(ok)
            push_cmd = run_mock.call_args_list[2].args[0]
            self.assertIn(
                f"--force-with-lease=refs/heads/{FRESH_BRANCH}:",
                push_cmd,
            )

    def test_caller_lease_skips_the_remote_read(self) -> None:
        # The squash/rewrite path pins the lease to the caller's pre-rewrite
        # HEAD. Reading a fresh ls-remote instead would adopt an out-of-band
        # remote update as the lease value and silently clobber it.
        with _patched_push([_git_result(), _git_result()]) as run_mock:
            ok = branch_transport._push_branch(
                _spec(), WORKTREE, ISSUE_BRANCH, force_with_lease=PINNED_SHA,
            )
            self.assertTrue(ok)
            # Only the transport probe and the push ran -- no ls-remote.
            self.assertEqual(run_mock.call_count, 2)
            push_cmd = run_mock.call_args_list[1].args[0]
            self.assertIn(
                f"--force-with-lease={ISSUE_REF}:{PINNED_SHA}",
                push_cmd,
            )

    def test_a_named_revision_is_what_gets_published(self) -> None:
        # A caller that decided to push by INSPECTING a commit must publish
        # that commit. `HEAD` between the reading and the push is not
        # necessarily the same one -- another tick, an operator, or a stray
        # agent can move the branch -- so the refspec names the SHA rather
        # than whatever the worktree is on by the time git runs.
        with _patched_push(
            [
                _git_result(),
                _git_result(stdout=f"{OBSERVED_SHA}\t{ISSUE_REF}\n"),
                _git_result(),
            ]
        ) as run_mock:
            ok = branch_transport._push_branch(
                _spec(), WORKTREE, ISSUE_BRANCH, revision=PINNED_SHA,
            )
            self.assertTrue(ok)
            push_cmd = run_mock.call_args_list[2].args[0]
            self.assertIn(f"{PINNED_SHA}:{ISSUE_REF}", push_cmd)
            self.assertNotIn(f"HEAD:{ISSUE_REF}", push_cmd)

    def test_ls_remote_failure_aborts_without_pushing(self) -> None:
        # git echoes the remote URL in transport errors, so the diagnostic is
        # scrubbed before it reaches the log.
        with (
            _patched_push([_git_result(), _transport_failure()]) as run_mock,
            self.assertLogs(branch_transport.log, level=ERROR_LEVEL) as logs,
        ):
            ok = branch_transport._push_branch(_spec(), WORKTREE, ISSUE_BRANCH)
            # Only the transport probe and ls-remote ran; the push subprocess
            # was not invoked.
            self.assertEqual(run_mock.call_count, 2)
            log_output = logs.output

        self.assertFalse(ok)
        _assert_token_scrubbed(self, log_output)


class PushBranchTokenTest(unittest.TestCase):
    """The push authenticates with `spec.slug`'s token and never leaks it."""

    def test_uses_per_spec_token_for_git_push(self) -> None:
        # Multi-repo regression guard: `_push_branch` must resolve the token
        # from `spec.slug` (so a per-repo `~/.config/<owner>/<repo>/token`
        # file is honored), not from the cached single-repo
        # `config.GITHUB_TOKEN` that was looked up once for `config.REPO`.
        run_mock = MagicMock(
            side_effect=[
                _git_result(),
                _git_result(stdout=f"{PINNED_SHA}\t{ISSUE_REF}\n"),
                _git_result(),
            ]
        )
        token_resolver = _TokenResolver()

        with (
            patch.object(config, TOKEN_RESOLVER, token_resolver),
            patch(SUBPROCESS_RUN, run_mock),
        ):
            self.assertTrue(
                branch_transport._push_branch(
                    _spec(REPOSITORY_SLUG), WORKTREE, ISSUE_BRANCH,
                )
            )

        # Token was resolved exactly once, for the spec's slug.
        self.assertEqual(token_resolver.slugs, [REPOSITORY_SLUG])
        ls_call = run_mock.call_args_list[1]
        push_call = run_mock.call_args_list[2]
        # ls-remote and push both run with the per-spec token in GIT_TOKEN.
        self.assertEqual(
            ls_call.kwargs["env"]["GIT_TOKEN"], "ghp-token-for-acme-widgets",
        )
        self.assertEqual(
            push_call.kwargs["env"]["GIT_TOKEN"], "ghp-token-for-acme-widgets",
        )
        # Auth URL targets the spec's slug, not the cached config.REPO.
        self.assertIn(
            "https://x-access-token@github.com/acme/widgets.git",
            ls_call.args[0],
        )

    def test_missing_spec_token_logs_slug_and_aborts(self) -> None:
        # A multi-repo deployment that forgot to populate the per-slug token
        # file should refuse to push and name the misconfigured repo rather
        # than emitting a generic "GITHUB_TOKEN missing".
        run_mock = MagicMock()

        with (
            patch.object(config, TOKEN_RESOLVER, return_value=""),
            patch(SUBPROCESS_RUN, run_mock),
            self.assertLogs(branch_transport.log, level=ERROR_LEVEL) as logs,
        ):
            ok = branch_transport._push_branch(
                _spec(REPOSITORY_SLUG), WORKTREE, ISSUE_BRANCH,
            )
            log_output = logs.output

        self.assertFalse(ok)
        # Push aborted before any subprocess ran.
        run_mock.assert_not_called()
        self.assertIn(REPOSITORY_SLUG, log_output[0])


class PushBranchRefusalTest(unittest.TestCase):
    """Agent-writable transport config and push rejections fail closed."""

    def test_push_failure_returns_false(self) -> None:
        with (
            _patched_push(
                [
                    _git_result(),
                    _git_result(stdout=f"{OBSERVED_SHA}\t{ISSUE_REF}\n"),
                    _transport_failure(),
                ]
            ),
            self.assertLogs(branch_transport.log, level=ERROR_LEVEL) as logs,
        ):
            ok = branch_transport._push_branch(_spec(), WORKTREE, ISSUE_BRANCH)
            log_output = logs.output

        self.assertFalse(ok)
        _assert_token_scrubbed(self, log_output)

    def test_url_rewrite_in_local_config_refuses_push(self) -> None:
        # Local .git/config carrying a url.<host>.insteadOf rewrite is the
        # exfil vector the security hardening guards against; ls-remote and
        # push must never run.
        with _patched_push([_git_result(stdout=REWRITE_HIT)]) as run_mock:
            ok = branch_transport._push_branch(_spec(), WORKTREE, ISSUE_BRANCH)
            self.assertFalse(ok)
            self.assertEqual(run_mock.call_count, 1)

    def test_refuses_on_real_local_http_proxy(self) -> None:
        # The url-rewrite refusal above mocks the config probe, so it cannot
        # prove the regexp catches http.* keys. Real git config resolution: a
        # worktree carrying `http.proxy` must fail closed before the
        # token-bearing push runs.
        with (
            _temp_git_repo_with_local_config(
                [(HTTP_PROXY_KEY, "http://evil.example:8080")],
            ) as repo,
            patch.object(config, TOKEN_RESOLVER, return_value=FAKE_TOKEN),
            self.assertLogs(branch_transport.log, level=ERROR_LEVEL) as logs,
        ):
            ok = branch_transport._push_branch(_spec(), repo, ISSUE_BRANCH)
            log_output = logs.output

        self.assertFalse(ok)
        self.assertTrue(
            any(HTTP_PROXY_KEY in line for line in log_output),
            f"expected {HTTP_PROXY_KEY} in refusal log, got {log_output!r}",
        )


if __name__ == "__main__":
    unittest.main()
