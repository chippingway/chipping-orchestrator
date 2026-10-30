# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Whether the branch, the checkout, and the pull request a pending capture reported on are still the issue's.

Asked last of a capture's admission (`completion_admission`), because each
costs a read of the checkout or of the remote, and a capture some cheaper
reading already answered never pays for them.

The branch is the live resolver's (`naming._admitted_branch`): a record that
pins another current-layout branch than the one the run stood on is another
branch's work, and one naming no branch live work may use stops every road
before a checkout, a launch, or a push, so it holds the capture rather than
proving it stale. The checkout is the issue's own only where it is proven a
worktree of the clone on that branch at the issue's own path
(`evidence._checkout_identity`), and the path the run recorded has to be that
path; a checkout missing, unreadable, or not proven its own holds the capture
the same way, since nothing here may adopt, reset, recreate, or delete one --
and so does a head that is no commit this store holds, since a ref pointed at
a missing object still names one. A proven checkout whose head is a readable
commit other than the one the report is about has moved on -- the developer,
or somebody, committed or reset since -- and the report no longer describes
what would be published.

The pull request, where the record names one, has to be open, on the run's
branch in this repository, and standing on the head the run started on or
the one it reported on: the first is a source still owed its push, the second
one already published. A rewritten-head refresh pushes nothing, so its pull
request has to stand on the very commit it reported on, as the refresh's own
road holds it to before it records anything. Any other head is somebody
else's push, and a pull request merged or closed ended the work the report
was for. One nobody could read holds the capture, and so does one read
without its head's branch, commit, or repository: a mismatch is proved only
against a reading that has all three.

On the implementing road the recorded pull request can be another stage's:
the `discussion` stage's plan, which a human merges to agree to the design
and then relabels, so the implementation is still owed its own publication.
That road's own classification tells the two apart
(`implementing.handler._recorded_pr_is_the_plan`), asked of the head this
one reading took, and a pull request it reads as the plan is none of the
run's: nothing about its state, branch, or head refuses the capture.
"""
from __future__ import annotations

import importlib
import logging
from dataclasses import dataclass

from orchestrator.config import models as _config_models
from orchestrator.git.verification import probes as _probes
from orchestrator.git.worktrees import evidence as _evidence, naming as _naming, paths as _paths
from orchestrator.git.worktrees.models import ProbeAnswer
from orchestrator.github.client import GitHubClient
from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.engine import (
    completion_records as _records,
    completion_recovery_models as _models,
    completion_routes as _routes,
    report_record_values as _record_values,
    stage_targets as _stage_targets,
)
from orchestrator.workflow.state import WorkflowLabel

log = logging.getLogger("orchestrator.workflow")

_PR_NUMBER = "pr_number"

_OPEN = "open"

_REFRESH = _routes.CompletionRoute.REPORT_REFRESH

_UNPROVEN = _models.Decision(_models.Standing.UNCERTAIN, _models.Reason.CHECKOUT_UNPROVEN)

_UNREAD = _models.Decision(_models.Standing.UNCERTAIN, _models.Reason.PULL_REQUEST_UNREAD)


def checkout_refusal(
    spec: _config_models.RepoSpec,
    issue_number: int,
    state: PinnedState,
    capture: _records.CompletionCapture,
) -> _models.Decision | None:
    """Why the branch and checkout `capture` reported from are no longer the issue's to hand on, or None."""
    branch = _naming._admitted_branch(state, spec, issue_number)
    if branch is None:
        return _models.Decision(_models.Standing.UNCERTAIN, _models.Reason.BRANCH_REFUSED)
    if branch != capture.run.branch:
        return _models.Decision(_models.Standing.INVALID, _models.Reason.BRANCH_MOVED)
    head = _own_head(spec, issue_number, capture)
    if not head:
        return _UNPROVEN
    if head != capture.run.source_sha:
        return _models.Decision(_models.Standing.INVALID, _models.Reason.CHECKOUT_MOVED)
    return None


