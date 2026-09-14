# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What a decomposed parent reads off its children before it acts on them.

The scan is one fresh read of every recorded child's issue and workflow label.
It can be a fresh read because the dispatcher serializes `decomposing`,
`blocked`, and `umbrella` into a single bucket on one worker thread, so a
child's own label flip cannot land between this read and the writes that follow
it. A read that raises abandons the whole tick for this parent rather than
acting on a partial picture -- the next poll retries.

Two child states end the parent's tick instead of advancing it, and both park
idempotently so they do not re-comment every tick. A `rejected` child is a
human decision the parent cannot interpret. A child closed without a terminal
label is invisible to the closed-issue sweep, so its label is frozen wherever
it was at close and the parent would otherwise wait on it forever -- except
when the close was an external merge, which is why each candidate is retried
against the PR-merge finalize before it counts as manually closed.

A parent also re-checks the human's requirements here. Its own body may have
been edited while children were running, and unlike an implementing issue there
is no later stage to notice; the reroute back to `decomposing` re-derives the
manifest against what the body says now.
"""
from __future__ import annotations

import logging

from github.Issue import Issue

from orchestrator.config import models as _config_models, settings as config
from orchestrator.github.client import GitHubClient
from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.engine import drift as _drift, guards as _guards, terminals as _terminals
from orchestrator.workflow.stages.decomposition import state as _state
from orchestrator.workflow.stages.decomposition.models import _ChildScan

log = logging.getLogger("orchestrator.workflow")

# The labels a closed child may wear without the close being a human override:
# the two terminals, and the externally-merged transient the closed-in_review
# sweep finalizes on the next tick.
_ENDED_LABELS = (_state._DONE, "rejected", "in_review")


def _route_parent_drift(
    gh: GitHubClient, issue: Issue, state: PinnedState
) -> bool:
    """Route a decomposed parent (or blocked child) back to `decomposing`
    on a user-content edit.

    Returns True when drift was detected and the issue was re-routed
    (caller must return); False when the content is unchanged.

    The hash baseline is initialized by `_detect_user_content_change`
    itself on the first encounter, so a legacy issue still missing the
    field is durably seeded (via the helper's own `write_pinned_state`)
    rather than silently absorbing the next edit as the new baseline. Both
    parent and child cases route to decomposing so the manifest is
    re-derived against the updated body: silently persisting the new
    baseline for a child would let `_handle_ready` later see a matching
    hash and skip the re-decomposer even when the edited body now needs
    splitting. Parents with in-flight children list those children as
    orphans in the notice (the new manifest may overlap; the operator
    closes the obsolete ones manually).
    """
    new_hash = _drift._detect_user_content_change(gh, issue, state)
    if new_hash is None:
        return False
    orphans = list(state.get(_state._CHILDREN) or [])
    _drift._route_drift_to_decomposing(gh, issue, state, new_hash, orphans)
    gh.write_pinned_state(issue, state)
    return True


def _read_child_labels(
    gh: GitHubClient, issue: Issue, children: list,
) -> _ChildScan | None:
    """Fetch each recorded child issue and its current workflow label.

    Returns a child scan with issues and labels keyed by child number, or
    None if any child read raised (the caller returns and the tick retries
    on the next poll). Labels are read fresh here: the family-aware bucket
    (see `dispatch._FAMILY_AWARE_LABELS`) serializes decomposing / blocked
    / umbrella within a tick, so a child's own label flip cannot race this
    read.
    """
    child_labels: dict[int, str | None] = {}
    child_issues: dict[int, Issue] = {}
    for child_number in children:
        try:
            child_issue = gh.get_issue(int(child_number))
        except Exception:
            log.exception(
                "issue=#%s could not read child #%d", issue.number, child_number,
            )
            return None
        child_issues[int(child_number)] = child_issue
        child_labels[int(child_number)] = gh.workflow_label(child_issue)
    return _ChildScan(children, child_issues, child_labels)


def _park_rejected_children(
    gh: GitHubClient, issue: Issue, state: PinnedState, child_labels: dict,
) -> bool:
    """Park the parent when any child carries the `rejected` label.

    Returns True when parked (caller must return); False otherwise.
    Idempotent by `awaiting_human` so a rejected child does not re-park
    every tick.
    """
    rejected = [
        child_number
        for child_number, child_label in child_labels.items()
        if child_label == "rejected"
    ]
    if not rejected:
        return False
    if state.get(_state._AWAITING_HUMAN):
        return True
    rejected_refs = _state._issue_ref_list(rejected)
    _guards._park_awaiting_human(
        gh, issue, state,
        f"{config.HITL_MENTIONS} child issue(s) rejected: "
        f"{rejected_refs}; "
        "decide whether to re-decompose or close.",
        reason="child_rejected",
    )
    gh.write_pinned_state(issue, state)
    return True


def _remaining_manually_closed(
    gh: GitHubClient,
    spec: _config_models.RepoSpec,
    scan: _ChildScan,
    candidates: list[int],
) -> list[int]:
    remaining: list[int] = []
    for number in candidates:
        child_issue = scan.issues[number]
        child_state = gh.read_pinned_state(child_issue)
        if _terminals._finalize_if_pr_merged(gh, spec, child_issue, child_state):
            scan.labels[number] = _state._DONE
        else:
            remaining.append(number)
    return remaining


def _park_manually_closed_children(
    gh: GitHubClient, spec: _config_models.RepoSpec, issue: Issue, state: PinnedState,
    scan: _ChildScan,
) -> bool:
    """Park the parent when a child was closed without reaching a terminal
    label.

    Returns True when parked (caller must return); False otherwise. On the
    way, each closed candidate is retried against the PR-merge finalize
    helper and its `child_labels` entry is flipped to `done` if the merge
    finalized -- so an externally-merged child whose label was never
    advanced past an in-flight stage no longer strands the aggregation.

    A child closed manually (e.g. via the GitHub UI) before reaching
    `in_review` is invisible to `list_pollable_issues`, which only sweeps
    closed issues for a small label set (the externally-merged path). Its
    workflow label stays frozen at whatever it was at close, so without
    this branch the parent would read the stale label, neither the rejected
    nor the all-done branch would fire, and the parent would wait forever
    for a child that is gone. `in_review` is intentionally allowed: a
    state=closed/label=in_review child is the externally-merged transient
    that the closed-in_review sweep finalizes on the next tick, NOT a manual
    override.
    """
    manually_closed = _remaining_manually_closed(gh, spec, scan, [
        number for number, child_issue in scan.issues.items()
        if getattr(child_issue, "state", "open") == "closed"
        and scan.labels.get(number) not in _ENDED_LABELS
    ])
    if not manually_closed:
        return False
    if state.get(_state._AWAITING_HUMAN):
        return True
    closed_refs = _state._issue_ref_list(manually_closed)
    _guards._park_awaiting_human(
        gh, issue, state,
        f"{config.HITL_MENTIONS} child issue(s) closed without reaching "
        f"`done` or `rejected`: "
        f"{closed_refs}; "
        "decide whether to re-decompose or close.",
        reason="child_manually_closed",
    )
    gh.write_pinned_state(issue, state)
    return True


def _parked_on_children(
    gh: GitHubClient,
    spec: _config_models.RepoSpec,
    issue: Issue,
    state: PinnedState,
    scan: _ChildScan,
) -> bool:
    """Whether a child's disposition ends this parent's tick for a human.

    The two questions in the order they are asked, published apart from the
    scan they are asked of because one caller has something to do on the way
    out: an umbrella parked here is still the owner of whatever its split put
    on the remote, and every disposition that parks it -- a child rejected,
    a child closed by hand -- is one the reclamation rule counts as ended. So
    the parent that stops for a human still settles its ledger, and the park
    itself is unchanged either way.
    """
    if _park_rejected_children(gh, issue, state, scan.labels):
        return True
    return _park_manually_closed_children(gh, spec, issue, state, scan)


def _usable_child_scan(
    gh: GitHubClient,
    spec: _config_models.RepoSpec,
    issue: Issue,
    state: PinnedState,
    children: list,
) -> _ChildScan | None:
    scan = _read_child_labels(gh, issue, children)
    if scan is None:
        return None
    if _parked_on_children(gh, spec, issue, state, scan):
        return None
    return scan
