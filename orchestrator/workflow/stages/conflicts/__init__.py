# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The rebase that drives an unmergeable PR back to mergeable.

Three routes hand a branch here -- an operator relabel, the refresh-time rebase
that ended in real conflicts, and the `fixing` dead-lock breaker whose parked
worktree fell behind base -- and all three want the same thing: the PR branch
sitting on top of the current base with its commits intact. Every pushed exit
hands back to `validating` rather than to `documenting`, because rebasing
rewrites SHAs and the reviewer has to re-approve the branch it produced; the
single docs pass stays deferred to the post-approval handoff.

The owners divide by what one tick has to establish before the rebase may run
and by what it does with the result. `handler` holds the order those questions
are asked in, `routing` the two that gate the rebase itself -- the
awaiting-human resume and the `MAX_CONFLICT_ROUNDS` cap -- plus the worktree
preparation behind them. `guards` and `divergence` are the pair that decides
whether the local branch may be published at all: a worktree behind its remote
PR head is refused, and the one exception (already rebased onto base, ahead of
a head the orchestrator itself recorded) is what `guards` proves and
`divergence` leases the force-push against. `rebase` runs the rebase and emits
the `merge_attempt` that records it; `publication` disposes of a clean one and
hands real content conflicts to the dev; `resume` owns the three dev-resume
entry points and `outcomes` what a finished run left behind, while
`resume_reports` carries the report a body edit's resume returns -- and the
reply to a park that left one owed -- into the developer-report transaction,
through the drift disposition the review stages share, with `resume_records`
writing down the publication that report goes out with. `evidence` is what
a clean rebase tells the size gate about the commit it replaced, so an
adjudicated change is recognized in the object the replay produced rather than
adjudicated a second time. Only that one publication reaches it: every other
push here carries a commit somebody else made -- an agent's resolution, a
rerouted fix, whatever an earlier tick left for the recovery -- and nothing
readable off the branch tells those from a replay. What it does answer for a
body edit's resume is the divergence a developer's own rebase leaves, off that
resume's record, so the force-push may go ahead -- never an exemption.

`transitions` is separate because every exit that changes the issue's state
shares one shape. A park is `_park_awaiting_human` plus the pinned-state write
that must accompany it, and a pushed round is a `review_round` reset, a
`conflict_round` bump, an audit event, a write, and a relabel -- so many exits
publish those that keeping them on one owner is what stops the pairs drifting
apart. `handoff` is the last two: the count goes down ahead of the move it pays
for, so a move a crash cut short is made by the next tick rather than counted
again. `report_debt` is what that tail owes `validating` when the round
rewrote the head -- a clean rebase, a resolution, a recovered push -- read off
the code-publication receipt the push left and written ahead of the relabel,
since the head it hands on is one no developer report is about. `state` holds
the two counter keys the writers and readers share.

Callers import the owner they need, so this initializer binds nothing: the
dispatcher resolves one handler per issue, and an eager binding here would
charge every importer of one stage for the worktree, git, and dev-resume
machinery only the rebase paths reach.
"""
