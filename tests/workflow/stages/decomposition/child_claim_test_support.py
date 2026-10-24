# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The families the claimed child-write cases drive, and a write that fails under a claim.

The release cases reach the walk directly rather than through a tick, so one
can hand it a scan read before another poller moved a child or fail one write
under its claim. Any case can have a human edit a child's record the moment its
claim is granted -- which no claim keeps out -- and read back what a child
still carries.
"""
from __future__ import annotations

import contextlib
from collections.abc import Callable, Iterator
from types import MappingProxyType
from unittest.mock import patch

from orchestrator.scheduler import writer_claims
from orchestrator.workflow.stages.decomposition import activation as _activation, parents as _parents
from tests.support.fakes import FakeGitHubClient, FakeIssue, FakePR, FakePRRef, make_issue
from tests.support.writer_claims import claimable
from tests.workflow.fixtures import _TEST_SPEC, LABEL_BLOCKED, LABEL_READY, LABEL_VALIDATING
from tests.workflow.stages.decomposition.late_test_support import generation_state, late_generation
from tests.workflow.value_helpers import _issue_branch

WORKFLOW_LOG = "orchestrator.workflow"

# The versions a pinned record admission refuses carries, by what a reader
# finds on it: none at all, as every record an earlier release wrote, and one
# this build does not admit. Seeded raw, so nothing stamps the first.
UNADMITTED = MappingProxyType({
    "unversioned": MappingProxyType({}),
    "another version": MappingProxyType({"schema_version": 2}),
})

PARENT = 90
CHILDREN = (901, 902)

# What a walk nothing holds back leaves: every child released, in order.
RELEASED = tuple((number, LABEL_READY) for number in CHILDREN)

MERGED_PARENT = 95
MERGED_CHILD = 951
_MERGED_PR = 9510

# What the merged child's record carries: the pull request that merged, and
# the parent that split it off.
MERGED_RECORD = MappingProxyType({"pr_number": _MERGED_PR, "parent_number": MERGED_PARENT})


def blocked_family(
    gh: FakeGitHubClient | None = None, *, registered: bool = False,
) -> tuple[FakeGitHubClient, FakeIssue]:
    """A `blocked` parent whose two `blocked` children depend on nothing.

    `registered` makes them a late split's own register, which its release
    asks no lineage of, and leaves each child genuinely fresh -- no pinned
    record at all -- rather than seeded with its parent link.
    """
    gh = gh or FakeGitHubClient()
    parent = make_issue(PARENT, label=LABEL_BLOCKED)
    gh.add_issue(parent)
    for number in CHILDREN:
        gh.add_issue(make_issue(number, label=LABEL_BLOCKED))
        if not registered:
            gh.seed_state(number, parent_number=PARENT)
    register = generation_state(late_generation().with_split_children(CHILDREN)) if registered else {}
    gh.seed_state(PARENT, children=list(CHILDREN), **register)
    return gh, parent


def walked(gh: FakeGitHubClient, parent: FakeIssue, scan=None) -> list:
    """One release walk, off `scan` or a scan read now, answering what it held."""
    scan = scan or _parents._read_child_labels(gh, parent, list(CHILDREN))
    return _activation._activate_ready_children(gh, _TEST_SPEC, parent, gh.read_pinned_state(parent), scan)


def blocked_on_a_merged_child(*, recorded: bool = True) -> tuple[FakeGitHubClient, FakeIssue]:
    """A `blocked` parent whose one child an external merge closed on `validating`.

    `recorded=False` leaves the child genuinely fresh -- no pinned record at
    all -- so nothing names the pull request that merged.
    """
    gh = FakeGitHubClient()
    parent = make_issue(MERGED_PARENT, label=LABEL_BLOCKED)
    gh.add_issue(parent)
    gh.add_issue(make_issue(MERGED_CHILD, label=LABEL_VALIDATING, closed=True))
    gh.add_pr(FakePR(
        number=_MERGED_PR,
        head_branch=_issue_branch(MERGED_CHILD),
        head=FakePRRef(sha="cafe1234"),
        merged=True,
        state="closed",
    ))
    if recorded:
        gh.seed_state(MERGED_CHILD, **MERGED_RECORD)
    gh.seed_state(MERGED_PARENT, children=[MERGED_CHILD])
    return gh, parent


def said_refused(output: list[str], number: int) -> bool:
    """Whether one warning names this issue's refused pinned comment, its repository, and both versions."""
    return any(
        f"issue=#{number} pinned comment" in line
        and "repo=" in line
        and "found schema_version" in line
        and "supported 1" in line
        for line in output
    )


def standing(gh: FakeGitHubClient, number: int) -> tuple:
    """What one issue carries: its pinned record, its thread, its labels, and whether it is closed."""
    issue = gh.get_issue(number)
    return (
        gh.pinned_data(number),
        [comment.body for comment in issue.comments],
        [label.name for label in issue.labels],
        issue.closed,
    )


class EditedOnClaim:
    """An edit run on each issue the moment its writer claim is granted, as a human's edit no claim keeps out.

    Installed on the claim's owner, so a reading taken before the claim -- a
    scan, or a record read ahead of it -- predates the edit, and only one
    taken behind the claim sees it.
    """

    def __init__(self, edit: Callable[[int], None]) -> None:
        self._edit = edit
        self._take = writer_claims.issue_writer

    def installed(self):
        """Patch the claim owner for the block."""
        return patch.object(writer_claims, "issue_writer", self._granted)

    @contextlib.contextmanager
    def _granted(self, repo_id: int, issue_number: int, **options) -> Iterator[bool]:
        """Take the claim as the owner does, editing the issue once it is held."""
        with self._take(repo_id, issue_number, **options) as held:
            if held:
                self._edit(issue_number)
            yield held


class RefusedWrite:
    """A write refused on every issue but `passing`, which notes first whether another writer could take it.

    Installed over a client's write, so a case reads whether the write was
    made under the issue's claim -- refused to another writer while it ran --
    and that the claim was given back once the write raised.
    """

    def __init__(self, gh: FakeGitHubClient, write, *passing: int) -> None:
        self._gh = gh
        self._write = write
        self._passing = passing
        self.claimable_during: list[bool] = []

    def __call__(self, issue, *written):
        """Land the write on a passing issue; on any other, note its claim and refuse it."""
        if issue.number in self._passing:
            return self._write(issue, *written)
        self.claimable_during.append(claimable(self._gh.repo_id, issue.number))
        raise RuntimeError("write refused")
