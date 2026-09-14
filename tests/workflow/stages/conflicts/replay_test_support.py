# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The one adjudicated branch this stage's replay tests rebase and publish.

A `single` verdict has already accepted the commit the pull request is standing
on, so the checkout, the remote, and the exemption all name the same object --
which is what a live issue looks like when its base moves under an approved
change. Every case here is that world with one thing replaced: the contribution
the replay produced, the fork points either end was read over, or the record
the exemption carries beside it.

The two comments a CRASH leaves are seeded from here too, because both are
that same world one write on and between them they are the whole of what
carries an exemption across a tick boundary. A rebase records what it is about
to replace before it runs and the commit it produced before it reaches the
gate; the gate's own grant then records the permission and the debt before the
push. So a tick that finds the replayed commit unpushed is answered from one
of those records -- never from anything it can read off the branch.
"""
from __future__ import annotations

from types import MappingProxyType

from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.late_split import (
    exemption as _exemption,
    exemption_reading as _exemption_reading,
    rewrite_values as _rewrite_values,
    rewrites as _rewrites,
)
from orchestrator.workflow.stages.conflicts import state as _state
from orchestrator.workflow.stages.implementing import (
    late_approval_reading as _late_approval_reading,
    late_approval_state as _late_approval_state,
)
from orchestrator.workflow.state import WorkflowLabel
from tests.support.authorization import _authorize
from tests.workflow.repo_values import (
    CONTRIBUTION_DIGEST,
    DIGEST_LENGTH,
    FORK_POINT_SHA,
    MEASURED_BASE_SHA,
    REPLAYED_FORK_POINT_SHA,
)
from tests.workflow.stages.conflicts.conflicts_test_support import (
    CONFLICT_PR_HEAD_SHA,
    RESOLVED_HEAD_SHA,
)

CONFLICT_ISSUE = 200
CONFLICT_PR = 800

# The commit a human adjudicated. It is the head the pull request stands on and
# the head this stage reads before it replays anything, because in production
# the three are one fact: an accepted candidate is published, and the branch is
# proved in sync with its remote before any rebase runs.
ADJUDICATED_HEAD = CONFLICT_PR_HEAD_SHA

# The commit the replay produced, and the one the gate proves the checkout to.
REPLAYED_HEAD = RESOLVED_HEAD_SHA

# The base the adjudication froze its reading over -- deliberately neither fork
# point below, since the record's own pair is what the accepted contribution is
# read between and a caller's claim about what it replaced is held to that by
# DIGEST rather than by spelling.
ADJUDICATED_BASE = MEASURED_BASE_SHA

# What a contribution that picked something up along the way fingerprints to.
OTHER_DIGEST = "a" * DIGEST_LENGTH

# Where each end of one replay left the base. Two answers, because that is the
# whole of what a rebase moves.
REPLAY_FORK_POINTS = MappingProxyType({
    ADJUDICATED_HEAD: FORK_POINT_SHA,
    REPLAYED_HEAD: REPLAYED_FORK_POINT_SHA,
})

# What `git rev-list --count HEAD..origin/<base>` answers for a branch whose
# unpushed commits already carry their base, and for one still behind it. The
# first is a replay an earlier tick ran; the second is the `fixing` reroute's
# fix commits on a stale base.
ON_BASE = "0\n"
BEHIND_BASE = "2\n"

# Every exemption that names a commit and cannot say which CHANGE it is: a
# comment written before the semantic record existed, and that record with a
# member a hand edit took. All of them leave the exact-SHA exemption exempting
# exactly the commit it names, and none of them can be carried onto anything.
UNTRANSFERABLE_EXEMPTIONS = MappingProxyType({
    "one recorded before the identity existed": (),
    "one a hand edit took the digest from": (
        _exemption_reading.LATE_EXEMPT_FINGERPRINT,
    ),
    "one a hand edit took the base from": (_exemption_reading.LATE_EXEMPT_BASE_SHA,),
})


# The permission the clean rebase's own grant records, naming both pairs, the
# publication it was made against, and the head its push is leased to. The
# recovery has no evidence of its own, so this record is the whole of what a
# tick finding the replayed commit unpushed may be answered from.
GRANTED_REPLAY = _rewrite_values.LateRewrite(
    kind=_rewrite_values.LateRewriteKind.CONFLICT_REBASE,
    from_sha=ADJUDICATED_HEAD,
    from_base_sha=FORK_POINT_SHA,
    to_sha=REPLAYED_HEAD,
    to_base_sha=REPLAYED_FORK_POINT_SHA,
    pr_number=CONFLICT_PR,
    source_stage=WorkflowLabel.RESOLVING_CONFLICT,
    lease=ADJUDICATED_HEAD,
)


def adjudicated_state(*, identity: bool = True, damaged: tuple = ()) -> dict:
    """The pinned fields a settled `single` verdict leaves on this issue.

    Written through the record's own owners rather than spelled out, so a case
    is seeded with exactly what an adjudication produces -- and damaged the way
    a live comment gets damaged, by taking a member out of a group that really
    round-tripped.

    The terms an operator authorized the publication on go down with the
    verdict, since an exemption is half a bypass and a replay of a commit only
    it names earns no transfer.
    """
    state = PinnedState(state_data={})
    _exemption.record_exemption(state, ADJUDICATED_HEAD)
    if identity:
        _exemption.record_semantic_identity(
            state,
            base_sha=ADJUDICATED_BASE,
            candidate_sha=ADJUDICATED_HEAD,
            fingerprint=CONTRIBUTION_DIGEST,
        )
    _authorize(
        state, ADJUDICATED_HEAD, ADJUDICATED_BASE, CONTRIBUTION_DIGEST,
    )
    for taken in damaged:
        state.data.pop(taken, None)
    return state.data


def granted_state() -> dict:
    """The comment a clean rebase leaves between its grant and its push.

    Both halves, because the grant writes both in one durable write: the
    permission that says what the push may carry over, and the debt that says
    the push is owed at all. A case seeding one without the other would be
    seeding a comment no grant ever produced -- and the debt is what tells the
    gate to defer to the permit rather than spend the approval on an object id.

    Built ON the replay record, because that is the order the writes happen
    in: the rebase stamps the commit it produced before the gate is entered,
    and the gate's own grant follows. A comment carrying the permission and no
    replay record is one no tick ever leaves -- and the divergence guard would
    park it, since the record is what accounts for a replayed branch standing
    off its publication.
    """
    state = PinnedState(state_data=replayed_state())
    _rewrites.record_rewrite_authorization(
        state, GRANTED_REPLAY, CONTRIBUTION_DIGEST,
    )
    _late_approval_state._approve(
        state, REPLAYED_HEAD, ADJUDICATED_HEAD,
        _late_approval_reading.LateApprovalBasis.UNMEASURED,
    )
    return state.data


def replayed_state(**damage) -> dict:
    """The comment a rebase leaves between its own second write and the grant.

    The window the replay record exists for: the branch has been replayed and
    the commit is unpushed, and the tick that would have granted a permission
    for it never got there. Spelled from the owner's own key names, since the
    two writes that really produce this group are what the clean-rebase cases
    beside these drive end to end.

    `damage` replaces one member of that group with what a hand edit or an
    older binary leaves, which is the only way a live comment gets one: the
    writer refuses a group it cannot name every end of, so a case spelling a
    damaged one straight out would be seeding a shape this domain never
    produces.
    """
    state = PinnedState(state_data=adjudicated_state())
    recorded = {
        _state._REPLAY_FROM_SHA: ADJUDICATED_HEAD,
        _state._REPLAY_FROM_BASE_SHA: FORK_POINT_SHA,
        _state._REPLAY_TO_SHA: REPLAYED_HEAD,
        _state._REPLAY_PR_NUMBER: CONFLICT_PR,
        **damage,
    }
    for key, written in recorded.items():
        state.set(key, written)
    return state.data


# Every way the group a replay left cannot be shown to be about the commit and
# the publication in hand. A None is the field being absent -- a crash between
# the two writes, or a comment written before the group existed -- and
# anything else is a value nothing here would have written.
UNUSABLE_REPLAYS = MappingProxyType({
    "one that names no pull request": {_state._REPLAY_PR_NUMBER: None},
    "one whose pull request is no identity": {_state._REPLAY_PR_NUMBER: 0},
    "one whose pull request is prose": {
        _state._REPLAY_PR_NUMBER: "the plan PR",
    },
    "one that names no replayed commit": {_state._REPLAY_TO_SHA: None},
    "one with an abbreviated replaced head": {
        _state._REPLAY_FROM_SHA: ADJUDICATED_HEAD[:7],
    },
    "one that names no fork point": {_state._REPLAY_FROM_BASE_SHA: None},
})
