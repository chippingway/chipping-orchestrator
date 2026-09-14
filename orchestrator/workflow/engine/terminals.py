# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""How an issue stops being worked.

Three conditions end one: the linked PR merged (`done`), the linked PR closed
without merging (`rejected`), and a human closed the issue while its PR is
still open (`rejected` too -- a human stop signal outranks whatever the stage
was about to do). What the three share is the tail, not the condition that
reaches them: each stamps its terminal timestamp, flips to a terminal label,
posts the cumulative usage receipt, and writes pinned state once. That shared
tail is why they sit together -- an arc added beside them inherits the order
rather than reinventing it.

Three entry points reach the arcs, and they differ only in who fetched the PR.
`_drain_review_pr_terminals` serves the stages already holding one --
`in_review`, `fixing`, `resolving_conflict` -- and tries all three arcs against
the PR the caller passes; `pr=None` is a deliberate no-op so `fixing` can hand
over its own fetch failure unchanged.

`_pr_terminal_stops_the_tick` serves the stages that hold no PR at handler
entry -- `implementing`, `documenting`, `validating` -- and decides BOTH
pull-request endings off one fetch of its own. One rather than a helper each,
because two fetches are two moments: a merge landing between them answers open
to the first and merged to the second, which a closed-without-merge arc is
right to ignore, and the stage behind it runs anyway over work that has landed.
`_finalize_if_pr_merged` keeps the single-ending form for the umbrella /
blocked child aggregation, which may not be held on a child whose remote
blinked.

A fetch that FAILS leaves both of those falling through: nothing about a failed
read says which ending, if any, it was hiding, and answered as one every issue
whose remote blinked would stop advancing. `_finalize_if_issue_closed` behind
them is the one that defers the whole tick on its own failed read, so a
transient failure cannot label a merged-PR issue `rejected`. Every entry point
returns True to mean "this tick is over".

The `discussion` stage composes the arcs itself rather than taking an entry
point here, because its third one differs: a closed issue whose plan PR is
still open KEEPS its label -- that label is what the closed-issue sweep finds
it by, and the plan the humans are reading is what decides.
`workflow/stages/discussion/plan_terminal.py` reaches `_finalize_merged_pr` and
`_finalize_rejected_pr` directly for that reason, and
`workflow/stages/discussion/terminal.py` reaches
`_finalize_closed_issue_with_open_pr` for a close with no pull request to poll
at all -- which is the same shape that arc already serves here, a close whose
linked PR is not the thing being decided. It records as fully as
the other two -- the stamp, the `rejected` label, the receipt, one write -- and
differs only in what it has nothing to say about: no event, since there is no
pull request for the payload to name, and no branch cleanup.

Branch cleanup is deliberately outside the shared tail. It runs on the two arcs
where the PR itself is gone and the branch is dead weight, and is withheld on
the open-PR arc so an operator can still reopen or salvage what the closed
issue left behind. That arc emits no `pr_closed_without_merge` for the same
reason -- the PR has not closed yet -- while the closed-issue entry point does
emit one once it confirms the linked PR is closed as well.

The receipt's position in the tail is a contract, not a preference: it is
posted BEFORE the write so its comment id rides the same persisted state and a
later drift or watermark tick reads it as orchestrator-authored.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from github.Issue import Issue

from orchestrator import config
from orchestrator.git.worktrees import naming as _naming, terminal as _worktree_terminal
from orchestrator.github.client import GitHubClient
from orchestrator.github.issues import (
    _ISSUE_STATE_CLOSED,
    _ISSUE_STATE_OPEN,
    _STATE_ATTR,
)
from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.engine import usage as _usage
from orchestrator.workflow.state import WorkflowLabel, stage_name

log = logging.getLogger("orchestrator.workflow")

# The pinned field every terminal here reads the linked pull request by.
_PR_NUMBER = "pr_number"

# What a pull request a human already landed reads as.
_MERGED = "merged"

# The two attributes a pull request's tip is reached through. Named because
# every arc here reads one of them off a lazily fetched object, and a literal
# repeated at each site is one a rename would leave behind at some of them.
_HEAD_ATTR = "head"
_HEAD_SHA_ATTR = "sha"


