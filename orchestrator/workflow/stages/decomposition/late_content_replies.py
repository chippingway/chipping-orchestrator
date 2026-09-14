# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Which of a human's fresh replies is a requirement, and which is a control.

The classification half of the late content read. `late_content` decides who
is counted and what a fingerprint is taken over -- the trust filter, the two
floors a reply has to clear, the ratcheting watermark, the digests -- and this
owner reads the comments that survive all of that, one at a time. They are
split because they are answerable from different things: the reading above is
about the thread and is held to a trust policy and a watermark, while this one
is about a single body and is held to the command vocabulary the whole
workflow shares.

Nothing is parsed here. Both controls are recognized by `engine/messages`,
asked through it rather than re-read, so what `/orchestrator continue` and
`/orchestrator authorize-oversized <commit>` MEAN is spelled in one place and
a late reading cannot drift from the gate that acts on them.

Only the WHOLE comment is either command, which is the same rule read in both
directions. Prose around the authorization is prose -- that is what keeps a
paragraph mentioning the command from becoming a bypass of the size gate --
and the same paragraph is still guidance, because a human who wrote a
sentence about a command wrote a sentence to act on.

What this owner does NOT decide is whether a comment counts toward a digest.
Both controls are trusted comments on the thread, so their bodies are
fingerprinted beside everyone else's by the owner above; being no requirement
is a statement about what an agent may be handed, not about what an edit after
the fact is allowed to hide.
"""
from __future__ import annotations

from orchestrator.workflow.engine import messages as _messages
from orchestrator.workflow.stages.decomposition.late_content_models import _LateAuthorization


def _authorization(fresh: list) -> _LateAuthorization | None:
    """The last authorization the fresh replies carry, if any of them is one.

    The last rather than the first, because a batch is read in thread order
    and a human who wrote the command twice meant the second -- a corrected
    commit below a mistyped one is the request, not the line it corrects.

    Whatever was written is carried forward, a malformed commit included: a
    command nobody could act on is one this workflow owes an answer to, and a
    reader handed nothing at all could not tell it from a line nobody typed.
    What is required here is only that the comment can be NAMED, because the
    record made from it names that comment and an authorization nothing can
    attribute is the one thing that record may not become.
    """
    latest = None
    for issue_comment in fresh:
        named = _messages._authorized_oversized_candidate(issue_comment)
        if named is not None and issue_comment.id > 0:
            latest = _LateAuthorization(
                candidate_sha=named, comment_id=issue_comment.id,
            )
    return latest


def _is_guidance(issue_comment) -> bool:
    """Whether one fresh trusted comment carries something to act on.

    A bare `/orchestrator continue` is not guidance: it is an operator control
    that says to proceed with what is already recorded, and feeding it to an
    agent as a requirement would answer a question with the word "continue".
    A whole-comment `/orchestrator authorize-oversized <commit>` is not
    guidance for the same reason and one of its own: it is a decision about
    the candidate that already exists, so handing it to a developer would
    answer a question about scope with a commit id and re-freeze the very
    change an operator just said may publish. Prose AROUND either command is
    guidance, since neither is the whole comment then.
    An empty body is not guidance either -- a reaction or an attachment with
    no text in it says nothing a developer could revise against.
    """
    if _messages._is_bare_orchestrator_continue(issue_comment):
        return False
    if _messages._authorized_oversized_candidate(issue_comment) is not None:
        return False
    return bool((issue_comment.body or "").strip())
