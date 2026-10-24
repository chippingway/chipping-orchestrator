# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Take a child's own writer claim before a parent's handler writes the child.

The claim a dispatch takes covers the issue it was dispatched for and no other,
and a decomposed parent's handler writes its children too: the walk that
relabels a `blocked` child `ready`, the seeds that give a child its parent link
and ancestry, the finalize of a child whose pull request merged, and the notice
that tells a consumer its snapshot is gone -- and it deletes the snapshot those
consumers were cut from, a decision about every one of them. A second poller on
this host dispatching one of those children holds the CHILD's claim, not the
parent's, so a parent that acted past it would race the child's own handler for
one pinned comment and one label set -- the race the family bucket keeps out of
one process, and the claim keeps out of two.

So each of those effects is made under the child's claim, taken without waiting
in front of the read it decides on and held through the effect -- every
consumer's at once for a snapshot's delete, and through the notices behind it.
A refusal is not the child's: each caller answers it as it answers a child it
may not act on yet, and a later pass asks again.

Every one of those effects holds the child's own pinned record, read under the
claim, to admission: a record admission refuses reads back empty -- what a
child nobody seeded reads as -- so a parent deciding on it would seed, repair,
start, finalize, or tell a child whose record nobody read, or take the ref it
was cut from, and its seed would stamp an unversioned record as current. A
finalize, a notice, a seed, or a repair asks of one child (`admitted_child`),
and a seed or a repair writes it through `write_seed`; both raise
`ChildRefused` -- the second where a human's edit since that reading left a
record the writer refuses -- so its caller answers the refusal as the effect
it could not complete. An effect that is all or nothing across children -- the
release walk, a snapshot's delete -- reads each child's record under those
claims and admits it before acting on any (`admitted_children`). The refusal is
said in one local line, never on the child, and nothing is written to it.
"""
from __future__ import annotations

import contextlib
import logging
from collections.abc import Iterable, Iterator, Mapping

from github.Issue import Issue

from orchestrator.github import pinned_refusal as _pinned_refusal
from orchestrator.github.client import GitHubClient
from orchestrator.github.pinned_state import PinnedState
from orchestrator.scheduler import writer_claims as _writer_claims
from orchestrator.workflow.engine import record_admission as _record_admission

log = logging.getLogger("orchestrator.workflow")


class ChildRefused(Exception):
    """A child's pinned record admission refuses, met by a parent's effect on that child.

    Raised by `admitted_child` and `write_seed`, with nothing written to the
    child and the refusal already said locally. Not a
    `pinned_refusal.RecordRefused`, which the dispatcher catches as a refusal
    of the issue it dispatched: a child's refusal abandons no parent handler,
    so each caller answers it as the seed, finalize, or notice it could not
    complete, as it answers a child whose claim was refused.
    """


@contextlib.contextmanager
def held_child(
    gh: GitHubClient,
    owner_number: int,
    child_number: int,
    *,
    alongside: bool = False,
) -> Iterator[bool]:
    """Hold one child's writer claim for the body, or say it was refused.

    Keyed on the client's `repo_id` for the reason the dispatch claim is:
    the id is the one key every poller on this host meets on, whatever name
    each was configured with or fetched the repository under. `alongside` is
    for a write that is append-only and built to land beside the child's own
    handler in this process -- it still keeps every other process out.
    """
    with _writer_claims.issue_writer(
        gh.repo_id, int(child_number), alongside=alongside, repo_name=gh.repo_slug,
    ) as held:
        if not held:
            log.info(
                "issue=#%s leaving child #%s for a later pass: its writer "
                "claim was refused",
                owner_number, child_number,
            )
        yield held


@contextlib.contextmanager
def held_children(
    gh: GitHubClient,
    owner_number: int,
    child_numbers: Iterable[int],
    *,
    alongside: bool = False,
) -> Iterator[bool]:
    """Hold these children's writer claims for the body, and say if all were granted.

    For a write that is all or nothing across children, as a release walk
    is. Taken in order and stopped at the first refusal, since one is enough
    to hold the write back; the claims already taken are given back as the
    body ends. `alongside` is `held_child`'s, for a step whose only write to
    any of them is a comment built to land beside its handler.
    """
    with contextlib.ExitStack() as claims:
        yield all(
            claims.enter_context(held_child(gh, owner_number, number, alongside=alongside))
            for number in child_numbers
        )


def admitted_child(owner_number: int, child: Issue, reading: PinnedState) -> PinnedState:
    """`reading` -- the child's pinned record, read under the claim the caller holds -- where admission takes it.

    Raises `ChildRefused` where admission refuses it, said locally first. A
    child with no authenticated pinned comment is admitted: it is a genuinely
    fresh child, whose first write the writer stamps with the supported version.
    """
    if _record_admission.refuses(child, reading, _left_unwritten(owner_number)):
        raise ChildRefused(f"child #{child.number} of issue #{owner_number} refused admission")
    return reading


def write_seed(gh: GitHubClient, owner_number: int, child: Issue, child_state: PinnedState) -> None:
    """Write a child's seed or repair whole, under the claim the caller holds.

    The writer raises `pinned_refusal.RecordRefused` over a record admission
    refuses -- a human's edit since the admitted reading is enough to leave
    one -- and that refusal is the child's, not the parent's the dispatcher
    would take it for, so it is raised again as `ChildRefused`.
    """
    try:
        gh.write_pinned_state(child, child_state)
    except _pinned_refusal.RecordRefused as refused:
        log.warning(
            "issue=#%s child #%s holds a pinned record admission refuses at its seed; %s",
            owner_number, child.number, _left_unwritten(owner_number),
        )
        raise ChildRefused(f"child #{child.number} of issue #{owner_number} refused at its seed") from refused


def admitted_children(
    gh: GitHubClient, owner_number: int, children: Mapping[int, Issue],
) -> dict[int, PinnedState] | None:
    """Each child's pinned record, read under the claims the caller holds, or None where any may not be acted on.

    For a write that is all or nothing across children, asked once every claim
    is held and in front of the first write. A record admission refuses is
    said locally, never on the child, and a read that fails is logged; either
    answers None, so the caller writes nothing to any of them and a later pass
    asks again.
    """
    readings: dict[int, PinnedState] = {}
    for number, child in children.items():
        try:
            readings[number] = admitted_child(owner_number, child, gh.read_pinned_state(child))
        except ChildRefused:
            return None
        except Exception:
            log.exception(
                "issue=#%s leaving child #%s for a later pass: its pinned "
                "comment could not be read", owner_number, number,
            )
            return None
    return readings


def _left_unwritten(owner_number: int) -> str:
    """What a parent does with a child whose record admission refuses, as the local line says it."""
    return f"issue #{owner_number} writing nothing to it and leaving it for a later pass"
