# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""A body built from the description a caller read is written only over it."""
from __future__ import annotations

import unittest
from unittest.mock import MagicMock

from orchestrator.github.client import GitHubClient

_PR_NUMBER = 7

_AS_READ = "the description as the caller read it"

_NAMED = "the body the caller built from it"

# What stands now, what the caller read, and whether the edit may be written.
# An empty description is one description, read as None or as "".
_STANDINGS = (
    (_AS_READ, _AS_READ, True),
    ("saved by somebody since", _AS_READ, False),
    (None, "", True),
    ("", None, True),
)


class GuardedBodyEditTest(unittest.TestCase):
    def setUp(self) -> None:
        # Bypass the networked __init__; the method reads only `self.repo`.
        self.gh = GitHubClient.__new__(GitHubClient)
        self.gh.repo = MagicMock()

    def test_the_body_is_compared_as_it_stands(self) -> None:
        # Read again immediately ahead of the edit, by number: a description
        # that moved since the caller's reading is left exactly as it is.
        standing = self.gh.repo.get_pull.return_value
        for stands, expected, written in _STANDINGS:
            with self.subTest(stands=stands, expected=expected):
                standing.reset_mock()
                standing.body = stands

                self.assertIs(
                    self.gh.edit_unchanged_pr_body(_PR_NUMBER, expected, _NAMED),
                    written,
                )

                self.gh.repo.get_pull.assert_called_with(_PR_NUMBER)
                self.assertEqual(standing.edit.call_count, int(written))
                if written:
                    standing.edit.assert_called_once_with(body=_NAMED)


if __name__ == "__main__":
    unittest.main()
