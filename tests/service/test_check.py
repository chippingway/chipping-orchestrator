# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""`check` on a host the service can run on, asking GitHub or not."""
from __future__ import annotations

import shlex
from pathlib import Path

from tests.service import check_test_support as _support

_REPO_ROOT = Path(__file__).resolve().parents[2]
_OPERATIONS_GUIDE = _REPO_ROOT / "docs" / "configuration" / "operations.md"
_SECTION = "### Check compatibility and start\n"
_COMMAND = ("chipping-orchestrator", "check")


def _documented_check() -> list[str]:
    """The `check` arguments the guide has operators run before a start."""
    section = _OPERATIONS_GUIDE.read_text(encoding=_support.ENCODING).split(_SECTION, 1)[1]
    fenced = section.split("```sh\n", 1)[1]
    block = fenced.split("```", 1)[0]
    for line in block.splitlines():
        words = shlex.split(line)
        if tuple(words[:2]) == _COMMAND:
            return words[2:]
    raise AssertionError(f"no {shlex.join(_COMMAND)} in the guide's compatibility check")


class ReadyServiceTest(_support.CheckCase):
    """Every setting, token, and agent the service needs is where it reads it."""

    def test_full_check_asks_once_per_repository(self) -> None:
        self.github.answer_reachable()

        checked = self.run_check()

        self.assertEqual((checked.returncode, checked.stderr), (0, ""))
        self.assertIn("every repository's token reaches it", checked.stdout)
        self.assertEqual(self.github.requests(), [
            (_support.repository_url(_support.API), _support.API_STAND_IN),
            (_support.repository_url(_support.WEB), _support.WEB_STAND_IN),
        ])

    def test_local_check_asks_github_nothing(self) -> None:
        checked = self.run_check(_support.LOCAL)

        self.assertEqual((checked.returncode, checked.stderr), (0, ""))
        self.assertIn("GitHub was not asked", checked.stdout)
        self.assertEqual(self.github.requests(), [])


class DocumentedCheckTest(_support.CheckCase):
    """The guide's check is this command, and answers as the service would start."""

    def test_documented_check_answers_for_the_service(self) -> None:
        documented = _documented_check()
        self.github.answer_reachable()
        self.assertEqual(self.run_check(*documented).returncode, 0)

        self.settings["ALLOWED_ISSUE_AUTHORS"] = ""

        self.assert_refused(self.run_check(*documented), _support.ALLOWLIST_REFUSAL)
