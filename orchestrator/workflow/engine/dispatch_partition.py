# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Partition fresh poll results together with cleanup the observation registry still owes.

Closed fanout entries receive their durable observation before submission.
A missing issue in the poll response remains scheduled when a prior close
has not been settled.
"""
from __future__ import annotations

from github.Issue import Issue

from orchestrator.config import models as _config_models
from orchestrator.github.client import GitHubClient
from orchestrator.github.issues import (
    issue_is_closed,
)
from orchestrator.workflow.engine import (
    dispatch_closure as _dispatch_closure,
    poll_models as _poll_models,
    poll_reading as _poll_reading,
)


def _partition_pollable_issues(
    gh: GitHubClient,
    spec: _config_models.RepoSpec,
    deferred: frozenset[int] | None = None,
) -> _poll_models._PollablePartition:
    """Split this tick's pollable issues into the family and fanout buckets.

    Family-aware labels (``decomposing`` / ``blocked`` / ``umbrella``) and
    the unlabeled-pickup ``None`` are cross-issue writers -- a parent's
    ``_handle_decomposing`` recovery seeds ``parent_number`` on a child
    while the child's ``_handle_blocked`` would otherwise clobber the same
    pinned-state comment -- so they must never run two at a time and are
    collected into ``family_numbers`` (with index-aligned ``family_labels``).
    Every other label touches only its own per-issue state and fans out, as
    does a CLOSED issue on a cleanup-swept label, whose handler is the sweep
    rather than the stage its label names. A closed fan-out issue is
    additionally recorded in ``fanout_closed``, because what it runs is a
    cheap terminal finalize or a cleanup pass over a closed owner's ledger --
    neither spawns, so both are submitted cap-exempt. Hard-skip (``backlog``
    / ``paused``) issues are dropped entirely.

    A held close observation outranks both of those filters, because it is
    not a reading of this tick's at all: it is one an earlier poll took and
    could hand to nobody. An operator who parks the issue does not undo it --
    the sweep it routes to marks the cancellation and defers every external
    step, which is exactly what the park asks for -- and an issue the
    enumeration does not even yield is added on the strength of the
    observation alone, since a human who moved the label off the two the
    closed sweep queries would otherwise take the reading away for good.
    """
    builder = _poll_models._PollablePartitionBuilder(deferred=deferred or frozenset())
    for issue in gh.list_pollable_issues():
        _sorted_pollable(builder, gh, spec, issue)
    builder.add_unyielded()
    return builder.build()


def _sorted_pollable(
    builder: _poll_models._PollablePartitionBuilder,
    gh: GitHubClient,
    spec: _config_models.RepoSpec,
    issue: Issue,
) -> None:
    """Classify one yielded issue into the bucket its route names.

    A CLOSED reading is latched the moment this establishes it, which is the
    earliest anything in this process knows. What stands between here and the
    submit that would carry it is the rest of the enumeration -- a label read
    per issue in the repository -- and a worker holding this issue is asking
    the latch before every irreversible step it takes for the whole of that
    window. A reading latched only once the scheduler had refused would leave
    that worker free to spawn, create a child, or activate one against an
    issue this poll already saw ended.

    It is the same reading either way, and every path that carries it settles
    it: an admitted cleanup drops it once its pass has run, an admitted
    ordinary pass drops it where the record positively says there is nothing
    to end, and a refused submit keeps it deliberately.

    And it is written DOWN here too, not only latched. A latch is memory, so
    an accepted submit whose task never starts -- a scheduler shutdown, a
    process that dies before the worker takes it -- would otherwise leave the
    observation with no durable half at all, and a human who reopens the issue
    before the next process polls it takes the reading off the remote for
    good. The receipt is the only thing that survives that, so it goes on the
    thread while the record can still name the cycle it belongs to.

    It costs one pinned read per closed fan-out issue, and no more: the
    receipt is written from the object this enumeration already listed, and
    the same read answers whether the reading is owed at all -- an issue whose
    record says there is nothing to end has its latch dropped again here, so
    the machinery is carried only by the owners that actually need it.

    Only where the reading actually travels with the route: the closed
    fan-out set is exactly what carries one, and a closed issue drained in the
    family bucket is a hard human stop with nothing to finalize.
    """
    issue_number = int(issue.number)
    closed = issue_is_closed(issue)
    skip, label = _poll_reading._classify_pollable_issue(gh, spec, issue)
    if skip and not (closed or builder.owed(issue_number)):
        return
    builder.add(issue_number, label, closed)
    if issue_number in builder.fanout_closed:
        _dispatch_closure._recorded_at_poll(gh, spec, issue)
