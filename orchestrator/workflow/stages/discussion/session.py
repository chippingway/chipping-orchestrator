# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What keeps a multi-round discussion on one agent, and what each round is fed.

Every helper here exists because something between two rounds is allowed to
change underneath the conversation. The configured `DECOMPOSE_AGENT` can be
flipped, so the spec that actually ran is pinned and read back rather than
re-resolved -- and the session id travels with it, because a conversation is
only resumable on the CLI that opened it. The issue thread can gain an
untrusted reply, so one filter drops those before they can steer the agent OR
move the watermark. And the backend can hand back no session id at all, which
is why both prompt choices sit together: a round with nothing to resume gets
the full conversation rebuilt instead, since a followup handed to a fresh agent
would arrive with no issue body, no frontier, and no design to fold an answer
into. Both are handed the plan path this stage would publish, spelled by its
own key owner rather than by the prompt: a round with nothing cached can still
be the round the humans confirm on, and a path the agent is told that differs
from the path the publication check looks for would refuse every plan written
to it.

Reading the replies and consuming them are deliberately separate calls, and
`run` puts the round's provenance write between them. Nothing is consumed until
a round is actually being opened on it, so a tick that finds a reply and then
declines to spawn leaves the answer waiting rather than swallowing it; and the
advance is staged in memory afterwards, so it reaches GitHub only with the park
that reports what the round made of it. A round withheld by a mid-run pause or
cut short by a crash is therefore replayed against the same replies -- the same
promise the anchor beside it makes about the same round's commits.

