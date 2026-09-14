# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""GitHub label vocabulary, bootstrap, and cached repository label reads.

Bootstrap renames legacy labels so existing issues move with the vocabulary.
The cache bounds repeated reads; confirmed-absent legacy spellings are
retried after a bounded number of closed sweeps, while failed requests stay
retryable. Each sweep reports only the absences that it observed itself.
"""
from __future__ import annotations

import logging

from github import GithubException
from github.Issue import Issue
from github.Label import Label

from orchestrator.github.aliases import StaticMethodAlias
from orchestrator.workflow.label_reading import issue_workflow_label
from orchestrator.workflow.state import ControlLabel, WorkflowLabel, legacy_label_name

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
# Every spelling the sweep's own label can be found under. The label is the
# sweep's dedup marker, so a PR still carrying the bare one -- on a repository
# the bootstrap rename could not reach -- has to read as already marked, or the
# HITL ping fires a second time on a PR a human was already asked to review.
COMMUNITY_CONTRIBUTION_LABEL_NAMES: tuple[str, ...] = tuple(
    label_name
    for label_name in (
        COMMUNITY_CONTRIBUTION_LABEL,
        legacy_label_name(COMMUNITY_CONTRIBUTION_LABEL),
    )
    if label_name is not None
)
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


# The one status that answers "this repository does not have that label".
# Anything else -- 403 on an exhausted rate limit, a 5xx -- says only that the
# question could not be asked, so the sweep has to ask it again.
_HTTP_NOT_FOUND = 404

# How many closed-issue sweeps a confirmed-absent label is taken at its word.
# Counted in sweeps rather than seconds because the cost being throttled is one
# request per sweep -- and counted off `_closed_sweeps`, which advances only
# when a sweep actually runs, so `CLOSED_ISSUE_SWEEP_EVERY_N_TICKS` stretches
# the window in wall-clock terms instead of eroding it. Long enough that a
# migrated repository is not re-asking for a label nobody has on every pass,
# short enough that a human re-adding one by hand is picked up without a
# restart -- the absence is throttled, never final.
_ABSENT_LABEL_RETRY_SWEEPS = 20


def issue_has_label(issue: Issue, label_name: str) -> bool:
    """Return whether an issue has a case-insensitive label name."""
    wanted_label = (label_name or "").lower()
    return any(
        ((getattr(label, "name", "") or "").lower() == wanted_label)
        for label in (issue.labels or [])
    )


def hard_skip_control_label(issue: Issue) -> str | None:
    """Return the first control label that suppresses issue processing."""
    for control_label in HARD_SKIP_CONTROL_LABELS:
        if issue_has_label(issue, control_label):
            return control_label
    return None


def workflow_label(issue: Issue) -> WorkflowLabel | None:
    """Return an issue's workflow label, excluding control labels.

    The namespaced spelling wins over a pre-namespace one on the same issue,
    whichever order GitHub lists them in -- see `issue_workflow_label`.
    """
    return issue_workflow_label(
        issue_label.name for issue_label in issue.labels
    )


WORKFLOW_LABEL_METHOD = StaticMethodAlias(workflow_label)


class GitHubLabelMixin:
    """Repository label provisioning, cached reads, and bounded absence retries."""

    def ensure_workflow_labels(self) -> None:
        """Best-effort provisioning of missing workflow and control labels."""
        existing_labels = self._existing_labels()
        if existing_labels is None:
            return
        label_specs = WORKFLOW_LABEL_SPECS + CONTROL_LABEL_SPECS
        for name, color, description in label_specs:
            if name in existing_labels:
                continue
            if not self._provision_label(
                existing_labels, name, color, description,
            ):
                return

    def _existing_labels(self) -> dict[str, Label] | None:
        """Return the repository's labels by name, or None if unreadable."""
        try:
            return {
                repo_label.name: repo_label
                for repo_label in self.repo.get_labels()
            }
        except GithubException as error:
            log.warning(
                "could not list labels (HTTP %s); skipping label bootstrap. "
                "Grant the PAT 'Issues: Read and write' to enable.",
                error.status,
            )
            return None

    def _provision_label(
        self,
        existing_labels: dict[str, Label],
        name: str,
        color: str,
        description: str,
    ) -> bool:
        """Rename the pre-namespace label into place, or create a fresh one.

        Renaming carries every issue already holding the old label across in
        one edit, which is the only migration path for an issue no polling
        pass revisits -- a closed one mid-sweep, or one parked under
        `backlog`. Returns False once a refusal has been logged, so the caller
        stops rather than retrying the same denied permission per spec.
        """
        legacy_name = legacy_label_name(name)
        legacy_label = (
            None if legacy_name is None else existing_labels.get(legacy_name)
        )
        try:
            if legacy_label is None:
                self.repo.create_label(
                    name=name, color=color, description=description,
                )
            else:
                legacy_label.edit(
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
        if legacy_label is None:
            log.info("created label %r", name)
        else:
            log.info("renamed label %r to %r", legacy_name, name)
        return True


    def _cached_label(
        self,
        name: str,
        *,
        throttle_absent: bool = False,
        absent_names: list[str] | None = None,
    ) -> Label | None:
        """Resolve and cache a label, while leaving failures retryable.

        Every failure is retried eventually; the only question is how soon.
        Retrying on the very next call is the default, because a label the
        bootstrap could not create is one a human may add at any moment.
        ``throttle_absent`` widens that to `_ABSENT_LABEL_RETRY_SWEEPS`
        closed-issue sweeps for one case: a 404 on a pre-namespace spelling
        the sweep asks for beside the namespaced one. Most repositories will
        never have that label again, so asking every sweep is a request spent
        on a certain miss -- but a human or an older integration can still
        re-apply one, so the window expires rather than closing.

        The throttle is a 404 only. A 403 is what this client sees when the
        primary rate limit is exhausted, and standing down on it would strand
        exactly the closed legacy-labeled issues the second query exists to
        reach.

        ``absent_names`` is where a throttled miss is recorded for the caller
        to summarize; a caller that passes none takes the miss silently.
        """
        cached_label = self._label_cache.get(name)
        if cached_label is not None:
            return cached_label
        if self._absent_after_sweep.get(name, 0) > self._closed_sweeps:
            return None
        try:
            label_object = self.repo.get_label(name)
        except GithubException as error:
            self._report_label_lookup_failure(
                name, error, throttle_absent, absent_names,
            )
            return None
        self._absent_after_sweep.pop(name, None)
        self._label_cache[name] = label_object
        return label_object

    def _report_label_lookup_failure(
        self,
        name: str,
        error: GithubException,
        throttle_absent: bool,
        absent_names: list[str] | None,
    ) -> None:
        """Report a label the sweep could not resolve, and when to re-ask."""
        if throttle_absent and error.status == _HTTP_NOT_FOUND:
            self._absent_after_sweep[name] = (
                self._closed_sweeps + _ABSENT_LABEL_RETRY_SWEEPS
            )
            # Handed to the caller's summary rather than reported here: this
            # answer is the expected one, and a line per spelling says nothing
            # a line per repository does not.
            if absent_names is not None:
                absent_names.append(name)
            return
        log.warning(
            "could not look up %r label for closed-issue sweep "
            "(HTTP %s); skipping. Externally-merged %s issues will "
            "not finalize to `done` until the label exists.",
            name,
            error.status,
            name,
        )

    def _report_absent_legacy_labels(self, absent_names: list[str]) -> None:
        """Summarize the legacy spellings one sweep confirmed absent.

        Reported per repository, and only for the spellings this sweep asked
        about: on a migrated host the alternative is a burst of near-identical
        lines naming no repository -- once per legacy spelling per repo on
        every fresh process, and again whenever the retry window expires --
        that reads like broken configuration while saying only that the rename
        landed.

        The names come from the sweep that collected them, so a sweep that
        raises partway through takes its own with it. Held on the client
        instead, they would outlive the pass that asked, and the next sweep
        would report a name it never re-asked -- a skip served from the retry
        window, restated as a fresh miss with the window starting over.
        """
        if not absent_names:
            return
        log.info(
            "repo=%s closed-issue sweep: %d legacy (pre-namespace) label "
            "spelling(s) absent; not asked again for %d sweeps: %s. Nothing "
            "is stranded unless issues still carry them.",
            self._repo_slug,
            len(absent_names),
            _ABSENT_LABEL_RETRY_SWEEPS,
            ", ".join(absent_names),
        )
