# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Clean-process import checks and owner identity for the scheduler package."""

from __future__ import annotations

import subprocess
import sys
import unittest

from orchestrator import scheduler as _scheduler
from orchestrator.scheduler import models as _models, service as _service

_MODULES = (
    "orchestrator.scheduler",
    "orchestrator.scheduler.models",
    "orchestrator.scheduler.service",
)

# Owner-only names the facade must not resolve: the normalized submission and
# its binding belong to `models`, the composition layers and the exempt pool
# size to `service`. Code that needs one imports its owner directly.
_OWNER_ONLY_NAMES = (
    "Submission",
    "bind_submission_request",
    "normalize_submission",
    "_SchedulerViewMixin",
    "_SchedulerReservationMixin",
    "_SchedulerExecutionMixin",
    "_EXEMPT_POOL_WORKERS",
)


class CleanProcessImportTest(unittest.TestCase):
    """Each scheduler module imports standalone in a fresh interpreter.

    The initializer reads `IssueScheduler` off `service`, which imports the
    sibling `models` owner back through the package, so importing either owner
    directly must run the initializer without a partially-initialized-module
    error. A subprocess per module gives each a clean `sys.modules` no other test
    has already populated, exposing an import-order cycle a package-first suite
    run would mask.
    """

    def test_each_module_imports_standalone(self) -> None:
        for module in _MODULES:
            with self.subTest(module=module):
                completed = subprocess.run(
                    [sys.executable, "-c", f"import {module}"],
                    capture_output=True,
                    text=True,
                    check=False,
                )
                self.assertEqual(completed.returncode, 0, msg=completed.stderr)


class PublicSurfaceTest(unittest.TestCase):
    """The facade publishes a narrow `__all__` backed by owner identities."""

    def test_all_names_the_narrow_public_surface(self) -> None:
        self.assertEqual(
            _scheduler.__all__,
            (
                "IssueScheduler",
                "SubmissionRequest",
            ),
        )

    def test_public_names_are_owner_re_exports(self) -> None:
        # Each public name resolves to the owning module's object rather than a
        # rebuilt copy, so a caller reaching through the facade sees the owner's
        # definition.
        self.assertIs(_scheduler.IssueScheduler, _service.IssueScheduler)
        self.assertIs(_scheduler.SubmissionRequest, _models.SubmissionRequest)

    def test_facade_hides_owner_only_names(self) -> None:
        for owner_only_name in _OWNER_ONLY_NAMES:
            with self.subTest(name=owner_only_name), self.assertRaises(AttributeError):
                getattr(_scheduler, owner_only_name)


if __name__ == "__main__":
    unittest.main()
