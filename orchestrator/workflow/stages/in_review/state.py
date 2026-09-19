# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The wire key the in_review owners scan and ratchet on.

`pr_last_comment_id` bounds both IssueComment surfaces -- the issue thread and
the PR conversation share that id namespace -- but it does not answer for
either alone. The pull request answers to it and to nothing else, since no
other cursor has read that surface; the issue thread answers to it AND to
`last_action_comment_id`, the delivery cursor an implementing or validating
resume settles for exactly the replies it quoted. `surfaces` is where those
two questions are asked apart. It is written into the pinned JSON comment live
issues already carry -- the validating handoff seeds it, the legacy migration
backfills it, the fixing handler reads it back -- so renaming it is a
migration of every open PR rather than a refactor.

It sits here rather than on the owner that carries it because the owner that
writes it is rarely the one that reads it: the handoff and the migration seed,
`watermarks` carries it over what a tick wrote, `surfaces` reads it, and
`feedback` scans what those reads answer.

`in_review_handoff_pending` is the other, and it answers a different kind of
question: whether this issue owes `workflow:validating` a label move it has
not made yet. A requirements edit leaves the approval this label stands on
stale, so the round is reset and the label moved -- two operations a process
can die between. The marker goes down with the reset and comes off once the
label has moved, so a relabel nobody made is found and remade rather than
leaving an issue here to be pinged as ready on an approval that is over. It
is additive: an issue without it owes no move, which is every issue that
predates it.
"""
from __future__ import annotations

_PR_LAST_COMMENT_ID = "pr_last_comment_id"

_HANDOFF_PENDING = "in_review_handoff_pending"
