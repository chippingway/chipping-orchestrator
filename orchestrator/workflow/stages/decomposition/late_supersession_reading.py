# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Prove that a split still names its exact published commit and supersession.

Only this cycle's closed supersession may complete an interrupted split.
A moved head or undone closure withholds child activation and reclamation.
"""
from __future__ import annotations

import logging

from orchestrator.workflow.late_split import (
    formats as _formats,
    payloads as _payloads,
)
from orchestrator.workflow.stages.decomposition import (
    late_publication as _late_publication,
)
from orchestrator.workflow.stages.decomposition.late_models import _LateContext

log = logging.getLogger("orchestrator.workflow")



# How the pull request a published split was measured on can fail to be the
# one the verdict was taken over. Each is spelled as the log line reads it,
# because what an operator has to reconcile differs by which of them moved.
_SETTLED_PUBLICATION = "PR #{number} is {state} rather than open"


def _publication_is_still_the_one(
    context: _LateContext,
    reading: _late_publication._PublicationReading,
    number: int,
) -> str:
    """Why this pull request is not the one the verdict was taken over, or "".

    Named rather than counted, because what an operator has to reconcile
    differs by which of the two moved: a change they settled themselves, and a
    change somebody pushed to while the adjudication was open.

    A pull request closed over THIS adjudication's own receipt is neither, as
    far as the STATE goes. It is the supersession this transaction already
    made, on a tick that died before the retirement behind it -- so the close
    is no disagreement and the step below finishes as a read. A MERGED one is
    not that, whatever the thread says: a human who reopened and landed the
    work decided the opposite of what the supersession claims, and handing it
    to children afterwards is the one outcome nothing takes back. A reopened
    one is not that either -- it reads `open`, so the close is made again,
    with the receipt already on the thread keeping the notice from repeating.

    The head is proved on that path too, and on every other. A close does not
    freeze a branch: somebody can push to it after this transaction closed the
    pull request and before the retry arrives, and the receipt says only that
    the close was made, never that what it closed is still what the verdict
    was taken over. Waved through, the retry would settle the split, activate
    the children, and RECLAIM that branch -- deleting a commit no snapshot
    holds, because the snapshot was taken of the frozen head.
    """
    if reading.state == _late_publication.CLOSED and reading.superseded:
        return _own_supersession_holds(context, reading, number)
    if reading.state != _late_publication.OPEN:
        return _SETTLED_PUBLICATION.format(
            number=number, state=reading.state,
        )
    return _publication_moved(context, reading, number)


def _own_supersession_holds(
    context: _LateContext,
    reading: _late_publication._PublicationReading,
    number: int,
) -> str:
    """Why the close this split already made cannot be finished, or "".

    The receipt answers the state and nothing else, so the head is asked
    exactly as it is on the open path: a branch pushed to behind the close is
    a disagreement whoever made it, and it fails closed here rather than being
    discovered by the reclamation that deletes it.
    """
    moved = _publication_moved(context, reading, number)
    if moved:
        return moved
    log.info(
        "issue=#%d finds PR #%d already closed over this adjudication's "
        "own supersession; finishing the split its retirement interrupted",
        context.issue.number, number,
    )
    return ""


def _publication_moved(
    context: _LateContext,
    reading: _late_publication._PublicationReading,
    number: int,
) -> str:
    """Why this pull request no longer stands where it was frozen, or "".

    A head that will not read as a whole object id is movement too: what the
    verdict was taken over is a named commit, and text that is not one cannot
    be shown to be it.
    """
    head = _payloads.as_hex(reading.head, _formats.COMMIT_LENGTHS)
    frozen = context.generation.publication.published_sha
    if head == frozen:
        return ""
    return _late_publication._MOVED_PUBLICATION.format(
        number=number, frozen=frozen, moved=head or "an unreadable head",
    )


def _publication_holds(context: _LateContext) -> str:
    """Why the close this pass made no longer holds, or "".

    The shared reading one owner down, taken off the record this pass is
    carrying -- which still names the publication past the retirement, since
    that write keeps the group.
    """
    return _late_publication._publication_undone(
        context.gh, context.issue, context.generation,
    )
