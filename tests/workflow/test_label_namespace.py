# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Which labels the GitHub-side namespace covers, and what it leaves alone."""
from __future__ import annotations

import unittest
from pathlib import PurePosixPath
from unittest.mock import patch

from orchestrator import config
from orchestrator.github import labels as _labels
from orchestrator.workflow.label_reading import (
    coerce_workflow_label,
    issue_workflow_label,
    label_for_name,
    replaced_label_names,
)
from orchestrator.workflow.state import ControlLabel, WorkflowLabel, stage_name
from orchestrator.workflow.transition_guard import IllegalTransition
from tests.support.fakes import (
    FakeGitHubClient,
    FakeIssue,
    FakeLabel,
)

_NAMESPACE = "workflow:"
_ISSUE_NUMBER = 1
_CANONICAL_IMPLEMENTING = "workflow:implementing"
_OBSOLETE_IMPLEMENTING = "implementing"
_CANONICAL_VALIDATING = "workflow:validating"
_OBSOLETE_BLOCKED = "blocked"
# A label the repository owns: not part of the workflow vocabulary.
_REPO_LABEL = "bug"
# Bare names that match a namespaced state or control. None is a spelling of
# it: each is a repository label like `bug`, whatever an earlier build wrote.
_OBSOLETE_NAMES = (
    "decomposing",
    "ready",
    _OBSOLETE_BLOCKED,
    "umbrella",
    _OBSOLETE_IMPLEMENTING,
    "validating",
    "documenting",
    "fixing",
    "resolving_conflict",
    "community_contribution",
)


def _issue_with(*label_names: str) -> FakeIssue:
    """An issue carrying exactly the given labels, in the given order."""
    return FakeIssue(
        number=_ISSUE_NUMBER,
        labels=[FakeLabel(name) for name in label_names],
    )


# The states a human also applies or reads on their own keep the bare
# spelling; everything the orchestrator drives itself is namespaced away from
# a repository's own vocabulary.
_UNNAMESPACED_LABELS = frozenset((
    WorkflowLabel.IN_REVIEW,
    WorkflowLabel.QUESTION,
    WorkflowLabel.DISCUSSION,
    WorkflowLabel.DONE,
    WorkflowLabel.REJECTED,
))
# The same split across the controls: an operator types these two by hand, and
# the sweep's community-contribution label is the one the orchestrator applies.
_MANUAL_CONTROL_LABELS = frozenset((
    ControlLabel.BACKLOG,
    ControlLabel.PAUSED,
))

# Issue label sets -> the state they put the issue in, read the same by the
# real client's predicate and the fake every stage suite runs on. A canonical
# label answers whichever order GitHub lists it in; an obsolete name never
# does, even alone.
_ROUTING_CASES = (
    ((_CANONICAL_VALIDATING,), WorkflowLabel.VALIDATING),
    ((_OBSOLETE_IMPLEMENTING, _CANONICAL_VALIDATING), WorkflowLabel.VALIDATING),
    ((_CANONICAL_VALIDATING, _OBSOLETE_IMPLEMENTING), WorkflowLabel.VALIDATING),
    ((_OBSOLETE_IMPLEMENTING,), None),
    (("ready", ControlLabel.BACKLOG), None),
    ((_REPO_LABEL, WorkflowLabel.IN_REVIEW), WorkflowLabel.IN_REVIEW),
)

# Labels on an issue -> what a relabel through the fake leaves beside the new
# workflow label. Only current workflow labels come off: an obsolete name stays
# alone or beside the canonical label of its own state, and so does every
# control, the namespaced one included.
_RELABEL_CASES = (
    ((_OBSOLETE_IMPLEMENTING,), [_OBSOLETE_IMPLEMENTING]),
    (
        (_OBSOLETE_IMPLEMENTING, _CANONICAL_IMPLEMENTING),
        [_OBSOLETE_IMPLEMENTING],
    ),
    ((_OBSOLETE_BLOCKED, _CANONICAL_IMPLEMENTING), [_OBSOLETE_BLOCKED]),
    (
        (
            ControlLabel.PAUSED,
            WorkflowLabel.IN_REVIEW,
            ControlLabel.BACKLOG,
            ControlLabel.COMMUNITY_CONTRIBUTION,
        ),
        [
            ControlLabel.PAUSED,
            ControlLabel.BACKLOG,
            ControlLabel.COMMUNITY_CONTRIBUTION,
        ],
    ),
)


