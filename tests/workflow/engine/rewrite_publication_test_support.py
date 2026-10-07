# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Issue #7's clean rebase published through the workflow, and what can move under it before the push.

The refresh fixture the base-sync cases stand on -- issue #7 in review over PR
#42, two commits behind its base, the pull request on the head the refresh
anchors -- with what the git owner reads a candidate off made into a world a
case can move (`RewriteWorld`): the head the checkout proves to, the base the
replay sits over, and PR #42's branch as the remote has it. A push lands on
that branch the way a real one would: refused where its lease is not the head
the pull request stands on, and moving the pull request onto the commit it
names otherwise.

Two moments a case moves that world in (`races_the_reread`,
`races_the_barrier`): as the git owner reads the candidate again for its push,
past the gate's measurement, and as the gate asks whether the publication
ended, past that reading and immediately before the push. The moves
themselves are `rewrite_publication_moves`.
"""
from __future__ import annotations

from dataclasses import replace
from unittest.mock import patch

from orchestrator.git import branch_transport
from orchestrator.git.base_sync import rewrite_facts as _rewrite_facts
from orchestrator.git.measurement import commits as _measurement_commits
from orchestrator.git.measurement.models import FrozenCommit
from orchestrator.git.publication import probes as _publication_probes
from orchestrator.git.ref_transport import _RefRead
from orchestrator.git.verification import probes as _verification_probes
from orchestrator.workflow.stages.implementing import late_publication as _late_publication
from tests.git.base_sync import refresh_test_support as base

ANCHOR = base.BEFORE_SHA
REPLAY = base.AFTER_SHA

# A head nothing in this attempt produced, and a base ref repointed off the tip
# the replay sits over.
FOREIGN = "f0e1a900" * 5
REWOUND_BASE = "0bad0bad" * 5


class RewriteWorld:
    """What the git owner reads a candidate off, as a case moves it.

    `head` is what the checkout proves to; `base_tip` is where the base ref
    stands -- the tip the candidate was read over, one repointed off it, or
    None for a count nobody could take; `answers` is whether the remote answers a
    read at all; `rejects` refuses every push whatever its lease; `answered` is
    what a push that landed tells the tick that made it. `pushes` is every push
    made, as the commit named and the head it was leased against.
    """

    def __init__(self, case) -> None:
        self.head = REPLAY
        self.base_tip: str | None = base.GATE_BASE_SHA
        self.answers = True
        self.rejects = False
        self.answered = True
        self.pushes: list[tuple[str | None, str | None]] = []
        self._case = case
        self._readings: list[str] = []
        self._probe = _publication_probes._branch_divergence
        for owner, name, double in (
            (_measurement_commits, "_prove_candidate_commit", self._proved),
            (_publication_probes, "_branch_divergence", self._counted),
            (_verification_probes, "_commit_contains", self._contains),
            (branch_transport, "_remote_branch_read", self._read),
        ):
            base._patched(case, owner, name, double)

    def push(self, _spec, _worktree, _branch, *, force_with_lease=None, revision=None) -> bool:
        """Land `revision` on PR #42 where the lease is the head it stands on; what the tick is told."""
        self.pushes.append((revision, force_with_lease))
        pull = self._case.gh.pulls[base.PR_NUMBER]
        if self.rejects or force_with_lease != pull.head.sha:
            return False
        pull.head = replace(pull.head, sha=revision)
        return self.answered

    def reads_first(self, *heads: str) -> None:
        """Answer the next remote readings with `heads`, in order, before following PR #42 again."""
        self._readings.extend(heads)

    def _proved(self, _worktree, _revision) -> FrozenCommit:
        return FrozenCommit(sha=self.head)

    def _counted(self, spec, worktree, branch, *revision):
        if branch != spec.base_branch:
            return self._probe(spec, worktree, branch, *revision)
        if self.base_tip is None:
            return _publication_probes._BranchDivergence()
        return _publication_probes._BranchDivergence(tip=self.base_tip, readable=True)

    def _contains(self, _worktree, _ancestor, _revision) -> bool:
        return self.base_tip == base.GATE_BASE_SHA

    def _read(self, _spec, _worktree, _branch) -> _RefRead:
        if not self.answers:
            return _RefRead(detail="the remote did not answer")
        if self._readings:
            return _RefRead(sha=self._readings.pop(0))
        pull = self._case.gh.pulls[base.PR_NUMBER]
        return _RefRead(sha=pull.head.sha)


class _Races:
    """A call that lets `move` move the case's world first, then makes the call it stands in for."""

    def __init__(self, case, move, asked) -> None:
        self._case = case
        self._move = move
        self._asked = asked

    def __call__(self, *args):
        self._move(self._case)
        return self._asked(*args)


def races_the_reread(case, move):
    """Run `move` over `case` as the git owner reads the candidate again for its push."""
    reread = _Races(case, move, _rewrite_facts._rereads_the_candidate)
    return patch.object(_rewrite_facts, "_rereads_the_candidate", reread)


def races_the_barrier(case, move):
    """Run `move` over `case` as the gate asks whether the publication ended, just before the push."""
    barrier = _Races(case, move, _late_publication._publication_ended)
    return patch.object(_late_publication, "_publication_ended", barrier)