What that advance is measured over is what the round's prompt was BUILT from,
never the thread as it stands when the park is written. Minutes pass inside an
agent run and a human can answer twice in them, so a ceiling taken afterwards
would record a comment nothing has read -- and this stage never reads a comment
twice, so it would be read never. The one thing that then has to be recognized
without a watermark is the stage's own posted analysis, which `engine/comments`
already stamps and records for exactly this: an id list for the comments still
in its bounded cap and a hidden body marker for the ones evicted from it.
Author-login matching is the alternative both readers refuse, since a PAT
shared with a human's account would swallow that human's real replies as bot
noise.
"""
from __future__ import annotations

from orchestrator import config
from orchestrator.github.comments import filter_trusted
from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.engine import (
    comments as _comments,
    conversation_prompts as _conversation_prompts,
    prompt_context as _prompt_context,
)
from orchestrator.workflow.stages.discussion import models as _models, state as _state


def _locked_discussion_session(
    state: PinnedState,
) -> _models._DiscussionSession:
    """Return the agent identity this issue's discussion is locked to.

    Mirrors `_read_question_session` / `_read_decomposer_session`: the spec
    pinned at the first spawn wins over the current config on every round
    after it, and the session id recorded beside it travels with it. A round
    can be replayed -- a mid-run pause, an interruption, or a crash ends one
    with no disposition and the next tick opens it again -- and a human reply
    opens one deliberately; re-reading `DECOMPOSE_AGENT` at either would let
    an env flip between two ticks move a conversation onto a backend and
    argument set that never ran on this issue, hand it a session id no CLI on
    that backend has ever heard of, and then overwrite the pin with them.

    Legacy bare-backend values (`"codex"` / `"claude"`) re-parse to
    `(backend, ())` and round-trip cleanly. Only an issue that has never
    spawned a discussion agent falls through to the configured decomposer,
    and it is also the only one with no session to resume rather than one a
    round simply failed to hand back.
    """
    stored = state.get(_state._DISCUSSION_AGENT_KEY)
    if stored:
        agent_spec = str(stored)
        backend, extra_args = config._parse_agent_spec(
            _state._DISCUSSION_AGENT_KEY, agent_spec,
        )
        return _models._DiscussionSession(
            agent_spec=agent_spec,
            backend=backend,
            extra_args=extra_args,
            session_id=_recorded_session_id(state),
        )
    return _models._DiscussionSession(
        agent_spec=config.DECOMPOSE_AGENT_SPEC,
        backend=config.DECOMPOSE_AGENT,
        extra_args=config.DECOMPOSE_AGENT_ARGS,
        session_id=None,
    )


def _recorded_session_id(state: PinnedState) -> str | None:
    """The conversation a later round resumes, or None when there is none.

    An empty recorded id answers None rather than an empty string, so the one
    question everything downstream turns on -- is there a session to resume --
    has a single answer. Otherwise a round could be given the full prompt for
    having nothing cached while still being spawned as a resume of it.
    """
    session_id = state.get(_state._DISCUSSION_SESSION_KEY)
    return str(session_id) if session_id else None


def _new_trusted_replies(
    run: _models._DiscussionRun, thread: tuple | None = None,
) -> list:
    """Replies posted since the watermark that a round may be opened on.

    Untrusted authors are dropped before the caller can see a batch at all, so
    with `ALLOWED_ISSUE_AUTHORS` set an outsider's reply neither resumes the
    conversation nor moves the watermark: a batch that is entirely theirs reads
    as "nobody has answered yet", and one of theirs trailing a trusted answer
    is simply not part of what the round is opened on.

    The stage's own comments go with them. Every park posts one and the
    watermark is deliberately left below it -- that is what preserves a reply
    posted mid-run -- so without this filter a discussion would answer its own
    analysis on the very next tick and never stop.

    `thread` is the snapshot a full-context round was already assembled from,
    and passing it is what keeps that round's ceiling and its prompt derived
    from ONE read. Re-reading here instead would pick up whatever landed in
    between: shown to the agent by the earlier read and left above the
    watermark by this one, or the reverse, and either way sent again next tick.
    Only the caller with no snapshot to offer -- the turn-taking gate, which
    has no prompt yet -- reads the thread itself.
    """
    watermark = run.state.get(_state._LAST_ACTION_COMMENT_ID)
    if thread is None:
        thread = run.gh.comments_after(run.issue, watermark)
    posted_here = _comments._orchestrator_ids(run.state)
    return [
        comment
        for comment in filter_trusted(thread)
        if _unread_reply(comment, watermark, posted_here)
    ]


def _unread_reply(comment, watermark, posted_here: set[int]) -> bool:
    """True for a comment past `watermark` that this stage did not write.

    The watermark is re-applied rather than assumed because a snapshot handed
    in covers the whole thread, most of which a round has already read. The
    authorship half mirrors the in_review and validating feedback filters: the
    recorded id list is exact but bounded, and the body marker survives
    eviction from it. Both are grounds to DROP a comment, so a marker anyone
    can paste costs its author their own comment and nothing else.
    """
    if watermark is not None and comment.id <= watermark:
        return False
    body = getattr(comment, "body", None) or ""
    return not (
        comment.id in posted_here or _comments._ORCH_COMMENT_MARKER in body
    )


def _consume_replies(run: _models._DiscussionRun, replies: list) -> None:
    """Stage the watermark past the newest comment this round's prompt read.

    `replies` is that set, whichever shape the round took: the batch a resume
    quotes, or the whole trusted thread a full prompt rebuilds. Nothing beyond
    it is consumed, which is the point -- an outsider's comment and one posted
    while the agent was still running both stay above the mark, so the day the
    allowlist changes or the next tick comes round they are still there to be
    read.

    An empty set leaves the watermark alone. A round can legitimately have
    nothing to consume (an opening round on an issue nobody has commented on),
    and inventing a ceiling for it would mean guessing at a comment id that
    does not exist.
    """
    if not replies:
        return
    run.state.set(
        _state._LAST_ACTION_COMMENT_ID,
        max(reply.id for reply in replies),
    )


def _build_round_prompt(
    run: _models._DiscussionRun,
    session: _models._DiscussionSession,
    replies: list | None,
) -> _models._DiscussionPrompt:
    """Assemble what the round is asked, and what asking it has consumed.

    The two travel together because they have to agree: what the agent was
    shown is exactly what the round may record as read, and deriving the
    second anywhere but from the first leaves a comment on one side of the
    watermark and in front of the agent on the other.
    """
    if replies and session.session_id:
        return _models._DiscussionPrompt(
            text=_conversation_prompts._build_discussion_followup_prompt(
                replies, _state._plan_path(run.issue.number),
            ),
            consumed=tuple(replies),
        )
    return _build_full_context_prompt(run)


def _build_full_context_prompt(
    run: _models._DiscussionRun,
) -> _models._DiscussionPrompt:
    """Rebuild the whole conversation for a round with nothing cached.

    One read of the thread answers both halves: the text the agent gets and
    the replies that text has therefore answered. `comments_after` with no
    watermark is that read -- the whole thread minus the pinned-state comment,
    which is neither conversation nor reply.

    The stage's own analyses are retained in the text by recorded id, because
    this prompt is where the conversation is reconstructed for an agent that
    was not in it. A deployment that allowlists its humans and not its bot
    would otherwise hand a fresh agent the human's answers by number with the
    numbered questions they answer missing.
    """
    thread = tuple(run.gh.comments_after(run.issue, None))
    return _models._DiscussionPrompt(
        text=_conversation_prompts._build_discussion_prompt(
            run.spec,
            run.issue,
            _prompt_context._thread_text(
                thread, retained_ids=_comments._orchestrator_ids(run.state),
            ),
            config.default_repo_specs(),
            _state._plan_path(run.issue.number),
        ),
        consumed=tuple(_new_trusted_replies(run, thread)),
    )
