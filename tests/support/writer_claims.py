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
from collections.abc import Iterator

from orchestrator.scheduler import writer_claims


@contextlib.contextmanager
def held_elsewhere(repo_slug: str, *issue_numbers: int) -> Iterator[None]:
    """Hold these issues' writer claims for the block, as another poller would."""
    with contextlib.ExitStack() as holding:
        for issue_number in issue_numbers:
            claim_path = writer_claims.claim_path(repo_slug, issue_number)
            claim_path.parent.mkdir(parents=True, exist_ok=True)
            claim_file = holding.enter_context(claim_path.open("a", encoding="utf-8"))
            fcntl.flock(claim_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
            holding.callback(fcntl.flock, claim_file, fcntl.LOCK_UN)
        yield


def claimable(repo_slug: str, issue_number: int) -> bool:
    """Whether another poller could take this issue right now."""
    with writer_claims.issue_writer(repo_slug, issue_number) as held:
        return held
