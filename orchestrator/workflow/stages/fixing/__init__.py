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
`continue_command` needs the second. `feedback` also owns the settlement,
because what a consumed batch is allowed to hide is the same decision as what
an unread scan is allowed to see -- and it is a settlement rather than one
watermark bump because a fix prompt quotes four surfaces and each answers to a
different reader. The issue thread answers to the issue-action boundary
`last_action_comment_id` as well as the PR-side cursor, since the implementing
and validating resumes deliver from that surface too; the pull request's three
surfaces answer to the in_review watermarks and to nothing else. `parked` is
the dispatcher for a tick that arrived `awaiting_human`, and `drift` is the
exit it takes when the validating-route recovery cannot clear a transient park
but the worktree has fallen behind base: the per-tick base sync stands down on
every park, so nobody else will rebase it.

`resume` is the run and everything a finished run leaves behind -- the quiet
window it waits out, the three refusals that count no delivery at all (a launch
nothing invoked, a shutdown kill, a live pause), the settlement every other
outcome earns, the ACK fast path, and the `validating` relabel a pushed fix
earns.

Which WRITE carries that settlement is the fork `reporting` answers, and it
turns on whether the run finished on a report. A fix prompt teaches the report contract like every
other developer prompt, so a round can end on `REPORT: READY` -- and then it
owes a publication this tick cannot guarantee. Its consumed pairs and its
route bookkeeping are recorded ON the transaction the report goes out as and
settled by the write that completes it, whichever tick makes that: the one
that binds and posts here, or the reconciliation ahead of a later handler.
Until then the bookmarks stand, the readers stand, and the label stays put, so
no reviewer is sent to a head whose report nothing on the pull request carries.
A round whose whole answer IS the report publishes it against the head its pull
request already stands on -- the prompt asks for exactly that, an item wanting
report content only answered with no commit for it -- and a push that did not
land settles its consumption on the spot instead, since nothing bound the
record and nothing goes back for a delivery. Every other outcome -- the
ordinary `ACK:`, the question, the timeout -- writes no report and closes its
own bookkeeping directly, ahead of the disposition. A reply that reached for
the contract and missed is none of these: it is held for a human ahead of
every road, because its two halves say opposite things -- an `ACK:` returns
the pull request to review as needing no change, and a commit beside it would
be pushed and relabelled with no report on the pull request at all.

What publishes a report-only round is a set of POSITIVE readings, never an
absence: the checkout named a head, that head is where the run began, and it
is what the pull request is standing on. A head nobody could read and a
divergence nothing could count both answer empty, and either taken for "in
sync" would describe work the remote does not have.

And a report the tick that recorded it never bound is answered by
`report_recovery` at the top of the next one, ahead of the scan: the input that
run consumed rides the same record, so leaving it there is what pays a second
developer to answer the same feedback and replaces the first report with the
second. Whether the code went out is re-proved against the checkout rather than
remembered off a receipt, which is persistent and on a tick that pushed nothing
names an older round; and a binding that takes the delivery ends the tick,
finishing the recovered route back to `validating` where the publication
settled and relabelling nothing where it is still owed.

Callers import the owner they need, so this initializer binds nothing: the
dispatcher resolves one handler per issue, and an eager binding here would
charge every importer of one stage for the worktree, GitHub, and dev-resume
machinery only the resume path reaches.
"""
