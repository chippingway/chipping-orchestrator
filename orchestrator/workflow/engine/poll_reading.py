# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Classify workflow labels and operator controls while preserving observed-close cleanup.

A paused or backlogged issue still ends a close already observed. Failed
label reads enter the family path, where processing isolates the issue
and reports any sustained failure.
"""
from __future__ import annotations

import logging

from github.Issue import Issue

from orchestrator.config import models as _config_models
from orchestrator.github.client import GitHubClient
from orchestrator.github.issues import (
    issue_is_closed,
)
from orchestrator.github.labels import hard_skip_control_label
from orchestrator.workflow.engine import (
    poll_models as _poll_models,
)

log = logging.getLogger("orchestrator.workflow")



def _cleanup_sweep_only(issue: Issue, label: str | None) -> bool:
    """True when this issue is here for its ledger and nothing else.

    A closed issue on one of the four cleanup-routed labels reaches a tick
    only because the cleanup sweep asked for it, and what it is owed is a pass
    over its generation ledger. Its label still names a stage handler -- one
    spawns the decomposer, one walks a dependency graph and activates
    children, one hands the issue to a developer -- so the closed reading has
    to be taken before the label is, or the sweep would be resuming the
    workflow a human closed.
    """
    return label in _poll_models._CLEANUP_ROUTE_LABELS and issue_is_closed(issue)


def _read_issue_routing(
    gh: GitHubClient, spec: _config_models.RepoSpec, issue: Issue,
) -> tuple[bool, str | None]:
    """Return ``(skip, label)`` from the issue's control / workflow labels.

    The label is reported whether or not the issue is skipped, because a
    caller that keeps a skipped one still has to bucket it -- and a parked
    issue answered `None` would read as the unlabeled pickup, which is a
    family-aware route and would flip the whole bucket cap-counted.
    """
    label = gh.workflow_label(issue)
    return _hard_skipped(spec, issue, label, _poll_models._POLLED_OPEN), label


def _hard_skipped(
    spec: _config_models.RepoSpec,
    issue: Issue,
    label: str | None,
    reading: _poll_models._PollReading,
) -> bool:
    """Whether a control label parks this issue outside the state machine.

    ``backlog`` / ``paused`` park everything, with one exception: an issue
    somebody observed CLOSED. Dropping one of those loses the close itself --
    an observed close ends a late cycle irreversibly, and the only pass that
    would ever record that is the one this filter is about to discard, so an
    owner paused while closed would come back from a reopen and an unpause
    with a live generation and spawn against it. So it is routed, and what
    the control label defers is everything past the mark: both the sweep and
    the dispatcher's own cancelled-cycle guard read the same label and stop
    there.

    Any of the three readings counts, because each is a close somebody saw:
    the bound cleanup route, the bound closed reading behind a label that
    names an ordinary terminal, and this tick's own look at a closed issue on
    a cleanup-swept label.
    """
    skip_label = hard_skip_control_label(issue)
    if skip_label is None:
        return False
    if reading.cleanup_only or reading.closed or _cleanup_sweep_only(
        issue, label,
    ):
        log.info(
            "repo=%s issue=#%s has %r and was observed closed; ending its "
            "late cycle and deferring everything else",
            spec.slug, issue.number, skip_label,
        )
        return False
    log.info(
        "repo=%s issue=#%s has %r; skipping",
        spec.slug, issue.number, skip_label,
    )
    return True


def _classify_pollable_issue(
    gh: GitHubClient, spec: _config_models.RepoSpec, issue: Issue,
) -> tuple[bool, str | None]:
    """Read one pollable issue's workflow label for the family / fanout split.

    Returns ``(skip, label)``. ``skip=True`` marks a hard-skip control label
    (``backlog`` / ``paused``): the operator parked the issue outside the
    state machine, so the caller drops it BEFORE the partition -- a parked,
    workflow-label-less issue folded into the family bucket would flip the
    whole bucket cap-counted and starve fanout under ``parallel_limit=1``
    (``_process_issue`` skips it anyway).

    A label-read failure (including one raised by ``hard_skip_control_label``
    itself) is reported as ``(False, None)`` so the issue is conservatively
    routed into the family bucket, where ``_process_issue``'s own per-issue
    exception isolation picks up any sustained failure. The label read runs
    on the caller thread so bucketing needs no extra worker-side round-trip.
    """
    try:
        return _read_issue_routing(gh, spec, issue)
    except Exception:
        log.exception(
            "repo=%s issue=#%s label read failed; routing to family bucket "
            "so per-issue exception isolation can pick up any sustained "
            "failure", spec.slug, issue.number,
        )
        return False, None
