# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""One late adjudication, from the pull-request hold to the run it settles.

`late_admission` owns the pre-run gates, `late_attempt` the durable attempt
and its unspent accounting, `late_execution` the fresh run, and
`late_completion` the post-run owner guard and settlement. This owner keeps
their order together with park retirement, content reconciliation, and reuse.

The coordinator an oversized committed candidate is adjudicated by. What puts
an issue in front of it is the size gate at the clean-committed pre-publication
seam, and what reaches it is the first question a `decomposing` tick asks: a
record carrying a live generation belongs to this owner entire, and no step of
the initial decomposition runs for it. What a finished reply decides is the
`late_verdict` owner beside it, and what any completion leaves on the record
is `late_outcome` beside that.

The order is the contract, and each step persists what it reached before it
acts. A generation that is not a live oversized one is not this owner's
business at all. Past that, a standing spent-budget park stops the tick where
it is: what it is waiting on is a human deciding to spend more of this issue's
day on the candidate, and no step below is that -- so the park is asked ahead
of the evidence probe, the hold, and the content settlement, and while it
stands nothing is proved, reconciled, read, or spawned. Past THAT, the pull
request standing over the candidate is held BEFORE anything is spawned -- the
plan one a discussion left behind where the generation was entered before
publication, and the implementation one the work is already on where it was
entered past it -- because the hold is what stops a human from merging a
change while the question of whether it should exist as one issue is still
open. So a hold that could not be reconciled parks and spawns nothing, and
every retry re-reconciles the same pull request rather than mutating it
again. Then a result already recorded for this cycle, generation, and exact
commit short circuits the spawn entirely: an agent that finished is not paid
for twice because the tick that read its answer died before acting on it, and
a second run is free to decide differently. Either way, the park a previous
attempt left is retired the moment the hold reconciles -- that attempt is the
answer to it, and a stale `awaiting_human` would go on to silence the
announcement a question verdict earns, whether the question came from this run
or from a recorded one whose own announcement never landed.

What the humans have said since the candidate was frozen is settled next, and
deliberately before that short circuit rather than after it: an answer to a
categorized question has to be able to drop the recorded outcome, and a
recorded outcome consulted first would suppress the very spawn the answer
earns. It is also where the whole tick can end -- requirements that moved park
the candidate without discarding it, and guidance that resumes the developer
re-freezes and re-measures the candidate this call was about, so there is
nothing left for the same tick to adjudicate. Everything that owner stages, it
persists, which is what lets the retired park be handed on rather than written
twice.

Past all of that, what comes back is the whole outcome rebuilt from the record
-- the children a split named included -- and whatever that answer still owed
the issue is reconciled instead of re-earned.

Every completed run goes through one more gate before anything acts on what it
left: the owner is read again. This call began by fetching an issue and then
spent minutes to hours running an agent, so the snapshot it is holding cannot
say whether a human has closed the issue since -- and publishing, snapshotting,
superseding, activating, or even announcing on the strength of it would act on
an issue nobody wants. It is asked of every completion, a question and a
timeout included, since a closure during one of those strands the same
generation and the same hold. A read that fails records itself on the
generation, which is why the very first thing this call does is reconcile one
an earlier tick left owed -- ahead of the live-generation gate, because the
state that gate routes past is exactly where such a read gets stranded. What
the read costs each of the three answers is the `late_owner` owner's; what a
verdict past it EARNS is `late_settlement`'s -- a `single` the park a human's
decision is owed on, and the settlement such a decision would license runs
through the reconciliation, proof, push, and handback owners beside it; and the
transaction
a cleared `split` becomes -- the snapshot every child is cut from, the children
themselves, the supersession of the pull request the candidate stands on, and
the cleanup obligation left behind -- is `late_transaction`'s, which this owner
reaches only through the guarded handoff that read carries.

Nothing gets that far on a generation that cannot be acted on. The prompt, the
hold, and every record afterwards are derived from the frozen fields, so the
identities and both commits are proved before a pull request is touched or an
agent is started: a candidate whose base was never recorded produces a diff
against nothing, and finding that out from a refused telemetry record means
the run has already been paid for.

Everything after the spawn is the shared post-run contract every other stage
runs: a `paused` label applied mid-run wins over the whole disposition and
leaves durable state exactly as the prior tick left it, a timeout parks, and
an interrupted run is dropped without being interpreted. The usage fold, the
retry budget, and the tracked spawn are the ones the rest of the workflow
already uses -- late adjudication spends the same per-issue budget as any
other decomposing run and is attributed to the same stage. "Leaves durable
state exactly as the prior tick left it" is what makes the pre-spawn write
the one place accounting is held back: the late identity goes out before the
agent starts, the retry slot does not, and a declined run therefore costs the
issue nothing.

One check has no counterpart in the initial mode, because the initial
decomposer runs in a scratch checkout and this one does not. The late
adjudicator reads the frozen candidate in the developer's OWN worktree, and
the CLI it runs under can write whatever it likes there whatever the prompt
says. So the candidate is proved unmoved and the tree proved clean before the
reply is read at all: an agent that committed over the evidence, or left
changes beside it, has contaminated the one artifact every later step acts on,
and its verdict is worth nothing next to that.
"""
from __future__ import annotations

import logging

from github.Issue import Issue

from orchestrator import config
from orchestrator.github.client import GitHubClient
from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.late_split import state as _late_state
from orchestrator.workflow.stages.decomposition import (
    late_admission as _late_admission,
    late_completion as _late_completion,
    late_execution as _late_execution,
    late_guidance as _late_guidance,
    late_outcome as _late_outcome,
    late_parks as _late_parks,
    late_session as _late_session,
)
from orchestrator.workflow.stages.decomposition.late_models import (
    _LateAdjudicationRun,
    _LateContext,
)

log = logging.getLogger("orchestrator.workflow")


def _adjudicate_late_generation(
    gh: GitHubClient,
    spec: config.RepoSpec,
    issue: Issue,
    state: PinnedState,
) -> _LateAdjudicationRun:
    """Adjudicate this issue's recorded late generation, if it has a live one.

    The whole late question in one call: hold the pull request the candidate
    stands on, settle what the humans have said since the candidate was
    frozen, then reuse a completed answer or spawn for a new one and record
    what it decided. Nothing is
    published here and no label is written -- the caller owns what a verdict
    earns.
    """
    context = _LateContext(
        gh=gh,
        spec=spec,
        issue=issue,
        state=state,
        generation=_late_state.read_late_generation(state),
    )
    blocked = _late_admission._blocked_before_running(context)
    if blocked is not None:
        return _late_outcome._finished(context, blocked)
    retired = _late_parks._retire_park(context)
    settled = _late_guidance._reconcile_late_content(context)
    if settled.disposition is not None:
        return _late_outcome._finished(context, settled.disposition)
    retired = retired and not settled.persisted
    recorded = _late_session._read_late_run(state)
    if recorded.answers(context.generation):
        log.info(
            "issue=#%d late generation %d already decided as %s; not "
            "spawning a second adjudication",
            issue.number, context.generation.generation, recorded.verdict,
        )
        return _late_completion._guarded(
            context, _late_outcome._reused(context, recorded, retired=retired),
        )
    return _late_execution._run_and_decide(context)
