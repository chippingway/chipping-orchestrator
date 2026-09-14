# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The adjudicated issue one interrupted transfer is classified over, as doubles.

Every record this owner reads is written through its own producer rather than
spelled as pinned fields, so a case is seeded with exactly what a grant, a
settlement, a receipt, and an approval leave behind -- and a group damaged the
way a live comment gets damaged, by taking a member out of one that really
round-tripped.

The anchor IS the accepted commit here, because that is what an interrupted
auto-rebase of an adjudicated head looks like: the pull request is standing on
the commit a human ruled on, the force-push is leased against it, and the
replay the crash left is the object the exemption would have to move onto.
"""
from __future__ import annotations

import unittest
from dataclasses import replace

from orchestrator.git.base_sync import models, transfers
from orchestrator.workflow.late_split import (
    exemption as _exemption,
    rewrite_values as _rewrite_values,
    rewrites as _rewrites,
)
from orchestrator.workflow.stages.implementing import (
    late_approval_reading as _late_approval_reading,
    late_approval_state as _late_approval_state,
    late_publication_state as _late_publication_state,
)
from orchestrator.workflow.state import WorkflowLabel
from tests.git.base_sync import base_sync_helpers as fixtures
from tests.support.authorization import _authorize

DIGEST_LENGTH = 64

# The commit a human ruled on, which is also the head the pull request stands
# on and the anchor this attempt's push is leased against.
ACCEPTED_SHA = fixtures.PRE_REBASE_SHA

# The head the interrupted replay left on the checkout.
REPLAYED_SHA = fixtures.RECOVERED_SHA

# The base the adjudication measured the accepted commit over, and the base
# the rebase replayed it onto. Two commits, because that is what a base
# advance is.
ACCEPTED_BASE_SHA = "acce97ed" * 5
REPLAYED_BASE_SHA = "5eba5ed0" * 5

# A commit belonging to no part of this attempt, for the records that have to
# be refused because they name something else.
FOREIGN_SHA = "f00e1907" * 5

# The commit a LATER adjudication accepted, once work landed on top of the
# transfer a rotation already settled, and the head a fresh rebase of it
# replayed to. Two more, because a settled group is never cleared and the
# issue goes on earning verdicts over it.
NEWER_SHA = "1a7e5add" * 5
NEWER_REPLAY_SHA = "5eca7ded" * 5

# What the adjudicated contribution fingerprints to, and what a reading taken
# somewhere else answers instead.
DIGEST = "d" * DIGEST_LENGTH
OTHER_DIGEST = "c" * DIGEST_LENGTH

# The stage the interrupted rebase was entered from, and one it was not.
STAGE = WorkflowLabel.IN_REVIEW
OTHER_STAGE = WorkflowLabel.FIXING

# A publication that is not the one this recovery holds.
OTHER_PR_NUMBER = fixtures.PR_NUMBER + 1

# The permission the interrupted tick's own grant records: both pairs, the
# publication it was made against, and the head its push is leased to.
GRANTED = _rewrite_values.LateRewrite(
    kind=_rewrite_values.LateRewriteKind.AUTO_CLEAN_REBASE,
    from_sha=ACCEPTED_SHA,
    from_base_sha=ACCEPTED_BASE_SHA,
    to_sha=REPLAYED_SHA,
    to_base_sha=REPLAYED_BASE_SHA,
    pr_number=fixtures.PR_NUMBER,
    source_stage=STAGE,
    lease=ACCEPTED_SHA,
)

# What the attempt recorded about its own replay before it died, and the two
# shapes a recovery may still find instead: the window before that write, and
# a group something took a member out of.
RECORDED = models._PendingRewrite(
    sha=REPLAYED_SHA, pr_number=fixtures.PR_NUMBER, stage=STAGE,
)
DECLARED = models._PendingRewrite(
    pr_number=fixtures.PR_NUMBER, stage=STAGE,
)
DAMAGED = models._PendingRewrite(damaged=True)

# The comment an older binary left, which claims no record of the attempt at
# all -- the one shape a permission standing here is not cross-bound against.
ABSENT = models._PendingRewrite()


def context(**terms):
    """A recovery context for the interrupted attempt, on an empty comment.

    `terms` override the attempt this recovery came back to, so a case naming
    another anchor or another replay record says only what it is about.
    """
    return replace(
        fixtures._recovery_context(),
        **{"pending_rewrite": RECORDED, **terms},
    )


def owes(state, commit: str, lease: str) -> None:
    """Put a debt on the comment the way the gate's own grant would."""
    _late_approval_state._approve(
        state, commit, lease, _late_approval_reading.LateApprovalBasis.UNMEASURED,
    )


