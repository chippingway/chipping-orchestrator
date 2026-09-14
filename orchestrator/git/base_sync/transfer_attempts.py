# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Match a rewrite authorization to the exact interrupted rebase attempt.

The lease, pending publication, and adjudicated fingerprint must agree.
Settled permissions name the rewritten pair, while outstanding ones still
name the pair from which the exemption would move.
"""
from __future__ import annotations

from orchestrator.git.base_sync import transfer_values as _transfer_values


def _made_by_this_attempt(context, authorization, local_head) -> bool:
    """Whether every term of this permission belongs to the attempt in hand.

    The reader above proves the group is WHOLE and that its rewritten end is
    the commit on this checkout. Whole is not the same as this attempt's: each
    field is individually well-shaped, and a comment where the publication,
    the leased head, or the digest came from somewhere else reads back exactly
    as cleanly as one that did not. Acted on, the caller finishes -- clears
    the anchor, posts a notice, files an event -- over a transfer it cannot
    tie to the rebase it is recovering.

    So the record is cross-bound to the two things that CAN say which attempt
    this is. The attempt's own record names the replay it made and the
    publication it made it for, and the anchor names the head its force-push
    was leased against; those are the three the permit itself is scoped by.
    And the semantic identity names the pair the digest was taken between --
    the accepted one while the transfer stands, the rewritten one once the
    receipt has moved it -- so a target base or a fingerprint from another
    reading is a contribution this issue never adjudicated.
    """
    rewrite = authorization.rewrite
    if rewrite.lease != context.pending_pre_rebase_sha:
        return False
    if not _agrees_with_the_attempt(
        context.pending_rewrite, rewrite, local_head,
    ):
        return False
    return _names_the_adjudicated_pair(context, authorization)


def _agrees_with_the_attempt(recorded, rewrite, local_head) -> bool:
    """Whether the attempt's own record and this permission say one thing.

    The permission is granted INSIDE the gate, and the replay the attempt made
    goes down before that gate is entered -- so a permission standing here
    cannot be older than the record beside it, and anywhere the two disagree
    one of them is describing something else.

    Three disagreements, and each of them reads back cleanly on its own. A
    record naming a head that is not the one in hand says out loud that this
    checkout is not that attempt's work, while the permission says it is. A
    record carrying the terms and no head still says which publication the
    attempt was for, so terms that are not the permission's own scope it to a
    push nobody made here. And a record that CLAIMS the group and cannot show
    it -- a member taken out, a head that is not a commit, a stage no
    publication is entered from -- can say neither, which is not the same as
    saying nothing.

    Silent only where there is no record at all. A comment written before this
    group existed carries the anchor and nothing beside it, and the permission
    is then held by its lease and the adjudicated pair alone -- which is the
    compatibility this owner owes issues that earned a verdict first.
    """
    if recorded.damaged:
        return False
    if not recorded.is_declared:
        return True
    if recorded.sha and not recorded.names(local_head):
        return False
    return (rewrite.pr_number, rewrite.source_stage) == (
        recorded.pr_number, recorded.stage,
    )


def _names_the_adjudicated_pair(context, authorization) -> bool:
    """Whether the digest and the pair this record carries are the issue's.

    The end the phase binds is the one the semantic identity has to name --
    the accepted commit and the base it was measured over while the transfer
    stands, the rewritten commit and the base it was replayed onto once the
    receipt has moved it -- and the digest between them is the one the grant
    was taken over. A record carrying a pair or a digest from another reading
    describes a contribution this issue never adjudicated, however well each
    field is shaped on its own.
    """
    from orchestrator.workflow.late_split import (
        exemption_reading as _exemption_reading,
    )
    identity = _exemption_reading.read_semantic_identity(context.state)
    if identity is None or identity.fingerprint != authorization.fingerprint:
        return False
    rewrite = authorization.rewrite
    named = (
        (rewrite.to_sha, rewrite.to_base_sha) if _transfer_values._is_settled(authorization)
        else (rewrite.from_sha, rewrite.from_base_sha)
    )
    return (identity.candidate_sha, identity.base_sha) == named