@dataclass(frozen=True)
class _LinkedPullRequest:
    """The pull request an issue records, fetched once and read once.

    One object rather than a fetch per question, because the two terminal
    states a pull request can be in are two readings of ONE fact. Asked with a
    fetch each, a merge landing between them answers `open` to the first and
    `merged` to the second -- which a closed-without-merge arc is right to
    ignore -- and the stage behind both carries on over a pull request that is
    finished, spawning a reviewer or measuring a candidate onto work that has
    landed.

    Three shapes, and each is a different answer for a caller. `pr` set is a
    reading any terminal may act on. `unreadable` is a request that did not
    come back, which says nothing about either state. Neither set is an issue
    that records no pull request at all.

    The HEAD travels with the state for the same reason the two states do. A
    caller that has to tell what a pull request IS before deciding what to do
    about it -- the `implementing` stage, whose recorded number can still be
    the `discussion` plan -- classifies on the head and finalizes on the
    state, and taking those from two fetches is two moments: a head that moved
    between them classifies one snapshot and ends another.
    """

    pr: Any = None
    state: str = ""
    head: str | None = None
    unreadable: bool = False

    @property
    def was_read(self) -> bool:
        """Whether there is a state here a terminal may decide on."""
        return self.pr is not None


def _linked_pull_request(
    gh: GitHubClient, issue: Issue, state: PinnedState, checking: str,
) -> _LinkedPullRequest:
    """Read the pull request this issue records, once, guarded.

    The state is read INSIDE the guard with the lookup, because a fetched pull
    request is lazy: `get_pr` asks GitHub nothing and the request that can fail
    is the attribute access behind it.

    `checking` is what the log says the reading was for, since what a failure
    costs differs by the caller that took it.
    """
    pr_number = state.get(_PR_NUMBER)
    if pr_number is None:
        return _LinkedPullRequest()
    try:
        return _pull_request_facts(gh, int(pr_number))
    except Exception:
        log.exception(
            "issue=#%s could not fetch PR #%s while %s; leaving alone",
            issue.number, pr_number, checking,
        )
    return _LinkedPullRequest(unreadable=True)


def _pull_request_facts(gh: GitHubClient, number: int) -> _LinkedPullRequest:
    """The lookup and the lazy reads behind it, as one reading."""
    pull_request = gh.get_pr(number)
    return _LinkedPullRequest(
        pr=pull_request,
        state=gh.pr_state(pull_request),
        head=getattr(
            getattr(pull_request, _HEAD_ATTR, None), _HEAD_SHA_ATTR, None,
        ),
    )


def _terminal_context(
    gh: GitHubClient,
    spec: config.RepoSpec,
    issue: Issue,
    state: PinnedState,
    pull_request: Any,
) -> _ReviewTerminalContext:
    """The subject a terminal finalizes, built from one proved reading."""
    return _ReviewTerminalContext(
        gh=gh,
        spec=spec,
        issue=issue,
        state=state,
        pr=pull_request,
        stage=stage_name(gh.workflow_label(issue)),
    )


def _finalize_if_pr_merged(
    gh: GitHubClient, spec: config.RepoSpec, issue: Issue, state: PinnedState,
) -> bool:
    """Flip the issue to `done` when its linked PR has already merged.

    Mirrors the terminal-merge arc in `_handle_in_review` / `_handle_fixing`
    / `_handle_resolving_conflict` so the same finalize path can fire from
    any stage. Used by the umbrella / blocked aggregation when a child PR was
    merged externally but the child's workflow label was never advanced past
    the in-flight stage -- the umbrella's all-`done` aggregation would
    otherwise wait forever for that stale child. The stages that carry no
    PR-state arc of their own ask `_pr_terminal_stops_the_tick` instead, which
    answers both endings off one reading.

    Returns True when the helper finalized the issue (caller must return
    immediately); False when there is nothing to do (no `pr_number`, PR
    fetch failed, or PR is not merged). The fetch failure stays fail-OPEN
    here: an aggregation held on a child whose remote blinked is one that
    never completes, and the reading costs nothing to take again.
    """
    linked = _linked_pull_request(
        gh, issue, state, "checking for external merge",
    )
    if not linked.was_read or linked.state != _MERGED:
        return False
    _finalize_merged_pr(
        _terminal_context(gh, spec, issue, state, linked.pr),
        close_error="could not close after detecting external merge",
        close_if_open_only=True,
    )
    return True


