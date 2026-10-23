# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Label vocabulary, predicates, bootstrap, and owner-targeted bindings."""
from __future__ import annotations

import unittest
from types import MappingProxyType
from unittest.mock import MagicMock, call

from github import GithubException
from github.Label import Label
from github.Repository import Repository

from orchestrator.github import labels as _labels
from orchestrator.github.client import GitHubClient
from orchestrator.workflow.state import ControlLabel, WorkflowLabel
from tests.support.fakes import FakeIssue, FakeLabel

_HTTP_FORBIDDEN = 403
_OBSOLETE_IMPLEMENTING = "implementing"
_OBSOLETE_COMMUNITY_CONTRIBUTION = "community_contribution"
_LABEL_SPECS = _labels.WORKFLOW_LABEL_SPECS + _labels.CONTROL_LABEL_SPECS
# The one creation the bootstrap may make for each canonical label, in the
# order it walks them: the exact name, color, and description of its spec.
_CREATIONS = MappingProxyType({
    name: call(name=name, color=color, description=description)
    for name, color, description in _LABEL_SPECS
})
# The only repository requests a bootstrap makes. Any other -- an issue read
# above all -- is a road to some issue's label assignments.
_BOOTSTRAP_REQUESTS = frozenset(("get_labels", "create_label"))

# Repository definitions -> how many of them the bootstrap finds canonical.
# Only an exact canonical name counts: an obsolete bare spelling beside or
# instead of the canonical label, or a label of the repository's own, is not
# one. The seven unprefixed names ARE canonical, so they are found rather than
# created a second time under the namespace.
_DEFINITION_CASES = (
    (
        "only obsolete",
        (_OBSOLETE_IMPLEMENTING, _OBSOLETE_COMMUNITY_CONTRIBUTION),
        0,
    ),
    (
        "both",
        (
            "workflow:implementing",
            _OBSOLETE_IMPLEMENTING,
            "workflow:community_contribution",
            _OBSOLETE_COMMUNITY_CONTRIBUTION,
        ),
        2,
    ),
    ("neither", (), 0),
    ("unrelated", ("bug", "enhancement"), 0),
    (
        "canonical unprefixed",
        (
            "in_review",
            "question",
            "discussion",
            "done",
            "rejected",
            "backlog",
            "paused",
        ),
        7,
    ),
)


def _issue_with(*label_names: str) -> FakeIssue:
    return FakeIssue(
        number=1,
        labels=[FakeLabel(name) for name in label_names],
    )


def _forbidden() -> GithubException:
    return GithubException(_HTTP_FORBIDDEN, {"message": "Forbidden"}, None)


def _missing_creations(defined_names: tuple[str, ...]) -> list[object]:
    """The creations a bootstrap owes a repository defining these labels."""
    return [
        creation
        for name, creation in _CREATIONS.items()
        if name not in defined_names
    ]


# Issue label sets -> the workflow member `workflow_label` reads past any
# control modifiers (a control label coexists with the workflow state), and
# past an obsolete bare name beside a canonical label in either order. An
# obsolete name alone is no state, so that issue reads as unlabeled.
_WORKFLOW_LABEL_CASES = (
    ((WorkflowLabel.IMPLEMENTING,), WorkflowLabel.IMPLEMENTING),
    (
        (ControlLabel.PAUSED, WorkflowLabel.IMPLEMENTING),
        WorkflowLabel.IMPLEMENTING,
    ),
    (
        (_OBSOLETE_IMPLEMENTING, WorkflowLabel.VALIDATING),
        WorkflowLabel.VALIDATING,
    ),
    (
        (WorkflowLabel.VALIDATING, _OBSOLETE_IMPLEMENTING),
        WorkflowLabel.VALIDATING,
    ),
    ((_OBSOLETE_IMPLEMENTING,), None),
    ((_OBSOLETE_IMPLEMENTING, ControlLabel.PAUSED), None),
    ((WorkflowLabel.QUESTION,), WorkflowLabel.QUESTION),
    ((ControlLabel.BACKLOG,), None),
    ((), None),
)

# Issue label sets -> the first hard-skip control label (backlog before
# paused); the community-contribution label coexists with the workflow state
# and never skips.
_HARD_SKIP_CASES = (
    ((ControlLabel.PAUSED, ControlLabel.BACKLOG), ControlLabel.BACKLOG),
    ((WorkflowLabel.IMPLEMENTING, ControlLabel.PAUSED), ControlLabel.PAUSED),
    ((ControlLabel.COMMUNITY_CONTRIBUTION,), None),
    ((WorkflowLabel.IN_REVIEW,), None),
)


class WorkflowLabelPredicateTest(unittest.TestCase):
    """`workflow_label` reports the FSM state, ignoring control modifiers.

    A control label coexists with the workflow state rather than masking it, so
    a paused, implementing issue still reports the implementing state. Only a
    canonical label is a state, the unprefixed ones such as `question`
    included; an obsolete bare name such as `implementing` is repository
    metadata and never answers, alone or beside a canonical label.
    """

    def test_reads_member_past_control_labels(self) -> None:
        for label_names, expected in _WORKFLOW_LABEL_CASES:
            with self.subTest(label_names=label_names):
                self.assertIs(
                    _labels.workflow_label(_issue_with(*label_names)),
                    expected,
                )


