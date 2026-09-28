# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The pinned keys the conflict owners key their decisions on.

Every name here is written into the pinned JSON comment live issues already
carry, so renaming one is a migration of every open PR rather than a refactor.
They sit here rather than on whichever owner writes one first because the
writer is never the only reader: `conflict_round` is bumped by five different
exits and read by the cap that ends the loop, and `review_round` is reset by
this stage but consumed by the reviewer rounds `validating` counts after the
handoff.

The settled pair is the same rule one seam further on. A content update the
size gate holds is a round this stage finished and could not publish, and what
names it -- which of the four it was, and the head it produced -- is exactly
what a later tick cannot re-derive: the settlement publishes the commit, so the
resumed tick reads a branch that already carries its base and would call the
round a no-op flip.

The replay group is the same idea one seam further still: a record a tick
writes for a LATER tick to read, because what it says is destroyed by the very
step it describes. The preamble head is the settled pair's counterpart for a
push that finishes no round: what that push's own write leaves for the report
debt of the head it published.

One slot, one round. A resume that commits while a receipt is still outstanding
would write its own over it -- pushed, the owed round is cleared without ever
being counted; held, the gate writes over it -- so every road that starts one
yields until the owed round has been counted: the body edit at the door of the
handler, the human reply at the door of the rebase.
"""
from __future__ import annotations

_CONFLICT_ROUND = "conflict_round"

_REVIEW_ROUND = "review_round"

_AWAITING_HUMAN = "awaiting_human"

_PARK_REASON = "park_reason"

# The park reasons this stage records durably, and the ones no human can
# answer. A transient park is a reading that DID NOT HAPPEN -- a ref nothing
# resolved, a status nothing read, a head nothing could name -- so what clears
# it is the same reading taken again, not a reply. The tick that finds one
# standing therefore carries on with its ordinary work rather than waiting.
# A rewrite's report debt the pinned comment had no room for is the same shape
# from the other side: a WRITE that did not happen, which no reply makes room
# for and the next tick takes again before anything else.
_REASON_FETCH_FAILED = "fetch_failed"

_REASON_UNREADABLE_DIVERGENCE = "unreadable_divergence"

_REASON_UNREADABLE_HEAD = "unreadable_head"

_REASON_UNREADABLE_WORKTREE = "unreadable_worktree"

_REASON_UNPINNABLE_RECOVERY = "unpinnable_recovery"

_REASON_UNRECORDED_DEBT = "unrecorded_report_debt"

_TRANSIENT_PARKS = frozenset((
    _REASON_FETCH_FAILED,
    _REASON_UNREADABLE_DIVERGENCE,
    _REASON_UNREADABLE_HEAD,
    _REASON_UNREADABLE_WORKTREE,
    _REASON_UNPINNABLE_RECOVERY,
    _REASON_UNRECORDED_DEBT,
))

# The account one replay leaves of itself: the head it was about to replace,
# the fork point that head's contribution was read over, the commit the
# replay produced, and the pull request it was all made against. Written in
# two steps around the rebase, because the tick that runs a replay and the
# tick that publishes it are not always the same one -- a crash between the
# rebase and the size gate leaves the replayed commit on the branch and
# unpushed, and nothing readable off the branch afterwards tells it from a
# resolution an agent wrote or a fix commit a reroute sent over. The commit
# it PRODUCED is what makes a stale record inert: a later tick acts on this
# only where the branch is standing on exactly that object.
_REPLAY_FROM_SHA = "conflict_replay_from_sha"

_REPLAY_FROM_BASE_SHA = "conflict_replay_from_base_sha"

_REPLAY_TO_SHA = "conflict_replay_to_sha"

# The pull request the replay was made against, recorded beside the commits
# for the reason the commits are recorded at all: `pr_number` is a field a
# later tick can find pointing somewhere else, and a rewrite is evidence about
# ONE publication. Read off the comment at recovery time instead, a replay of
# this branch would be offered as a rewrite of whatever pull request the issue
# had come to record -- and another open one standing on the same head would
# pass every check the permit makes.
_REPLAY_PR_NUMBER = "conflict_replay_pr_number"

_REPLAY_KEYS = (
    _REPLAY_FROM_SHA,
    _REPLAY_FROM_BASE_SHA,
    _REPLAY_TO_SHA,
    _REPLAY_PR_NUMBER,
)

_SETTLED_OUTCOME = "conflict_settled_outcome"

_SETTLED_SHA = "conflict_settled_sha"

# The head a recovered push that precedes a rebase publishes, written into the
# gate's own write for the report debt that head is owed. The settled pair is
# no place for it: that push finishes no round, and a receipt would have the
# resumed tick close one the rebase has not run. But the head is on the pull
# request once the push lands, and a crash before the debt's own write, or an
# adjudication that publishes it later, leaves nothing else naming it.
_PREAMBLE_SHA = "conflict_preamble_sha"
