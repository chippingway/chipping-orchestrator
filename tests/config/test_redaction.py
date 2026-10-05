# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Secret-redaction tests for the credentials owner."""

import os
import unittest
from unittest.mock import patch

from orchestrator.config import credentials

_REDACTION_MARKER = "***"
_CONFIGURED_TOKENS = "orchestrator.config.GITHUB_TOKENS"


def _patched_env(**env_values: str):
    return patch.dict(os.environ, env_values, clear=False)


class RedactSecretsTest(unittest.TestCase):
    """The agent retains its provider auth (ANTHROPIC_API_KEY etc.) so that
    its CLI can talk to the model. Anything we surface from its stderr to
    GitHub must scrub those values first; otherwise a prompt-injected agent
    that echoed its key onto stderr would leak it into a public issue.
    """

    def test_redacts_provider_api_key(self) -> None:
        with _patched_env(ANTHROPIC_API_KEY="sk-ant-supersecretvalue123"):
            out = credentials.redact_secrets(
                "Traceback ...\n  401 sk-ant-supersecretvalue123 invalid"
            )
        self.assertNotIn("sk-ant-supersecretvalue123", out)
        self.assertIn(_REDACTION_MARKER, out)

    def test_redacts_github_token_by_exact_name(self) -> None:
        # GITHUB_TOKEN itself doesn't end in any of the suffixes we strip,
        # but it's the orchestrator's own creds for git/gh subprocesses --
        # cover it explicitly via _SECRET_KEY_NAMES.
        with _patched_env(GITHUB_TOKEN="ghp_thisisthetokenvalue"):
            out = credentials.redact_secrets("remote: bad credential ghp_thisisthetokenvalue")
        self.assertNotIn("ghp_thisisthetokenvalue", out)

    def test_redacts_every_file_backed_token(self) -> None:
        # Token files (ORCHESTRATOR_TOKEN_FILE / each repository's default
        # ~/.config/<owner>/<repo>/token) populate config.GITHUB_TOKENS
        # without touching os.environ. The env-loop alone would miss them, so
        # the resolved setting is read straight off `orchestrator.config` at
        # call time, and every configured repository's token is masked, not
        # only the first one's: agent stderr that cat'd a second repository's
        # token file would otherwise leak it into the park comment.
        first_token = "ghp_filebackedtokenvalue9876"
        second_token = "ghp_secondrepositorytoken5432"
        # Ensure the env path wouldn't catch either on its own.
        env_without_token = dict(os.environ)
        env_without_token.pop("GITHUB_TOKEN", None)
        with patch.dict(os.environ, env_without_token, clear=True), \
                patch(_CONFIGURED_TOKENS, (first_token, second_token)):
            out = credentials.redact_secrets(
                f"cat ran: {first_token} and {second_token} got captured",
            )
        self.assertNotIn(first_token, out)
        self.assertNotIn(second_token, out)
        self.assertEqual(out.count(_REDACTION_MARKER), 2)

    def test_redacts_arbitrary_provider_via_suffix(self) -> None:
        # The suffix list is what catches the long tail (HF_TOKEN,
        # GEMINI_API_KEY, ...) without us enumerating every provider.
        with _patched_env(GEMINI_API_KEY="ya29.deadbeefdeadbeef"):
            out = credentials.redact_secrets("got ya29.deadbeefdeadbeef back")
        self.assertNotIn("ya29.deadbeefdeadbeef", out)

    def test_redacts_bare_name_secret(self) -> None:
        # Bare names like `TOKEN` or `PASSWORD` don't end in `_TOKEN` etc.,
        # so the suffix predicate misses them. agent_env only strips
        # GitHub-aliased tokens, so a bare $TOKEN passes through to the
        # agent and would leak unredacted if echoed to stderr.
        with _patched_env(TOKEN="ghp_barenametokenvalue123"):
            out = credentials.redact_secrets("auth failed for ghp_barenametokenvalue123")
        self.assertNotIn("ghp_barenametokenvalue123", out)
        with _patched_env(PASSWORD="hunter2isthepasswordvalue"):
            out = credentials.redact_secrets("login: hunter2isthepasswordvalue rejected")
        self.assertNotIn("hunter2isthepasswordvalue", out)


class RedactionBoundaryTest(unittest.TestCase):
    """Redaction preserves harmless text and handles empty input."""

    def test_leaves_short_values_alone(self) -> None:
        # A 4-char throwaway value would mask incidental substrings. The
        # min-length floor protects regular english text in stderr.
        with _patched_env(DEV_KEY="true"):
            out = credentials.redact_secrets("status was true and the build ran")
        self.assertEqual(out, "status was true and the build ran")

    def test_leaves_non_secret_keys_alone(self) -> None:
        with _patched_env(BUILD_NUMBER="this-string-is-long-enough"):
            out = credentials.redact_secrets("BUILD this-string-is-long-enough done")
        self.assertIn("this-string-is-long-enough", out)

    def test_empty_input_passthrough(self) -> None:
        self.assertEqual(credentials.redact_secrets(""), "")
