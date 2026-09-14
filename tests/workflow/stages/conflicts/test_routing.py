# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from orchestrator.workflow.engine import issue_processing as _issue_processing
from orchestrator.workflow.stages.conflicts import handler as _conflicts
from tests.support.fakes import FakeGitHubClient, make_issue
from tests.workflow.fixtures import _TEST_SPEC

CONFLICT_ISSUE = 42


class HandleResolvingConflictDispatchTest(unittest.TestCase):
    """The dispatcher must route `resolving_conflict` to the handler owner,
    which is where a patch has to land to intercept a dispatched tick."""

    def test_dispatcher_routes_conflict_handler(self) -> None:
        gh = FakeGitHubClient()
        issue = make_issue(CONFLICT_ISSUE, label="workflow:resolving_conflict")
        gh.add_issue(issue)

        conflict_handler = MagicMock()
        with patch.object(_conflicts, "_handle_resolving_conflict", conflict_handler):
            _issue_processing._process_issue(gh, _TEST_SPEC, issue)

        conflict_handler.assert_called_once_with(gh, _TEST_SPEC, issue)


if __name__ == "__main__":
    unittest.main()
