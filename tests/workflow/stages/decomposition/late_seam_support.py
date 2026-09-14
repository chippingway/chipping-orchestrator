# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What the world answers a late run's probes with, and how it is held.

The seams a late adjudication would otherwise really reach are a checkout on
disk, a size measurement and a contribution fingerprint that each shell out to
git, and -- on a cleared `split` alone -- a push and a fetch against a real
remote. Every one of them is held, and a case says which answers it is about
by handing one of the two seeds here; what is not asked about is held at the
answer that lets the run proceed, except the measurement, which is held at a
failure because a test that reaches it without saying what it expects has not
decided anything.
"""
from __future__ import annotations

import contextlib
import shutil
from dataclasses import dataclass
from pathlib import Path
from unittest.mock import MagicMock, patch

from orchestrator.git.measurement.models import (
    ContributionFingerprint,
    FingerprintFailure,
    FrozenCommit,
    MeasurementFailure,
    _BaseObject,
)
from orchestrator.git.snapshots import mirrors as _snapshot_mirrors, refs as _snapshot_refs
from orchestrator.git.snapshots.refs import SnapshotOutcome
from orchestrator.git.verification.probes import _WorktreeStatus
from tests.workflow.git_owners import seam_patch
from tests.workflow.stages.decomposition.late_test_support import (
    CANDIDATE_SHA,
    CONTRIBUTION_DIGEST,
    UNASKED_MEASUREMENT,
)

# A checkout path nothing put on disk: what the probe reads once a teardown
# has taken one down.
_ABSENT_CHECKOUT = "/nonexistent/orchestrator-test-checkout"

# The revision a checkout's own head is named by.
_HEAD_REVISION = "HEAD"


@dataclass(frozen=True)
class WorktreeSeed:
    """What the candidate's worktree answers a late run's probes with.

    The defaults are the only shape a verdict may be read on: the checkout is
    there, HEAD is still the frozen candidate, and the tree is provably clean.
    A test about a read-only agent that wrote says otherwise.
    """

    exists: bool = True
    head: str = CANDIDATE_SHA
    readable: bool = True
    dirty: tuple[str, ...] = ()
    # Whether this checkout can show the two commits the record names. Both
    # are proved before the plan PR is held or an agent is started, so a case
    # about a host the branch never reached says so here.
    candidate_object: bool = True
    base_object: bool = True
    # What the contribution between the frozen pair fingerprints to, which a
    # settled `single` records beside the commit it exempts. A
    # `FingerprintFailure` is the reading this store could not answer, which
    # leaves the exemption standing with no identity beside it.
    fingerprint: object = CONTRIBUTION_DIGEST
    # Whether the push a settled post-publication verdict makes lands. A
    # `single` taken over a pull request the remote already carries publishes
    # from the settlement itself -- it is the last tick holding the head the
    # verdict was measured over -- so a case about a lease that refused says
    # so here.
    push: bool = True
    # What the checkout becomes while that push runs. A push is a request and
    # the worktree is writable for the whole of it, so the two reads the
    # settlement takes on the far side can answer differently from the two it
    # took before; empty means nothing touched it and both readings agree.
    head_after_push: str = ""
    dirty_after_push: tuple[str, ...] = ()


@dataclass(frozen=True)
class SnapshotSeed:
    """What the world does to a split: the remote, and the local teardown.

    The defaults are the only shape a split may run under: the ref was written
    and then fetched back and resolved to the frozen candidate, and the
    checkout the superseded branch was on came down. A test about a namespace
    the token cannot write, a ref another commit already occupies, a remote
    that would not serve it back, or a worktree that would not go says
    otherwise.

    `local_gone` sits here rather than beside it because it answers the same
    question the other two do -- what the world outside this process did with
    what the transaction asked of it -- and because the branch obligation is
    settled by all three together.
    """

    create: SnapshotOutcome = SnapshotOutcome.CREATED
    prove: SnapshotOutcome = SnapshotOutcome.PROVEN
    local_gone: bool = True


class LocalTeardown:
    """The local half of a branch reclamation, held and recorded.

    The checkout removal is real where every other seam here is a mock: what
    decides whether a branch obligation is settled is a read of the checkout
    taken AFTER the teardown, so a teardown that changed nothing would leave
    every reclamation reading as refused.

    What it was ASKED is kept beside it, because that is the half no record
    distinguishes: a remote that refused and a local teardown that was never
    attempted leave the same `failed` entry behind, and only one of them
    leaves a superseded checkout for the per-tick base refresh to go on
    merging into.
    """

    def __init__(self, checkout: Path) -> None:
        self.checkout = checkout
        self.issues: list[int] = []
        self.branch_deleted = MagicMock()

    def __call__(self, _spec, issue_number, **_options) -> None:
        self.issues.append(issue_number)
        shutil.rmtree(self.checkout, ignore_errors=True)

    @classmethod
    @contextlib.contextmanager
    def held(cls, *, local_gone: bool = True):
        """Hold the local half of a reclamation and the read behind it.

        A real `git worktree remove` in a unit test is a command against
        whatever directory the configured root happens to name, and the read
        that decides whether it happened would shell out to a clone that is
        not there. What a case says is only the answer: `local_gone=False` is
        the checkout that would not come down.
        """
        with contextlib.ExitStack() as stack:
            stack.enter_context(seam_patch(
                "_worktree_path",
                MagicMock(return_value=Path(_ABSENT_CHECKOUT)),
            ))
            yield cls(Path(_ABSENT_CHECKOUT))._hold(
                stack, local_gone=local_gone,
            )

    @property
    def attempted(self) -> bool:
        """Whether both local surfaces were asked to come down."""
        return bool(self.issues) and self.branch_deleted.called

    def _hold(self, stack, *, local_gone: bool) -> LocalTeardown:
        """Hold this teardown and the read that decides it happened."""
        stack.enter_context(seam_patch("_remove_issue_worktree", self))
        stack.enter_context(
            seam_patch("_delete_local_issue_branch", self.branch_deleted),
        )
        stack.enter_context(seam_patch(
            "_local_branch_present", MagicMock(return_value=not local_gone),
        ))
        return self


# The local half of a reclamation, held for one case. Bound to the holder's
# own entry point so a caller reads one name rather than two.
local_teardown = LocalTeardown.held


class _Checkout:
    """The four reads one checkout answers, on both sides of the push.

    One holder rather than four independent seams, because a case about a
    worktree something wrote to while the push ran states a single fact and
    the reads that answer for it have to flip together -- on the push, and
    not before. The head proof carries two questions rather than one: what
    the checkout's own HEAD is, and whether the commit a record NAMES is an
    object this host still holds.
    """

    def __init__(self, seed: WorktreeSeed) -> None:
        self._seed = seed
        self._pushed = False

    def pushes(self, *_called, **_options) -> bool:
        """Publish the branch, leaving the checkout however the case says."""
        self._pushed = True
        return self._seed.push

    def status(self, _worktree) -> _WorktreeStatus:
        """What `git status` establishes about this checkout right now."""
        dirty = self._seed.dirty
        if self._pushed and self._seed.dirty_after_push:
            dirty = self._seed.dirty_after_push
        return _WorktreeStatus(readable=self._seed.readable, paths=tuple(dirty))

    def fingerprints(
        self, _worktree, base_sha: str, candidate_sha: str,
    ) -> ContributionFingerprint:
        """Which contribution the pair this reading was HANDED carries.

        Named against that pair rather than against the seed, which is what
        lets a case prove the settlement fingerprinted the commits it froze
        rather than whatever the checkout stands on: the record comes back
        naming the two it was asked about, and the identity written from it
        carries them.
        """
        seeded = self._seed.fingerprint
        if isinstance(seeded, FingerprintFailure):
            return ContributionFingerprint(
                base_sha=base_sha,
                candidate_sha=candidate_sha,
                failure=seeded,
            )
        return ContributionFingerprint(
            base_sha=base_sha, candidate_sha=candidate_sha, digest=seeded,
        )

    def proves(self, _worktree, revision: str) -> FrozenCommit:
        """What one revision this checkout names peels to right now."""
        if not self._seed.candidate_object:
            return FrozenCommit(
                failure=MeasurementFailure.CANDIDATE_ABSENT,
            )
        if revision != _HEAD_REVISION:
            return FrozenCommit(sha=CANDIDATE_SHA)
        if self._pushed and self._seed.head_after_push:
            return FrozenCommit(sha=self._seed.head_after_push)
        return FrozenCommit(sha=self._seed.head)


def hold_late_seams(
    stack,
    seed: WorktreeSeed,
    checkout: Path,
    measurement,
    snapshot: SnapshotSeed,
) -> None:
    """Hold every git seam one late run would otherwise really reach.

    The local teardown is held whatever a case is about, because a real `git
    worktree remove` in a unit test is a command against whatever directory
    the configured root happens to name.
    """
    held = {
        "_measure_candidate": measurement or UNASKED_MEASUREMENT,
        "_worktree_path": checkout,
        "_head_sha": seed.head,
        "_base_object_present": _BaseObject(present=seed.base_object),
        "create_snapshot_ref": (snapshot or SnapshotSeed()).create,
        "prove_snapshot_ref": (snapshot or SnapshotSeed()).prove,
    }
    for name, answer in held.items():
        stack.enter_context(seam_patch(name, MagicMock(return_value=answer)))
    reads = _Checkout(seed)
    for name, answer in (
        ("_push_branch", reads.pushes),
        ("_worktree_status", reads.status),
        ("_prove_candidate_commit", reads.proves),
        ("_fingerprint_contribution", reads.fingerprints),
    ):
        stack.enter_context(seam_patch(name, MagicMock(side_effect=answer)))
    LocalTeardown(checkout)._hold(
        stack, local_gone=(snapshot or SnapshotSeed()).local_gone,
    )


@contextlib.contextmanager
def snapshot_seams(snapshot: SnapshotSeed):
    """Hold the remote and the local teardown for one split transaction.

    The subset a transaction driven on its own needs: it never spawns an agent
    and never reads the worktree, so what has to be held is the push, the
    fetch, the teardown that follows them, and the read that decides whether
    that teardown happened. The seed's `local_gone` is the checkout that would
    not come down, which leaves the branch obligation owed.
    """
    with contextlib.ExitStack() as stack:
        stack.enter_context(seam_patch(
            "create_snapshot_ref", MagicMock(return_value=snapshot.create),
        ))
        stack.enter_context(seam_patch(
            "prove_snapshot_ref", MagicMock(return_value=snapshot.prove),
        ))
        stack.enter_context(seam_patch(
            "_worktree_path", MagicMock(return_value=Path(_ABSENT_CHECKOUT)),
        ))
        yield LocalTeardown(Path(_ABSENT_CHECKOUT))._hold(
            stack, local_gone=snapshot.local_gone,
        )


class RecordedDelete:
    """The remote's two answers about a snapshot, and what it was asked.

    `outcome` is what the destructive call returns; `presence` is what the
    read-only ask beside it sees, and they are separate because the pass asks
    the second one exactly where the first must not be spent -- a decision
    already recorded whose consumers are no longer unanimous. The default is
    a ref the remote still holds, which is the reading that deletes nothing.

    `raising` is what the call does instead of answering. A `KeyboardInterrupt`
    is the crash between the call landing and the write that would have
    recorded it -- the delete has happened as far as the remote is concerned,
    and nothing on the issue says so -- while an ordinary exception is the
    transport failing in a way it has no answer for, which a caller that must
    RECORD the attempt may not let escape.
    """

    def __init__(
        self,
        outcome,
        *,
        raising: BaseException | None = None,
        presence=SnapshotOutcome.PRESENT,
        mirror_sha: str = "",
    ) -> None:
        self.outcome = outcome
        self.presence = presence
        # What this host's own copy of the ref is at: the candidate, somebody
        # else's commit, or "" for no copy at all.
        self.mirror_sha = mirror_sha
        self.raising = raising
        # What each call was asked, in the order it was asked: the two the
        # destructive call names, and the refs the read-only ask saw.
        self.refs: list[str] = []
        self.shas: list[str] = []
        self._observed: list[str] = []

    def __call__(self, _spec, _cwd, *, ref: str, sha: str):
        self.refs.append(ref)
        self.shas.append(sha)
        if self.raising is not None:
            raise self.raising
        return self.outcome

    def observe(self, _spec, _cwd, *, ref: str, sha: str):
        """Answer the read-only ask, recording that it was made."""
        self._observed.append(ref)
        return self.presence

    def mirror(self, _spec, _cwd, *, ref: str, sha: str) -> bool:
        """Answer whether this host holds its copy of the ref, at that commit.

        Answered the way the real read answers it, because the question is
        what makes the answer sound: the copy is a ref in the store every
        agent's worktree shares, so what settles it is the commit the copy
        carries rather than the name existing. A copy re-pointed at anything
        but the candidate is the same answer as no copy at all.
        """
        return bool(self.mirror_sha) and self.mirror_sha == sha

    @classmethod
    def absent(cls) -> RecordedDelete:
        """A remote that has already let this ref go, both ways of asking."""
        return cls(SnapshotOutcome.ABSENT, presence=SnapshotOutcome.ABSENT)

    @property
    def observed(self) -> list:
        """The refs the read-only ask was spent on."""
        return list(self._observed)

    @contextlib.contextmanager
    def answering(self):
        """Hold remote answers and local mirror evidence for one walk."""
        with (
            patch.multiple(
                _snapshot_refs,
                delete_snapshot_ref=self,
                observed_snapshot_ref=self.observe,
            ) as patched,
            patch.object(_snapshot_mirrors, "local_snapshot_present", self.mirror),
        ):
            yield patched
