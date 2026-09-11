# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Retry measurement or publication of committed work without another developer run.

A trusted bare continue retries a failed measurement; restoring an approved
candidate to its checkout retries the held publication. Both routes carry
the proved commit into the ordinary publication seam and persist its answer.
"""
from __future__ import annotations

from github.Issue import Issue

from orchestrator import config
from orchestrator.agents import AgentResult
from orchestrator.git.worktrees import paths as _worktree_paths
from orchestrator.github.client import GitHubClient
from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.stages.implementing import (
    checkout_recovery as _checkout_recovery,
    disposition as _disposition,
    late_evidence as _late_evidence,
    late_parks as _late_parks,
    models as _models,
    session_read as _session_read,
    state as _state,
)


def _try_recover_late_measurement_park(
    gh: GitHubClient, spec: config.RepoSpec, issue: Issue, state: PinnedState
) -> bool:
    """Re-measure a candidate a human has told the orchestrator to retry.

    The recovery a measurement park earns, and it is deliberately not a
    session retry. What failed was a READING -- a base the remote would not
    name, an object this host does not hold, a diff nothing could pin -- and
    the developer that produced the commit finished long ago, so paying for
    another run would buy a second answer to a question nobody asked. The bare
    `/orchestrator continue` is the operator saying the reading should be
    taken again; everything else on the thread is guidance, which the ordinary
    resume feeds to the developer.

    Returns True when the command was answered and the caller must return, and
    it answers every one of them: a command this reconciliation recognized is
    never handed back to the generic parked-continue classifier, which would
    refuse it as carrying no guidance -- the wrong thing to tell an operator
    whose command is exactly the right one, and a refusal that consumes their
    reply against a question nobody asked.

    The committed work goes back through the same publication seam it came out
    of, so the retry reaches the same three outcomes a fresh disposition does:
    the branch is published, the candidate is routed to adjudication, or the
    park is taken again with the reason it fails for now. A checkout that is
    gone is the fourth, and it is the one outcome the seam cannot reach on its
    own: there is no commit to read there, the recorded SHA is evidence no
    fresh checkout may stand in for, and re-running the developer would answer
    with different work -- so it parks saying exactly that, and the next
    continue retries it once the worktree is back.

    The park flags are cleared ahead of the publish, because clearing them is
    what the answer means -- and the retry re-takes the park itself if the
    reading is still not there. The comments are consumed in the same breath,
    which is safe only because every one of them is a bare continue: nothing
    with words in it is dropped here.
    """
    replies = _late_parks._answers_the_measurement_park(gh, issue, state)
    if not replies:
        return False
    state.set(
        _state._LAST_ACTION_COMMENT_ID,
        max(reply.id for reply in replies),
    )
    wt = _worktree_paths._worktree_path(spec, issue.number)
    if not wt.exists():
        _late_evidence._holds_missing_candidate(gh, spec, issue, state, wt)
        gh.write_pinned_state(issue, state)
        return True
    if _late_evidence._holds_moved_candidate(gh, spec, issue, state, wt):
        gh.write_pinned_state(issue, state)
        return True
    state.set(_state._AWAITING_HUMAN, False)
    state.set(_state._PARK_REASON, None)
    _, _, _, dev_sid = _session_read._read_dev_session(state)
    agent_result = AgentResult(
        session_id=dev_sid,
        last_message=(
            "(orchestrator recovery: re-measuring the committed candidate)"
        ),
        exit_code=0,
        timed_out=False,
        stdout="",
        stderr="",
    )
    _disposition._publish_committed_work(
        gh, spec, issue, state, _models._RecoveredWork(
            agent_result, wt, _late_parks._recorded_candidate(state),
        ),
    )
    gh.write_pinned_state(issue, state)
    return True


def _try_recover_moved_candidate_park(
    gh: GitHubClient, spec: config.RepoSpec, issue: Issue, state: PinnedState
) -> bool:
    """Republish an approved commit whose checkout has been put back.

    The way out of the one park a human cannot answer with words. What that
    park refused was the HANDOFF -- the commit was measured and approved, and
    the checkout it would have handed to review was somewhere else -- so what
    settles it is the checkout coming back, not guidance and not another
    developer run over work that is already committed.

    Which makes it quiet: the approved commit is recorded beside the park, so
    every tick asks one local question of the checkout and says nothing until
    the answer changes. An operator who restores the worktree sees the branch
    publish on the next poll without having to ask for it, and one who leaves
    it where it is is not told the same thing once a tick.

    What it hands on is the ordinary reconciliation, and the approval travels
    with it rather than being spent on the way. The record is the gate's own
    verdict about that exact commit, so the reconciliation republishes it
    under it -- named against it and not measured again -- and the publication
    that lands is what drops it. Spending it here instead would leave the
    reconciliation asking the size question about a settled commit, against a
    base that has moved since, and a park in the window between the two with
    nothing on the issue naming what it is waiting for.
    """
    if state.get(_state._PARK_REASON) != _state._CANDIDATE_MOVED:
        return False
    wt = _worktree_paths._worktree_path(spec, issue.number)
    if not wt.exists():
        return False
    restored = _checkout_recovery._restored_checkout(issue, state, wt)
    if not restored:
        return False
    state.set(_state._AWAITING_HUMAN, False)
    state.set(_state._PARK_REASON, None)
    _, _, _, dev_sid = _session_read._read_dev_session(state)
    agent_result = AgentResult(
        session_id=dev_sid,
        last_message=(
            "(orchestrator recovery: the approved commit is back in the "
            "checkout)"
        ),
        exit_code=0,
        timed_out=False,
        stdout="",
        stderr="",
    )
    _disposition._publish_committed_work(
        gh, spec, issue, state, _models._RecoveredWork(agent_result, wt, restored),
    )
    gh.write_pinned_state(issue, state)
    return True
