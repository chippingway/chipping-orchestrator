# Workflow modules

This page maps `orchestrator/workflow/`: the state and transition owners, the `engine/` owners one tick is
composed of, the `late_split/` domain the late size gate is defined by, and the stage subpackages the label dispatch
routes into. It is split out of
[`../architecture.md#top-level-layout`](../architecture.md#top-level-layout), which keeps the top-level map and the
naming rules that hold for the tree as a whole. The packages this one decides with are in
[`platform-modules.md`](platform-modules.md).

Each entry below is the responsibility its module owns, and it answers there and on no second site. What a stage does
per label is in [`../state-machine.md`](../state-machine.md); what the agent it spawns is prompted with and allowed
to write is in [`../workflow.md`](../workflow.md).

## Enforced boundaries

Each rule below names the check that holds it. The last is a convention the tree keeps rather than one a test can
see, and is called out as such.

- **Callers name the state and tick owners directly.** `workflow/state.py` defines the label vocabulary,
  `label_reading.py` resolves its spellings, `transitions.py` declares the graph, and `transition_guard.py` guards
  writes. The per-repo entry point is `workflow.engine.tick.tick`. The package initializer binds no API and imports
  no owner. `github/` and `git/` can therefore import the state vocabulary without loading the
  engine or pointing back into their own initialization. `tests/workflow/test_imports.py` probes the import paths
  in a clean interpreter, and `tests/repository/test_layering.py` holds the direction under them.
- **The stage handlers are resolved at call time.** `engine/stage_targets.py` pairs each label with the module
  its handler lives on and imports it when it dispatches, as `engine/pickup.py` does for the stage it starts
  an issue on: the stage tree imports `engine/`, so a module-scope bind would point that edge back at itself.
  `tests/workflow/engine/test_dispatch.py` pins that the handler is read off its owner per call rather than
  bound at import, and `tests/workflow/stages/test_imports.py` that every labelled target lands on a stage
  package here. The late size gate's own refusal is resolved the same way and for the same reason — it lives
  on a stage owner, so the dispatcher imports it when it routes.
- **Two operator log channels, spelled literally.** The engine, `late_split/`, and stage owners report on
  `orchestrator.workflow`, and `workflow/transition_guard.py` on `orchestrator.state_machine`. A module moved
  between packages does not take its channel with it — `tests/workflow/test_imports.py` walks the package and
  checks every owner that declares a logger.
- **Nothing sits flat beside the package.** The retired spellings — `orchestrator.state_machine`,
  `orchestrator.workflow_drift`, `orchestrator.workflow_messages`, and the export and dependency manifests — resolve
  to nothing (`tests/workflow/test_imports.py`), and the repo-wide naming rule in
  `tests/repository/test_package_layout.py` keeps the `workflow_` family from returning one level down.
- **A borrowed helper keeps its owner (convention).** Stage-private helpers stay in the stage that owns them, and
  what more than one stage reaches for stays where it is defined with the borrower naming that owner — fixing's quiet
  window imports `_comment_created_at` from `in_review/watermarks.py`. No check enforces this one; what keeps it is
  that a second copy of a shared helper would drift from the owner and from the tests aimed at it.

## The map

`engine/`, `late_split/`, and every stage package publish nothing, so naming one costs no owner behind it. Each
stage package is listed with the labels its handlers answer for: eight own one label each, and `decomposition/` owns
four — `run.py` for `workflow:decomposing`, `blocked.py` for both `workflow:ready` and `workflow:blocked`, and
`umbrella.py` for `workflow:umbrella`. That is twelve of the dispatch table's thirteen targets; the thirteenth is the
unlabeled entry, which `engine/pickup.py` answers rather than a stage package.

```
workflow/                   marker package for state, engine, and stage owners
  state.py                  the exact `WorkflowLabel` / `ControlLabel` strings and the `workflow:` namespace boundary;
                            stage tags and legacy spellings retain the vocabulary used by live issues and event sinks
  label_reading.py           canonical and legacy label lookup, canonical-first issue state, strict coercion, and the
                            exact set of labels a workflow write replaces without removing unrelated bare labels
  transitions.py            the forward spine and declared interrupt sources, including cancelled `done` to `rejected`;
                            publication and base-refresh eligibility read the same stage sets used by those edges
  transition_guard.py       the same-label allowance and off/warn/enforce write guard, with strict rejection details and
                            the literal `orchestrator.state_machine` channel operators filter on
  engine/                   what every stage is driven by
    agent_diagnostics.py    what a park comment and a WARNING say about a run that left no usable message: the
                            agent's stderr under two budgets -- 1KB for the human who came to the issue, 400
                            characters so a log line still fits a screen -- and the exit code beside the first.
                            The shared redactor runs over the RAW stderr before either trim, since a secret sliced
                            by the cut survives as a fragment the redactor no longer matches, and that fragment is
                            what leaks; the same ordering puts it ahead of the `rstrip`, so a multi-line env value
                            ending in a newline still matches verbatim. The block is quoted through
                            `messages.py`'s blockquote, so it reads as the last-message body it is appended under
    comments.py             the orchestrator marker and bounded id ledger shared by issue and pull-request comment
                            posts; callers persist the ledger, and shared token accounts are never treated as
                            exclusively automated
    prompt_context.py       trusted-author thread reads, retained orchestrator comment ids, quoted comment lines, and
                            bounded tracked-repository awareness for agent prompts; marker text alone cannot admit a
                            comment
    community.py            the open pull requests this orchestrator never opened, which is why the tick sweeps
                            them itself: one opened by somebody else carries no pinned state for a handler to
                            consult, so nothing dispatches it. `ALLOWED_ISSUE_AUTHORS` decides there is anything
                            to sweep at all -- empty, the sweep returns before it costs a request -- and every
                            open PR from outside it earns one `workflow:community_contribution` label and one
                            HITL ping, with the ping posted BEFORE the label that dedups it, since a label
                            written ahead of a comment that failed would suppress that ping forever. Both
                            spellings of the label are read, so a PR the bootstrap rename could not reach is
                            recognized rather than pinged twice; a Bot author is skipped outright, its PR being
                            structural rather than a contribution. The enumeration and each per-PR step are
                            caught separately, so one PR's failure costs that PR's ping and never the sweep or
                            the tick around it
    completion_verdicts.py  the two markers a terminal agent closes its own stage with -- the reviewer's
                            `VERDICT:` line and the documentation run's `DOCS: NO_CHANGE` -- read out of its last
                            message, with the LAST match winning and anything short of the marker answered `unknown`,
                            so the caller parks a human in rather than recording a decision nobody made. The review
                            marker counts inline, a verdict naming its own outcome; the documentation one counts only
                            as the FINAL line, alone and unpunctuated, because "nothing to write" is a claim the next
                            sentence can take back. That stage's other outcome -- docs WERE updated -- is a commit on
                            the branch and is read there instead. Each parser returns the slice above its marker, the
                            part a human is shown
    stage_targets.py        exact label-to-handler and cleanup targets, with stage imports deferred to the call;
                            the unlabeled target reaches pickup through the same resolver
    poll_models.py          poll-time closure evidence and family/fanout/cleanup partitions, preserving deferred issues
                            absent from enumeration and the blocked/umbrella family capacity exemption
    run_limit_dispatch.py   hold exhausted work, replay its owed notice, and admit grants or terminal cleanup;
                            an implementing plan PR does not prove that implementation work ended
    dispatch_guards.py      pinned-state admission, restart before cancellation, publication reconciliation, and
                            operator controls; an already-pinned unlabeled issue is left where its labels put it
    poll_reading.py         classify labels and hard-skip controls while admitting observed-close cleanup;
                            a failed label read reaches per-issue exception isolation through the family bucket
    dispatch_closure.py     persist poll and refetch closes, retain them across ordinary processing, and preserve
                            receipts and deferred cleanup when a worker submission is refused
    cleanup_observation.py keep a close through cleanup exceptions and unsettled endings, including an ending owed
                            under a label no sweep queries; settle only after the defining stage proves it complete
    dispatch_partition.py  combine fresh poll results and still-owed closes, record closed fanout receipts before
                            submission, and include deferred issues that enumeration did not yield
    issue_processing.py    apply controls, select cleanup or guarded stage dispatch, hold publication through the
                            handler, and record timed evaluation analytics on success and failure
    dispatch_workers.py    refetch through each worker's GitHub client and optional semaphore, preserving ordinary
                            and cleanup observation scopes across sequential, scheduler, and pool execution
    scheduled_dispatch.py  drain the family bucket under active tracking, enforce capacity rules, and submit fanout
                            with claims released after execution or refusal; observed closes remain cap-exempt
    dispatch.py            drive the sequential poll's closure classification or submit its partition to the scheduler;
                            refetched owners and still-owed closes keep the processing scope their reading earned
    observation_state.py    the process-local close, receipt, scan, retirement, publication, and deferred-settlement
                            registries behind one lock; settlement advances the owner generation and clears its latch
                            and receipt memo atomically
    observations.py         latch, read, enumerate, and settle observed closes; settlement is deferred while a
                            publication holds the owner, so a record read cannot erase a close a running worker still
                            owes
    observation_receipts.py generation-scoped exclusive receipt-post claims and landed memos; bounded thread scans
                            release on failure and reopen when a receipt lands, so a failed or stale attempt suppresses
                            no later receipt
    retiring_cycles.py      the held cycle id across a retirement write and its final barrier; exit removes the marker
                            and reports the close observed inside the window under the same lock
    publication_holds.py    counted holds taken when a worker is admitted and nested around handler execution; only the
                            final release settles a deferred close, preserving the reading through queueing and refetch
    content_hash.py         the user-content hash and filters for pinned records, orchestrator output, bots, untrusted
                            authors, and whole-comment operator commands; the legacy bare-continue mode recognizes an
                            existing baseline
    drift.py                baseline persistence and legacy normalization, the dev resume a requirements edit earns, and
                            the pre-implementation decomposition reset; consumed watermarks cover the guidance delivered
                            to the agent
    guards.py               what a finished agent run may leave behind: the never-invoked, shutdown-interruption,
                            and freshly-read pause refusals, and the awaiting-human park. The first is asked ahead
                            of the second wherever a stage reads the worktree before it asks whether the run
                            happened -- what a killed run left there is the operator's to see, and what a launch
                            that never started left is nothing. The park marks the thread read to the id of the
                            notice it POSTED rather than to whatever the thread ends on afterwards: the two differ
                            only for a human replying between the post and that write, and on a park waiting for a
                            reply, reading the tip there consumes the answer with the question. A post whose id
                            nothing could read falls back to the tip, since a watermark that never moved leaves the
                            park's own notice to be read back as somebody's guidance on every later tick
    messages.py             the `ACK:` acknowledgement read out of an agent's last message, the one blockquote
                            form every agent output an issue carries is quoted in, and the two commands a HUMAN writes:
                            `/orchestrator continue` with the refusal a park needing real guidance owes it, and the
                            SYNTAX alone of `/orchestrator authorize-oversized <commit>` -- read from the whole
                            comment and nowhere else, with the argument captured as written, since a malformed one
                            is a command the workflow owes an answer to. What that second command MEANS is the
                            late-split stage owners', which is where the pair it names exists -- one per park it can
                            end, the adjudication's and the size gate's, each proving it against its own record
    pickup.py               an unlabeled issue's first tick: the author allowlist, the `DECOMPOSE` route, and the
                            greeting / hash / label / state order a start publishes in
    prompt_notes.py         shared empty-context placeholders, foreground execution and commit instructions, and the
                            continuation note for a session-limit retry
    prompts.py              implementation, review, documentation, fixing, conflict-resolution, and fresh-session prompt
                            builders; each response marker agrees with the parser that settles its stage
    conversation_prompts.py question, discussion, and PR-feedback follow-up prompts; discussion publication instructions
                            describe the confirmed plan artifact and the commit its stage verifies
    decomposition_prompts.py the decomposition prompt with the validator-owned child limit, and the bounded
                            single-decision comment that carries manifest notes into implementation
    retry_values.py         daily-retry decisions, notice phases, pinned keys, and the bounded continuation and
                            rolling-window constants
    retry_ledger.py         daily slot consumption, window expiry, and the remaining granted attempt; a standing
                            retry-cap park refuses even when time or configuration would otherwise reopen the budget
    retry_park_state.py     the durable retry-cap park, its recorded stage, and the exact notice still owed to the
                            thread; settling the sentence grants no launch
    retry_notices.py        bot-authored notice reconciliation, delivery, watermark advancement, and audit phases; an
                            unreadable thread keeps the notice owed and says nothing
    retry_budget.py         the shared charge-or-park form, persist-before-post ordering, stage-entry notice replay, and
                            the one bounded continuation; late adjudication uses the same ledger and owns its
                            generation-specific park
    run_budget_models.py    the four durable budget-event phases, refusal vocabulary, and the logical launch identity
                            used to correlate a charge
    run_budget_fields.py    the complete ledger payload, explicit unlimited remainder, reservation id combining a
                            bounded fingerprint and used count, and guarded stage lookup for a durable extension
    run_budget.py           budget events emitted only after the transition is durable; audit and analytics writes are
                            guarded independently so either may fail without costing the other or the tick
    run_charge_state.py     the issue and caller-state context of a launch charge, fresh pinned reads, guarded durable
                            writes, and a merge of only the fields that charge changed; an unreadable or failed record
                            refuses invocation
    run_circuit.py          the ordered reserved and started writes before the sole process invocation; only the logical
                            launch holding a reservation reuses it, each durable step emits its budget event, and
                            exhaustion parks on the same reading
    run_grant.py            the one command that answers the spent-ledger park below: a trusted `/orchestrator
                            add-agent-runs N`, read only while that park stands and only as the request the parser
                            beside it hands over. It persists an allowance of exactly `used + N` -- absolute rather
                            than additive, so the same command read twice buys the same ceiling -- clears that park
                            alone, consumes the batch it read and the answer it wrote under it (never a comment that
                            arrived between the two: the boundary is built from ids this tick observed rather than
                            re-read off the thread), and lets the tick reach the stage its label names. Every other
                            request leaves both counts where they were and earns one receipt; an untrusted one earns
                            nothing at all. Both answers are marked with the comment that asked, so a post whose write
                            never landed is recognized rather than said twice. Only the ending that moves the ceiling
                            reaches the shared budget stream, and only once the write that moves it has landed
    run_grant_request.py    what a `/orchestrator add-agent-runs N` comment has to say before the owner above acts on
                            it: the command as a whole line of its own, the exact positive count no larger than
                            `MAX_RUNS_PER_COMMAND` its argument has to be -- leading zeros dropped before the length
                            is measured, so `007` is seven and a digit string too long to be inside the bound is
                            turned away before `int()` can raise on it -- the last such line in a batch as the
                            request, and the record carrying it, the comment that asked, and the batch a tick may
                            claim to have read. It reads words and decides what they buy; no ledger, park, or thread
                            is touched here. The bare-command reading the drift hash filters on lives beside them,
                            since the tick that answers the command is the tick the stage below runs on and a hash
                            counting it would call a body nobody edited changed requirements
    run_ledger_models.py    immutable allowance, used-count, and reservation snapshots; the reserved/started vocabulary
                            and predicates for unlimited, spent, and reusable launch charges
    run_ledger_values.py    the pinned ledger field names and validated readings; an absent allowance defers to
                            configuration, the used count is floored by the legacy meter, and malformed values supply no
                            reservation evidence
    run_ledger.py           ledger snapshots and the reserve/start/settle mutations; used counts remain monotonic,
                            settlement clears only reservation fields, and PROJECTED_KEYS retains the allowance and
                            count across state projection
    run_limit_values.py     the lifetime-limit notice record, the allowance and spent count it explains, the audit
                            phases, and the pinned park fields
    run_limit_state.py      the standing lifetime-limit park and its owed sentence; changed ledger coordinates replace
                            the notice, and settlement clears the sentence without lifting the park or changing the
                            charge
    run_limit.py            persist a supplied exhaustion reading before its budget event and notice, reconcile
                            bot-authored delivery, and replay the sentence still owed; this owner grants and spends no
                            additional run
    terminal_reading.py    one guarded linked-PR reading for both endings, retaining failed reads and deferring a
                            merged publication to its merge path when recovering a human-closed issue
    terminal_context.py    the issue, publication, pinned state, and stage one ending is attributed to, with its
                            recorded PR number and conflict-round semantics
    terminal_effects.py    terminal stamps, labels, usage verdicts, pinned writes, events, issue closure, and branch
                            cleanup in their defined order; an open PR on a human-closed issue stays available
    terminals.py           select merged, rejected, and human-closed endings from their fresh readings; failed reads
                            leave the decision for a later tick, and the merged-PR path precedes closed-issue rejection
    tick.py                 one repo's polling pass and the order it drives: the base refresh, the
                            community-contribution sweep above, the skill-catalog emission, and the scheduler
                            handoff or in-tick execution behind them -- with the sequential mode of that execution
                            here, since streaming the enumeration rather than materializing it is what keeps a
                            partial one from losing what it already yielded
    parallel.py             the other in-tick mode: the bounded pool a `parallel_limit` above 1 runs the pass
                            across, the submission plan the executor is sized from -- which is why this half
                            materializes the enumeration the sequential one streams -- the family bucket folded
                            into exactly ONE task so it costs one worker slot however many family-aware issues
                            are pending, and the completion drain that reports each failure as it lands. Reached
                            only from the tick above, and every collaborator under it is named on the owner that
                            defines it
    run_requests.py         agent invocation requests, stable logical-round fingerprints, launch identities, and
                            optional runner arguments; prompt text is excluded so rebuilding a prompt cannot buy a
                            second charge
    run_reporting.py        agent-exit audit and analytics records, configured-model fallback, and triggered-skill
                            emissions; a failure to emit those skill records cannot discard a completed agent result
    issue_usage.py          historical per-issue usage counters and their terminal receipt; unknown and estimated costs
                            remain distinct from known prices and from the separate launch allowance
    usage.py                the tracked agent invocation: charge the required issue budget, emit spawn, call the runner,
                            record its exit and skills, and return the result for the stage to settle
  late_split/               the late size gate's own domain: what one generation IS, apart from anything that drives
                            one
    formats.py              what any late value has to look like -- a real integer, a git object id, a bounded
                            single-line value, where one line is asked as the split every reader on the far side
                            breaks on rather than as a search for one character -- the reducer that shapes a raw
                            diagnostic into what that last predicate accepts, so the one free-text field a record
                            carries is bounded by the rule that guards it, and the one refusal every owner raises
                            over any of them
    phases.py               durable phase vocabulary and the in-flight, settled-split, and pre-transaction boundaries
    models.py               verdict and failure vocabularies, and the frozen generation's measurement, bounded
                            lineage, ordered child register, and lifecycle; immutable updates preserve cancellation
                            provenance and prevent rewinding an in-flight transaction
    obligations.py          resource kinds, states, and entries, with frozen resource and consumer ledgers; keyed
                            updates are idempotent, and opaque ledgers refuse updates that a write would discard
    publication.py          frozen publication context with validated entry and a fail-closed completeness predicate;
                            the marker, source stage, pull request number, and head are one reconciliation claim
    identity.py             the monotonic cycle and generation identities, the child depth the bound still allows,
                            the two local content fingerprints a scope edit and a trusted answer are told apart by,
                            and the bounded name-free print one ledger entry is reported under
    payloads.py             what one hand-edited or older pinned late field reads back as: one reader per field
                            contract -- identity, count, depth, object id, literal flag, member, free text
    ledgers.py              what the two external ledgers read back as, the exact entry shape one of ours has, the
                            verbatim copy anything else is preserved through, and the all-or-nothing reading of the
                            ordered child register, whose entries are positional and so may not be skipped past
    keys.py                 the `late_*` pinned keys one GENERATION owns -- the frozen evidence, the misses a
                            reading of it lost and the step a notice about it named, the publication provenance,
                            the ledgers, the hold's route bookkeeping, and the cancellation and
                            pending-owner-check markers -- spelled once, as the tuple a clear is defined as
                            dropping exactly
    encoding.py             what each of those fields is spelled as on the way out: the wire string a vocabulary
                            member is recorded under, the empty value every field names itself by and is dropped
                            at (a lineage depth of 0 excepted, since that is a root), and the publication group a
                            pre-publication entry writes none of
    ledger_encoding.py      what the two external ledgers are written back as: the verbatim copy that outranks the
                            typed view wherever the reader could not type the whole of one, and the only fields a
                            record with no identity still records
    state.py                the round trip over the generation's own group, which leaves a legacy comment untouched
                            and an unreadable obligation intact: the fail-closed read, the write that drops every key
                            first and supersedes the retirement correlation on an identity, the clear defined as
                            that group and nothing else, and the all-or-nothing read and write of the hold's route
                            bookkeeping
    spends.py               the vocabulary that bounds a restored spend: every field a route may close, paired with
                            what that field may be set TO, since what comes back is applied to the pinned comment
                            and then read by the owner that knows what it is
    endings.py              what a cycle's ending leaves behind past the write that clears it, both records
                            deliberately outside the group a cleared generation drops -- three keys between them:
                            the cycle a retirement dropped, and the two-phase terminal record beside it -- the
                            decision naming the cycle a `rejected` is owed for, and the proof that one landed on
                            the issue, which together are the only durable evidence that the label an operator
                            removes to authorize a restart was ever applied, and which an attempt alone is not
    ancestry.py             frozen inherited ancestry, snapshot transforms, child and release receipt markers, and
                            the body reader that recovers a child's claimed lineage when its pinned write was lost
    lineage.py              durable inherited fields, fail-closed snapshot reads, and parent corroboration; keys and
                            write omission rules preserve ancestry after the child's own generation is retired
    exemption_reading.py    exact-commit exemption reads, their key groups, and whole semantic identities; a transferable
                            identity requires the frozen pair, matching exempt candidate, digest, and supported format,
                            while a claimed but unreadable group stays distinct from no record
    exemption.py            exemption and semantic-identity writes outside the generation's lifetime; moving the exempt
                            commit drops its old identity, and writing the same commit retains the identity it earned
    rewrite_values.py       persisted rewrite kinds, phases, and proof vocabulary, frozen authorization values, and the
                            valid kind/stage pairs; automatic rebases use the state graph's base-refresh stage set
    rewrite_fields.py       rewrite keys and wire shapes, bounded field reads, and validated encodings; the phase chooses
                            whether the accepted or rewritten commit binds the group to the exemption
    rewrite_reading.py      rewrite claims, whole authorizations, outstanding permissions, and pending reporting proofs;
                            unreadable claims cannot be replaced as though no authorization were recorded
    rewrites.py             rewrite grants before a push and publication rotation after one; the exemption, identity,
                            operator authorization, phase, and reporting proof are staged together for the caller's
                            settlement write, and only a readable outstanding grant may be spent
    overrides.py            the one oversized candidate an OPERATOR authorized to publish as it stands, bound to the
                            exact candidate SHA a human read: the frozen base it was read over, the canonical digest of
                            the contribution between them and the scheme that digest was taken under, the measurement
                            that made it oversized -- the additions counted and the ceiling they were counted against,
                            both recorded here rather than referred to, since the generation carrying them is cleared
                            and the ceiling is a knob an operator retunes -- and the trusted comment the authorization
                            was made in, which is what makes a bypass of the size gate attributable to one gesture at
                            one address. Deliberately outside the group a cleared generation drops, on the same terms as
                            the exemption: it is what a generation is cleared AGAINST. Read whole or not at all and more
                            strictly than that exemption, since here every member IS the authorization -- a missing or
                            damaged member, a digest scheme this build does not compute, a comment that is no identity,
                            and a reading at or under its own threshold, which describes a candidate the gate publishes
                            untouched, each authorize nothing, and what that costs is the measurement the gate would
                            have taken anyway. The write refuses the same terms rather than recording them and replaces
                            the whole group in one statement, so a record is never half about one candidate and half
                            about another; every other field on the pinned comment, an unknown one and a legacy
                            exemption group included, is left verbatim by both the write and the clear. What the
                            gate reads it FOR is the half of a bypass the exemption is not, so it moves with that
                            exemption: `carry_publication_override` re-points the pair onto the commit a workflow
                            rewrite produced -- the candidate and the base, and no other term, since the size, the
                            ceiling and the comment are what a human decided and the digest already describes the
                            rewritten pair -- while a comment with no readable authorization on it, and one about
                            some other commit, are each left exactly as found. The terms a caller offers answer for
                            themselves through `unusable_terms`, so a caller that has not decided to record yet
                            gets the same refusal the write would have raised
    collapses.py            the three terms a squash says it is about to collapse, written before the reset that
                            destroys them and deliberately outside the group a cleared generation drops: the head
                            being collapsed -- the rollback target, and the head the force-push behind it is leased
                            against -- the base it is collapsed over, and how many commits go in, which is the one
                            fact no reading past the rewrite could recover and what the handoff's notice is worded
                            from. Read whole or not at all, so a missing member, an end that is not a whole object
                            id, and a count no squash collapses each read back as no pending collapse -- while
                            CARRYING one of those is a separate question the recovery has to ask, since a comment
                            claiming a collapse it cannot produce describes a branch that reads as having nothing
                            to squash. What ENDS one is here too, and the write that does hands what it leaves
                            to `handoffs` beside it: the claim goes first and its successor is staged second, so
                            no comment a write could land from carries both -- a reader finding the pair would be
                            told a rewrite is outstanding over a branch already published, and refuse to resume
                            over it
    handoffs.py             the commit the relabel behind a finished collapse is still owed over,
                            `late_collapse_handoff_sha`: what the write that ends the claim leaves in its place,
                            since the relabel is a second call and an issue left on `validating` with the record
                            simply dropped is one the next tick runs a second reviewer on. Deliberately no member
                            of the collapse group and outside the one a cleared generation drops on the same
                            terms -- nothing about the rewrite is outstanding by then, so it freezes nothing and
                            refuses nothing -- and read for a usable value rather than for presence: a whole
                            object id at its exact length, since what it is spent on is a comparison against the
                            head the pull request stands on and an issue with no pull request to read has nothing
                            else between a value no commit could equal and a label moved past the reviewer. Such
                            a value is dropped rather than refused on the way in as well, the opposite of what
                            the claim it succeeds does with one: this write is taken past the push and past the
                            notice, where nothing is left to call off, so the worst it costs is that saved round.
                            One the relabel LANDED over is ended by `documenting`, which is the only owner that
                            can: having the issue is the proof that move happened, and the label history cannot
                            tell a move that never did from one a drift unwind later reversed
    restart.py              the two-phase restart marker: the closed pair of labels it may apply, the cycle it
                            mints, the whole-marker check that decides whether the one a crash left may still be
                            believed, the settled-ledger precondition retirement refuses without, and the fresh
                            cycle it projects
    events.py               the eight families, the per-family schema an event is refused against, the member each
                            detail has to actually be, the member each companion field has to sit BESIDE -- the
                            verdict a child count belongs to, and the one failure a measurement step and its line
                            belong to, since a field allowed beside every member describes none of them -- the
                            closed vocabulary a verdict category is chosen from, and the two the failure family
                            adds for a refused size reading, with the one constructor every seam that measures
                            builds them through, which drops the line with the step and reduces what survives,
                            since a refusal here would cost the only record of a reading that never happened
    validation.py           what a generation has to prove before a record of it may be written: the required
                            identity, the format of every field a sink would carry, the publication a marker has to
                            still be able to name, and what each family's own record has to be readable without
    records.py              the bounded payload both sinks carry -- including the closed pair every family's record
                            says which side of publication it was entered on under, the frozen context only the
                            marked half carries, and the refused reading's own step and line, the one free text on
                            a late record -- and the fields a duplicate record is deduplicated on
    telemetry.py            the dual audit / analytics emission, the stage tag resolved against the label
                            vocabulary, the refusal turned into a logged non-emission, and the guard on each half
                            that keeps a sink from reaching workflow
  stages/
    conflicts/              `workflow:resolving_conflict`
      handler.py            the order one tick asks its questions in: the missing-`pr_number` park, the terminal
                            arcs, and the rebase road behind them -- which owns the two dev resumes as well, since
                            deciding either needs the branch fetched and the checkout compared to it
      routing.py            the one reading every road runs behind -- the worktree restored, the branch fetched, the
                            checkout compared to it -- and everything that reading can report that is not a rebase:
                            a round the size gate held and an adjudication has since published, a behind-base
                            divergence, a body edit or a human reply the dev is resumed on, and commits a crashed
                            tick never pushed. Both resumes sit behind the divergence guard, since what either
                            starts is an agent whose commit this stage force-pushes and no lease catches a push made
                            from a checkout the remote has moved past -- the tip it is pinned to is the tip the
                            resume read. Only the BODY EDIT also defers over a checkout ahead of its remote: it
                            leases against the head the round began at, a local commit the remote never saw, which
                            the gate then refuses as somebody else's movement, while a reply's publication freezes
                            the pull request's own head and carries the unpublished commit out with the resolution.
                            It defers by falling THROUGH to the reply rather than ending the tick, since the drift
                            hash covers the thread too and so every reply reaches the routing looking like an edit.
                            The published round is settled ahead of both. The `MAX_CONFLICT_ROUNDS` cap comes after
                            all of it, in front of the REBASE alone: what it refuses is another ATTEMPT, and every
                            reconciliation above it is work already done that only this stage can still finish. A
                            park left by a reading rather than a question is retried rather than waited on, and
                            announced once per reason
      guards.py             the worktree restore and the two probes that prove a stale PR head is safe to
                            force-publish over
      divergence.py         admission over a stale orchestrator-produced head or a recorded replay, and recovered
                            publication through the size gate under the original lease; the behind-base count decides
                            whether the push finishes a round or precedes another rebase
      recovery_guards.py    recovery parks for an unreadable candidate, unpinned remote tip, or dirty/unreadable checkout;
                            each refusal retains the recovered work and the exact reason a later tick retries
      rebase.py             the branch and base fetches, the pre-rebase head every exit of the round leases its
                            push against -- refused when nothing could read it, since the gate reads no head as a
                            caller that established none and pins the push to whatever the pull request has moved
                            to -- the fork point that head's contribution is read over, taken in the same breath
                            since the replay destroys it and made DURABLE before the rebase runs, the rebase, its
                            `merge_attempt` event, and the three-way disposition
      publication.py        the unproven-tree and unreadable-head parks, the no-op flip, the rebased-head push
                            (measured by the size gate first, since a base that moved changes what the branch adds
                            to it, handed the pair the replay replaced beside it, and stamping the commit that
                            replay produced onto the durable record before the gate is entered), and the hand-off
                            of real conflicts to the dev -- which presents no such pair, since a resolution an
                            agent authored is content somebody wrote rather than a replay of content somebody
                            ruled on. Both parks are the same refusal read one step apart: a status that
                            established nothing names no paths and a head that would not resolve reads as the head
                            this stage started on, so taken as absences they hand a reviewer a tree nobody read or
                            a rewritten head the pull request never received
      evidence.py           live and recovered rewrite evidence: the replayed input pair and the new fork point;
                            recovery requires the recorded publication, original lease, and produced commit to agree
      replay_records.py     two-step replay persistence, before rebase and before publication; whole-commit reads and
                            the original publication identity keep a stale or unfinished record from proving a push
      resume.py             the three dev-resume entry points, the shared run, and the `/orchestrator continue`
                            classification. Each of the three can end in a commit this stage publishes onto a
                            pull request the remote already carries, so each passes the size gate -- the fresh
                            conflict and the reply behind it through the shared conflict disposition, the body edit
                            through the shared fix publication -- and each names the round it would have counted,
                            since a held candidate ends the tick on the adjudication and no later tick of this stage
                            counts one
      outcomes.py           the interrupt / timeout / mid-rebase parks read before HEAD, and the push a completed
                            resolution earns -- measured by the size gate first, since a resolution grows the pull
                            request like any other candidate, and pinned by the pre-rebase head this stage read
      parks.py              park notices, durable reasons, and the predicate that preserves a human question through
                            transient refusals; unreadable-head and unreadable-worktree parks are shared by callers
      transitions.py        held-round receipt reads and writes, exact-head recovery, round increments, and handoff to
                            validation; a settled receipt is cleared only by the tail that pays it
      models.py             frozen conflict context, checkout and resume results, live replay pairs, and recorded replay
                            values handed between the stage's owners
      state.py              the counter keys they share, the single settled pair one held round at a time is named
                            by, and the `conflict_replay_*` group a rebase writes about itself -- both ends of what
                            it replaced, the commit it produced, and the publication it was made against -- for the
                            tick that may have to publish it
    decomposition/          `workflow:decomposing`, `workflow:ready`, `workflow:blocked`, and `workflow:umbrella`
      run.py                one `decomposing` tick: the retry-cap notice a stranded park still owes replayed at
                            entry, the late route asked before anything else after it, the spent-budget park held
                            behind that and ahead of every road that would walk past one, the drift / recovery /
                            kill-switch order before the agent, and the pause, dirty-worktree, and interruption
                            checks after it
      retry_cap.py          the standing spent-budget park an initial decomposition meets: the hold that ends the
                            tick having written, spawned, and said nothing -- so the manifest, the children, the
                            locked session, the pull request, and the late record stay as they were -- the refusal
                            it still records, the sentence it waits to have said before any thread is read for an
                            answer, and the trusted `/orchestrator continue` that retires the session and renews the
                            budget for exactly one spawn, written down before the spawn it pays for
      handoff.py            the two ways this label hands an issue to implementation -- the kill switch and a
                            candidate the size gate settled, the latter releasing the hold and moving
                            `pr_number` onto the pull request the measured commit is on first -- and the re-read
                            the inline handler is given
      session.py            the locked decomposer session: the spec read, the fresh spawn that pins it -- gated
                            and parked by `engine/retry_budget.py`'s own parking form -- the
                            human-reply resume, and the retirement the drift reset and the continuation both take
                            -- the id dropped and the spec kept, since a spawn records an id only where the backend
                            hands one back and the resume after one that did not would replay the conversation the
                            issue was moved on from
      drift.py              what a body edit resets on an issue already wearing this label: the orphan notice said
                            before the new baseline is recorded, the manifest markers wiped in one step -- children,
                            dep graph, expected count, the seal that calls that count final, the umbrella flag, and
                            the park flags -- and the session retired through the owner above, so the tick falls
                            through and re-derives a manifest against the updated body instead of relabelling and
                            returning the way the pre-implementation routes do
      manifest.py           the fenced-block envelope rules both modes are held to, the JSON decode, and the parse entry
                            point the stage routes on
      child_validation.py   child text and dependency shapes; dependency indices must be real integers naming another
                            child in this manifest, and every malformed field is refused before graph traversal
      validation.py         bounded nonempty child envelopes, umbrella flags, and graph acyclicity after child validation
      outcomes.py           the live-pause and timeout settlement before the worktree check, and the three manifest
                            dispositions after it: the unparsed park, the `single` finalize, and the `split` hand-off
      child_creation.py     ordinary child creation, parent receipts, and pinned-state seeding; each created child is
                            recorded on its parent before seeding, and either failure parks the parent for repair
      split.py              persist the expected count, create the planned children, and publish the summary and parent
                            label before activating children without dependencies
      recovery.py           what a tick that died mid-split left behind: the stale-manifest markers, the orphan-child
                            repair, the incomplete park, and the two owners that hold those markers instead -- a
                            human the issue is parked awaiting, and the late transaction while its generation is
                            live
      parents.py            the fresh child scan, the rejected and manually-closed parks it earns -- published
                            apart from the scan, since one caller settles its ledger on the way out of them -- and
                            the parent's own drift reroute
      activation.py         the dep-graph walk that releases the next children, the child it passes over because
                            GitHub reports it closed or the scan holds no issue for it, the latch asked before
                            EVERY relabel -- a relabel is a request, so a close observed after the first child was
                            released may not release the second -- the pull request a late split superseded these
                            children out from under asked in the same place and off this parent's own record, so
                            a caller cannot answer it a child scan too early and a parent that never entered the
                            gate pays nothing, that ask itself a request and so the latch taken on BOTH sides of
                            it, the one behind having nothing between it and the relabel, and the
                            held-dependency line it logs
      blocked.py            the `workflow:blocked` poll and the `workflow:ready` handoff to implementing with its
                            consumed-comment ratchet
      umbrella_terminal.py  resolution text, usage totals, and cycle/generation receipts for published late splits;
                            retire the live cycle while retaining its obligations, then label done and close
      umbrella.py           the `workflow:umbrella` poll and barriers around child activation, cleanup, and completion;
                            require settled obligations and publication before retirement, and restore a cancelled
                            cycle when a close is observed inside the retirement window
      late_coordinator.py   the late mode's order: admission, park retirement, content settlement, then reuse
                            a recorded answer or buy one fresh adjudication; only the completion guard can
                            hand a cleared split to the transaction
      late_admission.py     recover owed owner reads and park notices before the live-generation gate;
                            hold a spent-budget park ahead of the frozen-evidence proof and pull-request hold;
                            the explicit live-generation predicate leaves initial decomposition to its own gate
      late_evidence.py      prove the record belongs to this issue and carries every frozen field its readers need,
                            then prove both commits on this host before a pull-request hold or agent spawn; a
                            failed proof parks with the recorded candidate left for the operator to restore; the
                            post-run check also refuses a moved head or a tree no longer proved clean
      late_attempt.py       the durable attempt identity and the retry accounting its pre-spawn write omits;
                            both close-latch checks restore the unspent counters before cancellation can write,
                            so a run declined by shutdown or a live pause costs the issue nothing
      late_execution.py     spend the shared retry budget and start one admitted adjudication, checking the close latch
                            around its durable attempt record
      late_completion.py    account usage, refuse unstarted, timed-out, interrupted, or mutated-candidate answers,
                            and record the session and verdict; re-read the owner for every completed or reused answer
                            before settlement, handing only a guarded split to the transaction
      late_retry_cap.py     the same standing park on the adjudication's own road: the gate its fresh spawn is
                            charged to, the refusal staged through this mode's park owner so the generation,
                            the frozen pair, and the hold on the pull request the candidate stands under all ride
                            the one write, the hold asked ahead of the evidence probe and the content settlement
                            so a held tick writes, spawns, and says nothing, the sentence it waits to have said
                            before any thread is read for an answer -- on either owner's field, since a park the
                            shared parking form took under this label owes its own and is said by the stage-entry
                            replay -- and the trusted `/orchestrator continue` that
                            renews the budget for exactly one adjudication -- written down before the spawn it
                            pays for, and needing no session retirement of its own, since the pre-spawn record
                            opens a fresh conversation for every run that is not answering a question
      late_run_reading.py   read the pinned role, locked spec, session, source pair, and validated verdict payload;
                            recover adjudications and resume only a session bound to this candidate generation
      late_result_payloads.py
                            encode verdicts and child estimates, and measure the actual serialized pinned payload
                            against the whole-comment budget with notice headroom
      late_session.py       persist spawn, bounded session, and result records and invoke the tracked adjudicator;
                            every discarded answer drops its publication override, and preflight reserves session room
      late_hold_text.py     exact cycle-marked descriptions for unpublished, published, and superseded hold forms
      late_hold_reading.py  choose the held, published, or issue-recorded pull request, read it once, and require plan
                            provenance for the issue pointer; missing or unreadable evidence refuses the hold
      late_hold_release.py  restore only descriptions matching this cycle's hold, and release a stale hold before its
                            replacement is taken; an open pull request whose restoration failed keeps the handoff held
      late_hold.py          preserve the chosen pull request's identity, head, and body before applying its hold;
                            refuse unrecorded or displaced descriptions and report moved heads without restamping them
      late_verdict.py       what one finished reply decides: the lineage-bound refusal recorded as the categorized
                            question it actually is, the record written and persisted before anything is posted,
                            and the announcement a recorded question is reconciled by -- made past the owner
                            guard rather than beside the record, and suppressed where a park already stands. All
                            three sentences a read reply hands the issue back under are worded here -- the
                            unusable reply, the outcome too large to record, and the question itself -- since the
                            reason is a shared value this mode's park owner is read against and the sentence is
                            the failing step's own to say. Too large is asked of the COMMENT alone -- how an
                            explanation will render is never grounds to refuse the verdict carrying it, since that
                            park is superseded and the refusal would buy a second run and leave a `single` short of
                            the durable park a human's decision is owed on
      late_outcome.py       what every completion leaves on the record: the write that closes one by carrying the
                            owner read it now owes -- under `owner_check` unless a split transaction was
                            interrupted, whose boundary the record itself refuses to let any pre-split write
                            rewind, since the phase is all that says a loop was in flight when nothing is
                            recorded yet -- the answer a crashed tick reads back rather than paying an agent for
                            a second time, the session a timeout or a contaminated worktree pins before the issue
                            is handed back, the one record every ending hands its caller -- a decided one
                            travelling on the adjudication itself rather than on a re-read of the comment it was
                            written to -- and the three emissions each written straight after the state they
                            describe: a verdict, a typed late failure -- carrying the step and the line behind it
                            where the reading was a re-measurement, so a reading that did not happen reads alike
                            wherever it was taken -- and the cancellation an owner read earns
      late_parks.py         the decisions that take, stage, retire, or answer a late park: a pre-run park stages
                            its claim, persists it through `late_park_state`, and releases its notice through
                            `late_park_delivery`; a post-run park is staged with its result and released only
                            after the owner guard. A fresh attempt retires only the reasons it answers, while a
                            human's answer clears its own park and any sentence that park still owes
      late_park_state.py    the park reasons, pinned keys, standing-claim predicates, and shared generation write
                            every late writer uses. The consumed-comment watermark ratchets here so a spent reply
                            cannot become fresh feedback in a later stage. Repeated parks read both the flag and
                            the owed notice, since a flag whose comment failed has told nobody anything
      late_park_delivery.py the release, redelivery, and reconciliation of a persisted park's notice. A delivered
                            comment is recognized on the thread when its settling write failed, so recovery
                            discharges the obligation without saying it twice. The shared spawn budget's
                            `retry_cap` keeps its delivery and reconciliation phases on the budget's own audit
                            stream. This owner reads state and notice owners directly and never calls back into
                            park decisions
      late_notice_fences.py safe Markdown fencing for a whole recorded explanation; candidate fence caps preserve line
                            endings, split hostile closing runs into blocks, and select the shortest complete rendering
      late_notice.py        durable park notices, explanation insertion, comment-size fallbacks, and authenticated receipt
                            reads; the notice must still match the standing park, and a failed read leaves it owed
      late_owner_reading.py fresh open/closed/unreadable owner readings, with the close-observation latch checked before
                            GitHub so a reopen cannot erase a close already observed during the worker's run
      late_owner_settlement.py
                            persist cleared claims, cancellation, and unreadable-owner parks, and deduplicate recovery
                            follow-ups within the park episode before clearing its state
      late_owner.py         guard late outcomes and child activation, claim completion ahead of the owner reading,
                            reconcile pending checks, and release or discard staged parks after that reading settles
      late_snapshot.py      the immutable copy every child of a split is cut from: the ref this generation's
                            identity names, the obligation written ahead of the push and again behind the proof, the
                            create-or-verify that never overwrites, the fetch that proves a child could obtain it,
                            and the one park every refusal takes
      late_child_content.py child scope, declared budgets, ancestry, immutable-snapshot reuse instructions, and exact
                            slice receipts; reserved markers in proposed scope are refused before publication
      late_child_records.py retain the child walk, write each child on every parent ledger before seeding its ancestry,
                            and seal a cancelled consumer ledger only once possible unrecorded children are accounted for
      late_child_adoption.py
                            recover the exact issue for a resumed slice or create it after the close latch; ambiguous,
                            closed, or already-started receipt holders are refused without creating another child
      late_children.py      walk the manifest with a fresh owner check before each slice; record a created child before
                            checking closure again, and stop rather than seed or advance after cancellation
      late_split_preparation.py
                            validate the manifest and ledgers before publishing a snapshot, prove that immutable
                            ref before creating any child, and return the durable children and ref together; an
                            owner close or an unprovable step leaves the transaction at the boundary it reached
      late_retirement.py    retire the generation with the umbrella label before activating children through
                            the shared guarded walk, then reconcile the recorded branch obligation; cleanup
                            failures remain on the ledger for the umbrella terminal to retry
      late_split_notices.py forward links and cycle-bound supersession notices naming the snapshot and ordered children;
                            thread receipts recover announcements whose pinned writes were interrupted
      late_supersession_state.py
                            persist reconciled or failed publication obligations and their parks before the split resumes
      late_supersession_reading.py
                            prove the published head and this cycle's supersession still hold; moved, merged, or reopened
                            publications withhold child activation and reclamation
      late_supersession.py  release held descriptions and supersede the exact publication; re-read published work
                            immediately before closure and record completion only after its proof and effects succeed
      late_transaction.py   prepare the snapshot and children, announce the split, supersede its publication, and retire
                            onto the umbrella; owner and publication barriers surround every externally visible step,
                            including the branch reclamation left for cleanup when the supersession is undone
      late_cleanup_state.py pass and reclamation values, obligation updates, and the shared close barrier that
                            persists cancellation once while retaining the current generation and its debts
      late_cleanup_reading.py
                            owed branches, held snapshots, opaque-ledger refusal, fresh consumer scans, and exact
                            generation-derived snapshot ownership; unreadable consumers retain their refs
      late_cleanup_proof.py prove the complete consumer ledger from its recorded phase, count, or cancellation seal,
                            then require every consumer to be freshly known closed before reclaiming its snapshot
      late_branch_reclamation.py
                            delete only this issue's superseded branch and verify both local branch and checkout teardown;
                            either remote or local refusal leaves the obligation failed
      late_consumer_release.py
                            deliver cycle-bound snapshot reclamation receipts once per child, checking closure around
                            every thread read and post; an unreachable child keeps delivery outstanding
      late_snapshot_reclamation.py
                            persist reclamation intent, refresh the consumer proof, and delete the exact snapshot;
                            recover missing refs and interrupted receipts without recreating or repointing the ref
      late_reclamation.py   select owed work, apply close and publication barriers, and retain attempted and changed
                            entries separately so unchanged failures require no pinned-state rewrite
      late_cleanup.py       settle and report attempts, persist changed entries, and hold the umbrella terminal until
                            every obligation and the superseded publication settle; opaque uncorrelated debts stay held
      late_reuse_reading.py snapshot reuse verdicts from the owner's reclamation receipt, corroborated ancestry,
                            trusted local mirror, and exact remote ref; unreadable evidence defers the dispatch
      late_reuse.py         hold or park the child before its label handler runs, distinguishing reclaimed and repointed
                            snapshots and repairing unseeded lineage from the evidence the child's body earns
      late_sweep.py         the cleanup-only pass over an owner a human closed mid-cycle -- reached by being closed
                            on `decomposing` or `umbrella`, where an adjudication runs, or on `ready` or `blocked`,
                            where a decomposition outcome that landed after the close can leave an ending nothing
                            else would find; never by the label alone: the one reading that says
                            whether there is a cycle to end, and the two readings that withhold everything but the
                            mark -- an issue open again between the poll and the refetch, and one an operator has
                            parked with `backlog` or `paused`. Being routed here at all says a close was observed,
                            so either leaves the mark behind and the rest to a later visit. What that ending
                            consists of is `late_cancellation`'s; what is here is the entry a closed issue has
                            no handler to give it -- the close a dead terminal left correlated on the record and
                            receipted on the thread, adopted before anything else is decided; and the one terminal
                            it writes itself, the `done` an
                            umbrella recorded in the write that retired its cycle and a crash took the label off,
                            retried for as long as the remote refuses it because the owner keeps the swept label
                            until it lands; and a swept label put BACK on an owner still owing the remote that a
                            hand relabel moved outside all four, since after a restart the label is the only
                            thing that reaches a closed issue
      late_cancellation_reading.py
                            outstanding cleanup and pull-request obligations, unprovable holds, and the combined
                            settled-ledger proof required before a cancelled cycle may end or restart
      late_cancellation_state.py
                            persist cancellation before telemetry and reconstruct a retired cycle from retained
                            obligations and this issue's ancestry; already-cancelled generations remain unchanged
      late_close_reading.py fresh owner and cycle readings, close-receipt markers, and the proof that cleanup ended;
                            a retirement in flight can still supply the cycle a concurrent close must name
      late_close_observation.py
                            claim and post observed-close receipts, adopt them after a process restart, and turn fresh
                            or latched closure into durable cancellation without letting a later reopen erase it
      late_cancellation_pr.py
                            release and close the held pull request with a cycle receipt, persist changed obligations,
                            report their outcome, and verify the publication again after cleanup
      late_cancellation_cleanup.py
                            reconcile the held publication, adopt an unrecorded superseded branch, scan consumers,
                            settle cleanup, and discharge child receipts before the final publication proof
      late_cancellation_terminal.py
                            record the owed rejected terminal, apply its label, and confirm it; recover confirmation
                            from the orchestrator's own label history so restart requires a terminal that really landed
      late_cancellation.py  route closed or reopened cancelled owners through the same cleanup and terminal rules;
                            hard-skip controls defer effects, and an ordinary handler never resumes a cancelled cycle
      late_authorization_proof.py
                            recompute the frozen contribution for trusted consent and retained publication overrides;
                            every frozen term and the digest must still match before publishing unsplit
      late_authorize.py     consume trusted whole-comment oversized authorizations against the recorded single verdict;
                            record the override, clear the park, and consume its reply in one write; refusals are
                            receipted per reading, and an unreadable contribution leaves the command unread
      late_unsplit.py       the park a `single` hands the issue to a human under: the sentence naming the frozen
                            candidate, the reading that stopped it, the two replies that end it -- words that change
                            the work, and the command spelled out against this candidate -- and what the verdict
                            said stopped a split --
                            NAMED rather than copied, since a park nothing supersedes whose notice could not be
                            recorded beside the record it came from is one no later tick would ever say, and quoted
                            LAST and fenced, since an explanation opening an HTML comment would swallow the
                            instruction after it -- with the candidate, the generation, the publication it was
                            measured against, the hold, the session and the recorded verdict all left where they
                            were, and a park already standing rewritten by no tick
      late_settlement.py    what a guarded verdict earns: the announcement a question owes the issue, the split
                            passed on to the transaction that creates its children, the park beside it a
                            `single` earns where no operator has authorized one, and the ORDER a candidate an
                            operator HAS authorized is settled in -- the hold and the pull request reconciled first,
                            then the
                            exemption naming the measured commit written with the identity of what that commit
                            contributes and the commit a push is still owed for beside it, then the handoff --
                            with the latch asked between every one of those steps, and never a snapshot, since
                            an accepted candidate is superseded by nothing and publishes as itself. The identity
                            is fingerprinted over the frozen pair the adjudication was run against rather than
                            over a checkout that stayed writable throughout, and a reading nobody could take
                            leaves the exact exemption alone
      late_reconcile.py     the two reconciliations that order opens with, shared with the handoff of a candidate a
                            remeasurement put back under the ceiling: the hold RESTORED rather than rewritten, and
                            the pull request settled against the measured commit in any state -- searched for by
                            commit where nothing had published it, with a settled pointer dropped rather than handed
                            on, and where the verdict was taken PAST publication proved rather than searched for,
                            still open, and refused otherwise, since dropping the number there would push onto a
                            branch whose pull request a human settled and open a second one for a change
                            adjudicated against the first
      late_proof.py         where that publication has to be STANDING, and the refusal every unconfirmed
                            reconciliation takes: the head the reading was frozen at, or the accepted candidate
                            WHERE the approval, or the receipt read with the head it replaced, vouches for it --
                            which is the settlement's own push having landed before the tick died, and is finished
                            rather than refused (that same head on a fresh pass, ahead of both writes, is something
                            else's push and refuses with every other moved one)
      late_verdict_push.py  the push an authorized settlement of a candidate taken past publication makes --
                            what an adjudicator's own `single` earns is the park beside it -- made HERE because
                            this tick still holds the evidence -- named against the accepted commit and leased
                            to the head the reading was taken over -- plus the checkout proved on the road out,
                            since every stage the label hands the issue to works from it and one carrying loose
                            edits or an unmeasured descendant would reach a review, a squash, and a merge with
                            nobody having read it
      late_handback.py      the effects a settled decision licenses, in the order a crash in them is safe in:
                            the push, the label handed to the stage the record names rather than to implementing
                            -- a pre-publication candidate goes back to the ordinary publication -- the accepted
                            notice, worded on the operator whose authorization is the only road here, and the
                            retirement behind them answered by REINSTATING the cycle rather than
                            refusing, since past that write there is none left to end, with the write and that
                            barrier held inside the observations owner's retirement window so a poll reading the
                            record between them is not told there is nothing to end, and the cycle that
                            retirement dropped recorded outside the group the write clears, so a process that
                            dies before its own barrier leaves a receipt something can still be adopted against
      late_publication.py   the pull request a verdict taken PAST the first push was measured on, read once for
                            both roads out of the adjudication: a settlement publishes onto it and a `split` closes
                            it over a supersession, and neither may look it up -- the entry the gate froze names
                            it and the head it was standing on. One reading, because a fetched pull request is
                            lazy and the reads behind the lookup are what talk, so a caller guarding only the
                            lookup leaves them to raise out of a road whose every other refusal parks -- and a
                            caller's own receipt is read there too, since one that CLOSED the pull request itself
                            and died before the work behind that close was finished cannot tell its own close
                            from a human's by the state alone -- and the pull request those facts were read off
                            travels back with them, so a caller that has to ACT acts on what it proved rather
                            than on a second lookup a human can move something between; plus the question a
                            SETTLED split keeps asking, which three owners share: whether the pull request it
                            closed is still closed over the head it froze, published as the ASK rather than as a
                            fact and taken off the record every time it is put -- the generation for the
                            transaction and the reclamation, the pinned comment for the activation walk -- since
                            a step licensed by an answer the step in front of it took is one a human had time to
                            overtake, and since the retirement that hands the issue to `workflow:umbrella`
                            outlives neither the children still to be released nor the branch still to be
                            deleted
      late_budget.py        the declared addition-budget field and positive whole-line reader, plus fresh-reply bounds;
                            each proposed child needs a count strictly below the frozen ceiling, while legacy records
                            can still omit a budget
      late_prompt.py        the late-only prompt: the committed candidate, the frozen diff, the measurement, the
                            lineage, and the three outcomes with the bounds they are judged against and the two
                            field names they are answered under, read off the owners that read the reply -- the
                            human decision a `single` requires and the explanation it owes for it, the
                            dependency-ordered slices and dormant prerequisites a split has to consider before
                            that answer, what every child body owns, and the addition budget each child declares
                            under this generation's own ceiling -- the figure its own JSON template shows scaled
                            to that ceiling, since a template is copied verbatim and a standing one would be a
                            child the reply contract refuses wherever the ceiling is narrower than it
      late_reply.py         the late reply envelope and its three structured decisions; fresh split replies use the
                            shared child validator and budget bounds, and a single decision must explain why no safe
                            split exists before it can be presented for a human decision
      late_content.py       WHICH content the two late-local fingerprints are taken over -- the title and body, and
                            the trusted-thread run the ratcheting watermark covers -- what a comparison against a
                            recorded baseline says moved, and the floor a comment has to clear to be a REPLY rather
                            than conversation the issue was already carrying. What each reply past that floor IS
                            comes back from `late_content_replies` on the same walk, reported beside the bare
                            `/orchestrator continue` this owner reads for itself, since that one earns a flag and
                            no record; the digests themselves are the `late_split/identity` owner's
      late_content_replies.py
                            which fresh reply is a requirement a developer may be resumed against, and which is the
                            whole-comment `/orchestrator authorize-oversized <commit>` that licenses a publication
                            past the size gate -- the last of those in a batch being the request, since a corrected
                            commit below a mistyped one is what a human who wrote both meant, and carried forward
                            with a malformed argument intact so the owner that refuses one has the command to
                            refuse. Neither that command nor a bare continue is guidance, because nothing hands an
                            agent a decision about the candidate that already exists as work to do, and prose
                            around either is guidance because neither is the whole comment then. Both are
                            recognized through `engine/messages` rather than re-read here, and neither is kept out
                            of the digest the owner above takes -- a counted command edited after the fact is
                            exactly what that digest exists to catch
      late_guidance.py      initial content baselines, drift parks, and routing of trusted guidance or bare continues
                            over the same frozen candidate
      late_answers.py       parked-answer dispatch, reverted edits, certification, question reopening, and reply consumption;
                            every consumed reading rebaselines and persists its watermark, while a bare continue cannot
                            answer a decomposer question
      late_revision.py      the developer run guidance buys -- the locked session resumed under `agent_role=developer`
                            and `stage=decomposing`, with a latched close asked on BOTH sides of it, since a resume
                            is the same step a spawn is and the run takes hours -- and the followup it is resumed
                            with, quoting the issue as it reads NOW and asking for the `ACK:` marker an UNCHANGED
                            commit needs before it counts as an answer. The two entry points are this owner's own --
                            the guidance that buys a run, and the reply to a revision that stalled -- and each asks
                            the two owners below in turn rather than re-exporting what they hold
      late_revision_obligations.py
                            the refusal a candidate the last adjudication already acted on earns instead of a
                            revision, asked on BOTH roads into one -- ahead of the notice and the spawn guidance
                            buys, and ahead of the re-read a bare continue takes without either. Two effects put a
                            candidate past replacing: children it created, which a second manifest over the top of
                            would strand, and a recorded snapshot obligation, refused in ANY state because a moved
                            `candidate_sha` leaves the reclamation comparing a ref against a commit it no longer
                            names and none of the states proves the ref absent -- an untypeable ledger entry
                            answering yes with them, since one this binary could not read may be exactly that
                            obligation. The hand-back is the reconciliation owner's own park, so a refusal exits on
                            the terms every other late park does
      late_revision_reconciliation.py
                            the clean tree, re-frozen commit, and fresh measurement a finished run's result is
                            proved through (which carries none of the last generation's split receipts, and none of
                            the authorization an operator gave the answer this re-freeze retires -- an acknowledged
                            unchanged candidate comes back matching every term of it), the reading of the `ACK:`
                            marker that decides whether an UNCHANGED commit is an answer at all, and the fresh owner
                            read a landed reconciliation and a parked one alike ride out past
      late_relabel.py       the `workflow:decomposing` label a live generation pins -- one still oversized, or one
                            whose owner read is still owed: the kill-switch route it refuses, and the dispatch it
                            refuses -- with the hand relabel it repairs -- when a human has moved the label out from
                            under an open adjudication
      late_restart_effects.py
                            deduplicate and adopt restart notices by cycle receipt, then establish the chosen label;
                            reapply a foreign label so the fresh cycle has the restart's own history boundary
      late_restart_state.py repair restart identity, persist its marker, and project the fresh cycle while retaining
                            thread attribution and cumulative usage; retirement drops the predecessor's work and sessions
      late_restart.py       admit and resume an authorized restart only after cancellation and every obligation settle;
                            hard-skip controls defer it, the recorded target outranks settings, and notice plus label
                            effects must succeed before retirement
      late_result_models.py late-run identity, adjudication answers, guarded splits, and settlement dispositions; an
                            actionable answer remains bound to the exact cycle, generation, and candidate it read
      late_content_models.py
                            frozen content fingerprints, trusted authorization replies, drift signals, and the outcome
                            of consuming one reading
      late_models.py        mutable tick context, tri-state owner readings, held pull requests, and staged park values
      models.py             the run plan and its worktree policy, the locked session, the split plan, and the child
                            scan
      state.py              the pinned-state field names the owners share, the held-child alias, and the
                            issue-reference renderer
    discussion/             `discussion`
      handler.py            the order one round asks its questions in: whether the conversation is over, whose turn it
                            is, what the checkout holds, and what the round left behind
      terminal.py           the order the endings are asked in: the recorded plan PR handed to `plan_terminal` before
                            the issue's own close is read, then the marker lookup that finds a PR a crash left
                            unrecorded -- whose branch is resolved once, ahead of the number it records, so the ref a
                            reap names is the one this stage pushed, and which holds here on a recovered PR still open
                            and on a lookup GitHub declined, handing on only a decided one -- and the pre-PR close,
                            which reaps nothing
      plan_terminal.py      what the humans did with the plan PR: the fetch by recorded number, held where GitHub
                            would not serve it, and the verdict both callers finalize through -- merged to `done`,
                            closed unmerged to `rejected`, an open one writing and reaping nothing
      session.py            the pinned agent and session a conversation is locked to, the filter its replies are drawn
                            through, and the prompt paired with the replies it read
      round_evidence.py     what the checkout was holding before a round could open over it: the tree read as a
                            status rather than a path list, since the list form answers its own failure the way a
                            clean tree does and what follows a clean answer force-removes the tree, and the tip
                            compared against the anchor the last round recorded -- falling back to that round's
                            branch where the directory has gone, and held where neither read could answer. Taken
                            ahead of the restorer in `run`, which is the step that would erase what they report
      run.py                one round in the issue's own worktree, the restorer that checkout is rebuilt by, and the
                            branch and SHA it records opening on
      settlement.py         one reading of the evidence above -- the tree and the round anchor -- and the ownership
                            test the commit it finds is settled by: this stage's to publish where a round was in
                            flight, and somebody else's to report otherwise, under a park this stage wrote and off
                            one alike
      outcomes.py           the pause, timeout, write, and response decisions one finished round is classified by, and
                            their routing
      publication.py        the re-runnable order a publishable commit earns: the durable marker that makes the
                            attempt recognizable, the lease the push is held to, the push itself, and the hold that
                            stops where GitHub could not say whether the commit is already on a PR
      artifact.py           one reading of what the branch carries -- the tree, the base-relative diff, the plan in
                            HEAD, and whether HEAD is the branch -- taken from the checkout the round ran in and
                            rebuilt only where that directory has gone, plus the fetch that makes a remote tip
                            askable there
      settled_prs.py        the pull requests that leave a commit nothing to publish: the merged or closed one found
                            by commit, and the open one whose head the humans moved past it
      recovery.py           a publication a tick died in the middle of: the marker that answers for the branch, the
                            remote reading that tells a plan that landed from a branch an operator reset, and the
                            stale refusal written once
      plan_pr.py            the plan's own pull request: the open one reused -- its body rewritten where it does not
                            already name the publishing session -- or the new one opened and announced, the title
                            taken from the plan commit's own subject, the body that names that session and says what
                            merging or closing decides, and the refusal of a plan no session can be named for
      records.py            what a finished publication writes down: the adoption of a PR already carrying the
                            commit, and the plan path, branch, number, PR head, and moved round anchor one durable
                            write leaves behind
      parks.py              the funnel every way the stage hands the issue back goes through, which stamps each
                            park's reason and restores the consumed ceiling
      checkout_parks.py     the endings the per-issue checkout earns: the agent's loose edits and the stranded tree
                            that arrived holding them, the tree that would not read at all behind both, the finished
                            round whose HEAD could not say what it did, the tip that moved with no round in flight,
                            and the reply no round may open on
      publication_parks.py  the endings a reading of the committed plan earns: the round's own unpublishable commit
                            and the recovered one beside it, the published plan, the plan no session can be named
                            for, the publication the branch moved off, and the diverged and failed pushes
      outcome_parks.py      the endings the run itself earns: the timeout, the silent backend and its diagnostics,
                            and the analysis a finished round posts
      park_messages.py      what those endings quote: the bounded path list, the reading of a committed artifact,
                            the refusal frame both unpublishable-commit parks share, the stale-publication standing
                            and remedy, and the anchor a reset is named against
      models.py             the run, the agent identity and session, the prompt and its replies, the round, the
                            outcome, and the publication artifact
      state.py              the park reasons and wire keys, the plan path and the commit its PR carries, the
                            open-round and in-flight publication markers, and the three park predicates
    documenting/            `workflow:documenting`
      handler.py            the order one final-docs tick asks its questions in
      preconditions.py      the terminals, the missing-`pr_number` guard, the parked-no-input fast path, and the
                            refused bare continue
      run.py                the branch refresh and diverged-worktree guard, the verdict an earlier pass left dropped
                            as this one begins -- every shape re-anchors the checked head, so a stale verdict beside
                            it would advertise a head no pass has documented as ready to merge -- plus the resume,
                            recovered-commit, and fresh-spawn shapes
      outcomes.py           the timeout / dirty / commit / `DOCS: NO_CHANGE` order a finished run is read in
      publication.py        the size gate a docs commit passes -- the last one before a human is asked to merge,
                            and handed the commit this pass made so a checkout something moved is refused rather than
                            measured in its place -- then the push, the docs watermarks it stamps, and the PR notice
                            it posts; a commit the gate held and one it let through leave the same receipt, the head
                            the handoff is still owed for, and the handler finishes from that only over a checkout
                            standing ON it, since in sync with its remote is what a replacement host rebuilt at a
                            moved pull request reads as too -- the write that records the pass drops it, so no
                            receipt outlives the handoff it was written for
      drift.py              a body edit mid-hop: the dropped approval, the unwind sentinel, and the relabel to
                            `workflow:validating`
      drift_reset.py        the fetch / probe / hard-reset that puts the worktree back on the PR head, and the parks
                            each failure earns
      handoff.py            the `pr_last_comment_id` ratchet that keeps in_review from replaying a consumed reply,
                            the write that carries it, and the relabel behind both -- taken ahead of that write, the
                            relabel leaves `in_review` a pass it reads as unfinished and no stage goes back for it.
                            The handoff that brought the issue HERE is ended here too, at the top of the tick and in
                            a write of its own: a `validating` approval settles a finished squash into
                            `late_collapse_handoff_sha` and drops it behind the label it moves, so a record still
                            standing is that move having landed and that write having failed -- and this stage
                            having the issue is the only proof of it, since the label history cannot tell a move
                            that never happened from one the drift unwind above later reversed
      parks.py              the shared awaiting-human park and the missing-PR, dirty-tree, and question parks
      models.py             the frozen records the owners hand each other
      state.py              the pinned-state keys they share
    fixing/                 `workflow:fixing`
      handler.py            the order one tick asks its questions in, plus the preflight terminals, the
                            missing-`pr_number` park, and the commit the no-feedback bounce publishes -- measured by
                            the same size gate the shared dev-fix publication passes, so a held candidate stops the
                            bounce rather than being relabelled over -- before it hands the PR back to the reviewer
      feedback.py           the rescan past the three in_review watermarks, the quiet window a fresh batch settles
                            through before a resume spends the session on a fragment of it, and the narrower ratchet
                            a consumed batch advances those watermarks by
      bookmarks.py          the `pending_fix_*` ids a replay rebuilds the triggering batch from, and the clear each
                            round earns
      resume.py             the dev run, the ACK fast path, the `workflow:validating` relabel a pushed fix earns, and
                            the round a fix the size gate sent to adjudication spends here -- no later tick of this
                            stage can, since the head the reviewer rejected is superseded whether that adjudication
                            parks its `single` for a human or an authorized settlement publishes before handing the
                            issue back
      parked.py             the four answers an `awaiting_human` tick can reach and the order they are asked in
      continue_command.py   `/orchestrator continue` on a parked fix: the replay and what it may hand the dev --
                            guidance, never the command itself -- plus the two refusals and the guidance passthrough
      drift.py              the `workflow:resolving_conflict` reroute a stuck validating-route park earns when its
                            worktree has fallen behind base
      models.py             the frozen records the owners hand each other
      state.py              the pinned-state keys they share
    implementing/           `workflow:implementing`
      handler.py            the order one tick asks its questions in, opening with the retry-cap notice a stranded
                            park still owes
      spawn.py              awaiting-human vs active, the restorer the checkout comes back from, the
                            recovered-worktree shortcut and the certified baseline it stands down for -- which
                            an unread head cannot spend, since that comparison is what a retirement rests on --
                            and the retry-gated fresh spawn, which retires the pinned session wherever a
                            continuation is what paid for it: the grant is durable and the budget is shared, so the
                            tick that spends one is not always the tick -- or even the stage -- that granted it
      session.py            the four session retirements -- the fourth being the continuation that buys a spent
                            budget one more attempt, which is a fresh spawn by definition -- and the fresh-spawn
                            prompt. The budget that retirement answers to is `engine/retry_budget.py`'s entire,
                            gate and park alike, and the spawn road calls it there
      session_read.py       the locked session read plus the stale / overflow / quota classifiers and the blockquote
                            they quote with
      resume.py             the two resume entry points and the historical call shape they keep, with the
                            orchestrator's OWN comments dropped from the batch by the recorded id ledger: every
                            park here posts before the write that records posting it, and the default empty
                            allowlist trusts every author, so a notice whose write was lost would otherwise
                            reach a developer as somebody asking for a change. A batch whose LAST fresh reply
                            is the command ending a standing authorization park defers the whole tick,
                            unconsumed, to the poll that can act on it: this read comes after that park's own
                            owner classified the thread, so a command landing between the two would otherwise
                            be spent -- not by this batch, which could spare it, but by the park the run it
                            starts goes on to take, whose notice lands above the command and takes it. A batch
                            the measurement park's own road would re-measure on defers the same way and for
                            the same window, asked of the trusted read BEFORE our own comments come out of it
                            since that is the read that road takes: reserved off a narrower one, this tick
                            would defer what that road then refuses and the two would hand the thread back and
                            forth forever
      resume_request.py     what one such call supplied, frozen and checked before a run is built: the stage
                            its records are attributed to, and the unknown option a named parameter would
                            have refused on its own
      execution.py          one resume, its poisoned-session retry -- withheld on an issue a poll observed closed,
                            since that retry is a SECOND agent -- and what each attempt is allowed to persist
      worktree.py           the checkout a resume runs in, restored when reaped
      disposition.py        run-output attribution, inherited floors, timeout parks and their recovery, and agent-result
                            settlement; both heads must be readable and the run must leave commits above its floor
      candidate_recovery.py exact-commit recovery for approved and frozen work, timeout-commit evidence, and publication
                            through a proved clean tree and the size gate; a recovery hands on the candidate it proved
      late_gate.py          prove the caller's committed candidate, ask receipts and existing permissions, and then
                            take a fresh or resumed measurement; the verdict carries the basis admitting publication
      late_gate_permission.py
                            read the authorized exemption, frozen remote tip, unspent approval, and proved receipt;
                            an unknown candidate reaches the switch only after those records have answered
      late_authority.py     whether the human behind an adjudicated commit is one this issue can show, which is
                            what every road past the measurement asks before it takes one. The exemption and the
                            `late_override_*` authorization are asked TOGETHER and both held to naming one commit,
                            since either alone is half a bypass -- an exemption records that an adjudicator ruled
                            the change one whole, and only an operator's own gesture says a human agreed to publish
                            past the ceiling. Neither is believed on its shape: every term of an authorization but
                            the digest is the pinned comment agreeing with itself, so the contribution between the
                            pair the record names is fingerprinted again here and held to what that record says,
                            and a reading this host cannot take refuses on the same footing as one that disagrees.
                            What a refusal costs is the measurement the gate would have taken anyway. One thing is
                            never held back by it: a commit the pull request this call FROZE is ALREADY standing
                            on, where the push moves nothing and only the bookkeeping behind a publication that
                            has happened is left -- the seam that froze none asks the same question of its receipt
                            through `late_delivery` instead. Work that is over is outside it too, since a merged
                            or closed issue is finalized before any handler reaches the gate. The publication DEBT
                            such a commit leaves is the same question one field over, answered off the approval's
                            own recorded basis rather than inferred: the two bases an operator's gesture is behind
                            defer to this reading, a gate-owned `reading` approval is untouched, and an approval an
                            older binary wrote with no basis falls back to the exemption -- read conservatively, so
                            a comment that CLAIMS one and cannot say which commit it is about is the
                            adjudication's debt rather than this workflow's own
      late_delivery.py      what the publication receipt has to prove before it vouches for anything, and the pull
                            request that proof was ABOUT. The note names what this stage last PUSHED and nothing
                            about where it went or whether it is still there, and it is never cleared -- so a
                            branch published rounds ago carries one for the rest of the issue's life, and answering
                            on it alone republishes unmeasured and unleased, opens a SECOND pull request over the
                            same work, and hands the issue on. A call taken past a publication has its own frozen
                            head and is checked against that; the implementing seam froze none -- its push is what
                            OPENS a pull request -- so there the remote is read for the number the record names and
                            answers only for an open pull request standing on this exact commit AND open on the
                            branch that seam would push, which it resolves for itself, with its head in the
                            repository the client that took the reading is for, and over a receipt recording no
                            LEASE -- a lease names the head a push REPLACED and only a call that froze a
                            publication writes one, so a receipt carrying one at this seam was left by some other
                            call and its commit matching the candidate is a coincidence the fresh receipt behind
                            the push would clear the evidence of. The answer is the NUMBER
                            rather than a permission, because a reading is a moment: it pins the lease its push is
                            held to, which is that commit, and the pull request its bookkeeping belongs to. A proof
                            that FAILS is a park rather than a fall-through, and the size of the candidate is why:
                            measured and found small it would be published, which force-pushes a branch nothing
                            could confirm and opens a second pull request over work the first may already carry.
                            A receipt GROUP this build cannot read whole is the same answer one step earlier
                            and is asked at the gate's own DOOR, of the record and of no candidate: every road
                            out of a gate call ends in the write that puts a fresh group down, and the road that
                            answers FIRST -- `DECOMPOSE=off` with no caller-named candidate -- never reaches the
                            candidate question the rest of the proof hangs off. It is apart from the commit
                            comparison because that comparison cannot see it: every late field is read
                            fail-closed, so a hand edit comes back as no receipt, and published over the push
                            writes a fresh group across the damage and destroys what an operator would have
                            repaired it from. The one road with no gate door of its own -- the accepted
                            settlement, which reaches the transport directly -- is refused by its own
                            reconciliation on the same terms. Three shapes are damage. A KEY that is gone while its siblings are
                            there is asked first, and it is why PRESENCE is asked of every member rather than of
                            the commit alone: the write puts all three keys down, `null` included, so a missing
                            one is a hand edit rather than the empty lease an initial publication records. A
                            member that CARRIES a value nothing can read is the second, named so the park says
                            which field to repair. A group naming no PUBLICATION is the third -- a commit with no
                            readable number beside it, or a lease or number with no readable commit -- and it is
                            the one a commit-only check walks past, since a receipt naming some other object id is
                            never compared against the candidate and the next push completes the partial group
                            rather than leaving it. An empty LEASE is the one member that is not damage where its
                            key is there: an initial publication froze no head and records `null`.
                            The park writes nothing else -- the receipt, the recorded number and any debt beside
                            them stand for the terminal or the retry. Which pull request is the RECEIPT's own,
                            written with it by the push that landed and never searched for: `pr_number` is the
                            relabel's write, which is the one this window is missing, and a lookup by branch
                            answers with whatever is open on that ref -- so a REPLACEMENT somebody opened after
                            closing the original would be taken for the publication this stage made, and the
                            relabel, the debt and the receipt would all be spent against it. Absent or unreadable
                            the proof refuses. NOTHING is outside the park, an exemption or an approval naming
                            the same commit least of all: each answers whether the candidate needs a fresh READING
                            and says nothing about where the work went, and the delivered road records the commit
                            as a debt BEFORE it pushes -- so a tick dying there leaves an approval with no lease,
                            and waving it past publishes unleased onto whatever a branch lookup finds
      late_consent_state.py durable authorization parks, candidate-scoped notice receipts, quiet delivery settlement,
                            and consumption through the command reading's watermark; later human replies remain unread
      late_consent.py       request an operator's authorization for an adjudicated oversized commit, validate the named
                            candidate, fingerprint its contribution again, and record the measured terms while retiring
                            the park; refusals retain the candidate and share the same scoped receipt rules
      late_command_reading.py
                            whole-comment command parsing, valid comment ids, and stage attribution from the id ledger
      late_command.py       select the last fresh trusted human reply from one thread reading, carry its furthest
                            watermark, and read through later attributed stage comments without crossing human guidance;
                            receipt checks exclude the pinned comment by id
      late_recovery.py      the ordered recovery dispatcher ahead of every developer spawn: repair stranded
                            authorship, restore a held park, retry measurement, answer authorization, then
                            recognize a restored candidate; committed work never buys a replacement developer run
      late_candidate_recovery.py
                            re-measure committed work on a trusted bare continue, or republish an approved
                            candidate restored to its checkout; both carry the proved commit into the ordinary
                            publication seam and persist its answer
      late_authorization_recovery.py
                            answer the authorization park's named command only on its own committed candidate;
                            guidance returns to the ordinary resume and silence holds without another reading;
                            missing, dirty, unreadable, or moved checkouts leave the park and command untouched;
                            a proved checkout hands the decision to `late_rollback`, which preserves the park
                            across a publication that fails or never returns
      late_authorship.py    which comments on that park's thread are this stage's own words, on two records. The
                            ID is the ordinary one: the client this owner lends the seam puts what GitHub hands
                            back into `orchestrator_comment_ids` the instant each post returns, since the seam
                            says several things before it comes back and a sentence unattributed for the whole
                            of that call is one every reader in between misreads. The RECEIPT covers the one API
                            call left, and it is a digest recorded before the comment carrying it exists.
                            What it commits to is the SENTENCE rather than the sender -- the secret AND the exact
                            body it goes out on -- which is the whole of why claiming one is safe. A secret is
                            unforgeable only until it is disclosed, and posting the sentence discloses it: from
                            that moment a reply quoting our comment carries the secret too, and the login beside
                            both is a token this repository says may be shared with the human whose consent this
                            park collects. Ordering told the two apart only while our comment stood, and ordering
                            does not survive that comment being DELETED -- one tidy-up on a thread where somebody
                            has already quoted it. Bound to the body, their reply answers nothing, since a quote
                            carries their words as well as ours; what can still answer is a verbatim copy, which
                            carries nobody's words to lose. One receipt per COMMENT, since a digest of one body
                            is answered by that body alone, and the first is recorded before the seam is entered
                            at all -- the seam can post the moment it is called. What answers one is a
                            LEDGER repair, run ahead of every routing decision this stage makes: one reading of
                            the thread, the EARLIEST comment whose body is that sentence recorded in
                            `orchestrator_comment_ids`, no watermark moved -- one moved to our sentence crosses
                            everything under it, so a corrected command written below would be consumed unread.
                            Earliest because a copy can only follow what it copies, and a reply merely quoting
                            our sentence carries its author's words too and answers nothing, so the accidental
                            case cannot be claimed at all. Where our own comment has been DELETED the earliest
                            answer left is a verbatim copy and nothing on a thread tells it from ours, which
                            takes reposting a bot notice byte for byte and removing the original -- not an
                            accident, and available only to somebody already holding the token that authorizes
                            publication outright. A receipt is dropped by that repair, by the write recording a
                            posted id, or -- for a promise the seam never worded a sentence for -- by the
                            handoff that made it, and nowhere else: one cleared while its sentence is still
                            unledgered leaves nothing able to find that comment again
      late_rollback.py      one handoff into that seam and what it is held across. The seam's refusals park under
                            reasons of their own and its notices move the watermark past whatever they find --
                            right on every other road, and here the operator's own decision thrown away. So the
                            park, its reason and its watermark go down on the RECORD before the call and are put
                            back after it: the seam's writes are durable before it returns, so a rollback living
                            in the frame that made it dies with the process. A record still carrying that pair is
                            a call that did NOT publish, since the write moving the label out of this stage is
                            what spends it -- so both roads that read it restore whatever the record says now,
                            the call that came back with nothing pushed and the poll that finds a tick killed
                            halfway through one. What the seam left the park FLAGS saying decides nothing:
                            several of the gate's roads to a held verdict clear them without publishing -- a
                            bounded transport miss counting a quiet retry, a close that ended the cycle, a record
                            this commit is superseded by -- and each taken for a publication drops an operator's
                            question and consumes their command. Put back over work the seam did publish that
                            costs a poll; left off it costs a decision, and an issue the seam relabelled never
                            reaches this road again.
                            How far the reading behind the command GOT goes onto the record in that same write,
                            for the opposite outcome: the seam consumes the command itself where it records an
                            authorization from it, and its two roads that publish without reading a thread -- a
                            candidate the ceiling now lets through, and one an authorization already on the
                            record covers -- would leave it standing on an issue that has moved to `validating`,
                            read there as somebody's fresh feedback. Written down rather than applied on the way
                            out, since the write that moves the label is the last one this stage makes on the
                            issue, and `late_park_state` spends it there. Consumed to what that reading LOOKED at and
                            no further, and never on a call that published nothing -- the gate's own reading can
                            have held the park over guidance written between the two readings, and that reply has
                            to still be there for the poll that acts on it -- so every road that puts the park
                            back drops the boundary instead
      late_reading.py       the reading itself, on the two roads into one: a fresh pair frozen before it is counted,
                            so a tick that dies over the diff comes back to the pair this one froze, and a recorded
                            one acted on only once its other fields say what the number MEANS and the base it names
                            is proved present here
      late_overflow.py      what a gate call taken PAST publication freezes before it may measure -- the stage it is
                            taking the issue out of, the pull request the work already has, and the head that pull
                            request is standing on -- and the seven refusals that make freezing them fail closed: a
                            tree that is not provably clean, a pull request nothing could read, one that is closed or
                            merged, one whose head lives in another REPOSITORY -- a fork carries this repository's
                            ref names over its commits, so every term below agrees while the branch the push names
                            was never what that pull request is about -- one open on a BRANCH other than the one
                            this publication will push, a
                            caller-named head that is no whole object id or that disagrees with the head
                            this owner reads, and a head that moved off what a live record froze; asked behind the
                            switch, so an install with the gate off pays neither the read nor the park. Also what a
                            record already carrying a publication is re-proved against -- the whole frozen identity
                            rather than the head alone, since a branch reused across two pull requests puts the same
                            commit at the tip of both -- and what the CALLER established rather than what this owner
                            would re-read: the head it pinned its own decision to, checked against the one this owner
                            reads rather than substituted for it, the BRANCH it resolved and is about to push, and
                            the stage a same-tick remote relabel wrote over a cached one. The branch is asked first
                            because it is what makes every answer behind it about the same publication: the number
                            and the branch are two fields on one pinned comment and they can disagree -- a `branch`
                            a hand edit moved, or a `pr_number` left over from a cycle that ran on another ref -- so
                            an entry frozen on the head alone would describe a pull request the push never touches,
                            and the settlement, the receipt and the relabel would all be spent against somebody
                            else's publication. That comparison has one carve-out and it is not a preference: a
                            tip a DURABLE RECORD says this issue put there -- an approval's commit, a live record's,
                            or `implementing_published_sha` read with `implementing_published_lease`, the head that
                            receipt replaced, AND `implementing_published_pr`, the publication it went onto -- is
                            this issue's own push having landed, which is the window an
                            approval exists for; anything else at the tip is somebody else's branch move and
                            refuses. The caller's own candidate is deliberately not among them: on a fresh attempt
                            no push of this workflow's has run, so a tip that merely happens to BE that commit says
                            an agent put it there, and waving it through would measure and route the candidate the
                            gate is holding back. The receipt is not among them ALONE either, since one that is
                            never cleared would read a pull request rewound onto a commit published rounds ago as
                            this tick's own push arriving -- and a checkout rewound with it agrees on every local
                            fact there is. Dated by the head it was PINNED to it names the one window it is evidence
                            for, a push made from the head this call was entered on, onto the pull request this
                            call is freezing, under a process that died before the relabel. The number is the term
                            the other two cannot supply: a branch pushed from that head onto a publication since
                            closed and REPLACED by another on the same ref satisfies both of them.
                            Two readings here answer no entry at all and are asked for opposite
                            sides of an effect: whether a pull request is OVER, read fail-open for a tick that hands
                            itself back, and whether one is still OPEN, read fail-closed immediately before a push
      late_publication.py   the answer half, between that entry and the push: the switch, the record, and the count
                            asked in one place, so the seam that reached the gate makes no difference to what it is
                            told -- an install with `DECOMPOSE=off` reads no pull request for the MEASUREMENT,
                            which is the one reading it saves rather than every reading there is, a record already
                            in the gate goes through the ordinary questions, and a commit an approval owes a push is one
                            this gate has already ruled on; a hold is the whole of what the tick did, parked or
                            handed to the adjudication, rather than a bare permission, and anything else carries the
                            commit the push is named against, the head it is leased against, and the head the pull
                            request stands on now, which is what says whether the push has anything left to do.
                            Whether that publication has ENDED is this owner's too, asked immediately before the
                            push it answered for: a pull request merged or closed in the window behind everything
                            that read it -- whose branch is still at the head this tick froze, so the lease SUCCEEDS
                            and the force-push moves a merged pull request's branch back onto the commits it merged
                            -- and then, LAST, a close a poll latched. Read fail-CLOSED, the opposite of the same
                            reading at the reconciliation's door, since there falling through costs a poll and here
                            a branch nothing can put back; asked of every push onto a pull request the record names,
                            whatever the switch says, since `DECOMPOSE=off` decides what enters the MEASUREMENT and
                            not whether a merged pull request may be force-moved; and the latch last because the
                            reading above it is a request, so a close landing while it is in flight is one only an
                            answer taken after it can still give. A record that cannot NAME a pull request refuses
                            ahead of the reading and with no absence carved out, since every road here publishes
                            onto one the remote already carries: a field that is gone and one that will not type
                            are the same refusal, and reading the second as "nothing to check" is how the barrier
                            would skip its request altogether and force-push onto a publication somebody ended
      late_push.py          the one call every gated push onto a pull request the remote already carries goes
                            through -- measure, push named against the measured candidate and leased against the
                            frozen head, spend the debt it paid, close what the route owed for it (in that same
                            write, since past it neither the approval nor the generation is left to say a round was
                            owed, while the caller still has a relabel and a write to make), record what reached the
                            remote so a tick that dies
                            past the push neither re-reads nor re-pushes it, refuse work that ENDED -- a pull
                            request somebody merged or closed, and then a close a poll saw -- immediately before
                            the push and nowhere else here, since every guard above spends a reading, a diff or a
                            request after it and an ending landing in one of those windows would be answered one
                            push too late (the question itself is `late_publication`'s, beside the entry it is the
                            far end of), and prove the checkout again on the far
                            side of the effect -- AHEAD of that write, so what the proof answers rides it: a
                            checkout that moved or was dirtied holds the handoff rather than the publication, and
                            the claim it owes lands with the receipt rather than one write behind it, where a crash
                            would take it and leave the stage below reading a dirty worktree as no stranded work;
                            asked through `checkout_guards` below, the same owner the initial publication is
                            proved by, for both; a pull request already
                            STANDING on the candidate goes through the same
                            tail, since the request is the only atomic proof that the publication this tick froze is
                            still the one the pull request has -- git has nothing left to send, and the lease moves
                            to the head the branch is on NOW rather than the one an approval was measured against.
                            That write is skipped for a push that had nothing to SEND and finds the receipt naming
                            its commit with no debt beside it, which is a retry of a publication already settled; a
                            push that MOVED the pull request settles whenever a pair the route owes is not already
                            the value on the comment, since the receipt is never cleared and on its own reads a
                            branch pushed back onto an older published commit as a round nothing is left to close.
                            The exemption a rewrite earned rides that same write, staged by `late_rotation` and
                            asked whether or not anything else is owed, so a comment whose receipt already names the
                            commit still gets the move if the write that should have carried it was lost -- and
                            `late_transfer_telemetry` is asked past that write, so a move that really landed is the
                            only one reported
      late_accepted.py      the push an adjudication already accepted, taken with no measurement -- a verdict read
                            this exact diff and said it ships as one change -- but still named against the commit
                            that was DECIDED, still pinned to the head the reading was taken over, made only
                            over a checkout re-proved to be the one that verdict was reached about, and refused
                            outright where the publication ENDED in the meantime. This road reaches the transport
                            directly rather than through the gated call, so it makes that call's own barrier for
                            itself -- and the window is the widest any publication has, since the pull request was
                            last read by the reconciliation and the exemption, the identity, the debt, the park
                            persist and both checkout probes all run between that reading and the push
      late_collapse_state.py
                            immutable pre-squash values and durable head/base/count claims written before reset;
                            failed writes restore in-memory state, and handoff or proved rollback clears the claim
      late_squash_proof.py  prove the checkout still holds the squash, decide whether approval, receipt, generation,
                            or a changed checkout keeps it standing, and choose the receipt-proved retry lease
      late_rewrite.py       enter and publish a squash, with the switch governing measurement and every push retaining
                            its terminal barrier; hand the actual pre-squash pair to transfer, name a resumed candidate,
                            and drop abandoned approval, transfer permission, and collapse claim after proved rollback
      late_transfer_reading.py
                            pending permissions and operator authorization; a damaged claim cannot be overwritten
                            as a grant, and an existing grant must agree with this reading's fingerprint
      late_transfer_evidence.py
                            bounded rewrite kind, stage, endpoint, and publication evidence; frozen and recorded PRs
                            agree with the lease, with a rewritten remote tip admitted only by its pending permission
      late_transfer_checkout.py
                            fresh clean-checkout, lease-object, unchanged-owner, and remote-backed base proofs;
                            an observed close, control label, relabel, or unprovable base refuses the transfer
      late_transfer_contribution.py
                            immutable permit results and fingerprints of accepted, claimed, and rewritten pairs;
                            the recorded adjudication reproduces locally and every claimed contribution agrees
      late_transfer.py      ask evidence and live-proof questions in order, then grant and persist the permission with
                            its publication debt; restore failed writes and abandon a permission after proved rollback
      late_rotation.py      what the receipt of that landed push does with the permission behind it, staged into the
                            push tail's own write so the exemption, the identity it carries, the phase that spends
                            the permission, the account of what the remote holds, and the bookkeeping the landing
                            closes land together or not at all. What licenses the move is the PERMIT `late_transfer`
                            re-asked on this tick, handed down the tail beside the commit it proved out for, and not
                            the permission on the comment: a refusal there is not a hold, so the rewritten commit
                            falls through to the ordinary cumulative gate and a count under the ceiling publishes the
                            same commit -- a settlement reading the record alone would rotate a human's verdict onto
                            a rewrite nothing revalidated and write the very digest the permit declined. A permission
                            no permit vouched for is therefore left exactly where it stands, neither spent nor
                            dropped, since the remote is now on a head the permit accounts for and a later tick whose
                            refusal has cleared can settle it. A permission naming the commit that just landed, where
                            this tick's permit proved out for it, is
                            SPENT -- the verdict moves onto it, since the pull request really carries it now -- and
                            the record says which of the two readings proved that: a leased force-push that moved
                            the publication off the head the permit was granted against, or the leased no-op a
                            recovery makes over a pull request a tick that pushed and died had already left it
                            standing on. There is no third, since a remote anywhere else is a permit `late_transfer`
                            refused and a reading that could not be taken refuses the same way -- neither is read as
                            equivalence, and neither is ever pushed for unleased. A permission the publication went
                            PAST is dropped instead, on the rollback's own terms (an outstanding record this build
                            can vouch for entirely), since the head it was granted against is gone and what is left
                            is a claim about a push that cannot happen. What it stages is the transition and not
                            what is said about it: the rewrite a verdict moved onto and the reading that proved the
                            publication ride the answer, and the record is the telemetry owner's below
      late_transfer_telemetry.py
                            the one record a settled transfer leaves on both sinks -- one `late_transfer` event
                            naming both pairs, the pull request, the rewrite kind, and which reading proved the
                            push, correlated by a generation minted from what the pinned comment already says, since
                            a transfer runs past the retirement that dropped the pair it was adjudicated under.
                            Called by `late_push` on the far side of the write `late_rotation` stages into rather
                            than by that owner, so the ordering is a property of the call site: a receipt GitHub
                            refuses ends the tick and reports nothing, and a rotation that moved no verdict -- a
                            permission left standing, one the publication went past -- says nothing either.
                            Deliberately no second `late_verdict` beside it, which would read as a second
                            adjudication of work nobody was asked about twice. The proof the settlement kept for
                            this record is dropped by this owner's own write, ordered after it: a comment still
                            carrying one MEANS a report is owed, so left standing it would say a settled transfer
                            had never been announced. A drop GitHub refuses is logged and walked past, since the
                            record has been made and a later tick may make it again
      late_terminal.py      whether the work a late record still owes a push for has already ended, asked ahead of
                            every road the reconciliation takes because all of them publish while the terminal that
                            drains such work runs inside the stage handler behind it. Two facts, since an issue's
                            own flag shows one of them: the OBJECT the tick opened with, and the PULL REQUEST the
                            record names -- a merge leaves the issue open until a stage terminal reads it, and the
                            gate below refuses to freeze an entry against either ending, so the road would
                            otherwise park a human over a publication that is finished. Read fail-OPEN, so a remote
                            that would not answer falls through to the road that parks with the reason it fails
                            for; the same fact immediately before a PUSH is `late_publication`'s and is read the
                            other way round, since what falling through costs there is a branch nothing can put
                            back. Asked behind the caller's record questions rather than at its door, because the
                            pull-request half is a request and this runs ahead of every stage on every poll
      late_reconcile.py     the reading the dispatcher takes for a pair frozen and never counted, scoped to the
                            stage the record names and taken with no run behind it: measured at or under the ceiling
                            the candidate is PUBLISHED before the stage runs -- nothing goes back for a push a
                            settled reading left owed, and the stage behind an unpublished one spawns a reviewer over
                            a pull request that never received it -- measured past the ceiling the issue is routed to
                            the adjudication, and a refusal parks. So does a push that was allowed and did not land.
                            An approval with no generation left behind it is the same window one step on, and
                            `late_debt` beside this answers it.
                            Both roads end in a PUSH, so work that is already OVER is handed back ahead of either,
                            which `late_terminal` answers and this owner only places: behind the three record
                            questions, since the pull-request half is a request and the only ticks its answer can
                            change are the ones with something left to reconcile.
                            It stops the tick outright where the checkout that pair names is not on this host and
                            where the label has left the stage the pair was frozen on, since neither a re-entry nor
                            the handler is this process's to pick -- and it retires its own measurement park on a
                            record whose split has settled, which is a group with no count that owes no reading
      late_claims.py        what a post-publication record claims and what it cannot produce: whether a live one
                            still owes its count, and -- ahead of both reconciliations -- the four refusals a record
                            that cannot make a claim whole earns. Read off the RAW fields, because the parse is what
                            loses them: a group missing one member comes back as no group, an approval missing its
                            lease as no approval, a frozen field the comment CARRIES and no reader will type as a
                            field nothing froze, and a spend group with one unusable member as no bookkeeping at all
                            -- so every question behind them answers "nothing owed" and the stage runs over a claim
                            nothing can check, while the freeze quietly re-derives the half it cannot see from a
                            remote that has moved. A field the comment does NOT carry is the same gap: what the
                            write that mints a generation puts down in one go is required rather than merely checked
                            when present, and a base is required beside any count, since a number is taken over a
                            pair. All four claims on the five stages the transition graph's own set names, since
                            `workflow:implementing` has an edge to the adjudication too and its approval carries no
                            head by design; `workflow:decomposing` is asked the publication one ALONE, because that
                            group is what a settlement decides everything by and cannot re-derive, while a verdict
                            taken before publication approves its commit with no head to pin it against -- the very
                            half-written pair the approval claim calls damage
      late_debt.py          the approval the dispatcher pays ahead of every handler, where a crash past the write
                            that granted one left no generation to reconcile from: that write retires the record
                            before the push, deliberately, so what is left names a commit the pull request never
                            received and nothing under the stage reads it. Paid under the id the gate decided about
                            and the head it decided against, both of which live only on the approval by then --
                            and only from a checkout still standing on that commit. One that is absent, unreadable,
                            or standing elsewhere PARKS rather than standing down: the debt says a commit the pull
                            request does not carry was allowed to join it, so a handler behind any of those reads a
                            publication the approved work is not on. A push that LANDS closes what its caller never
                            got to -- the route bookkeeping the approval carried past its own retirement, and the
                            transient park that failed push left -- since no tick behind this one can, and one that
                            misses again leaves both alone and says nothing: a second mention is one nobody can
                            answer any faster, and a rewritten reason turns a park the stage recoveries retry into
                            one only a human clears. The commit is read ONCE and named to the gate,
                            so the proof that the checkout is standing on it and the reading the gate takes behind
                            it are about one approval: a commit landing between the two is refused rather than
                            measured, pushed, and receipted while the debt it was granted for is dropped as paid.
                            A branch some owner deliberately moved off that commit never reaches here -- the auto
                            rebase's own reset drops the approval it abandons. Payable only from the five stages the
                            transition graph's own predicate names, rather than from every label with an edge to the
                            adjudication -- `ready`, `blocked`, and `umbrella` each have one for reasons of their
                            own, none of them a pull request -- and a debt whose label has moved to one of those
                            stops the tick rather than being ignored, since the stage behind it would run over a
                            publication the approved commit never reached
      late_gate_models.py   frozen gate calls, publication provenance, caller-owned route spending, and gate verdicts;
                            publication ids distinguish absence from damaged claims, and the close latch stays shared
      late_identity_reading.py
                            retained measurement misses, inherited root/depth, and generation identity validation;
                            unreadable or foreign records cannot supply a reportable identity
      late_records.py       gate construction and candidate-generation minting; identities advance durably, the frozen
                            candidate owns its spent readings, and existing publication context is retained
      late_freeze_guards.py reject missing measurement fields and foreign identities before a retained pair is used;
                            an unfinished base permits only that field to remain absent, preserving its original ceiling
      late_freeze.py        prove the candidate, freeze or recover its exact base, and account for failed base reads;
                            refuse a head differing from the caller's commit or a reconciling tick's record, and
                            recover retained bases by object identity
      late_evidence.py      what a recovery proves before it acts: the checkout, both recorded objects, a
                            head that is still the candidate, and a head that is still the commit an approval
                            owes a publication for -- proved ahead of every spawn
      late_verdict_retirement.py
                            retire the generation inside the observation window; a close before or inside its write
                            leaves a durable cancelled cycle for cleanup, including reinstatement after retirement
      late_verdict_debt.py  keep unmeasured candidate, lease, basis, and route spends together; stage debt with a
                            transfer or persist it before publication, drop superseded approvals, and spend the
                            caller's owed fields before routing
      late_verdict.py       approve accepted or authorized work, route oversized work with its unpublished notice,
                            retire answered parks, and coordinate generation retirement with route and publication debt
      late_approval_reading.py
                            whole candidate/lease/basis approval reads and explicit operator-backed bases; damaged
                            and legacy bases remain distinct from known permissions
      late_approval_state.py
                            coordinated approval writes, preservation of an existing candidate's basis, and debt
                            retirement together with its owed route spends
      late_publication_state.py
                            exact commit, lease, and PR receipt reads and writes; the recorded issue pointer stays
                            distinct, and recovery receipts must match the attempt's head and publication
      late_receipt_damage.py
                            whole-receipt validation, distinguishing absent or empty records from missing members,
                            unparseable claims, and nonempty receipts lacking a commit or publication
      late_measurement_state.py
                            notice ownership and quiet transport-retry coordinates, including held parks; reaching
                            the base clears misses and a completed measurement also clears its failure
      late_park_retirement.py
                            targeted retirement of measurement, authorization, and settled-split parks, and explicit
                            supersession of the current wait; unrelated park reasons remain standing
      late_park_state.py    persist generations and route spends, retire a measurement park bound to another candidate,
                            and consume a held authorization's command watermark monotonically
      late_park_notices.py  operational failure descriptions, stage-attributed events, and measurement park notices;
                            the failure is emitted before the wait is recorded
      late_measurement_reply.py
                            trusted bare-continue batches reserved for the active measurement park; mixed feedback
                            stays with its stage and the current reason and wait must agree
      late_parks.py         quiet transport retries and announce-once measurement failure handling; changed frozen bases
                            remain durable during a quiet repeat, and a different failure earns its own notice;
                            an unreadable candidate retains its resolved object id for recovery
      publication.py        the push -- named against the commit the gate decided and pinned to the head the
                            answer that admitted it was about: a published approval's frozen head where there is
                            one, and the CANDIDATE itself where the gate admitted it because its pull request is
                            already standing on it, since a lease the transport reads for itself adopts whatever
                            tip somebody moved to in the window and force-pushes over it -- work that ENDED
                            refused immediately before that push, which `push_barrier` beside this owns -- the
                            pull
                            request opened or reused for it, which is that same pull request by NUMBER on the
                            delivered road and never a second one where it closed in between, and the commit the
                            push carried (decided once ahead of the push --
                            the one that passed the gate, or the checkout's own head where the switch named none
                            -- and made durable there, with a checkout that can name none at all publishing
                            nothing), with the handoff below reached last -- held back until the checkout has
                            been proved on both sides of the push, since the worktree is writable while those
                            requests run -- and spending the record of that commit once the handoff it was owed
                            lands
      push_barrier.py       what may have ended between this tick's readings and the push it is about, asked
                            immediately before the transport and nowhere else: everything above spends a run, a
                            reading or a proof, and each is time a poll on another worker can find the world
                            changing under. Two endings -- a close a poll LATCHED, which the issue object cannot
                            give since it is the snapshot the tick opened with, and the pull request this push
                            would JOIN, which is the one the gate proved where it proved one and otherwise the one
                            the RECORD names: reuse is a lookup by branch, so one that ended in the window answers
                            nothing to it, a second pull request is opened over the work, and `pr_number` is
                            overwritten with it. The pull request is read first and the latch last, since the
                            reading is a request and a close landing while it is in flight is one only an answer
                            taken after it can still give. One ending is not an ending for this push and is the
                            reason this is an owner rather than an open-state check: a `discussion` plan the humans
                            SETTLED is an agreement rather than a delivery -- the stage ahead lets such a tick
                            carry on for the same reason, since finalizing on it would close the issue `done` with
                            no developer having run -- and what it licenses is an implementation with a pull
                            request of its own. Told apart by the two records the stage's own terminals use, read
                            off the same reading rather than a second fetch, and never offered to a number that
                            came from a proof, which no plan publication can produce. A record that NAMES a pull
                            request and cannot produce one is the third answer and refuses outright: absent is an
                            issue that has published nothing, which this seam's own first push is for, while a
                            field that will not type is the record disagreeing with itself and read as an absence
                            would buy exactly the push this owner withholds. Refusing writes nothing
      checkout_guards.py    the proof that the worktree is still the thing that was measured, asked of the
                            commit AND of the tree because work can appear beside a commit without moving it:
                            a head that has left the approved commit, and a tree that cannot be proved to carry
                            nothing, refused before the push -- where nothing is published and the commit stays
                            where the developer left it -- and refused again once the pull request is open,
                            where the publication stands and only the handoff stops so review never reads the
                            descendant; every one of them parked under the one reason a moved checkout earns,
                            named after the commit to go back to or the paths to clear, and settled by the
                            worktree rather than by a reply. The moved-head refusal writes the whole approval
                            group as it parks, through the same owner the publication mints one with: it stands
                            exactly where that publication would have recorded the debt this seam owes, so a
                            candidate a receipt or an exemption admitted would otherwise be parked as a commit
                            with no account of what its push rests on
      checkout_recovery.py  whether the checkout is the commit that was decided about, on the two parks that
                            turn on it. What a handoff refused for its checkout waits to see back is the only
                            park in this stage settled by a worktree rather than by a reply: the commit the
                            size gate approved under the checkout's own head, with a provably clean tree
                            around it -- both halves, since a proof narrower than the refusal it answers would
                            republish straight into that refusal again -- read off the commit the park wrote
                            down, on every ordinary tick rather than on a command, and silently, so an
                            operator who leaves the checkout where it is is not told the same thing once a
                            poll. The authorization park asks the same question one field over and is told WHY
                            rather than yes: what the seam past it measures is whatever the checkout is
                            standing on, so a head that has moved is a candidate the exemption does not cover
                            and the override does not name -- the policy's door closed, the ordinary road
                            measuring it, and a commit nobody authorized pushed under a command that named a
                            different one. Which commit that park is about is read off the record rather than
                            off an approval, the recorded override first since it is the terms a human agreed
                            to and it outlives the generation a failed publication retires, and a record
                            naming no commit at all held rather than published under
      dev_pr.py             what that pull request says and whose work it says it carries: the title taken from
                            the branch's own first commit subject, falling back to a prefix inferred from recent
                            base history so it reads like the repository it lands in; the body pairing the
                            `Resolves #N` that closes the issue with the dev session the branch was written by
                            and the run's closing message, cut on a paragraph, line, or word boundary and marked
                            as clipped where it outgrows the cap, with a fence the cut left open closed first;
                            and the reuse of whatever is already open on the branch, which `find_open_pr`
                            promises nothing else about -- one whose body already names this session is adopted
                            as it stands, human annotations included, and one that does not (an operator's, or
                            the `discussion` stage's plan PR sitting on the very ref the dev commits went to) is
                            re-bodied to the implementation's. One road names its pull request instead and may
                            OPEN none: a publication the gate admitted because that pull request already carries
                            the commit is finishing bookkeeping rather than publishing, so it is resolved by
                            number and re-read WHOLE -- open, in this repository, on the branch the push named,
                            and standing on the commit it sent, off one fetch and against the object handed on,
                            since what this writes is a receipt naming that commit and a relabel handing a
                            reviewer that pull request. One somebody closed OR MOVED between the gate's proof and
                            here holds the tick rather than earning a second pull request over the same work or a
                            receipt naming work the branch no longer carries
      handoff.py            the one write and the one relabel a finished publication is handed on by: the pull
                            request and the branch recorded together, since a state that arrived without a
                            branch would leave the next tick resolving the legacy name while the live pull
                            request sits on the slug-namespaced one; the plan SHA, the certified baseline, the
                            handoff anchor, the pair an authorization handoff carries while it is still in
                            flight -- which a poll finding them would read as a call into the seam that never
                            came back, and put a spent park back over an issue bounced here later -- and the
                            commit an approval said was still owed a push all spent
                            beside them; the reading that handoff staged CONSUMED rather than dropped, since two
                            of the seam's roads publish without reading the thread at all and the reply that
                            ended the park would cross this line unread, to be taken for fresh feedback on the
                            stage it lands in; the review round, the retry budget, the granted attempts, the
                            silent-park streak, and the timeout watermark all reset, since the issue moved
                            forward and any of them left behind would mis-fire a later hop back into
                            implementing -- and every one of those written durably AHEAD of the
                            `workflow:validating` label, so nothing this line spends is stranded on an issue
                            that has moved on and a relabel that fails leaves the branch recognizable
      park_watermarks.py    advance past the unbroken run of comments claimed by the orchestrator id ledger, stopping at
                            the first unclaimed reply; only an unavailable ledger update or prior watermark uses the tip
      checkout_parks.py     dirty and unreadable checkout refusals, operator messages, and staged park events; both retain
                            the work and use the shared watermark reader after posting their notice
      parks.py              classify session limits, transient provider failures, real questions, and silent exits;
                            retryable failures keep their reason and streak, while a question clears both
      drift.py              a body edit mid-implementation: the resume it earns -- withheld while a continuation
                            has bought an attempt, since a resume passes no gate and the attempt is owed as a fresh
                            spawn -- and the `ACK:` that answers it
      drift_preflight.py    a pre-session edit and the quiet timeout recovery
      continue_command.py   `/orchestrator continue` on a parked issue, opening with the one park below that the
                            classifier here would refuse the right command on, and handing back outright a
                            batch the measurement park's own road would re-measure on: this read comes after
                            that road looked at the thread, so a command landing between the two is in this
                            batch and in nobody else's -- and classified here it is a continue on a park
                            needing real guidance, refused and consumed past the refusal, with the reading its
                            author asked for one nothing will ever take
      retry_cap.py          the same standing park on this stage's road, held against the three that would read it
                            as an ordinary one -- the continue classifier, the drift check, and the resume -- so the
                            tick ends having written, spawned, and said nothing, and the pinned session, the pull
                            request, an approval's unpushed commit, and the late record stay as they were. The
                            refusal it still records, the sentence it waits to have said before any thread is read
                            for an answer, and the trusted `/orchestrator continue` -- looked for anywhere in the
                            unread batch, taken with whatever else its comment carries -- that retires the session
                            and renews the budget for exactly one spawn, written down before the spawn it pays for
      read_only_relabel.py  the `question` / `discussion` relabel screen: which park it answers for, and the
                            acceptance write that retires the conversation's records and hands its round anchor
                            on as the floor the dev run is measured against
      relabel_hazard.py     what a relabeled issue's branch and checkout are carrying, with every reading that
                            convicts reported together so one refusal names all of it
      relabel_evidence.py   what those readings have grounds to vouch for a tip sitting on -- the tip the round
                            opened on, the head the plan PR is on, and the ahead-of-base question a merged plan
                            takes back
      relabel_refusal.py    the idempotent `<stage>_unsafe_relabel` park a finding earns, and the remediation
                            aimed at the tip worth keeping
      plan_reading.py       what the recorded plan PR carries and where that leaves the branch, read afresh by
                            both halves rather than remembered
      plan_handoff.py       the reconcile that keeps an accepted plan handoff in step with its PR until a
                            developer commits, and the marker that makes its own re-anchor recoverable
      models.py             the frozen records the owners hand each other
      state.py              the pinned-state keys and CLI marker tuples they share, and the two retry bounds
                            beside them: the silent parks a session survives, and the readings one frozen pair
                            may lose
    in_review/              `in_review`
      handler.py            the order one tick asks its questions in, and the missing-`pr_number` park asked before
                            the rest
      feedback.py           the four surfaces scanned before the drift check, their author filters, and the park that
                            stays silent for the base-sync retry loop
      fixing_route.py       the pending-fix bookmarks, the hash refresh, and the `workflow:fixing` relabel
      drift.py              a body edit on an open PR: the unread PR conversation captured first, the dev resume, and
                            the `workflow:validating` return
      merge_gate.py         the unmergeable park and the one HITL ready-ping an approved, unvetoed head earns per head
                            SHA
      watermarks.py         the one-way issue-side ratchet and the legacy seed a manually-relabeled issue needs
      models.py             the per-tick handles and the drift-resume record
      state.py              the issue-side watermark key they share
    question/               `question`
      handler.py            the order one tick asks its questions in, the closed-issue finalize that outranks them,
                            and both worktree teardowns
      run.py                the resume and fresh-spawn routes, the tracked spawn they share, and the park funnel every
                            exit lands on
      session.py            the locked question-agent identity, the trusted-reply consume, and both prompt builders
      outcomes.py           the read-only violations checked before any answer, and the park each outcome earns
      models.py             the tick record, the locked session, and the outcome
      state.py              the park reasons and pinned-state keys they share
    validating/             `workflow:validating`
      handler.py            the order one review tick asks its questions in, the terminals it opens with, and the
                            recorded-collapse route it asks behind only those, ahead of every route that could
                            point an agent at the branch
      reviewer.py           the round cap, the tracked reviewer spawn and its two refusals, and the verdict
                            fan-out, with the subject an approved verdict hands the squash tail built here over
                            this run's own checkout
      collapse.py           whether a squash this issue began and did not finish is answered before anything else
                            runs an agent, over the same tail the approval road runs -- what the branch is owed
                            does not depend on which reading sent the tick. Asked only from that road it would be
                            asked on no tick whose reviewer times out, crashes, or votes CHANGES_REQUESTED: an
                            already-landed collapse would never get its notice, its watermarks, or its relabel, a
                            record nothing can read would reach `fixing` without the park it owes, and a body edit
                            would resume the dev on a branch standing on a commit nobody accounted for. Presence
                            on the pinned comment is the whole test, so an issue with nothing recorded costs one
                            lookup; ABOVE the drift resume and the awaiting-human branch both, which is what makes
                            the park its own to answer -- its own refusals park under a durable `squash_failed`
                            and are retried every tick without a second mention, while a park the size gate worded
                            is held until the human replies and that reply is then spent on the recovery rather
                            than on the dev; and the checkout is READ where it is there and rebuilt only where
                            it is not, which is the one thing this route may not borrow from the reviewer road:
                            ensuring a worktree force-removes a checkout carrying no commits over its base, and
                            that is exactly what a collapse rewound and not yet recommitted looks like, with
                            every change it was about in the index -- which is why the subject the squash tail
                            decides over is built here, off that reading, rather than a layer down off the pieces.
                            The settled handoff is answered beside it and needs no checkout at all: the label
                            a finished squash never got to move is moved here, but only while the pull request is
                            still standing on the commit that handoff named
      approval.py           the verify gate and the squash-and-hand-off tail both roads run, over the subject and
                            branch whichever road decided them hands in: the optional squash, the park each of
                            its four readings earns, the notice its count is worded from --
                            posted ahead of the seed it orders, and the one failure that stops the road, since
                            the count lives only on the collapse record the next tick would otherwise drop -- the
                            end of that record, and the `workflow:documenting` relabel that lands behind that
                            write rather than ahead of it, with the commit the move is owed over left on the
                            comment across that boundary, so a relabel that does not land is the next tick's to
                            retry rather than the next reviewer's to re-review
      handoff.py            what that arc posts on the pull request and seeds after: the approval comment whose
                            failure is logged and walked past, and the in_review watermarks in two halves -- the
                            snapshot taken behind the caller's notice so the seed walk steps past the notice's own
                            id, abandoned outright on an unreadable PR rather than stranding an approved branch on
                            a read, and the ratchets reached past it, which is what each of the three watermarks
                            becomes against what is already persisted
      verify.py             how a non-ok verify result reads and the park it earns
      watermarks.py         the seed walk past leading orchestrator comments and the ratchet that never regresses one
      requested_changes.py  the PR feedback and `workflow:fixing`-labeled dev fix, plus the no-VERDICT park and
                            the split that tells a provider's failure from a reviewer's
      dev_fix.py            what a finished dev fix leaves behind: the no-commit reading and the head it carries
                            on, the size gate every fix route publishes through -- told the state the run really
                            belongs to, since the route that relabels before it spawns reads its own cached labels
                            back -- the push and the approval it spends, and the round bump
      stranded.py           the probe under that reading, which the `fixing` handler asks off no dev run at all:
                            a clean checkout fetched and proved strictly ahead of the remote pull request branch
                            and behind nothing, answering with the head it was compared AGAINST so the push that
                            follows is pinned to it -- and refusing, on a dirty tree, a failed fetch, an unreadable
                            divergence, or a remote that moved, because pushing over a head nobody reconciled is
                            worse than one more park
      awaiting.py           the three park-reason claims on a human reply and the dev attempt they fall through to
      awaiting_resume.py    the order those claims are asked in and the resume none of them wanted
      drift.py              a body edit mid-review, the three parks that defer, and the consumed-thread watermark
      drift_models.py       the frozen record that route's resume hands the helper that finishes it
      drift_outcomes.py     the `ACK:` reply that must not park, over the shared fix disposition
      recovery.py           the silent retry of a push race or dev timeout, both through the size gate -- the
                            timeout's commit is the one road to a published pull request nothing else measures --
                            the debt the push that lands pays, the held outcome that owes the caller no follow-up and
                            no relabel, and the one sentence a park that healed itself owes the thread
      rounds.py             the `review_round` a fix pays for on the one event `MAX_REVIEW_ROUNDS` counts -- a head
                            the reviewer has not seen reaching the pull request -- spent by the push that lands and
                            by the hold that sends the candidate to the adjudication, the held form handed to the
                            gate so the count is not lost to a crash in the relabel window
      models.py             the frozen records several owners in this stage hand each other -- a record one
                            route builds and reads alone stays beside that route instead
      state.py              the pinned-state keys, park reasons, and outcome tokens they share
```
