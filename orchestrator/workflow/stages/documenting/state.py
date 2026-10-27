# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The pinned-state keys the documenting owners share.

Every name here is a key in the JSON comment live issues already carry, so
these are wire strings rather than internal spellings: renaming one is a
migration of every open issue, not a refactor. They sit in one module because
the owner that writes a key is rarely the owner that reads it -- the park that
stamps `park_reason` is not the precondition that classifies a continue
against it, and the resume that advances `last_action_comment_id` is not the
drift block that reads it back to decide whether a retry signal arrived.
"""
from __future__ import annotations

_PARK_REASON = "park_reason"

_AWAITING_HUMAN = "awaiting_human"

_LAST_ACTION_COMMENT_ID = "last_action_comment_id"

# Whether a drift unwind is still half-finished: set the moment the stale
# approval is dropped and cleared only by the relabel that ends it, so an
# unwind whose worktree reconcile parked is re-entered rather than falling
# through to a docs pass against the OLD body.
_UNWIND_PENDING = "docs_drift_unwind_pending"

# The comment that unwind asked its human for, and the boundary its silence is
# kept behind. It is NOT the reply boundary: no agent runs on that road, so the
# words that moved the requirements are delivered to nobody and
# `last_action_comment_id` stays where it was, below them, for a developer
# resumed past it to be handed them. This field is what the retry
# gate reads instead -- only a trusted reply ABOVE the notice is the "try it
# again" signal -- and it is additive, so an issue parked before it existed
# falls back to the cursor, which is where that park left its mark.
_UNWIND_ASKED_AT = "docs_drift_unwind_asked_at"

# The head a docs pass was last read against, which `in_review`'s merge gate
# pings on with a `docs_verdict` beside it. Every shape re-anchors it on the
# head it is about, and a pass that publishes re-anchors it again on the commit
# it hands the size gate, so the record never names one commit while the fields
# beside it name another.
_CHECKED_DOCS_SHA = "docs_checked_sha"

# The head an Antigravity docs pass was launched on, landed alone ahead of the
# launch and standing until the run's outcome is recorded or proved not to need
# it. A tick that ends before any disposition -- a live pause over a pass that
# fell short, a quota retirement that withheld the tick -- writes nothing and
# leaves it, so the next tick parks rather than publishing the pass's commit or
# launching another unasked. Additive: an issue without it has no launch out.
_LAUNCHED_DOCS_SHA = "docs_launched_sha"

# The head a docs pass produced and the size gate held before it reached the
# pull request. Written inside the gate's own routed write, ahead of the
# relabel to `workflow:decomposing`, because a hold is the end of this stage's
# tick: the pass is finished and paid for, and the settlement that publishes
# the accepted commit hands the label back to a stage whose ordinary reading
# of a branch in sync with its remote is "no docs pass has run".
_SETTLED_DOCS_SHA = "docs_settled_sha"

# The head the pull request stood on when that pass was entered, which its push
# is leased against: written beside the receipt in the gate's same write, and
# spent with it by the completion. The code-publication receipt names that head
# too, but only until the next publication rewrites it -- a recovery that
# republishes the docs commit over itself leaves it naming the docs commit --
# and the completion records this one as the head the pass was entered on,
# which the ready ping proves the approved commit links to. The two are one
# group: a docs receipt with no readable lease beside it is a record something
# edited, which the completion holds over rather than reading a head off
# anything else.
_SETTLED_DOCS_LEASE = "docs_settled_lease"

# The verdict a finished pass stamps beside `docs_checked_sha`: `no_change` for
# a pass that published nothing, `updated` for one that published a docs
# commit. Dropped as each pass begins and by every later approval, so one on
# the record is always the verdict of the pass that finished last for the
# approval it stands beside.
_DOCS_VERDICT = "docs_verdict"
