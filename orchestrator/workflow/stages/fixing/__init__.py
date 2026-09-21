# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The dev fix-loop that two different routes hand the same PR to.

`in_review` flips here when a human answers an open PR, and `validating` flips
here when its own reviewer requests changes. Almost every decision below turns
on which route it was, and the discriminator is `pending_fix_at`: the in_review
route records it beside the feedback bookmarks, the validating route never
does. It decides whether a pushed fix resets `review_round` or bumps it,
whether a no-commit `ACK:` may return the issue to `in_review`, and whether a
transient park is allowed to clear itself without a human ever commenting.

`handler` holds the order those questions are asked in. The preflight runs
first because a merged or closed PR outranks anything the loop would otherwise
compute, and the rescan behind it reads the in_review watermarks rather than
the `pending_fix_*` bookmarks -- the bookmarks stay untouched in pinned state
because the first resume advances those watermarks past the very feedback that
started the loop, and a later `/orchestrator continue` has nothing else left to
replay from.

That is why `feedback` and `bookmarks` are separate owners: one reads forward
from a watermark, the other reconstructs backward from recorded ids, and only
`continue_command` needs the second. Both keep their four surfaces apart, and
the reconstruction has to because a replay is DELIVERED: what an accepted
`/orchestrator continue` settles is the batch it replayed joined with the
fresh rescan, so the issue-thread half of a preserved batch moves the
issue-action boundary and its PR-conversation half never does. `feedback` also
owns the settlement, because what a consumed batch is allowed to hide is the
same decision as what an unread scan is allowed to see -- and it is a
settlement rather than one watermark bump because a fix prompt quotes four
surfaces and each answers to a different reader. The issue thread answers to
the issue-action boundary `last_action_comment_id` as well as the PR-side
cursor, since the implementing and validating resumes deliver from that surface
too; the pull request's three surfaces answer to the in_review watermarks and
to nothing else. `parked` is the dispatcher for a tick that arrived
`awaiting_human`, and `drift` is the exit it takes when the validating-route
recovery cannot clear a transient park but the worktree has fallen behind base:
the per-tick base sync stands down on every park, so nobody else will rebase it.

`resume` is the run and everything a finished run leaves behind -- the quiet
window it waits out, the three refusals that count no delivery at all (a launch
nothing invoked, a shutdown kill, a live pause), the settlement every other
outcome earns, the ACK fast path, and the `validating` relabel a pushed fix or
a delivered report earns.

A fix prompt teaches the report contract like every other developer prompt, so
a round can end on `REPORT: READY` -- and then it owes a publication this tick
cannot guarantee. Such a round settles nothing at the fork in `resume`: feedback
recorded as answered for a report no reviewer has is the reading that fork
refuses. What carries the batch on the one road where the report IS the handover
is the report's own record, so the readers move in the write that settles it.
Every other road answered the feedback in something already there -- a pushed
fix in code the pull request now carries, a park in a notice a human is being
asked to read -- and settles it in the tick, a park inside its own write rather
than a caller's behind it, since a park left over feedback that still reads as
unanswered is one the next tick resumes the developer over again.

A round that merely REACHED for that contract and missed -- a report block with
an `ACK:` line beside it -- is not an acknowledgement either, and the ACK fast
path refuses it: read as one it would hand the pull request back to `in_review`
over work whose report nothing carries.

`reporting` is the settlement-driven form of the same road, and no dispatched
tick runs through it: the consumed pairs and the route bookkeeping ride the
RECORD of the report rather than a caller's own write, the write that completes
the publication applies them, and a mark rides with them for the one thing that
write cannot do -- move a label. `round_marks` is the reading that mark is
placed by before any relabel is taken on it, kept apart from the owner that
takes the relabel so that every road reaching one asks the same question rather
than a copy of it.

What a round owes its pull request in words rather than code is
`validating/fix_reports`', which both this stage's resume and the
`CHANGES_REQUESTED` run that precedes it dispose through: the report is
recorded before the size gate, a report needing no commit is published onto the
head the pull request already carries, and the reviewer behind the relabel is
held until it is confirmed.

Callers import the owner they need, so this initializer binds nothing: the
dispatcher resolves one handler per issue, and an eager binding here would
charge every importer of one stage for the worktree, GitHub, and dev-resume
machinery only the resume path reaches.
"""
