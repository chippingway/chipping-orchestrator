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
clears it by hand. `fixing_round_handed_back` is the fourth and is this stage's
own: the receipt of the transaction a hand-back already closed a round on, which
is what makes that mark a claim on ONE transaction rather than on any settlement
whose handoff happens to still be lying there.
"""
from __future__ import annotations

from orchestrator.workflow.engine import report_records as _report_records

_AWAITING_HUMAN = "awaiting_human"

_PENDING_FIX_AT = "pending_fix_at"

_PARK_REASON = "park_reason"

_REVIEW_ROUND = "review_round"

_CONFLICT_ROUND = "conflict_round"

# What the no-feedback bounce files its own refusal under: not a fix that
# failed but a branch nothing could place against its pull request, so the
# relabel that would hand a reviewer that head is held. Durable, because it is
# the only thing that tells a later tick whose park it is standing over, and
# the one park on this stage waiting on a READING rather than on a person:
# `parked.py` reads it to send a quiet poll back to that bounce with the flags
# untouched, so the reading is taken again and the hand-back retires the park
# in the write that relabels. It is none of the validating transient reasons
# all the same -- those name a session or a reviewer run and dispatch to a
# recovery that would publish against a record this park has none of. A reply
# still resumes the developer, whose disposition publishes whatever the
# checkout turns out to be carrying.
_REASON_UNPROVED_BRANCH = "stranded_unproved"

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

# The handoff a hand-back has already closed a round on. The mark above comes
# down in that same write, but the handoff beside it is PERSISTENT -- nothing
# clears one, a settlement only replaces it -- so a mark reintroduced by hand
# afterwards would correlate against a transaction this stage already finished
# and hand the round back a second time, past whatever feedback arrived in
# between. Written by the hand-back, durable before the label moves like the
# mark it replaces, and read only by the correlation that places a mark.
_HANDED_BACK_RECEIPT = "fixing_round_handed_back"
