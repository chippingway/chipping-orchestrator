# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Call shapes and introspection the package `submit` surface accepts."""

from __future__ import annotations

import inspect
import unittest
from unittest.mock import MagicMock

from orchestrator.scheduler.models import SubmissionRequest
from orchestrator.scheduler.service import IssueScheduler

_REPO_SLUG = "owner/repo"
_ISSUE_NUMBER = 7
_EXPECTED_SUBMIT_SIGNATURE = (
    "(repo_slug, issue_number, fn, *, family=False, cap_exempt=False, "
    "per_repo_cap=None)"
)


class SchedulerSubmissionCompatibilityTest(unittest.TestCase):
    def setUp(self) -> None:
        self.scheduler = IssueScheduler(global_cap=1, per_repo_cap=1)

    def tearDown(self) -> None:
        self.scheduler.shutdown(wait=True)

    def test_typed_submission_request_dispatches(self) -> None:
        worker = MagicMock()
        request = SubmissionRequest(_REPO_SLUG, _ISSUE_NUMBER, worker)

        self.assertTrue(self.scheduler.submit(request))
        self.scheduler.shutdown(wait=True)
        worker.assert_called_once_with()

    def test_all_keyword_legacy_call_dispatches(self) -> None:
        worker = MagicMock()

        accepted = self.scheduler.submit(
            repo_slug=_REPO_SLUG,
            issue_number=_ISSUE_NUMBER,
            fn=worker,
        )

        self.assertTrue(accepted)
        self.scheduler.shutdown(wait=True)
        worker.assert_called_once_with()

    def test_legacy_signature_remains_introspectable(self) -> None:
        self.assertEqual(
            str(inspect.signature(self.scheduler.submit)),
            _EXPECTED_SUBMIT_SIGNATURE,
        )

    def test_typed_request_rejects_additional_fields(self) -> None:
        request = SubmissionRequest(_REPO_SLUG, _ISSUE_NUMBER, MagicMock())
        with self.assertRaises(TypeError):
            self.scheduler.submit(request, family=True)
        with self.assertRaises(TypeError):
            self.scheduler.submit(request, "unexpected", MagicMock())


if __name__ == "__main__":
    unittest.main()
