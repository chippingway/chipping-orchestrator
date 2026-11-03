# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Tests for full-spec decomposer persistence behavior."""

from __future__ import annotations

import unittest

from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.engine import content_hash as _content_hash
from orchestrator.workflow.stages.decomposition import run as _decomposing, session as _decomposer_session
from tests.workflow.stages import full_spec_test_support as support
from tests.workflow.stages.decomposition import correction_tick_support as _corrected

BACKEND_CLAUDE = support.BACKEND_CLAUDE
BACKEND_CODEX = support.BACKEND_CODEX
CLAUDE_ARGS = support.CLAUDE_ARGS
CLAUDE_SPEC = support.CLAUDE_SPEC
CODEX_ARGS = support.CODEX_ARGS
CODEX_SPEC = support.CODEX_SPEC
DECOMPOSER_AGENT = support.DECOMPOSER_AGENT
DECOMPOSER_PARK_ID = support.DECOMPOSER_PARK_ID
DECOMPOSER_REPLY_ID = support.DECOMPOSER_REPLY_ID
EXTRA_ARGS = support.EXTRA_ARGS
FRESH_DECOMPOSER_ISSUE = support.FRESH_DECOMPOSER_ISSUE
FakeComment = support.FakeComment
FakeGitHubClient = support.FakeGitHubClient
FakeUser = support.FakeUser
LABEL_DECOMPOSING = support.LABEL_DECOMPOSING
RESUMED_DECOMPOSER_ISSUE = support.RESUMED_DECOMPOSER_ISSUE
RESUME_SESSION_ID = support.RESUME_SESSION_ID
RUN_AGENT = support.RUN_AGENT
TEST_AUTHOR = support.TEST_AUTHOR
_FullSpecFixtureMixin = support._FullSpecFixtureMixin
_TEST_SPEC = support._TEST_SPEC
_agent = support._agent
make_issue = support.make_issue


