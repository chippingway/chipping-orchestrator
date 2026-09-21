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
outcome earns, the ACK fast path, and the `validating` relabel a pushed fix
earns.

A fix prompt teaches the report contract like every other developer prompt, so
a round can end on `REPORT: READY` -- and then it owes a publication this tick
cannot guarantee. `reporting` is that road: the consumed pairs and the route
bookkeeping ride the RECORD of the report rather than the comment, and the write
that completes the publication is what applies them, so feedback recorded as
answered for a report no reviewer has is a state this stage never reaches. It
also owns the mark that settlement raises, since the one thing such a write
cannot do is move a label. `report_recovery` is the other end of the same
contract, ahead of every scan: a report a crash left unbound, re-proved against
the checkout rather than remembered off a receipt, and a round whose report
settled somewhere this stage was not looking.

While a report is owed, nothing an outstanding publication carries may be spent
before it lands -- not the bookmarks, not the round, not the readers -- so the
readers stop being able to say what has been delivered. The record's own frozen
pairs are what `feedback` asks instead, which is why the handler's
nothing-to-act-on exit and the parked dispatch both read them.

Callers import the owner they need, so this initializer binds nothing: the
dispatcher resolves one handler per issue, and an eager binding here would
charge every importer of one stage for the worktree, GitHub, and dev-resume
machinery only the resume path reaches.
"""
