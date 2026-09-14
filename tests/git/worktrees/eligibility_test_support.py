# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The issue a terminal-artifact classification asks GitHub about.

The remote half of the fixture: an issue in whatever ending a case needs, the
pinned state it recorded, and the pull requests standing on its branches, all
through the in-memory double. The host half -- the clone, its remote, and the
checkouts -- is the ``candidate_host_test_support`` beside it.

The double is used rather than a stub of the client, because what these cases
turn on is which answer a lookup gives: a pull request open on another base,
a recorded number nothing resolves, a commit list GitHub refuses. Each of
those is something the double already models the way the real client does.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from orchestrator import config
from orchestrator.git.worktrees.candidates import IssueArtifacts
from orchestrator.git.worktrees.models import Retention
from tests.git.worktrees.artifact_test_support import BASE_BRANCH
from tests.support.fakes import (
    FakeGitHubClient,
    FakeIssue,
    FakeLabel,
    FakePR,
    FakePRRef,
)

DONE_LABEL = "done"
REJECTED_LABEL = "rejected"
IMPLEMENTING_LABEL = "workflow:implementing"
BACKLOG_LABEL = "backlog"
ISSUE_NUMBER = 314
CLOSED_PR_STATE = "closed"
OPEN_PR_STATE = "open"
# A base no configured repository names, for the cases about a pull request
# somebody retargeted: it is still open on this head branch, and a lookup
# pinned to the configured base would not see it.
OTHER_BASE_BRANCH = "release/2.0"


class _RaisingIssue:
    """An issue whose every field fails the way a lazy PyGithub one does.

    The attributes are what raise rather than the fetch, because that is the
    shape production has: the object comes back from `get_issue` intact and
    goes to GitHub on the first field anybody reads.
    """

    @property
    def state(self) -> str:
        raise RuntimeError("the issue could not be read")

    @property
    def labels(self) -> list:
        raise RuntimeError("the labels could not be read")

    @property
    def number(self) -> int:
        raise RuntimeError("even the number could not be read")


def _terminal_issue(
    issue_number: int = ISSUE_NUMBER,
    *,
    closed: bool = True,
    label_names: tuple[str, ...] = (DONE_LABEL,),
) -> FakeIssue:
    """An issue in the state a candidate's artifacts may be reclaimed from."""
    return FakeIssue(
        number=issue_number,
        closed=closed,
        labels=[FakeLabel(name) for name in label_names],
    )


def _github(
    issue: FakeIssue | None = None, **pinned: Any
) -> FakeGitHubClient:
    """The double, holding one issue and whatever pinned state it recorded."""
    issue = issue or _terminal_issue()
    gh = FakeGitHubClient(issues=(issue,))
    gh.seed_state(issue.number, **pinned)
    return gh


def _pull_request(
    number: int,
    branch: str,
    head_sha: str,
    *,
    state: str = CLOSED_PR_STATE,
    base: str = BASE_BRANCH,
) -> FakePR:
    """One pull request on a branch, standing on a named commit."""
    return FakePR(
        number=number,
        head_branch=branch,
        base_branch=base,
        state=state,
        merged=False,
        head=FakePRRef(sha=head_sha, ref=branch),
    )


def _candidate(
    spec: config.RepoSpec,
    issue_number: int = ISSUE_NUMBER,
    *,
    worktree: Path | None = None,
    worktrees: tuple[Path, ...] | None = None,
    branches: tuple[str, ...] = (),
) -> IssueArtifacts:
    """One entry in the shape the scan hands the classification.

    A single checkout is spelled as one, because that is what all but the
    migration cases hold; `worktrees` is for the case that holds both layouts
    at once and needs to say which is which.
    """
    if worktrees is None:
        worktrees = () if worktree is None else (worktree,)
    return IssueArtifacts(
        spec=spec,
        issue_number=issue_number,
        worktrees=worktrees,
        branches=branches,
    )


def _reasons(retentions: tuple[Retention, ...]) -> tuple[str, ...]:
    """The reasons a candidate is kept for, without the subjects beside them."""
    return tuple(retention.reason for retention in retentions)
