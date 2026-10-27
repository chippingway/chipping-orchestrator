# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""How much of the issue thread a developer prompt has been handed, apart from where a reply starts.

`last_action_comment_id` is the boundary a park waits above: everything past
it is a human's reply, and a resume delivers those replies whole and moves the
boundary over them. Plenty moves it with nothing delivered, though. The pickup,
the `ready` handoff, a disabled decomposition's handoff, and the relabel out
of a read-only conversation stand it past a thread nobody was handed, since
nothing on it is a reply to anything; a park stamps it at its own notice, over
whatever a human wrote while the agent was out; a grant consumes its command.
Read as delivery, every one of those would record unread input as answered.

So delivery is recorded on its own, as one stretch of the thread: the
comments numbered above `delivered_after_comment_id`, through
`delivered_through_comment_id`. Nothing but a prompt that quoted the thread
moves either. The implementer's first prompt quotes it whole but bounded,
dropping the oldest comments first, and its run records the stretch it
quoted (`records_delivery`): from the newest comment its excerpt cut -- or 0,
where it cut nothing -- through the newest it read that was quoted or is
nobody's input. The documenting resume's full prompt quotes it the same way
and records the same way, so a reply its excerpt cut stays unread while the
boundary it answered moves over it. Every settlement after that moves the
upper end from its own value (`prompt_delivery`), stopping below the first
omission above it, and only where it already reaches the boundary the settled
read began at -- below that, a park's stamp may stand over a reply the read
never saw. A road that moves the boundary over replies it read -- a resume
quoting chosen replies whole, a late consumption answering controls --
carries the upper end only where the thread, read again, shows nothing
between the two but those replies and nobody's input (`DeliveredThread.carry`);
a bounded park walking over posts of ours carries it only where it already
reaches the boundary (`reads_through`). A record carrying neither counts
nothing as delivered: no reader may take a missing field as feedback somebody
answered.

The PR-feedback readers ask it (`DeliveredThread`); parks and resumes never
do -- their question is whether a new reply exists, and the boundary still
answers that.

