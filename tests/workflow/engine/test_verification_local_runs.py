# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Which local verify runs are evidence, and exactly what they are evidence of.

Only a run that passed whole, with a clean tree proved after every command, is
evidence, carrying exactly the commands that ran -- and it is evidence the
records accept. A failed run binds nothing, however genuine: the runner reads
no worktree status after a nonzero exit, so a command that rewrote tracked
files before failing -- which is what an outcome naming dirty files records --
could otherwise be bound to the committed tree. An empty configuration, a
timeout, a dirty or moved tree, a run that never read what it tested, and a
transcript the artifact format would refuse bind nothing either.
"""
from __future__ import annotations

import dataclasses
import unittest

from orchestrator.git.verification import models as _verify_models
from orchestrator.github.pinned_state import MAX_PINNED_BODY, PinnedState
from orchestrator.github.verification_evidence import EvidenceSource
from orchestrator.workflow.engine import (
    verification_local_runs as _local_runs,
    verification_record_state as _record_state,
)
from tests.workflow.engine import verification_record_test_support as support

_LINT = "uv run ruff check orchestrator tests"

_CONFIGURED = (support.SUITE, _LINT)

_FAILED_EXIT = 1

_FAILED = _verify_models.VERIFY_STATUS_FAILED

_TIMED_OUT = _verify_models.VERIFY_STATUS_TIMEOUT

_MOVED = _verify_models.VERIFY_STATUS_HEAD_CHANGED

_DIRTY = _verify_models.VERIFY_STATUS_DIRTY

_REWRITTEN = ("orchestrator/cli.py",)

# Commands enough that each at the whole output budget is past one comment.
_MANY = 17

_MANY_CONFIGURED = tuple(f"check {index}" for index in range(_MANY))


def _outcome(command: str, **fields) -> _verify_models.VerifyCommandOutcome:
    """One command that exited 0 on the tested commit and tree, any field replaced."""
    ran = {
        "command": command,
        "status": _verify_models.VERIFY_STATUS_OK,
        "exit_code": 0,
        "output": f"{command}: ok",
        "head_before": support.TESTED_SHA,
        "head_after": support.TESTED_SHA,
        "tree_before": support.TESTED_TREE,
        "tree_after": support.TESTED_TREE,
    }
    return _verify_models.VerifyCommandOutcome(**(ran | fields))


def _run(*attempted: _verify_models.VerifyCommandOutcome, **fields) -> _verify_models.VerifyResult:
    """A run of `_CONFIGURED` on the tested commit and tree, any field replaced."""
    recorded = {
        "status": _verify_models.VERIFY_STATUS_OK,
        "commit": support.TESTED_SHA,
        "tree_identity": support.TESTED_TREE,
        "configured_commands": _CONFIGURED,
        "attempted_commands": attempted,
        "timeout": support.TIMEOUT,
        "context_revision": _verify_models._context_revision(_CONFIGURED, support.TIMEOUT),
    }
    return _verify_models.VerifyResult(**(recorded | fields))


_FAILED_LINT = _outcome(_LINT, status=_FAILED, exit_code=_FAILED_EXIT)


def _suite_printing(output: str) -> _verify_models.VerifyResult:
    """A passing run of `_CONFIGURED` whose suite printed `output`."""
    return _run(_outcome(support.SUITE, output=output), _outcome(_LINT))


class LocalRunEvidenceTest(unittest.TestCase):
    """A run binds only on its own transcript, and binds exactly what ran."""

    def test_a_passing_run_is_recordable_evidence(self) -> None:
        run = _run(_outcome(support.SUITE), _outcome(_LINT))

        binding, commands = _local_runs.local_run_evidence(run, support.TARGET)

        self.assertEqual(
            (binding.target, binding.tested_sha, binding.tested_tree, binding.context_revision),
            (support.TARGET, support.TESTED_SHA, support.TESTED_TREE, run.context_revision),
        )
        self.assertIs(binding.source, EvidenceSource.ORCHESTRATOR_EXECUTED)
        self.assertEqual(
            [(ran.command, ran.exit_status, ran.output) for ran in commands],
            [(outcome.command, 0, outcome.output) for outcome in run.attempted_commands],
        )
        state = PinnedState(comment_id=1)
        pending = _record_state.mint_pending_evidence(
            state, support.ISSUE_NUMBER, binding, commands,
        )
        self.assertTrue(_record_state.record_pending_evidence(state, pending))
        self.assertTrue(_record_state.read_pending_evidence(state).passed)

    def test_a_run_on_another_head_binds_nothing(self) -> None:
        # Fresh evidence is about the head it answers for; carrying a run to
        # another head is a carry-forward decision, never a local run's.
        run = _run(_outcome(support.SUITE), _outcome(_LINT))
        moved = support.binding().retargeted(support.REBASED_SHA).target

        self.assertIsNotNone(_local_runs.local_run_evidence(run, support.TARGET))
        self.assertIsNone(_local_runs.local_run_evidence(run, moved))

    def test_an_uncarriable_transcript_binds_nothing(self) -> None:
        # Every command is one the format renders, each at the whole output
        # budget; together they are past what one comment holds.
        run = _run(
            *(
                _outcome(command, output="x" * _verify_models._VERIFY_OUTPUT_BUDGET)
                for command in _MANY_CONFIGURED
            ),
            configured_commands=_MANY_CONFIGURED,
            context_revision=_verify_models._context_revision(_MANY_CONFIGURED, support.TIMEOUT),
        )

        self.assertTrue(run.is_reusable)
        self.assertIsNone(_local_runs.local_run_evidence(run, support.TARGET))

    def test_whatever_binds_is_recordable(self) -> None:
        # At the very edge of what binds, the transaction minted from it is one
        # the recorder accepts, artifact and all; a character past it binds
        # nothing.
        longest = self._longest_bound_transcript()
        binding, commands = _local_runs.local_run_evidence(_suite_printing(longest), support.TARGET)
        state = PinnedState(comment_id=1)
        pending = _record_state.mint_pending_evidence(
            state, support.ISSUE_NUMBER, binding, commands,
        )

        self.assertTrue(_record_state.record_pending_evidence(state, pending))
        self.assertIsNone(
            _local_runs.local_run_evidence(_suite_printing(f"{longest}x"), support.TARGET),
        )

    def test_a_run_about_no_one_tree_binds_nothing(self) -> None:
        fenced = _outcome(support.SUITE, output="```\nclosed early")
        runs = {
            "empty configuration": _verify_models.VerifyResult(
                status=_verify_models.VERIFY_STATUS_NOT_RUN,
            ),
            "timeout": _run(
                _outcome(support.SUITE, status=_TIMED_OUT, exit_code=None), status=_TIMED_OUT,
            ),
            "moved head": _run(
                _outcome(support.SUITE, status=_MOVED, head_after=support.REBASED_SHA),
                status=_MOVED,
            ),
            "dirty tree": _run(
                _outcome(support.SUITE, status=_DIRTY, dirty_files=_REWRITTEN), status=_DIRTY,
            ),
            "failure on the tested tree": _run(
                _outcome(support.SUITE), _FAILED_LINT, status=_FAILED,
            ),
            "failure that rewrote tracked files": _run(
                _outcome(support.SUITE),
                dataclasses.replace(_FAILED_LINT, dirty_files=_REWRITTEN),
                status=_FAILED,
            ),
            "failure that moved the head": _run(
                dataclasses.replace(_FAILED_LINT, head_after=support.REBASED_SHA),
                status=_FAILED,
            ),
            "never read what it tested": _run(status=_FAILED, commit=None, tree_identity=None),
            "unpublishable transcript": _run(fenced, _outcome(_LINT)),
            "transcript UTF-8 cannot carry": _run(
                _outcome(support.SUITE, output="12 passed \ud800"), _outcome(_LINT),
            ),
        }
        for case, run in runs.items():
            with self.subTest(case=case):
                self.assertIsNone(_local_runs.local_run_evidence(run, support.TARGET))


    def _longest_bound_transcript(self) -> str:
        """The longest suite transcript a run still binds with, found by bisection."""
        bound, refused = 0, MAX_PINNED_BODY
        while refused - bound > 1:
            middle = (bound + refused) // 2
            if _local_runs.local_run_evidence(_suite_printing("x" * middle), support.TARGET) is None:
                refused = middle
            else:
                bound = middle
        return "x" * bound


if __name__ == "__main__":
    unittest.main()