class FullSpecDecomposerPersistenceTest(
    unittest.TestCase,
    _FullSpecFixtureMixin,
):
    def test_fresh_decomposer_spawn_stores_full_spec(self) -> None:
        gh = FakeGitHubClient()
        issue = make_issue(FRESH_DECOMPOSER_ISSUE, label=LABEL_DECOMPOSING)
        gh.add_issue(issue)

        self._enter(
            self._patch_decompose_config(
                CODEX_SPEC,
                BACKEND_CODEX,
                CODEX_ARGS,
            )
        )

        # Manifest "single" -- simplest successful decompose path.
        manifest = 'OK\n\n```orchestrator-manifest\n{"decision": "single", "rationale": "fits one context"}\n```\n'
        mocks = self._run(
            lambda: _decomposing._handle_decomposing(gh, _TEST_SPEC, issue),
            run_agent=_agent(session_id="dec-67020", last_message=manifest),
        )

        call = mocks[RUN_AGENT].call_args
        self.assertEqual(call.args[0], BACKEND_CODEX)
        self.assertEqual(call.kwargs["options"].extra_args, CODEX_ARGS)
        self._pinned_data = gh.pinned_data(FRESH_DECOMPOSER_ISSUE)
        # Full spec, not the bare backend.
        self.assertEqual(self._pinned_data[DECOMPOSER_AGENT], CODEX_SPEC)
        self.assertEqual(self._pinned_data["decomposer_session_id"], "dec-67020")

    def test_decomposer_resume_uses_stored_spec(self) -> None:
        # Pinned with the full codex spec. After DECOMPOSE_AGENT flips to
        # claude, the awaiting-human resume must still resume on codex
        # with the codex args, not retarget the next call to claude -- over
        # a baseline recorded before the reply, which the reply moves past
        # without being read as an edit that retires the session.
        parked = FakeComment(id=DECOMPOSER_PARK_ID, body="park", user=FakeUser("orchestrator"))
        gh = FakeGitHubClient()
        issue = make_issue(
            RESUMED_DECOMPOSER_ISSUE,
            label=LABEL_DECOMPOSING,
            comments=[
                parked,
                FakeComment(id=DECOMPOSER_REPLY_ID, body="please split", user=FakeUser(TEST_AUTHOR)),
            ],
        )
        gh.add_issue(issue)
        gh.seed_state(
            RESUMED_DECOMPOSER_ISSUE,
            awaiting_human=True,
            last_action_comment_id=DECOMPOSER_PARK_ID,
            decomposer_agent=CODEX_SPEC,
            decomposer_session_id="dec-67021",
            user_content_hash=_content_hash._compute_user_content_hash(issue, set(), comments=[parked]),
        )

        self._enter(
            self._patch_decompose_config(
                CLAUDE_SPEC,
                BACKEND_CLAUDE,
                CLAUDE_ARGS,
            )
        )

        mocks = self._run(
            lambda: _decomposing._handle_decomposing(gh, _TEST_SPEC, issue),
            run_agent=_agent(
                session_id="dec-67021",
                last_message=('OK\n\n```orchestrator-manifest\n{"decision": "single", "rationale": "ok"}\n```\n'),
            ),
        )

        # Resume call used the stored backend AND the stored args.
        mocks[RUN_AGENT].assert_called_once()
        call = mocks[RUN_AGENT].call_args
        self.assertEqual(call.args[0], BACKEND_CODEX)
        self.assertEqual(call.kwargs["options"].resume_session_id, "dec-67021")
        self.assertEqual(call.kwargs["options"].extra_args, CODEX_ARGS)
        self.assertIn("please split", call.args[1])
        # Stored spec untouched.
        self.assertEqual(
            gh.pinned_data(RESUMED_DECOMPOSER_ISSUE).get(DECOMPOSER_AGENT),
            CODEX_SPEC,
        )

    def test_plain_decomposer_spec_round_trips(self) -> None:
        # `decomposer_agent="codex"` (no args) is a current pinned spec;
        # it round-trips cleanly to `("codex", "codex", ())`.
        spec, backend, args, sid = _decomposer_session._read_decomposer_session(
            PinnedState(
                state_data={DECOMPOSER_AGENT: BACKEND_CODEX, "decomposer_session_id": "sid-x"},
            )
        )
        self.assertEqual(spec, BACKEND_CODEX)
        self.assertEqual(backend, BACKEND_CODEX)
        self.assertEqual(args, ())
        self.assertEqual(sid, "sid-x")


def _unanswered(world: _corrected.CorrectionTickCase) -> None:
    raise RuntimeError("502")


class CorrectionSpecTest(unittest.TestCase, _FullSpecFixtureMixin, _corrected.CorrectionTickCase):
    """A correction resumes the session its rejected run saved under the command that run was pinned with."""

    def test_a_held_correction_keeps_its_command(self) -> None:
        # Refused its start by a GitHub read that did not answer, the
        # correction is launched on a later tick after DECOMPOSE_AGENT flipped
        # to claude, and still resumes the saved session on codex, with the
        # codex arguments, asked about the error its record keeps.
        self._held_under_codex()
        self._enter(self._patch_decompose_config(CLAUDE_SPEC, BACKEND_CLAUDE, CLAUDE_ARGS))
        later = self.decomposer(_corrected.SINGLE)

        self.tick(later)

        launched = later.launches[0]
        self.assertEqual(len(later.launches), 1)
        self.assertEqual(launched.command(), (BACKEND_CODEX, CODEX_ARGS))
        self.assertEqual(launched.resumed, _corrected.SESSION)
        self.assertIn(_corrected.UNLISTED_ERROR, launched.prompt)
        self.assertEqual(self.pinned()[DECOMPOSER_AGENT], CODEX_SPEC)

    def _held_under_codex(self) -> None:
        """A rejected run pinned under the codex spec, whose correction's start a read nobody answered refused."""
        self.opened()
        self._enter(self._patch_decompose_config(CODEX_SPEC, BACKEND_CODEX, CODEX_ARGS))
        rejected = self.decomposer(_corrected.UNLISTED)
        with _corrected.OnFetch.patch(self, _corrected.BEHIND_THE_CHARGE, _unanswered):
            self.tick(rejected)
        self.assertEqual(len(rejected.launches), 1)
        self.assertEqual(self.stage(), _corrected.PENDING)
