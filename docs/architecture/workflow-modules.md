# Workflow modules

This page maps `orchestrator/workflow/`: the package API, the state owner beside it, the `engine/` owners one tick is
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

- **The package API is six names.** Five are `workflow/state.py`'s own objects, re-exported and pinned by identity so
  the graph a caller reads cannot fork; the sixth is `tick`. In-tree callers name the owner, and the re-export is for
  callers outside the tree — `tests/workflow/test_imports.py`.
- **`tick` resolves the engine inside the call.** `github/` and `git/` import `workflow/state.py` for the label
  vocabulary they are typed by, and a submodule import runs this initializer first, so an engine import at module
  scope would send `github/labels.py` and `github/issues.py` back into the client they are still initializing.
  Importing the package therefore costs the initializer and the state owner, and pulls in neither the engine, the
  stage tree, nor the config, analytics, git, and GitHub graphs — `tests/workflow/test_imports.py` probes both import
  paths in a clean interpreter, and `tests/repository/test_layering.py` holds the direction under it.
- **The stage handlers are resolved at call time.** `engine/dispatch.py` pairs each label with the module its handler
  lives on and imports it when it dispatches, as `engine/pickup.py` does for the stage it starts an issue on: the
  stage tree imports `engine/`, so a module-scope bind would point that edge back at itself.
  `tests/workflow/engine/test_dispatch.py` pins that the handler is read off its owner per call rather than bound at
  import, and `tests/workflow/stages/test_imports.py` that every labelled target lands on a stage package here. The
  late size gate's own refusal is resolved the same way and for the same reason — it lives on a stage owner, so the
  dispatcher imports it when it routes.
