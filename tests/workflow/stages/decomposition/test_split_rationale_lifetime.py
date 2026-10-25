# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What clears the rationale an ordinary split recorded, and the one handoff that keeps it.

On a parent that is no umbrella the rationale is the scope the split left for
the parent's own pass. Whatever supersedes that split -- a `single` decision,
an edit that resets the manifest or reroutes the parent back to decomposition,
a restart -- clears it, so no later implementation reads residual scope
nothing owes it. The parent going back to its own work once every child is
done is what the scope was kept for, so that handoff keeps it while it retires
the split's attempt.
"""
from __future__ import annotations

import unittest
from functools import partial
from unittest.mock import patch

from orchestrator import config
from orchestrator.workflow.stages.decomposition import (
    blocked as _blocked,
    state as _state,
    umbrella as _umbrella,
)
from orchestrator.workflow.state import WorkflowLabel
from tests.support.fakes import FakeGitHubClient, FakeIssue, make_issue
from tests.workflow.fixtures import _TEST_SPEC, KEY_AWAITING_HUMAN, _agent, _manifest
from tests.workflow.stages.decomposition import late_restart_support as _restart
from tests.workflow.stages.decomposition.decomposing_test_support import _DecomposingWorkflowMixin
from tests.workflow.stages.decomposition.late_test_support import LATE_ISSUE_NUMBER

KEY_SPLIT_RATIONALE = "split_rationale"
KEY_SPLIT_ATTEMPT = "split_attempt"
PARENT_NUMBER = 70
CHILD_NUMBERS = (701, 702)
SPLIT_ATTEMPT = "0123456789abcdef"
DECOMPOSER_SESSION = "dec-sess"

# What the earlier split kept for the parent's own pass.
RATIONALE = "the parent keeps the release notes and the settings change for its own pass"

# A baseline the edited body no longer hashes to.
STALE_HASH = "stale-hash"

_SINGLE = _manifest('{"decision": "single", "rationale": "it fits one pass after all"}')

# The labels a parent waits on before any implementation of its own has
# started that reroute an edit seen there, each with its handler. `blocked`
# reroutes none: the edit waits for its release to `ready`.
_PRE_IMPLEMENTATION = (
    (WorkflowLabel.READY, _blocked._handle_ready),
    (WorkflowLabel.UMBRELLA, _umbrella._handle_umbrella),
)

# The two states a restart may start the issue over in, by the `DECOMPOSE`
# setting that chooses between them.
_RESTART_ROUTES = ((True, WorkflowLabel.DECOMPOSING), (False, WorkflowLabel.IMPLEMENTING))


def _split_markers() -> dict:
    """The markers the split whose rationale is recorded wrote beside it, fresh for each parent."""
    return {
        "children": list(CHILD_NUMBERS),
        "dep_graph": {"1": [0]},
        "expected_children_count": len(CHILD_NUMBERS),
        KEY_SPLIT_ATTEMPT: SPLIT_ATTEMPT,
    }


def _parent(label: str, **recorded) -> tuple[FakeGitHubClient, FakeIssue]:
    """A parent on `label` recording the earlier split's rationale beside `recorded`."""
    gh = FakeGitHubClient()
    issue = make_issue(PARENT_NUMBER, label=label, body="the requirements as they stand")
    gh.add_issue(issue)
    gh.seed_state(issue, split_rationale=RATIONALE, **recorded)
    return gh, issue


