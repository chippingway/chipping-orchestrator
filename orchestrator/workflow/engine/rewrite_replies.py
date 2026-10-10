# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The operator replies an auto-rebase attempt's park was answered with, and which of them are the attempt's.

Every `auto_base_rebase_*` notice asks for a reply, and the base sync reads
one for its arrival alone (`git/base_sync/eligibility.py`): any trusted
comment past the park's notice lets the attempt go again. What the reply SAYS
is a different question, and it is the late adjudication's to ask when the
replay is handed to one: a trusted comment it has not counted is guidance,
and guidance resumes the developer over a candidate nobody has adjudicated.
So the reply has to be told apart there. One that asks for the retry and
nothing else -- a bare `/orchestrator continue`, or a bare "retry", "try
again", "please retry" -- is the attempt's, spent with it; one that says
anything more is a human's words, a requirement or a decision, and stays
exactly where the late road reads it.

What spending a retry acknowledgment means is that the adjudication will not
read it again. It is recorded read where that reading comes from: the shared
`last_action_comment_id`, past which a comment is fresh, and the issue-wide
`user_content_hash`, which a generation's first late baseline counts comments
up to (`stages/decomposition/late_issue_baseline.py`) and short of which one
is withheld guidance. Only the leading run of acknowledgments is spent, since
a baseline covers a prefix of the thread and the first comment of guidance is
where it has to stop; and the baseline moves only where it already reproduces
over the thread up to the watermark the replies were written past -- short of
that, words nobody read stand before them, and folding the replies in would
fold those in too. It reproduces in either spelling the drift check accepts:
a baseline the legacy algorithm wrote counted a bare `/orchestrator continue`,
and is recognized as covering the same thread the current one does. What is
written past it is the current spelling, as that check normalizes a legacy
baseline it recognizes.

Recorded in the write that already spends the reply, so no crash can split
the two: the rebase's anchor write, which moves the watermark past the reply
that let it start (`git/base_sync/startup.py`, asked from
`base_rewrite`); the gate's write on the recovery's retry, which takes the
reply's park down (`rewrite_retry`); and the handoff's, which retires a park
the attempt's road left together with whatever answered it
(`rewrite_takeover_parks`) -- and, for a reply that only arrives after that
handoff, the dispatcher's own write ahead of the adjudication's first reading
of the thread, which that owner makes too.
"""
from __future__ import annotations

import itertools
import logging
import re
from dataclasses import dataclass, replace

from github.Issue import Issue

from orchestrator.github.client import GitHubClient
from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.engine import (
    comments as _comments,
    content_hash as _content_hash,
    messages as _messages,
    prompt_delivery as _prompt_delivery,
)
from orchestrator.workflow.late_split import formats as _formats

log = logging.getLogger("orchestrator.workflow")

_FLOOR = _prompt_delivery.PINNED_LAST_ACTION_COMMENT_ID
_BASELINE = _prompt_delivery.PINNED_USER_CONTENT_HASH

# The two marks a spent retry is recorded read on, which a write spending one owns.
REPLY_FIELDS = (_FLOOR, _BASELINE)

# The whole of a reply that asks for the retry its park offered and nothing
# else, its whitespace collapsed. A word beside it is no longer only a retry.
_RETRY_ONLY = re.compile(
    r"(?:please[ ,]+)?(?:re-?try|try again)(?:[ ,]+please)?[.!]*",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class AttemptReplies:
    """The replies that answered an attempt's park: every trusted comment past `after`, through `through`.

    `through` None is every one the thread carries, which is what a park the
    handoff itself retires was answered with.
    """

    after: int | None
    through: int | None = None

    @classmethod
    def past(cls, state: PinnedState) -> AttemptReplies:
        """Every reply past the shared watermark `state` carries -- all of them where none whole is recorded."""
        floor = state.get(_FLOOR)
        return cls(after=floor if _formats.whole_number(floor) else None)


def released_by(state: PinnedState, through: int | None) -> AttemptReplies | None:
    """The replies a road the reply `through` released was answered with, or None where no reply did.

    Asked before that road writes anything, while `state` still carries the
    watermark those replies were written past.
    """
    return None if through is None else replace(AttemptReplies.past(state), through=through)


def records_the_retry(gh: GitHubClient, issue: Issue, state: PinnedState, replies: AttemptReplies | None) -> None:
    """Stage the retry acknowledgments among `replies` read, for the caller's own write to land.

    The leading run of them, up to the first reply that says anything more,
    on the shared watermark -- and on the requirements baseline where that
    already covers the thread up to the watermark they were written past.
    """
    if replies is None:
        return
    read = list(issue.get_comments())
    answered = _replies(gh, issue, state, replies, read=read)
    spent = list(itertools.takewhile(_acknowledges_the_retry, answered))
    if not spent:
        return
    newest = spent[-1].id
    if newest > (AttemptReplies.past(state).after or 0):
        state.set(_FLOOR, newest)
    covered = (
        _baseline_through(issue, state, read, replies.after),
        _baseline_through(issue, state, read, replies.after, legacy=True),
    )
    if state.get(_BASELINE) in covered:
        state.set(_BASELINE, _baseline_through(issue, state, read, newest))
    log.info(
        "issue=#%d records %d retry acknowledgment(s) to its auto-rebase attempt as read with it",
        issue.number, len(spent),
    )


def replied_past_the_watermark(gh: GitHubClient, issue: Issue, state: PinnedState) -> bool:
    """Whether a trusted human has written anything past the shared reply watermark."""
    return bool(_replies(gh, issue, state, AttemptReplies.past(state)))


def _acknowledges_the_retry(reply) -> bool:
    """Whether one reply asks for the retry and says nothing else a developer could act on."""
    if _messages._is_bare_orchestrator_continue(reply):
        return True
    written = " ".join((reply.body or "").split())
    return _RETRY_ONLY.fullmatch(written) is not None


def _replies(
    gh: GitHubClient, issue: Issue, state: PinnedState, replies: AttemptReplies, *, read: list | None = None,
) -> list:
    """The trusted comments `replies` names, in thread order, as the adjudication's own reading would trust them.

    Cut from `read` where the caller holds the thread already, and from a
    read of its own otherwise.
    """
    ours = _comments._orchestrator_ids(state)
    return [
        reply for reply in gh.comments_after(issue, replies.after, comments=read)
        if not _content_hash._is_hidden_comment(reply, ours)
        and (replies.through is None or reply.id <= replies.through)
    ]


def _baseline_through(
    issue: Issue, state: PinnedState, read: list, last: int | None, *, legacy: bool = False,
) -> str:
    """The requirements baseline over the title, the body, and the thread `read` through comment `last`, if any.

    `legacy` spells it as the algorithm that counted a bare continue did.
    """
    through = [seen for seen in read if seen.id <= (last or 0)]
    return _content_hash._compute_user_content_hash(
        issue, _comments._orchestrator_ids(state), include_bare_continue=legacy, comments=through,
    )
