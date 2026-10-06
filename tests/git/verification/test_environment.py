# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Child-environment stripping and output redaction of a real verify run."""

from __future__ import annotations

import os
import shlex
import unittest
from unittest.mock import patch

from orchestrator.git.verification import runner
from tests.git.verification import command_helpers

VERIFY_FAILED = "failed"
OUTPUT_BUDGET = 4096
SECRET_PREFIX_SIZE = 90
REDACTION_PAYLOAD_SIZE = 4200


class _VerifyEnvironmentAssertionsMixin:
    def _boundary_payload(self):
        secret = "SUPERSECRET-TOKEN-VALUE-0123456789ABCDEF"
        prefix = "P" * SECRET_PREFIX_SIZE
        suffix = "S" * (
            REDACTION_PAYLOAD_SIZE
            - len(prefix)
            - len(secret)
        )
        payload = prefix + secret + suffix
        self.assertEqual(len(payload), REDACTION_PAYLOAD_SIZE)
        cut = len(payload) - OUTPUT_BUDGET
        self.assertLess(payload.index(secret), cut)
        self.assertGreater(payload.index(secret) + len(secret), cut)
        return secret, payload

    def _assert_no_secret_fragments(self, secret: str, output: str) -> None:
        for start in range(len(secret) - 7):
            secret_fragment = secret[start:start + 8]
            self.assertNotIn(
                secret_fragment,
                output,
                f"partial secret substring leaked: {secret_fragment!r}",
            )

    def _assert_production_values_hidden(self, output: str) -> None:
        self.assertNotIn("sk_live_VERY_SECRET_SHOULD_NOT_LEAK", output)
        self.assertNotIn("hunter2_should_not_leak", output)
        self.assertNotIn("deploytok_should_not_leak", output)
        self.assertNotIn("sk-ant-SHOULD_NOT_LEAK_TO_VERIFY", output)
        self.assertNotIn("sk-oai-SHOULD_NOT_LEAK_TO_VERIFY", output)


