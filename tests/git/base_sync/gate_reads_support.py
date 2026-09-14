# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What the size gate reads when a base refresh is about to push.

A refresh that rebases onto a base that has moved changes what the branch adds
to it, so its push goes through the same gate every other one does. These
answer the four readings that gate takes -- a provably clean tree, a candidate
this host holds, a base the remote named, and a count -- so a base-sync test
says nothing about size unless it is about size, and one that IS about size
seeds exactly the reading it is about.
"""
from __future__ import annotations

import contextlib
from unittest.mock import MagicMock, patch

from orchestrator.config import settings as config
from orchestrator.git.measurement import (
    additions as _measurement,
    commits as _measurement_commits,
)
from orchestrator.git.measurement.models import (
    AdditionMeasurement,
    FrozenCommit,
    _BaseObject,
)
from orchestrator.git.verification import status as _worktree_status
from tests.git.base_sync.refresh_test_support import (
    GATE_BASE_SHA,
    GATE_CANDIDATE_SHA,
    _patched,
)

# What the switch, the ceiling, and the count are named as here.
_DECOMPOSE = "DECOMPOSE"
_MAX_ADDED_LINES = "MAX_ADDED_LINES"
_COUNT_ADDED_LINES = "_count_added_lines"

# A ceiling the count below is over, so a measured candidate would be held and
# an unmeasured one goes out.
_CEILING = 5
_PAST_THE_CEILING = 6


@contextlib.contextmanager
def _gate_switched_off(counter):
    """The size gate off, a ceiling a candidate crosses, and a watched count.

    A refresh reaching the gate with `DECOMPOSE=off` is the case these three
    make sayable at once: the ceiling is one the seeded diff would fail, so a
    push that goes out went out unmeasured -- and the counter says so directly
    rather than by the label the reading would have written.
    """
    with (
        patch.object(config, _DECOMPOSE, False),
        patch.object(config, _MAX_ADDED_LINES, _CEILING),
        patch.object(_measurement, _COUNT_ADDED_LINES, counter),
    ):
        yield


def _oversized_count() -> MagicMock:
    """A count nothing switched off should reach, spelled as one that holds."""
    return MagicMock(return_value=AdditionMeasurement(
        base_sha=GATE_BASE_SHA,
        candidate_sha=GATE_CANDIDATE_SHA,
        additions=_PAST_THE_CEILING,
    ))


def _gate_reads(test_case) -> None:
    """Answer every read the size gate takes before a refresh may push.

    Every push onto a pull request the remote already carries is measured
    before it goes out: a provably clean tree, a candidate this host holds, a
    base the remote named, and a count. A refresh test is about the rebase
    rather than the size question, so it gets the ordinary answers, and one
    about the gate itself seeds what it is about. The pull request those reads
    are taken against is seeded beside the issue that has one, so a test whose
    premise is that `gh.get_pr` fails can still say so.
    """
    _patched(test_case, _worktree_status, "_worktree_status", MagicMock(
        return_value=_worktree_status._WorktreeStatus(readable=True),
    ))
    _patched(
        test_case, _measurement_commits, "_prove_candidate_commit",
        MagicMock(return_value=FrozenCommit(sha=GATE_CANDIDATE_SHA)),
    )
    _gate_base_reads(test_case)


def _gate_base_reads(test_case) -> None:
    """The remote half of the same, for a fixture whose git is a real one.

    A repository on disk answers the tree and the candidate for itself, and a
    test about a dirty checkout or a head that moved needs it to. What a real
    fixture cannot answer is the base: reading it goes to the remote, and
    these have no token to reach one with.
    """
    _patched(
        test_case, _measurement_commits, "_freeze_base_commit",
        MagicMock(return_value=FrozenCommit(sha=GATE_BASE_SHA)),
    )
    _patched(
        test_case, _measurement_commits, "_base_object_present",
        MagicMock(return_value=_BaseObject(present=True)),
    )
    _patched(test_case, _measurement, "_count_added_lines", MagicMock(
        return_value=AdditionMeasurement(
            base_sha=GATE_BASE_SHA,
            candidate_sha=GATE_CANDIDATE_SHA,
            additions=1,
        ),
    ))


class _AdvancingCandidate:
    """What the checkout proves to, reading by reading.

    A tick that pushes twice publishes two commits -- the recovered head, and
    the one the rebase behind it rewrote that into -- and telling a second
    push from the receipt of the first is exactly what the gate does with
    them. The last entry answers every reading past it.
    """

    def __init__(self, shas: tuple[str, ...]) -> None:
        self._shas = shas
        self._reads = 0

    def __call__(self, _worktree, _revision) -> FrozenCommit:
        reading = min(self._reads, len(self._shas) - 1)
        self._reads += 1
        return FrozenCommit(sha=self._shas[reading])


def _gate_candidates(test_case, *shas: str) -> None:
    """Advance the commit this checkout proves to across a tick's readings."""
    _patched(
        test_case, _measurement_commits, "_prove_candidate_commit",
        MagicMock(side_effect=_AdvancingCandidate(shas)),
    )