def _pr_terminal_stops_the_tick(
    gh: GitHubClient,
    spec: config.RepoSpec,
    issue: Issue,
    state: PinnedState,
    linked: _LinkedPullRequest | None = None,
) -> bool:
    """Both PR terminals off ONE reading, for a stage that carries neither.

    `implementing`, `validating` and `documenting` have no PR-state arc of
    their own -- `_handle_in_review` and `_handle_fixing` have always drained
    both endings inline -- so a pull request a human settled reaches them as an
    ordinary tick. What they do with one is the point: implementing measures
    the committed candidate again and pushes it, opening a second pull request
    since the first is gone, while validating and documenting spawn a reviewer
    or a docs agent against work that has already landed or been turned down.

    Both endings are decided off ONE fetch rather than a helper each, because
    two fetches are two moments: a merge landing between them reads `open` to
    the first and `merged` to the second, which the closed arc is right to
    ignore -- and the stage runs anyway, over a pull request nothing can add
    to. `_finalize_if_issue_closed` behind this drains the third ending, a
    human closing the ISSUE.

    A reading that did not come back falls through, which is the contract the
    merged terminal has always had and the one a request that can fail on any
    poll needs: answered as an ending, every issue whose remote blinked would
    stop advancing, and nothing about a failed read says which ending -- if
    any -- it was hiding. Nothing is written either way, so the next poll asks
    the same question of the same durable state.

    `linked` is for the caller that already took this reading and has already
    ACTED on it -- `implementing`, which has to tell the `discussion` plan
    from a delivery before either terminal may fire. Handed in, the
    classification and the finalize are about one snapshot; taken again here
    they would be two, and a head that moved in between would have one
    pull request classified and another ended.

    Returns True when the issue was finalized and the caller must return.
    False for an issue that records no pull request, one whose pull request is
    open, and one this host could not read.
    """
    if linked is None:
        linked = _linked_pull_request(
            gh, issue, state, "checking whether it has been merged or closed",
        )
    if not linked.was_read:
        return False
    return _finalized_pr_terminal(
        _terminal_context(gh, spec, issue, state, linked.pr), linked.state,
    )


def _finalized_pr_terminal(
    context: _ReviewTerminalContext, pr_state: str,
) -> bool:
    """Route one proved pull-request state to the terminal it earns.

    Spelled apart from the reading above so the reading stays about the
    request and this stays about the two endings: `done` for a merge, and
    `rejected` for a close nobody merged.
    """
    if pr_state == _MERGED:
        _finalize_merged_pr(
            context,
            close_error="could not close after detecting external merge",
            close_if_open_only=True,
        )
        return True
    if pr_state == _ISSUE_STATE_CLOSED:
        _finalize_rejected_pr(context)
        return True
    return False


@dataclass(frozen=True)
class _ReviewTerminalContext:
    gh: GitHubClient
    spec: config.RepoSpec
    issue: Issue
    state: PinnedState
    pr: Any
    stage: str | None

    @property
    def pr_number(self) -> int:
        return int(self.state.get(_PR_NUMBER))

    @property
    def conflict_round(self):
        conflict_round = self.state.get("conflict_round")
        if self.stage == "resolving_conflict":
            return int(conflict_round or 0)
        return conflict_round


def _close_terminal_issue(
    context: _ReviewTerminalContext, error_message: str,
) -> None:
    try:
        context.issue.edit(state=_ISSUE_STATE_CLOSED)
    except Exception:
        log.exception(
            "issue=#%s %s", context.issue.number, error_message,
        )


def _cleanup_review_terminal(context: _ReviewTerminalContext) -> None:
    _worktree_terminal._cleanup_terminal_branch(
        context.gh,
        context.spec,
        context.issue.number,
        branch=_naming._resolve_branch_name(
            context.state, context.spec, context.issue.number,
        ),
    )


