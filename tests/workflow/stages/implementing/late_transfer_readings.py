# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Controlled Git proofs, contribution readings, and line counts for rewrite transfers."""
from __future__ import annotations

from orchestrator.git.measurement.models import (
    AdditionMeasurement,
    ContributionFingerprint,
    FingerprintFailure,
    FrozenCommit,
    MeasurementFailure,
    _BaseObject,
)
from orchestrator.git.verification.status import _WorktreeStatus
from tests.workflow.git_owners import seam_patch
from tests.workflow.stages.implementing import late_transfer_payloads as _transfer_payloads


def _over(base_sha: str) -> str:
    """The digest a pair read over this base contributes, unseeded.

    One answer for the merge base the rewrite really sits on and another for
    every other end, since a contribution is what a candidate adds over ITS
    base and two bases are two contributions.
    """
    return (
        _transfer_payloads.ACCEPTED_DIGEST
        if base_sha == _transfer_payloads.MERGE_BASE_SHA
        else _transfer_payloads.OTHER_DIGEST
    )


class Readings:
    """The readings a permit spends, and what each answers this case.

    One controller installed once rather than a patch per case, because the
    refusals are a family: every one of them is the ordinary world with a
    single reading replaced, and a case that re-entered the whole patch set to
    move one of them would stack doubles over doubles.

    The fingerprints are keyed on the CANDIDATE rather than seeded as a
    sequence, so a case naming one side says which side it means: the accepted
    contribution and the rewritten one are read in order, and a positional
    seed would silently swap them if that order ever changed.

    What a case seeds nothing for still depends on the BASE, because that is
    what a contribution is: only the merge base both sides of this rewrite are
    read over answers with the digest the adjudication recorded, and any other
    end answers with a different one. Without that a hand-edited base would
    fingerprint identically to the frozen one and every reading of it would
    agree by construction.

    The base branch is a reading of its own and is kept apart from the
    digests, because it answers the question no digest can: which commits the
    branch a rewrite claims to sit over really carries. `carried` is that
    branch's history as far as this domain asks about it, and the merge base
    the rewrite is read over is on it unless a case takes it off.

    `absent` is the other half of the ordinary world being ordinary: every
    commit the evidence names is an object this host holds unless a case says
    otherwise.
    """

    def __init__(self) -> None:
        self.head = FrozenCommit(sha=_transfer_payloads.REWRITTEN_SHA)
        self.tree = _transfer_payloads.CLEAN
        self.digests: dict = {}
        self.absent: set = set()
        self.base = FrozenCommit(sha=_transfer_payloads.BASE_TIP_SHA)
        self.carried: set = {_transfer_payloads.MERGE_BASE_SHA, _transfer_payloads.BASE_TIP_SHA}

    def stands_on(self, head) -> None:
        """Put the checkout on this commit, or on this failed proof."""
        self.head = head if isinstance(head, FrozenCommit) else FrozenCommit(
            sha=head,
        )

    def proved(self, worktree, revision) -> FrozenCommit:
        """What one revision the permit names proves to.

        Two answers behind one seam, because the permit asks it two different
        questions: what the checkout stands on, and whether a commit the
        EVIDENCE names is an object this host still holds. A revision a case
        put in `absent` answers the way one made on another host does -- it
        resolves to itself and will not peel -- which is the whole reason a
        whole-looking id is not proof of anything.
        """
        if revision == _transfer_payloads._HEAD:
            return self.head
        if revision in self.absent:
            return FrozenCommit(
                sha=revision, failure=MeasurementFailure.CANDIDATE_ABSENT,
            )
        return FrozenCommit(sha=revision)

    def status(self, worktree) -> _WorktreeStatus:
        """What `git status` said about the tree a push would publish from."""
        return self.tree

    def frozen_base(self, spec, worktree) -> FrozenCommit:
        """What the remote says this repository's base branch is at."""
        return self.base

    def carries(self, worktree, ancestor: str, revision: str) -> bool:
        """Whether the base branch's tip really reaches this commit.

        Asked of the tip this case froze and of nothing else, so a permit that
        reached for some other revision would answer False rather than being
        waved through by a probe that agrees with everything.
        """
        return revision == self.base.sha and ancestor in self.carried

    def fingerprint(
        self, worktree, base_sha: str, candidate_sha: str,
    ) -> ContributionFingerprint:
        """What one pair contributes, as the digest naming it."""
        answered = self.digests.get(candidate_sha) or _over(base_sha)
        if isinstance(answered, FingerprintFailure):
            return ContributionFingerprint(
                base_sha=base_sha, candidate_sha=candidate_sha,
                failure=answered,
            )
        return ContributionFingerprint(
            base_sha=base_sha, candidate_sha=candidate_sha, digest=answered,
        )


def readings(fixture) -> Readings:
    """Install the ordinary world a transfer is granted in, and hand it back.

    The checkout stands on the rewritten commit over a provably clean tree,
    the base branch the remote names carries the merge base the rewrite sits
    over, and both contributions fingerprint to the digest the adjudication
    recorded -- so a case that touches nothing is a permit and a case about a
    refusal moves exactly one answer.
    """
    answers = Readings()
    fixture.enterContext(seam_patch(_transfer_payloads.PROVE_CANDIDATE, answers.proved))
    fixture.enterContext(seam_patch(_transfer_payloads.WORKTREE_STATUS, answers.status))
    fixture.enterContext(seam_patch(_transfer_payloads.FREEZE_BASE, answers.frozen_base))
    fixture.enterContext(seam_patch(_transfer_payloads.COMMIT_CONTAINS, answers.carries))
    fixture.enterContext(seam_patch(_transfer_payloads.FINGERPRINT, answers.fingerprint))
    return answers


def measures(fixture, additions: int = _transfer_payloads.UNDER_THE_CEILING) -> None:
    """Let the ordinary cumulative reading run, and come back this size.

    What a case about a REFUSED permit needs and no other case here does: the
    refusal is not a hold, so the rewritten commit falls through to the
    measurement, and only a count under the ceiling reaches the push whose
    receipt the settlement rides.

    The base the count is taken over is the one `readings` already froze, so
    the measurement and the permit are answered about the same base branch.
    """
    fixture.enterContext(seam_patch(
        _transfer_payloads.BASE_PRESENT,
        lambda spec, worktree, base_sha: _BaseObject(present=True),
    ))
    fixture.enterContext(seam_patch(
        _transfer_payloads.COUNT_ADDED_LINES,
        lambda worktree, base_sha, candidate_sha: AdditionMeasurement(
            base_sha=base_sha,
            candidate_sha=candidate_sha,
            additions=additions,
        ),
    ))
