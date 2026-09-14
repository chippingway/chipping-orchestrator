# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Read-only predicates over a frozen late generation and its recorded evidence."""
from __future__ import annotations

from orchestrator.workflow.late_split import (
    formats as _formats,
    phases as _late_phases,
)
from orchestrator.workflow.transitions import publishes_onto_a_pull_request

# How deep automatic splitting may go. The root issue of a lineage is depth 0,
# so a generation may only split while its own depth is strictly below this:
# the deepest child a split can create sits exactly at the bound and must
# resolve as one change or ask a human. It is a safety invariant, not a knob,
# which is why no configuration reads it.
MAX_LINEAGE_DEPTH = 3


class _GenerationReading:
    """Whether recorded measurement, lineage, ledgers, and publication context prove a fact."""

    @property
    def is_present(self) -> bool:
        """Whether a late cycle was ever recorded on this issue."""
        return self.cycle_id > 0

    @property
    def is_oversized(self) -> bool:
        """Whether the measurement is strictly past the threshold it named.

        Strictly: a candidate exactly at the configured value is accepted, so
        the trigger cannot move by one line when the threshold is retuned. An
        unmeasured generation is not oversized -- a missing measurement is a
        typed failure to reconcile, never a small candidate.
        """
        if self.threshold is None or self.additions is None:
            return False
        return self.additions > self.threshold

    @property
    def may_split(self) -> bool:
        """Whether this generation is allowed to create another one.

        Read fail-closed, so every depth that is not a real one below the
        bound refuses the split rather than unlocking a generation the cap
        exists to forbid: a depth at or past the bound, a negative one, one
        that is not a whole number at all, and an unknown one -- which is what
        a damaged or missing field on a recorded cycle reads back as -- all
        answer False.
        """
        if not _formats.whole_number(self.lineage_depth):
            return False
        return 0 <= self.lineage_depth < MAX_LINEAGE_DEPTH

    @property
    def has_opaque_ledger(self) -> bool:
        """Whether an external obligation here is one this binary cannot type.

        The one answer a reclamation may not read past: an unknown consumer or
        an unknown resource is still an obligation, so nothing may treat the
        cleanup as complete or the snapshot as reclaimable while this holds.
        """
        return (
            self.opaque_resources is not None
            or self.opaque_consumers is not None
        )

    @property
    def split_has_settled(self) -> bool:
        """Whether this record's candidate has been made into children.

        Two readings of one fact, because either can be the only one there.
        The register is what the transaction writes down as it creates them
        and what the retirement keeps -- it is what says which child owns
        which slice of the manifest -- while the phase is what answers in the
        window before the first of those writes lands, which is the window
        `IN_FLIGHT_PHASES` exists for.

        What it buys the readers behind it is the difference between a
        candidate nobody counted and one nobody needs to. A settled split
        drops the measurement, because a record still answering "oversized"
        pins `workflow:decomposing` and would put the umbrella label back on
        every tick, and keeps the publication group, because the umbrella
        re-asks it in front of every child it releases and every branch it
        deletes. A group with no number beside it is otherwise exactly the
        shape of a tick that died between the freeze and the diff.
        """
        return bool(self.split_children) or self.phase in _late_phases._PAST_THE_SNAPSHOT

    @property
    def has_publication_context(self) -> bool:
        """Whether a post-publication entry carries what it is reconciled by.

        The flag is not that answer on its own. Every field beside it is read
        fail-closed, so a hand-edited or older pinned comment can leave the
        marker standing with the stage, the pull request, or the head it named
        gone -- and none of the three can be recovered from anywhere else: the
        label the adjudication runs under has replaced the one it came from by
        the time anything asks, the hold beside it names a pull request only
        because this group named one first, and the head is a commit the
        branch has already moved off. A group
        that cannot say all three says nothing an entry is reconciled from.

        The stage is asked what it IS as well as whether it is there, and by
        the same predicate the entry was frozen under: only the five states
        that push onto a pull request the remote already carries. A record
        naming any other -- `ready`, `blocked`, `umbrella`, or the
        `implementing` seam whose own push is what OPENS the pull request --
        describes a publication this workflow never enters one on, so reading
        it back as context would let a reconciliation measure and push a
        candidate no post-publication stage ever committed. Written that way
        it is refused; read back that way it is no context at all, which is
        the same answer a pre-publication record gives.
        """
        if not self.post_publication:
            return False
        if not publishes_onto_a_pull_request(self.source_stage):
            return False
        return bool(self.published_pr_number and self.published_sha)
