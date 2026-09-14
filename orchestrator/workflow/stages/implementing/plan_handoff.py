# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Keeping an accepted plan handoff in step with its PR until a dev pushes.

The handoff is written before the developer runs, and everything the tick
stages after it is dropped by an interruption on purpose -- so the window
between that write and the first dev commit is one a crash, a restart or a live
pause can leave an issue sitting in for polls at a time. The humans still have
the design on an open pull request through all of it, and what they do to it
there is exactly what the handoff existed to take account of.

Nothing was left watching. `discussion_plan_path` is retired by that write, so
plan identity falls to the recorded commit against the PR's live head -- and an
amendment made in this window moves that head, which reads as this stage having
pushed: merged, the issue is closed `done` with no developer having run, and
unmerged the developer is spawned on the checkout the handoff left, whose push
takes the amendment back out. A merge alone is enough to matter even with
nothing amended, since the baseline freezes base sync and the developer would
start behind a base the plan has just landed in.

So the handoff's own record is read as the state it is: `read_only_baseline_sha`
beside `discussion_plan_sha` says a relabel was accepted and this stage has
published nothing since. While it stands, the reading the guard took once is
taken again -- the same PR read, the same re-anchor onto what it carries, the
same two records written -- and the tick then continues to a developer starting
where its reviewers left off.

What ends it is the branch, because the branch is the only durable record of a
developer having committed: pinned state written after a push is lost by the
same crash this exists for. A tip nothing could read is not that answer -- it is
no answer -- and the tick holds rather than deciding the plan question on a
reading nobody took.

A tip past the baseline is not that answer on its own, though, because the
re-anchor here moves the branch BEFORE it records where it put it. A tick that
dies in between leaves the branch on the plan PR's live head with the older
commit still recorded -- indistinguishable, by the branch alone, from a
developer having committed. Read that way, the next tick hands the reviewers'
own amendment to the recovered-work shortcut, which skips the agent and
publishes their edit as the implementation. So the move writes a marker of its
own before it makes it, and a marker still standing says the branch is where
this stage put it and nothing has been published from here.
"""
from __future__ import annotations

import logging

from github.Issue import Issue

from orchestrator import config
from orchestrator.git.worktrees import (
    naming as _naming,
    recovery as _worktree_recovery,
)
from orchestrator.github.client import GitHubClient
from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.stages.discussion.state import _PLAN_SHA, _PR_NUMBER
from orchestrator.workflow.stages.implementing import (
    plan_reading as _plan_reading,
    state as _state,
)

log = logging.getLogger("orchestrator.workflow")


def _reconcile_open_plan_handoff(
    gh: GitHubClient, spec: config.RepoSpec, issue: Issue, state: PinnedState,
) -> bool:
    """Catch an unspent handoff up to its plan PR, or hold the tick on it."""
    baseline = _accepted_handoff_baseline(state)
    if baseline is None:
        return False
    unspent = _handoff_unspent(spec, issue, state, baseline)
    if unspent is None:
        log.warning(
            "issue=#%s holding the accepted plan handoff: the branch tip "
            "could not be read, so nothing here can say whether a developer "
            "has committed on it", issue.number,
        )
        return True
    if unspent:
        return _readvance_plan_handoff(gh, spec, issue, state)
    return False


def _accepted_handoff_baseline(state: PinnedState) -> str | None:
    """The tip an accepted plan handoff recorded, while its records stand.

    All three are the one state: the baseline says a relabel was accepted and
    nothing here has published since, the plan commit says the pull request
    that relabel handed over is a design rather than a build, and the number
    says which one. An issue missing any of them is not in it.
    """
    baseline = str(state.get(_state._READ_ONLY_BASELINE_SHA) or "")
    if not baseline or not state.get(_PLAN_SHA):
        return None
    if state.get(_PR_NUMBER) is None:
        return None
    return baseline


def _handoff_unspent(
    spec: config.RepoSpec,
    issue: Issue,
    state: PinnedState,
    baseline: str,
) -> bool | None:
    """Whether no developer has committed on this branch yet, or None unread.

    A move still marked in flight answers before the branch is asked at all,
    and answers yes whatever the tip is: the marker is written before the ref
    is touched and retired by the write that records where it landed, so a tick
    finding one knows the branch is where this stage was putting it. Nothing is
    spawned between the two, so no developer can have committed under it.

    Otherwise the baseline answers. It names the tip the last completed write
    vouched for, and a branch that has moved off it since has moved for one
    reason -- the developer this handoff was accepted for committed on it.

    A tip nothing could read is neither, and the caller holds on it: proving no
    developer has published cannot rest on a probe that did not run.
    """
    if state.get(_state._HANDOFF_ANCHOR_SHA):
        return True
    tip = _worktree_recovery._branch_tip_sha(
        spec, _naming._resolve_branch_name(state, spec, issue.number),
    )
    if not tip:
        return None
    return tip == baseline


def _readvance_plan_handoff(
    gh: GitHubClient, spec: config.RepoSpec, issue: Issue, state: PinnedState,
) -> bool:
    """Move an unspent handoff onto whatever the plan PR carries now.

    The same three answers the relabel guard has. A PR that could not be read
    decides nothing and ends the tick; a head that could not be put on the
    branch holds the handoff where it is rather than spawning a developer
    behind the reviewers; and anything else records what the branch really
    ended up on.

    A MERGED plan is re-anchored even when its head has not moved, because what
    the developer starts from is the base by then and the base moves on its own
    -- the design landed in it, and so has everything else that landed since.
    Only a reading that changes neither record writes nothing, which is the
    ordinary poll of a handoff nobody has touched.

    The marker is what makes the move itself recoverable, and it is durable
    before the ref is touched for the same reason the publication's is:
    everything after that point can leave the world changed, and the branch it
    leaves behind is one the next tick has to be able to recognize as this
    stage's rather than as a developer's work to publish. It is retired by the
    write that says where the branch ended up, so the two are never both true
    and never both false.
    """
    reviewed = _plan_reading._read_plan_pr(gh, issue, state.get(_PR_NUMBER))
    if reviewed is None:
        return True
    recorded = str(state.get(_PLAN_SHA) or "")
    if reviewed.head == recorded and not reviewed.merged:
        return _spend_handoff_anchor(gh, issue, state)
    state.set(_state._HANDOFF_ANCHOR_SHA, reviewed.head)
    gh.write_pinned_state(issue, state)
    inherited = _plan_reading._inherited_tip(spec, issue, state, reviewed)
    if inherited.pending:
        return True
    state.set(_PLAN_SHA, reviewed.head)
    state.set(_state._READ_ONLY_BASELINE_SHA, inherited.sha)
    state.set(_state._HANDOFF_ANCHOR_SHA, None)
    gh.write_pinned_state(issue, state)
    return False


def _spend_handoff_anchor(
    gh: GitHubClient, issue: Issue, state: PinnedState,
) -> bool:
    """Retire a marker whose move has nothing left to make, and continue.

    The ordinary poll leaves it alone, since there is none. One IS standing
    when the move that wrote it landed and the tick died before recording it,
    and the humans then put the PR back where the records already say it is --
    at which point the branch is where it belongs and only the marker is left
    to spend.
    """
    if state.get(_state._HANDOFF_ANCHOR_SHA):
        state.set(_state._HANDOFF_ANCHOR_SHA, None)
        gh.write_pinned_state(issue, state)
    return False
