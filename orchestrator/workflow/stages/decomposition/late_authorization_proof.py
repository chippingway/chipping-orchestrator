# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Proof that a recorded oversized authorization still names this exact contribution.

Both the trusted command and a resumed publication must fingerprint the
frozen candidate and base. A changed digest leaves the candidate unpublished.
"""
from __future__ import annotations

import logging

from orchestrator.git.measurement import fingerprint as _fingerprint
from orchestrator.git.worktrees import paths as _worktree_paths
from orchestrator.workflow.late_split import (
    overrides as _overrides,
)
from orchestrator.workflow.stages.decomposition.late_models import _LateContext

log = logging.getLogger("orchestrator.workflow")



def _proved_contribution(context: _LateContext):
    """Recompute what the frozen pair contributes, or None if it cannot.

    Taken here rather than carried, and taken over the pinned pair rather than
    over whatever the checkout stands on. The worktree is writable for the
    whole of an adjudication and for the whole of the wait after it, so its
    head says nothing about what a human read; the frozen base and the frozen
    candidate are what the notice named and what the decision was made about.

    A reading this host cannot take leaves the park standing and the command
    unconsumed. Nothing about that is the operator's doing -- a store that
    cannot hand back the content between two commits it holds is repaired by
    an operator, not by a comment -- so the next tick takes the same reading
    again rather than asking a human to authorize the same change twice.
    """
    generation = context.generation
    contribution = _fingerprint._fingerprint_contribution(
        _worktree_paths._worktree_path(context.spec, context.issue.number),
        generation.base_sha,
        generation.candidate_sha,
    )
    if contribution.is_fingerprinted:
        return contribution
    log.warning(
        "issue=#%d cannot fingerprint what candidate %s contributes (%s); "
        "leaving the authorization unread and the candidate parked",
        context.issue.number,
        generation.candidate_sha,
        contribution.failure,
    )
    return None


def _publishes_unsplit(context: _LateContext) -> bool:
    """Whether an operator's authorization still covers THIS candidate.

    Asked by the settlement, of the record rather than of the thread: what a
    tick acts on is the durable evidence, so a process that died between the
    write and the publication finishes from what the write left.

    Every frozen term is compared, not the commit alone. The commit says which
    object was read; the base says what that object was read as CONTRIBUTING,
    and the two counts say the reading a human was shown when they decided. A
    generation that has moved under any of them is a different question from
    the one that was answered.

    Then the contribution is fingerprinted AGAIN and held to the digest the
    record carries, and that is the whole point of recording one. The terms
    above are the pinned comment agreeing with itself, which a hand edit, an
    older binary, and a record half-written by a crash can all arrange; the
    digest is the only term answered by the objects rather than by the record,
    so it is the only one that says the change about to publish is the change
    a human read. It is re-taken here rather than trusted from the tick that
    wrote it because the two are not the same tick: the publication can be
    reached by a later poll, on a later process, and on a host that never held
    the content between the pair.

    A reading this host cannot take is refused on the same footing as one that
    disagrees. Both leave the candidate where it stands with the authorization
    still on the record, and what that costs is a poll: the next tick takes
    the reading again, and a store somebody repairs publishes what they
    authorized without asking them to authorize it twice.

    WHICH answer was authorized is deliberately not asked here, because no
    term of the record could answer it: the same candidate can be adjudicated
    again, and every field would still match. What holds that line is the
    record being dropped with the answer it covers -- wherever a result is
    thrown away and wherever a re-freeze mints a fresh question -- so a record
    still readable here is one whose answer nothing has replaced.
    """
    override = _overrides.read_publication_override(context.state)
    if override is None:
        return False
    publication = override.publication
    if not _names_this_candidate(publication, context.generation):
        return False
    contribution = _proved_contribution(context)
    if contribution is None:
        return False
    if contribution.digest == publication.fingerprint:
        return True
    log.warning(
        "issue=#%d has an authorization for candidate %s whose contribution "
        "no longer fingerprints to the digest it was recorded on; leaving the "
        "candidate unpublished",
        context.issue.number,
        context.generation.candidate_sha,
    )
    return False


def _names_this_candidate(publication, generation) -> bool:
    """Whether the record's frozen terms are the ones on the record now.

    The cheap half of the question, asked first so a record about another
    candidate costs no reading at all. What it establishes is only that the
    two agree about which pair, how much, and against which ceiling -- the
    digest beside it is what establishes that the pair still contributes what
    a human was shown.
    """
    return (
        publication.candidate_sha == generation.candidate_sha
        and publication.base_sha == generation.base_sha
        and publication.additions == generation.additions
        and publication.threshold == generation.threshold
    )
