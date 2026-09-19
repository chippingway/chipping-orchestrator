# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Result fields and statuses owned by the verification model module."""

from __future__ import annotations

import unittest

from orchestrator.git.verification import models

VERIFY_STATUSES = models.VERIFY_STATUSES


_COMMIT_SHA = "f00dcafe"
_TREE_SHA = "0f1e2d3c"
_COMMAND = "pytest"


class VerifyResultTest(unittest.TestCase):
    """Every status is constructible from `status` alone."""

    def test_variant_fields_default_to_empty(self) -> None:
        for status in VERIFY_STATUSES:
            with self.subTest(status=status):
                self._assert_default_fields(models.VerifyResult(status=status), status)

    def test_is_reusable_requires_ok_and_identities(self) -> None:
        reusable = models.VerifyResult(
            status=models.VERIFY_STATUS_OK,
            commit=_COMMIT_SHA,
            tree_identity=_TREE_SHA,
            configured_commands=(_COMMAND,),
        )
        self.assertTrue(reusable.is_reusable)

        not_reusable_cases = (
            models.VerifyResult(status=models.VERIFY_STATUS_NOT_RUN),
            models.VerifyResult(
                status=models.VERIFY_STATUS_OK,
                commit=_COMMIT_SHA,
                tree_identity=_TREE_SHA,
                configured_commands=(),
            ),
            models.VerifyResult(
                status=models.VERIFY_STATUS_OK,
                commit=None,
                tree_identity=_TREE_SHA,
                configured_commands=(_COMMAND,),
            ),
            models.VerifyResult(
                status=models.VERIFY_STATUS_OK,
                commit=_COMMIT_SHA,
                tree_identity=None,
                configured_commands=(_COMMAND,),
            ),
            models.VerifyResult(
                status=models.VERIFY_STATUS_FAILED,
                commit=_COMMIT_SHA,
                tree_identity=_TREE_SHA,
                configured_commands=(_COMMAND,),
            ),
        )
        for non_reusable in not_reusable_cases:
            with self.subTest(result=non_reusable):
                self.assertFalse(non_reusable.is_reusable)

    def _assert_default_fields(self, run: models.VerifyResult, status: str) -> None:
        self.assertEqual(run.status, status)
        self.assertIsNone(run.commit)
        self.assertIsNone(run.tree_identity)
        self.assertEqual(run.configured_commands, ())
        self.assertEqual(run.attempted_commands, ())
        self.assertIsNone(run.timeout)
        self.assertEqual(run.output, "")
        self.assertFalse(run.is_reusable)


class VerifyCommandOutcomeTest(unittest.TestCase):
    """Command outcome records preserve command, status, exit code, and output."""

    def test_default_fields(self) -> None:
        outcome = models.VerifyCommandOutcome(command="true", status="ok")
        self.assertEqual(outcome.command, "true")
        self.assertEqual(outcome.status, "ok")
        self.assertIsNone(outcome.exit_code)
        self.assertEqual(outcome.output, "")
        self.assertEqual(outcome.dirty_files, ())
        self.assertIsNone(outcome.head_before)
        self.assertIsNone(outcome.head_after)


if __name__ == "__main__":
    unittest.main()
