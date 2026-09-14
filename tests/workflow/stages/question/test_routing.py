# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""`question` label bootstrap + dispatcher routing. Handler behavior lives
in the focused sibling modules; this module pins only the label-spec /
family-aware / dispatcher wiring that keeps the dispatcher from falling through
to pickup or implementing."""

from __future__ import annotations

import unittest
from unittest.mock import patch

from orchestrator.workflow.engine import (
    issue_processing as _issue_processing,
    pickup as _pickup,
    poll_models as _poll_models,
)
from orchestrator.workflow.stages.implementing import handler as _implementing
from orchestrator.workflow.stages.question import handler as _question
from tests.support.fakes import FakeGitHubClient, make_issue
from tests.workflow.fixtures import _TEST_SPEC, LABEL_QUESTION

QUESTION_ISSUE_NUMBER = 801


class QuestionLabelRoutingTest(unittest.TestCase):
    """`question` is a first-class workflow label routed to its own stage
    handler owner, which is where a patch has to land to intercept a
    dispatched tick. The behavioral tests for that handler live in the sibling
    modules; this class only covers label bootstrapping and dispatcher routing.
    """

    def test_label_is_recognized(self) -> None:
        from orchestrator.github.labels import WORKFLOW_LABELS

        self.assertIn(LABEL_QUESTION, WORKFLOW_LABELS)

    def test_question_label_is_in_bootstrap_specs(self) -> None:
        # Label bootstrap iterates WORKFLOW_LABEL_SPECS; if the spec entry
        # is missing, `ensure_workflow_labels` would never create the
        # label on a fresh repo and operators would be unable to apply it.
        from orchestrator.github.labels import WORKFLOW_LABEL_SPECS

        names = [name for name, _, _ in WORKFLOW_LABEL_SPECS]
        self.assertIn(LABEL_QUESTION, names)

    def test_question_label_is_not_family_aware(self) -> None:
        # Open `question` issues touch only their own pinned state, so the
        # label must stay out of `_FAMILY_AWARE_LABELS` -- otherwise the
        # parallel tick path would route it through the single-threaded
        # family bucket and defeat fan-out concurrency.
        self.assertNotIn(LABEL_QUESTION, _poll_models._FAMILY_AWARE_LABELS)

    def test_dispatcher_routes_question_to_handler(self) -> None:
        gh = FakeGitHubClient()
        issue = make_issue(QUESTION_ISSUE_NUMBER, label=LABEL_QUESTION)
        gh.add_issue(issue)

        with (
            patch.object(_question, "_handle_question") as question_handler,
            patch.object(_pickup, "_handle_pickup") as pickup,
            patch.object(_implementing, "_handle_implementing") as impl,
        ):
            _issue_processing._process_issue(gh, _TEST_SPEC, issue)
            question_handler.assert_called_once_with(gh, _TEST_SPEC, issue)
            pickup.assert_not_called()
            impl.assert_not_called()


if __name__ == "__main__":
    unittest.main()
