# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The frozen publication context a late adjudication must reconcile.

The marker and its three identifying fields travel together. A strict entry
validates all three before claiming a publication; a pinned read may retain
an incomplete group, whose predicate refuses to treat it as usable context.
Keeping that distinction preserves an operator's damaged record for the
reconciliation that must park it rather than infer a different publication.
"""
from __future__ import annotations

from dataclasses import dataclass

from orchestrator.workflow.late_split import formats as _formats
from orchestrator.workflow.state import WorkflowLabel
from orchestrator.workflow.transitions import publishes_onto_a_pull_request


@dataclass(frozen=True)
class PublicationContext:
    """How a generation entered work the remote already carries."""

    post_publication: bool = False
    source_stage: WorkflowLabel | None = None
    published_pr_number: int | None = None
    published_sha: str = ""

    @property
    def is_complete(self) -> bool:
        """Whether a post-publication entry carries what it is reconciled by.

        The flag is not that answer on its own. Every field beside it is read
        fail-closed, so a hand-edited or older pinned comment can leave the
        marker standing with the stage, the pull request, or the head it named
        gone -- and none of the three can be recovered from anywhere else: the
        label the adjudication runs under has replaced the one it came from by
        the time anything asks, the hold beside it names a pull request only
        because this group named one first, and the head is a commit the
        branch has already moved off. A group that cannot say all three says
        nothing an entry is reconciled from.

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

    @classmethod
    def enter(
        cls, *, stage: str, pr_number: int, published_sha: str,
    ) -> PublicationContext:
        """Record the stage, pull request, and head a publication was entered on.

        All three are proved here rather than left to the write, for the
        reason the exemption is proved where it is recorded: the pinned write
        drops what it cannot type, so a stage that is not a workflow state, a
        pull request that is not an identity, or a head that is not a whole
        object id would each leave the marker standing over a context nothing
        could reconcile -- and the reader on the far side would report a
        post-publication entry with no publication in it. A caller that cannot
        name all three has an entry this domain must not record as one.

        The stage is taken through the label vocabulary rather than kept as
        whatever was passed, for the reason a restart target is: what it names
        is the state a settled adjudication puts the issue back into, and a
        string nobody looked up would reach a later tick wearing this domain's
        word that the workflow has such a state.

        Being a state is not enough, and the same predicate the entry is
        frozen under is what says which: the five that push onto a pull
        request the remote already carries. `ready`, `blocked`, and `umbrella`
        each have an edge to the adjudication for reasons of their own and no
        pull request behind any of them, and `implementing`'s own push is the
        one that OPENS the pull request. Recorded from one of those, the group
        would send a later reconciliation to measure and push a candidate no
        post-publication stage ever committed.
        """
        if stage not in WorkflowLabel or not publishes_onto_a_pull_request(
            WorkflowLabel(stage),
        ):
            raise _formats.InvalidLateValue(
                "source stage is not one a publication is entered from "
                f"({type(stage).__name__})",
            )
        if not _formats.whole_number(pr_number) or pr_number <= 0:
            raise _formats.InvalidLateValue(
                "published PR is not an identity "
                f"({type(pr_number).__name__})",
            )
        if not _formats.is_hex_of(published_sha, _formats.COMMIT_LENGTHS):
            raise _formats.InvalidLateValue(
                "published head is not a commit "
                f"({type(published_sha).__name__})",
            )
        return cls(
            post_publication=True,
            source_stage=WorkflowLabel(stage),
            published_pr_number=pr_number,
            published_sha=published_sha,
        )
