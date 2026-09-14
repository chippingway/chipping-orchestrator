# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Transition decisions, terminal edges, and guard wiring."""
from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from orchestrator import config
from orchestrator.workflow import transition_guard as _transition_guard
from orchestrator.workflow.state import WorkflowLabel
from orchestrator.workflow.transition_guard import IllegalTransition, guard_transition, is_allowed_transition
from orchestrator.workflow.transitions import ALLOWED_TRANSITIONS
from tests.support.fakes import FakeGitHubClient, make_issue

_VALIDATING_LABEL = "workflow:validating"
_GUARD_ENFORCE = "enforce"
_GUARD_CONFIG_NAME = "WORKFLOW_TRANSITION_GUARD"
_GUARD_LOGGER_NAME = "orchestrator.state_machine"


def _guarded_issue():
    github = FakeGitHubClient()
    issue = make_issue(1, label=_VALIDATING_LABEL)
    github.add_issue(issue)
    return github, issue


class IsAllowedTransitionTest(unittest.TestCase):
    def test_spine_edges_allowed(self) -> None:
        for cur, nxt in (
            (None, WorkflowLabel.DECOMPOSING),
            (None, WorkflowLabel.IMPLEMENTING),
            (WorkflowLabel.IMPLEMENTING, WorkflowLabel.VALIDATING),
            (WorkflowLabel.VALIDATING, WorkflowLabel.DOCUMENTING),
            (WorkflowLabel.VALIDATING, WorkflowLabel.FIXING),
            (WorkflowLabel.DOCUMENTING, WorkflowLabel.IN_REVIEW),
            (WorkflowLabel.IN_REVIEW, WorkflowLabel.FIXING),
            (WorkflowLabel.FIXING, WorkflowLabel.VALIDATING),
            (WorkflowLabel.BLOCKED, WorkflowLabel.READY),
            (WorkflowLabel.BLOCKED, WorkflowLabel.DECOMPOSING),  # drift
            (WorkflowLabel.UMBRELLA, WorkflowLabel.DONE),
        ):
            self.assertTrue(is_allowed_transition(cur, nxt), (cur, nxt))

    def test_illegal_edges_rejected(self) -> None:
        for cur, nxt in (
            (WorkflowLabel.VALIDATING, WorkflowLabel.IN_REVIEW),  # skips docs
            (WorkflowLabel.IMPLEMENTING, WorkflowLabel.IN_REVIEW),  # skips the reviewer path
            (WorkflowLabel.IMPLEMENTING, WorkflowLabel.DOCUMENTING),
            (WorkflowLabel.READY, WorkflowLabel.VALIDATING),  # skips implementing
            (None, WorkflowLabel.DONE),  # entry not terminalizable
        ):
            self.assertFalse(is_allowed_transition(cur, nxt), (cur, nxt))

    def test_conflict_only_from_detour_sources(self) -> None:
        self.assertTrue(
            is_allowed_transition(
                WorkflowLabel.VALIDATING, WorkflowLabel.RESOLVING_CONFLICT,
            )
        )
        # `ready` is not a PR-having detour source.
        self.assertFalse(
            is_allowed_transition(
                WorkflowLabel.READY, WorkflowLabel.RESOLVING_CONFLICT,
            )
        )

    def test_late_gate_edges_are_declared(self) -> None:
        # The late size gate's own four: an oversized committed candidate
        # goes back to adjudication instead of publishing, an adjudication
        # whose owner is closed cancels from either label it can be wearing,
        # and the umbrella that reached `done` in the same visit the close
        # cancelled it has that terminal corrected to the one it earned.
        for cur, nxt in (
            (WorkflowLabel.IMPLEMENTING, WorkflowLabel.DECOMPOSING),
            (WorkflowLabel.DECOMPOSING, WorkflowLabel.REJECTED),
            (WorkflowLabel.UMBRELLA, WorkflowLabel.REJECTED),
            (WorkflowLabel.DONE, WorkflowLabel.REJECTED),
        ):
            self.assertTrue(is_allowed_transition(cur, nxt), (cur, nxt))

    def test_published_candidate_edges_are_declared(self) -> None:
        # The size gate runs in front of every push onto a pull request the
        # remote already carries, so a cumulative candidate past the ceiling
        # is held and adjudicated from whichever state that push was reached
        # under -- the fix loop, the conflict rebase, or the final docs pass.
        # The pre-PR states own no such edge: nothing there has a publication
        # to be measured against.
        # Each is also the way BACK: a settled adjudication continues at the
        # stage it was taken out of, because that stage is the only owner of
        # the completion the candidate still owes.
        for source in (
            WorkflowLabel.VALIDATING,
            WorkflowLabel.DOCUMENTING,
            WorkflowLabel.IN_REVIEW,
            WorkflowLabel.FIXING,
            WorkflowLabel.RESOLVING_CONFLICT,
        ):
            with self.subTest(source=source):
                self.assertTrue(
                    is_allowed_transition(source, WorkflowLabel.DECOMPOSING),
                )
                self.assertTrue(
                    is_allowed_transition(WorkflowLabel.DECOMPOSING, source),
                )
        # `ready` and `blocked` own the edge already, as the re-decompose
        # route rather than as a size hold; `question` owns none at all.
        self.assertFalse(
            is_allowed_transition(
                WorkflowLabel.QUESTION, WorkflowLabel.DECOMPOSING,
            ),
        )

    def test_a_restart_re_enters_from_unlabeled(self) -> None:
        # A restart after a completed cancellation is authorized by the
        # operator REMOVING `rejected`, so the label it writes starts from the
        # unlabeled entry -- which is why the terminal keeps no outgoing edge
        # and a rejected issue left labeled stays inert.
        self.assertEqual(
            ALLOWED_TRANSITIONS[WorkflowLabel.REJECTED], frozenset(),
        )
        for target in (WorkflowLabel.DECOMPOSING, WorkflowLabel.IMPLEMENTING):
            self.assertTrue(is_allowed_transition(None, target), target)

    def test_same_label_is_allowed(self) -> None:
        # Idempotent re-set, even on a terminal.
        self.assertTrue(
            is_allowed_transition(WorkflowLabel.DONE, WorkflowLabel.DONE)
        )
        self.assertTrue(
            is_allowed_transition(
                WorkflowLabel.VALIDATING, WorkflowLabel.VALIDATING,
            )
        )