class VerifyCommandEnvironmentTest(
    command_helpers.VerifyCommandsFixtureMixin,
    unittest.TestCase,
    _VerifyEnvironmentAssertionsMixin,
):
    """Redact output and strip secrets or credential locators from env."""

    def test_virtualenv_filter_preserves_conda(self) -> None:
        with patch.dict(os.environ, {
            "VIRTUAL_ENV": "/srv/orchestrator/.venv",
            "CONDA_PREFIX": "/opt/conda/envs/operator",
            "CONDA_DEFAULT_ENV": "operator",
            "CONDA_SHLVL": "1",
            "PATH": (
                "/srv/orchestrator/.venv/bin:/opt/conda/envs/operator/bin:"
                "/usr/bin:/bin:/srv/orchestrator/.venv/bin"
            ),
        }):
            commands = (
                'test -z "${VIRTUAL_ENV+x}"',
                'test "$CONDA_PREFIX" = /opt/conda/envs/operator',
                'test "$CONDA_DEFAULT_ENV" = operator',
                'test "$CONDA_SHLVL" = 1',
                'test "$PATH" = /opt/conda/envs/operator/bin:/usr/bin:/bin',
            )
            run = runner._run_verify_commands(self.worktree, commands, 60)
        self.assertEqual(run.status, "ok")

    def test_boundary_secret_fully_redacted(self) -> None:
        # `redact_secrets` does `str.replace(value, "***")` on the full
        # value, so a secret whose bytes straddle the truncation cut
        # would no longer match a post-truncation replace and would leak
        # a partial value verbatim in the park comment. The redact pass
        # runs BEFORE truncating so any matched secret collapses to
        # `***` before its bytes can be sliced.
        secret, payload = self._boundary_payload()
        # Engineer the payload so the truncation cut (last 4096 bytes)
        # falls inside the secret rather than before it. Budget = 4096;
        # we want secret_start < (total - 4096) < secret_end so a
        # "truncate-then-redact" pass would leak the secret's tail.
        # total = 4200 → cut at byte 104; secret occupies 90..129, so
        # bytes 14..39 of the secret (`E-0123456789ABCDEF`) would survive
        # a naive truncation.
        cmd = f"sh -c 'printf %s {shlex.quote(payload)}; exit 1'"
        with patch.dict(os.environ, {"VERIFY_TEST_API_KEY": secret}):
            run = runner._run_verify_commands(self.worktree, (cmd,), 60)
        self.assertEqual(run.status, VERIFY_FAILED)
        # The full secret must be gone -- baseline check.
        self.assertNotIn(secret, run.output)
        # And no 8+ char substring of the secret survives either.
        # Length 8 matches `_REDACT_MIN_VALUE_LEN`: shorter accidental
        # collisions are below the redaction threshold and tolerable.
        self._assert_no_secret_fragments(secret, run.output)
        # And the redaction marker is present (proves the runner
        # actually saw and replaced the secret).
        self.assertIn("***", run.output)

    def test_github_token_stripped_from_env(self) -> None:
        # Verify commands run in the per-issue worktree against code the
        # implementer agent just produced. If the runner inherited the
        # orchestrator's process env, a prompt-injected `pytest` plugin
        # (or a hostile dependency) could read `$GITHUB_TOKEN` and push
        # or call the GitHub API as us. The runner strips via
        # `filter_agent_env`, mirroring what `agent_env` does for the
        # implementer / reviewer subprocesses.
        cmd = (
            # `printenv GITHUB_TOKEN` prints the value if the var is in
            # the child env and exits 0; if unset, it prints nothing and
            # exits 1. We pipe both branches through `exit 1` so the
            # runner reports the verify as failed and we can inspect
            # `run.output` either way.
            "sh -c 'echo TOKEN_PRESENT=$([ -n \"$GITHUB_TOKEN\" ] && echo YES || echo NO); exit 1'"
        )
        with patch.dict(
            os.environ,
            {"GITHUB_TOKEN": "ghp_ORCHESTRATOR_PAT_SHOULD_NOT_LEAK"},
        ):
            run = runner._run_verify_commands(self.worktree, (cmd,), 60)
        self.assertEqual(run.status, VERIFY_FAILED)
        # The verify environment must NOT carry GITHUB_TOKEN through.
        self.assertIn("TOKEN_PRESENT=NO", run.output)
        # And the original token value must not appear verbatim. (This
        # also catches redaction doing the heavy lifting instead of env
        # stripping -- redaction would mask the value with `***`, but the
        # variable would still have been exposed to the verify command.)
        self.assertNotIn("ghp_ORCHESTRATOR_PAT_SHOULD_NOT_LEAK", run.output)

    def test_strips_write_locators_from_env(self) -> None:
        # SSH-agent socket, askpass binaries, and `GIT_SSH_COMMAND` are
        # write-credential pointers, not secret-shaped values. Leaving
        # them in the verify shell lets a hostile dependency forward
        # through the operator's loaded ssh-agent (and push to any host
        # whose key is loaded) or invoke the operator's askpass binary in
        # their session.
        cmd = (
            "sh -c '"
            'echo SSH_AUTH=$([ -n "$SSH_AUTH_SOCK" ] && echo YES || echo NO); '
            'echo SSH_ASK=$([ -n "$SSH_ASKPASS" ] && echo YES || echo NO); '
            'echo GIT_ASK=$([ -n "$GIT_ASKPASS" ] && echo YES || echo NO); '
            'echo GIT_SSH=$([ -n "$GIT_SSH_COMMAND" ] && echo YES || echo NO); '
            "exit 1'"
        )
        with patch.dict(
            os.environ,
            {
                "SSH_AUTH_SOCK": "/tmp/ssh-test/agent.42",
                "SSH_ASKPASS": "/usr/lib/ssh/ssh-askpass",
                "GIT_ASKPASS": "/usr/share/git/askpass-helper",
                "GIT_SSH_COMMAND": "ssh -i /home/op/.ssh/deploy-key",
            },
        ):
            run = runner._run_verify_commands(self.worktree, (cmd,), 60)
        self.assertEqual(run.status, VERIFY_FAILED)
        self.assertIn("SSH_AUTH=NO", run.output)
        self.assertIn("SSH_ASK=NO", run.output)
        self.assertIn("GIT_ASK=NO", run.output)
        self.assertIn("GIT_SSH=NO", run.output)
        # The locator values must not survive verbatim anywhere.
        self.assertNotIn("/tmp/ssh-test/agent.42", run.output)
        self.assertNotIn("/home/op/.ssh/deploy-key", run.output)

    def test_strips_credential_file_locators_from_env(self) -> None:
        # Credential-file LOCATORS (env vars whose value is a path to a
        # file holding the secret) must also be stripped. The verify
        # shell runs as the same OS user as the orchestrator, so leaving
        # `ORCHESTRATOR_TOKEN_FILE` / `GOOGLE_APPLICATION_CREDENTIALS` /
        # `AWS_SHARED_CREDENTIALS_FILE` in the child env lets a hostile
        # dependency simply `cat` the pointer's target. The
        # `ORCHESTRATOR_TOKEN_FILE` strip is the most important case: it
        # points at the orchestrator's own write-credential file.
        cmd = (
            "sh -c '"
            'echo ORCH_TF=$([ -n "$ORCHESTRATOR_TOKEN_FILE" ] && '
            "echo YES || echo NO); "
            'echo GAC=$([ -n "$GOOGLE_APPLICATION_CREDENTIALS" ] && '
            "echo YES || echo NO); "
            'echo AWS_SCF=$([ -n "$AWS_SHARED_CREDENTIALS_FILE" ] && '
            "echo YES || echo NO); "
            "exit 1'"
        )
        with patch.dict(
            os.environ,
            {
                "ORCHESTRATOR_TOKEN_FILE": "/etc/secrets/orch-token-path",
                "GOOGLE_APPLICATION_CREDENTIALS": "/etc/secrets/gcp.json",
                "AWS_SHARED_CREDENTIALS_FILE": "/etc/secrets/aws-creds",
            },
        ):
            run = runner._run_verify_commands(self.worktree, (cmd,), 60)
        self.assertEqual(run.status, VERIFY_FAILED)
        self.assertIn("ORCH_TF=NO", run.output)
        self.assertIn("GAC=NO", run.output)
        self.assertIn("AWS_SCF=NO", run.output)
        # And the locator path itself must not survive verbatim either
        # (env strip, not redaction-only).
        self.assertNotIn("/etc/secrets/orch-token-path", run.output)
        self.assertNotIn("/etc/secrets/gcp.json", run.output)
        self.assertNotIn("/etc/secrets/aws-creds", run.output)

    def test_strips_production_secret_shapes_from_env(self) -> None:
        # GitHub-token aliases are not the only credential shape that
        # should not be inherited by operator-configured verify shell.
        # Production-secret-shaped variables (suffix or bare-name
        # matches) must be stripped too. The verify runner ALSO strips
        # the agent's provider-auth keys (`ANTHROPIC_API_KEY`,
        # `OPENAI_API_KEY`) -- unlike the agent subprocess case, where
        # the allowlist preserves them, the verify shell executes
        # untrusted agent-produced code and a hostile dependency reading
        # `$ANTHROPIC_API_KEY` would gain billable access to the
        # operator's model account.
        cmd = (
            'sh -c \'echo STRIPE_PRESENT=$([ -n "$STRIPE_API_KEY" ] && '
            "echo YES || echo NO); "
            'echo DBPW_PRESENT=$([ -n "$DATABASE_PASSWORD" ] && '
            "echo YES || echo NO); "
            'echo DEPLOY_PRESENT=$([ -n "$DEPLOY_TOKEN" ] && '
            "echo YES || echo NO); "
            'echo ANTH_PRESENT=$([ -n "$ANTHROPIC_API_KEY" ] && '
            "echo YES || echo NO); "
            'echo OPENAI_PRESENT=$([ -n "$OPENAI_API_KEY" ] && '
            "echo YES || echo NO); exit 1'"
        )
        with patch.dict(
            os.environ,
            {
                "STRIPE_API_KEY": "sk_live_VERY_SECRET_SHOULD_NOT_LEAK",
                "DATABASE_PASSWORD": "hunter2_should_not_leak",
                "DEPLOY_TOKEN": "deploytok_should_not_leak",
                "ANTHROPIC_API_KEY": "sk-ant-SHOULD_NOT_LEAK_TO_VERIFY",
                "OPENAI_API_KEY": "sk-oai-SHOULD_NOT_LEAK_TO_VERIFY",
            },
        ):
            run = runner._run_verify_commands(self.worktree, (cmd,), 60)
        self.assertEqual(run.status, VERIFY_FAILED)
        self.assertIn("STRIPE_PRESENT=NO", run.output)
        self.assertIn("DBPW_PRESENT=NO", run.output)
        self.assertIn("DEPLOY_PRESENT=NO", run.output)
        # Provider auth is stripped from the verify env -- stricter
        # than the agent-subprocess case. An operator who legitimately
        # wants to drive the agent from a verify command sets the key
        # inline (`ANTHROPIC_API_KEY=... pytest ...`).
        self.assertIn("ANTH_PRESENT=NO", run.output)
        self.assertIn("OPENAI_PRESENT=NO", run.output)
        # The stripped secret values must not appear verbatim anywhere
        # in the captured output (env strip, not redaction-only).
        self._assert_production_values_hidden(run.output)


if __name__ == "__main__":
    unittest.main()
