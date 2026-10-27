# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The records one squash scenario is seeded and reported by.

A squash-on-approval force-pushes onto a pull request the remote already
carries, so the size gate is entered on that publication first: readable,
open, standing on the head this stage read, over a provably clean tree, and
under the ceiling once the squashed commit is measured against the frozen
base. A scenario about the rewrite therefore has to give it one to be entered
on, and a scenario about the refusals moves or closes the pull request it
seeds here.

`_InterruptsTheRewrite` is how a case puts one of those refusals in the one
window that is not seeded: the step between the two entry readings, where the
first has already answered over an intact branch and the second has still to
be taken over the commit the squash just made.

`SquashRun` is the other end: what the squash decided, beside the push seam
that recorded whether anything went out and under what name.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from unittest import mock

from orchestrator.git.measurement import commits as _measurement_commits
from orchestrator.git.measurement.models import FrozenCommit
from orchestrator.git.publication import models, rewrite as _rewrite
from orchestrator.git.verification import probes as _verification_probes
from orchestrator.workflow.stages.implementing import (
    late_records as _late_records,
)
from tests.git.publication.publication_helpers import _spec
from tests.support.fakes import (
    FakeGitHubClient,
    FakeLabel,
    FakePR,
    FakePRRef,
)

# The stage the squash runs in. It has an edge to the adjudication, which is
# what the gate asks of whatever stage it is taking an issue out of.
SQUASH_LABEL = "workflow:validating"

SQUASH_PR_NUMBER = 77

BASE_BRANCH_NAME = "main"

REMOTE_NAME = "origin"

OPEN = "open"

# The two readings a case can drive: the head the squash names, and the proof
# the gate takes of the checkout it would publish from.
HEAD_SHA_HELPER = "_head_sha"
PROVE_CANDIDATE_HELPER = "_prove_candidate_commit"

CLOSED = "closed"

MERGED = "merged"

# A head somebody else pushed while the rewrite was running. Closing a pull
# request does not move its branch and moving one does not close it, so the
# second entry read is the only thing that catches either.
MOVED_HEAD = "cafe1234" * 5

# A file the topic branch the repository fixture seeds already tracks, and
# what somebody writes into it while the rewrite is running: a `--hard` reset
# would take that edit with it.
TRACKED_FILE = "f1.txt"

TRACKED_EDIT = "kept across the restore\n"


@dataclass(frozen=True)
class SquashRun:
    """One squash outcome, with the push seam that recorded what went out."""

    outcome: models._SquashOutcome
    push_mock: mock.MagicMock

    @property
    def success(self) -> bool:
        return self.outcome.success

    @property
    def sha(self) -> str | None:
        return self.outcome.sha

    @property
    def count(self) -> int:
        return self.outcome.count

    @property
    def error(self) -> str | None:
        return self.outcome.error

    @property
    def held(self) -> bool:
        return self.outcome.held

    @property
    def standing(self) -> str:
        """Which of the three places this failure left the branch in."""
        return self.outcome.standing


@dataclass(frozen=True)
class PublicationSeed:
    """What the pull request a squash would rewrite looks like this tick.

    The defaults are the only shape a squash may be entered on: an open pull
    request the client holds, standing on the head this stage read before it
    rewrote anything. A case about a refusal moves, closes, or unseeds it.
    """

    issue: Any = None
    head: str = ""
    state: str = OPEN
    # The number the pinned comment records, where a case wants one nothing
    # put on the client -- which is what a lookup that fails reads as.
    pinned_number: int = 0
    # A subject built ahead of the run, for a case that reads the pinned
    # comment or the label history back afterwards: a held candidate writes
    # both, and a subject the runner builds for itself is one the case has no
    # way to reach.
    gate: Any = None