class TerminalTransitionTest(unittest.TestCase):
    """Terminal transitions are limited to their exact workflow sources."""

    def test_done_allowed_only_from_its_exact_sources(self) -> None:
        # External-merge / drain sources, plus umbrella/question/discussion
        # whose own forward completion is `-> done`. NOT the pre-PR states.
        sources = {
            WorkflowLabel.IMPLEMENTING, WorkflowLabel.VALIDATING,
            WorkflowLabel.DOCUMENTING, WorkflowLabel.IN_REVIEW,
            WorkflowLabel.FIXING, WorkflowLabel.RESOLVING_CONFLICT,
            WorkflowLabel.UMBRELLA, WorkflowLabel.QUESTION,
            WorkflowLabel.DISCUSSION,
        }
        for state in WorkflowLabel:
            if state in (WorkflowLabel.DONE, WorkflowLabel.REJECTED):
                continue
            self.assertEqual(
                is_allowed_transition(state, WorkflowLabel.DONE),
                state in sources, state,
            )

    def test_rejected_only_from_exact_sources(self) -> None:
        # `decomposing` and `umbrella` are the late gate's cancellation: an
        # adjudication whose owner is closed reconciles its external cleanup
        # and stops, under whichever of the two it had reached.
        sources = {
            WorkflowLabel.IMPLEMENTING, WorkflowLabel.VALIDATING,
            WorkflowLabel.DOCUMENTING, WorkflowLabel.IN_REVIEW,
            WorkflowLabel.FIXING, WorkflowLabel.RESOLVING_CONFLICT,
            WorkflowLabel.DISCUSSION, WorkflowLabel.DECOMPOSING,
            WorkflowLabel.UMBRELLA,
        }
        for state in WorkflowLabel:
            if state in (WorkflowLabel.DONE, WorkflowLabel.REJECTED):
                continue
            self.assertEqual(
                is_allowed_transition(state, WorkflowLabel.REJECTED),
                state in sources, state,
            )

    def test_question_can_finish_but_not_reject(self) -> None:
        # Maximal-exactness: `question` only finalizes to `done`; nothing
        # writes `question -> rejected`, so it must be illegal.
        self.assertTrue(
            is_allowed_transition(WorkflowLabel.QUESTION, WorkflowLabel.DONE)
        )
        self.assertFalse(
            is_allowed_transition(WorkflowLabel.QUESTION, WorkflowLabel.REJECTED)
        )

    def test_discussion_leaves_by_either_terminal(self) -> None:
        # The other operator-applied state settles both ways: a discussion ends
        # in the work being done or in the issue being turned down. Asserting
        # the edge set rather than a probe per edge is what makes the pair
        # exhaustive -- a discussion that could reach a working state would be
        # the orchestrator resuming work on a hold nobody lifted.
        self.assertEqual(
            ALLOWED_TRANSITIONS[WorkflowLabel.DISCUSSION],
            frozenset((WorkflowLabel.DONE, WorkflowLabel.REJECTED)),
        )

    def test_pre_pr_states_are_not_terminalizable(self) -> None:
        # ready / blocked have no PR and no terminal writer at all;
        # `decomposing` reaches exactly one terminal, the late gate's
        # cancellation, and still has no way to finish successfully.
        for state in (
            WorkflowLabel.DECOMPOSING, WorkflowLabel.READY, WorkflowLabel.BLOCKED,
        ):
            self.assertFalse(
                is_allowed_transition(state, WorkflowLabel.DONE), state,
            )
        for pre_pr_state in (WorkflowLabel.READY, WorkflowLabel.BLOCKED):
            self.assertFalse(
                is_allowed_transition(pre_pr_state, WorkflowLabel.REJECTED),
                pre_pr_state,
            )


