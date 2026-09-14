# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Which labels the GitHub-side namespace covers, and what it leaves alone."""
from __future__ import annotations

import unittest

from orchestrator.workflow.label_reading import (
    coerce_workflow_label,
    issue_workflow_label,
    label_for_name,
    replaced_label_names,
)
from orchestrator.workflow.state import ControlLabel, WorkflowLabel, legacy_label_name, stage_name
from tests.support.fakes import (
    FakeGitHubClient,
    FakeIssue,
    FakeLabel,
    make_issue,
)

_NAMESPACE = "workflow:"
_MIXED_ISSUE = 1
_CANONICAL_IMPLEMENTING = "workflow:implementing"
_LEGACY_IMPLEMENTING = "implementing"
_CANONICAL_VALIDATING = "workflow:validating"
# A label the repository owns: not part of the workflow vocabulary.
_REPO_LABEL = "bug"


def _issue_with(*label_names: str) -> FakeIssue:
    """An issue carrying exactly the given labels, in the given order."""
    return FakeIssue(
        number=_MIXED_ISSUE,
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

    def test_legacy_name_is_the_tag_only_when_renamed(self) -> None:
        # The bare spelling a repository may still carry, which is what the
        # bootstrap renames and what a labeled PR is recognized under.
        self.assertEqual(legacy_label_name(WorkflowLabel.FIXING), "fixing")
        self.assertEqual(
            legacy_label_name(ControlLabel.COMMUNITY_CONTRIBUTION),
            "community_contribution",
        )
        self.assertIsNone(legacy_label_name(WorkflowLabel.DONE))
        self.assertIsNone(legacy_label_name(ControlLabel.BACKLOG))


class LegacyLabelCompatibilityTest(unittest.TestCase):
    """A pre-namespace label still resolves, and a write replaces it.

    A repository whose labels the bootstrap could not rename keeps issues
    carrying the bare spelling; reading it as its member is what keeps those
    issues routing, and dropping it on the next write is what stops the two
    spellings from coexisting on one issue.
    """

    def test_both_spellings_resolve_to_one_member(self) -> None:
        self.assertIs(label_for_name("fixing"), WorkflowLabel.FIXING)
        self.assertIs(label_for_name("workflow:fixing"), WorkflowLabel.FIXING)
        self.assertIsNone(label_for_name("backlog"))
        # Sharing the prefix does not make a control label a workflow state:
        # resolving one would route the PR sweep's own label to a handler.
        self.assertIsNone(
            label_for_name(ControlLabel.COMMUNITY_CONTRIBUTION),
        )

    def test_coercion_accepts_the_legacy_spelling(self) -> None:
        self.assertIs(coerce_workflow_label("fixing"), WorkflowLabel.FIXING)

    def test_legacy_labeled_issue_reads_and_relabels(self) -> None:
        gh = FakeGitHubClient()
        issue = make_issue(1, label="implementing")
        gh.add_issue(issue)

        self.assertIs(gh.workflow_label(issue), WorkflowLabel.IMPLEMENTING)

        gh.set_workflow_label(issue, WorkflowLabel.VALIDATING)

        self.assertEqual(
            [label.name for label in issue.labels],
            [WorkflowLabel.VALIDATING],
        )


class CanonicalLabelPrecedenceTest(unittest.TestCase):
    """A namespaced label outranks a bare one on the same issue, either order.

    The orchestrator writes only the namespaced spelling, so a bare tag beside
    one is never the state: reading it as the state routes the issue to the
    wrong handler, and stripping it on the next write deletes a label the
    repository owns.
    """

    def test_canonical_wins_either_order(self) -> None:
        for names in (
            (_LEGACY_IMPLEMENTING, _CANONICAL_VALIDATING),
            (_CANONICAL_VALIDATING, _LEGACY_IMPLEMENTING),
        ):
            with self.subTest(names=names):
                self.assertIs(
                    issue_workflow_label(names), WorkflowLabel.VALIDATING,
                )

    def test_bare_tag_answers_only_alone(self) -> None:
        self.assertIs(
            issue_workflow_label((_LEGACY_IMPLEMENTING,)),
            WorkflowLabel.IMPLEMENTING,
        )
        self.assertIsNone(issue_workflow_label((_REPO_LABEL, "backlog")))

    def test_write_replaces_only_its_own(self) -> None:
        # `blocked` beside a namespaced label is the repository's own; the
        # same name alone is this issue's pre-migration state.
        self.assertEqual(
            replaced_label_names(
                ("blocked", _CANONICAL_IMPLEMENTING, _REPO_LABEL),
            ),
            frozenset((_CANONICAL_IMPLEMENTING,)),
        )
        self.assertEqual(
            replaced_label_names((_LEGACY_IMPLEMENTING, _REPO_LABEL)),
            frozenset((_LEGACY_IMPLEMENTING,)),
        )
        self.assertEqual(
            replaced_label_names((_REPO_LABEL, "backlog")), frozenset(),
        )


class MixedLabelIssueTest(unittest.TestCase):
    """The client reads and writes a mixed-label issue the same way.

    Mirrors `CanonicalLabelPrecedenceTest` through the fake, which the whole
    stage suite runs on: a divergence there would hide the real client's
    behavior behind a double that disagrees with it.
    """

    def test_canonical_read_wins(self) -> None:
        for names in (
            (_LEGACY_IMPLEMENTING, _CANONICAL_VALIDATING),
            (_CANONICAL_VALIDATING, _LEGACY_IMPLEMENTING),
        ):
            with self.subTest(names=names):
                gh = FakeGitHubClient()
                issue = _issue_with(*names)
                gh.add_issue(issue)
                self.assertIs(
                    gh.workflow_label(issue), WorkflowLabel.VALIDATING,
                )

    def test_write_keeps_repo_label(self) -> None:
        gh = FakeGitHubClient()
        issue = _issue_with("blocked", _CANONICAL_IMPLEMENTING)
        gh.add_issue(issue)

        gh.set_workflow_label(issue, WorkflowLabel.VALIDATING)

        self.assertEqual(
            [label.name for label in issue.labels],
            ["blocked", WorkflowLabel.VALIDATING],
        )

    def test_write_drops_stale_bare_label(self) -> None:
        # Both spellings of the SAME state: the bare one is the leftover the
        # migration has not reached, so the write clears it rather than
        # leaving the issue carrying two labels for one state.
        gh = FakeGitHubClient()
        issue = _issue_with(_LEGACY_IMPLEMENTING, _CANONICAL_IMPLEMENTING)
        gh.add_issue(issue)

        gh.set_workflow_label(issue, WorkflowLabel.VALIDATING)

        self.assertEqual(
            [label.name for label in issue.labels],
            [WorkflowLabel.VALIDATING],
        )


if __name__ == "__main__":
    unittest.main()
