# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Retry measurement or publication of committed work without another developer run.

A trusted bare continue retries a failed measurement; restoring an approved
candidate to its checkout retries the held publication. Both routes carry
the proved commit into the ordinary publication seam and persist its answer.
"""
from __future__ import annotations

from pathlib import Path

from github.Issue import Issue

from orchestrator.agents.models import AgentResult
from orchestrator.config import models as _config_models
from orchestrator.git.worktrees import creation as _worktree_creation, naming as _naming, paths as _worktree_paths
from orchestrator.github.client import GitHubClient
from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.stages.implementing import (
    candidate_recovery as _candidate_recovery,
    checkout_recovery as _checkout_recovery,
    late_evidence as _late_evidence,
    late_measurement_reply as _late_measurement_reply,
    late_park_state as _late_park_state,
    models as _models,
    session_read as _session_read,
    state as _state,
)


def _try_recover_late_measurement_park(
    gh: GitHubClient, spec: _config_models.RepoSpec, issue: Issue, state: PinnedState
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
    continue retries it once the worktree is back. The branch and a checkout
    standing there are admitted before any of it (`_admitted_checkout`): a
    refusal consumes no reply and measures nothing.

    The park flags are cleared ahead of the publish, because clearing them is
    what the answer means -- and the retry re-takes the park itself if the
    reading is still not there. The comments are consumed in the same breath,
    which is safe only because every one of them is a bare continue: nothing
    with words in it is dropped here.
    """
    replies = _late_measurement_reply._answers_the_measurement_park(gh, issue, state)
    if not replies:
        return False
    wt = _admitted_checkout(spec, issue, state)
    state.set(
        _state._LAST_ACTION_COMMENT_ID,
        max(reply.id for reply in replies),
    )
    if wt is None:
        wt = _worktree_paths._worktree_path(spec, issue.number)
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
        invoked=False,
    )
    _candidate_recovery._publish_committed_work(
        gh, spec, issue, state, _models._RecoveredWork(
            agent_result, wt, _late_park_state._recorded_candidate(state),
        ),
    )
    gh.write_pinned_state(issue, state)
    return True


def _try_recover_moved_candidate_park(
    gh: GitHubClient, spec: _config_models.RepoSpec, issue: Issue, state: PinnedState
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

    The checkout put back has to be the issue's own, admitted with the branch
    before it is read (`_admitted_checkout`): a tree on the flat branch at the
    approved commit is no restoration.
    """
    if state.get(_state._PARK_REASON) != _state._CANDIDATE_MOVED:
        return False
    wt = _admitted_checkout(spec, issue, state)
    if wt is None:
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
        invoked=False,
    )
    _candidate_recovery._publish_committed_work(
        gh, spec, issue, state, _models._RecoveredWork(agent_result, wt, restored),
    )
    gh.write_pinned_state(issue, state)
    return True


def _admitted_checkout(spec: _config_models.RepoSpec, issue: Issue, state: PinnedState) -> Path | None:
    """The checkout standing at the issue's path once its branch and it are the issue's own; None where none stands.

    Both recoveries carry the commit in that checkout into the publication
    seam, whose size gate records what it measures as this issue's candidate
    and can hand it to an adjudication, so the record's branch and the tree
    are admitted before it is read, as the seam would prove them
    (`creation._retained_checkout`, detached in the middle of rebasing
    exactly that branch included). A refusal raises `naming.BranchRefused`.
    """
    _naming._resolve_branch_name(state, spec, issue.number)
    return _worktree_creation._retained_checkout(spec, issue.number, rebasing=True)