`known_through` sits here because every reader of the shared IssueComment id
space needs it: the two surfaces are read one after the other, and what a
watermark over both may cross is bounded by what those two reads prove
complete. A fix round settles that watermark over the comments it DELIVERED,
pull-request comments included, so its bound reads the thread once more
where the first bound would hold one of those below it
(`known_through_both`): left there, the comment is handed to a developer again
on every round.
"""
from __future__ import annotations

from dataclasses import dataclass

from github.Issue import Issue

from orchestrator.github.client import GitHubClient
from orchestrator.github.comments import is_trusted_author
from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.engine import (
    comments as _comments,
    messages as _messages,
    prompt_delivery as _prompt_delivery,
    run_grant_request as _run_grant_request,
)

# The newest issue-thread comment below the delivered stretch: one the first
# prompt's excerpt cut, or 0.
DELIVERED_AFTER = "delivered_after_comment_id"

# The newest issue-thread comment a developer prompt has been handed.
DELIVERED_THROUGH = _prompt_delivery.PINNED_DELIVERED_THROUGH

# What the floor reads as where the prompt that set it left nothing out.
_FROM_THE_BEGINNING = 0

_THREAD = _prompt_delivery.SURFACE_ISSUE_THREAD

# A road that quoted no reply whole vouches for none.
_NOTHING_QUOTED: frozenset = frozenset()


def _whole(recorded) -> int | None:
    """`recorded` where it is a comment id as its writers spell it, else None."""
    if isinstance(recorded, int) and not isinstance(recorded, bool):
        return recorded
    return None


def _answered(seen, ours: set) -> bool:
    """Whether a comment the reply boundary crossed is nobody's unread input.

    A post of ours, by the ledger or the hidden marker; an author the
    allowlist does not trust, whose words no feedback reader ever hands
    anybody; or a bare operator control -- a whole-comment `/orchestrator
    continue`, `add-agent-runs`, or `authorize-oversized` -- which carries no
    words for a developer, so a road answering it spends nothing anybody is
    owed. Prose around any of them is guidance, and is not answered here.
    """
    if seen.id in ours or not is_trusted_author(getattr(seen, "user", None)):
        return True
    if _comments._ORCH_COMMENT_MARKER in (getattr(seen, "body", None) or ""):
        return True
    return (
        _run_grant_request._is_bare_command(seen)
        or _messages._is_bare_orchestrator_continue(seen)
        or _messages._authorized_oversized_candidate(seen) is not None
    )


@dataclass(frozen=True)
class DeliveredThread:
    """The issue-thread comments a developer prompt has been handed: numbered above `after`, through `through`.

    Either one unrecorded covers nothing.
    """

    after: int | None
    through: int | None

    @classmethod
    def read(cls, state: PinnedState) -> DeliveredThread:
        """The delivered stretch `state` records."""
        after = _whole(state.get(DELIVERED_AFTER))
        return cls(after, _whole(state.get(DELIVERED_THROUGH)))

    def covers(self, comment_id: int) -> bool:
        """Whether the issue-thread comment `comment_id` has been in a developer prompt."""
        if self.after is None or self.through is None:
            return False
        return self.after < comment_id <= self.through

    def joins(self, after: int, through: int) -> bool:
        """Whether the stretch above `after` through `through` meets or overlaps this one."""
        if self.after is None or self.through is None:
            return False
        return after <= self.through and self.after <= through

    def recorded(self) -> tuple:
        """The ids this record names, each a comment that existed when it was written."""
        return (self.after, self.through)

    def reaches(
        self, boundary: int, gh: GitHubClient | None, issue: Issue | None, state: PinnedState,
        quoted: frozenset = _NOTHING_QUOTED,
    ) -> bool:
        """Whether nothing unread stands between this stretch and `boundary`.

        Answered without a read where the stretch already reaches it. Below
        it, the thread may hold comments some road crossed -- a park's own
        notice, or a thread an anchor or a park stamped over unread -- and
        with `gh` and `issue` the thread above the stretch is read to say
        which: every comment up to `boundary` has to be nobody's input, or one
        of the `quoted` comments a prompt handed a developer whole.
        """
        if self.after is None or self.through is None:
            return False
        if self.through >= boundary:
            return True
        if gh is None or issue is None:
            return False
        ours = set(_comments._orchestrator_ids(state)) | quoted
        crossed = gh.comments_after(issue, self.through, state_comment_id=state.comment_id)
        return all(_answered(seen, ours) for seen in crossed if seen.id <= boundary)

    def carry(
        self, through: int | None, gh: GitHubClient, issue: Issue, state: PinnedState,
        quoted: frozenset = _NOTHING_QUOTED,
    ) -> None:
        """Carry this stretch in `state` to `through`, where nothing unread stands between.

        For a road that moves the reply boundary over replies it read: every
        comment above the stretch up to `through` has to be one of the
        `quoted` replies its prompt handed a developer whole, or nobody's
        input -- ours, an outsider's, a bare control the road answered. The
        thread is read to say so, never taken on the road's word, so a reply
        a recovered notice was stamped over, or guidance a grant left owed,
        keeps the stretch below it while the boundary moves on.
        """
        if through is not None and self.reaches(through, gh, issue, state, quoted):
            state.set(DELIVERED_THROUGH, max(through, self.through))


def records_delivery(
    state: PinnedState, delivered: _prompt_delivery.PromptDeliverySnapshot,
) -> None:
    """Record what `delivered`, a prompt over the WHOLE issue thread, quoted of it.

    The excerpt drops the oldest comments first, so what it left out is the
    run up to the newest comment it omitted, one cut part-way included, and
    everything after that reached the prompt or is nobody's input -- a post of
    ours, an outsider's comment the excerpt filtered. The stretch runs to the
    newest of those, so a pickup above the thread it quoted is inside it and a
    settlement after the boundary standing there can carry it. A thread with
    no human comment on it is recorded all the same, as the stretch over our
    own posts: a stretch left unrecorded there would count no reply a later
    resume hands over as delivered. That stretch joins the one recorded where
    the two meet, and otherwise replaces it: a gap between them is comments no
    prompt quoted, and one stretch cannot leave them out.
    """
    read = delivered.delivered_inputs(_THREAD) + delivered.filtering_decisions(_THREAD)
    omitted = [entry.id for entry in delivered.bounded_excerpt_omissions(_THREAD)]
    floor = max(omitted, default=_FROM_THE_BEGINNING)
    through = max([floor, *(entry.id for entry in read)])
    prior = DeliveredThread.read(state)
    if prior.joins(floor, through):
        floor = min(floor, prior.after)
        through = max(through, prior.through)
    state.set(DELIVERED_AFTER, floor)
    state.set(DELIVERED_THROUGH, through)


def reads_through(state: PinnedState, through: int) -> None:
    """Move the reply boundary to `through` over posts of ours, carrying the delivered stretch with it.

    For a bounded park's walk, which crosses only the comments our ledger
    names. The stretch follows only where it already reaches the boundary
    the walk began at (`DeliveredThread.reaches`): the boundary may stand over
    comments a road crossed with nobody handed them -- an anchor's thread,
    what a park stamped its notice over -- and the stretch may not step over
    those to whatever comes after. A road that reads the thread as well
    carries the stretch itself (`DeliveredThread.carry`).
    """
    delivered = DeliveredThread.read(state)
    boundary = _whole(state.get(_prompt_delivery.PINNED_LAST_ACTION_COMMENT_ID))
    if boundary is not None and delivered.reaches(boundary, None, None, state):
        state.set(DELIVERED_THROUGH, max(through, delivered.through))
    state.set(_prompt_delivery.PINNED_LAST_ACTION_COMMENT_ID, through)


def known_through(first_read: list, *recorded) -> int | None:
    """The newest id a snapshot taken in two reads proves complete beneath, or None.

    The two IssueComment surfaces share one id space and are read one after
    the other, so a comment landing on the surface read first, after that
    read, is in neither read, while a comment numbered above it can land on
    the surface read second and be in the snapshot. What is certain is that
    every comment numbered at or below one that already existed when the
    first read began is in one of the two: the newest comment `first_read`
    carries, and every id in `recorded` -- ids a record named before either
    read, such as the ledger of our own posts, the delivered stretch, a
    persisted watermark, or the frozen record of a prompt this tick built.
    Anything in `recorded` that is not a whole comment id names nothing.
    """
    known = [comment.id for comment in first_read]
    known.extend(found for found in map(_whole, recorded) if found is not None)
    return max(known, default=None)


def known_through_both(gh: GitHubClient, issue: Issue, thread: list, conversation: list, *recorded) -> int | None:
    """The bound of a snapshot that read the issue `thread` first and the pull request's `conversation` second.

    Where every comment the second read carries is under `known_through`'s own
    bound, that bound is the answer and nothing more is read. Where one is
    above it, the thread is read again past its first read's newest comment,
    behind the second read: every comment created before that second read is
    then in one of the reads, so the bound rises to the newest either carried
    -- but stays below the first comment the thread read again finds, a reply
    that landed between the two reads and is in neither batch. Held there, the
    shared cursor never steps over it, and the next scan delivers it.
    """
    bound = known_through(thread, *recorded)
    if all(bound is not None and seen.id <= bound for seen in conversation):
        return bound
    newest = max((seen.id for seen in thread), default=None)
    landed = [seen.id for seen in gh.comments_after(issue, newest)]
    bound = known_through([*thread, *conversation], *recorded)
    return min(bound, min(landed) - 1) if landed else bound
