# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The families the claimed child-write cases drive, and a write that fails under a claim.

Every family write here is made inside `child_claims.claiming()`, the entry
point no production path enters yet, so each case reaches the claim-aware
operation directly rather than through a tick.
"""
from __future__ import annotations

from orchestrator.workflow.stages.decomposition import (
    activation as _activation,
    child_claims as _child_claims,
    parents as _parents,
)
from tests.support.fakes import FakeGitHubClient, FakeIssue, FakePR, FakePRRef, make_issue
from tests.support.writer_claims import claimable
from tests.workflow.fixtures import _TEST_SPEC, LABEL_BLOCKED, LABEL_READY, LABEL_VALIDATING
from tests.workflow.value_helpers import _issue_branch

WORKFLOW_LOG = "orchestrator.workflow"

PARENT = 90
CHILDREN = (901, 902)

# What a walk nothing holds back leaves: every child released, in order.
RELEASED = tuple((number, LABEL_READY) for number in CHILDREN)

MERGED_PARENT = 95
MERGED_CHILD = 951
_MERGED_PR = 9510


def blocked_family(gh: FakeGitHubClient | None = None) -> tuple[FakeGitHubClient, FakeIssue]:
    """A `blocked` parent whose two `blocked` children depend on nothing."""
    gh = gh or FakeGitHubClient()
    parent = make_issue(PARENT, label=LABEL_BLOCKED)
    gh.add_issue(parent)
    for number in CHILDREN:
        gh.add_issue(make_issue(number, label=LABEL_BLOCKED))
        gh.seed_state(number, parent_number=PARENT)
    gh.seed_state(PARENT, children=list(CHILDREN))
    return gh, parent


def walked(gh: FakeGitHubClient, parent: FakeIssue, scan=None) -> list:
    """One claimed release walk, off `scan` or a scan read now, answering what it held."""
    scan = scan or _parents._read_child_labels(gh, parent, list(CHILDREN))
    with _child_claims.claiming():
        return _activation._activate_ready_children(gh, _TEST_SPEC, parent, gh.read_pinned_state(parent), scan)


def blocked_on_a_merged_child() -> tuple[FakeGitHubClient, FakeIssue]:
    """A `blocked` parent whose one child an external merge closed on `validating`."""
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
    gh.seed_state(MERGED_CHILD, pr_number=_MERGED_PR, parent_number=MERGED_PARENT)
    gh.seed_state(MERGED_PARENT, children=[MERGED_CHILD])
    return gh, parent


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
