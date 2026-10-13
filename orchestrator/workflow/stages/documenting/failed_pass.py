# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What makes a docs pass one that did not finish, and the record that keeps one from going unseen.

A pass fell short of success where a tool step was left unfinished, where the
backend kept a failure record of the run -- Antigravity's error, cancelled,
interrupted, or missing terminal result -- or where Antigravity's own process
exited nonzero behind a terminal that said it succeeded (`_fell_short`). None
of what such a run left is a finished pass: not its commit, not the tool calls
it completed, not a `DOCS: NO_CHANGE` it wrote. The disposition parks it.

Several ticks end before any disposition and write nothing of it: a live pause,
and a quota retirement the comment would not take, which withholds the tick's
state. Whatever the pass left would then be read by the next tick as a branch
nothing failed on -- its commit published by the recovered-commit shortcut, or
a fresh pass launched -- with no human having seen the failure. So the record
is landed BEFORE the launch rather than after the failure is known, where a
write that does not land could lose it: every Antigravity docs launch first
lands `docs_launched_sha`, the head it is launched on, alone through the
guarded commit over a fresh reading of the comment, and a launch that record
did not land on is not made (`_armed`). Only Antigravity runs can fall short
here, so no other backend's launch pays the write.

The record stands until the run's outcome is known not to need it: the
disposition drops it in whatever write records the outcome, and a paused pass
that succeeded or a run no disposition may read -- a shutdown-sweep kill, a
launch never made -- drops it alone (`_settle`). A pass that fell short under
a pause, or a tick a quota retirement withheld, writes nothing and leaves it
standing, as does a poller that died mid-run. The next tick that is not
answering a park and finds it takes the park the pass earned instead of the
recovered or fresh shape (`_unfinished_pass_owed`); that park, a stamped docs
verdict, and a drift unwind that resets the commits away each drop it
(`_forget`). The base refresh ahead of every handler reads it too, and holds
the branch still while it stands (`git/base_sync/frozen`): rebased first, the
pass's commit -- or with none, the base -- would be pushed and the issue
handed back to review before that park could be taken. A drop that does not
land leaves the record standing, so that next tick parks: a pass that
succeeded can be asked about once more, but one that failed is never published
unseen.
"""
from __future__ import annotations

import copy
import logging

from orchestrator.agents.models import AgentResult
from orchestrator.github.pinned_state import PinnedState
from orchestrator.observability.usage import protocol as _protocol
from orchestrator.workflow.engine import pinned_commit as _pinned_commit, pinned_commit_models as _commit_models
from orchestrator.workflow.stages.documenting import (
    models as _models,
    state as _state,
)
from orchestrator.workflow.stages.implementing import session_read as _session_read

log = logging.getLogger("orchestrator.workflow")


def _fell_short(ctx: _models._DocumentingContext, agent_result: AgentResult) -> bool:
    """Whether the run ended short of the success a docs verdict is stamped on, whatever it left.

    An unfinished tool step is one shortfall, and a failure record the backend
    kept is another: Antigravity normalizes an error, cancelled, interrupted,
    or missing terminal result to a failure and records it whatever the run did
    first, so a commit, completed tool calls, or a response carrying
    `DOCS: NO_CHANGE` ahead of the failing terminal is still a run that failed.
    The third is an Antigravity process that exited nonzero behind a terminal
    that said it succeeded, which keeps the response as its final message and
    no failure record. The recovered commit's synthesized result carries none
    of these, and whether that shortcut may publish at all is decided before it
    is synthesized (`_unfinished_pass_owed`).
    """
    if agent_result.unfinished_steps or agent_result.terminal_failure is not None:
        return True
    return _launches_antigravity(ctx) and agent_result.exit_code != 0


def _armed(ctx: _models._DocumentingContext, head: str) -> bool:
    """Land `docs_launched_sha` as `head` ahead of an Antigravity docs launch; whether the launch may be made.

    Any other backend's launch is made unrecorded, since none of its runs can
    fall short here. A record that did not land -- refused, unreadable, or
    sent and never answered -- holds the launch, and the tick returns writing
    nothing; one that landed unanswered may be found by the next tick, which
    parks for a continue rather than launch over it.
    """
    if not _launches_antigravity(ctx):
        return True
    return _landed(ctx, head)


def _settle(ctx: _models._DocumentingContext) -> None:
    """Drop `docs_launched_sha` alone, for a tick that writes nothing else and whose run did not fall short.

    A tick whose state a quota retirement withheld writes nothing over the
    comment at all, so the record stands for the next tick to park on.
    """
    if ctx.state.withheld or ctx.state.get(_state._LAUNCHED_DOCS_SHA) is None:
        return
    _landed(ctx, None)


def _unfinished_pass_owed(ctx: _models._DocumentingContext) -> bool:
    """Whether a tick that is not answering a park has to take the one a launched pass earned.

    A standing `docs_launched_sha` is a launch whose outcome nothing recorded
    and nothing proved finished: it fell short under a pause, a quota
    retirement withheld its tick, or the poller died with it out.
    """
    return ctx.state.get(_state._LAUNCHED_DOCS_SHA) is not None


def _forget(state: PinnedState) -> None:
    """Drop `docs_launched_sha` on `state`, for the write that records what answers for the launch.

    Asked before it is dropped, so an issue that never carried one is not
    given the key to carry a null under.
    """
    if state.get(_state._LAUNCHED_DOCS_SHA) is not None:
        state.set(_state._LAUNCHED_DOCS_SHA, None)


def _launches_antigravity(ctx: _models._DocumentingContext) -> bool:
    """Whether the pinned developer command, the one every docs pass runs under, is Antigravity's."""
    return _session_read._read_dev_session(ctx.state)[1] == _protocol.AGY


def _landed(ctx: _models._DocumentingContext, head: str | None) -> bool:
    """Commit `docs_launched_sha` as `head` over a fresh reading, owning that field alone; whether it landed.

    Taken onto the tick's state once it lands, so the write the tick goes on
    to make carries the comment's own spelling of it.
    """
    read = _commit_models.PinnedCommit.capture(ctx.state)
    fresh = _pinned_commit.reread(ctx.gh, ctx.issue, read)
    if isinstance(fresh, _commit_models.CommitOutcome):
        outcome = fresh
    else:
        staged = PinnedState(comment_id=fresh.comment_id, state_data=copy.deepcopy(fresh.data))
        staged.set(_state._LAUNCHED_DOCS_SHA, head)
        guard = _commit_models.PinnedCommit.capture(fresh, owned=(_state._LAUNCHED_DOCS_SHA,))
        outcome = _pinned_commit.commit(ctx.gh, ctx.issue, guard, staged.data)
    if outcome.status is not _commit_models.CommitStatus.COMMITTED:
        log.warning(
            "issue=#%d could not record docs_launched_sha=%r on the pinned comment (%s)",
            ctx.issue.number, head, (outcome.refusal or outcome.status).value,
        )
        return False
    ctx.state.set(_state._LAUNCHED_DOCS_SHA, head)
    _pinned_commit.takes_in(ctx.state, outcome.reading.data, (_state._LAUNCHED_DOCS_SHA,))
    return True
