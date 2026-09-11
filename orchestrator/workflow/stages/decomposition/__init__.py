# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""How one issue becomes a manifest, and what that manifest becomes.

Four workflow labels share this package because they share one artifact. The
decomposer runs on `decomposing` and answers with a single fenced manifest;
`single` sends the issue straight to `ready`, and `split` turns the manifest's
children into real GitHub issues and leaves the parent on `blocked` or
`umbrella` until every one of them resolves. The parent-side labels are the
back half of the same decision, so the manifest that produced the children and
the walk that waits on them belong in one package rather than one per label.

The owners divide by what each is responsible for rather than by label:
`manifest` and `validation` decide what the agent's reply is allowed to be,
`session` owns the decomposer session an issue is locked to and every spawn or
resume under it, `retry_cap` owns the park a spent spawn budget leaves an
INITIAL decomposition -- held ahead of every road that would walk past one, and
lifted only by the command that renews the budget -- `run` owns the order one
tick asks the others in and `outcomes` the three dispositions its reply earns,
`recovery` owns what a tick that died mid-split left behind, `split` owns the
crash-safe order children are created in, and `parents`, `activation`,
`blocked`, and `umbrella` own the parent-side polling that drives the tree to
completion.

The `late_*` owners are an additive second mode under the same `decomposing`
label, for the issue whose implementation is already committed and turns out to
be oversized. They are named apart rather than folded in because what a missing
or malformed INITIAL manifest means may not change: `late_prompt` and
`late_reply` are the question that mode asks and the fence it is answered on,
`late_hold` owns the cycle-marked hold a reusable pull request wears while the
question is open -- the plan one where the gate was entered before publication,
and the implementation one the work is already on where it was entered past it
-- `late_session` owns the run's pinned record and the tracked spawn over it,
`late_content` fingerprints the requirements the candidate was frozen against
and `late_content_replies` tells the fresh replies it counted apart -- what is
work for an agent, and what is one of the two operator controls that are a
decision about the candidate instead -- while `late_guidance` decides what a
change to those requirements or an answer about them earns, `late_revision`
owns the developer run guidance buys and the followup it is resumed with --
with `late_revision_obligations` holding the refusal a candidate the last
adjudication already acted on earns instead of a revision, and
`late_revision_reconciliation` the clean tree, re-frozen commit, and fresh
measurement what that run left is proved through -- `late_relabel` owns the
label a live generation pins against the kill switch and a hand relabel,
`late_owner` owns the fresh read that stands between a finished run and
anything it earns,
`late_unsplit` owns the park an adjudicator's own `single` hands the issue to a
human under and `late_authorize` the one command that ends it -- a trusted
whole-comment `/orchestrator authorize-oversized <commit>`, proved against the
frozen candidate, the recorded verdict, and a contribution fingerprinted again
before anything publishes -- `late_settlement` owns what a guarded verdict
becomes and the order an authorized
one is acted on in -- `late_reconcile` takes the hold off and settles which
pull request the issue records, `late_proof` decides whether the publication a
candidate was measured against is still standing somewhere the verdict may act
on, `late_verdict_push` makes the push only this tick still holds the evidence
for, and `late_handback` hands the label on and retires the cycle --
`late_retry_cap` owns the same spent-budget park on this mode's road -- the
gate its one spawn is charged to, and the hold that keeps a park nothing
supersedes ahead of the evidence probe, the pull-request hold, and the content
read -- `late_notice` owns the sentence any late park still owes the thread,
`late_park_state` the reasons, standing claim, watermark, and durable write,
`late_park_delivery` the release and reconciliation of that sentence, and
`late_parks` the decisions that take, stage, retire, or answer the park.
`late_coordinator` owns their order: `late_admission` recovers owed effects and
proves the frozen evidence before taking the hold, `late_attempt` records the
attempt with retry charges held back, `late_execution` runs and reads the agent,
and `late_completion` guards every completion before settling it. `late_verdict`
interprets one finished reply, `late_outcome` records every completion, and
`late_models` carries what they hand each other. The budget both
`retry_cap` owners are decided by is neither of theirs: it is the shared
`engine/retry_budget.py`, so a park taken on either road is the same durable
reason, answered by the same command, and audited on the same stream.
`late_split_preparation` proves the snapshot and creates durable children through
`late_snapshot` and `late_children`. `late_transaction` orders their announcement,
the supersession, and the guarded handoff to `late_retirement`, which retires
the generation, activates its children, and attempts branch reclamation.
`late_cleanup` owns what that leaves the remote holding, `late_cancellation` owns the irreversible ending an
owner observed closed earns, `late_sweep` is the cleanup-only pass that
revisits an owner a human closed mid-cycle, and `late_restart` owns the fresh
cycle an operator authorizes by taking that ending's `rejected` back off. What
puts an issue in front of them is the size gate at the implementing package's
publication seam, and what reaches them is the first question a `decomposing`
tick asks: a record carrying a live generation belongs to the coordinator
entire, and no step of the initial decomposition runs for it. Two answers short
of one are routed rather than adjudicated -- a settled candidate the
measurement put back under the ceiling goes to `workflow:implementing` for
publication, and `DECOMPOSE=off` may not route an unadjudicated one there at
all -- so the four labels above are still the whole of what this package
answers for. `handoff` owns both of those routes, together because neither is a
decomposition and both end the same way: the label moves and the implementing
handler runs on the same tick, against an issue read back after the write
rather than the stale object that write was made against.

Callers import the owner they need, so this initializer binds nothing: the
dispatcher resolves one handler per label, and an eager binding here would
charge the `blocked` walk for the manifest parser and the split writer it
never reaches.
"""
