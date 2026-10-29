# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Tests for implementing full spec reader behavior."""

from __future__ import annotations

import unittest

from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.stages.implementing import session_read as _session_read
from tests.support import agy_stream
from tests.workflow.stages import full_spec_test_support as support

BACKEND_CLAUDE = support.BACKEND_CLAUDE
BACKEND_CODEX = support.BACKEND_CODEX
CLAUDE_ARGS = support.CLAUDE_ARGS
CLAUDE_SPEC = support.CLAUDE_SPEC
CODEX_ARGS = support.CODEX_ARGS
CODEX_SPEC = support.CODEX_SPEC
DEV_AGENT_KEY = support.DEV_AGENT_KEY
DEV_SESSION_ID = support.DEV_SESSION_ID
_FullSpecFixtureMixin = support._FullSpecFixtureMixin


# A conversation id under a key no current release reads.
_UNREAD_SESSION_KEY = "codex_session_id"


class FullSpecSessionReaderTest(unittest.TestCase, _FullSpecFixtureMixin):
    def test_read_dev_session_round_trips_full_spec(self) -> None:
        # A plain backend is a current spec like any full one: it locks that
        # backend with no arguments, whatever the configuration says now.
        self._enter(self._patch_dev_config(CLAUDE_SPEC, BACKEND_CLAUDE, CLAUDE_ARGS))
        for spec, backend, args in (
            (CODEX_SPEC, BACKEND_CODEX, CODEX_ARGS),
            (agy_stream.SPEC, agy_stream.BACKEND, agy_stream.ARGS),
            (BACKEND_CODEX, BACKEND_CODEX, ()),
            (BACKEND_CLAUDE, BACKEND_CLAUDE, ()),
        ):
            with self.subTest(spec=spec):
                self.assertEqual(
                    _session_read._read_dev_session(
                        PinnedState(state_data={DEV_AGENT_KEY: spec, DEV_SESSION_ID: "sid-y"}),
                    ),
                    (spec, backend, args, "sid-y"),
                )

    def test_unseeded_dev_session_uses_config(self) -> None:
        # Only `dev_agent` and `dev_session_id` lock a session: a conversation
        # id under any other key is neither resumed nor given a backend.
        self._enter(
            self._patch_dev_config(
                CLAUDE_SPEC,
                BACKEND_CLAUDE,
                CLAUDE_ARGS,
            )
        )
        for seeded in ({}, {_UNREAD_SESSION_KEY: "unread-sid"}):
            with self.subTest(seeded=seeded):
                self.assertEqual(
                    _session_read._read_dev_session(PinnedState(state_data=seeded)),
                    (CLAUDE_SPEC, BACKEND_CLAUDE, CLAUDE_ARGS, None),
                )
