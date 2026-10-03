# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Writer claims another process takes through the claim owner alone.

The other process runs the program below over the shared namespace
`tests/support/writer_claim_processes.py` sets up, keyed by the repository id
it is handed, and asks nothing of a client or a dispatch seam: what these
tests hold up is the claim itself.
"""
from __future__ import annotations

import os
from pathlib import Path

from orchestrator.scheduler import writer_claims
from tests.support import writer_claim_processes as _processes

# The holder program. It reports what the claim answered, then does what its
# mode says with it: holds it until told to let go, raises out of it and
# stays alive, or lets it go at once.
_HOLDER = """
import sys

from orchestrator.scheduler import writer_claims

repo_id, number, mode = int(sys.argv[1]), int(sys.argv[2]), sys.argv[3]
try:
    with writer_claims.issue_writer(repo_id, number) as held:
        print("held" if held else "refused", flush=True)
        if mode == "raise":
            raise RuntimeError("the body failed")
        if mode == "hold":
            sys.stdin.readline()
except RuntimeError:
    print("released", flush=True)
    sys.stdin.readline()
"""


class SharedNamespaceCase(_processes.SharedNamespaceCase):
    """A checkout root of this test's own, claimed in by real processes."""

    def other_process(self, repo_id: int, issue_number: int, mode: str) -> _processes.OtherProcess:
        return self.run_elsewhere(_HOLDER, repo_id, issue_number, mode)

    def granted_here(self, repo_id: int, issue_number: int) -> bool:
        """Whether this process could claim the key right now."""
        with writer_claims.issue_writer(repo_id, issue_number) as held:
            return held


def descriptors_on(path: Path) -> int:
    """How many of this process's descriptors are open on `path`."""
    descriptor_root = Path("/proc/self/fd")
    target = str(path)
    count = 0
    for descriptor in descriptor_root.iterdir():
        try:
            opened = os.readlink(descriptor)
        except OSError:
            continue
        count += opened == target
    return count
