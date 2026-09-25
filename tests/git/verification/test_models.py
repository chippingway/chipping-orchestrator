# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Result fields, statuses, and evidence rules owned by the verification model module."""

from __future__ import annotations

import dataclasses
import re
import unittest

from orchestrator.git.verification import models

VERIFY_STATUSES = models.VERIFY_STATUSES

_COMMIT_SHA = "f00dcafe"
_TREE_SHA = "0f1e2d3c"
_COMMANDS = ("pytest", "ruff check .")
_TIMEOUT = 60

_PASSED = models.VerifyCommandOutcome(
    command=_COMMANDS[0],
    status=models.VERIFY_STATUS_OK,
    exit_code=0,
    head_before=_COMMIT_SHA,
    head_after=_COMMIT_SHA,
    tree_before=_TREE_SHA,
    tree_after=_TREE_SHA,
)

_REUSABLE = models.VerifyResult(
    status=models.VERIFY_STATUS_OK,
    commit=_COMMIT_SHA,
    tree_identity=_TREE_SHA,
    configured_commands=_COMMANDS,
    attempted_commands=(_PASSED, dataclasses.replace(_PASSED, command=_COMMANDS[1])),
    timeout=_TIMEOUT,
    context_revision=models._context_revision(_COMMANDS, _TIMEOUT),
)


def _with_second_outcome(**changes: object) -> models.VerifyResult:
    second = dataclasses.replace(_REUSABLE.attempted_commands[1], **changes)
    return dataclasses.replace(_REUSABLE, attempted_commands=(_PASSED, second))


class VerifyResultTest(unittest.TestCase):
    """Every status is constructible from `status` alone, and only a complete run is evidence."""

    def test_variant_fields_default_to_empty(self) -> None:
        for status in VERIFY_STATUSES:
            with self.subTest(status=status):
                run = models.VerifyResult(status=status)
                self.assertEqual(run.status, status)
                self.assertIsNone(run.commit)
                self.assertIsNone(run.tree_identity)
                self.assertEqual(run.configured_commands, ())
                self.assertEqual(run.attempted_commands, ())
                self.assertIsNone(run.timeout)
                self.assertIsNone(run.context_revision)
                self.assertEqual(run.output, "")
                self.assertFalse(run.is_reusable)

    def test_only_a_complete_ok_record_is_reusable(self) -> None:
        self.assertTrue(_REUSABLE.is_reusable)
        incomplete = {
            "not ok": dataclasses.replace(_REUSABLE, status=models.VERIFY_STATUS_FAILED),
            "no commit": dataclasses.replace(_REUSABLE, commit=None),
            "no tree": dataclasses.replace(_REUSABLE, tree_identity=None),
            "no configured commands": dataclasses.replace(
                _REUSABLE, configured_commands=(), attempted_commands=(),
            ),
            "no timeout": dataclasses.replace(_REUSABLE, timeout=None),
            "zero timeout": dataclasses.replace(_REUSABLE, timeout=0),
            "no context revision": dataclasses.replace(_REUSABLE, context_revision=None),
            "context revision of another configuration": dataclasses.replace(
                _REUSABLE, context_revision=models._context_revision(_COMMANDS, _TIMEOUT + 1),
            ),
            "no transcript": dataclasses.replace(_REUSABLE, attempted_commands=()),
            "a skipped command": dataclasses.replace(_REUSABLE, attempted_commands=(_PASSED,)),
            "commands out of order": dataclasses.replace(
                _REUSABLE, attempted_commands=tuple(reversed(_REUSABLE.attempted_commands)),
            ),
            "another command": _with_second_outcome(command="true"),
            "a refused outcome": _with_second_outcome(status=models.VERIFY_STATUS_FAILED),
            "a non-zero exit": _with_second_outcome(exit_code=1),
            "an unrecorded exit": _with_second_outcome(exit_code=None),
            "dirty files": _with_second_outcome(dirty_files=("dirty.txt",)),
            "a moved HEAD": _with_second_outcome(head_after="other_sha"),
            "an unread HEAD": _with_second_outcome(head_after=""),
            "another tree": _with_second_outcome(tree_after="other_tree"),
            "an unread tree": _with_second_outcome(tree_after=None),
            "another baseline": _with_second_outcome(head_before="other_sha"),
        }
        for case, run in incomplete.items():
            with self.subTest(case=case):
                self.assertFalse(run.is_reusable)

    def test_context_revision_digests_configuration(self) -> None:
        revision = models._context_revision(_COMMANDS, _TIMEOUT)
        # A token the verification artifact header carries verbatim.
        self.assertRegex(revision, re.compile("^[0-9a-f]{64}$"))
        self.assertEqual(revision, models._context_revision(tuple(_COMMANDS), _TIMEOUT))
        others = {
            "reordered": models._context_revision(tuple(reversed(_COMMANDS)), _TIMEOUT),
            "one command fewer": models._context_revision(_COMMANDS[:1], _TIMEOUT),
            "commands joined": models._context_revision(("; ".join(_COMMANDS),), _TIMEOUT),
            "another timeout": models._context_revision(_COMMANDS, _TIMEOUT + 1),
            "no commands": models._context_revision((), _TIMEOUT),
        }
        for case, other in others.items():
            with self.subTest(case=case):
                self.assertNotEqual(other, revision)


class VerifyCommandOutcomeTest(unittest.TestCase):
    """Command outcome records preserve command, status, exit code, output, and readings."""

    def test_default_fields(self) -> None:
        outcome = models.VerifyCommandOutcome(command="true", status="ok")
        self.assertEqual(outcome.command, "true")
        self.assertEqual(outcome.status, "ok")
        self.assertIsNone(outcome.exit_code)
        self.assertEqual(outcome.output, "")
        self.assertEqual(outcome.dirty_files, ())
        for reading in ("head_before", "head_after", "tree_before", "tree_after"):
            with self.subTest(reading=reading):
                self.assertIsNone(getattr(outcome, reading))


if __name__ == "__main__":
    unittest.main()
