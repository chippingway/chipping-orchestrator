# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The final-docs hop between a reviewer approval and `in_review`.

The owners here divide by what one `documenting` tick has to settle before it
may spawn, because every one of those questions becomes unanswerable once the
agent has run. `handler` holds the order they are asked in. `preconditions`
owns the ones that end the tick outright -- a PR merged or an issue closed out
of band, a label applied with no `pr_number` to anchor on, and a content-free
`/orchestrator continue` on a park that needs real words. `drift` owns the one
that unwinds instead: a body edit invalidates the approval the docs pass is
running against, so the issue goes back to `validating` -- with `drift_reset`
beside it for the git half, which fails closed on every step because a docs
commit left on disk against the old body is what the next tick's
recovered-commit shortcut would push unreviewed.

What the pass itself is worth is three more. `run` refreshes the branch,
refuses a diverged worktree, and picks between the awaiting-human resume, the
recovered-commit shortcut, and a fresh docs spawn. `outcomes` reads what the
run left behind -- timeout, dirty tree, new commit, or a bare
`DOCS: NO_CHANGE` -- and `publication` turns the surviving two into a push,
a PR notice, and the stamped `docs_verdict`, entered on the commit `subject`
hands it once that commit's subject names the pull request. `handoff` is separate from both
because it protects a stage this one does not run: the `pr_last_comment_id`
ratchet is what stops in_review from replaying a human reply the docs pass
already consumed as fresh PR feedback.

`parks` collects the four ways the tick stops for a human, over the records
the owners hand each other (`models`) and the pinned-state keys they share
(`state`).

Callers import the owner they need, so this initializer binds nothing: the
dispatcher resolves one handler per issue, and an eager binding here would
charge a park or a verdict parse for the drift unwind it never reaches.
"""
