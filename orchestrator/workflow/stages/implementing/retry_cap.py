# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The spent-budget park a dev tick meets, and the one reply that lifts it.

An `implementing` tick has three roads that would walk straight past a park,
and each of them is right for the park it was written against. The generic
`/orchestrator continue` classifier refuses a command that carries no
guidance, because the parks it knows about are waiting for words. The drift
check hands an edited body to the locked session, because requirements that
moved have to reach whoever is writing the code. The awaiting-human resume
reads any trusted reply as the answer the issue was stopped for, because that
is what an agent's question is waiting on.

None of the three is an answer to THIS park. What its notice asked for is a
human deciding to spend more of this issue's day on it -- and a body edit, a
setting an operator changed, and "any update?" are none of them, while the
classifier would refuse the one command that IS one. So the park is asked
ahead of all three, and while it stands the tick ends there. Nothing is
spawned and nothing is written, which is what leaves the pinned session and
its spec, the recorded pull request, the commit an approval still owes a push
for, and a late generation's whole record exactly as the park found them. The
refusal is still recorded, because a park nobody can see going on refusing is
one an operator reads as a workflow that stopped for no reason.

The one thing that lifts it is a trusted `/orchestrator continue`: the renewal
the notice itself asks for, and the only reading of a thread that means "spend
another attempt here". The command is taken with whatever else the comment
carries -- a decision that arrives with an explanation is still the decision,
and the explanation reaches the fresh implementer through the prompt's own
comment context -- while an untrusted account's copy of it buys nothing, since
what it would buy is agent time on somebody else's word.

What one command buys is one attempt, and a FRESH one. The grant is durable
before the spawn and the spend is not, so a tick that dies -- or a run a pause
or a shutdown declines -- between the two leaves the attempt where the human
put it. Everything else that could run an agent stands down for it: the
body-edit resume passes no gate, and the session that spent the budget is
retired here, since the spawn pins an id of its own only when the run hands
one back.
"""
from __future__ import annotations

import logging

from github.Issue import Issue

from orchestrator.github.client import GitHubClient
from orchestrator.github.comments import filter_trusted
from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.engine import (
    messages as _messages,
    retry_budget as _retry_budget,
    retry_notices as _retry_notices,
    retry_park_state as _retry_park_state,
    retry_values as _retry_values,
)
from orchestrator.workflow.stages.implementing import (
    session as _session,
    state as _state,
)

log = logging.getLogger("orchestrator.workflow")


def _park_owns_the_tick(
    gh: GitHubClient, issue: Issue, state: PinnedState,
) -> bool:
    """Whether a standing retry-cap park stops this tick where it is.

    True is the whole tick: the caller returns, having neither classified a
    command, read a body edit, nor resumed a session. False means either that
    this issue is not parked on its budget at all, or that a human has just
    bought it another attempt -- and on that second answer the grant is
    already durable, so the fresh spawn below spends something the next tick
    would find again if this one dies before reaching it.

    What runs AHEAD of this question is not about the park: a merged pull
    request and a closed issue end the issue whether or not one stands, and a
    hard-skipped issue reaches no handler at all. So the tick can be over
    before this is asked, and a poll that leaves no record of the park behind
    is not a park that lifted.

    A park that still owes the thread its sentence is held before any of that
    is asked. The stage-entry replay is what says that sentence, and saying it
    moves the response boundary past everything written under the old one --
    so while the obligation stands, a command on the thread is a command
    written before the question was asked. The replay leaves the obligation
    standing for exactly one reason, an unreadable thread, and a second read
    taken here is as likely to succeed as the first was to fail: read clean,
    it would buy an attempt with words nobody wrote in reply and clear the
    notice they were owed on the way out.
    """
    if not _retry_park_state._park_stands(state):
        return False
    if _park_is_explained(issue, state):
        if _continuation_is_bought(gh, issue, state):
            gh.write_pinned_state(issue, state)
            return False
        log.info(
            "issue=#%d stands on a spent spawn budget; holding it until a "
            "trusted /orchestrator continue buys another attempt",
            issue.number,
        )
    _retry_notices._emit_phase(
        gh, issue, state, _retry_values.RetryCapPhase.STANDING,
    )
    return True


def _park_is_explained(issue: Issue, state: PinnedState) -> bool:
    """Whether the thread has been told what this park is for.

    Asked before the thread is read for an answer, because an unsaid sentence
    means the question has not been put yet -- and what the delivery does when
    it finally lands is move the response boundary past every comment written
    under the old one. Read for a command first, the same words would buy an
    attempt and then be consumed by the notice explaining why the issue had
    stopped.
    """
    if _retry_park_state._owed_notice(state) is None:
        return True
    log.info(
        "issue=#%d has still to be told what its retry-cap park is for; "
        "holding it rather than reading a command written before the "
        "question as an answer to it",
        issue.number,
    )
    return False


def _continuation_is_bought(
    gh: GitHubClient, issue: Issue, state: PinnedState,
) -> bool:
    """Renew the budget if the thread carries the command that renews it.

    The command is looked for across the whole unread batch rather than in
    one comment of it, and the comment that carries it may carry words too.
    Both follow from what this park is: nothing here can pay for a developer,
    so guidance beside the command is not an alternative reading of the thread
    to be preferred over it -- and a refused tick consumes nothing, so a rule
    that wanted the command alone would let one "on it, give me an hour" stand
    above the watermark refusing every command written after it.

    A grant consumes the whole batch it was read out of, up to the last
    TRUSTED comment exactly as the resume beneath this does. Those comments
    are this park's answer, and the words among them reach the fresh spawn
    through the implement prompt's own comment context rather than through a
    watermark. What is left unconsumed is an outsider's, which the next tick
    filters out again.

    The dev session goes with the park. What the attempt buys is the fresh
    spawn the budget refused, and that spawn pins an id of its own only when
    the backend hands one back -- so an id left standing here is one a reply
    after a timeout or a question would resume, replaying the conversation
    that ran out of budget instead of the one a human paid for. The spec
    stays: a fresh spawn still has to land on the CLI this issue is locked to.
    Taken here so the write that lifts the park leaves durable state saying
    what is true of it; the spawn road asks the same question again for a
    grant that reaches it from anywhere else (`spawn._charge_fresh_spawn`).

    Mutates in memory only. The caller writes, so the grant, the retirement,
    and the watermark that says which words bought them land in one write
    rather than three.
    """
    answered = _trusted_replies(gh, issue, state)
    if not _messages._parse_orchestrator_continue(answered):
        return False
    log.info(
        "issue=#%d was continued by a trusted operator command; granting one "
        "more implementer attempt", issue.number,
    )
    state.set(
        _state._LAST_ACTION_COMMENT_ID,
        max(reply.id for reply in answered),
    )
    _session._drop_poisoned_dev_session(state)
    _retry_budget._grant_continuation(gh, issue, state)
    return True


def _trusted_replies(
    gh: GitHubClient, issue: Issue, state: PinnedState,
) -> list:
    """What trusted humans have said since this park consumed the thread.

    A read that could not be taken answers nothing said, which holds the park
    for the tick. The two failures are not symmetric: a park held one poll too
    long is answered by the next read, while a grant handed out on a thread
    nobody could read would spend an attempt no human asked for.
    """
    try:
        thread = gh.comments_after(
            issue, state.get(_state._LAST_ACTION_COMMENT_ID),
        )
    except Exception:
        log.exception(
            "issue=#%d could not be read for the command that lifts a "
            "retry-cap park; holding the park this tick",
            issue.number,
        )
        return []
    return filter_trusted(thread)
