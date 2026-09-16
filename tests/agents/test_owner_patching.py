# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Backend runners route options and env through the package owners."""

from __future__ import annotations

import unittest
from unittest.mock import patch

from orchestrator.agents import (
    environment as _environment,
    runner as _runner,
    session_ids as _session_ids,
    sessions as _sessions,
)
from orchestrator.agents.backends import agy as _agy, claude as _claude, codex as _codex
from tests.agents import agent_test_support as _support, agent_test_values as _agent_cases

# (label, backend runner) pairs so each owner-routing assertion runs against
# every backend without duplicating the body per backend.
_BACKENDS = (
    ("agy", _agy.run_agy),
    (_agent_cases._CODEX, _codex.run_codex),
    (_agent_cases._CLAUDE, _claude.run_claude),
)


class RunnerOwnerRoutingTest(unittest.TestCase):
    """Patching the `runner` / `environment` owners intercepts every backend.

    The Codex / Claude / Antigravity backends resolve run options through
    `runner.resolve_agent_run_options` and the child environment through
    `environment.agent_env` -- the direct owners, not facade-captured
    aliases -- so a monkeypatch on the owner module is observed by the
    runner rather than silently bypassed.
    """

    def test_env_reaches_environment_owner(self) -> None:
        for label, backend_runner in _BACKENDS:
            with self.subTest(backend=label):
                marker_env = {"MARKER_ENV": "owner-sentinel"}
                with (
                    patch.object(
                        _environment,
                        "agent_env",
                        return_value=marker_env,
                    ) as env_owner,
                    patch(
                        _agent_cases._POPEN_TARGET,
                        return_value=_support.completed(),
                    ) as run_mock,
                ):
                    backend_runner(_agent_cases._PROMPT, _agent_cases._CWD)
                    self.assertEqual(env_owner.call_count, 1)
                    self.assertEqual(
                        run_mock.call_args.kwargs[_agent_cases._ENV_KWARG],
                        marker_env,
                    )

    def test_options_reach_runner_owner(self) -> None:
        for label, backend_runner in _BACKENDS:
            with (
                self.subTest(backend=label),
                patch.object(
                    _runner,
                    "resolve_agent_run_options",
                    wraps=_runner.resolve_agent_run_options,
                ) as resolve_owner,
                patch(
                    _agent_cases._POPEN_TARGET,
                    return_value=_support.completed(),
                ),
            ):
                backend_runner(_agent_cases._PROMPT, _agent_cases._CWD)
                self.assertEqual(resolve_owner.call_count, 1)


class ParserOwnerRoutingTest(unittest.TestCase):
    """Patching a parser owner intercepts the backends reading through it.

    Result assembly harvests the session id through
    `session_ids.parse_session_id`, and the Claude backend resolves its final
    message through `sessions.claude_last_message` -- each the direct owner
    module, not a parser captured onto a facade alias -- so a monkeypatch on
    the owner is observed by the runner rather than silently bypassed.
    """

    def test_session_id_reaches_session_ids_owner(self) -> None:
        for label, backend_runner in _BACKENDS:
            with (
                self.subTest(backend=label),
                patch.object(
                    _session_ids,
                    "parse_session_id",
                    return_value="owner-session-id",
                ) as parse_owner,
                patch(
                    _agent_cases._POPEN_TARGET,
                    return_value=_support.completed(),
                ),
            ):
                agent_result = backend_runner(
                    _agent_cases._PROMPT,
                    _agent_cases._CWD,
                )
                self.assertEqual(parse_owner.call_count, 1)
                self.assertEqual(agent_result.session_id, "owner-session-id")

    def test_final_message_reaches_sessions_owner(self) -> None:
        with (
            patch.object(
                _sessions,
                "claude_last_message",
                return_value="owner-final-message",
            ) as message_owner,
            patch(
                _agent_cases._POPEN_TARGET,
                return_value=_support.completed(),
            ),
        ):
            agent_result = _claude.run_claude(
                _agent_cases._PROMPT,
                _agent_cases._CWD,
            )
            self.assertEqual(message_owner.call_count, 1)
            self.assertEqual(agent_result.last_message, "owner-final-message")
