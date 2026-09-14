# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The requirements a frozen candidate was measured against, fingerprinted.

Two digests, local to one late generation, and neither of them is the global
`user_content_hash`. That hash keeps a single baseline per issue and drives the
re-decompose and dev-resume routes every other stage depends on, so folding a
late question into it would move a baseline those routes read and fire a drift
they were not asking about. What late adjudication needs is a different
reading of the same thread: not "did anything the human wrote change" but
"which of the two things changed", because the two are answered in opposite
directions. A title or body edit changes what the candidate is supposed to BE
and is a reason to stop; trusted conversation arriving after the freeze is a
human answering and is a reason to go on.

So the title and body are digested on their own, and the trusted thread is
digested beside a watermark naming the last comment counted into it. The
watermark is what makes "new" a question with an answer -- a digest can say
that something moved, never which comment moved it -- and it is a ratchet
rather than a maximum recomputed from the thread, because a comment a human
deleted must not put it back down and let already-consumed guidance read as
fresh.

"New" and "an answer" are still not the same thing, which is why a reply is
read against a floor of its own: the higher of that watermark and the
issue-wide `last_action_comment_id`, which every announced park advances past
the notice it posted. A comment written before a park cannot be a reply to it
-- the human had not been told anything yet -- so a park that fires while
somebody is mid-sentence is not resolved on the next tick by the sentence they
had already sent.

The counted prefix is digested rather than trusted to the watermark alone, and
that is what catches the edit nothing else would see: a comment already folded
into the baseline, rewritten in place, moves no id at all. Reading that as
drift is deliberate. It is a change to the requirements with no new comment to
read it out of, which is exactly what a title edit is, so it is answered the
same way rather than lost.

Two of the things a human can write are not requirements at all, and which
fresh reply is which is `late_content_replies`' reading rather than this
owner's: a bare `/orchestrator continue` and a whole-comment
`/orchestrator authorize-oversized <commit>` are operator controls, reported
beside the guidance so the owner that answers a park can act on the one it is
waiting for. What they are NOT is guidance -- nothing hands either to an agent
as a requirement -- but they are still trusted comments on the thread, so
their bodies count into the digest here like anybody else's. That is the
opposite of what the global `user_content_hash` does with them, and
deliberately: there a counted command would fire a drift the stage below was
never asking about, while here the digest's whole job is to notice a counted
comment that was EDITED after the fact, and a command left out of it could be
rewritten into requirements nothing would see.

Neither digest is taken here. Both are the `late_split/identity` owner's --
the domain that already spells what a late generation is keyed by, hashing
discipline included -- so this owner decides WHICH content is fingerprinted
and that one decides what a fingerprint IS. Two SHA-256 implementations of
one contract is exactly the drift the single owner exists to prevent.

