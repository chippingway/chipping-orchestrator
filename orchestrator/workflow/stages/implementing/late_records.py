# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Construct gate calls and mint reportable candidate generations.

A new generation advances durable identities, carries inherited scope and
lineage, and freezes the threshold read for this attempt. Post-publication
provenance is applied only when the generation does not already carry it.
"""
from __future__ import annotations

import logging
from dataclasses import replace
from pathlib import Path

from github.Issue import Issue

from orchestrator.config import models as _config_models, settings as config
from orchestrator.github import client as _client, pinned_state as _pinned_state
from orchestrator.workflow.late_split import (
    endings as _endings,
    identity as _identity,
    lineage as _lineage,
    phases as _late_phases,
)
from orchestrator.workflow.late_split.models import LateGeneration
from orchestrator.workflow.late_split.publication import PublicationContext
from orchestrator.workflow.stages.implementing import (
    late_gate_models as _late_gate_models,
    late_identity_reading as _late_identity_reading,
)

log = logging.getLogger("orchestrator.workflow")


def _gate(
    gh: _client.GitHubClient,
    spec: _config_models.RepoSpec,
    issue: Issue,
    state: _pinned_state.PinnedState,
    worktree: Path,
) -> _late_gate_models._Gate:
    """The subject one gate call is about, from what its caller was handed.

    A factory rather than five keywords at each site: every owner in this
    domain opens by building one, and spelling the same five fields out again
    each time is how one of them ends up carrying a different worktree from
    the checkout it is reading.
    """
    return _late_gate_models._Gate(
        gh=gh, spec=spec, issue=issue, state=state, worktree=worktree,
    )


def _minted(
    gate: _late_gate_models._Gate,
    recorded: LateGeneration,
    candidate_sha: str,
    base_sha: str,
) -> LateGeneration:
    """The generation this freeze records, under identities nothing reused.

    The cycle is this issue's own while one is live, and the number after the
    one a retirement dropped otherwise, so two attempts at the same issue are
    never the same attempt in a record. The generation counter advances with
    every candidate frozen inside a cycle, which is what keeps a verdict
    recorded against an earlier commit from reading as an answer to this one.

    The lineage comes off the ancestry wherever there is one, because that is
    the record a split WROTE about this issue and the one the split
    transaction checks its own generation against. An issue no split created
    is the root of its own lineage at depth 0; one whose ancestry records no
    readable depth stays unknown, which reads as "may not split" rather than
    as a root with room to spare.

    The readings a retry has already lost travel with the CANDIDATE rather
    than with the generation counter beside it, and that is what makes the
    bound reachable at all: a base the remote would not name records no base,
    so the next tick freezes afresh -- under a new generation, over the same
    commit -- and a count reset there would start every retry of that pair
    back at nothing. A candidate that MOVED is fresh work whose reading nobody
    has lost yet, so its own count starts at zero rather than inheriting one
    taken over a commit nothing measures any more.
    """
    return replace(
        _identified(gate, recorded),
        candidate_sha=candidate_sha,
        base_sha=base_sha,
        threshold=config.MAX_ADDED_LINES,
        additions=None,
        **_late_identity_reading._misses_of(recorded, candidate_sha),
    )


def _identified(gate: _late_gate_models._Gate, recorded: LateGeneration) -> LateGeneration:
    """The identities and the lineage a record of this attempt is joined by.

    Everything a record needs to be correlatable and nothing about a commit,
    so a failure taken before either end of the diff was established is still
    reportable under the cycle a later freeze writes.
    """
    ancestry = _lineage.read_late_ancestry(gate.state)
    root, depth = _late_identity_reading._lineage_of(gate, recorded, ancestry)
    return _entered(gate, replace(
        recorded,
        cycle_id=recorded.cycle_id or _identity.next_identity(
            _endings.read_retired_cycle(gate.state),
        ),
        generation=_identity.next_identity(recorded.generation),
        root_issue=root,
        current_issue=gate.issue.number,
        lineage_depth=depth,
        scope=recorded.scope or ancestry.scope,
        phase=_late_phases.LatePhase.MEASURING,
    ))


def _entered(gate: _late_gate_models._Gate, generation: LateGeneration) -> LateGeneration:
    """Stamp the publication this call was entered on onto one record.

    Every record a call writes goes through here, the measurement and the
    refusal alike, because the group is context rather than a result: what an
    operator has to be able to ask of a stream is which of two questions a
    record answers -- whether an unpublished candidate may be pushed at all,
    or whether a pull request the remote already carries may be pushed to
    again -- and a failure taken before either end of the diff was established
    is as much one of those as a count is.

    A call entered before anything was published stamps nothing, and that
    absence IS the answer: a record with no group describes an initial
    publication, which is what every record written from the implementing seam
    is and what a live pinned comment already says without having been
    migrated to say it.

    A record that already carries a WHOLE group is left exactly as it is, and
    that is a refusal rather than an optimization: the evidence a generation
    was frozen against is the evidence it is reconciled against, and a stamp
    that replaced it would let a reading taken over one publication be settled
    against another. The caller proves the two agree before anything reaches
    here -- a group that disagrees, or one too damaged to compare, refuses the
    tick outright -- so the only thing this can be asked to overwrite is a
    group identical to what it holds.
    """
    if gate.entry is None or generation.publication.is_complete:
        return generation
    return replace(
        generation, publication=PublicationContext.enter(
            stage=gate.entry.stage,
            pr_number=gate.entry.pr_number,
            published_sha=gate.entry.published_sha,
        ),
    )


def _named(
    gate: _late_gate_models._Gate, recorded: LateGeneration, candidate_sha: str,
) -> LateGeneration:
    """The record an attempt that NAMED a commit is retried under.

    A reading can fail with an id in hand: a revision that resolved and would
    not peel is the commonest, and the id it resolved to is the only record of
    which commit the attempt was about. Minting a generation around it is what
    turns "we could not read something" into "we could not read THIS", which
    is the difference between a retry that asks for one exact object and one
    that proves whatever the checkout points at by then.

    An attempt that named nothing, and one whose id the record already
    carries, are both left as they are: the first has no commit to mint
    around, and the second is already the record the retry will read.
    """
    if not candidate_sha or recorded.candidate_sha == candidate_sha:
        return _reportable(gate, recorded)
    return _minted(gate, recorded, candidate_sha, "")


def _reportable(gate: _late_gate_models._Gate, recorded: LateGeneration) -> LateGeneration:
    """The identity a failure is reported under, minted where there is none.

    A candidate the gate could not name is one no generation has been written
    for, and a record with no cycle is exactly what the sinks may not carry --
    so the identity is minted here rather than the failure going unreported.
    A DAMAGED record is the same problem wearing a cycle: the record gate
    refuses it just as flatly, and a record whose `late_current_issue` names
    another issue is worse than refused, since both sinks would accept it and
    file this issue's failure over there. Either way the refusal would be lost
    with the record it is about -- which is precisely the failure an operator
    has to be told about -- so the whole identity is asked, not just the
    cycle.

    Minted identities are deliberately not PERSISTED: a pinned record naming a
    cycle and no candidate freezes nothing, reconciles nothing, and would be
    read as a live cycle by the guard that ends one when the issue is closed.
    Minting is stable across retries -- the cycle is derived from what the
    record already says -- so a reading that keeps failing reports the same
    correlation each time rather than a new attempt per tick.
    """
    if _late_identity_reading._unusable_identity(gate, recorded) is None:
        return recorded
    return _identified(gate, recorded)