- **Two operator log channels, spelled literally.** The engine, `late_split/`, and stage owners report on
  `orchestrator.workflow`, and `workflow/state.py` on `orchestrator.state_machine`. A module moved between packages
  does not take its channel with it — `tests/workflow/test_imports.py` walks the package and checks every owner that
  declares a logger.
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
workflow/                   publishes the two label vocabularies, `guard_transition` and `is_allowed_transition`,
                            `IllegalTransition`, and the per-repo `tick`
  state.py                  the `WorkflowLabel` / `ControlLabel` vocabularies, strict label coercion, the declared
                            transition graph and the guard over it -- including the one edge OUT of a terminal,
                            `done` to `rejected`, which the umbrella cancelled between its label write and its
                            close is corrected over -- the two predicates that read the graph's own stage sets
                            back, one for the states a candidate the remote already carries may be published from
                            and one for the states the per-tick base refresh drives, which is what the rewrite
                            record holds a kind and its stage to together -- and the `workflow:` namespace
                            boundary
  engine/                   what every stage is driven by
    agent_diagnostics.py    what a park comment and a WARNING say about a run that left no usable message: the
                            agent's stderr under two budgets -- 1KB for the human who came to the issue, 400
                            characters so a log line still fits a screen -- and the exit code beside the first.
                            The shared redactor runs over the RAW stderr before either trim, since a secret sliced
                            by the cut survives as a fragment the redactor no longer matches, and that fragment is
                            what leaks; the same ordering puts it ahead of the `rstrip`, so a multi-line env value
                            ending in a newline still matches verbatim. The block is quoted through
                            `messages.py`'s blockquote, so it reads as the last-message body it is appended under
    comments.py             the orchestrator marker, the capped id ledger both posters write, and the trusted-author
                            thread read every prompt quotes
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
    dispatch.py             one tick's pollable issues turned into handler calls: the observation a refused
                            fan-out submit was carrying -- latched from the poll's own closed reading and dropped
                            again only where the RECORD positively says there is nothing to end, since the probe
                            that asks is a request and a request can fail -- the same reading BOUND to an admitted
                            one instead, since the worker refetches and a reopen in that window would answer
                            differently -- the publication HOLD that postpones that drop, taken where the scheduler
                            ADMITS the submit and given back by the task it wrapped, since a poll refused in
                            between is refused precisely because a worker has the issue and the queue, the refetch
                            and the label checks are all window a dropped reading would never be seen through, with
                            one of its own taken over the handler this owner runs -- the only hold the sequential
                            path has -- the hard-skip filter a held close
                            observation outranks (it is not this tick's reading, so a park, a reopen, and a relabel
                            off the swept labels each leave it standing -- an owner the enumeration never yields is
                            added by number), the family /
                            fanout partition and its cap exemptions, the per-worker refetch and the sequential path's
                            own classify-and-refetch beside it (a CLOSED issue is routed by any of the four cleanup
                            labels, while only the two an adjudication RUNS under earn the refetch an OPEN issue
                            costs, since neither reading of one may be taken from the poll), the hold that keeps a
                            closed reading across the pass that would spend it -- a pass can fail to spend one
                            without failing at all -- the close latched by the ENUMERATION that read it AND
                            written down there, so a worker already holding the issue is answered for the whole
                            window between that reading and the submit that carries it and an accepted task that
                            never starts still leaves a receipt on the thread, the same observation taken at the
                            REFETCH by both paths that take one -- an issue open when it was listed and closed by
                            the time it is read carries a reading nothing else holds -- the record-driven pair
                            asked ahead of every handler (an authorized restart first, then the refusal a cancelled
                            cycle earns, since a restart between its label write and its retirement wears a
                            live-looking label over a record that still says cancelled), the unlabeled issue
                            that already carries a pinned comment and so is one this orchestrator has already
                            MET -- left where a human's label removal put it rather than greeted a second
                            time, since a second pinned comment is shadowed by the first from the moment it
                            is written while the finished workflow in that first one goes on deciding, the
                            park re-applied behind
                            the mark that reading was waived for, the cleanup submission
                            wrapped in the settlement its observation is owed -- kept by a pass that failed, by one
                            nothing ever called, and by one that RAN and left the ending owed under a label no
                            query asks for, settled everywhere else (a swept label reaches the owner on its own
                            cadence), and shared by all three tick paths
                            with the refetch inside the hold --
                            the refusal that keeps a relabelled late adjudication off every other
                            stage's handler, the reading owed for a size-gate pair frozen and never counted --
                            taken ahead of the handler that would otherwise run against a pull request still
                            standing where the gate froze it, and only on the stage the record itself names --
                            the hold an issue that has spent its whole lifetime agent-run allowance gets, taken
                            once here rather than taught to thirteen handlers because `awaiting_human` means a
                            different road on each of them and none of those buys back a run (it replays the
                            sentence the park still owes, since nothing below it runs to say one, it reads the
                            thread for the one trusted command that widens the ceiling -- which lets the tick go on
                            to the stage its label names, since the run a human just paid for is the one the issue
                            was stopped for -- and it is the one question here that steps aside for work that has
                            ENDED, whose handler is a terminal that ends the issue rather than a road that spends
                            anything on it: a closed ISSUE, which the object in hand already shows, and a recorded
                            PULL REQUEST that has merged or been closed, which it cannot -- a merge leaves the
                            issue open until a stage terminal reads it, and the three stages that drain both
                            endings at handler entry are behind this hold. That second reading is a request per
                            parked poll, fails OPEN so a remote that would not answer lifts nothing, and is read
                            against the LABEL the tick was routed on: a settled `discussion` plan is the agreement
                            that licensed the build, so it is carved out on `workflow:implementing` and nowhere
                            else -- `discussion` itself drains the same pull request through its own terminal)
                            -- and the timed dispatch
    observations.py         the closes a poll saw and could hand to no worker: the process-wide latch the run
                            holding the issue asks before every step the remote keeps (a close and a reopen inside
                            one of its own steps is the reading GitHub cannot give back), the settle a pass that
                            RAN takes -- which moves the per-owner generation with it -- the claim one receipt is
                            posted under, and the memo the attempt that landed a durable receipt writes against
                            the generation it was claimed at -- so a refused post is retried by the next poll
                            rather than lost, two polls in the check/post gap post once, and a settlement landing
                            mid-post leaves no memo to suppress the NEXT reading's receipt, and a receipt that
                            LANDS owes the thread walk again -- the window a worker
                            retiring a cycle holds across its own write, which is what
                            keeps a poll from calling a reading spent against a record whose cycle identity has
                            just come off, is the only place that cycle can still be read, and decides what it
                            observed as it CLOSES, under the lock that closes it, so no interval is left between
                            the answer and the exit for a poll to latch a close in; the HOLD a worker has on an
                            issue, under which a settle is postponed rather than taken -- the drop rule reads
                            "nothing to end" off the late cycle, and every publication the push barriers guard
                            carries none, so without it a poll would drop the very reading a worker is about to ask
                            for -- taken where the CLAIM is, which is the scheduler admitting the submit rather
                            than wherever the worker first reads something, since the queue, the refetch and the
                            label checks all sit in between and a poll refused in there is refused precisely
                            because a worker has the issue; counted, so the dispatch's own hold over its handler
                            nests inside the claim's and the sequential path has that one alone; and the drop taken
                            again as the last hold goes, so nothing is held over an issue somebody reopens; and the
                            once-per-owner-per-process claim that bounds the thread scan recovering an observation
                            a DEAD process was holding, held for the length of the walk and handed back where it
                            raised
    drift.py                the user-content hash and the eight filters that keep content nobody wrote out of it --
                            the three whole-comment operator commands among them, since answering one edits nothing
                            and the tick that answers it hands the same issue on to a stage handler -- the dev
                            resume a drift earns, and the decomposition reset the pre-implementation route takes
                            -- manifest, session, and every claim that manifest made about the children it created
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
    prompts.py              the prompt builders the stages share, the header, notes, and placeholders they are
                            assembled from, and the single-decision comment
    retry_budget.py         the per-issue daily spawn budget every stage's gate is decided by: the decision it
                            answers and posts nothing for, the parking form that composes the tail around it for
                            the stages whose park carries nothing of their own,
                            the durable `retry_cap` park and the stage that ran out,
                            the sentence that park owes the thread until the thread is shown to carry it -- and the
                            replay that says it at stage entry, since a park routes the tick past the gate that
                            took it -- the one bounded renewal, whether an attempt it granted is still owed, which
                            is what tells a stage's other roads to an agent to stand down for the gate, and the
                            four audit phases over them. The late adjudication is decided by the same gate and
                            renewed by the same step, and owns its park's delivery itself, since what a refusal
                            leaves standing there is a generation's whole record
    run_budget.py           the one record every agent-run budget transition leaves on both observability sinks:
                            the `agent_run_budget` family, its four durable phases -- a charge reserved, the spawn
                            it paid for, the lifetime a refusal ended, and the ceiling a command widened -- the
                            launch identity a charge is taken under and the id a record correlates on -- the bounded
                            head of that identity and the count the charge moved, since the identity alone repeats
                            across charges -- the whole ledger reading every phase repeats (the configured ceiling,
                            the allowance in force, the runs spent, and what is left of them, spelled out as a word
                            where nothing bounds them rather than dropped), the closed vocabulary a refusal explains
                            itself from, and the
                            two guarded writes that reach the audit and analytics streams without either being
                            able to cost the other or the tick -- along with the one guarded read that builds a
                            record, since an extension's stage is asked past the write that widened the ceiling.
                            It decides nothing and is asked only once a transition is durable, so what the stream
                            counts is what an issue actually spent
    run_circuit.py          the charge one launch takes at the boundary a process is invoked from: the launch
                            identity a request is fingerprinted under, the two durable writes the crash window
                            lives between -- `reserved` before anything is invoked, `started` before the
                            invocation -- the standing charge only the launch that took it may reuse, the fresh
                            durable read the pair is written onto, the merge that carries back its own fields and
                            nothing the caller staged, and the interrupted answer every refusal returns. The park
                            below is taken here, on the reading the refusal was made on, and no process is invoked
                            unless the charge landed. Each of the three durable steps is recorded to both sinks
                            through `run_budget.py` and recorded AFTER the write that takes it, so a reused charge
                            reports only the spawn it paid for and a refused write reports nothing
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
    run_ledger.py           the lifetime agent-run ledger one issue is read against: the allowance in force -- the
                            issue's own where it carries one, the configured ceiling everywhere else -- the
                            monotonic count of runs it has spent, seeded and floored by the legacy `issue_agent_runs`
                            meter and kept running while the ceiling is off, the `reserved` / `started` phases of the
                            launch currently holding a charge and the fingerprint naming which launch that is, the
                            typed snapshot carrying what is left of the allowance and whether the charge standing on
                            it is this launch's, and the two fields an issue-state projection keeps of the group. It
                            decides nothing and posts nothing: what to do about a spent ledger is the reader's
    run_limit.py            what a spent lifetime ledger leaves: the durable `agent_run_limit` park, the sentence it
                            owes the thread scoped to the exhaustion that minted it -- the allowance in force and
                            the runs spent against it, so a notice quoting numbers the issue has moved off is
                            replaced rather than said -- the persist-before-post composition that takes the park and
                            says it once, the reconciliation that reads a bot-authored notice back off the thread
                            before repeating it, the replay the dispatcher's hold makes when nothing ever said it,
                            and the five audit phases over them -- the two the command beside it ends on included.
                            The moment the park is TAKEN goes to the shared budget stream instead, once per park and
                            on the write that makes it durable, carrying the launch the ceiling stopped.
                            Nothing here decides an issue is out: the ledger reading is handed in, so the park
                            quotes the numbers the refusal was made on
    terminals.py            the merged, rejected, and human-closed arcs, the stamp / receipt / label / write tail they
                            share, and the entry-time finalizers. The stages carrying no PR-state arc of their own
                            ask for both pull-request endings off ONE guarded reading -- a merge, and a close
                            nobody merged, which leaves the ISSUE open so the closed-issue arc behind it sees
                            nothing while the stage measures and pushes onto a pull request that is gone or spawns
                            over work a human rejected. One reading rather than a fetch each, because two fetches
                            are two moments: a merge landing between them answers open to the first and merged to
                            the second, which the close arc is right to ignore, and the stage runs anyway. A fetch
                            that FAILED falls through, since nothing about it says which ending it was hiding
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
    usage.py                the tracked agent run: the request model, the launch fingerprint taken off it and the
                            stage / role identity a charge is recorded under,
                            the required budget every caller names the issue and its pinned state through, the circuit
                            the sole low-level spawn is gated on, the audit spawn / exit pair, the analytics record,
                            the `skill_triggered` emission, and the per-issue counters a terminal receipt is read off
  late_split/               the late size gate's own domain: what one generation IS, apart from anything that drives
                            one
    formats.py              what any late value has to look like -- a real integer, a git object id, a bounded
                            single-line value, where one line is asked as the split every reader on the far side
                            breaks on rather than as a search for one character -- the reducer that shapes a raw
                            diagnostic into what that last predicate accepts, so the one free-text field a record
                            carries is bounded by the rule that guards it, and the one refusal every owner raises
                            over any of them
    models.py               the phase / verdict / failure / resource vocabularies, the boundaries a split
                            transaction owns among them, the frozen generation record with the transforms that
                            return a new one -- including the boundary move that refuses to rewind out of one of
                            those, which is the rule every retry above the transaction is held to, the record of
                            a reading that did NOT happen, which is on the generation because a fresh process
                            remembers no miss and is scoped to the frozen pair beside it, and the
                            post-publication entry no record carries unless it can name the stage, the pull
                            request, and the head at once, the answer that tells a candidate already made into
                            children from one nobody counted -- and the lineage bound it is read against
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
    lineage.py              what a child born of a split inherits and reads back fail-closed: the lineage it
                            continues, the adjudication that created it, the snapshot ref and exact commit it may
                            reuse, and the slice it owns -- plus the two markers that claim a lineage outside the
                            pinned comment, the receipt the transaction stamps into a child's body and the one a
                            reclamation leaves on its thread, and the reader that turns the first back into a
                            lineage when the pinned write that would have recorded one never landed
    exemption.py            the one commit an accepted candidate publishes under, and the semantic identity of what
                            that commit contributes beside it -- the frozen pair it was adjudicated between, the
                            canonical digest of the contribution between them, and the version that digest was taken
                            under. Both written, read, and compared fail-closed and deliberately outside the group a
                            cleared generation drops; the identity is read whole or not at all, so a missing or
                            damaged member, a candidate that is not the exempt commit, a version this build does not
                            compute, and a comment older than the group each transfer nothing while the exact-SHA
                            exemption goes on answering for the commit it names. The group belongs to the commit on
                            the field beside it, so a write that moves that field to another commit takes the
                            identity with it -- and one that re-records the same commit keeps it, which is what a
                            settlement resumed between that write and its handoff is standing on
    rewrites.py             what authorizes that exemption to MOVE onto the commit a workflow rewrite replaced the
                            accepted one with: the bounded rewrite kind, both pre- and post-rewrite pairs, the
                            digest they were granted equal on and the scheme it was taken under, the publication
                            the rewrite was made against, and the phase the transfer stands at. Written BEFORE the
                            push it licenses and moving nothing -- the exemption stays on the commit a human ruled
                            on, since the object the rewrite produced is on no remote yet and a verdict rotated
                            onto it there would be stranded by a push that failed. What SPENDS a permission is
                            `record_rewrite_publication`, staged into the write that receipts the landed push: the
                            exemption, the identity beside it, the operator authorization that made that exemption
                            a bypass, and the phase move to `published` in one statement,
                            since a reader is entitled to find them agreeing. Both writes live here rather than at
                            the seam that decides, so the reader is the writer's own gate -- a publication is
                            recorded only over a permission this build can read back whole and still finds
                            outstanding, and every other record is refused rather than repaired. The phase is what
                            binds the group to the exemption -- the accepted end while `authorized`, the rewritten
                            one once `published` -- and what a rollback reads, since only an `authorized`
                            permission may be dropped when a refused force-push resets the branch back onto the
                            commit the exemption never left. Read whole or not at all, so a missing member, a kind
                            or a phase this build cannot account for, a stage that does not make the kind recorded
                            beside it, and a bound end the exemption does not name each authorize nothing. The
                            kind and the stage are held TOGETHER, on the one predicate the reader and the writer
                            share (`entered_from`): each is a value this build knows, and only the pair says
                            whether the record describes a rewrite anything here produced -- a `conflict_rebase`
                            against `validating`, or a `squash` against `resolving_conflict`, types in both halves
                            and names a rewrite that stage does not make. Each kind is held to the stages its own
                            producer names: the squash to `validating`, where the approval handoff makes one
                            before it relabels; the `conflict_rebase` to `resolving_conflict`, whose owner spells
                            that label itself; and the `auto_clean_rebase` to the four the base refresh drives,
                            since what its evidence names is whichever of them the issue was on when the base
                            moved
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
      divergence.py         the park a behind-base worktree earns, the two leases that excuse it -- a head
                            validated as orchestrator-produced, and a divergence this stage's own replay record
                            accounts for, which is the shape every real rebase leaves since the head it replayed
                            stops being an ancestor -- and the crash-recovered push -- measured by the size gate
                            first, since a crash between a commit and the gate is the window this recovery exists
                            for, named against the head this stage read, which is the commit the round it finishes
                            is recorded under, and PINNED to the tip the divergence reading was taken against,
                            since "ahead and not behind" is a claim about that one commit and an unpinned push
                            would have the gate adopt whatever the pull request moved to in between; a push
                            neither the exceptional lease nor that tip can name refuses (`unpinnable_recovery`)
                            rather than letting git read the remote for itself. The behind-base probe is taken
                            BEFORE that push, since the reading is the same either side of one and taken first it
                            says which round a held candidate would owe: on base the push completes a round of its
                            own and leaves the receipt for it, behind base it is the preamble to a rebase that
                            owns the round instead. The rewrite it hands the gate is READ rather than probed: the
                            commits it finds are whatever an earlier tick left, and nothing off the branch says
                            which -- a replay that tick ran, a resolution its agent authored, or the unpushed fix
                            commits the `fixing` drift reroute sends over, which it does on base as readily as
                            behind it. So it is answered from the `conflict_replay_*` record a rebase wrote about
                            itself, and only where that record is about the publication and the commit in hand --
                            the pull request it names is the one this issue still records, the head it names is
                            the one this push is leased against, and the commit it names is the one the checkout
                            is standing on. Past the grant the PERMISSION takes over, which the gate falls back to
                            and re-asks in full. The commit the push publishes is NAMED on both roads and a head
                            nothing could read refuses on both -- unnamed, the gate measures and pushes whatever
                            landed between this owner's reading and its own -- while only what the push owes turns
                            on the behind-base count. The tree is PROVED clean rather than asked for its paths,
                            since a status that established nothing names none either and the gate's own proof is
                            part of a measurement `DECOMPOSE=off` never takes
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
      evidence.py           what a clean rebase tells the size gate it replaced, and the record it leaves so a
                            later tick can be told the same thing. The evidence is the pair the replay came FROM
                            -- the head the pull request was standing on, which is also the head the force-push is
                            leased against, since a rebase runs only over a checkout proved in sync with its
                            remote -- and the pair it went TO, over the fork point the branch left the base at
                            now. One caller builds it from a reading of its own, and no other can, because no
                            other knows what the commit it is publishing IS: every other push here carries a
                            commit somebody else made. So the replay also WRITES ITSELF DOWN, in the two steps its
                            shape forces -- the head, its fork point, and the pull request it is being made
                            against before the rebase destroys the first two, then the commit it produced before
                            the gate is entered -- and the group is read twice on the tick that finds the replayed
                            commit unpushed. The divergence guard asks it first, since a replay leaves the branch
                            ahead of its publication AND behind it -- the shape a stale checkout carrying somebody
                            else's commit also has, which this stage parks -- so a record naming that head, that
                            commit and that pull request is what tells the two apart and leases the force-push to
                            the pre-rebase head; the recovery then reads it again for the evidence it hands the
                            gate, rather than probing the branch. The pull request is on it because `pr_number` is
                            a field a later tick can find repointed, and a replay read against whichever one the
                            issue records THEN is a rewrite offered about a publication it was never made against.
                            The stamped commit is what makes a stale group inert: one naming a commit the checkout
                            is not on describes a replay that is not in hand. Both writes are spent only for a
                            branch standing on the commit this issue exempts. It grants nothing: a replay that
                            moved a byte fingerprints to another contribution and is measured like any other
                            candidate. An end nothing could name presents no evidence at all rather than a claim
                            with a hole in it
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
      transitions.py        the park-and-write pair, the unreadable-head park the rebase and the body-edit resume
                            share, the one predicate that says whether a standing park is a PERSON's -- which the
                            same pair reads, so a transient refusal taken over a question records nothing and
                            leaves the reason the resume turns on where it is -- the pushed-round tail every exit
                            shares, plus the round a
                            hold owes: named for the gate to write down ahead of its relabel, read back by the tick
                            the settlement hands the label to -- through the one parse the handler asks in front of
                            the body-edit resume, so what is outstanding cannot be read two ways -- and only over a
                            checkout standing ON the head it names,
                            since in sync with its remote is what a replacement host rebuilt at a moved pull request
                            reads as too -- and dropped by whichever tail finally pays it, since the resumed tick
                            reads a published resolution as a branch already standing on its base, which is the no-op
                            flip that resolves nothing
      models.py             the frozen records the owners hand each other
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
      validation.py         what a `split` payload must satisfy: the child cap, each child's shape, and the acyclicity
                            of the graph they declare
      outcomes.py           the three dispositions of a finished reply: the unparsed park, the `single` finalize, and
                            the `split` hand-off
      split.py              the crash-safe order a `split` manifest becomes child issues in, and the summary / label /
                            activation tail
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
      umbrella.py           the `workflow:umbrella` poll, the barriers around everything that acts on the child
                            scan -- past the scan, behind the settlement the terminal waits on, and once more
                            immediately before the write that records the resolution and RETIRES the cycle
                            together -- correlating that retirement to nothing, since the cycle it drops finished
                            -- correlating it to the cycle it dropped, since the barrier behind the write is this
                            process's -- which is what leaves no live cycle under a `done` no sweep queries, with
                            that write held inside the retirement window and the latch asked once more BEHIND it,
                            where a close is answered by putting the cycle back cancelled rather than refused; the
                            resolution said once off that same stamp -- and, on an umbrella a POST-PUBLICATION
                            split made and no other, off a marker naming this cycle and generation on the thread,
                            since only there can the barrier behind it refuse a terminal whose sentence has
                            already gone out and only there may an umbrella held on a reopened pull request repeat
                            itself every poll, while a restart out of a rejected cycle keeps the thread; the
                            publication that split closed asked about once more immediately in front of the
                            retirement write, which is the boundary past which the group is gone and nothing could
                            ask again, a refusal there writing nothing at all; the label and close
                            asked of a record that
                            already says the terminal is due, the close its all-done branch earns
                            instead of
                            an implementation pass, and the reconciliation that close waits on -- the one boundary at
                            which what a late split still owes a remote can be settled, and the last that comes
                            back if it cannot
      late_coordinator.py   the additive late mode's order: the owed owner read and the undelivered park notice both
                            reconciled ahead of every gate, the live-generation gate, the spent-budget park held
                            behind it and ahead of everything that would touch the world, the frozen-evidence
                            proof, the hold on the pull request the candidate stands on before any spawn -- and the displaced
                            one no new agent is started under --
                            the content settlement that can end the tick, the completed-result short circuit, the
                            retry-budgeted run whose pre-spawn write holds the whole accounting back -- the
                            counters and the attempt a continuation bought alike, since a run the tick then
                            declines must cost neither -- the read-only proof
                            over the candidate worktree, the fresh owner read every completion but a declined
                            run passes through on its way to settlement, and the split transaction that read hands
                            a cleared `split` on to
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
      late_session.py       the late run's pinned record -- role, locked spec, session, cycle, source commit,
                            generation, and the whole of what a verdict decided, each slice of a split manifest
                            carrying the addition budget it was proposed at, since the child issue created from
                            it states that number -- the ONE whole-comment budget every
                            verdict is refused past, since charging a `single` for the sentence it earns would buy a
                            superseded refusal, another decomposer run, and a `single` short of the park a human's
                            decision is owed on, while the sentence itself goes in the headroom that budget leaves
                            under GitHub's limit -- the rules it is read back
                            through, and the tracked spawn in the candidate's
                            own worktree, resuming the pinned session only for the run that carries a human's answer
                            to the question it asked. The drop that ends a recorded outcome is here too, and it takes
                            the operator's authorization to publish that outcome with it -- one statement, reached by
                            every road that ends an answer, since the run being recorded is by definition the one
                            replacing it and every term of that authorization survives the same candidate being
                            adjudicated twice
      late_hold.py          the cycle-marked hold a reusable open pull request wears: which one that is -- a hold
                            already recorded (released first and re-taken where the publication entry has since
                            named another, since the record holds one identity and one preserved body), then that
                            entry naming the implementation PR the work is already on, then the issue's own
                            `pr_number` -- the one guarded read every decision is
                            made from, the discussion provenance the last of those three has to establish, the
                            identity, head, and original body persisted (and proved persisted) before the edit --
                            a head this reading could not name refusing the hold rather than being recorded absent --
                            the notice worded by the side of publication it is written onto, the spelling an earlier
                            binary wrote beside the two this one does, and the one question that recognizes any of
                            the three as ours, the head that moved under a standing hold reported and never
                            restamped, and the retry, the refusal, and the settled pull request it reconciles to
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
      late_parks.py         every reason a late exit hands the issue back under, and the durable write each of
                            them rides out on: the park staged for the owner read to release, released anyway
                            where nothing would ever say it, and re-said at the top of a later tick when the
                            comment that should have said it was refused; the repeat that suppresses a second
                            notice, read off the sentence rather than off the flag, since a park whose comment was
                            refused is one nobody has been told about; the obligation discharged from what the
                            thread already carries where a failed write left the record claiming the opposite; the
                            parks a fresh attempt retires ahead of itself and the ones only a human's answer
                            clears; and the shared consumed-comment watermark every one of those answers
                            ratchets. The shared spawn budget's `retry_cap` is the one park here whose reason this
                            owner did not invent: it is staged like the rest so the late record rides its write,
                            and it is the only one audited on the budget's own stream rather than as a late
                            verdict or a typed late failure
      late_notice.py        the sentence a park owes the issue until it is actually on the thread: the durable
                            `{reason, message}` beside the flag, matched against the park it explains, the thread
                            read that discharges one a failed write left claiming the opposite of what GitHub holds,
                            and the pinned budget a notice too long to write down is refused past -- the reserve
                            beside what the record ALREADY costs rather than a flat ceiling, since a record an older
                            binary left, or one written before the payload escaped the wrapper's own terminator, can
                            sit outside that ceiling on its own and a sentence refused for it is a human never told.
                            A sentence
                            explaining a RECORDED outcome names that record rather than copying it: a marker where
                            the explanation goes, bounded by this orchestrator's wording rather than an agent's, put
                            back on the way to the thread on the first post and on every redelivery alike -- since
                            an explanation an outcome could be recorded with would otherwise be one its own
                            obligation could not be written beside. What goes back in is the WHOLE of it, blocked off
                            by whichever of markdown's two fence characters the quote leaves cheap; the one no fence
                            answers -- a long LINE of each, since only a line that is a run and nothing else can
                            close one -- is blocked off in PIECES instead, so the long lines land in blocks of their
                            own and every HTML-comment opener between them stays inside a block where it is shown
                            rather than obeyed; every fence width from the shortest up to the widest line is tried by
                            doubling and the smallest rendering wins. What ends a line is markdown's answer rather
                            than this owner's -- a newline, a carriage return, or the pair -- so the quote is split
                            on all three and rejoined by the terminators it arrived with, and a fence line written
                            with a carriage return is one, rather than three characters the block it rides in could
                            be closed at. Past what pieces hold, the quote goes in
                            unblocked with its openers escaped a backslash apiece, and past what that holds it is cut
                            and said to be cut -- unreachable for anything recorded here, and there because a comment
                            GitHub refuses is rebuilt identically on every poll
                            The thread read that finds a delivered one
                            names the pinned comment by ID rather than by the marker in a body, since a sentence
                            quoting that marker reads as the pinned comment to the body test -- and rewriting the
                            marker out of the sentence instead would grow it per occurrence, past what GitHub
                            accepts
      late_owner.py         the fresh tri-state read EVERY completed run passes before anything acts on what it
                            left: the latch consulted ahead of GitHub, since a close a poll saw while this worker
                            held the issue is the one reading a request cannot give back, the standing claim it is
                            entered past rather than makes (written by the completion's
                            own write, so a tick that died on the way here still left a park and an owed read), the
                            reconciliation that takes an owed read again ahead of every gate, the
                            cancellation a closed owner earns -- recorded and reported once per cycle, since
                            several barriers reach the same closed reading in one run and the cycle ended at the
                            first, with the repeat's own claim still dropped -- the park an unreadable one takes
                            only where nothing
                            else already holds the issue, and the one follow-up that park owes the thread --
                            posted before the write that clears it. Two barriers beside it take the latch ALONE,
                            for the steps whose own moment is too tight for a request and where a claim would name
                            `owner_check` over the boundary the tick actually reached: the create, the spawn, the
                            developer revision on both sides of its run and against the resume itself, and each
                            step of an authorized settlement's publication
                            share one, and the activation past a retirement already standing at `cleaning_up` has
                            its own
      late_snapshot.py      the immutable copy every child of a split is cut from: the ref this generation's
                            identity names, the obligation written ahead of the push and again behind the proof, the
                            create-or-verify that never overwrites, the fetch that proves a child could obtain it,
                            and the one park every refusal takes
      late_children.py      the children a split creates: the umbrella flag and count written before the first one,
                            the owner re-read before every one of them -- the first included, since that flag is a
                            remote write -- the latch asked once more against the create itself, since the
                            orphan lookup ahead of it walks the whole repository, once BEHIND it, and once between
                            the read of the child's own comment and the write that adds to it, since a close
                            landing inside either leaves a real issue: recorded either way, because a child
                            nothing names is the one state no pass can clean up, never seeded, because a
                            cancelled cycle owes its children nothing, and answered back to the loop rather than
                            stopped at, since the seed is the last step of one child's turn and a caller told it
                            succeeded opens the next slice against an ended cycle, the single write that records
                            each as a child, a
                            consumer, and an obligation, the seal that says the register a cancellation stopped
                            the loop over is FINAL -- the count it was measured against is one a cancelled loop
                            can never reach, so the ref would be held on a proof no pass could complete -- withheld
                            on a resumed walk short of the first unrecorded index, where a child an earlier attempt
                            made and never recorded would not be on it, the adopt
                            -- never repeat -- a resumed walk does, the one-receipt-only check a candidate has to
                            pass to be adopted, the manifest test that refuses a slice declaring a receipt of ours,
                            the seed that adds an ancestry without replacing a child's own work, and the body
                            naming the snapshot, the two reuse forms, the hunk splitting it forbids, and the
                            budget the slice was proposed at -- stated BESIDE the declared scope rather than
                            folded into it, with the paths that estimate covers named, and dropped entirely for a
                            slice nobody sized
      late_transaction.py   the order a cleared split runs in: the four refusals no step below could repair, the
                            snapshot before any child, the owner re-read before every step the remote keeps -- the
                            same guard the handoff took, taken between the children and again between the
                            announcement, the supersession, and the retirement, since a close a poll saw while this
                            worker held the issue reaches no cleanup pass on the tick it happened -- the children
                            before any link, the forward links behind the receipt that stops them repeating, the
                            pull request this cycle's work is on superseded and closed under a marker scoped to
                            this adjudication -- the plan one where the gate was entered before publication, and
                            the implementation one where it was entered past it, which is proved still open
                            and still standing where the reading found it before it is closed, since the tail
                            behind this deletes the branch and hands the work to children and an unsuperseded one
                            is an open change carrying work nobody will finish, with a pull request already
                            closed over THIS adjudication's own receipt recognised as the supersession a crashed
                            tick already made rather than as a human's settlement -- though never a MERGED one,
                            whatever the thread says, and never one whose head moved behind the close, since a
                            close does not freeze the branch the tail behind it reclaims -- the publication
                            asked about between every step of the tail on the same rule the owner is -- in
                            front of the close, the retirement, EVERY child released, and the branch delete,
                            the last two from inside the walk and the reclamation rather than in front of
                            either, since a child scan and a snapshot probe are requests of their own -- since
                            each is licensed by that supersession being on it and a human can merge, reopen, or
                            push in between any two; the close itself made against a SECOND
                            reading taken with no comment listing behind it, so a change settled or pushed to
                            inside the first window is left untouched rather than marked and closed and only
                            then refused, with the receipt that reading skipped handed to the write so no thread
                            scan stands in the interval either; a refusal before the retirement a park with the
                            record still live and one past it the step declined and left to the umbrella's own
                            walk or its terminal, which ask the same question themselves, per relabel and per
                            delete, off the publication group the retirement keeps -- the
                            generation retired onto `workflow:umbrella` in the write that hands the issue on, the
                            activation behind it -- through the shared dep-graph walk, so a child that ended while
                            the supersession was parked is left where it is -- and the branch cleanup recorded as
                            owed and attempted after
      late_cleanup.py       what a split still owes a remote once its children are running, with the latch asked
                            between every obligation it settles, between the fresh consumer proof and the ref
                            delete it authorizes, between that delete and the receipts behind it, and between
                            every two of those receipts, since each is a comment on somebody ELSE's issue -- a cancelled cycle settles by the same rules and tells its
                            consumers nothing -- reported and written
                            back only where a state actually MOVED -- so a remote that goes on refusing one delete
                            costs a request per visit rather than a record and a comment write per visit, while the
                            log goes on naming what is held: the fresh per-consumer
                            scan every rule here is proved against (a read that fails keeps its own ref and stops
                            nothing else), the branch obligations in every state but reconciled and the refs still
                            held, the refusal -- taken immediately in front of the delete, since the snapshot rule
                            beside it may spend a probe first -- to delete a branch at all while the pull request
                            it was superseded under is open again, nothing attempted, nothing recorded failed, the
                            entry left owed and the terminal held, that same pull request asked about once more by
                            the settlement the terminal waits on, which is the hold no ledger carries -- a
                            reclamation that FINISHED owes nothing, so a branch restored and a change reopened
                            after it would find every entry settled and `done` free to fire over them -- and
                            nothing written back for it, since nothing is owed and an entry saying so would send a
                            later pass to delete a branch a human put back, the exact-name check a branch and a snapshot ref each have to
                            pass before anything is deleted by it, the rule that decides whether a ref's recorded consumers have all
                            ended -- read off each consumer's issue state, since a reopen keeps the terminal label,
                            and whether the list names all of them read off the record's phase, since a child is
                            created before it is recorded, with a PRE-SPLIT phase corroborated against the ledgers
                            and against the count the transaction writes ahead of its first create -- which is what
                            upgrades a record an earlier binary rewound, and what tells a `splitting` loop that
                            finished from one still running, since the phase is written beside every child
                            recorded, with a SEALED register answering ahead of that count, since a cancelled loop
                            can never reach one -- beside the claim that no longer rewinds a transaction boundary
                            at all -- the
                            two deletes, the branch one taking the remote ref, the checkout, and the local
                            ref and proving all three gone, the snapshot one ordered on the record before it is
                            carried out and then re-proved against consumers read past that write (and retried past
                            the proof only for a ref one read-only ask shows the remote no longer has, with a
                            raising transport read as the refusal it is), the receipt every child cut from a
                            reclaimed ref is left by a LIVE split -- one comment, marked with this owner, cycle, and
                            generation so it is said once, proved against the child's own thread with the latch
                            asked between that reading and the comment it authorizes, never a write to that
                            child's own pinned state, and left
                            unsaid entirely by a cancelled cycle, which owes its children nothing -- with the entry
                            left `reclaiming` for a consumer it could not reach -- the one write that records any of
                            it, the settle both callers share, what may not be left behind (everything
                            unreconciled, an opaque ledger and a damaged identity included), and the question the
                            umbrella's terminal asks before it closes -- and that a park for a rejected or
                            hand-closed child asks on its way out, since both of those ended the consumer they
                            name and nothing else revisits an open umbrella
      late_reuse.py         what a child born of a split proves before it starts, taken on the child's own
                            dispatch because the owner that reclaimed the ref cannot write another live issue's
                            pinned comment safely: its own owner's receipt read off its thread first, which is what
                            says the reclamation HAPPENED and outranks a mirror nobody dropped or a ref pushed again
                            at the same commit -- so a thread that could not be READ holds the dispatch rather than
                            falling through; then, where the thread answered and carries none, this host's mirror
                            read for the commit it carries -- and only where the pointer carries the stamp saying a
                            reclamation would have dropped it first -- and the remote behind it, whose absent /
                            re-pointed / unreadable answers park, park, and HOLD the dispatch respectively; and,
                            for a child the split recorded but never managed to seed, the same answers over the
                            pointer its BODY marker earns -- corroborated against
                            the owner's own fresh generation first, since a body is a field the world can write and
                            a receipt is posted only after the ref is gone -- with the park, the pointer dropped or
                            the lineage repaired, taken before the label's handler is reached
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
      late_cancellation.py  the irreversible ending an owner observed closed earns, the mark a CLOSED owner gets
                            from this guard when its label names an ordinary terminal rather than the cleanup
                            sweep, the record read the dispatcher asks of a refused submit for the same window,
                            the refusal EVERY label earns over a
                            cancelled cycle -- each of them names a handler that would act on the issue rather
                            than end it -- with the terminal written wherever the transition graph declares the
                            edge from, plus the `ready` and `blocked` the cycle's own decomposer writes as its
                            ordinary outcome, where a refusal would stand on every visit the sweep makes forever,
                            and never from the unlabeled
                            state, which IS the restart handshake, and
                            deferred whole past a control label that says now is not the time; the reading of that
                            ending the dispatcher takes on the way OUT of a cleanup pass, so a pass that returned
                            with the ending owed under a label no query asks for keeps the observation that routes
                            it back, and the obligations half of the same question, asked by the sweep deciding
                            whether an owner may be let out of it; the receipt a
                            poll leaves on
                            the thread for a close it could hand to no worker -- a comment, since the pinned
                            comment is written whole and the worker holding the issue owns it, retried until one
                            lands, written from the SAME read that answers whether the reading is still owed, and
                            scoped to the cycle a retirement in flight names where the record names none -- the
                            once-per-process scan that adopts one a DEAD process was holding, scoped
                            to the cycle so an operator's authorized restart is not ended by an older close and
                            claimed only once the walk answered; the mark a handler already inside its own child
                            walk takes when the latch answers mid-scan; and the two
                            entries into the ending: the closed owner's, and the dispatcher refusal a REOPENED one
                            takes, which runs the same reconciliation and writes the same terminal -- reaching no
                            handler either way,
                            since an issue worked again without passing the ending would be the cancelled cycle
                            resumed by accident -- the unlabeled state included, which `late_restart` answers
                            one guard ahead and which falls through to nothing, since the pickup path behind
                            it would greet a cancelled cycle as new; the reading of what is owed by ANY
                            measure that decides both, the ending's own list plus the settled-ledger answer
                            the domain gives, since a child receipt and an untypeable consumer ledger are on
                            neither of the first two; the terminal written from the unlabeled state only
                            where the record shows one was never applied, so the operator's own
                            restart (taking `rejected` off) is not undone while a workflow label a human
                            stripped mid-cleanup still earns the ending it interrupted; the cycle that
                            terminal is owed for, recorded before the label write so a tick that dies between
                            the two has something to come back to, with the PROOF a restart reads taken from a
                            label that LANDED -- from the write returning where this pass made it, since a
                            client's cached labels outlive the write that changes them and a closed owner
                            gets no second visit, and from seeing `rejected` on the issue where it did not,
                            which is what backfills a cycle that ended before the record existed, and from
                            the newest workflow label THIS orchestrator applied where neither reached --
                            asked from BEHIND the reconciliation, so an obligation the ending discovers
                            rather than reads is on the ledger before anything decides the cycle owes
                            nothing -- what answers an
                            unlabeled issue over a cancelled cycle is
                            `late_restart`, asked one guard ahead of this one. The pass
                            itself is the cancellation persisted (with the boundary it interrupted, since
                            `cancelling` overwrites the phase every later rule reads) and reported once, before any
                            external call; the held pull request -- the one obligation no other pass ever sees --
                            released, told once over a cycle-scoped marker, and closed, re-asked on every visit
                            because its state is a human's to change and recorded only where that state moved; the
                            branch a supersession left behind but never wrote down taken on as owed, off the
                            announcement's own receipt rather than the phase a retry rewinds, only where the record
                            names none, and only once that pull request is settled -- the boundary is written
                            before the attempt, so it says nothing about whether it landed; the child receipts
                            discharged so the terminal a restart reads is one it will accept; the rest handed to
                            `late_cleanup`'s own rules unchanged, with the consumer
                            scan taken only where a ref is actually held; that pull request asked ONCE MORE on
                            the far side of all of it, since a branch delete, a ref delete and a consumer read apiece
                            stand between the first ask and the terminal; and the `rejected` terminal, written last,
                            only for a closed owner, and only once nothing is owed -- which is what takes the issue
                            out of the sweep for good
      late_authorize.py     the one decision that ends that park: a trusted whole-comment
                            `/orchestrator authorize-oversized <commit>`, read only while the park stands and only
                            as a reply to its notice -- prose around it is guidance the developer is resumed
                            against, guidance in the same batch outranks it, `/orchestrator continue` is refused as
                            the non-decision it is, and an untrusted author is not in the reading at all. What a
                            proved command earns is the contribution RECOMPUTED between the frozen pair (never a
                            digest a caller handed in) and the `late_split/overrides` group written with the park
                            cleared and the reply consumed in ONE write, since either half alone is a state the next
                            tick reads wrong. The commit has to be the frozen candidate and the `single` has to
                            still answer this cycle, generation and commit; both refusals are said once per READING
                            -- under a receipt scoped to it, since the sentence and the write that consumes it are
                            two operations -- and a contribution this host cannot fingerprint is not answered at
                            all, so the operator is never asked to decide twice for a store an operator repairs. The
                            predicate the settlement enters that road on is here too, asked of the RECORD: every
                            frozen term compared against the generation in hand, and then the contribution
                            fingerprinted AGAIN and held to the recorded digest, since the terms alone are the
                            pinned comment agreeing with itself and the publication may be reached on a later
                            process and a host that never held the content between the pair. WHICH answer was
                            authorized is the one thing no term can say -- a candidate can be adjudicated twice and
                            an acknowledged unchanged one matches every field -- so the record is bound to its
                            answer by being dropped with it, by `late_session` where a result is discarded AND where
                            the run replacing it is recorded, which is the statement no road gets around, and by
                            `late_revision_reconciliation` where a re-freeze mints a fresh generation one step
                            earlier. The no-verdict refusal retires the park on its way out, since the issue stops
                            next for whatever the replacement adjudication answers and a standing `awaiting_human`
                            would silence the question it might ask
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
      late_budget.py        the addition budget one proposed child declares: the manifest field the prompt asks
                            under and the parser, the record, and the child issue all read back, and the one rule
                            for what a declared budget IS -- a whole number of at least one line, so a bool, a
                            float, a numeric string, and zero each read back as no budget at all. What an absent
                            one earns stays the caller's: a fresh reply is refused, a record writes none, and a
                            child issue states none
      late_prompt.py        the late-only prompt: the committed candidate, the frozen diff, the measurement, the
                            lineage, and the three outcomes with the bounds they are judged against and the two
                            field names they are answered under, read off the owners that read the reply -- the
                            human decision a `single` requires and the explanation it owes for it, the
                            dependency-ordered slices and dormant prerequisites a split has to consider before
                            that answer, what every child body owns, and the addition budget each child declares
                            under this generation's own ceiling -- the figure its own JSON template shows scaled
                            to that ceiling, since a template is copied verbatim and a standing one would be a
                            child the reply contract refuses wherever the ceiling is narrower than it
      late_reply.py         the late reply's own fence, its three structured decisions, and the envelope and split rules
                            it borrows from the initial mode -- plus the two rules that are this owner's alone and
                            are asked of a fresh reply and of nothing recorded: the explanation a `single` owes for
                            why no safe split is available, without which the verdict a human has to act on carries
                            none of what it turns on, and the per-child addition budget, required and bounded
                            against the ceiling this candidate was measured at. Neither is asked of a record: the
                            borrowed validator also reads back manifests written before any budget existed, and a
                            `single` recorded before the explanation was kept still answers, with a stand-in. The
                            number itself travels past this owner, since the record keeps it and the child issue
                            created from the slice states it
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
      late_guidance.py      what that comparison earns: the baseline a first tick takes, the park an edit wins over
                            every concurrent answer, the certificate a bare continue writes, the question a real
                            answer reopens, the continue that answers none, and the routing of the `single` park to
                            the owner that ends it -- routed rather than answered, since what ends that one is a
                            decision to publish past the size gate rather than a reading of what the humans said
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
      late_restart.py       the fresh cycle an operator authorizes by taking a settled cancellation's `rejected`
                            back off: what the record has to prove before that gesture counts -- a cycle that
                            exists, one a close already ended, and one that owes nothing under BOTH readings, since
                            the ending's outstanding list and the domain's settled ledger overlap without
                            containing each other (only the first reports a held PR this generation cannot show it
                            held, which no pass can settle and a restart would erase; only the second counts a
                            child receipt or an untypeable consumer ledger, over which the retirement would refuse
                            with the marker already down) -- the proof half of the terminal record, saying
                            this cycle's `rejected` LANDED on the issue, without which a workflow label a
                            human stripped mid-cleanup and a terminal write GitHub refused both read exactly
                            like the removal that authorizes a restart -- the
                            open, unlabeled issue the gesture is read off, and the marker that answers it for
                            itself once a transaction has begun; the identity that record is repaired to before
                            anything is written, since a pinned comment naming another issue would file the fresh
                            cycle and both sinks' records of it under that one, and a root naming no issue at all
                            is a record the telemetry contract refuses outright -- the current issue is the issue
                            the comment was read off, and the root is kept where the record is this issue's own and
                            re-derived from the ancestry otherwise; the control label that defers the whole of it;
                            the `DECOMPOSE` setting that chooses between the two labels a restart may apply, and the
                            record that outranks it from the moment a notice has announced one; then the
                            transaction -- the marker made durable first, the notice said once over a cycle-scoped
                            receipt proved from the thread and ADOPTED off it where an earlier pass posted one and
                            lost the id it tracked in memory only, the label written where the issue is not already
                            on it and put back where the name is there but this orchestrator is not what applied it
                            -- the restart's own application is what separates the fresh cycle from its
                            predecessor's terminal in the history the ending's last-resort proof reads, and GitHub
                            records no event for a label already present -- and the retirement behind both, with the
                            projection that retirement writes: a
                            whitelist keeping the pinned comment's own identity, the bounded orchestrator comment
                            ids, the cumulative issue usage, and the identity joining the fresh cycle to its
                            predecessor, and dropping everything else
      late_models.py        the carriers the late owners hand each other: the tick's subject, the hold, the run, the
                            adjudication, the tri-state owner reading and the park staged for it to release, the
                            split that reading cleared for the transaction which creates its children, the content
                            fingerprint and what the humans have said since, and what one call did
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
      disposition.py        the publish / timeout-park decision, taken on both readings of what a run left --
                            the head moved off `before_sha`, and the branch is ahead of base -- so a checkout
                            something advanced onto that base is not read as a commit, at the timeout's
                            disposition or at its next-tick recovery; the attribution both readings rest on,
                            which needs BOTH ends of the comparison read and parks where either is not; the
                            certified floor a clean exit is credited against, the size gate every clean
                            committed candidate passes, the timeout park's own recovery, and the approved
                            commit an interrupted publication owes, disposed against the record naming it
                            rather than against any ahead-of-base reading -- and NAMED on the work handed
                            to the seam, like every other recovery, since the gate reads the head again and
                            a commit landing between the two proofs would be approved in the original's
                            place and pushed under a record naming neither. The three parks the size gate
                            itself takes are answered by `late_recovery` beside it, which routes each back
                            through this owner's publication seam
      late_gate.py          the order the size gate's questions are asked in, taken over one subject so both seams
                            ask them the same way: the switch, the commit the caller named -- proved against the
                            checkout before anything is persisted or pushed, since between the caller's read and this
                            one the worktree is writable and a commit landing there is a different candidate, and
                            every RECOVERY names one too, since no developer ran and the reading that licensed it
                            was about a commit a previous tick recorded -- the four records that
                            say a commit is already decided (the adjudication's exemption asked as a pair with the
                            operator authorization beside it, the commit an open pull request this call froze is
                            already standing on, the gate's own unspent
                            approval, and the commit this stage already pushed -- that last one proved by
                            `late_delivery` rather than read off the note, once per call and for every candidate,
                            since a second reading is a second answer over a decision already made), a record
                            already answering, and
                            the count that answers a pair nothing has yet. A commit an exemption names and no
                            authorization stands behind takes none of those roads and is answered past the switch
                            by the ordinary reading, which `late_consent` parks an oversized answer to: the
                            exemption is an agent's verdict, so reading it here as "already decided" would publish
                            half a bypass. What ADMITTED the candidate travels out with the verdict, because this
                            is the only place that knows and a proof taken again at the write is a second chance
                            to fail
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
      late_consent.py       the park an adjudicated candidate with no operator authorization behind it waits on.
                            What reaches it is every oversized reading of a candidate `late_authority` beside it
                            calls exempt on a record nobody authorized, and an issue already standing behind the
                            park is brought back to the gate by `late_recovery` on every poll. The reading is the
                            gate's OWN -- the pair it froze, the count it took on the tick that acts, the ceiling
                            it counted against -- since those are the terms an authorization is recorded on, and a
                            candidate the count puts at or below the ceiling needs nobody's permission and settles
                            with the park taken off on the way into the retirement's own durable write: a commit
                            published over a record still saying a human holds the issue is one the source stage's
                            parked road stops on every poll after. Then everything a reply to it is worth: a hold
                            rather than a route back to
                            the adjudication, since the change has been ruled one change already and what is
                            missing is the person, taken without deleting, migrating, or repairing a field,
                            announced once per pair, and taken without making the COUNT durable -- a generation
                            answering "oversized" is what the dispatcher restores `workflow:decomposing` over, so a
                            park carrying one would be relabelled out from under itself on the next poll and
                            nothing could ever answer it. The command earns the `late_override_*` group written
                            from the gate's OWN reading -- the pair it froze, the count it took, the ceiling it was
                            counted against, the digest recomputed between that pair, and the comment it was
                            written in -- in the one write that takes the park off, consumes the reply and drops
                            any sentence the park still owed the thread, while a reading this host cannot take
                            records nothing and leaves both where they stand. What that write consumes is what the
                            READING got to, then the unbroken run of OUR OWN comments above it, and no further: ids
                            ascend, so an answer of ours lands above the reply it answers and must be consumed or
                            the next poll reads our own words as a human's, while a watermark taken from the
                            thread's tip NOW would swallow whatever landed since the fetch -- a retraction of the
                            very command being acted on included -- unread and unanswered, and one jumped straight
                            to the answer's own id would swallow the corrected command an operator posted between
                            the reading and that answer. A command it may not act on is answered under a scoped
                            receipt and consumed on the same terms. Both sentences this owner words -- the park's
                            notice and that refusal -- carry a receipt scoped to what they answer, RECORDED before
                            the sentence carrying it goes out and dropped by the write past the post. So the record
                            says whether a tick died mid-sentence and the THREAD says which side of the post it
                            died on: a receipt some comment of ours carries is a sentence that was said, one no
                            comment carries is a sentence still owed, and a park that reaches the quiet road with a
                            receipt outstanding drops it rather than re-reading the thread on every later poll. The
                            park itself goes down ahead of its notice too, so a restarted tick finds somebody
                            already waiting rather than announcing a second time over a watermark that would move
                            past the command written in between. Both halves of the thread's answer are asked --
                            the receipt and the author -- which is the safe direction for SILENCING a sentence and
                            the wrong one for claiming a comment: these strings are public text, deterministic from
                            an issue and a commit, and the login may be the operator's own, so read as proof of
                            authorship a retraction written under a quoted receipt would be taken for one of ours,
                            deleted from the reading, and the authorization beneath it would publish on consent
                            withdrawn. Nothing here writes the id ledger, which is the only thing that says a
                            comment is ours; what an unclaimed sentence of ours costs is standing in the reading as
                            somebody's word, which is no command, so the park holds. The notices are worded on
                            the side of publication the park was taken on, since guidance reaches a developer only
                            where the ordinary resume is still in front of the issue
      late_command.py       which reply on a standing park a tick should act on, and nothing else: no record is
                            written and nothing is decided. The LAST fresh trusted reply, because reading the
                            batch as a set is what poisons a park -- a reply matching nothing is never consumed
                            on the seams that publish onto an open pull request, so it would stand in every
                            later batch and refuse the correct command behind it. ONE fetch answers every
                            question a poll of that park has -- which reply to act on, whether anybody spoke at
                            all, and how far the look got -- because the first two decide opposite things and a
                            road that asked them separately would answer from two different threads: a command
                            landing between the two reads is classified as guidance, handed to the ordinary
                            resume, and consumed past the watermark with an agent paid to answer it. How far
                            the look got travels because that is what an answer may consume and no more, and
                            because it is what a sentence posted on the strength of it is scoped by.
                            A reply that IS the command is carried whatever it
                            goes on to say, an argument nobody could act on included, which is what earns an
                            abbreviation the sentence saying so instead of a silent park. Three authors are
                            never in the reading: an outsider, a comment with no id, and the orchestrator itself
                            -- the park notice spells the command out ready to copy, so our own sentences are
                            exactly what a reader matching on that syntax would mistake for one. The pinned
                            record is named by its ID rather than by its marker, since that
                            fallback hides every comment merely QUOTING one and a reply hidden from this
                            reading is a reply whose author never spoke -- and it is DROPPED outright from both
                            reads that ask a THREAD about a receipt: a receipt is a field
                            on that record before it is a sentence on a thread, and a record whose escaped
                            rendering would not fit is written as its own payload, so on those issues the receipt
                            asked about sits verbatim in the pinned comment under our own login. Read there, a
                            sentence recorded and not yet said reads as one already said -- and, since the record
                            is the earliest comment on most threads, as one already ATTRIBUTED, which drops the
                            receipt and means the notice is never posted at all. Being ours is
                            PROVED by the recorded id and by nothing else, because the last-reply rule makes
                            dropping a comment the same act as deleting what its author said: a retraction taken
                            for one of ours never happened, and the authorization beneath it becomes the last
                            word and publishes on consent withdrawn. A batch the generic resume forms whose
                            LAST fresh reply is one of these commands, while the park is standing, defers that
                            whole tick unconsumed -- since that read comes after the road classifying this park
                            has handed the tick back, so a command landing between the two is in its batch and
                            in nobody else's. Deferring rather than sparing the one reply, because a watermark
                            is one number and the resume is not the last thing to move it: the run it starts
                            parks, and that park stamps the thread read to the notice it posts, above the
                            command. Only where the command is LAST, since one with guidance written over it
                            has been replaced. The marker is text anybody may paste, and
                            the author login is the shared-PAT hazard named where that ledger is defined -- a
                            reviewer posting from the token's own account matches it exactly, and they are the
                            one whose consent this park collects. A comment the ledger cannot vouch for stays in
                            the reading, which leaves the park standing rather than publishing
      late_recovery.py      every park the size gate takes, answered ahead of every spawn because the work
                            in question is committed already: one owed another READING, which a trusted bare
                            `/orchestrator continue` asks for; one owed another LOOK at the checkout, which no
                            reply can supply and which says nothing until the answer changes, asking
                            `checkout_recovery` below whether the worktree has come back; and one owed a
                            DECISION nothing but the named command can be -- and every poll of that last one
                            comes through here, since an issue behind it has committed work and no run to
                            dispose, so nothing else would reach the gate to measure the candidate again or say
                            a sentence the park still owes. What each poll costs is what the thread says: a
                            command or an unsaid sentence is answered through a fresh reading, guidance is
                            handed to the ordinary resume, and a thread nobody has written on is held where it
                            stands without a request or a word. Each hands its answer to the same
                            publication seam the committed work came out of, so a recovery reaches exactly the
                            outcomes a fresh disposition does and decides nothing the gate would have decided. A
                            checkout that is GONE stops all three before that seam, and what it costs differs by
                            what the park was waiting for: a reading can be asked for again, so the measurement
                            park lets the seam park under a reason of its own, while the seam's reason would
                            take the authorization park's off and its notice would move the watermark past the
                            command still standing -- so that road asks the seam's own questions first, the
                            worktree on this host, its tree provably carrying nothing loose, and its head the
                            commit the park is about, and holds exactly as found wherever the answer is no.
                            The head is asked because a checkout that has moved is a candidate the exemption
                            does not cover and the override does not name, measured and published on its own
                            count under a command that named another. The commit it proves is then NAMED on
                            the work handed over, so the gate holds its own head read to it: the worktree is
                            writable between the two readings, and asking here alone would leave that window
                            open. Every recovery road carries the commit it proved for that reason.
                            Asking first cannot close the tree half, since the
                            tree is read again INSIDE the seam, so the park, its reason and its watermark are
                            held across that call and put back wherever it did not PUBLISH -- which is the one
                            question asked, and it is read off the held record rather than off the park flags,
                            since several of the seam's roads clear those without publishing anything. Held on
                            the RECORD rather than in the frame that made them, in
                            `late_held_authorization_park` written before the call: the seam records an
                            authorization, clears the park and consumes the command durably before this owner
                            gets an answer back, so a rollback living in memory dies with the process and the
                            poll after a crash finds an issue nobody is waiting on over a watermark that has
                            swallowed the decision. A record still carrying that field is a handoff that never
                            RETURNED, which is why the poll finding one restores what it holds without asking
                            what the seam meant -- there is no answer to read, only a call caught halfway, and
                            a park put back over work the seam did publish costs a poll while one left off
                            costs the operator's decision. The attempt is RECORDED before that call for the
                            same reason, since the seam posts its
                            own refusal before anything persists the id of it. What that call did not account
                            for is then left exactly where it is: a receipt still outstanding when it returns
                            names a sentence of ours the seam said and no id write recorded, and it is the only
                            thing telling a later reading that comment is not somebody's guidance -- so only
                            the promise the seam never worded a sentence for goes with the park. That notice is
                            the one sentence
                            on this park nobody here words, so the seam is handed `late_authorship`'s client
                            and the park itself is held across the call by `late_rollback`.
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
                            issue, and `late_parks` spends it there. Consumed to what that reading LOOKED at and
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
      late_rewrite.py       the publication a squash-on-approval may rewrite and the push it then makes, and the
                            switch asked ahead of both: a squash is NEW work by the switch's own definition -- the
                            commit it publishes is one it makes itself -- so `DECOMPOSE=off` freezes no entry:
                            no pull request is read for the MEASUREMENT and nothing parks over one, and what such
                            an install does is squash and push under the lease this stage read for itself, which is
                            the second answer that makes the skipped reading safe: a remote somebody moved rejects
                            it. What the switch does not reach is the terminal-safety barrier immediately before
                            that push, which reads the recorded pull request on every install -- a setting about
                            what enters the measurement does not license force-moving one somebody merged. The road with NO push behind it is given its
                            own entry point here for exactly that reason, and the switch does not reach that one --
                            a recovery that drops a record and hands the branch back has no lease to answer with,
                            so the reading it skipped would be the last thing before `documenting` had the issue.
                            The gate's own switch question is asked here because the seam reaches it twice and the
                            first of the two is the pull-request read the switch is meant to save.
                            With the
                            switch on: entered on
                            that pull request before the reset destroys anything locally, so a closed or unreadable
                            one, a dirty tree, or a head that moved costs a refusal rather than a rewrite and a
                            rollback; then the commit the squash MADE goes through the whole gate, because that is the
                            object the push would put on the pull request -- the tree is the approved one, but the
                            base moves, and this is the last push before a human is asked to merge. That commit is
                            checked on both sides of the gate, since the gate proves the checkout for itself and a
                            first generation has no record to prove it against, so something committing over the
                            worktree in that window would be measured and published in its place. Which holds keep
                            the rewrite is answered here too (`_rewrite_stands`), over the three records that can
                            point at a commit: the receipt naming the squash says a push landed, the approval says a
                            push is still owed for it, and a live record says the adjudication owns it or the
                            reconciliation still owes it a count -- and a checkout that is not the squash says
                            something else made the commit. Anything else is a reading that REFUSED and froze
                            nothing, where the squash is a local commit nobody measured and the caller puts the
                            branch back rather than leave a retry one commit to call success. Asked as a group
                            because a road that lost a write can leave any subset of them down: a transfer whose
                            grant landed and whose push the remote took has the APPROVAL naming the squash while the
                            receipt still names the head that commit was pushed over, and rolling back there would
                            take the checkout off an object the remote already carries. And the debt a
                            rollback abandons is dropped there, durably, since the reconciliation ahead of every
                            handler would otherwise stop the tick for a publication that is never coming -- with the
                            permission an authorized transfer holds dropped on the same write, since the commit it
                            was granted for is on no branch any more and the reset landed on a head the record
                            itself names as the one the rewrite found -- the accepted end for a squash, the lease
                            for a rebase. The before-state the rewrite destroyed -- the head it replaced and the
                            merge base both sides are read over, taken from the PLAN rather than from the entry,
                            since the entry admits a remote tip a durable record says this issue's own push put
                            there and only the plan says which commit was collapsed -- is handed into the gate
                            beside the publication it was entered on as the evidence `late_transfer` grants a
                            transfer on.
                            That same before-state is what this owner makes DURABLE before the reset, and what a
                            tick coming back to a half-finished rotation is answered from: the three terms go onto
                            the pinned comment ahead of anything destructive (`_records_the_collapse`, refusing the
                            rewrite outright where GitHub will not take the write), the record is read back and
                            dropped here, and `_resumed_entry` is the entry a resume freezes -- over the head the
                            record names, or over the rewritten commit itself where a receipt dates that tip to
                            this attempt, and NAMING the commit, which a fresh squash cannot do and which is what
                            lets a pull request already standing on the rewrite be admitted as this issue's own
                            push having landed. The drop rides the write of whichever owner ends the claim: the
                            rollback where a reset put the branch back, the reset that never ran, and the approval
                            handoff's own write -- taken ahead of its relabel -- where a push landed. While it
                            stands it also holds the branch out of the pre-tick base refresh, since a rebase
                            replaces the collapse with a commit carrying the base advance and the recovery's own
                            tree proof stops answering. `_already_published` is the receipt and the head it
                            replaced asked as one question, and it is what both ends of the resumed window turn
                            on: the entry is frozen over the rewritten commit where it answers yes, and a push
                            that then does not go out may not put the branch back, since the remote has the
                            commit and the count the handoff owes a notice would go with the record. The ENTRY's
                            own frozen tip answers the second of those beside it and covers more: a crash
                            between a push and its receipt leaves no receipt to date, and what says the pull
                            request carries the commit there is the reading this tick took of it
      late_transfer.py      whether a rewrite may carry an adjudication's exemption onto the object it produced,
                            rather than have the same change measured past the same ceiling and adjudicated a
                            second time with a pull request already open over the work. A permit is granted only
                            over a whole semantic record whose exempt commit IS the one the rewrite came from,
                            evidence naming a bounded kind from a stage that really makes that kind -- the two are
                            one claim, so a `conflict_rebase` offered from `validating` types in both halves while
                            describing a rewrite that stage does not make -- and every end of both contributions,
                            an operator authorization standing behind the exemption it would move, proved through
                            the owner the GATE proves one through, since moving an exemption nothing authorizes
                            would hand the rewritten commit a permission the accepted one never had,
                            no authorization this build cannot read already standing for that exemption -- a grant
                            REPLACES that group rather than adding to it, so an unreadable claim about the exempt
                            commit is evidence a transfer may not overwrite to repair -- the publication this call
                            itself froze (same pull request, same stage, a remote still standing on the lease) and
                            the one the issue still records, a provably clean checkout standing on the rewritten
                            commit, a leased head that peels to a commit this host holds -- the one end nothing
                            else here reads as an object, since the lease may name a different commit from the
                            accepted one -- an issue re-read past the close latch and found UNCHANGED -- open,
                            carrying no `paused` or `backlog`, and still on the stage the rewrite recorded, since
                            the entry read that stage off the issue the tick opened with and a relabel during the
                            rewrite is invisible to every other reading -- a rewritten base the base branch really
                            carries, frozen from what the REMOTE says that branch is at and held to reachability
                            rather than to equality, since the branch advances on its own while a base carrying
                            work no remote has is one only this host ever saw -- and canonical fingerprints that
                            agree.
                            The accepted one is taken over the pair the RECORD names rather than the pair the
                            caller claims, so a hand-edited `late_exempt_base_sha` is the record failing to prove
                            itself instead of a field nothing ever reads, and the caller's own claim about what it
                            replaced is held to that same digest -- by digest rather than by spelling, since the
                            frozen base and the fork point a squash collapses onto or a rebase replays onto
                            disagree as object ids the moment the base branch advances. A digest a standing
                            permission already recorded is held to that same reading, since carried forward
                            unchecked it would be rewritten by whatever this tick happened to take -- a repair of
                            evidence nobody checked, made under the authority of the transfer being decided.
                            Granted, ONE durable write records the authorization and the debt the push is still
                            owed -- both before the push, because a comment that explains a one-commit branch and
                            does not say a push is outstanding is one the next squash reads as nothing to squash.
                            The exemption itself does not move here: the rotation belongs to `late_rotation`, on
                            the write that receipts a landed push, so a verdict is never left on a commit no
                            remote carries. A write GitHub REFUSES is handled here rather than allowed out: the
                            staged payload is put back exactly as it was found and the permit is refused, so the
                            tick falls through to the ordinary gate instead of ending in an exception that would
                            carry past every rollback its caller has. Refused, nothing moves and the ordinary
                            cumulative size gate measures the rewrite like any other candidate. The drop a
                            rolled-back force-push needs lives here too, so the rollback takes back exactly the
                            permission the rewrite was granted and leaves the exemption, which never moved, alone
                            -- keyed on the head the record itself names as the one that rewrite found, since a
                            squash is reset onto the commit it collapsed and a rebase onto the anchor it leased.
                            And the tick AFTER a crash between the grant and its push is answered from the same
                            record: the recovery has no plan behind it, so both pairs, the publication, and the
                            lease come off the standing permission and every question is asked again over them --
                            which is why the gate's approved bypass defers here rather than answering on the
                            object id, since a hand-edited permission, a repointed pull request, or a relabelled
                            issue would each otherwise push an oversized rewrite nothing revalidated. That
                            deferral is asked of the PHASE rather than of the commit the record names -- the
                            permission and the debt go down in one write for one commit, so an approval beside an
                            outstanding permission is either the one it licensed or a comment disagreeing with
                            itself, and a hand-edited target would otherwise make the permit invisible. An
                            outstanding permission is also what makes a lost receipt recoverable: a remote already
                            standing on the rewritten commit is this permit's own push having landed, admitted as
                            such rather than read as a moved remote, which would remeasure a squash the pull
                            request already carries
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
      late_records.py       what one gate call is about -- the publication it was entered on included, where there
                            is one, and the two claims a caller makes about its tick: that no developer ran, which
                            decides whether a moved head is fresh output, and the narrower one that it is answering
                            a reading the gate itself recorded, which is what the switch is asked against -- plus
                            the before-state a caller that REWROTE its way here destroyed, which is the one thing
                            no reading taken now could recover and the only evidence a transfer may be granted on --
                            the answer it hands back, the identities a record of it
                            is minted under -- the readings already lost travelling with the CANDIDATE rather than
                            with the generation counter, since a base the remote would not name records no base and
                            freezes the same commit afresh next tick -- and the validated-or-minted identity every
                            refusal is reported
                            under so a damaged record cannot take its own refusal down with it -- and, for the
                            pull request a record names, the THREE-way answer a barrier standing in front of a
                            push needs: a number, an absence, or a field the comment carries and no reader here
                            will type. Told apart because reading the third as the second is how every one of
                            those barriers fails open: each identity is read fail-closed, so an unusable one
                            comes back as no identity, and a push held to nothing goes out onto whatever the
                            branch's pull request has become
      late_freeze.py        the pair a count is taken over -- the candidate proved, the base frozen or re-proved,
                            and a base neither of those could reach counted as one of the readings this pair may
                            lose rather than parked outright -- and whether a recorded one may be acted on at all,
                            its identity and the issue it names included, asked as the REUSED pair's own
                            precondition rather than at each road into one, since the miss that retry writes back
                            would otherwise repair a record recorded against another issue under this one's
                            identity. A pair still waiting for its base is held to the same evidence less the base
                            itself, which is the one field the failure being retried leaves absent: the mint the
                            retry freezes under keeps the record's cycle, scope and spent readings while re-stamping
                            the issue number, the ceiling and the boundary from the process running NOW, so a
                            generation short of the ceiling it was frozen under would otherwise be re-judged against
                            whatever the setting has been retuned to since. Also the one state the switch answers
                            outright, which every seam that measures asks the same way
      late_evidence.py      what a recovery proves before it acts: the checkout, both recorded objects, a
                            head that is still the candidate, and a head that is still the commit an approval
                            owes a publication for -- proved ahead of every spawn
      late_verdict.py       what a measured candidate earns -- the push and the head an approval on the published
                            side is pinned to, which outlives the generation that froze it for as long as the push
                            is still owed, the `workflow:decomposing` hold and the
                            notice it owes the thread on the side of publication the record was entered on, the
                            approval a publication naming another commit supersedes, the same debt recorded for a
                            candidate that skipped the reading -- an exemption's, a supersession the switch let
                            past -- since no generation was frozen for one and the push it licenses would
                            otherwise leave the branch on the remote with nothing on the issue naming it, that
                            debt also offered STAGED rather than written, for the one owner that has a record of
                            its own to make durable in the same breath -- a permission that licenses a rewritten
                            commit and a debt naming the push it is owed may not be split across two writes, since
                            a process dying between them comes back to a one-commit branch nothing says a push is
                            outstanding for -- and
                            the retirement each is durable behind, that write held inside the observations
                            owner's retirement window with the latch asked ahead of it and the window's own
                            answer behind it, where a close is answered by putting the cycle back cancelled; both
                            verdicts are also where a measurement park is retired, since an answer is what it was
                            waiting for and a tick that only re-read the pair has not given it one, and the measured
                            one is where the step a notice named is dropped -- every failure-prone step is behind
                            that line, and the record it clears from is the one an oversized candidate is
                            adjudicated from. The authorization park is retired on the unmeasured verdict alone
                            and past every refusal on it, since that is the only road publishing a commit an
                            override already covers: what that park waits for is a PERSON, so a close or a
                            supersession above the line has to leave the operator waiting exactly as it found them
      late_parks.py         the approval group -- the commit a publication is owed, the head it is pinned to, and
                            the bounded basis saying which owner granted it, so a later reader tells this gate's
                            own count from a debt an operator's gesture is behind rather than inferring it from
                            the records standing beside them; the two bases that gesture IS behind are named as
                            one group, since what a reader decides is whether a debt has to be revalidated
                            rather than which owner granted it, and the one write the implementing seam mints a
                            debt through, so the publication and the guard that refuses a moved checkout leave
                            one debt rather than two. That write never INVENTS grounds: an approval already
                            standing for the very commit is carried as it reads, an unknown one included, since
                            promoting a legacy record to `unmeasured` would turn "fall back to the exemption"
                            into debt this workflow owns and nobody would revalidate; and where none stands the
                            grounds come off the exemption CLAIM -- presence rather than readability, so a field
                            a hand edit truncated still leaves the adjudication's debt -- falling to
                            `unmeasured` only on an issue carrying no such field at all -- plus
                            the one park shape every unreadable reading takes, worded on the side of publication it
                            was taken on, the typed failure both sinks carry under the stage the reading happened in
                            -- carrying the step that stopped and the line it wrote wherever the refusal was a
                            reading, and the family alone where it was a record nobody may act on --
                            the bounded quiet retry the two TRANSPORT steps get instead -- the miss counted on the
                            record and written before anything is reported or said, since a fresh process remembers no
                            miss, with the park taken only past the bound; the announce-once guard every refusal of a
                            typed step passes through, holding a tick that finds a park already standing over THE
                            SAME PAIR, still latched, and stopping at the step that park's own notice named -- the
                            member recorded by the roads that announce and by no other, so a quiet miss cannot pass
                            for a notice and a base that comes back -- which is not the last step a reading can stop
                            at -- cannot unsay one -- silent to the thread alone,
                            since the typed failure still reaches both sinks and a base id the remote finally named
                            is written even there, with a refusal stopping somewhere else announced once instead and
                            taking that member's place, and the notice itself naming the member and the line an
                            operator acts on it by with whatever the failing step said for itself carried up beside
                            it -- a park standing over
                            some other pair retired inside the write that records that pair rather than obeyed, since
                            nothing on the comment says which commit a park was taken over and a resumed developer's
                            fresh commit owes its own bound, the count ended by a base that was reached and both it
                            and the member ended by a reading that landed -- the
                            bare continue that re-reads rather than re-runs, the measurement park a reading that
                            SETTLED retires -- latch and all, since a reconciliation has no run behind it to clear the
                            flag, and from the verdict rather than from the gate's door, since entering the gate is
                            not answering the question the park was taken for -- and that park ALONE, since the
                            authorization park beside it waits on a person and no reading answers a person: a road
                            that lost the base and is counting a quiet retry would unpark an issue whose operator
                            never replied, and the exemption nobody stands behind would publish on the next poll,
                            so it has a retirement of its own that only a publication under it reaches -- the same
                            measurement park retired on a record
                            whose split has already become children, where no reading is owed and nothing about it is
                            a human's to answer, and the commits a publication is read by: the one an approval owes a
                            push for with the head it is pinned to, and the one this stage made. The boundary an
                            authorization handoff staged is spent from here too: `late_rollback` records it and
                            the write that moves the label out of this stage consumes it, and this is the one
                            owner both of those can reach
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
      parks.py              the session-limit, provider-unavailable, question, silent-failure, dirty-tree, and
                            unreadable-tree parks, the last two behind one seam so the caller asks whether the
                            tree is PROVABLY clean. Each records the thread read past its OWN notice and past
                            nothing else: the run it ends took minutes nobody read the thread during, so a
                            watermark stamped to the tip carries this stage's notice over whatever a human wrote
                            in them -- an `/orchestrator authorize-oversized` among it -- and the only road that
                            could act on that comment never sees it. The walk stops at the first comment the
                            ledger does not vouch for, and gives up the tip only where no walk could work: a post
                            whose id nothing recorded, and a thread with no watermark at all, whose spawn quoted
                            the whole of it to the agent already
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
