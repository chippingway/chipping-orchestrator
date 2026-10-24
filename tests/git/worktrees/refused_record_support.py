# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Finished issues on a real host whose pinned records are real comments.

Three issues closed on `done`, each with a branch the base already carries,
published on the remote, and a checkout on it left alone past the quiet
period -- everything a maintenance pass needs to reclaim them. What tells them
apart is the record on each thread: one pinned under a version admission
refuses, one under the supported version, and one with nothing pinned at all.
Each record names its branch and a pull request that has ended, so read as
current none of them keeps anything.

Each record is the pinned comment itself, posted on the issue's thread by the
account the token belongs to and spelled as the writer spells one, and the
client reads and writes it through the production pinned-state reader and
writers rather than the double's own store: admission refuses or takes it from
the comment's bytes, as a deployed poller's would.

Everything a pass could change can be read back whole: each checkout's files
and HEAD, each branch on the host and on the remote, and every thread byte for
byte with the issue's labels and state and every pull request's.
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from orchestrator.git.worktrees import paths as _paths
from orchestrator.github.pinned_state import (
    SCHEMA_VERSION_KEY,
    SUPPORTED_SCHEMA_VERSION,
    GitHubStateMixin,
    pinned_state_body,
)
from tests.git.worktrees import maintenance_host as _maintenance_host
from tests.git.worktrees.artifact_test_support import WIDGET_SLUG, _namespaced_branch
from tests.git.worktrees.candidate_refs import _branch_at
from tests.git.worktrees.eligibility_test_support import ISSUE_NUMBER, _pull_request, _terminal_issue
from tests.support.git import _run_git

# The record admission refuses, the one it takes, and the issue that pinned none.
REFUSED = ISSUE_NUMBER
ADMITTED = ISSUE_NUMBER + 1
UNPINNED = ISSUE_NUMBER + 2
FINISHED = (REFUSED, ADMITTED, UNPINNED)

# What `standing` reads for an issue whose checkout and branches are all gone.
GONE = (None, None, None)

# A later build's version, which is what the refused record carries unless a
# case pins another.
REFUSED_VERSION = SUPPORTED_SCHEMA_VERSION + 1

# What the pass says it does with a refused record.
KEPT = "keeping every checkout and branch of the issue"

# The client's pinned-state roads taken from the production client: the
# reader, the whole-state writer, and the two requests the strict edit makes.
_PRODUCTION_PINNED_ROADS = ("read_pinned_state", "write_pinned_state", "_pinned_comment", "_send_pinned_edit")

_PR_OFFSET = 100

_BRANCH_KEY = "branch"


class FinishedIssues:
    """The three issues, their artifacts, and the records on their threads.

    Built on a maintenance host case, whose own issue is the refused one and
    whose client every issue here is added to.
    """

    def __init__(self, case) -> None:
        self._case = case
        self._github = case.gh
        for road in _PRODUCTION_PINNED_ROADS:
            production = getattr(GitHubStateMixin, road)
            case.enterContext(patch.object(type(self._github), road, production))
        self._pins: dict = {}
        self._found: dict = {}
        tip = case.landed()
        for number in FINISHED:
            self._finished(number, tip)
        self.pin(REFUSED, REFUSED_VERSION)
        self.pin(ADMITTED, SUPPORTED_SCHEMA_VERSION)

    def pin(self, number: int, version: object) -> None:
        """Pin issue `number`'s record under `version`, or under no version at all where it is None."""
        stamped = {} if version is None else {SCHEMA_VERSION_KEY: version}
        recorded = {_BRANCH_KEY: _namespaced_branch(WIDGET_SLUG, number), "pr_number": _PR_OFFSET + number}
        self.post(number, pinned_state_body({**recorded, **stamped}))
        self._found[number] = version

    def post(self, number: int, body: str) -> None:
        """Put `body` on issue `number`'s thread as its pinned comment, editing the one posted before in place.

        A body posted here is no record a version can be read off, until `pin`
        says which one it carries.
        """
        pinned = self._pins.get(number)
        if pinned is None:
            self._pins[number] = self._github.get_issue(number).create_comment(body)
        else:
            pinned.edit(body)
        self._found[number] = None

    def standing(self) -> dict:
        """Each issue's checkout files and HEAD, or None where it is gone, and its branch on the host and remote."""
        return {
            number: (
                _checkout(_paths._worktree_path(self._case.spec, number)),
                _tip(self._case.clone, _namespaced_branch(WIDGET_SLUG, number)),
                _tip(self._case.world.remote, _namespaced_branch(WIDGET_SLUG, number)),
            )
            for number in FINISHED
        }

    def on_github(self) -> dict:
        """Each thread byte for byte with its issue's labels and state, and every pull request's state."""
        threads = {
            number: (
                [(comment.id, comment.body) for comment in self._github.get_issue(number).comments],
                sorted(label.name for label in self._github.get_issue(number).labels),
                self._github.get_issue(number).closed,
            )
            for number in FINISHED
        }
        held = self._github.pulls.values()
        pulls = sorted((pull.number, pull.state, pull.merged) for pull in held)
        return {"threads": threads, "pull requests": pulls, "deleted branches": self._github.deleted_remote_branches}

    def said(self, output: list[str]) -> int:
        """How many warnings name the refused issue's record, the version it carries, and what was done with it."""
        slug = self._github.repo_slug
        comment_id = self._pins[REFUSED].id
        version = self._found[REFUSED]
        wanted = (
            f"repo={slug} issue=#{REFUSED} pinned comment #{comment_id}",
            f"found schema_version {version!r}, supported {SUPPORTED_SCHEMA_VERSION}",
            KEPT,
        )
        return sum(all(part in line for part in wanted) for line in output)

    def _finished(self, number: int, tip: str) -> None:
        """Close issue `number` on `done` with a branch at `tip` on both hosts, a settled checkout, and an ended PR.

        The refused issue is the case's own, already on the client with its
        branch published, so only its checkout and pull request are added.
        """
        branch = _namespaced_branch(WIDGET_SLUG, number)
        if number != REFUSED:
            self._github.add_issue(_terminal_issue(number))
            _branch_at(self._case.clone, branch, tip)
            self._case.world.publish(self._case.clone, branch, tip)
        checkout = self._case.world.attached_checkout(self._case.spec, number, branch)
        _maintenance_host._settle(checkout)
        self._github.add_pr(_pull_request(_PR_OFFSET + number, branch, tip))


def _checkout(worktree: Path) -> tuple[dict[str, bytes], str] | None:
    """Every file in the checkout, git's own pointer file aside, and its HEAD, or None where it is gone."""
    if not worktree.exists():
        return None
    files = {
        str(path.relative_to(worktree)): path.read_bytes()
        for path in sorted(worktree.rglob("*"))
        if path.is_file() and path.name != ".git"
    }
    return files, _run_git("rev-parse", "HEAD", cwd=worktree).stdout.strip()


def _tip(repository: Path, branch: str) -> str | None:
    """The commit `branch` names in `repository`, or None where it has no such branch."""
    listed = _run_git("for-each-ref", "--format=%(objectname)", f"refs/heads/{branch}", cwd=repository)
    return listed.stdout.strip() or None