class GuardModeTest(unittest.TestCase):
    """`guard_transition` is the mode-aware wrapper `set_workflow_label`
    calls. `off` no-ops, `warn` logs+proceeds, `enforce` raises."""

    def test_off_never_raises_or_logs(self) -> None:
        with self.assertNoLogs(_GUARD_LOGGER_NAME, level="WARNING"):
            guard_transition(
                WorkflowLabel.VALIDATING, WorkflowLabel.IN_REVIEW, "off",
            )

    def test_warn_logs_but_proceeds(self) -> None:
        warning_mock = MagicMock()
        with patch(
            "orchestrator.workflow.transition_guard.log.warning",
            warning_mock,
        ):
            guard_transition(
                WorkflowLabel.VALIDATING, WorkflowLabel.IN_REVIEW, "warn",
            )
        warning_mock.assert_called_once()
        message, *args = warning_mock.call_args.args
        self.assertIn(
            "illegal workflow transition",
            message % tuple(args),
        )

    def test_enforce_raises_on_illegal(self) -> None:
        with self.assertRaises(IllegalTransition):
            guard_transition(
                WorkflowLabel.VALIDATING, WorkflowLabel.IN_REVIEW, _GUARD_ENFORCE,
            )

    def test_enforce_allows_legal(self) -> None:
        guard_transition(
            WorkflowLabel.VALIDATING, WorkflowLabel.DOCUMENTING, _GUARD_ENFORCE,
        )  # no raise

    def test_enforce_allows_same_label(self) -> None:
        guard_transition(
            WorkflowLabel.DONE, WorkflowLabel.DONE, _GUARD_ENFORCE,
        )  # no raise


class GuardLoggerTest(unittest.TestCase):
    """The warn-mode logger keeps the name operator filters select on."""

    def test_logger_name(self) -> None:
        self.assertEqual(_transition_guard.log.name, _GUARD_LOGGER_NAME)


class SetWorkflowLabelGuardWiringTest(unittest.TestCase):
    """The guard is wired through `set_workflow_label` (the single
    chokepoint), driven by `config.WORKFLOW_TRANSITION_GUARD`."""

    def test_enforce_blocks_illegal_relabel(self) -> None:
        gh, issue = _guarded_issue()
        with patch.object(config, _GUARD_CONFIG_NAME, _GUARD_ENFORCE), self.assertRaises(IllegalTransition):
            gh.set_workflow_label(issue, WorkflowLabel.IN_REVIEW)
        # Label unchanged after the rejected write.
        self.assertEqual(gh.workflow_label(issue), WorkflowLabel.VALIDATING)

    def test_warn_allows_illegal_relabel(self) -> None:
        gh, issue = _guarded_issue()
        with patch.object(config, _GUARD_CONFIG_NAME, "warn"), self.assertLogs(_GUARD_LOGGER_NAME, level="WARNING"):
            gh.set_workflow_label(issue, WorkflowLabel.IN_REVIEW)
        self.assertEqual(gh.workflow_label(issue), WorkflowLabel.IN_REVIEW)

    def test_enforce_allows_legal_relabel(self) -> None:
        gh, issue = _guarded_issue()
        with patch.object(config, _GUARD_CONFIG_NAME, _GUARD_ENFORCE):
            gh.set_workflow_label(issue, WorkflowLabel.DOCUMENTING)
        self.assertEqual(gh.workflow_label(issue), WorkflowLabel.DOCUMENTING)

    def test_enforce_allows_validation_fix_loop(self) -> None:
        gh, issue = _guarded_issue()
        with patch.object(config, _GUARD_CONFIG_NAME, _GUARD_ENFORCE):
            gh.set_workflow_label(issue, WorkflowLabel.FIXING)
        self.assertEqual(gh.workflow_label(issue), WorkflowLabel.FIXING)