def adjudicated(state, *, accepted: str = ACCEPTED_SHA, identity: bool = True):
    """Record the verdict a settled `single` left, on the head it accepted.

    `identity=False` is the legacy shape: a comment written before the
    semantic record existed, so the exact commit is exempt and nothing on it
    says what that commit contributes.

    The terms an operator authorized the publication on go down either way,
    since an exemption is half a bypass and a rewrite of a commit only it
    names earns no transfer.
    """
    _exemption.record_exemption(state, accepted)
    if identity:
        _exemption.record_semantic_identity(
            state,
            base_sha=ACCEPTED_BASE_SHA,
            candidate_sha=accepted,
            fingerprint=DIGEST,
        )
    _authorize(state, accepted, ACCEPTED_BASE_SHA, DIGEST)


def granted(state, rewrite=GRANTED, *, digest: str = DIGEST):
    """Write both halves of one grant: the permission and the debt beside it.

    Together because the grant writes them in one durable statement -- the
    permission saying what a push may carry a verdict over, the debt saying
    the push is owed and what it is pinned to -- and a case seeding one
    without the other would be seeding a comment no grant ever produced.
    """
    _rewrites.record_rewrite_authorization(state, rewrite, digest)
    _late_approval_state._approve(
        state, rewrite.to_sha, rewrite.lease,
        _late_approval_reading.LateApprovalBasis.UNMEASURED,
    )


def settled(state, rewrite=GRANTED):
    """One whole transfer, from the grant to the receipt that spends it.

    The rotation, the receipt naming the push it was proved by, and the drop
    of the debt it paid, in the order one write puts them down. The grant is
    made here rather than by the caller because a settlement is what that
    grant becomes: a case seeding the second without the first would be
    spending a permission this issue never earned.
    """
    granted(state, rewrite)
    spent = _rewrites.record_rewrite_publication(
        state, _rewrite_values.LateRewriteProof.PUSHED,
    )
    _late_publication_state._record_publication(
        state, spent.to_sha, spent.lease, fixtures.PR_NUMBER,
    )
    _late_approval_state._forget_approval(state)
    return spent


def receipted(
    state,
    *,
    published: str = REPLAYED_SHA,
    superseded: str = ACCEPTED_SHA,
    pull_request: int = fixtures.PR_NUMBER,
):
    """Record the commit a push put on the remote, and what it replaced."""
    _late_publication_state._record_publication(state, published, superseded, pull_request)


class TransferCase(unittest.TestCase):
    """One interrupted rebase of a head an adjudication already accepted.

    The verdict is seeded by the fixture rather than by each case, because
    every question this owner answers is asked of an issue that HAS one: a
    comment carrying none takes the one road that costs nothing, and the cases
    about it say so by building their own.
    """

    def setUp(self) -> None:
        self._fresh()

    def _fresh(self, **terms) -> None:
        """Start over on the interrupted attempt, for the next case."""
        self.context = context(**terms)
        self.state = self.context.state
        adjudicated(self.state)

    def _carried(self, head: str = REPLAYED_SHA):
        """How far the transfer on this comment got, for the head in hand."""
        return transfers._carried_by(self.context, head)
