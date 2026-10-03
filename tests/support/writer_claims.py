# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Issue writer claims held the way another poller on this host holds them.

A second open file description on an issue's claim file, which `flock` treats
exactly as it treats another process's: nothing in this interpreter's own
bookkeeping knows about it. The claim owner's tests prove the same refusal
across real processes; a caller here asks what its own path does with it.
"""
from __future__ import annotations

import contextlib
import fcntl
import tempfile
from collections.abc import Iterator
from pathlib import Path
from unittest.mock import patch

from orchestrator.scheduler import writer_claims


@contextlib.contextmanager
def held_elsewhere(repo_id: int, *issue_numbers: int) -> Iterator[None]:
    """Hold these issues' writer claims for the block, as another poller would.

    `repo_id` is the repository's numeric id -- the client's `repo_id` --
    since that, and no name the repository goes by, is the key.
    """
    with contextlib.ExitStack() as holding:
        for issue_number in issue_numbers:
            claim_path = writer_claims.claim_path(repo_id, issue_number)
            claim_path.parent.mkdir(parents=True, exist_ok=True)
            claim_file = holding.enter_context(claim_path.open("a", encoding="utf-8"))
            fcntl.flock(claim_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
            holding.callback(fcntl.flock, claim_file, fcntl.LOCK_UN)
        yield


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


@contextlib.contextmanager
def unusable_namespace() -> Iterator[None]:
    """A claim namespace nothing can be opened in: a file where the directory belongs."""
    with tempfile.TemporaryDirectory() as root:
        blocked = Path(root) / "namespace"
        blocked.write_text("", encoding="utf-8")
        with patch.object(writer_claims, "_namespace", return_value=blocked):
            yield


def claimable(repo_id: int, issue_number: int) -> bool:
    """Whether a writer could take this issue right now."""
    with writer_claims.issue_writer(repo_id, issue_number) as held:
        return held
