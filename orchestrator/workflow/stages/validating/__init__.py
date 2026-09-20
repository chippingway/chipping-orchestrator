# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The review loop between a pushed implementation and the final-docs hop.

The owners here divide by what a `validating` tick is answering, because the
reviewer is only one of the things this stage runs. `handler` holds the order
those questions are asked in -- the terminals a landed or rejected PR ends the
tick on, a body edit, a park a human replied to, and only then a reviewer
round -- and it is the order that carries the safety: each check ahead of the
spawn is one the reviewer's own output would make unanswerable.

One verdict fans out three ways. `approval` owns the approved arc, and the
local verify gate at the head of it is the last thing standing between a
branch that does not build and `in_review`; the optional squash, the notice
its count is worded from, the end of the collapse record, and the relabel to
`documenting` follow it, in that order. `verify` holds the other side of that
gate -- how a non-ok result reads and the park it earns. `handoff` owns what
that arc leaves on the pull request for its own sake: the approval comment,
and the watermark seed `approval` runs behind its notice so neither the docs
hop nor in_review replays the orchestrator's own comments as human feedback.
`watermarks` holds the seed walk `handoff` hands the PR to, which stops at the
first comment the dev has not consumed rather than at the first one the
orchestrator did not write. `requested_changes` owns the remaining two
verdicts: the feedback posted on the PR and the dev fix run under the `fixing`
label, plus the park a reviewer that emitted no VERDICT line earns.

Between rounds the stage is a dev-fix driver, and `dev_fix` owns what one
finished dev run leaves behind -- the no-commit reading, the push, and the
`review_round` bump a landed fix earns so the reviewer re-reads the new head.
Three entry points feed it: `awaiting` and `awaiting_resume` for a park a
human replied to, `drift` and `drift_outcomes` for a body edit mid-review, and
`recovery` for the parks that can clear without a human at all. `stranded`
holds the probe under that no-commit reading -- the one that keeps a
committed-but-unpublished fix from ping-ponging between parks -- because the
`fixing` handler asks it off no dev run at all, on the ACK fast path it has to
stand down on and on the no-feedback bounce that is the last tick left to
publish such a commit.

A body-edit resume also owes the pull request its developer report.
`drift_reports` records it before the size gate under the requirements
revision the resume was handed, `report_settlement` binds it to the
publication the code reached and settles it, and `report_hold` holds the
reviewer, on every tick, until the pull request carries it -- which is why
`handler` asks that hold last, ahead of the spawn.

`models` and `state` carry the records and the wire keys the rest share.
Callers import the owner they need, so this initializer binds nothing: the
dispatcher resolves one handler per issue, and an eager binding here would
charge every importer of one stage for the reviewer spawn, the verify runner,
and the watermark walk it never reaches.
"""