def pull_request_head(
    gh: GitHubClient, state: PinnedState, capture: _records.CompletionCapture,
) -> _models.Decision | str | None:
    """The head the recorded pull request stands on, None where none is recorded, or why it refuses the capture."""
    if state.get(_PR_NUMBER) is None:
        return None
    reading = _pull_request_reading(gh, state.get(_PR_NUMBER))
    if reading is None:
        return _UNREAD
    return _reading_refusal(gh, state, capture, reading) or reading.head


@dataclass(frozen=True)
class _PullRequestReading:
    """What one read of the recorded pull request said: its state, and its head's branch, commit, and repository."""

    state: str
    branch: str | None
    head: str | None
    repository: str | None


def _reading_refusal(
    gh: GitHubClient, state: PinnedState, capture: _records.CompletionCapture, reading: _PullRequestReading,
) -> _models.Decision | None:
    """Why the pull request `reading` read refuses `capture`, or None where it is the run's or the discussion's plan."""
    if capture.handoff.origin is WorkflowLabel.IMPLEMENTING:
        implementing = importlib.import_module(_stage_targets._IMPLEMENTING_HANDLER_OWNER)
        if implementing._recorded_pr_is_the_plan(state, reading.head):
            return None
    if reading.state != _OPEN:
        return _models.Decision(_models.Standing.INVALID, _models.Reason.PULL_REQUEST_ENDED)
    owed_its_push = () if capture.handoff.route is _REFRESH else (capture.run.before_sha,)
    on_the_run = reading.head in {capture.run.source_sha, *owed_its_push}
    own_branch = reading.branch == capture.run.branch and gh.is_own_repository(reading.repository)
    if not (own_branch and on_the_run):
        return _models.Decision(_models.Standing.INVALID, _models.Reason.PULL_REQUEST_MOVED)
    return None


def _own_head(spec: _config_models.RepoSpec, issue_number: int, capture: _records.CompletionCapture) -> str:
    """The head of the issue's own checkout, where it is the one `capture` ran in; "" where nothing proves that.

    The head is proved a commit this store holds before it is answered: a
    ref pointed at an object the store does not hold still names one, and
    that name compared with the commit reported on would read as a checkout
    that moved rather than one nobody can read.
    """
    worktree = _paths._worktree_path(spec, issue_number)
    if str(worktree) != capture.run.worktree:
        return ""
    if _evidence._checkout_identity(spec, issue_number, worktree) is not ProbeAnswer.CONFIRMED:
        return ""
    head = _probes._head_sha(worktree)
    return head if head and _probes._commit_present(worktree, head, peeled=False) else ""


def _pull_request_reading(gh: GitHubClient, recorded: object) -> _PullRequestReading | None:
    """One whole read of the pull request `recorded` names, or None where it names none, or none was read whole.

    Every member is read inside the one request a failure answers for -- the
    lazy reads behind the pull request included -- and a reading missing its
    head's branch, commit, or repository is no reading: what it cannot say is
    exactly what would tell a pull request that moved from one that did not.
    """
    number = _record_values.as_recorded_number(recorded)
    if number is None:
        return None
    try:
        reading = _read_whole(gh, number)
    except Exception:  # noqa: BLE001 - a pull request nobody could read holds the capture, never invalidates it
        log.warning("PR #%d could not be read to admit a captured completion over it", number)
        return None
    whole = reading.branch and reading.head and reading.repository
    return reading if whole else None


def _read_whole(gh: GitHubClient, number: int) -> _PullRequestReading:
    """The pull request `number`, its state, and its head's branch, commit, and repository, as read now."""
    pull_request = gh.get_pr(number)
    head = getattr(pull_request, "head", None)
    return _PullRequestReading(
        state=gh.pr_state(pull_request),
        branch=getattr(head, "ref", None),
        head=getattr(head, "sha", None),
        repository=getattr(getattr(head, "repo", None), "full_name", None),
    )