class IssueHasLabelTest(unittest.TestCase):
    """A control label matches however a human cased it; a workflow state
    matches only its exact canonical label, so a recased or bare stage name
    is a repository label."""

    def test_matches_case_insensitively(self) -> None:
        issue = _issue_with("Implementing")
        self.assertTrue(_labels.issue_has_label(issue, _OBSOLETE_IMPLEMENTING))
        self.assertTrue(_labels.issue_has_label(issue, "IMPLEMENTING"))

    def test_absent_label_is_false(self) -> None:
        self.assertFalse(_labels.issue_has_label(_issue_with("ready"), "done"))
        self.assertFalse(_labels.issue_has_label(_issue_with(), "ready"))

    def test_a_state_matches_only_canonically(self) -> None:
        for label_name, wanted, expected in (
            ("question", WorkflowLabel.QUESTION, True),
            ("Question", WorkflowLabel.QUESTION, False),
            ("workflow:implementing", WorkflowLabel.IMPLEMENTING, True),
            ("Workflow:Implementing", WorkflowLabel.IMPLEMENTING, False),
            (_OBSOLETE_IMPLEMENTING, WorkflowLabel.IMPLEMENTING, False),
        ):
            with self.subTest(label=label_name):
                self.assertIs(
                    _labels.issue_has_workflow_label(
                        _issue_with(label_name), wanted,
                    ),
                    expected,
                )


class HardSkipControlLabelTest(unittest.TestCase):
    """Only `backlog` and `paused` suppress processing, backlog reported first.

    The community-contribution label is registered for bootstrap but coexists
    with the workflow rather than pausing it, so it is never a hard skip.
    """

    def test_reports_first_hard_skip_control_label(self) -> None:
        for label_names, expected in _HARD_SKIP_CASES:
            with self.subTest(label_names=label_names):
                self.assertIs(
                    _labels.hard_skip_control_label(_issue_with(*label_names)),
                    expected,
                )


class EnsureWorkflowLabelsTest(unittest.TestCase):
    """Bootstrap creates the missing canonical labels and touches nothing else.

    Every definition the repository already lists -- canonical, obsolete, or
    its own -- is left as it is: never edited, renamed, or deleted, and no
    issue is read, so no issue's label assignments move either. The PAT may
    lack `Issues: Read and write`, and the orchestrator has to keep polling
    either way: a failed listing skips the pass entirely, and a failed creation
    stops after the first refusal instead of retrying it per spec.
    """

    def setUp(self) -> None:
        # Bypass the networked __init__; the bootstrap reads only `self.repo`.
        self.gh = GitHubClient.__new__(GitHubClient)
        self.gh.repo = MagicMock(spec=Repository)

    def test_creates_only_missing_canonical_labels(self) -> None:
        for case, defined_names, found_count in _DEFINITION_CASES:
            with self.subTest(case=case):
                definitions = self._define(*defined_names)

                self.gh.ensure_workflow_labels()

                self.assertEqual(
                    self.gh.repo.create_label.call_args_list,
                    _missing_creations(defined_names),
                )
                self.assertEqual(
                    self.gh.repo.create_label.call_count,
                    len(_CREATIONS) - found_count,
                )
                self._assert_untouched(definitions)

    def test_unreadable_labels_skip_the_bootstrap(self) -> None:
        self.gh.repo.get_labels.side_effect = _forbidden()

        self.gh.ensure_workflow_labels()

        self.assertEqual(
            [request[0] for request in self.gh.repo.method_calls],
            ["get_labels"],
        )

    def test_refused_creation_stops_bootstrap(self) -> None:
        # A refusal is no cue to fall back on the obsolete definitions: they
        # stay as they are, and the denied write is not retried per spec.
        definitions = self._define("decomposing", _OBSOLETE_IMPLEMENTING)
        self.gh.repo.create_label.side_effect = _forbidden()

        self.gh.ensure_workflow_labels()

        self.gh.repo.create_label.assert_called_once()
        self._assert_untouched(definitions)

    def _define(self, *label_names: str) -> list[MagicMock]:
        """Give a fresh repository exactly these label definitions.

        `name` is assigned after construction because `MagicMock(name=...)`
        configures the mock's own repr instead of the attribute under test.
        """
        definitions = []
        for label_name in label_names:
            definition = MagicMock(spec=Label)
            definition.name = label_name
            definitions.append(definition)
        self.gh.repo = MagicMock(spec=Repository)
        self.gh.repo.get_labels.return_value = definitions
        return definitions

    def _assert_untouched(self, definitions: list[MagicMock]) -> None:
        for definition in definitions:
            self.assertEqual(
                definition.method_calls, [], f"{definition.name} was written",
            )
        self.assertLessEqual(
            {request[0] for request in self.gh.repo.method_calls},
            _BOOTSTRAP_REQUESTS,
        )


if __name__ == "__main__":
    unittest.main()
