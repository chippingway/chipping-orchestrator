# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The park an oversized candidate no adjudicator could split waits in.

What a `single` verdict earns, split from the settlement beside it because
they are opposite answers to the same reading. A settlement is what a decision
to publish an oversized candidate unsplit licenses; this is what the workflow
does when nobody has made that decision, which is every verdict an adjudicator
reaches on its own. The command that makes it is `late_authorize`'s, and this
park's own sentence is where a human is told the command exists.

The whole of it is a durable claim and the sentence that claim owes the
thread. Nothing is published and nothing is taken back, so the wait costs the
issue one comment and no agent -- and everything a human would decide against
is left exactly where the adjudication put it, which is what makes a later
tick free.
"""
from __future__ import annotations

import logging
from dataclasses import replace

from orchestrator.workflow.stages.decomposition import (
    late_notice as _late_notice,
    late_park_state as _late_park_state,
    late_parks as _late_parks,
)
from orchestrator.workflow.stages.decomposition.late_models import (
    _LateAdjudicationRun,
    _LateContext,
    _LateDisposition,
)

log = logging.getLogger("orchestrator.workflow")

# What the issue is told an unsplittable oversized candidate is waiting for.
# It names the frozen commit and the reading that stopped it, because the
# generation carrying both is what a decision retires -- and it names what the
# adjudicator said stood in the way of a split, which is the one thing nobody
# can recover once the run is over. NAMES rather than carries: the explanation
# goes in on the way to the thread, so the durable half of this sentence stays
# the size of the sentence.
#
# What it leaves alone is worded for both sides of the gate. A candidate
# entered past publication stands on a pull request; one entered before it may
# stand on the plan pull request a discussion opened, or on none at all -- so
# the sentence promises a human that whichever of those this issue has is
# untouched, rather than telling them about one they do not have.
#
# It names both ways out, because they are the two answers and a human owed a
# decision is owed the shape of each: words that change the work, and the one
# command that publishes the change as it stands. The command is spelled
# against this candidate rather than left abstract, since what an
# authorization may license is exactly what somebody read.
#
# The quote comes LAST and on lines of its own, because what fills it is an
# agent's prose and a thread is markdown: text opening an HTML comment
# swallows everything after it, so a quote in the middle of this sentence
# would cost the human the instruction that follows it. Last, and blocked off
# where it is delivered, it can cost them nothing but itself.
_UNSPLIT_PARK = (
    "the late decomposer read this issue's committed candidate `{candidate}` "
    "as one change it could not split ({additions} added lines against a "
    "ceiling of {threshold}). Nothing was published. "
    "Publishing an oversized change unsplit is a decision for a human, so "
    "the commit, the worktree it is in, any held or existing pull request, "
    "and the recorded adjudication are all left exactly as they are, and no "
    "further decomposer is spawned against them. Reply with the change to "
    "make and the developer is resumed against it, or post "
    "`/orchestrator authorize-oversized {candidate}` as the entire comment "
    "and it publishes as it stands."
    "\n\nWhat it said stopped a split:\n\n{blocker}"
)


def _parked_single(
    context: _LateContext, finished: _LateAdjudicationRun,
) -> _LateAdjudicationRun:
    """Hand an oversized candidate no agent could split to a human.

    What the adjudicator answered is that this change stays one change, and
    that is the one answer it may not act on: the ceiling exists so unreviewed
    bulk does not reach a pull request, and an agent proposing to publish past
    it is the thing being guarded against rather than the grounds for waiving
    the guard. So the whole of what a settlement would have written -- the
    exemption, the approval the push is owed under, the push, the label -- is
    withheld, and the issue stops here.

    Nothing else is taken back either, and that is what makes the wait cheap.
    The commit stands in the worktree it was committed in, the generation
    stays live and oversized so the record still says which candidate is being
    asked about, whichever pull request this cycle held or was measured
    against keeps what was put on it, and the session and the recorded verdict
    stay where they are. A later tick reuses
    that verdict rather than paying for a second adjudicator, and the park it
    reaches is the one already standing.

    The verdict IS the answer, which is why the park is not one a fresh
    attempt supersedes: there is no retry that could decide differently
    without an agent, and no agent runs against a candidate this issue has
    already adjudicated. What ends it is a human, either way they can answer:
    guidance that changes the work, which resumes the developer and
    re-measures whatever comes back, or the authorization that publishes this
    candidate as it stands, which is `late_authorize`'s.

    What travels back is the outcome exactly as it was decided, wearing the
    disposition the park gave it. A park is not an absence of an answer, and
    a caller reading the verdict off this run is reading the one the pinned
    comment holds.

    A park already standing for this reason is left exactly where it is, and
    that is not only about the notice: an issue waiting on a human is waiting
    for as long as the human takes, and re-writing the same claim once a poll
    would spend a pinned write per tick on a record nothing has changed. What
    a sentence a refused comment stranded gets instead is the redelivery every
    unsuperseded park's notice gets, at the top of the tick.
    """
    if _late_park_state._stands_for(context, _late_park_state.PARK_SINGLE_DECISION):
        return replace(
            finished,
            disposition=_LateDisposition.PARKED,
            generation=context.generation,
        )
    log.info(
        "issue=#%d late generation %d was adjudicated as one unsplittable "
        "change; parking the candidate %s for a human rather than publishing "
        "it past the ceiling",
        context.issue.number,
        context.generation.generation,
        context.generation.candidate_sha,
    )
    _late_parks._park(
        context,
        _unsplit_notice(context),
        reason=_late_park_state.PARK_SINGLE_DECISION,
    )
    return replace(
        finished,
        disposition=_LateDisposition.PARKED,
        generation=context.generation,
    )


def _unsplit_notice(context: _LateContext) -> str:
    """Word this park so its own retry can always be written beside it.

    The explanation this verdict gave is already durable on the record, so the
    sentence NAMES it rather than copying it. A notice repeating that prose
    would put the same agent text in the same comment twice, and an
    explanation an outcome could be recorded with would then be one whose
    obligation could not be recorded at all -- which for a park nothing
    supersedes is a human never told what their candidate is waiting on.

    What the thread is told is the whole of it either way: the marker is
    replaced with the recorded explanation on the way out, on this tick's own
    post and on every redelivery after it. What is bounded is the durable
    half, by this module's wording rather than by anything an agent wrote,
    and the room it needs is reserved where the outcome was accepted.
    """
    generation = context.generation
    return _UNSPLIT_PARK.format(
        candidate=generation.candidate_sha,
        additions=generation.additions,
        threshold=generation.threshold,
        blocker=_late_notice.RECORDED_EXPLANATION,
    )
