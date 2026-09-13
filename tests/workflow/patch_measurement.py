# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What the two readings of a frozen pair answer, under the hermetic patch set.

The default world is the ordinary one -- a commit this host holds, a base the
remote named, a diff well under any ceiling, and a contribution that
fingerprints -- so a test about publishing says nothing about either reading
and a test about one of them seeds exactly what it is about.
"""
from __future__ import annotations

from collections.abc import Mapping
from unittest.mock import MagicMock

from orchestrator.git.measurement.models import (
    AdditionMeasurement,
    ContributionFingerprint,
    FingerprintFailure,
    FrozenCommit,
    MeasurementFailure,
    _BaseObject,
)
from tests.workflow.patch_models import _WorkflowRunContext
from tests.workflow.repo_values import (
    CONTRIBUTION_DIGEST,
    MEASURED_BASE_SHA,
    MEASURED_CANDIDATE_SHA,
)

# The revision the gate names the checkout's own head by. Every other
# revision it asks about is a commit some record names by id.
_HEAD = "HEAD"


class _CountedAdditions:
    """What the size gate's count reports for one frozen pair.

    Named against the pair it was handed rather than against the seed, so a
    measurement carries the commits the caller froze -- which is what the
    record written from it is then correlated by. A `MeasurementFailure` seed
    is a reading that did not happen and carries no count at all, because
    "unknown" and "small" are the two answers this domain exists to keep
    apart.

    A CALLABLE seed is taken as the reading itself, which is what a case
    about the number rather than about the decision needs: the production
    count, over a real checkout, so what the gate acts on is what git says
    the candidate adds rather than what a test chose to tell it.
    """

    def __init__(self, context: _WorkflowRunContext) -> None:
        self._context = context

    def __call__(self, worktree, base_sha: str, candidate_sha: str):
        counted = self._context.added_lines
        if callable(counted):
            return counted(worktree, base_sha, candidate_sha)
        if isinstance(counted, MeasurementFailure):
            return AdditionMeasurement(
                base_sha=base_sha, candidate_sha=candidate_sha,
                failure=counted,
            )
        return AdditionMeasurement(
            base_sha=base_sha, candidate_sha=candidate_sha, additions=counted,
        )


class _FingerprintedContribution:
    """Which contribution one frozen pair carries, as the digest naming it.

    Named against the pair it is HANDED rather than against the seed, which is
    what lets a case prove a caller fingerprinted the pair it froze rather
    than whatever the checkout stands on now: the record comes back naming the
    two commits it was asked about, and anything written from it carries them.

    A `FingerprintFailure` seed is a reading that did not happen and carries
    no digest at all, because a digest over the empty stdout a failed `git
    diff` writes is one every broken reading in the fleet would agree on.

    A mapping keyed on the CANDIDATE is what a rewrite needs, since the whole
    question a transfer turns on is whether two commits contribute the same
    thing: a case about a replay that moved content seeds the rewritten end
    apart and leaves the accepted one where the adjudication recorded it.

    Built from the seed alone rather than from a run context, since both
    harnesses that hold this seam -- the stage-handler patch set and the late
    adjudication's own -- seed it the same way.
    """

    def __init__(self, seeded) -> None:
        self._seeded = seeded

    def __call__(self, worktree, base_sha: str, candidate_sha: str):
        answered = self._answer(candidate_sha)
        if isinstance(answered, FingerprintFailure):
            return ContributionFingerprint(
                base_sha=base_sha,
                candidate_sha=candidate_sha,
                failure=answered,
            )
        return ContributionFingerprint(
            base_sha=base_sha, candidate_sha=candidate_sha, digest=answered,
        )

    def _answer(self, candidate_sha: str):
        """What this candidate contributes, from either spelling of the seed."""
        if isinstance(self._seeded, Mapping):
            return self._seeded.get(candidate_sha, CONTRIBUTION_DIGEST)
        return self._seeded


class _ProvedCommit:
    """What one revision the size gate names proves to.

    Two answers behind one seam, because the gate asks it two different
    questions: what the checkout's HEAD is, and whether the commit a record
    NAMES is an object this host still holds. A test that seeds neither gets
    the ordinary world -- a head, and a recorded object that is here.
    """

    def __init__(self, context: _WorkflowRunContext) -> None:
        self._context = context
        self._reads = 0

    def __call__(self, worktree, revision: str):
        if revision == _HEAD:
            return self._head()
        return self._context.recorded_commit or FrozenCommit(sha=revision)

    def _head(self):
        """What the checkout's own head proves to, this reading.

        A tuple seeds a head that MOVES between readings -- the gate takes one
        and the publication takes another -- which is the race the handoff
        refuses. Its last entry answers every reading past it, so a caller
        that asks once more than a test counted reads the head the test left
        the checkout on rather than running out of answers.
        """
        seeded = self._context.candidate_commit
        if seeded is None:
            return FrozenCommit(sha=MEASURED_CANDIDATE_SHA)
        if not isinstance(seeded, tuple):
            return seeded
        reading = min(self._reads, len(seeded) - 1)
        self._reads += 1
        return seeded[reading]


def _measurement_mocks(context: _WorkflowRunContext) -> dict[str, object]:
    """The four reads the size gate takes, and the identity of what it read."""
    return {
        "_fingerprint_contribution": MagicMock(
            side_effect=_FingerprintedContribution(
                context.contribution_digest,
            ),
        ),
        "_prove_candidate_commit": MagicMock(side_effect=_ProvedCommit(context)),
        "_freeze_base_commit": MagicMock(
            return_value=context.frozen_base or FrozenCommit(
                sha=MEASURED_BASE_SHA,
            ),
        ),
        "_base_object_present": MagicMock(
            return_value=_BaseObject(present=context.base_object_present),
        ),
        "_count_added_lines": MagicMock(side_effect=_CountedAdditions(context)),
    }