class _InterruptsTheRewrite:
    """What arrives between the squash commit and the gate's own reading.

    Hung on the squash commit rather than on a call count, because that is
    exactly the step between the two entry readings: the first answered while
    the branch was intact, and the second is taken once this has run. The
    pull request can be settled or moved in it, and the WORKTREE can be
    written to -- a tracked edit is the gate's first refusal, and the only
    one whose repair a `--hard` reset would throw away.
    """

    def __init__(
        self, pull_request, *, state=None, head=None, writes=None,
    ) -> None:
        self._pull_request = pull_request
        self._state = state
        self._head = head
        self._writes = writes
        # Bound before the seam is replaced, so making the commit does not
        # re-enter the double standing in for it.
        self._commits = _rewrite._create_squash_commit

    def __call__(self, worktree, message):
        made = self._commits(worktree, message)
        if self._state is not None:
            self._pull_request.state = self._state
        if self._head is not None:
            self._pull_request.head.sha = self._head
        if self._writes is not None:
            (worktree / TRACKED_FILE).write_text(self._writes)
        return made


def _gate_base_read(fixture) -> None:
    """Answer the one reading a real repository cannot take for itself.

    The squashed commit is measured before it is published, and freezing the
    base goes to the REMOTE: these fixtures build a real bare repository but
    have no token to reach one through. Everything else in that reading is
    real -- the tree, the commit the checkout proves to, the object store the
    base is looked for in, and the three-dot diff between the two -- so a case
    about the size is about the size of an actual squash.
    """
    fixture.enterContext(mock.patch.object(
        _measurement_commits,
        "_freeze_base_commit",
        mock.MagicMock(return_value=FrozenCommit(sha=fixture._base_sha())),
    ))


def _driven_reads(fixture, *, head_reads=None, proved_heads=None) -> None:
    """Let a case drive the two readings the squash and the gate each take.

    Both are real against a real repository unless a case says otherwise. One
    about the window between the squash reading its own head and the gate
    proving that checkout for itself has to drive them, since the window only
    exists between two readings of the same worktree.
    """
    if head_reads is not None:
        fixture.enterContext(mock.patch.object(
            _verification_probes, HEAD_SHA_HELPER,
            mock.MagicMock(side_effect=head_reads),
        ))
    if proved_heads is not None:
        fixture.enterContext(mock.patch.object(
            _measurement_commits, PROVE_CANDIDATE_HELPER,
            mock.MagicMock(side_effect=proved_heads),
        ))


def _squash_gate(fixture, seed: PublicationSeed):
    """The subject the size gate is entered on for one squash.

    The pull request stands on the pre-squash head by default, which is what
    the rewrite leases its force-push against: the gate compares the two
    readings of that one fact and refuses a squash over a publication that
    moved -- or one a human closed while the review ran, which no lease would
    catch, since closing a pull request does not move its branch.

    A subject the case built for itself is handed straight back, so the client
    it wrote through is the one the case reads its labels and pinned comment
    off afterwards.
    """
    if seed.gate is not None:
        return seed.gate
    issue = seed.issue or fixture._make_issue()
    _gate_base_read(fixture)
    github = FakeGitHubClient()
    # Seeded on the issue rather than written through the client, because the
    # relabel that put it there happened long before this tick: a write from
    # nothing would be the illegal transition the guard refuses.
    issue.labels.append(FakeLabel(SQUASH_LABEL))
    github.add_issue(issue)
    github.add_pr(FakePR(
        number=SQUASH_PR_NUMBER,
        head_branch=fixture.branch,
        head=FakePRRef(sha=seed.head or fixture._head_sha()),
        merged=seed.state == MERGED,
        state=CLOSED if seed.state == MERGED else seed.state,
    ))
    github.seed_state(
        issue.number,
        pr_number=seed.pinned_number or SQUASH_PR_NUMBER,
        # Persisted beside the number, as every publication that opens a pull
        # request persists it: a record naming one without the other names no
        # branch the resolver lets live work use, so no tick past the gate
        # could stand on it.
        branch=fixture.branch,
    )
    return _late_records._gate(
        github,
        _spec(base_branch=BASE_BRANCH_NAME, remote_name=REMOTE_NAME),
        issue,
        github.read_pinned_state(issue),
        fixture.work,
    )