def _finalize_merged_pr(
    context: _ReviewTerminalContext,
    *,
    close_error: str,
    close_if_open_only: bool = False,
) -> None:
    context.state.set("merged_at", _usage._now_iso())
    context.gh.set_workflow_label(context.issue, WorkflowLabel.DONE)
    _usage._post_issue_usage_verdict(context.gh, context.issue, context.state)
    context.gh.write_pinned_state(context.issue, context.state)
    context.gh.emit_event(
        "pr_merged",
        issue_number=context.issue.number,
        stage=context.stage,
        pr_number=context.pr_number,
        sha=getattr(context.pr.head, _HEAD_SHA_ATTR, None) or None,
        merge_method="external",
        review_round=int(context.state.get("review_round") or 0),
        conflict_round=context.conflict_round,
        retry_count=context.state.get("retry_count"),
    )
    if (
        not close_if_open_only
        or getattr(context.issue, _STATE_ATTR, _ISSUE_STATE_OPEN) != _ISSUE_STATE_CLOSED
    ):
        _close_terminal_issue(context, close_error)
    _cleanup_review_terminal(context)


def _finalize_rejected_pr(context: _ReviewTerminalContext) -> None:
    context.state.set("closed_without_merge_at", _usage._now_iso())
    context.gh.set_workflow_label(context.issue, WorkflowLabel.REJECTED)
    _usage._post_issue_usage_verdict(context.gh, context.issue, context.state)
    context.gh.write_pinned_state(context.issue, context.state)
    context.gh.emit_event(
        "pr_closed_without_merge",
        issue_number=context.issue.number,
        stage=context.stage,
        pr_number=context.pr_number,
        sha=getattr(context.pr.head, _HEAD_SHA_ATTR, None) or None,
        review_round=int(context.state.get("review_round") or 0),
        conflict_round=context.conflict_round,
        retry_count=context.state.get("retry_count"),
    )
    _close_terminal_issue(context, "could not close after reject")
    _cleanup_review_terminal(context)


def _finalize_closed_issue_with_open_pr(context: _ReviewTerminalContext) -> None:
    context.state.set("closed_without_merge_at", _usage._now_iso())
    context.gh.set_workflow_label(context.issue, WorkflowLabel.REJECTED)
    _usage._post_issue_usage_verdict(context.gh, context.issue, context.state)
    context.gh.write_pinned_state(context.issue, context.state)


def _drain_review_terminal(context: _ReviewTerminalContext) -> bool:
    if context.pr is None:
        return False
    pr_status = context.gh.pr_state(context.pr)
    if pr_status == "merged":
        _finalize_merged_pr(context, close_error="could not close after merge")
        return True
    if pr_status == _ISSUE_STATE_CLOSED:
        _finalize_rejected_pr(context)
        return True
    if getattr(context.issue, _STATE_ATTR, _ISSUE_STATE_OPEN) == _ISSUE_STATE_CLOSED:
        _finalize_closed_issue_with_open_pr(context)
        return True
    return False


def _drain_review_pr_terminals(
    gh: GitHubClient,
    *context_args,
    stage: str,
) -> bool:
    """Drain the three PR/issue terminal arcs shared by `_handle_in_review`,
    `_handle_fixing`, and `_handle_resolving_conflict`.

    Caller passes the already-fetched PR and its own `stage` label. Each
    stage owns its fetch-failure semantics: `in_review` and
    `resolving_conflict` let `gh.get_pr` exceptions propagate to
    `_process_issue`'s catch; `fixing` catches and bails with `pr=None`
    so the rest of its handler can short-circuit. Passing `pr=None` here
    is a no-op (returns False) so fixing's deferral arrives unchanged.

    Three arcs:

      1. `pr_state == "merged"`: stamp `merged_at`, flip to `done`,
         write state, emit `pr_merged` (`merge_method="external"`),
         close the issue if still open, and clean up the branch.
      2. `pr_state == "closed"` (unmerged): stamp
         `closed_without_merge_at`, flip to `rejected`, write state,
         emit `pr_closed_without_merge`, close the issue if still open,
         and clean up the branch.
      3. Issue is closed but PR is still open (the closed-issue sweep
         surfaced a human stop signal): stamp
         `closed_without_merge_at`, flip to `rejected`, write state.
         Deliberately no event emit (the PR is still open and may be
         reopened/salvaged) and no branch cleanup (the operator may
         want the open PR's history).

    Returns True when an arc fired (caller must return immediately).
    Returns False when none fired (caller continues with the same `pr`).
    """
    spec, issue, state, pr = context_args
    return _drain_review_terminal(
        _ReviewTerminalContext(gh, spec, issue, state, pr, stage),
    )


