# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Deliver snapshot reclamation receipts to consumers while the owner remains open.

Each child's cycle-bound receipt is deduplicated from its thread. Close
checks surround the reads and writes, and an unreachable child keeps the
notification obligation outstanding.
"""
from __future__ import annotations

import logging

from github.Issue import Issue

from orchestrator import config
from orchestrator.github import comments as _comments
from orchestrator.workflow.late_split import (
    ancestry as _ancestry,
)
from orchestrator.workflow.late_split.models import (
    LateGeneration,
)
from orchestrator.workflow.stages.decomposition import (
    late_cleanup_state as _late_cleanup_state,
)
from orchestrator.workflow.stages.decomposition.models import _ChildScan

log = logging.getLogger("orchestrator.workflow")


# What a child is told when the snapshot it was created to reuse is reclaimed.
# Said once, at the moment it becomes true, so an issue reopened long after
# its owner closed still reads it rather than following a pointer to nothing.
# It is a comment and only a comment -- see `_release` for why this owner may
# not write a consumer's pinned state at all.
_RELEASED_NOTICE = (
    "{mentions} the immutable snapshot this issue was created to reuse (from "
    "the split on #{owner}) has been reclaimed, now that every issue cut from "
    "it has ended. That ref is never recreated -- what made it worth reusing "
    "was that it provably carried one exact commit, and a ref pushed again "
    "from whatever is reachable now proves nothing. If this issue is "
    "reopened, it is parked before any implementation starts: continuing "
    "means an ordinary change, or an explicit new split cycle on #{owner}, "
    "which preserves a candidate of its own.\n\n{marker}"
)


def _release_consumers(
    walk: _late_cleanup_state._Pass, generation: LateGeneration, ref: str, proven: _ChildScan,
) -> tuple[LateGeneration, bool]:
    """Let every child cut from this ref know it is gone, once each.

    Answers with the record this left and whether ALL of them were reached.
    Every consumer is attempted before that answer is given -- one child this
    pass could not reach is not a reason to leave the rest untold.

    A CANCELLED cycle tells none of them, and answers as though it had. Its
    children are issues a human's close stranded rather than work this
    orchestrator is still driving, and what that ending owes them is nothing
    at all: it does not close them, relabel them, write their pinned state, or
    put a word on their threads. Nothing about the ref is left unsaid by it --
    the transport drops this host's copy before it touches the remote and
    refuses the whole reclamation if that copy cannot be proved gone, so a
    child reopened afterwards finds no mirror, asks the remote once, and is
    stopped and told by its own guard on its own dispatch. The receipt is what
    a live split owes the children it is still responsible for, and this is
    the one pass that is responsible for none.

    Which is why the reading is taken between EVERY two of them rather than
    once for the walk. Each receipt is a comment on somebody else's issue, so
    a close observed after the first is one the second may not be written
    over: the children left are owed nothing, and the pass stops telling them
    where it stands. It answers "all told" for those, because a cycle that
    owes no receipt has left none undelivered.

    And once more INSIDE each of them, because proving a child untold is a
    request of its own: the thread walk stands between the reading this loop
    took and the comment it authorizes, and a close landing in there would
    otherwise be written over exactly as one landing between two children
    would.
    """
    if generation.cancelled:
        return generation, True
    marker = _ancestry.release_marker(
        owner=walk.issue.number,
        cycle=generation.cycle_id,
        generation=generation.generation,
    )
    told = True
    for consumer in generation.obligations.consumers:
        generation = _late_cleanup_state._observed_close(walk, generation)
        if generation.cancelled:
            break
        generation, delivered = _release(
            walk, proven, consumer, marker, generation,
        )
        told = delivered and told
    return generation, told


def _release(
    walk: _late_cleanup_state._Pass,
    proven: _ChildScan,
    consumer: int,
    marker: str,
    generation: LateGeneration,
) -> tuple[LateGeneration, bool]:
    """Say on one child that the ref it was cut from is gone.

    A COMMENT, and nothing else. Everything this owner knows about a consumer
    it would rather write into that consumer's pinned comment -- drop the
    dangling pointer, park it -- and it may not: the pinned comment is written
    whole by whoever writes it, and a handler of the child's own that read it
    before this pass and wrote it after would put the reclaimed pointer back
    and take the park off, silently, with the owner already reconciled and
    nothing left to come back. A label is no proxy for "no writer" either: a
    finalize sets the terminal label BEFORE its last write, and the two
    pre-PR states a human can close an issue on are swept by nothing at all,
    so they never reach one.

    A comment has none of that. It is appended rather than rewritten, so no
    concurrent writer can lose it, and it reaches a consumer in every state a
    consumer can be in. What acts on it is the child's own guard
    (`late_reuse`), evaluated by the child's own handler, where there is
    nobody to race.

    Said once, proved from the thread rather than from state for the same
    reason: the receipt is a marker naming this issue, this cycle, and this
    generation, and a consumer already carrying one of ours has been told.

    Read off the scan the delete was proved on, not the one the pass opened
    with: that is the freshest reading of this child there is. A consumer that
    scan could not fetch, or whose thread could not be read or posted to,
    answers False -- the ref is gone either way, and a child that was never
    told is the one thing this step exists to prevent, so the obligation stays
    on the ledger until it can be.
    """
    child = proven.issues.get(int(consumer))
    if child is None:
        log.warning(
            "issue=#%d reclaimed a snapshot but could not reach consumer #%d "
            "to tell it; the obligation stays owed until it can",
            walk.issue.number, int(consumer),
        )
        return generation, False
    try:
        return _told(walk, child, marker, generation)
    except Exception:
        log.exception(
            "issue=#%d could not tell consumer #%d its snapshot is gone",
            walk.issue.number, int(consumer),
        )
        return generation, False


def _told(
    walk: _late_cleanup_state._Pass,
    child: Issue,
    marker: str,
    generation: LateGeneration,
) -> tuple[LateGeneration, bool]:
    """Post this reclamation's receipt on one child unless it carries one.

    The thread walk that proves this child untold is a REQUEST, and the poll
    runs beside it: a close observed in there makes this a cancelled cycle,
    which owes its children nothing at all -- not a comment, and certainly not
    one addressed to a human. So the latch is asked between the reading and
    the write it authorizes, and the mark goes down where the walk stands
    rather than after the sentence it would have made unsayable.

    It answers "told" for that child all the same, because a cycle that owes
    no receipt has left none undelivered -- the same answer the loop above
    gives for every consumer it stops short of.
    """
    if _comments.carries_own_marker(
        child.get_comments(), marker,
        bot_login=getattr(walk.gh, "_bot_login", None),
    ):
        return generation, True
    generation = _late_cleanup_state._observed_close(walk, generation)
    if generation.cancelled:
        log.warning(
            "issue=#%d was observed closed while consumer #%s was being "
            "read; writing nothing to it",
            walk.issue.number, child.number,
        )
        return generation, True
    walk.gh.comment(child, _RELEASED_NOTICE.format(
        mentions=config.HITL_MENTIONS,
        owner=walk.issue.number,
        marker=marker,
    ))
    return generation, True
