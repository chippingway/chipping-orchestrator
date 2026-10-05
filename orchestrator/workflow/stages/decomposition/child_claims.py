# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Take a child's own writer claim before a parent's handler writes the child.

The claim a dispatch takes covers the issue it was dispatched for and no other,
and a decomposed parent's handler writes its children too: the walk that
relabels a `blocked` child `ready`, the seeds that give a child its parent link
and ancestry, the finalize of a child whose pull request merged, and the notice
that tells a consumer its snapshot is gone. A second poller on this host
dispatching one of those children holds the CHILD's claim, not the parent's, so
a parent that wrote past it would race the child's own handler for one pinned
comment and one label set -- the race the family bucket keeps out of one
process, and the claim keeps out of two.

So each of those writes is made under the child's claim, taken without waiting
in front of the read it decides on and held through the write. A refusal is not
the child's: each caller answers it as it answers a child it may not act on
yet, and a later pass asks again.
"""
from __future__ import annotations

import contextlib
import logging
from collections.abc import Iterable, Iterator

from orchestrator.github.client import GitHubClient
from orchestrator.scheduler import writer_claims as _writer_claims

log = logging.getLogger("orchestrator.workflow")


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
    gh: GitHubClient, owner_number: int, child_numbers: Iterable[int],
) -> Iterator[bool]:
    """Hold these children's writer claims for the body, and say if all were granted.

    For a write that is all or nothing across children, as a release walk
    is. Taken in order and stopped at the first refusal, since one is enough
    to hold the write back; the claims already taken are given back as the
    body ends.
    """
    with contextlib.ExitStack() as claims:
        yield all(
            claims.enter_context(held_child(gh, owner_number, number))
            for number in child_numbers
        )
