# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The stage where the orchestrator stops driving and a human merges.

Nothing here merges a PR, and nothing here routes a conflict: an unmergeable
branch parks for a human rather than detouring through `resolving_conflict`.
What the stage does own is the decision of whose turn it is, and the owners
divide by the four answers one tick can reach.

`handler` holds the order those questions are asked in, and the order is the
contract. `feedback` runs first because the four surfaces it scans overlap
with the drift hash: an issue-thread review comment moves `user_content_hash`
just as a body edit does, so asking `drift` first would resume the dev and
bounce to `validating` instead of bookmarking the batch and flipping to
`fixing`. `fixing_route` is what that flip writes -- bookmarks rather than
watermarks, because the fixing handler re-reads the same comments to build its
prompt. `drift` is the body edit nobody commented about, and both of its
outcomes hand back to `validating` with `review_round` reset, since the
approval it already earned was against the old requirements. `merge_gate` is
the last answer: a mergeable, approved, unvetoed head earns one HITL ping per
head SHA, and everything else waits.

`surfaces` is underneath all of that: it is where the one id space GitHub
numbers the issue thread and the PR conversation in is read as the two
surfaces it actually is, each against the cursors that have read it.
`watermarks` is the pair of writers over the same field -- the carry a park
owes its own notice, and the legacy seed a manually-relabeled issue needs --
and neither jumps to a tip, because both walk forward from where the mark is
and stop at the first comment they cannot vouch for. `models` and `state`
carry the per-tick handles and the wire keys.

Callers import the owner they need, so this initializer binds nothing: the
dispatcher resolves one handler per issue, and an eager binding here would
charge every importer of one stage for the worktree, GitHub, and dev-resume
machinery only the drift route reaches.
"""
