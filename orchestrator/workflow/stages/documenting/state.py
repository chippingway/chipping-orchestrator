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

# The head a docs pass was last read against, which `in_review`'s merge gate
# pings on with a `docs_verdict` beside it. Every shape re-anchors it on the
# head it is about, and a pass that publishes re-anchors it again on the commit
# it hands the size gate, so the record never names one commit while the fields
# beside it name another.
_CHECKED_DOCS_SHA = "docs_checked_sha"

# The head a docs pass produced and the size gate held before it reached the
# pull request. Written inside the gate's own routed write, ahead of the
# relabel to `workflow:decomposing`, because a hold is the end of this stage's
# tick: the pass is finished and paid for, and the settlement that publishes
# the accepted commit hands the label back to a stage whose ordinary reading
# of a branch in sync with its remote is "no docs pass has run".
_SETTLED_DOCS_SHA = "docs_settled_sha"