class LabelNamespaceTest(unittest.TestCase):
    """Automated labels are namespaced on GitHub and bare everywhere else."""

    def test_every_driven_state_is_namespaced(self) -> None:
        for member in WorkflowLabel:
            with self.subTest(label=member):
                self.assertEqual(
                    str(member).startswith(_NAMESPACE),
                    member not in _UNNAMESPACED_LABELS,
                )

    def test_only_the_automatic_control_is_namespaced(self) -> None:
        for member in ControlLabel:
            with self.subTest(label=member):
                self.assertEqual(
                    str(member).startswith(_NAMESPACE),
                    member not in _MANUAL_CONTROL_LABELS,
                )

    def test_stage_name_strips_the_namespace(self) -> None:
        # The tag is the analytics / audit / agent-session identifier, so it
        # has to come back out of the label unchanged by the namespace.
        self.assertEqual(stage_name(WorkflowLabel.DECOMPOSING), "decomposing")
        self.assertEqual(stage_name(WorkflowLabel.IN_REVIEW), "in_review")
        self.assertIsNone(stage_name(None))


class CanonicalResolutionTest(unittest.TestCase):
    """Only a current member or its exact wire string names a workflow state.

    The seven labels that were never namespaced are canonical under their bare
    spelling. Every other bare name is repository metadata: it resolves to no
    state, and a label about to be written in it is refused.
    """

    def test_each_member_resolves_by_value(self) -> None:
        for member in WorkflowLabel:
            for named in (member, str(member)):
                with self.subTest(label=named):
                    self.assertIs(label_for_name(named), member)
                    self.assertIs(coerce_workflow_label(named), member)
                    self.assertIs(
                        issue_workflow_label((_REPO_LABEL, named)), member,
                    )

    def test_an_obsolete_or_control_name_is_no_state(self) -> None:
        # A control is canonical as a control and never a state: the operator
        # ones keep their bare spelling, and sharing the prefix does not make
        # the sweep's own label one either.
        for name in (*_OBSOLETE_NAMES, *ControlLabel):
            with self.subTest(name=name):
                self.assertIsNone(label_for_name(name))
                self.assertIsNone(issue_workflow_label((name,)))
                with self.assertRaises(ValueError):
                    coerce_workflow_label(name)

    def test_a_non_string_label_is_no_state(self) -> None:
        # The value is checked, not its text: a path reading `done` is not the
        # terminal state, so nothing resolves, routes, or comes off for it.
        for rendered in (PurePosixPath("done"), PurePosixPath(_CANONICAL_VALIDATING)):
            with self.subTest(value=rendered):
                self.assertIsNone(label_for_name(rendered))
                self.assertIsNone(issue_workflow_label((rendered,)))
                self.assertEqual(
                    replaced_label_names((rendered, WorkflowLabel.DONE)),
                    frozenset((WorkflowLabel.DONE,)),
                )
                with self.assertRaises(ValueError):
                    coerce_workflow_label(rendered)


class SharedResolverRoutingTest(unittest.TestCase):
    """The real client and the fake read and write labels the same way.

    Both route through `label_reading`, which the whole stage suite relies
    on: a double that disagreed would hide the real client's behavior.
    """

    def test_both_clients_read_one_state(self) -> None:
        for names, expected in _ROUTING_CASES:
            with self.subTest(names=names):
                gh = FakeGitHubClient()
                issue = _issue_with(*names)
                gh.add_issue(issue)
                self.assertIs(_labels.workflow_label(issue), expected)
                self.assertIs(gh.workflow_label(issue), expected)

    def test_relabel_keeps_every_other_label(self) -> None:
        for names, kept in _RELABEL_CASES:
            with self.subTest(names=names):
                gh = FakeGitHubClient()
                issue = _issue_with(*names)
                gh.add_issue(issue)

                gh.set_workflow_label(issue, WorkflowLabel.IMPLEMENTING, guarded=False)

                self.assertEqual(
                    [label.name for label in issue.labels],
                    [*kept, WorkflowLabel.IMPLEMENTING],
                )
                self.assertEqual(
                    gh.recorded_events[-1]["stage"], "implementing",
                )

    def test_an_obsolete_label_selects_no_edge(self) -> None:
        # The guard reads the issue as unlabeled, so the bare name buys no
        # edge out of the stage it resembles: only the unlabeled entry's own
        # targets are allowed, and an enforced refusal writes nothing.
        gh = FakeGitHubClient()
        issue = _issue_with(_OBSOLETE_IMPLEMENTING)
        gh.add_issue(issue)

        with patch.object(config, "WORKFLOW_TRANSITION_GUARD", "enforce"):
            with self.assertRaises(IllegalTransition):
                gh.set_workflow_label(issue, WorkflowLabel.VALIDATING)
            self.assertEqual(gh.label_history, [])
            gh.set_workflow_label(issue, WorkflowLabel.IMPLEMENTING)

        self.assertEqual(
            [label.name for label in issue.labels],
            [_OBSOLETE_IMPLEMENTING, WorkflowLabel.IMPLEMENTING],
        )


if __name__ == "__main__":
    unittest.main()
