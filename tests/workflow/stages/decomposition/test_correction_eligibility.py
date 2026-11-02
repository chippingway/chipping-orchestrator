# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Which rejected initial decomposer answer earns a manifest correction, and the launch it buys.

Only a completed, accounted run whose manifest the parser refuses with a
concrete error earns one, tied to that run's invocation, the requirements its
record carries, the pinned command and the session it returned and saved, and
the parser's own error. Every other answer -- a question, silence, a usable manifest, a run
that failed, stopped, or went unaccounted, and a correction's own answer --
earns none, and so does a conversation the pinned command cannot resume. The
launch resumes that session under the pinned command whatever the
configuration says now, asking for the whole manifest again beside the exact
error, and names no retry count, so it is the same launch in every window.
"""
from __future__ import annotations

import unittest
from pathlib import Path
from unittest.mock import patch

from orchestrator import config
from orchestrator.agents.models import TerminalFailure
from orchestrator.observability.usage.agy_events import ToolLifecycle
from orchestrator.workflow.engine import decomposition_prompts as _prompts
from orchestrator.workflow.stages.decomposition import correction_source as _source
from tests.workflow.fixtures import _TEST_SPEC, _manifest
from tests.workflow.git_owners import seam_patch
from tests.workflow.stages.decomposition import (
    correction_launch_support as launch_support,
    correction_test_support as support,
)

# Answers and returns that earn nothing, each beside the result fields it comes back with.
_UNEARNED = (
    ("a question", {"last_message": "Should the parser ship apart?"}),
    ("silence", {"last_message": ""}),
    ("a usable manifest", {"last_message": _manifest('{"decision": "single", "rationale": "fits"}')}),
    ("no process", {"invoked": False}),
    ("an interruption", {"interrupted": True}),
    ("a timeout", {"timed_out": True}),
    ("a failed exit", {"exit_code": 1}),
    ("a terminal failure", {"terminal_failure": TerminalFailure(process_exit_code=0)}),
    ("an unfinished step", {"unfinished_steps": (ToolLifecycle(step_index=0),)}),
    ("unaccounted usage", {"unaccounted": True}),
    ("no invocation", {"invocation": None}),
    ("no returned session beside an older pin", {"session_id": None}),
    ("a returned session other than the pin", {"session_id": "decomposer-session-2"}),
)

# Saved conversations no pinned command resumes: a pin missing, commands that do
# not parse, and sessions no resume may name.
_UNRESUMABLE = (
    ("no session", {support.SESSION_PIN: None}),
    ("an option-shaped session", {support.SESSION_PIN: "--last"}),
    ("a session with a space", {support.SESSION_PIN: "decomposer session"}),
    ("no command", {support.COMMAND_PIN: None}),
    ("an unknown backend", {support.COMMAND_PIN: "bash -lc decompose"}),
    ("an unbalanced quote", {support.COMMAND_PIN: "codex -c 'model"}),
    ("an empty command", {support.COMMAND_PIN: " "}),
)

# The backend and arguments the seeded command parses to.
_PINNED = ("codex", ("--model", "gpt-5.5", "-c", "model_reasoning_effort=high"))

# The role and stage the launch is charged under, and the checkout it runs in.
_LAUNCHED = ("decomposer", "decomposing", launch_support.CHECKOUT)

# A checkout gone from the host, recreated for the launch.
_GONE = Path("/nonexistent/decompose-checkout")


class EarnedTest(unittest.TestCase):
    """A completed run's refused manifest is the one answer that earns a correction."""

    def test_a_refused_manifest_earns_its_source(self) -> None:
        world = support.seeded()

        earned = _source.earned(world.issue, world.state, launch_support.rejected(world))

        self.assertEqual(earned, support.source(world))
        self.assertEqual(earned.diagnostic, support.DIAGNOSTIC, "the parser's own error, verbatim")

    def test_other_answers_earn_nothing(self) -> None:
        for name, fields in _UNEARNED:
            with self.subTest(name):
                world = support.seeded()

                answered = launch_support.rejected(world, **fields)

                self.assertIsNone(_source.earned(world.issue, world.state, answered))

    def test_a_corrections_own_answer_earns_nothing(self) -> None:
        world = support.seeded()
        corrected = launch_support.rejected(world)
        corrected.correction = support.attempt(world)

        self.assertIsNone(_source.earned(world.issue, world.state, corrected))

    def test_an_unresumable_session_earns_nothing(self) -> None:
        # Each run returns the very session its pin records, so the pin's own
        # shape -- and the command beside it -- is what refuses it.
        for name, pins in _UNRESUMABLE:
            with self.subTest(name):
                world = support.seeded(**pins)
                answered = launch_support.rejected(world, session_id=world.state.get(support.SESSION_PIN))

                self.assertIsNone(_source.earned(world.issue, world.state, answered))


class ResumedTest(unittest.TestCase):
    """The launch is the saved session under the pinned command, asked for the whole manifest beside its error."""

    def test_the_pinned_command_resumes_the_session(self) -> None:
        world = support.seeded()
        self.enterContext(patch.object(config, "DECOMPOSE_AGENT_SPEC", "claude --model opus"))
        self.enterContext(seam_patch("_decompose_worktree_path", lambda spec, number: launch_support.CHECKOUT))

        request = _source.resumed(_TEST_SPEC, world.issue, support.source(world))
        world.state.set(launch_support.RETRIES, launch_support.DAILY)
        again = _source.resumed(_TEST_SPEC, world.issue, support.source(world))

        named = (request.backend, request.extra_args, request.agent_spec, request.resume_session_id)
        self.assertEqual(named, (*_PINNED, support.COMMAND, support.SESSION))
        self.assertEqual((request.agent_role, request.stage, request.cwd), _LAUNCHED)
        self.assertEqual(request.prompt, _prompts._build_correction_prompt(support.DIAGNOSTIC))
        self.assertIsNone(request.retry_count)
        self.assertEqual(again.fingerprint, request.fingerprint, "the same launch whatever the retry count reads")

    def test_a_missing_checkout_is_recreated(self) -> None:
        world = support.seeded()
        self.enterContext(seam_patch("_decompose_worktree_path", lambda spec, number: _GONE))
        self.enterContext(seam_patch("_ensure_decompose_worktree", lambda spec, number: launch_support.CHECKOUT))

        request = _source.resumed(_TEST_SPEC, world.issue, support.source(world))

        self.assertEqual(request.cwd, launch_support.CHECKOUT)


if __name__ == "__main__":
    unittest.main()
