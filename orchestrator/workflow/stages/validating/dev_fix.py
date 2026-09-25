# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What one finished dev fix leaves behind, whichever route started it.

The reviewer feedback route, the awaiting-human resume, and the drift resume
all end here, because the questions after a dev run are the same three
regardless of what prompted it: did the run produce something publishable, is
the tree clean enough to push, and does the reviewer owe the branch another
look. Only the disposition order differs, and `_dispose_dev_fix_result` fixes
it -- an interrupted run first, so a shutdown-killed agent parks nothing and
the next tick simply retries it, then the timeout park, then the question.

`stranded.py` beside this owns the proof of where the branch stands against
its remote, which every reading here takes: it is what lets a no-commit run
publish work an earlier tick left, and it is the head the push replaces
whichever run made the commit. The fixing handler's no-feedback bounce and its
ACK fast path ask the same question off no dev run at all. What it refuses is
what the reading here inherits: a dirty tree, a failed fetch, or a remote that
moved prove nothing, because pushing over a head nobody reconciled is worse
than one more park.

`rounds.py` beside this owns the counter every landed fix pays into. It sits there
rather than beside any one caller because all three routes owe it for the
same reason -- the head the reviewer approved or rejected no longer exists,
so the round it spent does not count against the cap.
"""
from __future__ import annotations

from dataclasses import replace as _replace

from github.Issue import Issue

from orchestrator import config
from orchestrator.config import models as _config_models
from orchestrator.git.verification import probes as _verification_probes, status as _worktree_status
from orchestrator.git.worktrees import naming as _naming
from orchestrator.github.client import GitHubClient
from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.engine import guards as _guards
from orchestrator.workflow.stages.implementing import (
    checkout_parks as _checkout_parks,
    late_gate_models as _late_gate_models,
    late_push as _late_push,
    late_records as _late_records,
    parks as _dev_parks,
)
from orchestrator.workflow.stages.validating import (
    models as _models,
    state as _state,
    stranded as _stranded,
)


def _park_dev_fix_timeout(
    gh: GitHubClient, issue: Issue, state: PinnedState, before_sha: str,
) -> None:
    """Park a fix round whose agent the timeout killed, bounded by our ledger.

    Bounded for the reason implementing's counterpart is: the notice lands
    above anything a human wrote during the run, and the transient recovery
    that retries this park fires only on a thread with nothing new on it.
    """
    _guards._park_awaiting_human(
        gh, issue, state,
        f"{config.HITL_MENTIONS} agent timed out after {config.AGENT_TIMEOUT}s, "
        "manual intervention needed.",
        reason=_state._REASON_AGENT_TIMEOUT,
        bounded=True,
    )
    state.set(_state._PARK_REASON, _state._REASON_AGENT_TIMEOUT)
    state.set(_state._PRE_DEV_FIX_SHA, before_sha or "")


def _publishable_dev_fix(
    spec: _config_models.RepoSpec, issue: Issue, state: PinnedState, run: _models._DevFixRun,
) -> _models._DevFixRun | None:
    """The run a fix publishes, carrying the head it was decided on, or None.

    The head is read ONCE and travels on the answer, because the decision and
    the push have to be about the same commit. Between this reading and the
    proof the size gate takes for itself the worktree is writable -- another
    tick, an operator, a stray descendant -- and a commit landing there is a
    different candidate: measured, pushed, and receipted while the route that
    reached this answer goes on as if the head it read had gone out. Handed on
    instead of dropped, the two are one decision and a checkout standing
    anywhere else refuses.

    The remote tip is proved for EVERY candidate rather than only for the one
    a run committed nothing towards, because it is the head the push replaces
    in both shapes and a run that committed is no evidence about where the
    pull request stands. A tick that commits over work an earlier one
    stranded begins at that stranded commit, which the pull request has never
    carried: pinned to it, the gate reads a publication it cannot name and
    parks unmeasured, so the accumulated code and the report describing it
    stay in the checkout however many times the resume is retried.

    What the proof refuses -- a dirty tree, a fetch that failed, a remote that
    moved -- leaves a run that committed pinned to the head it began at, which
    is the ordinary in-sync reading and the one the gate then refuses on if
    the pull request has moved at all.

    None is every no-publish reading: a checkout that could not name its head
    at all, and one whose head is exactly what the run started on with nothing
    of that run's stranded on the branch unpushed.
    """
    if run.agent_result.unfinished_steps:
        return None
    after_sha = run.after_sha
    if after_sha is None:
        after_sha = _verification_probes._head_sha(run.worktree)
    if not after_sha:
        return None
    published = _stranded._stranded_fix_unpushed(
        spec, run.worktree, state, issue,
    )
    if after_sha == run.before_sha and not published:
        return None
    return _replace(run, after_sha=after_sha, published_head=published)


def _publish_dev_fix(
    gh: GitHubClient,
    spec: _config_models.RepoSpec,
    issue: Issue,
    state: PinnedState,
    run: _models._DevFixRun,
) -> bool:
    """Push what a finished dev fix left, once it is small enough to push.

    The one seam every fix route publishes through, which is what makes the
    size gate between the tree read and the push a contract rather than a
    check: a candidate that would take the pull request past `MAX_ADDED_LINES`
    is held here whether the run came from reviewer feedback, a human's reply,
    or an edited issue body. Held means the gate has already done everything
    this tick does with the candidate -- parked it, or handed the issue to the
    adjudication under `workflow:decomposing` -- so the caller reads it as
    every other no-publish exit: nothing is pushed and no label is advanced.

    The push is named and pinned by what the gate handed back rather than by
    the checkout it is run in: the measured commit goes out even if `HEAD`
    moved since, and the head the entry froze is the lease, so a pull request
    somebody pushed to in that same window rejects this push instead of being
    overwritten by work measured against the head it used to be on.

    The state the gate freezes is the run's own where it carries one. A route
    that relabels remotely and then publishes in the same tick names the state
    it moved to, because an issue object that relabel did not go through
    still carries the state the issue has left -- and a settled adjudication
    continues at whatever the record names.

    The approval the gate leaves behind is spent HERE, on the push that pays
    it. It says one commit is still owed a publication, and a record left
    standing past the push that made it would freeze this branch out of the
    pre-tick base refresh with nothing coming back to drop it.
    """
    state.set("silent_park_count", 0)
    dirty = _worktree_status._worktree_dirty_files(run.worktree)
    if dirty:
        _checkout_parks._on_dirty_worktree(
            gh, issue, state,
            _guards._ParkedRun(
                run.agent_result, _guards._ROUTE_DEV_FIX,
            ),
            dirty,
        )
        return False
    branch = _naming._resolve_branch_name(state, spec, issue.number)
    published = _late_push._publishes(
        _late_records._gate(gh, spec, issue, state, run.worktree), branch,
        _late_gate_models._Entered(
            stage=run.stage,
            # The head the pull request is standing on under this candidate.
            # Left for the gate to read afterwards, a pull request somebody
            # pushed to while the agent was out becomes the lease and the
            # force-push overwrites them with work measured against the head
            # it used to be on.
            head=run.entered_head,
            spends=run.spends or _late_gate_models._SPENDS_NOTHING,
            # The head this route read and decided to publish on. The gate
            # proves the checkout again, and a commit landing between the two
            # reads would otherwise be measured, pushed, and receipted here
            # while the route behind this call reports the fix it read as
            # published.
            candidate=run.after_sha or "",
        ),
    )
    if published.held:
        return False
    if published.landed:
        return True
    _guards._park_awaiting_human(
        gh, issue, state,
        f"{config.HITL_MENTIONS} git push failed; see orchestrator logs.",
        reason=_state._REASON_PUSH_FAILED,
        bounded=True,
    )
    state.set(_state._PARK_REASON, _state._REASON_PUSH_FAILED)
    return False


def _dispose_dev_fix_result(
    gh: GitHubClient,
    spec: _config_models.RepoSpec,
    issue: Issue,
    state: PinnedState,
    run: _models._DevFixRun,
) -> bool:
    if _guards._ignore_if_interrupted(issue, run.agent_result):
        return False
    if run.agent_result.timed_out:
        _park_dev_fix_timeout(gh, issue, state, run.before_sha)
        return False
    publishable = _publishable_dev_fix(spec, issue, state, run)
    if publishable is None:
        _dev_parks._on_question(
            gh, issue, state,
            _guards._ParkedRun(
                run.agent_result,
                _guards._ROUTE_DEV_FIX,
                before_sha=run.before_sha,
            ),
        )
        return False
    return _publish_dev_fix(gh, spec, issue, state, publishable)


def _handle_dev_fix_result(
    gh: GitHubClient,
    spec: _config_models.RepoSpec,
    issue: Issue,
    *context_args,
    **fields,
) -> bool:
    """Post-agent handling for a dev fix during validating.

    Returns True if a fix was committed, pushed, and the caller should
    advance the label (validating routes the issue back to `validating`
    on True so the reviewer re-runs against the new head; any stale
    approval state must be reset by the caller before relabeling). A
    no-new-commit run also returns True when it published a stranded fix
    a prior parked run had committed (see `stranded._stranded_fix_unpushed`).
    Returns False if the run produced no fix (timeout, no-new-commit, dirty
    tree, or push failure); caller should write state and return.
    A shutdown-killed (interrupted) run also returns False WITHOUT parking,
    posting, or publishing, so the next tick re-runs the dev cleanly.

    `after_sha`, when provided, is the post-agent HEAD the caller already
    read (e.g. the fixing handler's ACK fast path); passing it avoids a
    redundant `_head_sha` call. When None it is read here.
    """
    state, run = _models._dev_fix_run(context_args, fields)
    return _dispose_dev_fix_result(gh, spec, issue, state, run)
