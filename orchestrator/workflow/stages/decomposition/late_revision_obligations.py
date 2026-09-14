# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What the adjudication before this one already did outside this process.

Asked once, ahead of the notice and ahead of the spawn, because a revision
ends in a NEW candidate under a new generation and everything that generation
decides is decided about work the old one may already have handed to something
this process does not own. Two effects put a candidate past the point of
replacement, and both are read off the record rather than guessed.

**Children.** They exist as real GitHub issues, carry an ancestry naming the
adjudication that made them, and are recorded as the consumers a snapshot is
retained for -- so a second manifest over the top of them would strand every
one: nothing polls a child the parent no longer records, and no automatic rule
can say which of two manifests a human meant.

**A snapshot obligation.** The ref is named for the generation but the commit
under it is the candidate that generation froze, and the reclamation proves a
ref is ours to delete by comparing the two. A revision moves `candidate_sha`
and leaves the entry pointing at a ref that no longer matches it, so the
reclamation reads a mismatch and refuses -- forever, holding the umbrella's
terminal open over a ref nothing can settle. The entry is refused in every
state it can be in, because none of them proves the ref is absent: `pending`
is a push that may have landed, and `failed` is a create that may have landed
and a verification that did not.

So the issue is handed back instead. What the human asked for is not lost --
their comment stands, whatever the split created stands, and the recorded
verdict stands -- and settling it is a decision about things that already
exist, which is theirs to make.

The hand-back is the reconciliation owner's own park rather than one written
here. A refusal is a late exit like every other: it stages the same reason,
completes on the same record, and rides out past the same fresh owner read --
so the issue learns about it on exactly the terms a reconciliation that failed
would have used.
"""
from __future__ import annotations

from orchestrator.workflow.late_split.obligations import LateResourceKind
from orchestrator.workflow.stages.decomposition import (
    late_park_state as _late_park_state,
    late_revision_reconciliation as _late_reconciliation,
)
from orchestrator.workflow.stages.decomposition.late_content_models import _LateContentSettlement
from orchestrator.workflow.stages.decomposition.late_models import _LateContext

_STRANDED_CHILDREN_PARK = (
    "this issue's committed candidate cannot be revised: the adjudication "
    "before this one already created {children} from it, and a new candidate "
    "would be split into a manifest that has nothing to do with them. The "
    "children, the recorded verdict, and your comment all stand. Decide what "
    "the existing children should be first -- close them and clear this "
    "issue's `late_split_children`, or let them run -- and the next tick "
    "continues from there."
)

_STRANDED_SNAPSHOT_PARK = (
    "this issue's committed candidate cannot be revised: the adjudication "
    "before this one has already asked the remote to preserve it, and this "
    "issue records that obligation. A new candidate would replace the commit "
    "the reclamation names, leaving the ref it created behind for good -- "
    "nothing would then be able to prove the ref is ours to delete. The "
    "recorded verdict and your comment both stand. Let the split finish, or "
    "settle the snapshot obligation on this issue by hand, and the next tick "
    "continues from there."
)


def _stranded_by_effects(
    context: _LateContext,
) -> _LateContentSettlement | None:
    """Refuse to replace a candidate whose split has already acted outside.

    `None` is the answer for a candidate still free to be replaced, which is
    what lets the revision carry on. The children are asked about first
    because they are the effect a human can see and the park can name them;
    the snapshot obligation is the one only the record knows about, and it
    stands on its own wherever no child was ever created from it.
    """
    if context.generation.split_children:
        return _late_reconciliation._parked(
            context, _STRANDED_CHILDREN_PARK.format(
                children=", ".join(
                    f"#{number}"
                    for number in context.generation.split_children
                ),
            ),
            reason=_late_park_state.PARK_REVISION_UNANSWERED,
        )
    if not _owes_a_snapshot(context.generation):
        return None
    return _late_reconciliation._parked(
        context,
        _STRANDED_SNAPSHOT_PARK,
        reason=_late_park_state.PARK_REVISION_UNANSWERED,
    )


def _owes_a_snapshot(generation) -> bool:
    """Whether this issue records a snapshot the remote may already hold.

    An opaque ledger answers yes: an entry this binary could not type may be
    exactly that obligation, and the one reading it must not take is the one
    that lets the candidate under it be replaced.
    """
    if generation.obligations.is_opaque:
        return True
    return any(
        entry.kind == LateResourceKind.SNAPSHOT_REF
        for entry in generation.obligations.resources
    )
