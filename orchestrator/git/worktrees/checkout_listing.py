# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""A complete reading of the branches this clone has checked out.

A porcelain listing can silently omit damaged linked-worktree entries. It is
only evidence when its records account for every registered checkout."""
from __future__ import annotations

import logging

from orchestrator.config import models as _config_models
from orchestrator.git import locks
from orchestrator.git.worktrees import (
    evidence_reads as _evidence_reads,
    probes,
    tip_evidence as _tip_evidence,
)

log = logging.getLogger("orchestrator.worktree_lifecycle")


# How `worktree list --porcelain` spells the branch a worktree is on. A
# detached one carries no such line at all.
_WORKTREE_BRANCH = "branch "

# The line that opens each worktree's record in the same listing, and the
# directory inside a clone's git directory holding one entry per linked
# worktree. The two are counted against each other, because the listing drops
# an entry whose backlink is missing and says nothing about having done so.
_WORKTREE_RECORD = "worktree "

_WORKTREE_ADMIN = "worktrees"


def _registered_worktrees(spec: _config_models.RepoSpec) -> int | None:
    """How many linked worktrees this clone keeps administrative entries for.

    The count the listing beside this is checked against. Every linked worktree
    git knows about has a directory of its own under the clone's
    `worktrees/`, and that directory is what survives when the backlink inside
    it does not -- which is exactly the state `worktree list` passes over in
    silence.

    Zero where the clone has never had one, which is an established answer: a
    repository with no `worktrees/` directory has no linked worktrees. `None`
    for every other refusal, since a count nobody could take must not arrive as
    agreement with whatever the listing said.
    """
    common_dir = probes._checkout_clone(spec.target_root)
    if common_dir is None:
        return None
    try:
        return len(list((common_dir / _WORKTREE_ADMIN).iterdir()))
    except FileNotFoundError:
        return 0
    except OSError as read_error:
        log.debug(
            "could not read the worktree entries of %s: %s",
            spec.target_root, read_error,
        )
        return None


def _checked_out_branches(spec: _config_models.RepoSpec) -> frozenset[str] | None:
    """Every branch a worktree of this clone still has checked out, or None.

    The one thing `update-ref -d` gives up in exchange for its commit pin.
    `branch -D` refuses to delete a branch a worktree is on, and the plumbing
    form does it without a word -- leaving that tree holding a HEAD that names
    a ref nothing resolves. So a caller deleting through the plumbing has to
    ask this question itself, and it has to ask the clone rather than reason
    from the candidate: a worktree an operator added by hand to look at a
    finished branch is on it just as squarely as one this orchestrator made,
    and no scan of the per-issue paths would ever name it.

    A listing that exits zero is not on its own the whole answer, which is why
    it is counted against the clone's own administrative entries. `worktree
    list` drops a linked worktree whose backlink file is missing -- silently,
    with nothing on stderr and a zero exit -- while that worktree goes on
    working and goes on holding its branch. A caller spending the short answer
    would delete the ref under it, which is the very thing this read exists to
    prevent, so anything the two readings cannot account for between them is
    answered as no reading at all.

    Both are taken under one hold of the lock every mutation of this clone
    serializes on, so the listing and the count describe one moment rather than
    two either side of a `worktree add`.

    The names come back stripped of `refs/heads/`, which is how every
    derivation in ``paths`` spells a branch, so a caller compares against them
    without either side adjusting. A detached worktree names no branch and
    contributes nothing.
    """
    with locks._target_root_lock(spec.target_root):
        listed = _evidence_reads._hardened_read(
            spec.target_root, "worktree", "list", "--porcelain",
        )
        registered = _registered_worktrees(spec)
    if listed is None or listed.returncode != 0:
        log.debug(
            "could not list the worktrees of %s: %s",
            spec.target_root,
            None if listed is None else (listed.stderr or "").strip(),
        )
        return None
    reported = (listed.stdout or "").splitlines()
    if not _all_worktrees_accounted(spec, reported, registered):
        return None
    on_branch = f"{_WORKTREE_BRANCH}{_tip_evidence._LOCAL_REF_PREFIX}"
    return frozenset(
        line[len(on_branch):]
        for line in reported
        if line.startswith(on_branch)
    )


def _all_worktrees_accounted(
    spec: _config_models.RepoSpec, reported: list[str], registered: int | None,
) -> bool:
    """Whether the listing named every worktree this clone has an entry for.

    One line per worktree opens each record, and the clone's own is the first
    of them -- so a healthy listing names exactly one more worktree than there
    are linked entries. Anything else is a worktree git declined to report
    while its directory is still there, and this read may not answer for a
    clone it could only see part of.
    """
    if registered is None:
        log.warning(
            "could not count the worktrees registered in %s; taking the "
            "listing as unread rather than as the part of it that answered",
            spec.target_root,
        )
        return False
    named = sum(
        1 for line in reported if line.startswith(_WORKTREE_RECORD)
    )
    if named == registered + 1:
        return True
    log.warning(
        "%s registers %d linked worktrees and listed %d; taking the listing "
        "as unread rather than deleting a branch one of them may be on",
        spec.target_root, registered, named - 1,
    )
    return False
