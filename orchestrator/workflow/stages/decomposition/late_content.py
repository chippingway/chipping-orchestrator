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
had already sent. What that floor holds back is not thrown away, though: the
guidance under it is reported as withheld, which no park is answered by and
no consumer may fold until an agent has been handed it.

The counted prefix is digested rather than trusted to the watermark alone, and
that is what catches the edit nothing else would see: a comment already folded
into the baseline, rewritten in place, moves no id at all. Reading that as
drift is deliberate. It is a change to the requirements with no new comment to
read it out of, which is exactly what a title edit is, so it is answered the
same way rather than lost.

Three of the things a human can write are not requirements at all, and which
fresh reply is which is `late_content_replies`' reading rather than this
owner's: a bare `/orchestrator continue`, a whole-comment
`/orchestrator authorize-oversized <commit>`, and a bare
`/orchestrator add-agent-runs N` are operator controls. The first two are
reported beside the guidance so the owner that answers a park can act on the
one it is waiting for; the run grant is the run-limit hold's to answer, so it
is reported as nothing at all. What none of them is is guidance -- nothing
hands one to an agent as a requirement -- but they are still trusted comments
on the thread, so their bodies count into the digest here like anybody
else's. That is the
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

The global hash is still asked for here, off the same batch. An owner that consumes
this reading records the issue-wide baseline for what it consumed --
`late_park_state` does, beside both watermarks -- or the drift check of
whatever stage the issue reaches next meets already-answered guidance as a
fresh edit. So the signal carries
`user_content_hash` over the very title, body, and comment batch the late
digests were taken from: the whole batch as read rather than the trusted run
below, handed to `engine/content_hash` so its own filter -- operator commands
dropped, where the late digest counts them -- decides what counts, exactly as
it will when that drift check compares against it. Nothing behind it is read a
second time -- not the thread, and not the title or body either -- because a
comment or edit arriving after this reading must not enter a value that
vouches for having been consumed, nor split it from the late fingerprint taken
beside it. Carrying it settles nothing; this owner writes no pinned state.

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

    The title, the body, and the thread are each read exactly once, here, and
    everything the signal says is computed off those values. An edit landing
    between two reads of the body would otherwise leave the late fingerprint
    describing one body and the requirements hash another, and a reply landing
    between two reads of the thread would enter a hash that vouches for
    content nothing consumed.
    """
    return _signal_of(
        (issue.title or "", issue.body or ""),
        list(issue.get_comments()),
        state,
        generation,
    )


def _signal_of(
    text: tuple[str, str], read: list, state: PinnedState,
    generation: LateGeneration,
) -> _LateContentSignal:
    """The signal one reading of the title, body, and thread amounts to.

    The fingerprint is what the generation would be re-baselined to; the two
    drift flags compare the recorded baseline against the same reading; the
    guidance is the trusted comments past the watermark that carry something
    to act on; and the requirements hash is the global filter's reading of
    the same title, body, and batch, so it describes nothing the rest of the
    signal did not see.

    The counted prefix is taken at the recorded watermark rather than at the
    one this reading produces, because what "drifted" means is a comparison
    against the baseline that was written, not against the thread as it stands
    now. A generation with no watermark counted nothing, so its prefix is
    empty and nothing on the issue has been folded into a digest yet.

    What counts as a REPLY is a different question and has its own floor --
    see `_partitioned`. The two are deliberately not the same reading: a
    comment can be uncounted by the baseline and still be no answer to
    anything, and the guidance in that gap is reported as withheld.
    """
    trusted = _trusted_thread(read, state)
    counted, held, fresh = _partitioned(trusted, state, generation)
    fingerprint = _fingerprint(
        text, trusted, generation.comment_watermark_id,
    )
    return _LateContentSignal(
        fingerprint=fingerprint,
        requirements_hash=_content_hash._hash_requirements(
            *text, read, _comments._orchestrator_ids(state),
        ),
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
        withheld=tuple(
            issue_comment for issue_comment in held
            if _replies._is_guidance(issue_comment)
        ),
        owed=tuple(
            issue_comment for issue_comment in trusted
            if issue_comment.id in generation.owed_replies
        ),
        bare_continue=any(
            _messages._is_bare_orchestrator_continue(issue_comment)
            for issue_comment in fresh
        ),
        authorization=_replies._authorization(fresh),
        text=text,
        read=tuple(read),
    )


def _rebaselined(
    generation: LateGeneration, fingerprint: _LateFingerprint,
) -> LateGeneration:
    """Return this generation baselined against the content as it now stands.

    The whole fingerprint or none of it. Advancing the watermark without the
    digest beside it would leave a prefix nothing had hashed, and advancing
    the digest without the watermark would leave the comments it covers
    reading as fresh guidance for a second time.

    Marked bounded, since every caller takes it over no more than the
    issue-wide baseline covers -- the first baseline's covered prefix, or a
    consumption that records that baseline over the same reading.
    """
    return replace(
        generation,
        title_body_hash=fingerprint.title_body_hash,
        comment_hash=fingerprint.comment_hash,
        comment_watermark_id=fingerprint.comment_watermark_id,
        baseline_bounded=True,
    )


def _fingerprint(
    text: tuple[str, str], trusted: list, watermark: int | None,
) -> _LateFingerprint:
    """The fingerprint the content as it stands would be recorded as.

    The watermark only ever rises. A deletion that removed the highest counted
    comment would otherwise lower it, and the comments between the new
    maximum and the old one -- already read by an agent, already answered --
    would come back as guidance nobody had written twice.
    """
    ids = [issue_comment.id for issue_comment in trusted]
    return _LateFingerprint(
        title_body_hash=_identity.title_body_fingerprint(*text),
        comment_hash=_thread_digest(trusted),
        comment_watermark_id=max([*ids, watermark or 0]) or None,
    )


def _trusted_thread(read: list, state: PinnedState) -> list:
    """The comments of one thread read a late fingerprint is allowed to count.

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
        for issue_comment in read
        if _formats.whole_number(getattr(issue_comment, "id", None))
        and not _content_hash._is_hidden_comment(
            issue_comment, orchestrator_ids,
        )
    ]