Who counts is the same trust policy the global hash applies, asked through the
same filter: the pinned-state comment, the orchestrator's own marker and its
recorded ids, third-party bots, and every author outside `ALLOWED_ISSUE_AUTHORS`
are dropped before anything is digested. Nothing an outsider posts can shift a
fingerprint, become guidance, or move the watermark. A comment with no usable
id is dropped for a narrower reason: the watermark is what would consume it,
and a comment nothing can watermark would read as fresh guidance on every tick
forever.
"""
from __future__ import annotations

from dataclasses import replace

from github.Issue import Issue

from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.engine import (
    comments as _comments,
    content_hash as _content_hash,
    messages as _messages,
)
from orchestrator.workflow.late_split import formats as _formats, identity as _identity
from orchestrator.workflow.late_split.models import LateGeneration
from orchestrator.workflow.stages.decomposition import (
    late_content_replies as _replies,
)
from orchestrator.workflow.stages.decomposition.late_content_models import _LateContentSignal, _LateFingerprint

# The issue-wide record of what the workflow has already acted on, which every
# announced park advances past its own notice. Read here as the floor a REPLY
# has to clear, never written: what it means is the shared one.
_LAST_ACTION_COMMENT_ID = "last_action_comment_id"


def _read_content_signal(
    issue: Issue, state: PinnedState, generation: LateGeneration,
) -> _LateContentSignal:
    """Read what the human's content now says about this frozen candidate.

    One walk of the thread answers all of it. The fingerprint is what the
    generation would be re-baselined to; the two drift flags compare the
    recorded baseline against the same reading; and the guidance is the
    trusted comments past the watermark that carry something to act on.

    The counted prefix is taken at the recorded watermark rather than at the
    one this reading produces, because what "drifted" means is a comparison
    against the baseline that was written, not against the thread as it stands
    now. A generation with no watermark counted nothing, so its prefix is
    empty and nothing on the issue has been folded into a digest yet.

    What counts as a REPLY is a different question and has its own floor --
    see `_fresh_replies`. The two are deliberately not the same reading: a
    comment can be uncounted by the baseline and still be no answer to
    anything.
    """
    trusted = _trusted_thread(issue, state)
    watermark = generation.comment_watermark_id
    counted = [
        issue_comment for issue_comment in trusted
        if watermark is not None and issue_comment.id <= watermark
    ]
    fresh = _fresh_replies(trusted, state, watermark)
    fingerprint = _fingerprint(issue, trusted, watermark)
    return _LateContentSignal(
        fingerprint=fingerprint,
        baselined=(
            generation.title_body_hash is not None
            and generation.comment_hash is not None
        ),
        title_body_drifted=(
            generation.title_body_hash != fingerprint.title_body_hash
        ),
        conversation_drifted=(
            generation.comment_hash != _thread_digest(counted)
        ),
        guidance=tuple(
            issue_comment for issue_comment in fresh
            if _replies._is_guidance(issue_comment)
        ),
        bare_continue=any(
            _messages._is_bare_orchestrator_continue(issue_comment)
            for issue_comment in fresh
        ),
        authorization=_replies._authorization(fresh),
    )


def _rebaselined(
    generation: LateGeneration, fingerprint: _LateFingerprint,
) -> LateGeneration:
    """Return this generation baselined against the content as it now stands.

    The whole fingerprint or none of it. Advancing the watermark without the
    digest beside it would leave a prefix nothing had hashed, and advancing
    the digest without the watermark would leave the comments it covers
    reading as fresh guidance for a second time.
    """
    return replace(
        generation,
        title_body_hash=fingerprint.title_body_hash,
        comment_hash=fingerprint.comment_hash,
        comment_watermark_id=fingerprint.comment_watermark_id,
    )


def _fingerprint(
    issue: Issue, trusted: list, watermark: int | None,
) -> _LateFingerprint:
    """The fingerprint the content as it stands would be recorded as.

    The watermark only ever rises. A deletion that removed the highest counted
    comment would otherwise lower it, and the comments between the new
    maximum and the old one -- already read by an agent, already answered --
    would come back as guidance nobody had written twice.
    """
    ids = [issue_comment.id for issue_comment in trusted]
    return _LateFingerprint(
        title_body_hash=_identity.title_body_fingerprint(
            issue.title or "", issue.body or "",
        ),
        comment_hash=_thread_digest(trusted),
        comment_watermark_id=max([*ids, watermark or 0]) or None,
    )


def _trusted_thread(issue: Issue, state: PinnedState) -> list:
    """The comments on this issue a late fingerprint is allowed to count.

    The trust filter is the global hash's own, so what counts as a human's
    requirements is decided in one place: an outsider, a third-party bot, and
    the orchestrator's own comments are dropped here and can neither shift a
    digest nor arrive as guidance.

    A comment with no usable id is dropped beside them. The watermark is the
    only thing that ever consumes one, so a comment it cannot name would be
    read as new guidance on every tick for as long as the generation lived.
    """
    orchestrator_ids = _comments._orchestrator_ids(state)
    return [
        issue_comment
        for issue_comment in issue.get_comments()
        if _formats.whole_number(getattr(issue_comment, "id", None))
        and not _content_hash._is_hidden_comment(
            issue_comment, orchestrator_ids,
        )
    ]


def _fresh_replies(trusted: list, state: PinnedState, watermark) -> list:
    """The trusted comments that are a reply to where this issue now stands.

    Two floors, and the higher of them wins. The generation's own watermark is
    the conversation its baseline folded in. `last_action_comment_id` is the
    issue-wide record of what the workflow has already acted on, and every
    announced park advances it past the notice it just posted -- which is what
    makes it the response boundary a park needs. A comment written BEFORE a
    park is not an answer to it: the human had not been told anything yet, and
    a scope edit that parked while they were mid-sentence must not be resolved
    one tick later by the sentence they had already sent. Reading the higher
    floor is what holds that line for as long as the park stands, rather than
    for the single tick that took it.

    Nothing advances that watermark without consuming what it advances past,
    so the conservative reading costs no real reply: a comment above it has
    never been acted on by anything.
    """
    floor = watermark or 0
    acted = state.get(_LAST_ACTION_COMMENT_ID)
    if _formats.whole_number(acted) and acted > floor:
        floor = acted
    return [
        issue_comment for issue_comment in trusted
        if issue_comment.id > floor
    ]


def _thread_digest(trusted: list) -> str:
    """The digest of one trusted comment run, in the order it was posted."""
    return _identity.comment_fingerprint(
        issue_comment.body or "" for issue_comment in trusted
    )
