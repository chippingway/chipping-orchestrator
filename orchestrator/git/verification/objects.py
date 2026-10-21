# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What object an id names in a checkout, told apart from a read that established nothing.

`probes._commit_present` asks a yes-or-no question and answers no on any
failure, which is right for a caller that must treat an object nobody proved
as absent. A caller that must not take a failed read for a proof of absence --
the verification-evidence proof, which holds where nothing could be read and
retires evidence only on what it proved (`workflow/engine/verification_world.py`)
-- asks here once that answer is no: git's own type for the object; the empty
answer only where git's lookup exits as it does for a name that resolves to
nothing, without a word about any object it could not open; and None where it
said neither.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

from orchestrator.git import commands as _commands

# The status a quiet `git rev-parse --verify` exits with for a name that
# resolves to no object. Any other failure -- git's fatal 128, or the negative
# status of a process a signal ended -- is a lookup that never answered.
_ABSENT_STATUS = 1


def _object_kind(worktree: Path, revision: str) -> str | None:
    """The type of the object `revision` names in `worktree`; "" where git answers none is here; None unread.

    Read without peeling, the way an id recorded as a commit is asked about.
    The type comes first, and its failure reads the same for an object that is
    missing and for one git could not open. So does an existence check's exit
    status: `cat-file -e` exits 1 for an object behind a directory it may not
    read, as for one that is not there. What tells them apart is what git
    SAYS: a quiet lookup of an object that is missing exits with its own
    status for a name that resolves to nothing and says nothing on stderr,
    while one git could not open fails with git's own account of why -- a
    difference read off whether anything was said, never off the words, which
    a locale may translate. A lookup that ended any other way, killed by a
    signal among them, said nothing about the object either way. Hardened like
    every read of a checkout an agent writes, and None where git could not be
    run at all.
    """
    typed = _git(worktree, "cat-file", "-t", revision)
    if typed is None:
        return None
    if typed.returncode == 0:
        return (typed.stdout or "").strip() or None
    looked_up = _git(worktree, "rev-parse", "--verify", "--quiet", f"{revision}^{{object}}")
    if looked_up is None or looked_up.returncode != _ABSENT_STATUS:
        return None
    return None if (looked_up.stderr or "").strip() else ""


def _git(worktree: Path, *args: str) -> subprocess.CompletedProcess | None:
    """One hardened git read in `worktree`, or None where git could not be run."""
    try:
        return _commands._git_hardened(*args, cwd=worktree)
    except OSError:
        return None
