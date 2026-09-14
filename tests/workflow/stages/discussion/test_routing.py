# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""`discussion` label bootstrap + dispatcher routing. What a tick does with the
label is pinned in the sibling modules; this one covers only the label-spec /
family-aware / dispatcher wiring that keeps the dispatcher from falling through
to pickup or to its unrecognized-label warning."""

from __future__ import annotations

import unittest
from unittest.mock import patch

from orchestrator.github.labels import (
    WORKFLOW_LABEL_SPECS,
    WORKFLOW_LABELS,
)
from orchestrator.workflow.engine import (
    issue_processing as _issue_processing,
    pickup as _pickup,
    poll_models as _poll_models,
)
from orchestrator.workflow.stages.discussion import handler as _discussion
from tests.support.fakes import FakeGitHubClient, make_issue
from tests.workflow.fixtures import _TEST_SPEC, LABEL_DISCUSSION

DISCUSSION_ISSUE_NUMBER = 901


class DiscussionLabelRoutingTest(unittest.TestCase):
    """`discussion` is a first-class workflow label routed to its own stage
    handler owner, which is where a patch has to land to intercept a dispatched
    tick."""

    def test_label_is_recognized(self) -> None:
        self.assertIn(LABEL_DISCUSSION, WORKFLOW_LABELS)

    def test_discussion_label_is_in_bootstrap_specs(self) -> None:
        # Label bootstrap iterates WORKFLOW_LABEL_SPECS; without a spec entry
        # `ensure_workflow_labels` would never create the label on a fresh
        # repo and an operator would have nothing to apply.
        names = [name for name, _, _ in WORKFLOW_LABEL_SPECS]
        self.assertIn(LABEL_DISCUSSION, names)

    def test_discussion_label_is_not_family_aware(self) -> None:
        # A discussion round reads and writes only its own issue and worktree,
        # so the label must stay out of `_FAMILY_AWARE_LABELS` -- routing it
        # through the single-threaded family bucket would serialize every
        # repo's fan-out work behind one long-running agent conversation.
        self.assertNotIn(LABEL_DISCUSSION, _poll_models._FAMILY_AWARE_LABELS)

    def test_dispatcher_routes_discussion_to_handler(self) -> None:
        gh = FakeGitHubClient()
        issue = make_issue(DISCUSSION_ISSUE_NUMBER, label=LABEL_DISCUSSION)
        gh.add_issue(issue)

        with (
            patch.object(_discussion, "_handle_discussion") as discussion_handler,
            patch.object(_pickup, "_handle_pickup") as pickup,
        ):
            _issue_processing._process_issue(gh, _TEST_SPEC, issue)
            discussion_handler.assert_called_once_with(gh, _TEST_SPEC, issue)
            pickup.assert_not_called()


if __name__ == "__main__":
    unittest.main()
