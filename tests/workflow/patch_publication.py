# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Publication and fetch result adapters for hermetic workflow runs."""
from __future__ import annotations

from unittest.mock import MagicMock

from orchestrator.git.publication import models as _publication_models

# The push seam, and the commit one call carried, as the hermetic mock table
# spells them.
_PUSH_BRANCH = "_push_branch"
_REVISION = "revision"


def _published_branch(push) -> MagicMock:
    """The push seam, recording its calls whichever seed drives it.

    A callable becomes the side effect rather than the mock, so a scenario
    that moves the pull request under its own push still answers `call_count`
    and `call_args` the way every other seam here does.
    """
    if callable(push):
        return MagicMock(side_effect=push)
    return MagicMock(return_value=bool(push))


def _squashed(seed) -> MagicMock:
    """The squash seam, recording its calls whichever seed drives it.

    A callable becomes the side effect rather than the answer, which is what a
    case about a HELD candidate needs: the gate parks in memory and leaves the
    flags for its caller to persist, so the double has to mutate the state the
    same way before it reports the hold. A record is taken as itself, and a
    tuple is the historical `(success, sha, count, error)` shape every other
    case here was written in, widened to the same record.
    """
    if callable(seed):
        return MagicMock(side_effect=seed)
    return MagicMock(return_value=_squash_outcome(seed))


def _squash_outcome(seed) -> _publication_models._SquashOutcome:
    """One squash outcome, from either spelling of the seed."""
    if isinstance(seed, _publication_models._SquashOutcome):
        return seed
    success, sha, count, error = seed
    return _publication_models._SquashOutcome(
        success=success, sha=sha, count=count, error=error,
    )


def _fetched(seed) -> MagicMock:
    """The fetch seam, answering once or a reading at a time.

    A sequence is a tick whose two fetches differ -- the pull request's branch
    lands and the base does not -- which is the only way the second refusal is
    reached at all.
    """
    if isinstance(seed, (list, tuple)):
        return MagicMock(side_effect=list(seed))
    return MagicMock(return_value=seed)


def _stand_opened_prs_on_the_push(github, mocks, opened_before: int) -> None:
    """Put a pull request this tick opened on the commit it was pushed.

    What the double cannot derive: the push is mocked, so `open_pr` has no way
    to know which commit the branch it is opened over now carries, while
    GitHub answers with that commit from the moment the pull request exists.
    The poll after a publication reads that head to tell one this issue made
    from a branch somebody else moved -- so a fixture that left it at its
    default would have every such reading refuse a publication this very tick
    produced, and a case asserting on the next poll would be asserting on a
    remote no tick could have left.

    The sha alone: the ref and the repository are what `open_pr` already
    answered with, and replacing the whole head would drop the two facts every
    publication reading is identified by.
    """
    pushed = mocks[_PUSH_BRANCH].call_args
    if pushed is None:
        return
    revision = pushed.kwargs.get(_REVISION)
    if not revision:
        return
    for opened in github.opened_prs[opened_before:]:
        opened.head.sha = revision
