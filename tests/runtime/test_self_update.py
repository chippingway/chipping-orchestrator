# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The restart probe: which upstream move counts as self-modifying."""

from __future__ import annotations

import subprocess
import unittest
from unittest.mock import patch

from orchestrator import config
from orchestrator.runtime import self_update

_GIT_ATTR = "git"
_BASE_BRANCH_ATTR = "ORCHESTRATOR_BASE_BRANCH"
_BASE_BRANCH = "main"
_BASE_REF = f"origin/{_BASE_BRANCH}"
_START_SHA = "1a2b3c4"
_MOVED_SHA = "5d6e7f8"
_HEAD_COMMAND = "rev-parse HEAD"
_FETCH_COMMAND = f"fetch --quiet origin {_BASE_BRANCH}"
_BASE_COMMAND = f"rev-parse {_BASE_REF}"
_DIFF_COMMAND = f"diff --name-only {_START_SHA} {_MOVED_SHA}"
_ANCESTOR_COMMAND = f"merge-base --is-ancestor {_START_SHA} {_MOVED_SHA}"
_RUNTIME_CHANGE = "orchestrator/runtime/loop.py\nREADME.md\n"
_UNRELATED_CHANGE = "docs/architecture.md\nplans/roadmap.md\n"
_UNRESOLVED_REVISION = 128
_NOT_AN_ANCESTOR = 1


def _completed(stdout: str = "", returncode: int = 0):
    return subprocess.CompletedProcess(
        args=(_GIT_ATTR,),
        returncode=returncode,
        stdout=stdout,
        stderr="",
    )


class FakeGit:
    """Answer each probe by the command it runs, and record the order."""

    def __init__(self, answers: dict) -> None:
        self._answers = answers
        self.commands: list[str] = []

    def __call__(self, *args: str):
        command = " ".join(args)
        self.commands.append(command)
        return self._answers.get(command, _completed())


def _moved_upstream(overrides: dict | None = None) -> FakeGit:
    """A checkout whose base branch fast-forwarded onto runtime sources."""
    answers = {
        _BASE_COMMAND: _completed(f"{_MOVED_SHA}\n"),
        _ANCESTOR_COMMAND: _completed(),
        _DIFF_COMMAND: _completed(_RUNTIME_CHANGE),
    }
    answers.update(overrides or {})
    return FakeGit(answers)


class GitProbeTest(unittest.TestCase):
    """Every probe runs against the orchestrator's own checkout."""

    def test_commands_run_in_the_checkout(self) -> None:
        with patch.object(
            subprocess,
            "run",
            return_value=_completed(),
        ) as ran:
            self_update.git("rev-parse", "HEAD")

            self.assertEqual(
                ran.call_args.args[0],
                ["git", "rev-parse", "HEAD"],
            )
            self.assertEqual(
                ran.call_args.kwargs["cwd"],
                str(config.REPO_ROOT),
            )

    def test_head_sha_none_when_it_does_not_resolve(self) -> None:
        for answer, expected in (
            (_completed(f"{_START_SHA}\n"), _START_SHA),
            (_completed(returncode=_UNRESOLVED_REVISION), None),
        ):
            with self.subTest(returncode=answer.returncode), patch.object(
                self_update,
                _GIT_ATTR,
                FakeGit({_HEAD_COMMAND: answer}),
            ):
                self.assertEqual(self_update.own_head_sha(), expected)


class SelfModifyingMergeTest(unittest.TestCase):
    """Only a fast-forward of the orchestrator's own base branch that touched
    `orchestrator/` is worth a restart: anything else would trade a live
    process for nothing.
    """

    def setUp(self) -> None:
        branch_patch = patch.object(config, _BASE_BRANCH_ATTR, _BASE_BRANCH)
        branch_patch.start()
        self.addCleanup(branch_patch.stop)

    def test_forward_runtime_move_asks_for_restart(self) -> None:
        fake_git = _moved_upstream()
        with patch.object(self_update, _GIT_ATTR, fake_git):
            self.assertTrue(
                self_update.self_modifying_merge_happened(_START_SHA),
            )

        # The fetch is what makes the comparison current, so it has to run
        # before the base ref is read.
        self.assertEqual(
            fake_git.commands[:2],
            [_FETCH_COMMAND, _BASE_COMMAND],
        )

    def test_other_moves_keep_the_process_polling(self) -> None:
        for reason, overrides in (
            ("unmoved", {_BASE_COMMAND: _completed(f"{_START_SHA}\n")}),
            ("unresolvable base", {_BASE_COMMAND: _completed()}),
            (
                "not a fast-forward",
                {_ANCESTOR_COMMAND: _completed(returncode=_NOT_AN_ANCESTOR)},
            ),
            (
                "nothing under orchestrator/",
                {_DIFF_COMMAND: _completed(_UNRELATED_CHANGE)},
            ),
        ):
            with self.subTest(reason=reason), patch.object(
                self_update,
                _GIT_ATTR,
                _moved_upstream(overrides),
            ):
                self.assertFalse(
                    self_update.self_modifying_merge_happened(_START_SHA),
                )


if __name__ == "__main__":
    unittest.main()
