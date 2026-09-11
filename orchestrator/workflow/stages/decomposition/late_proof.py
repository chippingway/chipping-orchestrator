# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Where the pull request a verdict was measured against has to be standing.

The deepest question a settled `single` asks, and the only one about a HEAD
rather than about which pull request the issue should carry. It is asked on the
published road alone: a candidate nothing had published has no head to be
compared against, and the search that finds its pull request belongs to the
reconciliation above.

Two heads qualify and every other one is external movement. The frozen head is
the ordinary answer -- nothing has touched the pull request since the reading
the verdict was taken over, and the push that verdict earns is still owed. The
other is the accepted candidate WHERE THE RECORD vouches for having put it
there, which is this settlement's own push having landed before the tick died.
Read as movement, that one would refuse the very publication this verdict made,
forever; recognized, the retry finishes the label and the retirement it never
reached and pushes nothing a second time.

The refusal is owned here as well. Every reconciliation that could not confirm
what it read ends in the same park -- publishing on the strength of a reading
nobody could confirm is the one thing all of this exists to prevent -- and it
sits with the deepest check rather than with the road above it, so the
dependency between the two runs one way.
"""
from __future__ import annotations

import logging

from orchestrator.workflow.late_split import (
    formats as _formats,
    payloads as _payloads,
)
from orchestrator.workflow.late_split.models import LateFailure
from orchestrator.workflow.stages.decomposition import (
    late_outcome as _late_outcome,
    late_park_state as _late_park_state,
    late_parks as _late_parks,
)
from orchestrator.workflow.stages.decomposition.late_models import _LateContext
from orchestrator.workflow.stages.implementing import late_parks as _gate_parks

log = logging.getLogger("orchestrator.workflow")

_MOVED_PUBLICATION_PARK = (
    "this issue's committed candidate was adjudicated as one coherent change "
    "against pull request #{number} standing at `{frozen}`, and it is "
    "standing at `{moved}` now. Something pushed to it during the "
    "adjudication, so what the verdict was taken over is not what the branch "
    "would come to -- and it was not handed on for publication. Reconcile the "
    "branch with what landed, then commit again so the candidate is measured "
    "afresh."
)


def _reconciled_head(
    context: _LateContext, observed: str | None, number: int,
) -> bool:
    """Prove the pull request is standing somewhere this verdict may act on.

    Two heads qualify and everything else is external movement. The frozen one
    is the ordinary answer: nothing has touched the pull request since the
    reading, and the push this verdict earns is still owed.

    The other is the ACCEPTED CANDIDATE where the RECORD says this road put
    it there, and it is this settlement's own push having already landed.
    That push happens before the relabel and the retirement, so a tick that
    died in between comes back to a live generation over a pull request the
    commit is already on -- and read as movement, the one thing that would be
    refused forever is the publication this very verdict made. Recognized,
    the tick carries on from where it stopped: nothing is pushed a second
    time, and the label and the retirement it never reached are what it
    finishes.

    The record is what qualifies it, and asking for one is the whole of the
    safety. On a FRESH pass this call runs before the exemption, the approval,
    and the push behind them, so nothing of this workflow's has touched the
    remote yet: a pull request that moved off the frozen head onto the
    candidate moved because something else -- an agent that pushed its own
    commit is the plain case -- put it there, and taking that for a landed
    settlement would publish and hand on a candidate the adjudication was
    never allowed to release. It refuses with every other moved head instead.
    """
    head = _payloads.as_hex(observed, _formats.COMMIT_LENGTHS)
    if head and head == _this_settlements_own_push(context):
        log.info(
            "issue=#%d finds PR #%d already standing on the accepted "
            "candidate %s; finishing the settlement its push interrupted",
            context.issue.number, number, head,
        )
        context.already_published = True
    elif head != context.generation.published_sha:
        return _moved_publication(context, number, head)
    return True


def _this_settlements_own_push(context: _LateContext) -> str:
    """The accepted candidate where a record vouches for its push, or "".

    The two halves of the one window this road opens, and each is durable
    where the candidate on its own is not. The approval is written with the
    exemption in the write immediately ahead of the push and says this
    settlement owes exactly that commit a publication; the receipt is written
    by the push itself, in the same write that drops the approval, and says
    the commit reached the remote. A crash anywhere past that write leaves one
    of the two on the pinned comment, so the retry recognizes the publication
    it made -- and a pass that has written neither has made no push to
    recognize.

    The receipt is read with the head it REPLACED, which is what dates it to
    this settlement. It is never cleared, so on its own it goes on naming a
    commit this issue published rounds ago -- and where the accepted candidate
    IS that commit, a pull request somebody rewound onto it would read as this
    settlement's push having landed. The head this verdict was measured over
    is the one this settlement's push was pinned to, so a receipt recording
    any other head belongs to some earlier publication and answers for
    nothing.

    The pull request the receipt names is read with them, because the head
    cannot supply it: a branch pushed from that head before, onto a publication
    since closed and REPLACED by another on the same ref, dates a receipt to
    this settlement while the push it records went somewhere else. Held to the
    number the verdict was frozen on, the three together name one publication.
    """
    candidate = context.generation.candidate_sha
    vouched = (
        _gate_parks._approved_commit(context.state),
        _gate_parks._publication_from(
            context.state,
            context.generation.published_sha,
            context.generation.published_pr_number,
        ),
    )
    return candidate if candidate and candidate in vouched else ""


def _moved_publication(
    context: _LateContext, number: int, head: str,
) -> bool:
    """Refuse a verdict whose pull request somebody else has moved."""
    frozen = context.generation.published_sha
    log.error(
        "issue=#%d was adjudicated against PR #%d standing at %s and it "
        "stands at %s now; refusing to publish against a publication "
        "that moved",
        context.issue.number, number, frozen, head or "an unreadable head",
    )
    return _unreconciled(
        context,
        _MOVED_PUBLICATION_PARK.format(
            number=number,
            frozen=frozen,
            moved=head or "an unreadable head",
        ),
    )


def _unreconciled(context: _LateContext, message: str) -> bool:
    """Park rather than publish against a pull request nobody could confirm."""
    _late_outcome._emit_failure(context, LateFailure.PR_RECONCILE_FAILED)
    _late_parks._park(
        context, message, reason=_late_park_state.PARK_PR_UNRECONCILED,
    )
    return False