@dataclass(frozen=True)
class _ClosedIssuePR:
    number: int | None
    pr: Any = None
    defer: bool = False


def _closed_issue_pr(
    gh: GitHubClient, issue: Issue, state: PinnedState,
) -> _ClosedIssuePR:
    raw_number = state.get(_PR_NUMBER)
    if raw_number is None:
        return _ClosedIssuePR(number=None)
    number = int(raw_number)
    try:
        pr = gh.get_pr(number)
    except Exception:
        log.exception(
            "issue=#%s could not fetch PR #%s while finalizing a "
            "closed issue; deferring (next tick retries the "
            "merged-PR path)", issue.number, raw_number,
        )
        return _ClosedIssuePR(number=number, defer=True)
    return _ClosedIssuePR(
        number=number,
        pr=pr,
        defer=gh.pr_state(pr) == "merged",
    )


def _emit_closed_pr_rejection(context: _ReviewTerminalContext) -> None:
    context.gh.emit_event(
        "pr_closed_without_merge",
        issue_number=context.issue.number,
        stage=context.stage,
        pr_number=context.pr_number,
        sha=getattr(context.pr.head, _HEAD_SHA_ATTR, None) or None,
        review_round=int(context.state.get("review_round") or 0),
        conflict_round=context.state.get("conflict_round"),
        retry_count=context.state.get("retry_count"),
    )
    _cleanup_review_terminal(context)


def _finalize_if_issue_closed(
    gh: GitHubClient, spec: config.RepoSpec, issue: Issue, state: PinnedState,
) -> bool:
    """Flip a closed-but-not-merged issue to `rejected`.

    Pairs with `_pr_terminal_stops_the_tick`: that helper drains both
    pull-request endings off one reading, this one drains the closed-issue
    counterpart so closed issues yielded by the `implementing` /
    `documenting` / `validating` sweep entries do NOT spawn the dev / docs /
    reviewer agent, push to the per-issue branch, or post on the now-closed
    issue thread. `_handle_in_review` / `_handle_fixing` carry equivalent
    guards inline via their PR-state arcs; callers in the sweep stages
    invoke this helper right after that one, so a merged or closed PULL
    REQUEST is drained first and only a closed ISSUE lands here.

    Branch cleanup follows the in_review / fixing convention: only when
    the linked PR itself is also closed (a closed PR without merge is
    `pr_closed_without_merge`-emit territory and the branch is dead
    weight). An open PR with a manually-closed issue is left alone so
    the operator can salvage / reopen it; the orchestrator-owned branch
    and worktree stay until the PR closes.

    Returns True when the caller must NOT continue the handler this
    tick: the issue was finalized to `rejected`, OR the issue is closed
    but the linked PR state could not be confirmed yet (deferred to a
    later tick so a transient fetch failure cannot permanently mis-
    label a merged-PR issue, AND so the closed issue is not driven
    through normal dev / docs / reviewer work). Returns False only
    when the issue is still open and the handler should proceed.
    """
    if getattr(issue, _STATE_ATTR, _ISSUE_STATE_OPEN) != _ISSUE_STATE_CLOSED:
        return False
    linked_pr = _closed_issue_pr(gh, issue, state)
    if linked_pr.defer:
        return True
    context = _ReviewTerminalContext(
        gh, spec, issue, state, linked_pr.pr,
        stage_name(gh.workflow_label(issue)),
    )
    _finalize_closed_issue_with_open_pr(context)
    if linked_pr.pr is not None and gh.pr_state(linked_pr.pr) == _ISSUE_STATE_CLOSED:
        _emit_closed_pr_rejection(context)
    return True
