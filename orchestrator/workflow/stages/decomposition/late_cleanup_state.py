# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Late-cleanup pass values, obligation updates, and observed-close persistence.

One pass keeps its issue and scan together. Resource updates retain failed
readings, and a close is made durable once before reclamation continues
with the cancelled generation.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, replace

from github.Issue import Issue

from orchestrator.config import models as _config_models
from orchestrator.github.client import GitHubClient
from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.engine import observations as _observations
from orchestrator.workflow.late_split import (
    formats as _formats,
    obligations as _obligations,
    state as _late_state,
)
from orchestrator.workflow.late_split.models import LateGeneration
from orchestrator.workflow.stages.decomposition import (
    late_cancellation_state as _late_cancellation_state,
)
from orchestrator.workflow.stages.decomposition.models import _ChildScan

log = logging.getLogger("orchestrator.workflow")


_BRANCH = _obligations.LateResourceKind.BRANCH


@dataclass(frozen=True)
class _Pass:
    """One issue's reclamation pass, and what it reads its rules against.

    Held together because the steps below are not independent: the delete is
    ordered on the record, carried out against the remote, announced on the
    consumers, and only then recorded -- and every one of those needs the same
    issue, the same pinned comment, and the same scan.
    """

    gh: GitHubClient
    spec: _config_models.RepoSpec
    issue: Issue
    state: PinnedState
    scan: _ChildScan

    def persist(self, generation: LateGeneration) -> None:
        """Make one step of this pass durable before the next one acts."""
        _late_state.write_late_generation(self.state, generation)
        self.gh.write_pinned_state(self.issue, self.state)


@dataclass(frozen=True)
class _Reclamation:
    """What one pass over this issue's obligations settled, and what it did not.

    `entries` holds every obligation this pass ACTED on, in the state the
    record now gives them, and it is what the per-visit log line is drawn
    from: a visit that keeps happening is happening for one of these, and
    saying so on each of them is what makes an unreclaimable object visible.

    `moved` is the subset whose recorded state this visit actually CHANGED,
    and it is what the sinks and the pinned write are drawn from instead. The
    two differ exactly where a retry keeps giving the same answer -- a remote
    that goes on refusing one delete, a consumer that goes on being live --
    and that is the shape a per-visit record would repeat forever: one
    `late_cleanup`, one `late_failure`, and one comment write per sweep, for
    as long as the refusal lasts. The transition is the news; the standing
    state is what the log and the held terminal already say.
    """

    generation: LateGeneration
    entries: tuple[_obligations.LateResource, ...] = ()
    moved: tuple[_obligations.LateResource, ...] = ()

    @property
    def attempted(self) -> bool:
        """Whether anything was asked of the remote at all."""
        return bool(self.entries)


def _observed_close(
    walk: _Pass, generation: LateGeneration,
) -> LateGeneration:
    """Mark a close a poll observed while this pass was reclaiming.

    The barrier every step of a reclamation is asked past, and it costs no
    request -- which is why it can be asked as often as there are steps. The
    write behind it happens once, on the pass that first reads one: a record
    that already carries the mark is handed straight back.

    Cancellation state is persisted by its independent owner; reclamation
    keeps the same generation and outstanding obligations through that write.
    """
    if generation.cancelled:
        return generation
    if not _observations.close_observed(walk.spec.slug, walk.issue.number):
        return generation
    return _late_cancellation_state._marked(
        walk.gh, walk.issue, walk.state, generation,
    )


def _recorded(
    generation: LateGeneration,
    kind: _obligations.LateResourceKind,
    target: str,
    settled: _obligations.LateResourceState,
) -> LateGeneration:
    """Move one obligation to the state this pass just established for it."""
    try:
        return replace(
            generation, obligations=generation.obligations.with_resource(_obligations.LateResource(
                kind=kind, target=target, resource_state=settled,
            )),
        )
    except _formats.InvalidLateValue:
        log.exception("could not record the %s obligation %r", kind, target)
        return generation


def _record_branch_obligation(
    generation: LateGeneration, branch: str,
) -> LateGeneration:
    """Return this generation owing the remote one superseded branch.

    Written by the transaction before it attempts the delete, so a crash in
    between leaves the obligation for the umbrella above to retry rather than
    a branch nothing on the issue names.
    """
    return replace(
        generation, obligations=generation.obligations.with_resource(_obligations.LateResource(
            kind=_BRANCH, target=branch, resource_state=_obligations.LateResourceState.PENDING,
        )),
    )