def _partitioned(
    trusted: list, state: PinnedState, generation: LateGeneration,
) -> tuple[list, list, list]:
    """Split one trusted run into what is counted, held back, and a reply.

    The counted prefix is what the recorded baseline folded in: the comments
    at or below the generation's own watermark, and none at all for a
    generation that has not taken one. A REPLY is a comment past a floor of
    its own, and what sits between the two -- past the watermark, at or below
    the floor -- is held back: conversation nothing has consumed, which is
    still no answer to the park that raised the floor over it.

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
    never been acted on by anything. The one exception is a park's own
    notice, which moves it past every comment written before the notice went
    out -- and that is exactly the held-back run, which is why it is
    reported rather than dropped.

    A generation that has not taken its baseline holds nothing back HERE,
    because where its counted prefix ends is not this reading's to say: a
    park can already stand over it -- a spent budget's, taken before the
    first late tick -- but what the first baseline counts is
    `late_issue_baseline`'s decision, which stops at what the issue-wide
    requirements baseline covers and counts nothing where none is recorded.
    Its callers take that baseline first and read the thread again against it,
    and it is that second reading whose held-back run is withheld guidance.
    """
    watermark = generation.comment_watermark_id
    held_from = watermark or 0
    floor = held_from
    acted = state.get(_LAST_ACTION_COMMENT_ID)
    if _formats.whole_number(acted) and acted > floor:
        floor = acted
    if generation.title_body_hash is None or generation.comment_hash is None:
        held_from = floor
    return (
        [
            issue_comment for issue_comment in trusted
            if watermark is not None and issue_comment.id <= watermark
        ],
        [
            issue_comment for issue_comment in trusted
            if held_from < issue_comment.id <= floor
        ],
        [issue_comment for issue_comment in trusted if issue_comment.id > floor],
    )


def _thread_digest(trusted: list) -> str:
    """The digest of one trusted comment run, in the order it was posted."""
    return _identity.comment_fingerprint(
        issue_comment.body or "" for issue_comment in trusted
    )
