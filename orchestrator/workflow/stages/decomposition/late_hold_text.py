# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Cycle-marked pull-request hold text and exact recognition of supported descriptions.

Pre-publication and published candidates explain their hold separately.
Restoration recognizes only complete descriptions produced for this cycle.
"""
from __future__ import annotations

from orchestrator.workflow.late_split.models import LateGeneration

# The marker every late hold opens with. The prefix is what identifies a body
# as held at all -- by any cycle, including one an older binary wrote -- and
# it is what decides whether capturing the current body would preserve
# somebody's description or a hold.
_HOLD_PREFIX = "<!--orchestrator-late-hold"

# What every hold says once it has said which change it is holding. Shared
# rather than repeated because it is the part that is true on both sides of
# publication, and because the older spelling below has to reproduce it
# exactly.
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
    if generation.has_publication_context:
        return _published_hold_body(generation)
    return _unpublished_hold_body(generation)


def _unpublished_hold_body(generation: LateGeneration) -> str:
    """The notice a pull request nothing has pushed to carries.

    Byte-for-byte what this hold has always said, because a spelling is a
    compatibility contract: holds written by earlier binaries are standing on
    live pull requests right now, and a word changed here would read every one
    of them as a human's own description -- refusing to restore the copy it
    replaced, and refusing to start anything under it, for good.
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


def _superseded_hold_body(generation: LateGeneration) -> str:
    """The same hold as an earlier binary of ours spelled it.

    A hold is bytes on somebody else's pull request, which makes its wording a
    compatibility contract rather than a detail: an orchestrator upgraded
    mid-adjudication meets descriptions its predecessor wrote, and a spelling
    it cannot reconstruct is one it reads as a human's own words -- refusing
    to restore the preserved copy and refusing to start anything under the
    pull request, for good.

    So the older spelling is kept, exactly, as something to RECOGNIZE. It is
    never written: a body found in it is rewritten in the current one by the
    same reconciliation that would have applied a fresh hold, which is one
    edit and leaves every later comparison with a single answer to make.

    It is marked by generation as well as cycle and quotes the measurement,
    which is why it was replaced -- both move inside a cycle, so a
    re-measurement left the pull request wearing a notice the next tick could
    no longer rebuild. Reconstructible here for the generation that is
    actually recorded, which is the upgrade this exists for: the binary
    changed under a hold, and nothing about the candidate did.

    There is no published counterpart to reconstruct. No binary that wrote
    this spelling ever marked a pull request the work was already on, so a
    body found in it was written before publication whatever the record beside
    it says now.
    """
    return (
        f"{_HOLD_PREFIX}:cycle={generation.cycle_id}"
        f":generation={generation.generation}-->\n"
        ":hourglass: **Held by the orchestrator.** The committed "
        f"implementation for issue #{generation.current_issue} measures "
        f"{generation.additions} added lines against a ceiling of "
        f"{generation.threshold}, so it is being adjudicated before anything "
        f"is published. {_HOLD_TAIL}"
    )


def _wears_our_hold(generation: LateGeneration, body: str) -> bool:
    """Whether this description is a hold THIS generation wrote, any spelling.

    The one question both the retry and the release ask, so an upgrade is
    handled in one place rather than in two that could disagree about it.
    Three spellings are reconstructible and no others: the two this binary
    writes, one per side of publication, and the one the binary before it
    wrote. Anything else is a human's, whatever hidden marker it happens to
    carry.

    Both current spellings are recognized, and only ever one of them written.
    That is what makes a record that crosses publication mid-cycle -- a
    developer resumed on guidance, a push, a re-measurement entered past it --
    an upgrade like any other rather than a hold this issue reads as somebody
    else's: the notice already standing is still ours, so the same edit that
    would have applied a fresh one rewrites it in the side the record now
    names, and every later comparison has a single answer to make.
    """
    return body in (
        _unpublished_hold_body(generation),
        _published_hold_body(generation),
        _superseded_hold_body(generation),
    )
