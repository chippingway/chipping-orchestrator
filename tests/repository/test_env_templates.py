# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The two configuration templates a setup is copied from.

`.env.example` is the basic template: a reader copies it and edits its live
`REPOS` value, guided by the commented example beside it, into a setup for one
repository or several. Each of those values has to parse the way the
configuration parses `REPOS`, or the template teaches a setting that aborts the
first start. The developer fallback settings belong to `.env.example.advanced`
alone: one of them in the basic template would put a control no user setup
needs back on the first-run path, and `REPOS` in the advanced template would
give the one setting the basic template owns a second home.

Both are read through the owner that ships them as package data, so these
checks parse the very text an installed version carries. The poller itself
never reads either file, so a drifted example would otherwise surface only
when a new user's first start refused it. The package holds the one copy: a
second at the repository root would be free to drift from what installs
receive while the documentation and these checks read the first.
"""
from __future__ import annotations

import re
import unittest
from pathlib import Path
from typing import NoReturn

from orchestrator.config.repositories import parse_repos_env
from orchestrator.service.templates import (
    ADVANCED_TEMPLATE,
    BASIC_TEMPLATE,
    TEMPLATES,
    template_text,
)

_REPO_ROOT = Path(__file__).resolve().parents[2]
_REPOS = "REPOS"
_DEVELOPER_SETTINGS = frozenset(("REPO", "TARGET_REPO_ROOT", "BASE_BRANCH", "REMOTE_NAME"))
# One assignment as the templates spell it: live, or commented out as an
# example, which leaves the `#` in `comment`.
_ASSIGNMENT = re.compile(r"^(?P<comment>#?)\s*(?P<key>[A-Z_]+)=(?P<value>.*)$", re.MULTILINE)


def _assignments(template: str) -> list[re.Match[str]]:
    """Every assignment the template writes, in file order."""
    return list(_ASSIGNMENT.finditer(template_text(template)))


def _keys(template: str) -> set[str]:
    return {assignment["key"] for assignment in _assignments(template)}


def _refuse(message: str) -> NoReturn:
    raise AssertionError(message)


def _entry_count(repos_value: str) -> int:
    """How many repositories a `REPOS` value names, failing where it aborts."""
    return len(parse_repos_env(repos_value, default_parallel_limit=1, config_error=_refuse))


class EnvTemplatesTest(unittest.TestCase):
    def test_basic_template_repos_values_parse(self) -> None:
        repos_lines = [
            assignment
            for assignment in _assignments(BASIC_TEMPLATE)
            if assignment["key"] == _REPOS
        ]
        live_values = [line["value"] for line in repos_lines if not line["comment"]]
        self.assertEqual(len(live_values), 1, "the copy has to start from one live REPOS line")
        self.assertGreater(len(repos_lines), 1, "the live value has to have an example beside it")
        for repos_line in repos_lines:
            with self.subTest(repos=repos_line["value"]):
                _entry_count(repos_line["value"])
        self.assertEqual(
            _entry_count(live_values[0]),
            1,
            "the live REPOS value is the single-repository example a reader edits",
        )

    def test_developer_settings_stay_advanced(self) -> None:
        basic_keys = _keys(BASIC_TEMPLATE)
        advanced_keys = _keys(ADVANCED_TEMPLATE)
        self.assertIn(_REPOS, basic_keys)
        self.assertFalse(basic_keys & _DEVELOPER_SETTINGS, "developer settings in the basic template")
        self.assertLessEqual(_DEVELOPER_SETTINGS, advanced_keys)
        self.assertNotIn(_REPOS, advanced_keys)

    def test_the_package_holds_the_only_copy(self) -> None:
        for name in TEMPLATES:
            with self.subTest(template=name):
                self.assertFalse((_REPO_ROOT / name).exists(), f"{name} is copied at the repository root")
