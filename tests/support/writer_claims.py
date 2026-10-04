# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Issue writer claims held the way another poller on this host holds them.

A second open file description on an issue's claim file, which `flock` treats
exactly as it treats another process's: nothing in this interpreter's own
bookkeeping knows about it. It leaves on the file what another poller's hold
leaves -- a holder token that is not this process's, the retirement it noted
where a case says it was retiring a cycle, and the moment it let go -- so the
next acquisition here finds another poller's hold and when it ended, and a
contender finds the note. The claim owner's tests prove the same refusal
across real processes; a caller here asks what its own path does with it.
"""
from __future__ import annotations

import contextlib
import fcntl
from collections.abc import Iterator
from pathlib import Path
from unittest.mock import patch

from orchestrator.scheduler import claim_notes, writer_claims

# The token the other poller's holds are signed with.
_OTHER_POLLER = "other-poller"

_ENCODING = "utf-8"


@contextlib.contextmanager
def held_elsewhere(repo_id: int, *issue_numbers: int, retiring: int | None = None) -> Iterator[None]:
    """Hold these issues' writer claims for the block, as another poller would.

    `repo_id` is the repository's numeric id -- the client's `repo_id` --
    since that, and no name the repository goes by, is the key. `retiring`
    is a late cycle the holds say they are retiring, as a poller inside a
    retirement window notes it.
    """
    with contextlib.ExitStack() as holding:
        for issue_number in issue_numbers:
            claim_path = writer_claims.claim_path(repo_id, issue_number)
            claim_path.parent.mkdir(parents=True, exist_ok=True)
            claim_file = holding.enter_context(claim_path.open("a", encoding=_ENCODING))
            fcntl.flock(claim_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
            holding.callback(fcntl.flock, claim_file, fcntl.LOCK_UN)
            holding.callback(_released, claim_path)
            signed_by_another_poller(repo_id, issue_number, retiring=retiring, released=False)
        yield


def signed_by_another_poller(
    repo_id: int, issue_number: int, *, retiring: int | None = None, released: bool = True,
) -> None:
    """Leave on an issue's claim file what another poller's hold of it leaves.

    Every write another poller makes to the issue is made under its claim, so
    a case that writes the issue as that poller would signs the claim too, at
    the point its writes are over; the next acquisition here then finds that
    poller's hold, ended as of the call, as it would. `released=False` leaves
    the hold unfinished, for a holder that stamps its release as it lets go.
    """
    noted = "" if retiring is None else f"{claim_notes._RETIRING}{retiring}\n"
    claim_path = writer_claims.claim_path(repo_id, issue_number)
    claim_path.parent.mkdir(parents=True, exist_ok=True)
    claim_path.write_text(f"{writer_claims.HOLDER_LINE}{_OTHER_POLLER}\n{noted}", encoding=_ENCODING)
    if released:
        _released(claim_path)


def _released(claim_path: Path) -> None:
    """Stamp the moment the other poller's hold let go, as its last act under it."""
    with claim_path.open("a", encoding=_ENCODING) as claim_file:
        claim_file.write(f"{writer_claims.RELEASED_LINE}{claim_notes.moment()}\n")


@contextlib.contextmanager
def claimed_on_creation(client) -> Iterator[None]:
    """Every child `client` creates is held elsewhere from the moment it exists.

    What a second poller does whose own poll reaches a child before the split
    that created it has seeded it: the child is dispatchable as soon as the
    create returns, so its claim is taken in that same breath.
    """
    with contextlib.ExitStack() as holding:
        claiming = _ClaimingCreates(client, holding)
        with patch.object(client, "create_child_issue", claiming):
            yield


class _ClaimingCreates:
    """A child create that hands the new issue's claim to another poller."""

    def __init__(self, client, holding: contextlib.ExitStack) -> None:
        self._client = client
        self._create = client.create_child_issue
        self._holding = holding

    def __call__(self, **fields):
        """Create the child, then hold its claim as the other poller would."""
        child = self._create(**fields)
        self._holding.enter_context(held_elsewhere(self._client.repo_id, child.number))
        return child


def claimable(repo_id: int, issue_number: int) -> bool:
    """Whether a writer could take this issue right now."""
    with writer_claims.issue_writer(repo_id, issue_number) as held:
        return held
