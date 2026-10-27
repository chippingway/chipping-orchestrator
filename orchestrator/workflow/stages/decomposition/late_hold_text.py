# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Cycle-marked pull-request hold text and exact recognition of supported descriptions.

Pre-publication and published candidates explain their hold separately.
Restoration recognizes only complete descriptions this binary writes for this
cycle, in either spelling; any other body under the hold marker is nobody's
hold to replace or take back off, and one under a marker this cycle never
stamped is told apart only so its preserved copy is kept.
"""
from __future__ import annotations

from orchestrator.workflow.late_split.models import LateGeneration

# The marker every late hold opens with. The prefix is what identifies a body
# as held at all -- by any cycle, in any spelling, whether or not this binary
# could have written it -- and it is what decides whether capturing the
# current body would preserve somebody's description or a hold. That is the
# one recognition kept for a spelling this binary does not write: enough to
# refuse taking a hold over it, and never enough to replace or restore it.
_HOLD_PREFIX = "<!--orchestrator-late-hold"

# What every hold says once it has said which change it is holding. Shared
# rather than repeated because it is the part that is true on both sides of
# publication.
_HOLD_TAIL = (
    "Do not merge this pull request while the hold stands.\n\n"
    "This description is temporary. The original is preserved in the issue's "
    "pinned orchestrator state and is restored when adjudication finishes."
)


def _hold_marker(generation: LateGeneration) -> str:
    """The marker identifying one CYCLE's hold on a held PR body.

    Scoped to the cycle and not to the generation inside it, because what the
    hold says is true of the whole adjudication rather than of one attempt at
    it: the generation counter advances on every reconciliation that lands,
    and a marker that moved with it would leave every re-measured candidate
    wearing a notice its own record no longer recognized.
    """
    return f"{_HOLD_PREFIX}:cycle={generation.cycle_id}-->"


def _hold_body(generation: LateGeneration) -> str:
    """The temporary description a held pull request carries.

    Every part of it is derived from fields that do not move inside a cycle,
    which is the property both the retry and the release are built on: the
    body this issue wrote is reconstructible EXACTLY, so "is this still ours?"
    is one comparison rather than a guess from a hidden marker somebody could
    have left in place while rewriting the sentence around it. What the
    candidate currently measures is deliberately not in here for that reason
    -- it moves with every revision, and the issue thread is where each new
    measurement is announced.

    Which of the two it writes is the side of publication the generation was
    entered on, because the sentence a human reads has to be true of the
    change they are looking at. A pull request nothing has pushed to is
    adjudicated before anything is published; one the work is already ON was
    published a while ago, and telling its author their change is being held
    "before anything is published" describes somebody else's.
    """
    if generation.publication.is_complete:
        return _published_hold_body(generation)
    return _unpublished_hold_body(generation)


def _unpublished_hold_body(generation: LateGeneration) -> str:
    """The notice a pull request nothing has pushed to carries.

    Byte-for-byte frozen, because a spelling is a current format: holds this
    binary wrote are standing on live pull requests, and a word changed here
    would read every one of them as a human's own description -- refusing to
    restore the copy it replaced, and refusing to start anything under it.
    """
    return (
        f"{_hold_marker(generation)}\n"
        ":hourglass: **Held by the orchestrator.** The committed "
        f"implementation for issue #{generation.current_issue} measured past "
        "the size ceiling, so it is being adjudicated before anything is "
        f"published. {_HOLD_TAIL}"
    )


def _published_hold_body(generation: LateGeneration) -> str:
    """The notice the pull request the work is already on carries.

    What the gate measured on this side is not the commit's own diff but
    everything the pull request comes to with the commit in it, and the commit
    is not on it yet -- so what the notice names is the push the adjudication
    stands in front of, rather than a publication that already happened.

    Cycle-stable like the other one, and for the same comparison: the pull
    request it is written onto, the ceiling it is measured against, and what
    it currently comes to are all left out, since every one of them can move
    while a hold stands.
    """
    return (
        f"{_hold_marker(generation)}\n"
        ":hourglass: **Held by the orchestrator.** The committed "
        f"implementation for issue #{generation.current_issue} takes this "
        "pull request past the size ceiling, so it is being adjudicated "
        f"before that commit is pushed onto it. {_HOLD_TAIL}"
    )


def _wears_our_hold(generation: LateGeneration, body: str) -> bool:
    """Whether this description is a hold THIS cycle wrote, in either spelling.

    The one question both the retry and the release ask, so the answer is
    given in one place rather than in two that could disagree about it. Two
    spellings are reconstructible and no others: the two this binary writes,
    one per side of publication. Anything else is not ours to replace or
    restore, whatever hidden marker it happens to carry -- a human's words, a
    notice somebody edited, or a hold in a spelling this binary never writes.

    Both are recognized, and only ever one of them written. That is what
    makes a record that crosses publication mid-cycle -- a developer resumed
    on guidance, a push, a re-measurement entered past it -- still this
    issue's hold rather than one it reads as somebody else's: the notice
    already standing is ours, so the same edit that would have applied a
    fresh one rewrites it in the side the record now names, and every later
    comparison has a single answer to make.
    """
    return body in (
        _unpublished_hold_body(generation),
        _published_hold_body(generation),
    )


def _wears_unwritten_hold(generation: LateGeneration, body: str) -> bool:
    """Whether this description is held by a notice this cycle never wrote.

    The hold marker without this cycle's own: another cycle's hold, or one in
    a spelling this binary does not write. Told apart from a human editing
    this cycle's notice, which keeps the marker this cycle stamped, because
    the two leave different things under them. An edited notice is somebody's
    words, so the copy preserved beside it is no longer a description of
    anything; a notice nobody here wrote is still a hold, and the copy is still
    the only one of the description it covers.
    """
    return _HOLD_PREFIX in body and _hold_marker(generation) not in body
