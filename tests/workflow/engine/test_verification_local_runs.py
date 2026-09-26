# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Which local verify runs are evidence, and exactly what they are evidence of.

A run that passed whole and a run whose last command failed on the tested tree
are evidence, carrying exactly the commands that ran with the status each
earned -- the failure stays actionable rather than vanishing. An empty
configuration, a timeout, a dirty or moved tree, a run that never read what it
tested, and a transcript the artifact format would refuse are not evidence of
anything and bind nothing.
"""
from __future__ import annotations

import dataclasses
import unittest

from orchestrator.git.verification import models as _verify_models
from orchestrator.github.verification_evidence import EvidenceSource
from orchestrator.workflow.engine import verification_local_runs as _local_runs
from tests.workflow.engine import verification_evidence_test_support as support

_LINT = "uv run ruff check orchestrator tests"

_TIMEOUT = 600

_CONFIGURED = (support.SUITE, _LINT)

_FAILED_EXIT = 1

_FAILED = _verify_models.VERIFY_STATUS_FAILED

_TIMED_OUT = _verify_models.VERIFY_STATUS_TIMEOUT

_MOVED = _verify_models.VERIFY_STATUS_HEAD_CHANGED


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
        "timeout": _TIMEOUT,
        "context_revision": _verify_models._context_revision(_CONFIGURED, _TIMEOUT),
    }
    return _verify_models.VerifyResult(**(recorded | fields))


_FAILED_LINT = _outcome(_LINT, status=_FAILED, exit_code=_FAILED_EXIT)


def _transcript(run: _verify_models.VerifyResult, statuses: tuple) -> list[tuple]:
    """What `run` attempted, each command with the exit status it is expected to publish."""
    return [
        (outcome.command, status, outcome.output)
        for outcome, status in zip(run.attempted_commands, statuses, strict=True)
    ]


class LocalRunEvidenceTest(unittest.TestCase, support.VerificationEvidenceCase):
    """A run binds only on its own transcript, and binds exactly what ran."""

    def setUp(self) -> None:
        support.VerificationEvidenceCase.setUp(self)
        self.target = self.binding().target

    def test_passing_and_failing_runs_are_evidence(self) -> None:
        runs = (
            (_run(_outcome(support.SUITE), _outcome(_LINT)), (0, 0)),
            (_run(_outcome(support.SUITE), _FAILED_LINT, status=_FAILED), (0, _FAILED_EXIT)),
        )
        for run, statuses in runs:
            with self.subTest(status=run.status):
                binding, commands = _local_runs.local_run_evidence(run, self.target)

                self.assertEqual(
                    (binding.tested_sha, binding.tested_tree, binding.context_revision),
                    (support.TESTED_SHA, support.TESTED_TREE, run.context_revision),
                )
                self.assertIs(binding.source, EvidenceSource.ORCHESTRATOR_EXECUTED)
                self.assertEqual(
                    [(ran.command, ran.exit_status, ran.output) for ran in commands],
                    _transcript(run, statuses),
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
            "failure that moved the head": _run(
                dataclasses.replace(_FAILED_LINT, head_after=support.REBASED_SHA),
                status=_FAILED,
            ),
            "never read what it tested": _run(status=_FAILED, commit=None, tree_identity=None),
            "unpublishable transcript": _run(fenced, _outcome(_LINT)),
        }
        for case, run in runs.items():
            with self.subTest(case=case):
                self.assertIsNone(_local_runs.local_run_evidence(run, self.target))


if __name__ == "__main__":
    unittest.main()
