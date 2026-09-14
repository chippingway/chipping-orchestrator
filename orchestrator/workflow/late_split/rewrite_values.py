# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Rewrite vocabulary, frozen authorization values, and valid entry stages.

Kinds, phases, and proof values are persisted wire strings. A recognized
kind also needs a stage that produces it; the pair is the authorization
boundary, including the state graph's own base-refresh stage set.
"""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from types import MappingProxyType

from orchestrator.workflow.state import WorkflowLabel
from orchestrator.workflow.transitions import rebased_by_the_base_refresh


class LateRewriteKind(StrEnum):
    """Which rewrite of its own the workflow may carry an exemption over.

    Bounded, and small on purpose: a member is a rewrite this workflow makes
    itself, over a checkout it is holding still, out of commits it can name
    both ends of. Three are, and two of them are rebases told apart by which
    owner runs one. The SQUASH a reviewer's approval earns collapses the
    accepted commit into an object of the orchestrator's own making. The
    AUTO_CLEAN_REBASE the per-tick refresh publishes replays it onto a base
    that moved -- the refresh holds a branch standing on an exempt commit out
    of the rebase only while the stage that has to act on that commit still
    has the issue, and past that handoff keeping the pushed head in step with
    base is the PR-aware sync's own job. The CONFLICT_REBASE is the replay
    `workflow:resolving_conflict` runs when a branch has stopped merging
    cleanly, which is the one rebase that refresh never drives: it does not
    own that label.

    No member is a claim that the contribution survived. A rebase that
    resolved content conflicts and a squash of work nobody adjudicated are
    both a kind this build authorizes carrying evidence that fingerprints to
    some other change, and the permit refuses them on the fingerprints rather
    than on the kind.

    A wire string this build does not know is not a kind to widen the
    vocabulary for at read time. It is a record from another build or a hand
    edit, and what it would license -- a human's verdict carried onto an
    object nothing here produced -- is the one thing this domain may never
    grant on evidence it cannot account for.
    """

    SQUASH = "squash"
    AUTO_CLEAN_REBASE = "auto_clean_rebase"
    CONFLICT_REBASE = "conflict_rebase"


# Which stages each kind is entered from, because the two fields are one claim
# rather than two. A rewrite record says which rewrite this workflow made and
# where it was made, and each half types perfectly on its own -- so a
# `conflict_rebase` recorded against `validating`, or a `squash` against
# `resolving_conflict`, passes every check asked a field at a time while
# describing a rewrite that stage does not make. Believed, it carries a
# human's verdict onto an object under a provenance nothing here can account
# for, which is the one thing this domain may never do.
#
# Each set is what its producer really names. The SQUASH is the push a
# reviewer's approval earns, made from `validating` and made there before the
# approval handoff relabels. The CONFLICT_REBASE is the replay
# `workflow:resolving_conflict` runs, and that owner spells its own label. The
# AUTO_CLEAN_REBASE names whichever stage the refresh found the issue on, so
# its set is the four that refresh drives -- and telling those from
# `resolving_conflict` is exactly what keeps the two rebase kinds apart.
#
# Every member also publishes onto a pull request the remote already carries,
# which is the predicate the entry a rewrite is made under was frozen against
# -- so this is the narrower of the two questions and never admits a record
# that one would refuse.
_ENTERED_FROM: Mapping[LateRewriteKind, frozenset] = MappingProxyType({
    LateRewriteKind.SQUASH: frozenset((WorkflowLabel.VALIDATING,)),
    LateRewriteKind.CONFLICT_REBASE: frozenset(
        (WorkflowLabel.RESOLVING_CONFLICT,),
    ),
})


def entered_from(
    kind: LateRewriteKind | None, stage: WorkflowLabel | None,
) -> bool:
    """Whether this stage is one that makes this kind of rewrite.

    The cross-field question, asked in one place so the reader and the writer
    cannot answer it differently -- and asked of the PAIR, since each field
    alone is a value this build knows and only the two together say whether
    the record describes a rewrite anything here produced.

    The refresh's own rebase is asked of the stages that refresh DRIVES rather
    than of a set spelled here, since what its evidence names is whichever of
    them the issue was on when the base moved.

    False for a kind this build does not authorize, which is the same answer
    the kind's own check gives: there is no stage that makes a rewrite nothing
    here knows how to make.
    """
    if kind == LateRewriteKind.AUTO_CLEAN_REBASE:
        return rebased_by_the_base_refresh(stage)
    return stage in _ENTERED_FROM.get(kind, frozenset())


class LateRewriteProof(StrEnum):
    """Which reading proved the push a transfer was settled on had landed.

    Beside the phase rather than with the record that reports it, because it
    is the other half of what `PUBLISHED` means: an exemption moves only onto
    a commit the remote holds, so a transfer that reached that phase reached
    it by one of exactly two proofs. `PUSHED` is the ordinary one -- a leased
    force-push moved the pull request off the head the permit was granted
    against. `ALREADY_PUBLISHED` is the recovery -- a tick that pushed and
    died before its receipt came back to a pull request standing there
    already, and the leased no-op that found it so is what proved it this
    time.

    Closed at two, because a remote standing anywhere else is not a third
    outcome: it is a permit that was refused, and a refused permit spends no
    permission and reports nothing.

    Recorded on the comment under `late_rewrite_proof` and dropped by the
    write that follows the record it feeds, so a process lost between the
    settlement and the report leaves the next reader something to report
    from. It sits OUTSIDE the authorization's own keys all the same: those
    are the evidence the permission was granted on, which a reader holds
    whole, and this is a note about a record that may already be out.
    """

    PUSHED = "pushed"
    ALREADY_PUBLISHED = "already_published"


class LateRewritePhase(StrEnum):
    """How far the transfer this record authorizes got.

    `AUTHORIZED` is written before the push and moves NOTHING: the exemption
    is still the commit a human ruled on, and what the record says is that a
    push for the rewritten one is outstanding. `PUBLISHED` is what the write
    that receipts that landed push moves it to, and that write is where the
    exemption is carried over -- `record_rewrite_publication` makes both moves
    at once, so no reader ever sees one without the other.

    So an outstanding permission says three things at once, and every reader
    here turns on one of them. A push is OWED for the commit it names, which
    is why the approval standing beside it may not be spent on the object id
    alone. The exemption has NOT moved, which is why the accepted end binds
    the record while it stands here and the rewritten one binds it after. And
    the move is still undoable, which is why a rollback may drop an
    `AUTHORIZED` permission -- the reset puts the branch back onto the commit
    the exemption never left -- while a `PUBLISHED` one describes a transfer
    the pull request already carries and an exemption already moved.
    """

    AUTHORIZED = "authorized"
    PUBLISHED = "published"


@dataclass(frozen=True)
class LateRewrite:
    """One rewrite a caller made of work a pull request already carries.

    The evidence a transfer is granted on, handed in by the owner that made
    the rewrite because every field is something no reading taken afterwards
    could recover: the commit and base the contribution came FROM are off the
    branch the moment it is rewound, and the head the pull request was
    standing on before the force-push is one the push itself moves.

    All eight travel because a transfer is granted on the whole of them and on
    nothing else. The two pairs are what the contribution is fingerprinted
    between, at both ends, so the equality is re-derived rather than asserted.
    The `kind` says which rewrite this workflow made, and it is bounded because
    what a member licenses is a commit the orchestrator produced itself. And
    the publication group -- the pull request, the stage it was entered from,
    and the pre-rewrite head the force-push is leased against -- is what scopes
    the whole claim to one push onto one pull request.

    The same record is what goes down on the pinned comment once a permit is
    granted, so what a later reader is held to is exactly what the grant was
    taken over rather than a second spelling of it.
    """

    kind: LateRewriteKind | None = None
    from_sha: str = ""
    from_base_sha: str = ""
    to_sha: str = ""
    to_base_sha: str = ""
    pr_number: int = 0
    source_stage: WorkflowLabel | None = None
    lease: str = ""


@dataclass(frozen=True)
class LateRewriteAuthorization:
    """One granted transfer, once every field of it proved out.

    Handed out whole or not at all, so nothing downstream has to decide what
    half of one means. Which end the exemption names when a reader holds this
    follows from the `phase` -- the accepted one at `authorized`, the
    rewritten one at `published` -- and the reader PROVES that rather than
    assuming it: the end and the exemption are separate pinned fields, and a
    comment where the bound one disagrees describes a transfer some later
    write moved the exemption off.

    The `fingerprint` is what the permission was granted OVER, and it is
    handed out to be compared: a caller re-deriving the contribution holds
    this digest to its own reading rather than carrying it forward, since a
    digest nobody checks is one a grant would quietly rewrite. And
    `fingerprint_format` travels with it because two digests taken under
    different rules are not comparable.
    """

    rewrite: LateRewrite
    phase: LateRewritePhase
    fingerprint: str
    fingerprint_format: int
