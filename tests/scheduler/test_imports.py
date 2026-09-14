# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Clean-process import checks and owner identity for the scheduler package."""

from __future__ import annotations

import subprocess
import sys
import unittest

from orchestrator.scheduler import (
    models as _models,
    service as _service,
)

_MODULES = (
    "orchestrator.scheduler",
    "orchestrator.scheduler.models",
    "orchestrator.scheduler.service",
)


class CleanProcessImportTest(unittest.TestCase):
    """Each owner imports cleanly before any siblings are cached."""

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
    """Scheduler requests and service are reached on their defining owners."""

    def test_names_belong_to_their_defining_modules(self) -> None:
        for owner, name in (
            (_service, "IssueScheduler"), (_models, "SubmissionRequest"),
        ):
            with self.subTest(name=name):
                self.assertEqual(getattr(owner, name).__module__, owner.__name__)


if __name__ == "__main__":
    unittest.main()
