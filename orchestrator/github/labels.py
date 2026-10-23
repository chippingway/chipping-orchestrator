# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""GitHub label vocabulary, bootstrap, and cached repository label reads.

Bootstrap creates the canonical labels a repository lacks and leaves every
other definition, with the issues carrying it, as it found it. The cache keeps
each label it resolves for the client's life and remembers no failed lookup,
so the next closed sweep asks for that label again.

A workflow state is matched by its exact canonical label, through the shared
resolver; an operator's control label is matched however a human cased it.
"""
from __future__ import annotations

import logging

from github import GithubException
from github.Issue import Issue
from github.Label import Label

from orchestrator.github.aliases import StaticMethodAlias
from orchestrator.workflow.label_reading import issue_workflow_label, label_for_name
from orchestrator.workflow.state import ControlLabel, WorkflowLabel

log = logging.getLogger("orchestrator.github")

WORKFLOW_LABEL_SPECS: tuple[tuple[WorkflowLabel, str, str], ...] = (
    (WorkflowLabel.DECOMPOSING, "fbca04", "Orchestrator is breaking this issue into sub-issues"),
    (WorkflowLabel.READY, "0e8a16", "Decomposed and ready for implementation"),
    (WorkflowLabel.BLOCKED, "b60205", "Blocked on another issue"),
    (WorkflowLabel.UMBRELLA, "ededed", "Parent of child issues with no implementation of its own"),
    (WorkflowLabel.IMPLEMENTING, "1d76db", "A coding agent is working on this"),
    (WorkflowLabel.VALIDATING, "8a2be2", "Reviewer agent is checking the diff; verify gate runs on approval"),
    (
        WorkflowLabel.DOCUMENTING,
        "c2e0c6",
        "Documentation pass after reviewer approval (final-docs hop), before in_review",
    ),
    (WorkflowLabel.IN_REVIEW, "d93f0b", "PR is open, awaiting human review"),
    (
        WorkflowLabel.FIXING,
        "fef2c0",
        "Dev fix-loop addressing reviewer changes or in_review PR feedback before re-validation",
    ),
    (
        WorkflowLabel.RESOLVING_CONFLICT,
        "e99695",
        "Resolving an actual rebase conflict (clean rebases route straight to validating)",
    ),
    (WorkflowLabel.QUESTION, "d876e3", "Awaiting a clarifying answer from a human before the orchestrator can advance"),
    (
        WorkflowLabel.DISCUSSION,
        "0ea5e9",
        "Decomposer-led architecture discussion; the agent proposes, humans decide, nothing is implemented",
    ),
    (WorkflowLabel.DONE, "cccccc", "Merged to main"),
    (WorkflowLabel.REJECTED, "5c0000", "Issue rejected / closed without merge"),
)
assert {spec[0] for spec in WORKFLOW_LABEL_SPECS} == set(WorkflowLabel)
WORKFLOW_LABELS = frozenset(WorkflowLabel)

BACKLOG_LABEL = ControlLabel.BACKLOG
PAUSED_LABEL = ControlLabel.PAUSED
COMMUNITY_CONTRIBUTION_LABEL = ControlLabel.COMMUNITY_CONTRIBUTION
CONTROL_LABEL_SPECS: tuple[tuple[ControlLabel, str, str], ...] = (
    (
        BACKLOG_LABEL,
        "c5def5",
        "Skip orchestrator processing entirely until the label is removed",
    ),
    (
        PAUSED_LABEL,
        "d4c5f9",
        "Pause an in-flight issue: skip orchestrator processing entirely until the label is removed",
    ),
    (
        COMMUNITY_CONTRIBUTION_LABEL,
        "7057ff",
        "PR opened by an author outside ALLOWED_ISSUE_AUTHORS; human review requested",
    ),
)
HARD_SKIP_CONTROL_LABELS: tuple[ControlLabel, ...] = (
    BACKLOG_LABEL,
    PAUSED_LABEL,
)


def issue_has_label(issue: Issue, label_name: str) -> bool:
    """Return whether an issue has a case-insensitive label name."""
    wanted_label = (label_name or "").lower()
    return any(
        ((getattr(label, "name", "") or "").lower() == wanted_label)
        for label in (issue.labels or [])
    )


def issue_has_workflow_label(issue: Issue, wanted: str) -> bool:
    """Return whether an issue carries this exact canonical workflow label.

    Read through the shared resolver rather than case-insensitively as
    `issue_has_label` reads a control: a repository's `Question` or a bare
    `implementing` names no state, so it holds no stage's checkout either.
    """
    return any(
        label_for_name(getattr(issue_label, "name", None)) == wanted
        for issue_label in (issue.labels or [])
    )


def hard_skip_control_label(issue: Issue) -> str | None:
    """Return the first control label that suppresses issue processing."""
    for control_label in HARD_SKIP_CONTROL_LABELS:
        if issue_has_label(issue, control_label):
            return control_label
    return None


def workflow_label(issue: Issue) -> WorkflowLabel | None:
    """Return an issue's workflow label, excluding control labels.

    Only a canonical label counts, so an issue whose sole stage-like label is
    a bare name such as `ready` reads as unlabeled -- see
    `issue_workflow_label`.
    """
    return issue_workflow_label(
        issue_label.name for issue_label in issue.labels
    )


WORKFLOW_LABEL_METHOD = StaticMethodAlias(workflow_label)


class GitHubLabelMixin:
    """Repository label provisioning and cached label reads."""

    def ensure_workflow_labels(self) -> None:
        """Best-effort creation of the canonical labels the repository lacks.

        Only the exact canonical name counts as present, the bare-spelled
        canonical labels included. Any other definition -- a pre-namespace
        spelling or a label of the repository's own -- is never looked up,
        edited, or deleted, so the issues carrying it keep it.
        """
        existing_names = self._existing_label_names()
        if existing_names is None:
            return
        label_specs = WORKFLOW_LABEL_SPECS + CONTROL_LABEL_SPECS
        for name, color, description in label_specs:
            if name in existing_names:
                continue
            if not self._provision_label(name, color, description):
                return

    def _existing_label_names(self) -> frozenset[str] | None:
        """Return the repository's label names, or None if unreadable."""
        try:
            return frozenset(
                repo_label.name for repo_label in self.repo.get_labels()
            )
        except GithubException as error:
            log.warning(
                "could not list labels (HTTP %s); skipping label bootstrap. "
                "Grant the PAT 'Issues: Read and write' to enable.",
                error.status,
            )
            return None

    def _provision_label(self, name: str, color: str, description: str) -> bool:
        """Create one missing canonical label.

        Returns False once a refusal has been logged, so the caller stops
        rather than retrying the same denied permission per spec.
        """
        try:
            self.repo.create_label(
                name=name, color=color, description=description,
            )
        except GithubException as error:
            log.error(
                "could not provision label %r (HTTP %s). "
                "Fine-grained PAT needs 'Issues: Read and write'. "
                "Skipping remaining label bootstrap; orchestrator will "
                "keep running and may retry on the next restart.",
                name,
                error.status,
            )
            return False
        log.info("created label %r", name)
        return True

    def _cached_label(self, name: str) -> Label | None:
        """Resolve and cache a label, while leaving failures retryable.

        A resolved label is fetched once per client: every closed sweep asks
        for the same canonical labels, and a repository's definition of one
        does not change between passes. A failure is not remembered: a 404 is
        a label the bootstrap could not create and a human may add at any
        moment, and a 403 -- what an exhausted primary rate limit answers --
        says nothing about whether the label exists, so the next call asks
        again either way.
        """
        cached_label = self._label_cache.get(name)
        if cached_label is not None:
            return cached_label
        try:
            label_object = self.repo.get_label(name)
        except GithubException as error:
            log.warning(
                "could not look up %r label for closed-issue sweep "
                "(HTTP %s); skipping. Externally-merged %s issues will "
                "not finalize to `done` until the label exists.",
                name,
                error.status,
                name,
            )
            return None
        self._label_cache[name] = label_object
        return label_object