class SupersededSplitTest(unittest.TestCase, _DecomposingWorkflowMixin):
    """A decision or an edit that replaces the split takes its rationale with it."""

    def test_a_single_decision_clears_it(self) -> None:
        gh, issue = _parent(WorkflowLabel.DECOMPOSING)

        self._run_decomposing(gh, issue, run_agent=_agent(session_id=DECOMPOSER_SESSION, last_message=_SINGLE))

        self.assertEqual(gh.workflow_label(issue), WorkflowLabel.READY)
        self._assert_cleared(gh)

    def test_a_death_at_the_flip_leaves_it_cleared(self) -> None:
        # The flip sets the label before the decision's own write, so the
        # clear is made durable ahead of it, while the issue is `decomposing`.
        gh, issue = _parent(WorkflowLabel.DECOMPOSING)
        dies = patch.object(gh, "set_workflow_label", side_effect=KeyboardInterrupt("flip"))

        with dies, self.assertRaises(KeyboardInterrupt):
            self._run_decomposing(gh, issue, run_agent=_agent(session_id=DECOMPOSER_SESSION, last_message=_SINGLE))

        self.assertEqual(gh.workflow_label(issue), WorkflowLabel.DECOMPOSING)
        self._assert_cleared(gh)

    def test_an_edit_while_decomposing_clears_it(self) -> None:
        # The decomposer answers the edited body with a question, so no split
        # writes a rationale of its own over the one the reset cleared.
        gh, issue = _parent(WorkflowLabel.DECOMPOSING, user_content_hash=STALE_HASH, **_split_markers())

        self._run_decomposing(gh, issue, run_agent=_agent(session_id=DECOMPOSER_SESSION, last_message="Which docs?"))

        parked = gh.pinned_data(PARENT_NUMBER)
        self.assertTrue(parked.get(KEY_AWAITING_HUMAN), "the question parks the parent")
        self.assertIsNone(parked.get(KEY_SPLIT_ATTEMPT))
        self._assert_cleared(gh)

    def test_a_pre_implementation_reroute_clears_it(self) -> None:
        for label, tick in _PRE_IMPLEMENTATION:
            with self.subTest(label=label):
                gh, issue = _parent(label, user_content_hash=STALE_HASH, **_split_markers())

                self._run(partial(tick, gh, _TEST_SPEC, issue), run_agent=_agent())

                self.assertEqual(gh.label_history, [(PARENT_NUMBER, WorkflowLabel.DECOMPOSING)])
                self.assertIsNone(gh.pinned_data(PARENT_NUMBER).get(KEY_SPLIT_ATTEMPT))
                self._assert_cleared(gh)

    def _assert_cleared(self, gh: FakeGitHubClient) -> None:
        """The parent's durable record holds no rationale for any later reader to take."""
        self.assertIsNone(gh.pinned_data(PARENT_NUMBER).get(KEY_SPLIT_RATIONALE))
        self.assertIsNone(_state._recorded_split_rationale(gh.read_pinned_state(gh.get_issue(PARENT_NUMBER))))


class HandedBackParentTest(unittest.TestCase, _DecomposingWorkflowMixin):
    """A parent whose children are all done goes back to its own work with the scope the split left it."""

    def test_the_handoff_to_its_own_work_keeps_it(self) -> None:
        gh, parent = _parent(WorkflowLabel.BLOCKED, umbrella=False, **_split_markers())
        for child_number in CHILD_NUMBERS:
            gh.add_issue(make_issue(child_number, label=WorkflowLabel.DONE))
            gh.seed_state(child_number, parent_number=PARENT_NUMBER)

        self._run(partial(_blocked._handle_blocked, gh, _TEST_SPEC, parent), run_agent=_agent())

        handed_back = gh.pinned_data(PARENT_NUMBER)
        self.assertEqual(gh.workflow_label(parent), WorkflowLabel.READY)
        self.assertIsNone(handed_back.get(KEY_SPLIT_ATTEMPT), "nothing is left for a recovery to adopt")
        self.assertEqual(handed_back.get(KEY_SPLIT_RATIONALE), RATIONALE)

        self._run(partial(_blocked._handle_ready, gh, _TEST_SPEC, parent), run_agent=_agent())

        self.assertIn((PARENT_NUMBER, WorkflowLabel.IMPLEMENTING), gh.label_history)
        self.assertEqual(_state._recorded_split_rationale(gh.read_pinned_state(parent)), RATIONALE)


class RestartedIssueTest(_restart.RestartCase, unittest.TestCase):
    """A restart's projection keeps no split's rationale, whichever state it starts the issue over in."""

    def test_neither_route_inherits_it(self) -> None:
        # The parent a split handed back keeps its rationale with the attempt
        # retired, which is the record its own late cycle is cancelled over.
        for decompose, target in _RESTART_ROUTES:
            with self.subTest(target=target):
                self._seed(**_restart.CARRIED_OVER, split_rationale=RATIONALE)

                with patch.object(config, "DECOMPOSE", decompose):
                    self._reported_route()

                self.assertEqual(self._labels(), ((LATE_ISSUE_NUMBER, target),))
                self.assertNotIn(KEY_SPLIT_RATIONALE, self._pinned())
                self.assertIsNone(_state._recorded_split_rationale(self.github.read_pinned_state(self.issue)))


if __name__ == "__main__":
    unittest.main()
