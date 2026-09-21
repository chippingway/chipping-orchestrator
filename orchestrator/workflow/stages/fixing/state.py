# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The pinned-state keys the fixing owners key their decisions on.

Every one of these is written into the pinned JSON comment live issues already
carry, so renaming one is a migration of every open PR rather than a refactor.

They sit here rather than on whichever owner happens to write one first because
the writer is rarely the reader. `pending_fix_at` is the sharpest case: the
in_review route sets it and this stage never does, yet it is the discriminator
`parked` reads to decide whether a transient park may recover itself and
`resume` reads to decide whether a pushed fix resets `review_round` or bumps
it. `park_reason` is the same shape from the other direction -- the base-sync
retry loop writes reasons this stage must recognize and refuse to answer.
`fixing_round_settled` is the third, and the one key here whose spelling is the
engine's: a report transaction's settlement writes it from inside the engine --
raised by the route bookkeeping a fixing record froze, retired by every
settlement that froze none -- and this stage is the only thing that reads it or
clears it by hand.
"""
from __future__ import annotations

from orchestrator.workflow.engine import report_records as _report_records

_AWAITING_HUMAN = "awaiting_human"

_PENDING_FIX_AT = "pending_fix_at"

_PARK_REASON = "park_reason"

_REVIEW_ROUND = "review_round"

_CONFLICT_ROUND = "conflict_round"

# The mark a fixing report transaction's own settlement leaves behind, and the
# whole of the evidence the tick behind it acts on. That settlement applies this
# route's bookkeeping and cannot move a label, so the round is over with the
# issue still sitting on `workflow:fixing` -- and nothing else on the comment
# says so: the settled report and the publication receipt beside it are
# PERSISTENT, so a head a pull request is standing on for reasons of its own
# would let a manual relabel skip the feedback it was moved here to answer.
# Written by the settlement, read once, and cleared by the relabel that closes
# the round, so a later fixing round can never be finished by an older one --
# and REPLACED by every settlement, so the mark standing on a comment is always
# about the handoff standing beside it rather than about some earlier one.
_SETTLED_ROUND = _report_records.SETTLED_ROUND
