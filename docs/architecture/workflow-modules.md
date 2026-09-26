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
  writes. The public `workflow.tick` shim resolves `workflow.engine.tick.tick` inside the call. The initializer
  re-exports labels and guards but imports no engine or stage, so `github/` and `git/` can import the vocabulary
  without loading the engine or pointing back into their own initialization. `tests/workflow/test_imports.py` probes
  the import paths in a clean interpreter, and `tests/repository/test_layering.py` holds the direction under them.
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
workflow/                   publishes labels, transition guards, and the lazy per-repo tick entry point
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
    comments.py             the orchestrator marker, bound from the GitHub trust owner, and the bounded id ledger
                            shared by issue and pull-request comment posts; a developer report enters the ledger on
                            whichever reading finds it on the thread, since a post whose response was lost hands
                            back no id, and a verification artifact enters the same one through the sibling owner
                            below; callers persist the ledger, and shared token accounts are never treated as
                            exclusively automated. The id a report landed as is read off the LOOKUP, which
                            resolves it once when the reading is taken: this records a comment before its caller
                            ever sees the reading, and an id answered afresh to each of them could fail here and
                            succeed there -- leaving the settled report at a comment the ledger never learned
    verification_comments.py
                            one verification artifact published onto a pull request and recorded in the ledger
                            above, beside the owner holding that ledger rather than inside it: what this answers
                            for is one domain's publication, while that owner answers for the marker, the id
                            list, and the plain comment posts every stage makes. The id is read off the LOOKUP
                            for the reason a report's is, and recorded on whichever reading finds the artifact,
                            since a post whose response was lost hands back none. Both halves are needed: the
                            marker in the artifact's own rendering says the comment is ours once its id ages out
                            of the ledger, and the id says so once somebody edits the marker away -- without
                            which a feedback scan reads this orchestrator's own evidence as a human's request
    prompt_context.py       trusted-author thread reads, retained orchestrator comment ids, quoted comment lines, and
                            bounded tracked-repository awareness for agent prompts; marker text alone cannot admit a
                            comment, and a delivery snapshot over a read taken by the pinned comment's id is handed
                            that id too. `_delivered_thread` takes the read ITSELF for the prompts whose delivery is
                            recorded -- the text, the entries it is made of, and the revision that read fingerprints
                            to, so a prompt and the mark taken for it cannot be two readings
    prompt_delivery.py      shared process-local input-delivery snapshot and conservative settlement contract recording
                            exact delivered issue-thread, PR-conversation, inline-review, and review-summary inputs;
                            preserves distinct namespaces, watermark fields, bounded-excerpt omissions, filtering decisions,
                            and requirements revisions without copying live thread tips or taking unrestricted maximums.
                            A caller that names the pinned state comment has it excluded by id on the issue thread, so a
                            reply quoting its marker is still a reply; one that does not keeps the marker test. The
                            forged-marker refusal is the two IssueComment surfaces' alone, because those are the two
                            this orchestrator posts on and the id ledger evicts old posts from; it writes no review
                            and no inline comment, so a body quoting the marker there is a reviewer quoting it, and
                            refusing it would hide their words from the prompt AND stall the watermark that would
                            have recorded them, since a refused entry is neither delivered nor blocking.
                            `human_replies` is the same classification asked as a list question -- the trust filter,
                            the pinned comment, our own posts by recorded id, and a marker the ledger cannot vouch for
                            -- for the roads that decide who OWNS a batch before anything builds a prompt from it, so a
                            command classifier and a delivery record cannot become two readings of one thread
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
    review_verification_models.py the reviewer verification vocabulary, kept apart from the `VERDICT:` line: the
                            `VERIFICATION: RUN` / `VERIFICATION: END` block with its `COMMAND:` and `EXIT:` step
                            lines, and the `VERIFICATION: REUSED` line naming a SHA-256 evidence revision; the subject
                            a declaration has to be about -- the reviewed commit and the current evidence revision
                            the reviewer was shown; the two accepted outcomes, each sourced to the reviewer run and
                            labeled reviewer-reported, with every command, exit status, and output kept as written;
                            and the closed refusals: five for a run that did not complete, three for a completed
                            run's message whose declaration is missing, malformed, or stale
    review_verification.py  the strict reader of that declaration, which nothing calls until the reviewer round asks
                            for it. A run never invoked, interrupted, timed out, refused by its provider, or exited
                            nonzero is refused before its message is read; the declaration has to be the message's
                            only marker use, outside any code block, and a RUN block has to be closed, list at least
                            one command with one POSIX exit status right below it, and hold no verdict the verdict
                            reader would accept. Shape is settled before truth: a well-formed declaration naming
                            another commit, or any revision but the current one, is stale. Nothing is counted or
                            inferred from what the reviewer wrote
    stage_targets.py        exact label-to-handler and cleanup targets, with stage imports deferred to the call;
                            the unlabeled target reaches pickup through the same resolver. Named here too, though
                            no label routes to any of them, are the stage owners a report record's own measurement
                            REPLAYS to size the writes that land behind it: the two code-publication receipt
                            owners, which the report evidence reads and whose gate write the record reserves; the
                            stale-approval hand-back an `in_review` relabel writes; the stamp a fixing
                            hand-back leaves on the comment the settlement ahead of it left
                            (`stages/fixing/round_marks.py`); and the records a reviewer round writes onto that
                            comment (`stages/validating/review_records.py`)
    poll_models.py          poll-time closure evidence and family/fanout/cleanup partitions, preserving deferred issues
                            absent from enumeration and the blocked/umbrella family capacity exemption
    run_limit_dispatch.py   hold exhausted work, replay its owed notice, and admit grants or terminal cleanup;
                            an implementing plan PR does not prove that implementation work ended
    dispatch_guards.py      pinned-state admission, restart before cancellation, publication reconciliation, and
                            operator controls; an already-pinned unlabeled issue is left where its labels put it.
                            A standing auto-rebase anchor holds the handler, on the adjudication's own road too,
                            and is asked again behind the reconciliation; whether it holds and what a held tick
                            is owed are `base_sync/recovery_holds.py`'s. The developer-report transaction is
                            answered last of the reconciliations -- behind that second anchor reading as well as
                            behind the reconciliation itself -- and ahead of the reuse guard: its own evidence asks
                            whether the commit the report is about reached the pull request, which is the question
                            the publication reconciliation settles and which a pair it leaves on a still-pinned
                            anchor would answer soundly over work no recovery has finalized
    poll_reading.py         classify labels and hard-skip controls while admitting observed-close cleanup; drop open
                            blocked/umbrella dependency walks on the ticks `DEPENDENCY_POLL_EVERY_N_TICKS` skips;
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
                            authors, and whole-comment operator commands, over the live thread or a read the caller
                            already holds; the legacy bare-continue mode recognizes an existing baseline
    drift.py                baseline persistence and legacy normalization, the dev resume a requirements edit earns, and
                            the pre-implementation decomposition reset; no road here marks a thread read to its tip,
                            since a tip crosses what a bounded excerpt dropped and what landed while an agent was
                            out. On a parked tick the check measures the
                            requirements by what the park had already read (`answered`), so replies to the park are
                            the frozen batch's, not drift
    drift_delivery.py       the prompt a requirements edit is answered with and the record of what it quoted, frozen
                            together off ONE read and settled by whoever disposes the run: context the excerpt bound
                            dropped holds the watermark below it, a reply written while the agent was out is in
                            neither, and the revision recorded is that read's fingerprint rather than the thread's tip.
                            The PR-backed variant freezes a second surface into the same record -- the pull request's
                            unread conversation, quoted entire below the bounded thread -- and names an outsider's
                            comment refused rather than dropping it, so the carry behind the run may cross what no
                            reader is owed. It names NO shared watermark field: the two surfaces are covered at two
                            moments, so the cursor spanning them is the caller's merged re-read to derive and no
                            settlement's to write
    guards.py               what a finished agent run may leave behind: the never-invoked, shutdown-interruption,
                            and freshly-read pause refusals, and the awaiting-human park. The first is asked ahead
                            of the second wherever a stage reads the worktree before it asks whether the run
                            happened -- what a killed run left there is the operator's to see, and what a launch
                            that never started left is nothing. The park forwards explicit bounded correlation
                            fields (`route`, `agent_role`, `session_id`, `review_round`, `retry_count`,
                            `pr_number`, `sha`) to the emitted audit event and analytics record, rejecting
                            unsupported fields before emission through the same screen a park that emits for
                            itself reaches. Also the shared park vocabulary: the allow-list every road is
                            screened against, the route names the roads into a self-emitting park are spelled
                            with -- the two conversation stages own theirs on their own `state.py`, since their
                            stage funnels reach this one rather than emitting for themselves -- and the
                            `_ParkedRun` four stage packages hand one of those parks: a finished run plus the
                            road it came off, which the workflow label cannot say.
                            It marks the thread read to the id of the notice it POSTED rather than to whatever the
                            thread ends on afterwards: the two differ only for a human replying between the post and
                            that write, and on a park waiting for a reply, reading the tip there consumes the answer
                            with the question. A post this call could not identify moves the mark nowhere, since what
                            it may record itself read past is a comment actually posted AND identified; our own
                            unrecorded sentence is refused as forged by every prompt reading instead. `bounded=True`
                            asks for the other answer, and every park that FOLLOWS an agent run asks for it: it stamps
                            `park_watermarks.py`'s walk instead, and is popped before the correlation screen. Only a
                            bounded park reads the comment-id ledger ahead of its post, since the walk needs it; the
                            ordinary park only appends to that ledger, so a malformed legacy entry parks it all the
                            same
    park_watermarks.py      the bounded answer to how far a park ending an agent run may record the thread read,
                            taken by the funnel's `bounded=True`, by the implementing question and checkout parks
                            that post for themselves, by the run-limit notice's repair, and by the refusal a parked
                            `/orchestrator continue` earns: through the comments our id ledger names, stopping at the
                            first it does not -- a reply from the run, one quoting the pinned record's marker (the
                            thread is read by that record's id), or our own sentence whose recording write was lost.
                            It never reads the tip: no floor to walk from (the pickup anchors one), a post the ledger
                            did not gain, and a thread the re-read fails on all leave the mark where it was, the last
                            without raising, since the notice is already posted and the park still has to be recorded
    messages.py             the `ACK:` acknowledgement read out of an agent's last message, the one blockquote
                            form every agent output an issue carries is quoted in, and the two commands a HUMAN writes:
                            `/orchestrator continue` with the refusal a park needing real guidance owes it, and the
                            SYNTAX alone of `/orchestrator authorize-oversized <commit>` -- read from the whole
                            comment and nowhere else, with the argument captured as written, since a malformed one
                            is a command the workflow owes an answer to. What that second command MEANS is the
                            late-split stage owners', which is where the pair it names exists -- one per park it can
                            end, the adjudication's and the size gate's, each proving it against its own record
    report_outcome_models.py the developer report vocabulary: the `REPORT: READY` / `REPORT: END` and
                            `REPORT: VERIFIED` spellings the prompts teach, the two successful outcomes -- a complete
                            report ready for publication, and a report asserted to be on the pull request at a URL
                            and SHA-256 revision -- and the closed refusals: five for a run that did not complete,
                            two for a completed run's message that carries no marker or a malformed one
    report_outcomes.py      the strict reader of those outcomes. A run never invoked, interrupted, timed out, refused
                            by its provider, or exited nonzero is refused before its message is read; the outcome has
                            to be the message's only marker use and its last lines, outside any code block, and an
                            `ACK:` beside it makes it malformed. A verified location and revision are parsed for
                            shape, never taken as proof. Two yes/no readings beside it: whether a run FINISHED on an
                            outcome, for the stage whose other replies are ordinary answers, and whether it REACHED
                            for the contract at all -- well or badly -- for the caller whose other readers must not
                            take a message that reached and missed as one of their own
    report_fences.py        which lines of an agent's message a code fence may enclose, asked by both the developer
                            report reader and the reviewer verification reader, judged without a Markdown parser so
                            that a doubt reads as fenced: a fence opens at the top level or in a list item, closes
                            only on a bare run at its opening run's column, and stays open to the end past a line
                            that may have ended its list item. Asked by `report_prose.py` of a pull request's
                            description, it reads the fences a blockquote holds too, behind any nesting of list and
                            quote markers, closing one only behind the markers it opened behind; the marker readers
                            do not ask, since no marker line opens on `>`.
                            That reading errs towards code, so `definite_fences` answers the other end of the
                            doubt: the closed fences that are fences however the text is read -- opened at the
                            margin of their markers, outside anything an HTML block may hold, and closed where
                            Markdown closes them rather than only where the stricter reading does
    report_prose.py         what of a description is certainly prose, for the closing keywords GitHub does not act
                            on inside code. Not one reading of the Markdown but what EVERY reading leaves, so a
                            doubt reads as code. Lines are ended as Markdown ends them, a bare carriage return
                            included; a line a fence may enclose and a line indented as code are code behind any
                            nesting of list and blockquote markers; so is every span `report_code_spans.py` finds
                            possible and everything `report_html_literals.py` finds literal. What is taken out
                            leaves a character no reference is made of, so a keyword and a number either side of
                            code are never read as one, and a tag's own markup goes the same way, quoted attribute
                            values and all -- to its `>`, or to the end of the text for one that opens a line,
                            behind markers or what was taken out, and that nothing closes. So does what
                            `report_link_fields.py` finds read and not shown, asked once the tags are out. Both are
                            read TWICE, which backticks pair being a doubt of theirs too: with every possible span
                            out, where a span may hide a closing bracket, and with nothing out but certain code,
                            since a span only some reading encloses -- from a backtick a bare URL took, into a
                            title -- takes the link's syntax along and leaves the rest of the title as prose
    report_link_fields.py   what of a text a link, an image or a definition reads and shows nothing of, each
                            wherever it MAY be one. An image's description, an `alt` attribute once rendered: from
                            its `!` to the bracket that closes it, brackets paired innermost first and a backslash
                            escaping one, whatever follows it -- a collapsed or a shortcut image is one by a
                            definition nobody looks up. What stands behind a link's or an image's text: the
                            destination and title in parentheses, or the label it names; a bare destination holds
                            parentheses in pairs as deep as the renderer GitHub runs reads them, and one that goes
                            deeper runs to the whitespace that ends it, found once for the run it stands in. And a
                            link reference definition whole, behind the markers its line opens on, its destination
                            on the next line and its title on the one after included. A title goes on over line
                            endings, one behind a backslash included, and the parts of a link stand either side of
                            one behind the blockquote markers the next line opens on
    report_code_spans.py    the inline code spans of a text, POSSIBLE and CERTAIN. Markdown pairs backticks within
                            one stretch of inline text, and where one begins is the doubt: a heading or a list item
                            starts a block with no blank line above it, a table reads each cell on its own, and a
                            backtick is no delimiter where something else has TAKEN it -- a tag or an autolink,
                            which binds as tightly as a span, a bare `https://`, `ftp://` or `www.` URL, which
                            GitHub links where it stands through every backtick to ASCII whitespace or a `<`, a
                            link or an image, which reads its destination and title itself, a reference's label,
                            math -- so the pairing starts afresh past it. So a span is looked for from every line,
                            every cell of a block that may hold a table, and past every `>`, `]`, `)`, `$` and bare
                            URL's end from the first `<`, `[`, `$` or bare URL standing in no certain code, within
                            what blank lines bound and against one index of the text's backtick runs; possible is
                            whatever any reading encloses, and a block with more places to begin than the readings
                            allow is code throughout. Certain is what every reading agrees on: a span that ends
                            before the next place a reading could begin, begun where no earlier reading's span runs
                            in, with no taker before it in its block outside the certain spans already found. An
                            escaped backtick opens nothing, and a backslash inside a span escapes nothing
    report_html_literals.py what HTML shows literally or hides -- `<pre>`, `<code>` and their kind, and what renders
                            as nothing: a comment, a declaration, a processing instruction, a CDATA section, and the
                            bogus comment any other `<!`, `<?` or `</` opens, each hidden to the LATER of Markdown's
                            terminator and HTML's `>` and read on as HTML from that `>` -- read off the text AS
                            WRITTEN, since an element is literal whether or not some reading pairs a backtick
                            across its opening tag. EVERY tag is read, as an HTML tokenizer reads one -- a quote
                            opens a value only after a name's `=`, a value never closed takes the rest, whitespace
                            is HTML's own five characters rather than `\s`, and a name is folded in ASCII alone --
                            so a closing tag in another tag's markup, a comment, or the bogus comment a `<!` opens
                            closes nothing, while an opening tag counts wherever it is found, since what shelters
                            it may be no tag as Markdown reads it; `report_prose.py` takes tag markup out through
                            the same reader, `TagEnds`, which remembers what one reading found unclosed so a text
                            of nothing but openers is read once. Opening tags are counted by name, so nesting
                            holds, and an element opened in another tag's markup is literal from where that markup
                            began; a CLOSING tag is trusted only where it stands in the same possible code, or the
                            same prose, as the tag that opened the element under every reading -- each span is asked
                            apart, since two that overlap may come from readings that each hide one tag only; and an
                            OPENING tag or comment opens nothing in DEFINITE code -- a certain span or a definite
                            fence -- since a tag quoted as an example is no tag, unless an element is already open,
                            where no Markdown is read. A tag is found by its opener and read to its end only once
                            it counts: a quoted one is passed over at its `<`, so one cut short inside its code
                            never takes a real tag after it as attributes, nor one right behind that code into its
                            name
    report_redelivery.py    whether a run that moved no head is ANSWERING a report this issue owes rather than
                            asking a question -- the debt, a finished report outcome, and a branch that carries
                            something, asked in the order that spends least -- which is the one reading that keeps
                            the reply an undeliverable-report park earns from being parked as a question again. It
                            sits apart from the recording beside it because it is a reading about a LATER run and
                            the branch it ran over
    report_records.py       the four additive pinned records one developer report goes through: the DELIVERED
                            report a completed run wrote before any of its code was published, the PENDING
                            transaction that report is bound into once a pull request carries the code, the
                            CURRENT report the pull request carries, and the HANDOFF receipt saying one
                            transaction finished. The subject the transaction and the CURRENT report share --
                            repository, pull request, branch, source commit, and the requirements revision the
                            run was actually handed -- is spelled apart, because it is the whole of what a
                            completion has to prove again. The other two carry parts of it rather than the group:
                            the delivered record names the one member the RUN settles, the requirements revision,
                            and nothing a pull request decides, and the handoff keeps the pull request, the source
                            commit and the workflow LABEL the issue was carrying when the settlement landed beside
                            its receipt: what it has to answer is whether THIS transaction is already done, and --
                            for a route whose bookkeeping includes a hand-back its own stage has to make -- whether
                            that stage was ever standing behind it, which no other record reconstructs afterwards.
                            `HandedRun` beside them is no record at all: what a caller
                            tells the recording about the run -- the road it came down, the requirements revision it
                            was handed where the caller took a snapshot, and the round, bookmarks and consumed
                            readers its handover owes where nothing behind that caller will carry them: a report
                            that is the whole handover passes no size gate, and the feedback it answers may not read
                            as answered until it lands. The MARK a fixing round's own settlement raises rides that
                            last group and is spelled here because every settlement writes it -- put up by a fixing
                            record's frozen spends, retired by every settlement that froze none, so the mark and the
                            handoff beside it are always about one transaction
    report_record_values.py what each recorded field may be, and the widths two of them are bounded by, published
                            because a record written before its publication exists has to reserve the room that
                            publication's subject will take: a receipt spelled the way the published report header
                            carries it, one repository slug, one ref-shaped branch, a number inside the range
                            GitHub issues its identities out of, and a report that says something, fits a comment
                            with headroom to spare, and quotes no receipt marker of this orchestrator's. Text is
                            held to what UTF-8 can carry rather than to what `str` can hold, since a JSON escape
                            spells lone surrogates every pattern here would pass and the digest that hashes a
                            report would raise on
    report_consumed_values.py the bookkeeping a recovered record may write, per key and per shape -- the delivery
                            watermarks and the requirements baseline a completion advances, read off
                            `prompt_delivery.py`'s own field names rather than respelled, plus the round and
                            bookmark fields it closes through the held-pair vocabulary. A group is read
                            all or nothing -- its members shape-checked before either table is asked, since a
                            recorded field name JSON wrote as an array would raise out of the lookup -- and the
                            watermarks are ratcheted forward only, which is what makes a replayed settlement a
                            no-op and what makes their ceiling load-bearing: a boundary no later comment can pass
                            leaves every human reply reading as already answered
    report_record_fields.py the groups more than one report record shares, read and written one way, so no
                            spelling can drift from another's: the subject and the location a transaction and the
                            settled report both name, and the routing and the mode's own half a delivered report
                            and the transaction it becomes both carry. The transaction's whole pinned object is
                            spelled here too, beside the groups it composes, since the subject is the only thing it
                            adds to the report a run delivered
    report_record_reading.py what one recorded object reads back as, for both outstanding records: identity,
                            routing, and the half its own mode owns, each refused whole rather than partly. A
                            delivered report is the same reading with the subject left out, since a report
                            waiting for a pull request names none
    report_record_state.py  the pending record's round trip, with presence asked apart from meaning -- a damaged
                            record and an issue with nothing outstanding are the same absence to the reader and
                            opposite answers to the guard -- and a write refused rather than truncated when its own
                            reader would not hand the record back, or when either the comment it writes or the one
                            its settlement would leave is past what GitHub accepts. That second payload and the
                            fit test over it are published as a pair, because the publication asks them again on
                            the tick it would settle: a record that stands down lets the routes behind the guard
                            write to this same comment, so the room proved at acceptance is not the room the
                            settlement has. It is the
                            WHOLE settling write -- the watermarks it advances, the bookkeeping it closes, the two
                            records it adds, and the comment-id ledger entry that publishing the report leaves
                            between the two, reserved under an id that ledger does not already hold since its
                            writer is idempotent. A record whose own spends RAISE the fixing mark reserves the
                            hand-back behind it too, through that stage's own writer
                            (`stages/fixing/round_marks.py`): a settlement cannot move a label, so the round such
                            a record closes is handed back by the tick after it, onto the comment that settlement
                            leaves -- and unreserved, a transaction is accepted at the ceiling, settles, raises the
                            mark, and meets a hand-back GitHub refuses, with the mark raised and no later tick able
                            to relabel. Only where those spends raise it, since no other route writes it. The code-publication receipt is reserved in BOTH measurements
                            beside it, since a record written before its commit is pushed waits for the publication
                            gate and that gate writes onto this same comment -- reserved at the widest that receipt
                            records, and measured in BOTH worlds, since the reservation replaces what is there and a
                            comment can carry a receipt wider than any spelling this build writes. The settling
                            LABEL is reserved beside them at the longest spelling the vocabulary has, since which
                            one a settlement lands under depends on where the issue has got to by then -- a question
                            no record can answer for itself, and one the real write answers with something no wider.
                            The reviewer round the settled report is handed to is reserved in the settled world
                            too, since it writes onto this same comment -- its spec and subject, its launch
                            charge, its session and return time, and its approval -- replayed through the
                            validating stage's own writers at the widest each is written
                            (`stages/validating/review_records.py`).
                            All of it is
                            replayed through the owners that perform those writes rather than allowed for by a
                            margin, so a field added to any of them moves this refusal with it. The two later
                            writes are published as one world builder beside the round trip -- that receipt, and
                            the stale-approval hand-back `in_review` makes when a requirements edit sends an
                            approved pull request back -- because the delivered record written ahead of the same
                            push is measured against both, each for the roads that make it
    report_delivery_state.py the delivered report's round trip and the write that BINDS one: presence asked apart
                            from meaning as the transaction's is, a record refused rather than truncated where
                            this owner's reader would not hand it back or the comment could not carry it, and the
                            binding composed on a copy so the drop of the delivery and the record of the
                            transaction land together or not at all -- two records claiming one report are two
                            reports the next tick would publish, and a drop with no transaction beside it is a
                            finished run's report lost. Acceptance also reserves what the TRANSACTION will cost,
                            since the binding happens after the push and a report refused there is one the code
                            went out without: the subject it will be bound to is unknowable then, so the
                            reservation is taken at the width every member of one is recorded at -- except for a
                            verification, held to its own location's pull request, which is the number the
                            transaction has to be about and a refusal no width could prevent. The BRANCH is
                            reserved at the width the comment RENDERS rather than at the count its reader bounds:
                            codepoints are what the field is bounded in, and the comment is measured in the
                            characters a JSON escape spells them as, so one outside the BMP costs twelve and a ref
                            bounded at 256 can occupy 3072. All of it measured over
                            the comment that binding LEAVES, since the exchange gives back the room a delivery
                            being replaced is holding and costs the `null` its drop writes. The record's OWN write
                            is measured in four worlds beside that one -- this comment, and this comment carrying
                            the code-publication receipt, the stale-approval hand-back, or both -- because what
                            stands between the record and the binding is the push and, on the `in_review` drift
                            road, the hand-back behind it; both write here. The hand-back is reserved for the
                            ROUTE the record names, since `in_review` is the only stage that makes one: charged
                            for a write its own road never makes, an implementation's report near the ceiling
                            would be refused for room nothing was going to take. They are a different world from
                            the exchanged one: the delivery ADDED to everything the issue already carries, a transaction
                            an earlier publication left outstanding included. The subject a binding
                            takes is held to the requirements revision the delivery froze, and one restating it
                            differently is refused with nothing staged: bound, the transaction would claim the
                            report answers content the run never saw. A refusal SAYS which
                            it was, by offering the same transaction to an empty comment: accepted there the record
                            is sound and this comment is full, which the routes behind a report still owed give
                            back, and refused there no comment would ever hold it
    report_delivery.py      the report one finished run earns, recorded before its code is published: the outcome
                            read off the run, the revision minted one past every report this issue has already
                            recorded -- the settled one, any transaction still outstanding, and any delivery still
                            waiting to be bound, since a receipt is spelled from the revision and a retry finds its
                            own comment by it -- the requirements
                            revision the run was handed rather than one computed now, which is the snapshot a caller
                            names on its `HandedRun` or else the pinned baseline the drift check left before the
                            spawn, and the route its caller names. The write is this owner's, because being durable
                            before the size gate and the push is the whole of what makes the report recoverable.
                            The round, the bookmarks and the readers the record carries are the caller's frozen pair
                            JOINED with those of every record this one SUPERSEDES -- the outstanding transaction and
                            the unbound delivery, oldest first, so a field two of them name keeps the newest reading
                            of it. Nothing an outstanding record owes has been written anywhere, and this record
                            replaces it, so a report minted on its own caller's pair alone settles leaving a round
                            nobody spent, bookmarks nobody cleared, and feedback a developer already answered reading
                            as fresh -- which is what a requirements-drift resume superseding an unsettled fix
                            report would otherwise do.
                            TWO ways a run holds the tick instead, both parked under `report_undeliverable` and
                            both before the size gate and the push, so nothing is published and the commit stays
                            in the worktree. A report this build cannot RECORD is one no later tick could publish
                            either -- the record is the only thing a publication reads a report from, and the run
                            that wrote it has ended. A run that COMPLETED and handed over no usable report at all
                            -- no marker, a malformed one, a verification on another repository -- is the contract
                            every developer prompt teaches being broken, and published anyway it would send a
                            reviewer an implementation nobody described -- and a verification whose repository this
                            build could not hold against its own is held the same way, whether because it names
                            somebody else's or because the reading that would have proved it could not be taken:
                            that reading completes a repository PyGithub may hold only a URL for, and raised out of
                            here it would leave a finished run's report neither recorded nor parked. Either notice
                            names what its own road held back: the implementing seam publishes for the first time
                            and has no pull request yet, while a resume under review has one that stands on the
                            commit it stood on, so the initial wording there would deny an open pull request its
                            human is reading. A run that did
                            NOT complete is left
                            alone: a launch nothing invoked (which is every synthesis an implementing recovery
                            makes for a publication no developer ran), a shutdown kill, a timeout, a provider
                            refusal, a nonzero exit -- `INCOMPLETE_RUNS`, public for the stage that remembers which
                            commit such a run left. The park is announced once per attempt -- while it still STANDS -- with
                            the notice worded by whichever road took it, and it is retired the moment a report IS
                            recorded. It also carries the input the caller said the run's prompt delivered into its
                            OWN write: a park durable over feedback still marked unread is one the next tick reads
                            as fresh and resumes the developer over again, with nobody having replied. It is bounded like every park ending a run, so a reply written while the
                            agent was out stays unread under its notice. `owes_a_report` beside it is what the implementing publication asks before
                            it hands work on: both records asked as a CLAIM so a truncated one counts as a debt, and the
                            park, which writes `developer_report_owed` beside its reason so the debt of a road with
                            no record to leave outlives any later park that replaces that reason -- and onto an
                            older park still standing with the reason alone, with no second notice. A park already
                            saying everything the notice would still WRITES: what a caller staged into the same
                            state -- the consumed pairs, and a record the road behind them released -- is what
                            that write is for, and skipping it would tell the caller the tick ended while the
                            comment still carried both. Both holding
                            roads write `UNREPORTED_WORK` as well, which is the narrower fact the debt cannot
                            carry: these commits are undescribed, whatever record an EARLIER run left, and only a
                            report recorded over the branch as it stands retires it. `OWED_ROUND_RESET` is the
                            third, and the only one no road here writes: the fresh review budget an `in_review`
                            requirements edit earned, recorded by that stage's hand-back where the publication the
                            edit produced is still owed, read by `stages/validating/rounds.py` so the delayed road
                            spends none of it, and retired with the debt by the settlement that ends it. And
                            `redelivers_an_owed_report` is what both implementing dispositions ask of a run that
                            moved no head -- a debt owed, a run that finished on a report outcome, and a branch
                            that carries something -- so the reply answering such a park publishes rather than
                            parking as a question. The implementing publication seam is the caller, between its
                            tree reading and the size gate, and so are the two dispositions an open pull request's
                            fix loop runs ahead of that same gate -- the requirements-drift one both review stages
                            share (`stages/validating/drift_reports.py`) and the reviewer-requested one the
                            `workflow:fixing` label covers (`stages/validating/fix_reports.py` for the round
                            `validating` spawns, `stages/fixing/reporting.py` for every round behind it), which is
                            why the label is one of the roads whose park notice says the pull request stands where
                            it stood rather than that none was opened. A caller may freeze the bookkeeping its handover
                            owes onto the record as well as onto the gate, which is what covers a report reaching
                            the pull request with no code in it and so no gate behind it
    report_settlement_state.py the current report and the handoff receipt, written in the one durable write that
                            drops the pending record, each refused rather than stored when this owner's own reader
                            would not hand it back. The handoff also names the workflow LABEL the issue was carrying
                            as that write landed, because the reconciliation making one runs ahead of every handler
                            on every non-terminal label: a route whose bookkeeping includes a hand-back its own
                            stage has to make cannot otherwise tell a settlement that stage is standing behind from
                            one taken while the issue was somewhere else. Additive like the current report's road --
                            absent on a settlement written before the member existed, which every reader holds to
                            the stricter answer, and damage where it is present and names no label, `null`
                            included. Nothing here CLEARS a settled record -- a settlement replaces
                            one -- so either key is claimed by its presence alone, `null` included, which is the
                            one place this parts company with the pending record whose ordinary resting state that
                            is. What produces one is a publication that reached its report -- the initial
                            implementation delivery through `report_binding.py` below, or the reconciliation at
                            the end of this group a poll later -- and `dev_pr.py`'s body asks
                            `carries_settled_record` before writing the run's closing message
    report_locations.py     which places on a pull request this issue's reports claim, asked of all three records
                            -- a record nobody can read, or a settled pair missing its current report, included --
                            since even an edit keeping every word moves a verified DESCRIPTION off its digest, while
                            a report in a comment is out of a body edit's reach. A damaged record claims the
                            description unless the place it still names is readably elsewhere. The second reading
                            is what a description has to say: whether it closes this issue -- any spelling GitHub
                            accepts, bare or qualified with this repository, outside everything `report_prose.py`
                            takes out, ASCII from end to end, its number compared as digits -- and names the
                            session; `costs_the_description` is that answer held against a verification living on
                            the same description. It also answers which publication the SETTLED pair is about,
                            agreeing with itself and naming this repository, pull request, branch and commit; what
                            it hands back is a claim, for its caller to re-read. Asked by `report_binding.py`,
                            `stages/implementing/pr_description.py` and `stages/implementing/unreported_recovery.py`
    report_evidence_models.py the four answers one reading gives: PROVED, which alone licenses a publication and
                            alone carries the pull request it proved; HOLD for a reading nobody could take; DEFER
                            for everything structural, which the routes behind the evidence are what clear; and
                            ENDED for a pull request that is over. The vocabulary heads the four evidence owners
                            below, which the reconciliation at the end of this group composes into one tick
    report_evidence.py      the affirmative evidence a completion needs, in two entry points: the pull-request
                            reading, which every other one stands behind, and the rest composed behind it cheapest
                            first. The requirements revision closes it, held against the one the run was handed and
                            COMPUTED here rather than read, so the comment walk that computes it answers with a
                            hold rather than leaving the reading by an exception. That last reading is published on
                            its own as well, over an issue read AGAIN from GitHub, for a caller completing the
                            publication it has just made: the issue it holds was fetched before its developer ran,
                            and a re-read that fails answers HOLD, since nobody could say the issue is unchanged.
                            That fetch hands the ISSUE back beside the verdict, for the settlement that stamps its
                            handoff with the label the issue is carrying -- one question, so one fetch.
                            `refuses_for_good` says, posting nothing, whether an owed transaction can ever settle: a
                            report of ours a human edited, or a verified location gone, changed or untrusted
    report_checkout_evidence.py the checkout half: on this host, clean by a reading that HAPPENED rather than by an
                            empty path list, and standing on the commit the report is about
    report_remote_evidence.py the remote half, which the checkout cannot answer: the recorded branch is fetched and
                            one divergence reading decides all three of unpushed commits, a remote that moved on,
                            and a tip that is not the commit the report is about. The branch asked for is the one
                            the record FROZE, since the whole point of freezing it was that a later tick's answer
                            can differ
    report_publication_evidence.py the pull-request half: the repository, then ONE pull request read by the number
                            the record froze, still open, on the recorded branch, with a head in this repository
                            and STANDING on the recorded commit. Selected by number rather than searched for by
                            commit, because a number is unique in a repository and a search is not -- several pull
                            requests can stand on one branch carrying one commit, and a search answering with
                            whichever it reached first would refuse the transaction forever while the recorded
                            thread sits open on that very commit, and would hide an ending besides. A read that did
                            not happen HOLDS, the lazy members included. The code-publication receipt is asked
                            beside all of it, as one group through the receipt's own damage reader and then on both
                            of its members, since standing on a commit says it is there and nothing about how it
                            got there. Both those owners are reached through `stage_targets.py`, resolved when
                            called
    report_replay_guards.py whether a record and the settlement beside it are about one thing. Either settled record
                            CLAIMED and unreadable stops the tick before anything is proved, since both are records
                            a settlement writes over. Two READABLE settled records are then held to each other,
                            without reference to any receipt: they are copied out of one pending record in one
                            write, so a pair naming two pull requests, two revisions or two commits is one nothing
                            here produced -- and under a previous transaction's receipt that is the only question
                            there is, since such a pair is never compared against the record in hand. A handoff
                            carrying THIS receipt is believed only beside the current report written with it, once
                            its own pull request, commit and revision agree and once that report matches the pending
                            record's whole subject AND the content that transaction would have left -- a
                            publication's own digest at a location that IS a comment, a verification's own exact
                            location and revision -- which is the only half of a settled record that says which
                            report actually landed and where. The road is held first wherever the settlement
                            names one: a settlement saying it verified is no completion of a publication, and one
                            naming no road, written before any did, is held to the content alone. A `null` comment
                            field is the pull request's description, which a verification records and a
                            publication never writes. Believed on
                            the receipt alone, or on the digest without the kind of place beside it, it would drop
                            a pending record whose report was never published. A current report
                            already recorded at this revision or a later one says the transaction in hand is stale,
                            which settled would replace the newest report on the pull request with an older one.
                            None answers with a repair: a caller that finds the records disagree stops, because
                            choosing between them loses something unrecoverable
    report_publishing.py    the two ways a proved transaction finishes -- a receipt-scoped post that a retry finds
                            rather than repeats, and a re-read of a trusted location whose content still hashes to
                            the revision verified -- and the one write that settles either, composed whole on a copy
                            so that a settled writer's refusal lands none of itself rather than dropping the record
                            beside a report nothing says the pull request carries. A refusal short of PRESENT is
                            split the way the evidence beside it splits one: only a read nobody could take stops the
                            tick, while an edited report, a deleted one, and an untrusted author are definite
                            answers about content a human owns and stand down onto the routes behind the guard.
                            The landed comment id and the verified report's author are read under boundaries of
                            their own, since each is a lazy member that can fail on a worker holding an uncompleted
                            object -- and an author nobody could read HOLDS rather than standing down, because it
                            is not an author this deployment refuses. Both roads prove the room first: the
                            settlement is re-measured against the comment as it stands before anything is posted,
                            since what the record reserved may since have been spent by the routes a deferred
                            transaction let run -- and the REQUIREMENTS last, over the issue read afresh after the
                            request, since a post is long enough for an edit to land under it. Each settlement
                            records which road made it, for the re-read below, and which LABEL the issue was on as
                            it landed -- read off that fresh issue rather than off the copy in hand, since a human
                            who relabelled while the developer ran is invisible there, and fail-closed, since the
                            labels are a lazy read and a settlement raising out of that line would leave the report
                            published with the transaction still outstanding. The fixing MARK is REPLACED by the
                            same write, never merely left: retired first and put back up only where this record's
                            own frozen spends carry it, so a mark an earlier settlement raised elsewhere cannot
                            outlive the handoff it was about. And it retires what the transaction
                            it ends is still recorded as owing: the debt, the fresh review budget an `in_review`
                            edit reset for this publication, and the undeliverable-report park itself where that
                            park is the one this settlement answers. Conditions like it are
                            repaired rather than replied to -- an edited report restored, a checkout cleaned -- so
                            the settlement is the only thing that would ever end the wait, and a debt outliving it
                            would hold the reviewer over a report the pull request carries. Any other park reason
                            belongs to whoever took it and stands. NOTHING is retired at all while the issue
                            records work nobody has described: a report written over the branch as it stands
                            retires that flag as it is recorded, so one still standing says this transaction was
                            written before those commits existed -- a true account of an earlier head, and no
                            account of the head the branch is on now
    report_settled_reading.py a SETTLED report read again where it settled, posting nothing, and held to the
                            road the record says settled it: a VERIFIED location has to hash to the digest still,
                            under a trusted author; a PUBLISHED one has to re-render in its comment as our report,
                            written by the login this client posts under, with the text digest and whole header
                            (pull request, commit, requirements, revision, receipt) recorded -- so a comment cut
                            down to its bare text is CHANGED though it hashes. A record naming no road is read off
                            its location: a description was verified, a comment is held to the rendering. An
                            author nobody could read is UNCONFIRMED, and so is a published comment whose body will not
                            read again for its parse. `stages/implementing/report_handoff.py` asks it last before a
                            handoff, for the report a publication settled and for the one a recovery would hand on.
                            `carried_text` takes the same reading and returns the TEXT as well, the settled revision
                            alone -- a publication's words out of the very parse whose header the reading proved, a
                            verified location's whole body -- held to the digest once more, "" on every answer but
                            PRESENT; `stages/validating/review_report.py` asks it before a reviewer is handed the
                            report
    report_binding.py       what a publication does with the report its run delivered once the push has landed:
                            the record bound to that repository, pull request, branch and commit in one write made
                            BEFORE anything is posted, then published. Both steps on every call, held to the
                            publication in hand, so a record naming other work is the reconciliation's. The
                            REQUIREMENTS are proved afresh first, and a report answering an edited issue is left
                            owed for the drift resume. Nothing is DISCARDED: a comment too full is retried; a record
                            nobody can read, a verification on another pull request, and one on the DESCRIPTION this
                            publication needs park once under `report_undeliverable` with the record intact -- that
                            last the collision, held for a human to name the description, since nothing here
                            rewrites one. A transaction the settled pair beside it refuses is left owed, for the
                            reconciliation to park. The implementing publication calls it, through
                            `stages/implementing/report_handoff.py`, once its push has reached a pull request; the
                            review stages' `stages/validating/report_settlement.py` calls the binding step alone,
                            `binds_the_delivery`, and leaves the post to the reconciliation's full evidence
    report_transaction.py   the reconciliation the dispatcher runs ahead of every handler, behind the pause,
                            terminal, outstanding-publication and adjudication guards and ahead of the reuse guard
                            and the stage: it hands work that has ENDED straight back -- a closed issue, or one
                            wearing `done` or `rejected`, since a terminal label resolves to no handler and the
                            no-op behind this guard protects nothing -- then settles what it can prove, holds what
                            nobody could read, stands down on what a route behind it would fix, retires a
                            transaction whose pull request is over, and parks once on a record it may not act on:
                            one that will not read, a settled pair that contradicts itself, one whose handoff
                            disagrees with it, and one a newer report has already passed. That park is its own to
                            take and its own to retire -- the record repaired and settled, or the field cleared to
                            abandon it, both take the flags down, and no other owner's park is ever touched. A park
                            another route already holds STANDS THIS DOWN rather than holding in front of it: what
                            answers one is the handler behind this guard, so a hold there would leave both parks
                            standing for the life of the issue with neither announced, while a stand-down lets that
                            handler run and takes this park on the tick after its own clears
    pickup.py               an unlabeled issue's first tick: the author allowlist, the `DECOMPOSE` route, and the
                            greeting / hash / label / state order a start publishes in. The greeting anchors both
                            `pickup_comment_id` and `last_action_comment_id`, the floor the park ending the first
                            agent run walks from, since the spawn it opens quotes this thread as it stands
    prompt_notes.py         shared empty-context placeholders, foreground execution and AGY asynchronous-command
                            instructions, the commit-subject contract every prompt that may author one carries -- mirror
                            the repository's own recent history rather than any enumerated prefix set, and write the
                            descriptive subject alone, since the ` (#N)` suffixes in that history are the publication
                            metadata the orchestrator appends for the pull request and the tracked issue's number is
                            never one of them -- the developer report contract spelled from the report vocabulary with
                            its fresh-respawn counterpart, and the continuation notes for a session-limit retry
    prompts.py              implementation, documentation, fixing, conflict-resolution, and fresh-session prompt
                            builders; each response marker agrees with the parser that settles its stage
    review_prompts.py       the fresh reviewer's prompt and the handover it is built over -- the backend that
                            implemented the work and the subject the validating stage resolved -- with the developer
                            report quoted whole between the issue and the inspection commands, named by revision and
                            location, and a note where the requirements have moved on since it was written; a subject
                            with no report says none is recorded
    review_subjects.py      what one review is of -- pull request, head, requirements revision, and report revision
                            and digest -- recorded as `review_subject` before the spawn and as
                            `review_approved_subject` once an approval passes the verify gate, where recording the
                            approval also retires the head-keyed `docs_verdict` and `ready_ping_sha` an earlier one
                            left; the widest subject either record can be written at (`ReviewSubject.widest`),
                            which the report settlement's measurement reserves; and the question every
                            later reader of an approval asks, whether the report recorded as current is the one it
                            covered, compared on the pinned records alone. An approval with no record covers only an
                            issue with no report either -- one approved before the record existed over a pull
                            request that has settled a report goes back for a fresh review -- and a record nobody
                            can read covers nothing: it is read whole, exactly the five members its writer spells,
                            each in its shape -- requirements that are a digest or "", both report members or
                            neither, a whole commit id as the head wherever a pull request is named, and neither a
                            head nor a report where none is -- or neither its identity, its head, nor its
                            requirements are read
    conversation_prompts.py question, discussion, PR-feedback follow-up, and developer human-reply resume prompts;
                            discussion publication instructions describe the confirmed plan artifact and the commit
                            its stage verifies
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
                            than additive, so the same command read twice buys the same ceiling -- takes that park
                            down and puts back the park the refused launch was on, so a resume refused on a reply
                            is resumed on that reply, consumes the batch it read and the answer it wrote under it
                            (never a comment that arrived between the two: the boundary is built from ids this
                            tick observed rather than re-read off the thread, and nothing at all where the batch
                            begins below a notice of ours, over replies a refused resume was handed), and
                            lets the tick reach the stage its label names. Every other
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
                            phases, and the pinned park fields; `DisplacedPark` is the park a run-limit park goes up in
                            front of, read off the standing flag and reason (the run-limit reason itself reads as
                            none) and back off its `agent_run_limit_displaced` record, which anything missing or
                            malformed reads as no park
    run_limit_state.py      the standing lifetime-limit park and its owed sentence; changed ledger coordinates replace
                            the notice, and settlement clears the sentence without lifting the park or changing the
                            charge. Taking the park records the park it stands in front of, read off the durable
                            state the circuit refused on, and `_restore_displaced` is how the grant puts that one back
    run_limit.py            persist a supplied exhaustion reading before its budget event and notice, reconcile
                            bot-authored delivery, and replay the sentence still owed; this owner grants and spends no
                            additional run. The notice is a bounded park and its repair walks the same way, entering
                            the found notice in the id ledger first, so replies a refused resume froze stay unread
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
                            and then read by the owner that knows what it is -- the rounds, the cleared bookmarks
                            and settled heads, and the one MARK a record may put up, which may only ever be raised,
                            since what takes one down is the route that reads it
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
    collapses.py            the three terms a squash says it is about to replace, written before the reset that
                            destroys them and deliberately outside the group a cleared generation drops: the head
                            being replaced -- the rollback target, and the head the force-push behind it is leased
                            against -- the base it is rewritten over, and how many commits go in, which is the one
                            fact no reading past the rewrite could recover, what the walk proving the record is
                            held to, and what the handoff's notice is worded from. The wire names are a
                            compatibility contract live issues already carry, so one record covers every rewrite
                            this workflow makes: a collapse of several commits, and the subject rewrite of a
                            one-commit branch, which records a count of one and is the shape whose interruption
                            the branch itself cannot show at all. Read whole or not at all, so a missing member,
                            an end that is not a whole object id, and a count no squash replaces -- zero replaces
                            nothing -- each read back as no pending collapse, while
                            CARRYING one of those is a separate question the recovery has to ask, since a comment
                            claiming a rewrite it cannot produce describes a branch that reads as having nothing
                            left to do. What ENDS one is here too, and the write that does hands what it leaves
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
                            classification. The body edit quotes one frozen read of the issue thread and settles
                            that record -- the comments and the requirements revision alike -- once the run is back
                            and only for an outcome that reached an agent; it reads no pull-request surface, so
                            none of their cursors moves. Each of the three can end in a commit this stage publishes onto a
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
                            values handed between the stage's owners; a body-edit resume's result carries the
                            delivery record its prompt was cut from, since the thread moves while an agent is out
                            and a mark taken off the one it returns to crosses replies nobody delivered
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
      late_run_reading.py   read the pinned role, locked spec, session, source pair, and validated verdict payload,
                            with a rationale only beside a `single` or `split` and within its bound, absent otherwise;
                            recover adjudications and resume only a session bound to this candidate generation
      late_result_payloads.py
                            encode verdicts, bounded rationales, and child estimates, and measure the actual
                            serialized pinned payload against the whole-comment budget with notice headroom
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
                            notice, worded on the operator whose authorization is the only road here and quoting
                            the decomposer's rationale off the record through `late_notice`'s fencing, with a
                            display-only stand-in where the record holds none a reader can use, and the
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
                            human decision a `single` requires and the explanation it owes for it, the optional
                            rationale a `single` or a `split` keeps apart from that explanation, with the length the
                            record cuts it at read off `late_result_models`, the dependency-ordered slices and
                            dormant prerequisites a split has to consider before that answer, what every child body
                            owns, and the addition budget each child declares under this generation's own ceiling
                            -- the figure its own JSON template shows scaled to that ceiling, since a template is
                            copied verbatim and a standing one would be a child the reply contract refuses wherever
                            the ceiling is narrower than it
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
                            with, quoting the issue as it reads NOW, carrying the developer report contract, and
                            asking for the `ACK:` marker an UNCHANGED commit needs before it counts as an answer,
                            offered only while the report needs no change either. The two entry points are this
                            owner's own --
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
      late_result_models.py late-run identity, adjudication answers, guarded splits, and settlement dispositions, plus
                            the rationale bound, its truncation marker, and the two verdicts that keep one; an
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
                            taken from the plan commit's own subject the way a dev PR's is -- the tracked issue's
                            own trailing reference dropped off it by the title owner under `git/publication/` --
                            the body that names that session and says what merging or closing decides, and the
                            refusal of a plan no session can be named for
      records.py            what a finished publication writes down: the adoption of a PR already carrying the
                            commit, and the plan path, branch, number, PR head, and moved round anchor one durable
                            write leaves behind
      parks.py              the funnel every way the stage hands the issue back goes through, which stamps each
                            park's reason, restores the consumed ceiling, and builds the bounded correlation the
                            park reports: the road off the tick's own record, the role, the pinned conversation,
                            the plan's own pull request -- read as the round gate reads it, so a developer's pull
                            request the issue merely arrived carrying is not reported as one -- and the commit the
                            artifact stands on, the in-flight marker ahead of the published record since the two
                            can both be pinned and only the marker is a claim about the publication this park is
                            about
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
      models.py             the run and the road it opened on, the agent identity and session, the prompt and its
                            replies, the round, the outcome, and the publication artifact
      state.py              the park reasons and wire keys, the plan path and the commit its PR carries, the
                            open-round and in-flight publication markers, the three park predicates, and the
                            stage, role, and two route names a record is attributed by
    documenting/            `workflow:documenting`
      handler.py            the order one final-docs tick asks its questions in
      preconditions.py      the terminals, the missing-`pr_number` guard, the parked-no-input fast path, and the
                            refused bare continue -- classified over the batch written since the park ASKED, which
                            on a half-finished drift unwind is that road's own notice rather than the delivery
                            cursor it holds back: read from the cursor, the instruction nobody delivered would
                            demote the command to guidance and the reconcile would re-run on an operator's nudge
      run.py                the branch refresh and diverged-worktree guard, the verdict an earlier pass left dropped
                            as this one begins -- every shape re-anchors the checked head, so a stale verdict beside
                            it would advertise a head no pass has documented as ready to merge -- plus the resume,
                            recovered-commit, and fresh-spawn shapes
      outcomes.py           the timeout / dirty / commit / `DOCS: NO_CHANGE` order a finished run is read in
      subject.py            the single ` (#N)` reference the docs commit's subject is normalized to end in under
                            `PR_REF_IN_SUBJECT`, ahead of the gate. Both numbers this pass knows -- the tracked issue's
                            and the pull request's -- go to the shared `git/publication/pr_references` owner, so the
                            issue's own reference is dropped, alone or from beside one an earlier publication
                            appended, and the line ends in exactly one reference to the request. The amendment is a
                            new commit bound to the one this pass read rather than to HEAD, so a checkout something
                            committed on meanwhile refuses it, and the replacement it creates -- handed on only once
                            HEAD reads back as standing on it -- is the only id the gate, a hold's receipt, the push,
                            and the stamp may name. Only the subject's own text changes, its line ending and the rest
                            of the message kept as written; a subject the normalization hands back as written is
                            published as the commit it is, and a message that does not read, a replacement git
                            refuses, a moved checkout, or a HEAD that does not read back as the replacement parks
                            `subject_amend_failed` rather than publishing it
      publication.py        the size gate a docs commit passes -- the last one before a human is asked to merge,
                            and handed the commit this pass made so a checkout something moved is refused rather than
                            measured in its place -- then the push, the docs watermarks it stamps, and the PR notice
                            it posts; a commit the gate held and one it let through leave the same receipt, the head
                            the handoff is still owed for, and the handler finishes from that only over a checkout
                            standing ON it, since in sync with its remote is what a replacement host rebuilt at a
                            moved pull request reads as too -- the write that records the pass drops it, so no
                            receipt outlives the handoff it was written for
      drift.py              a body edit mid-hop: the dropped approval, the unwind sentinel, and the relabel to
                            `workflow:validating`. No developer runs on this road, so nothing about the conversation
                            is recorded -- the requirements revision alone goes down, and it says only that this
                            stage has already rerouted for the edit. A git step that cannot be proved parks through
                            the shared HITL helper, which stamps the thread read as far as its own notice, so this
                            owner puts the delivery cursor back and keeps that notice as the unwind's own boundary:
                            the silence a pending unwind holds is measured against it rather than against a cursor
                            that would read the triggering comment as a retry signal every poll
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
      parks.py              the shared awaiting-human park and the missing-PR, dirty-tree, and question parks, plus
                            the hold a park taken during a drift unwind applies inside its OWN write: that road
                            runs no agent, so the delivery cursor goes back where the tick found it and the notice
                            just posted is kept as the unwind's boundary instead -- a correction in a second write
                            is one a crash between them loses, and it loses it in the direction that waits forever.
                            `_asked_since` is the reader half, and it is what every road classifying a parked reply
                            asks so the two boundaries cannot be confused for each other
      models.py             the frozen records the owners hand each other, including the one reading of a finished
                            run three of them branch on -- whether it ended on a report -- taken where the run is
                            built rather than parsed again by each
      state.py              the pinned-state keys they share, the unwind sentinel and the boundary its silence
                            is kept behind among them -- the second is no delivery cursor, since the road that
                            writes it runs no agent at all
    fixing/                 `workflow:fixing`
      handler.py            the order one tick asks its questions in, plus the preflight terminals, the
                            missing-`pr_number` park, and the commit the no-feedback bounce publishes -- measured by
                            the same size gate the shared dev-fix publication passes, named BOTH ends of the
                            reading that placed it so a checkout something moved refuses instead of having
                            whatever it points at pushed, and a held candidate stops the
                            bounce rather than being relabelled over -- before it hands the PR back to the reviewer.
                            Ahead of the scan, everything this issue's report obligation owes
                            (`report_recovery.py`): a round whose publication SETTLED while nobody was looking is
                            handed back, and a record a crash left unbound is re-proved and bound. That position
                            is the point -- the input a dead tick consumed rides the same record, so a scan
                            running past it reads that feedback as unread and pays a second developer to answer
                            it. The nothing-to-act-on exit behind the scan answers to two readings for the same
                            reason: watermarks that already cover the batch, and a report the issue OWES whose
                            own frozen pairs cover everything the scan found. Either way the bounce publishes
                            whatever is stranded, BINDS the report that push is the publication for -- on the
                            commit the receipt of that attempt names, never the standing value -- and hands the
                            round back; while a report is still owed over a branch PROVED to be carrying nothing
                            to publish it holds the relabel, the bookmarks and the round instead, and announces
                            the wait nothing left can end. A branch the stranded reading could not PLACE holds
                            the same three AHEAD of that, under `stranded_unproved` and a notice naming which
                            reading refused: every refusal reads identically to an empty branch, and this exit
                            is the last tick that would publish a commit. That park waits on a READING rather
                            than on a person, so a quiet poll arrives back here with the flags untouched, takes
                            the reading again, and hands the round back on the first one that places the branch
                            -- publishing a report owed for that commit on the same push -- while a refusal that
                            repeats holds again without a second notice. Ordered that way because a report owed
                            behind a refusal is owed a PUBLICATION: parked as a report no road can move, the
                            retry never runs and the reading coming back ends nothing
      feedback.py           the rescan past the three in_review watermarks -- read through that stage's own
                            per-surface owner, so the issue thread answers to the issue-only delivery cursor too and
                            the pull request never does (a bare `/orchestrator add-agent-runs` is no
                            feedback there, as in in_review) -- the quiet window a fresh batch settles
                            through before a resume spends the session on a fragment of it, and the settlement a
                            consumed batch earns: one reader per surface, derived through `engine/prompt_delivery.py`
                            -- whose classifier the two REVIEW surfaces are scanned through, since an item the scan
                            admits and the settlement refuses reaches a developer and moves no reader, so the next
                            tick hands the identical comment to a second one (the pinned record is dropped by
                            identity for the same reason). The issue thread settles the issue-action boundary
                            `last_action_comment_id` beside the PR-side cursor -- a reply this round quoted has been
                            in a developer prompt, and left behind it routes back to a second developer the moment a
                            human moves the label -- while the pull request's three surfaces settle only the
                            in_review watermarks that are theirs. The same pairs are offered FROZEN as well as
                            written, for the round that has to hand them to the report which answers its feedback.
                            The issue thread is read ONCE and the whole read is kept on the batch, because the
                            round owes that surface two more answers than the cut -- the conversation a retired
                            session is re-grounded on and the requirements a report is stamped with -- and a
                            second read taken later in the tick carries a comment the watermarks stop below.
                            While a report is OWED the readers say less than usual, so what says a batch has
                            already been delivered is the RECORD's own frozen pairs rather than any reader
      bookmarks.py          the `pending_fix_*` ids a replay rebuilds the triggering batch from -- each surface
                            apart, since the replay is delivered and so is settled -- and the clear each round earns.
                            The issue-thread half is CUT from the caller's own read of that surface rather than one
                            taken here, because a replay is part of the batch: a bookmarked comment edited or
                            deleted between two reads would reach the developer in the prompt while the requirements
                            fingerprint beside it never saw it, and the report that round writes is then one no
                            settlement can place
      resume.py             the dev run, whose head is read on BOTH sides of it however the run ended -- a timeout
                            is a way to commit like any other, and the road that holds a commit made over a standing
                            report record has to see it -- the three refusals that will not count one as a delivery
                            -- a launch
                            nothing invoked, a shutdown kill, a live pause -- the settlement of the batch every other
                            outcome DID deliver, the ACK fast path -- which stands down on any reply that USED the
                            report contract, well or badly: one that reported is a handover to a fresh reviewer
                            rather than a reason to re-arm a ready ping, and one that reached for the markers and
                            missed (a report block with an `ACK:` beside it) is a broken contract rather than an
                            acknowledgement to act on, and neither is a reply on an issue that already OWES a
                            report, which is a debt read off the record rather than off this run, and which asks
                            the branch PROVED to be carrying nothing unpublished rather than merely nothing proved
                            stranded, since the ack vouches for the feedback and the hand-back is a claim about
                            the branch -- the report
                            contract the resume is held to through `reporting.py`, the `workflow:validating`
                            relabel a published report earns, and the round a PUSHED fix spends here while a
                            report still owed leaves the round, the bookmarks and the readers to the write that
                            settles it. The gate is handed NOTHING to close while a report stands, for that same
                            reason: a receipt write that cleared the bookmarks would leave an outstanding
                            publication with no batch to replay and a round counted for a report that may still
                            fail to post, so a held candidate rides its record to the adjudication and the
                            settlement behind that publication closes it. The settlement is taken ahead of the disposition, so whichever
                            durable write comes next -- the size gate's receipt, a park's own -- carries it, and it
                            is taken for every outcome but one: a run that finished on a report outcome
                            (`engine/report_outcomes.py`) owes a publication this tick cannot promise, and feedback
                            recorded as answered for a report no reviewer has is the reading that fork refuses. What
                            carries that batch instead is the report's own record, frozen onto it beside the round
                            and the bookmarks, so the readers move in the write that settles the report -- and on
                            every road but that one the settlement is taken in this caller's write, because a pushed
                            fix answered the feedback in code the pull request now carries and a PARK answered it
                            with a notice a human is being asked to read. A
                            replay settles the batch it REPLAYED joined with the fresh rescan, each item against the
                            reader of the surface it was posted on
      reporting.py          the settlement-driven form of that road, which the resume above disposes every
                            reported round through. Which reply this is -- a report, an ordinary answer, or one that reached
                            for the contract and missed, an `ACK:` beside a report, which is held for a human rather
                            than acted on by either half; whether a round that committed nothing may publish onto
                            the head its pull request already carries, on the affirmative proof that the head read,
                            never moved, is the one the pull request is STANDING on, and left a tree proved clean.
                            Three readings there HOLD rather than answering -- a pull request reading this poll
                            could not take, a head the checkout would not name, and a tree status that established
                            nothing are about this tick and not about the round, so nothing is published and
                            nothing is parked -- while a head that moved, a publication this report may not go
                            onto and a tree PROVED to be carrying something are decisive, the last of them for the
                            terminal park in `report_recovery.py` rather than for the roads that wait on a reply,
                            and for every reported round rather than only the one with nothing to push: taken by
                            the push tail's own checkout park instead, one condition is announced twice. The record that
                            carries this round's consumed readers, its route bookkeeping, the requirements revision
                            its own spawn was handed -- never a baseline re-read after the run, which would fold in
                            every reply that arrived while the developer worked -- and the settlement MARK for the
                            write that completes the publication. The binding taken only on a commit the CALLER
                            proved, never on the persistent publication receipt, and held to the fresh reading in
                            `report_publication.py` that both those roads share. A request that FAILED is the one
                            refusal the answer names for itself, because a caller may spend nothing on it. Then the
                            park a report no road left can move earns, once -- beside the park a run that
                            COMMITTED and did not finish earns, in this road's own words rather than the
                            engine's, since nothing else publishes for such a run. The silent-park streak comes
                            down with the recording, the earliest moment a session has proved it can speak. Then
                            the hand-back, which retires the mark in a write of its own BEFORE the relabel -- a tick dying between them has to leave
                            a round nothing can mistake for one that just settled -- and STAMPS the transaction it
                            closed the round on, since the mark falls with that write and the handoff beside it
                            never does -- and which takes down the `push_failed` park a landed publication is itself
                            the answer to, since the push a recorded report rides is durable a step ahead of the
                            publication and a relabel over that park hands a reviewer an issue still waiting on
                            a human. That reason and no other: the rest of the transient set is about a SESSION or a
                            reviewer run, so a park a LATER round left would have its question retired by a
                            publication that never answered it
      report_publication.py the one fresh reading of the pull request those two roads take, spelled apart because
                            neither may carry a copy of it: answered twice they would come to disagree, and the
                            disagreement is a report on a thread nobody meant. It establishes the whole IDENTITY of
                            the publication, as `engine/report_publication_evidence.py` does for a transaction the
                            reconciliation is finishing -- still OPEN, since a thread somebody merged or closed
                            mid-run keeps the head it had and every other comparison passes on a publication that
                            is over; on this issue's own branch in THIS repository, since a number is all that
                            brought the object back and a second thread on another branch or a fork's carries this
                            repository's ref names over somebody else's commits while standing on the very commit
                            a caller proved; and STANDING on that commit rather than merely carrying it, since a
                            push landing between the proof and this reading leaves it in the history while the work
                            under review moves on. The DESCRIPTION comes back with it -- whether it still closes
                            this issue and names the session -- because the one report this workflow cannot both
                            keep and manage is a `REPORT: VERIFIED` naming that very body, and the binding refuses
                            it only if a caller says so. EVERY read is inside one boundary, the fetch included and
                            nothing only around it: a fetched pull request asks GitHub nothing, so the state, the
                            ref, the head repository, the sha and the body are each a request of their own, and the
                            client resolves its repository lazily too -- left outside, any one of them leaves the
                            reading by an exception rather than by an answer
      report_recovery.py    the other end of that contract, reached by the handler ahead of its scan and by the
                            parked dispatch behind it: what a tick coming back to one
                            of those windows owes, written for the position ahead of a scan because a scan is what
                            the damage runs through -- the input a dead tick consumed rides the same record, so a
                            scan running past it reads that feedback as unread and pays a second developer to
                            answer it. A round whose report SETTLED while nobody was looking is handed back on the
                            mark that settlement raised, never on the settling itself: a delivery is claimed by one
                            key whoever wrote it, so the record settling there can be an implementing candidate's
                            or a drift resume's, closing THAT route's bookkeeping and raising no mark of this
                            stage's. A record a crash left unbound is answered off its own pairs, and whether the
                            code went out is RE-PROVED against the checkout rather than remembered off the
                            persistent receipt -- a tree provably clean and a head it could name, with where that
                            head stands left to the binding, which reads the pull request afresh. A record nobody
                            can READ parks with the record untouched, since the debt is claimed by the key alone
                            and reading it as an absence would let the scan behind it through. The two refusals no
                            later poll takes back, a worktree that is GONE and a tree this host proved DIRTY,
                            announce once and RELEASE the record as they park -- left there, restoring or cleaning
                            the checkout would be enough on its own to publish the report and send the issue to
                            review, which is the decision the notice exists to put in front of a human. What that
                            record SUPERSEDED is released with it, held to the revision that says the two are one
                            lineage: a delivery recorded over an outstanding transaction carries its frozen pairs
                            forward and the binding behind it is what would have dropped it, so a transaction left
                            standing is one the reconciliation proves, settles and publishes over report text this
                            issue has already replaced. The debt outlives both, and a reading nobody could take is
                            neither refusal and buys nothing at all
      round_marks.py        whether the mark a settlement raised still places the round in hand, which is the one
                            reading the two owners that could relabel over one share. No mark is asked nothing. A mark
                            is correlated against the handoff beside it and refused on any of four: an outstanding
                            report, a handoff this build cannot read, one recorded under any label but
                            `workflow:fixing`, and either route anchor standing -- a settlement clears both, so one
                            there belongs to a round opened after the mark went up. The label is what catches an
                            anchorless manual relabel back onto `workflow:fixing`, which the rest of the comment
                            cannot tell from a round that has just closed, and a fifth reading catches the same
                            move made LATER: the mark falls with the hand-back and the handoff beside it never
                            does, so a comment whose round closed legitimately goes on satisfying all four, and
                            what ties a mark to ONE transaction is the receipt that hand-back stamped. That stamp
                            is this owner's too, and is taken only where a mark was RAISED: the reading above
                            places every road reaching a relabel on its own reasons as well, and one of those
                            closes no transaction to record. Either
                            owner CONSUMES the mark it asks about: one it may not place is the mark of a round
                            that is over either way, and left standing it would be waiting for whichever fixing
                            round came next
      parked.py             the five answers an `awaiting_human` tick can reach and the order they are asked in.
                            What counts as a reply is the reading the readers cannot give while a report is owed,
                            so the record's own frozen pairs decide it: a rescan with nothing above them clears
                            no park. The silent recovery is widened for one shape by the same rule -- a
                            `push_failed` park on the in_review route with a report still owed, where both groups
                            are the settlement's and the default would hold the issue on a park nothing clears --
                            and the retry that lands publishes the report against the commit ITS receipt names
                            before the hand-back retires the park. The `stranded_unproved` park the no-feedback
                            bounce files is the one shape here waiting on a READING rather than on a person, so
                            a quiet poll falls back through to that bounce with the flags left exactly as they
                            are: it is the single reader, and the park comes down in the write that relabels --
                            which is what keeps a reading that refuses again from announcing itself twice. An
                            accepted `/orchestrator continue` is
                            resolved here rather than falling through, since the stay-parked default behind it
                            would refuse the operator's retry as "nothing new"
      continue_command.py   `/orchestrator continue` on a parked fix: the replay and what it may hand the dev --
                            guidance, never the command itself -- plus the two refusals and the guidance passthrough
                            for retryable session failures (`agent_silent`, `agent_timeout`, `agent_execution_failed`)
      drift.py              the `workflow:resolving_conflict` reroute a stuck validating-route park earns when its
                            worktree has fallen behind base. Only a condition that has not resolved reaches it: a
                            park the branch READING withheld the clear from answers in a word of its own, since the
                            reconciliation this owner hands off to publishes that checkout with no report debt
                            staged for whatever it turns out to be carrying
      models.py             the frozen records the owners hand each other, the batch among them carrying the
                            whole issue-thread READ it was cut from -- the conversation a fresh spawn quotes and
                            the requirements a report is stamped with both come off it -- and the comment ids this
                            orchestrator RECORDED as it posted them, which is what keeps its own questions in that
                            conversation under an allowlist naming only humans: an agent handed the answers
                            without the questions they answer is re-grounded on half a thread
      state.py              the pinned-state keys they share, and the one park reason this stage files itself:
                            what a no-feedback bounce holds a branch it could not place under, which is the only
                            park here waiting on a READING rather than on a person -- durable, because nothing
                            else tells a later tick whose park it is standing over, and none of the validating
                            transient reasons, since those dispatch to a recovery that would publish against a
                            record this park has none of
    implementing/           `workflow:implementing`
      handler.py            the order one tick asks its questions in, opening with the retry-cap notice a stranded
                            park still owes
      spawn.py              awaiting-human vs active, the restorer the checkout comes back from, the
                            recovered-worktree shortcut and the certified baseline it stands down for -- which
                            an unread head cannot spend, since that comparison is what a retirement rests on --
                            and the retry-gated fresh spawn, which retires the pinned session wherever a
                            continuation is what paid for it: the grant is durable and the budget is shared, so the
                            tick that spends one is not always the tick -- or even the stage -- that granted it.
                            The spawn routes through `execution.py`'s bounded developer run coordinator to resume
                            premature AGY command exits before disposition. The spawn's prompt and the record of the
                            thread it quoted come off one read and travel on the prepared run, for the pre-session
                            edit that is settled by nothing earlier
      session.py            the four session retirements -- the fourth being the continuation that buys a spent
                            budget one more attempt, which is a fresh spawn by definition -- and the fresh-spawn
                            prompt, whose re-grounding conversation is the caller's frozen read wherever it holds
                            one and its own read otherwise. The budget that retirement answers to is
                            `engine/retry_budget.py`'s entire, gate and park alike, and the spawn road calls it
                            there
      session_read.py       the locked session read plus the stale / overflow / quota classifiers and the blockquote
                            they quote with
      resume.py             the two resume entry points and the historical call shape they keep. The
                            human-reply one is handed its caller's frozen batch rather than reading the
                            thread itself, hands that batch's frozen conversation down for the re-grounding
                            a retired session's fresh spawn needs, and settles the consumed issue watermark
                            from the batch AFTER the run -- only for an outcome that counts the input as
                            delivered, so a launch the run circuit refused, a shutdown kill, and a live pause
                            consume nothing while a timeout, an empty result, and a question park all do
      resume_batch.py       the frozen reply batch every `implementing` and `validating` awaiting-human resume
                            reads: ONE whole-thread fetch, by the pinned comment's id, from which the quoted
                            followup, the delivery record naming exactly the quoted ids, the whole and the retry
                            re-grounding conversations, and command ownership are all cut. Each stage's handler
                            freezes it once per parked tick and hands it to every road that tick takes. The
                            measurement retry is asked of the delivered replies, and so is the parked-continue
                            classifier where a caller says it looked at an earlier read (`continue_claimed`,
                            which neither handler passes); the authorization command is asked of the last reply the
                            id ledger leaves, and while its park stands it is in no prompt text even where
                            something after it demoted it. An owned batch is handed back whole, delivering and
                            settling nothing. `answered` -- the frozen comments at or below the park's watermark
                            -- is what the drift check measures a parked issue's requirements by. Settlement is the
                            ordinary issue-only `prompt_delivery` ratchet, taken after the run and only for an
                            outcome that counts as delivered: not a live pause, a shutdown kill, or a launch never
                            invoked. It records `user_content_hash` too, the fingerprint of the frozen read through
                            the last reply delivered, so a delivered reply is never answered again as an edit
      parked_replies.py     the one cut of a parked thread's fresh replies the batch above and the command roads
                            share: `prompt_delivery.human_replies`, less a bare `/orchestrator add-agent-runs` the
                            run-limit hold has already answered. The measurement retry and the quiet timeout
                            recovery read it; the authorization park keeps its own first cut (the id ledger alone)
                            and takes the grant out through this one too. A reply counted on one side of those
                            hand-offs and not the other is a tick each road leaves to the next on every poll
      resume_request.py     what one such call supplied, frozen and checked before a run is built: the stage
                            its records are attributed to, the frozen conversation a fresh spawn is
                            re-grounded from where the caller holds one, and the unknown option a named
                            parameter would have refused on its own
      execution.py          one resume, its poisoned-session retry -- withheld on an issue a poll observed closed,
                            since that retry is a SECOND agent -- and what each attempt is allowed to persist; the
                            bounded AGY command-recovery coordinator (`_coordinate_developer_run`) that recognizes
                            incomplete command outcomes and permits at most one immediate tracked continuation for
                            both fresh spawns and resumes
      worktree.py           the checkout a resume runs in, restored when reaped
      disposition.py        run-output attribution, inherited floors, timeout parks and their recovery, and agent-result
                            settlement; both heads must be readable and the run must leave commits above its floor --
                            with one exception, an issue still owing a report it could not deliver, where a run that
                            comes back with a report and moved no head is publishing the commits already on the branch
                            rather than asking a question. A RECOVERED run -- the restart shortcut -- is settled
                            against the pinned comment as well as the tree, through `unreported_recovery.py`. The
                            timeout park is bounded so its notice cannot carry the watermark over a reply written
                            while the agent was out
      candidate_recovery.py exact-commit recovery for approved and frozen work, timeout-commit evidence, and publication
                            through a proved clean tree and the size gate; a recovery hands on the candidate it proved.
                            The report the run wrote is recorded between the tree and the gate, the last moment it is
                            certainly recoverable; a report this build cannot record, and a completed run that handed
                            over none, stop the call there with nothing measured, pushed or opened. Every synthesis a
                            recovery hands the seam carries `invoked=False`, so it records nothing -- and a candidate
                            a gate record named is held there instead, through `unreported_recovery.py`, where
                            nothing on the comment describes it
      unreported_recovery.py
                            committed work a recovery republishes -- the restart shortcut and every road that
                            republishes a candidate a gate record named -- held under `report_undeliverable` before
                            anything is measured, pushed or opened unless a debt is still owed or a settled pair
                            names this repository, branch, commit and the receipt's pull request, re-read where it
                            settled with the requirements first. A commit a run that never COMPLETED left is
                            recorded as `implementing_incomplete_run_sha`, durably before the gate, and owed no
                            report, a timeout-park recovery's stranded commit included; a completed run retires it
                            in the write that records its report -- except over a
                            delivery or transaction an earlier run recorded and has not settled, which describes the
                            branch before that commit, so the commit is held the same way with the record kept.
                            Also the `invoked=False` result those recoveries hand the seam
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
                            receipt checks exclude the pinned comment by id. A bare `/orchestrator add-agent-runs` is
                            no reply to the park (`parked_replies.py`'s cut, which the frozen resume batch shares)
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
                            publication ride the answer, and the record is the telemetry owner's below. A permission
                            whose rewrite a merged or closed pull request shipped -- pushed from the anchor the
                            attempt was leased against, onto that pull request -- is settled from the head it ended
                            on, the same proof a leased no-op buys
      late_transfer_telemetry.py
                            the one record a settled transfer leaves on both sinks -- one `late_transfer` event
                            naming both pairs, the pull request, the rewrite kind, and which reading proved the
                            push, correlated by a generation minted from what the pinned comment already says, since
                            a transfer runs past the retirement that dropped the pair it was adjudicated under.
                            Called by `late_push` on the far side of the write `late_rotation` stages into rather
                            than by that owner, so the ordering is a property of the call site: a receipt GitHub
                            refuses ends the tick and reports nothing, and a rotation that moved no verdict -- a
                            permission left standing, one the publication went past -- says nothing either. A
                            settlement whose record was lost is reported from the proof the comment kept, with the
                            proof dropped durably behind it, so a later poll has nothing left to report once that
                            drop lands.
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
                            pull-request half is a request and this runs ahead of every stage on every dispatch
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
                            record whose split has settled, which is a group with no count that owes no reading.
                            Ahead of every answer it makes the record a settled transfer never got to report, since
                            every settled rewrite's crash comes back through this seam and no other is guaranteed to
      late_claims.py        what a post-publication record claims and what it cannot produce: whether a live one
                            still owes its count, and -- ahead of both reconciliations -- the five refusals a record
                            that cannot make a claim whole earns. Read off the RAW fields, because the parse is what
                            loses them: a group missing one member comes back as no group, an approval missing its
                            lease as no approval, a frozen field the comment CARRIES and no reader will type as a
                            field nothing froze, a spend group with one unusable member as no bookkeeping at all, and
                            a settled transfer's proof nothing can report from as no report owed
                            -- so every question behind them answers "nothing owed" and the stage runs over a claim
                            nothing can check, while the freeze quietly re-derives the half it cannot see from a
                            remote that has moved. A field the comment does NOT carry is the same gap: what the
                            write that mints a generation puts down in one go is required rather than merely checked
                            when present, and a base is required beside any count, since a number is taken over a
                            pair. All five claims on the five stages the transition graph's own set names, since
                            `workflow:implementing` has an edge to the adjudication too and its approval carries no
                            head by design; `workflow:decomposing` is asked the publication one and the transfer
                            proof's, because that group is what a settlement decides everything by and cannot
                            re-derive and a proof nothing can report from is damage in any mode, while a verdict
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
                            recover retained bases by object identity; a permit-only caller is never kept out
                            of the gate by the switch
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
                            the failure is emitted before the wait is recorded, and whether that park already stands
                            is what an announce-once refusal asks before taking it again
      late_measurement_reply.py
                            bare-continue batches reserved for the active measurement park; mixed feedback
                            stays with its stage and the current reason and wait must agree. Which replies count
                            is `parked_replies.py`'s cut, so the park's own notice cannot make the batch look mixed
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
                            nothing); the receipt naming that commit and pull request is written the moment the
                            pull request is known, before one this tick opened is announced, and everything from
                            there to the relabel is handed to `report_handoff.py`, the handoff left owed wherever
                            that refuses it, so the next tick republishes the same commit onto the same pull request
      report_handoff.py     a landed push to the handoff: the description judged on a fresh read, the report the
                            run delivered bound and published through `engine/report_binding.py` with that verdict,
                            and the relabel reached last -- held until no report is still owed (a debt no retry
                            can pay -- no record left, or a report a human edited, removed or wrote untrusted, per
                            `engine/report_evidence.py` -- parking for a report-only reply), the issue's
                            requirements read afresh and then the report settled for this commit, read where it
                            settled, still stand (the check `unreported_recovery.py` asks too, before a recovery's
                            push) -- or, where no report covers the commit, the requirements still answer the drift
                            check against the revision the run was handed, held unparked for the drift resume where
                            they do not -- the checkout is proved after those requests, and the description, read
                            afresh again, closes this issue and names the session
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
                            base history so it reads like the repository it lands in, less the tracked issue's own
                            trailing reference, which the title owner under `git/publication/` takes off whichever
                            line it reuses since the body below is what links that issue; the body pairing the
                            `Resolves #N` that closes the issue with the dev session the branch was written by
                            and the run's closing message, cut on a paragraph, line, or word boundary and marked
                            as clipped where it outgrows the cap, with a fence the cut left open closed first --
                            that message written only where the issue neither owes a report nor has one settled,
                            since the report comment is the authority and a capped excerpt would be a second,
                            unmarked copy; and the reuse of whatever is already open on the branch, which `find_open_pr`
                            promises nothing else about, handed back with its description untouched for
                            `pr_description.py` to judge. Opening one announces nothing: `_announce_opened_pr` posts
                            the comment and emits `pr_opened` once `publication.py` has written the receipt naming
                            it, so a response lost there leaves that pull request recorded. One road names its
                            pull request instead and may
                            OPEN none: a publication the gate admitted because that pull request already carries
                            the commit is finishing bookkeeping rather than publishing, so it is resolved by
                            number and re-read WHOLE -- open, in this repository, on the branch the push named,
                            and standing on the commit it sent, off one fetch and against the object handed on,
                            since what this writes is a receipt naming that commit and a relabel handing a
                            reviewer that pull request. One somebody closed OR MOVED between the gate's proof and
                            here holds the tick rather than earning a second pull request over the same work or a
                            receipt naming work the branch no longer carries
      pr_description.py     the report-aware verdict on a reused description, read afresh by number, which
                            `report_handoff.py` asks before the binding and again before the relabel: one closing
                            this issue and naming this session stands, and any other is held for a human, the two
                            lines quoted in the notice. It WRITES no description: GitHub offers no conditional write for one, so a
                            body built from any reading can overwrite an edit saved since, and human text, legacy
                            tails and concurrent edits stand as found. A failed re-read holds silently; one a
                            report claims -- delivered, pending, settled, or too damaged to say -- is left to the
                            binding's collision park while that report is owed, and parks here once it has settled
      handoff.py            the one write and the one relabel a finished publication is handed on by, spending the
                            two park reasons reaching that line answers -- the agent timeout, and the report this
                            publication could not deliver and since did: the pull request and the branch recorded
                            together, since a state that arrived without a
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
      park_correlation.py   the bounded payload the two parks below report beside their reason, since neither can
                            reach the shared funnel's: the caller's route, the session and exit status off the
                            result, and the pinned counters -- screened against the funnel's own allow-list, and
                            built from no part of what the agent wrote
      checkout_parks.py     dirty and unreadable checkout refusals, operator messages, and staged park events; both retain
                            the work and use the shared watermark reader after posting their notice; the refusal
                            reports which half failed, how many paths git named where it named any, and whether the
                            run had timed out
      parks.py              classify unfinished commands, session limits, transient provider failures, real questions,
                            and silent exits; retryable failures keep their reason and streak, while a question clears
                            both. Structured unfinished command diagnostics precede message checks; otherwise the
                            final message picks the branch -- the quota and provider phrasings matched as a prefix,
                            an empty one the silent exit -- reporting the branch that ran so the emitted vocabulary
                            stays closed however the agent phrased itself
      drift.py              a body edit mid-implementation: the resume it earns -- withheld while a continuation
                            has bought an attempt, since a resume passes no gate and the attempt is owed as a fresh
                            spawn -- and the `ACK:` that answers it. A commit-less reply bringing the report an
                            undeliverable-report park asked for publishes the commits already on the branch; on a
                            parked tick only an edit reaches this road, a reply going to the park's own resume.
                            What the resume quoted is settled by its disposition, and a pre-session edit by the
                            spawn that answered it, for every outcome that reached an agent and no other -- the
                            shutdown kill, the live pause and the launch the circuit turned away each returning
                            before anything is written. That settlement is also what records the new baseline:
                            nothing here stages it ahead of a run, since a baseline written for a prompt nobody
                            read marks the edit answered and hands the words under it on as already delivered
      drift_preflight.py    a pre-session edit -- handed on rather than consumed, since clearing a park delivers
                            nothing at all -- the refusal that records nothing about the edit and its own reason
                            durably instead, so the tick after it recognizes that park, says nothing again and
                            stands down to the resume the reply it asked for belongs to, the quiet
                            timeout recovery, held off by that reason and by a reply the
                            tick's frozen batch would deliver, and the awaiting-human resume on that batch
      continue_command.py   `/orchestrator continue` on a parked issue for retryable session failures (`agent_silent`,
                            `agent_timeout`, `agent_execution_failed`), opening with the one park below that the
                            classifier here would refuse the right command on, and handing back outright a
                            batch the measurement park's own road would re-measure on: this read comes after
                            that road looked at the thread, so a command landing between the two is in this
                            batch and in nobody else's -- and classified here it is a continue on a park
                            needing real guidance, refused and consumed past the refusal, with the reading its
                            author asked for one nothing will ever take. What it classifies is the tick's one
                            frozen batch (`_parked_batch`, frozen here and handed on to the drift check and the
                            resume) -- the replies the resume would DELIVER -- so a notice of ours or a forged
                            marker above a bare command cannot turn an explicit retry into a generic resume over
                            prose. The retry is re-grounded, wherever its session is missing or retired, off that
                            freeze's conversation less the commands it consumes
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
      models.py             the frozen records the owners hand each other, including what a fresh spawn quoted and
                            what a requirements edit leaves the rest of the tick
      state.py              the pinned-state keys and CLI marker tuples they share, the label a report this stage
                            delivers records as its route -- a wire value like every key beside it -- and the two
                            retry bounds: the silent parks a session survives, and the readings one frozen pair
                            may lose
    in_review/              `in_review`
      handler.py            the order one tick asks its questions in, and the missing-`pr_number` park asked before
                            the rest -- with an approval that no longer covers the work, stale by a requirements
                            edit or recorded against another developer report, asked right behind the terminals
      feedback.py           the four surfaces scanned before the drift check, their author filters (a bare
                            `/orchestrator add-agent-runs` is nobody's review), and the park that stays silent for
                            the base-sync retry loop
      fixing_route.py       the pending-fix bookmarks, the hash refresh, and the `workflow:fixing` relabel
      drift.py              a body edit on an open PR: the move to `workflow:validating` it owes staged with the
                            refreshed requirements hash, since every write the disposition makes persists both and
                            the hash is what stops a later tick re-detecting the edit -- a report recorded or a
                            debt withheld says the move is owed on the roads that leave one, and the marker says it
                            for the `ACK:` and the park that leave none, so neither may become durable without the
                            other; the unread PR conversation captured first and frozen with the bounded issue
                            excerpt into ONE delivery record, settled after the run and only for an outcome that
                            reached an agent -- the issue thread's own cursor and the requirements revision, and no
                            more, since the cursor the two surfaces SHARE covers a numbering this record read at two
                            moments and only the carry's merged re-read can answer for it; neither review
                            surface moves at all, as no prompt here reads one -- with the carry over that record
                            taken BOTH before the disposition -- so the first durable write that disposition
                            makes carries it, rather than a process dying mid-way leaving a report and a push over
                            feedback still marked unread -- and after, for the notices the disposition posts; the
                            dev resume
                            under the requirements revision that record fingerprints, and the `workflow:validating`
                            return a pushed fix, an `ACK:`, and a report alone all take -- the fresh round and the
                            marker saying the move is owed persisted BEFORE that relabel, since a label moved first
                            and a write then lost hands the reviewer the budget the stale approval was earned
                            under, while a relabel that does not land leaves both durable for the next tick to
                            move -- and the report bound only once the relabel is behind it; and the hand-back a
                            later tick gives an issue whose approval an edit made stale, read off a report it still
                            owes (a failed push, a held candidate, a tick that died mid-way) or off that marker,
                            which is the only thing an `ACK:` and a resume that PARKED leave, or off an approval
                            recorded against another report than the current one or of one since edited or
                            removed at its location -- a location nobody could read holding the tick -- a question
                            answers
                            the edit with nothing, so the move is owed from there too, and made ahead of the
                            feedback scan that would otherwise route the answer to `workflow:fixing` -- with the
                            comment a human wrote while the resume was out still unread beneath the carry, so the
                            move hands on the reply they wrote. A publication still owed when either move
                            is made is recorded as belonging to the budget that reset gives it, so the road that
                            lands it on `workflow:validating` spends no round the edit has already paid for
      merge_gate.py         the unmergeable park -- bounded, since the scan that let the tick reach it ran several
                            round-trips ago -- and the one HITL ready-ping an approved, unvetoed head earns per head
                            SHA, which is no park and carries no mark; a fresh approval retires the stamp, so a
                            report re-reviewed on an unchanged head is pinged again, and the subject the approval
                            covered is read again at the ping itself -- the report at its location, the requirements
                            over the issue read afresh against the approval's revision and the baseline, the head
                            over the pull request read afresh (`review_coverage.py`), and last the report records on
                            the pinned comment -- since the requests before it are time another
                            road can settle a later report in, a human edit the report or the issue in, or a push
                            move the head in; refused or unread, nobody is pinged and nothing written. The park
                            asks the pinned comment the same before it writes
      surfaces.py           the two reads the shared IssueComment id space is taken as -- the issue thread against
                            the delivery cursor an issue-only resume settled as well, the PR conversation against
                            neither -- and the raw merged read tagged by surface that the watermark walks consume.
                            The thread cut takes a caller's OWN read of that surface where one is handed in, since a
                            caller deriving more than the batch from it -- the conversation a fresh spawn quotes,
                            the requirements its report is stamped with -- owes each of those to the same read
      watermarks.py         how far a park's own notice may carry the issue-side mark, and the legacy seed a
                            manually-relabeled issue needs -- both walks forward from where the mark is, over what
                            they can vouch for, and neither reads a tip. The carry is handed the tick's frozen
                            delivery record rather than the read behind it, since a bounded excerpt delivers less
                            than it read and the context it cut is what the walk has to stop below
      models.py             the per-tick handles and the drift-resume record, which carries the delivery its prompt
                            was built from -- what the issue may mark answered, and the revision its report is
                            stamped with, off the one read
      state.py              the issue-side watermark key they share, the marker saying this issue owes
                            `workflow:validating` a label move its own relabel did not land, the predicate reading
                            that marker beside a report still owed, an approval of another report, and one of other
                            requirements than `user_content_hash` holds -- whose own test is spelled here -- and the one
                            staged write spelled here rather than at the owner that makes it: every field the
                            hand-back puts down, asked by the report reservation so a field added moves it too
    question/               `question`
      handler.py            the order one tick asks its questions in, the closed-issue finalize that outranks them,
                            and both worktree teardowns
      run.py                the resume and fresh-spawn routes, the tracked spawn they share, and the park funnel every
                            exit lands on -- which is also where the bounded correlation every park reports is
                            built: the road off the tick's own record, the role, the pinned conversation, and any
                            recorded pull request, screened against the shared funnel's allow-list and read from
                            no part of what the agent wrote
      session.py            the locked question-agent identity, the trusted-reply consume, and both prompt builders
      outcomes.py           the read-only violations checked before any answer, and the park each outcome earns
      models.py             the tick record and the road it opened on, the locked session, and the outcome
      state.py              the park reasons and pinned-state keys they share, plus the role a run is attributed to
                            and the two route names a park is recorded under
    validating/             `workflow:validating`
      handler.py            the order one review tick asks its questions in, the terminals it opens with, and the
                            recorded-collapse route it asks behind only those, ahead of every route that could
                            point an agent at the branch -- and the report hold it asks last, behind the drift
                            resume that would supersede a stale report and ahead of the reviewer spawn, writing
                            a park the awaiting-human branch cleared into a round the hold then stops
      reviewer.py           the round cap, the tracked reviewer spawn and its two refusals, what a round that
                            RAN records about the reply or grant that bought it -- taken from the one read its
                            OWN prompt was rendered from, under that prompt's bound, never from the unbounded
                            batch a park froze for a developer, and owed to that reply whether or not the park
                            outlived the tick that cleared it -- and about the note a deferral
                            left, which that round discharges -- and the verdict
                            fan-out, with the subject an approved verdict hands the squash tail built here over
                            this run's own checkout. The developer report is resolved through `review_report.py`
                            ahead of the spawn and the subject it yields written beside the reviewer spec before
                            the spawn, onto the comment as that resolution read it, through `review_records.py`; the
                            pinned comment is read again through `review_comment.py` as the reviewer returns, before
                            any park or record the run leaves is written, and an approval is acted on only while
                            `review_coverage.py` finds that whole subject standing
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
                            still standing on the commit that handoff named, the developer report recorded as
                            current is the one its approval covered and still reads at its location as it settled,
                            and the issue read afresh still carries the requirements the approval was given and the
                            baseline holds -- a report settled on that same commit since, edited or removed in place,
                            or an issue edited since, is work no reviewer has read, and the record goes for the round
                            below to answer; a location, an issue, or a pull request nobody could read holds the tick
      approval.py           the verify gate and the squash-and-hand-off tail both roads run, over the subject,
                            branch, and pull request number whichever road decided them hands in -- the review
                            subject recorded as approved once the gate passes, riding whichever write the tail
                            makes, and the relabel that tail owes held wherever that approval no longer covers the
                            report the pull request carries, the requirements the issue carries, or the head the
                            rewrite published (the approved head where it rewrote nothing), each read afresh, the
                            rewrite finished either way -- the one check the recovery of a squash an earlier tick
                            did not finish gets -- and nothing posted or written past a published rewrite, nor the
                            label moved on either road, where the pinned comment no longer carries the report
                            records in hand, so a report settled meanwhile is left for the next tick; that number
                            read as an identity before the squash subject may reference it: the optional squash,
                            the park each of its four readings earns, the notice its count is worded from --
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
      verify.py             how a refused verify result reads and the park it earns; `ok` and the `not_run` an
                            empty `VERIFY_COMMANDS` returns both advance instead
      watermarks.py         the seed walk past leading orchestrator comments and a bare `/orchestrator
                            add-agent-runs` a grant left unread, and the ratchet that never regresses one
      requested_changes.py  the PR feedback and `workflow:fixing`-labeled dev fix, its report disposed of through
                            `fix_reports.py` and bound behind the round and the relabel, plus the no-VERDICT park
                            and the split that tells a provider's failure from a reviewer's
      dev_fix.py            what a finished dev fix leaves behind: the publishable reading and the proved remote
                            head it carries on as the lease, taken for a run that committed as well as for one
                            that did not -- a tick committing over work an earlier one stranded begins at a
                            commit the pull request has never carried, so a lease read off that head parks every
                            such tick unmeasured -- the tree proved in BOTH halves before the push, since the
                            size gate's own proof rides the entry it freezes and `DECOMPOSE=off` freezes none,
                            the size gate every fix route publishes through, told the
                            state the run really belongs to by the route that relabels before it spawns rather
                            than reading it off the issue object, the push and the approval it spends, the round
                            bump, and the bounded timeout park
      stranded.py           one reading of a branch against the publication it is on, answered in words rather
                            than yes-or-nothing. Eight findings, two of them readings and six refusals. A clean
                            checkout fetched and proved strictly AHEAD of the remote pull request branch and
                            behind nothing is `stranded`; the two proved EQUAL are `in_sync`. Both name BOTH
                            ends -- the remote tip the count was taken against, which is what the push replaces
                            and is leased to, and the local commit it was counted over, which is the work going
                            out. That local commit is FROZEN before anything counts it, and the commit AND the
                            tree are both proved again afterwards, so the numbers and the checkout handed on are
                            one world: `HEAD` is a symbol every command re-resolves, and a fetch and a count are
                            time a worktree can move or pick up loose work in. A size gate given both ends then
                            refuses a checkout that moved rather than measuring whatever it points at. The refusals are a status nobody could take, a tree holding
                            loose work, a fetch that did not return, a divergence git would not count, a remote
                            that moved, and a HEAD that did not read or disagreed with the count. Typed
                            because "nothing to publish" and "nothing could be read" are opposite facts about the
                            branch: collapsed, the fix disposition publishes blind, the ACK fast path hands back a
                            pull request that may be short of a commit, the transient recovery clears a drift park
                            over one or leases a push to a head its publication never carried, and the no-feedback
                            bounce relabels past the last tick that would have published it. What each refusal MEANS is spelled here too, so the road that stops on
                            one names the reading rather than the silence
      awaiting.py           the three park-reason claims on the context's one frozen reply batch, and the dev
                            attempt they fall through to, handed that same batch; the explicit `/orchestrator
                            continue` retry is re-grounded off its conversation less the commands it consumes.
                            The cap's grant is the one control road recording anything of its own, and only
                            where the comment IS the command: those WORDS as read, since the orchestrator
                            answered them on the thread, and nothing else, because what no agent has read is
                            the requirements they arrived beside. A command written inside a comment of
                            guidance records none of it -- the round the grant buys is what delivers those
                            words, under its own bound -- so the grant writes down the COMMENT it answered
                            instead, beside the round reset and in the same write: durable exactly where that
                            reset is, which is what a launch the run circuit refuses discards, and what keeps
                            one comment from resetting every cap the issue later reaches. A
                            reviewer-side park's retry records nothing at all: that reply belongs to the round it
                            buys, which reads it under the round's own bound (`reviewer.py`). Both roads DO write
                            down the round those words bought, since the clear can go out on a tick that runs no
                            round and the reply has moved the requirements by the next one.
                            A transient retry that resolves drops the fresh review budget a hand-back recorded
                            with the park it clears: that retry IS the publication the budget was reset for --
                            pushed, or found not to exist -- and a record left standing would spend nothing for
                            the next unrelated publication this stage owes
      awaiting_resume.py    the order those claims are asked in and the resume none of them wanted, over the context
                            the handler built before its drift check -- and, where the park was one this stage took
                            over a report it owes, the drift reading of that resume's answer, stamped with the
                            revision the batch delivered, since a reply to a park is no drift and this is the road
                            it arrives on -- a park over an edit its own resume never answered reads the same
                            way, off a claim taken BEFORE the run, since the resume clears the park it was written
                            beside -- and spending the round `rounds.py` says it does, which is none where the
                            park came back from `in_review` with the budget already reset for it
      drift.py              a body edit mid-review, the three parks that defer -- which deliver nothing and so
                            record nothing, baseline included -- the one thing that outranks a deferral, which is
                            a report this stage still owes its pull request: no reviewer runs behind that debt,
                            and the record it is owed was written against requirements a reply has already moved,
                            so standing down for the held round would leave the two waiting on each other for the
                            life of the issue -- and the frozen prompt its resume settles once the
                            run is back. The requirements revision its report is stamped with is that prompt's own,
                            not the drift check's a moment earlier: a reply landing between the two is in the prompt
                            and in the settled baseline, and a report stamped behind them is one the reviewer hold
                            refuses; on a parked tick the edit is measured by what the park had already read
      drift_models.py       the frozen record that route's resume hands the helper that finishes it, the delivery
                            it was built from -- and the revision that read fingerprints -- included
      drift_outcomes.py     the claim that the edit is still unanswered, written -- for a caller that named what
                            its resume was `handed`, which is the caller that reads it back -- beside every park a
                            resume ends on and dropped by every outcome that answers it, with the fresh review
                            budget a hand-back recorded, but only once the publication that budget was reset for
                            has happened, so an `ACK:` leaving a commit withheld for its report keeps it; the `ACK:`
                            reply that must not park, over the shared fix disposition, and -- where the
                            caller names what its resume was `handed` -- the report reply that is neither, recorded
                            for the unchanged head as `reported`, and a commit held to the same contract
      drift_reports.py      that contract for a drift resume on an open pull request, which is that nothing this
                            road publishes may be work no report describes: the run's report recorded ahead of the
                            size gate under the route and the revision its CALLER handed it -- the prompt-delivery
                            record's on either review stage -- a
                            commit of this run's with no usable report parked rather than pushed, a report alone
                            recorded only over a tree proved clean -- parked on the tree otherwise, with nothing
                            recorded -- and a commit an earlier run stranded, under a run that committed NOTHING,
                            withheld until a reply brings the report that describes it; a run that committed is
                            held to its own report ahead of the gate instead, so a reply with none parks for the
                            report both commits are short of rather than posting an `ACK:` over new code.
                            Which run wrote nothing decides none of it: the engine
                            exempts an unfinished run from the contract because the roads it serves publish
                            nothing either way, while this road publishes, so a nonzero exit, a provider refusal
                            and a launch nothing invoked are each parked here as the missing report they also are.
                            What the debt is asked against is a record of THIS work: a delivery
                            or transaction an earlier run left describes the branch before the commits a later run
                            made, so the undescribed-work flag those commits leave is read first and the reply
                            that publishes them is the one that describes them
      fix_reports.py        that same contract for the `CHANGES_REQUESTED` run this stage spawns itself, which is
                            the half of the fix loop it owns -- every later round is `stages/fixing/reporting.py`'s,
                            holding it to the same contract and, while the report is owed, holding the readers,
                            the round and the relabel with it. The
                            run's report recorded ahead of the size gate, a report with no code in it recorded for
                            the head `fix_report_evidence.py` PROVED the pull request to be standing on, and a
                            commit of this run's with no usable report parked rather than pushed, in this road's
                            own words rather than the engine's. The report contract is the RUN's only where that
                            run committed or reported: a commit an EARLIER round stranded is published through the
                            ordinary gate either way, since its report was that round's to record and the debt it
                            left is what holds the reviewer off the head this lands on
      fix_report_evidence.py what a report with no code in it has to prove before it is recorded, and what its
                            refusal owes: the branch proved to be standing exactly where its remote is (a clean
                            tree, a local head, a tip, the two equal) AND the code-publication receipt naming that
                            same commit on the pull request the report would go onto. Asked of a CHECKOUT rather
                            than of a run, because what it is about is a checkout rather than a session: this
                            disposition holds the run and the worktree it ran in, and everything it proves is
                            about where that worktree stands. One caller only -- the `fixing` stage answers the
                            same question for itself, over a pull request it reads AFRESH rather than over this
                            receipt, which is persistent and on any tick that pushed nothing names an older
                            round's commit. Nothing is inferred from an
                            absence, because "this run committed nothing publishable" is the same answer the
                            disposition gives a checkout nobody could read, a fetch that failed, a divergence git
                            refused and a remote that moved -- each of which may be a branch carrying a commit the
                            pull request has not got. Short of all of it the round parks with the debt recorded and
                            the report UNWRITTEN, since a record over an unproved head is one no reconciliation
                            could settle honestly. The consumed-input write sits here beside them because it is the
                            same kind of obligation, owed by every park rather than by one: a park is durable the
                            moment it is taken, so the input the prompt delivered rides that write rather than a
                            caller's afterwards
      report_settlement.py  a recorded report bound to the publication the code-publication receipt names -- only
                            where the checkout, resolved as the reviewer resolves it, stands on that commit -- over
                            the pull request, its description, and the issue all read again by number: the binding
                            is told whether that description still closes the issue and names the session, and the
                            dispatch reconciliation settles it over the FRESH issue, since the one in hand predates
                            the resumed run and an edit made during it exists only on the new object. Asked by both
                            drift callers behind their own bookkeeping and by the hold, so a delivery a later push
                            carried (a recovered failed push, a settled adjudication) is bound on the first tick
                            that proves it; a refusal no retry changes parks once under `report_undeliverable`
      report_hold.py        the hold that keeps the reviewer off while the issue still owes a report, settling what
                            it can through `report_settlement.py` first and parking for what no retry settles: a
                            report written against requirements the issue has moved past, a receipt naming another
                            pull request or none, a checkout on a commit the pull request never received, a
                            checkout that has picked up loose work or moved off the commit a bound transaction is
                            about, a report the thread has moved out of reach --
                            edited, removed, or written untrusted, asked with the reading the implementing handoff
                            takes -- and a debt no record describes at all. Every one of those is something the
                            reconciliation stands down on rather than holding, so a silent hold there would
                            suppress every later reviewer with nobody told
      review_report.py      the report a reviewer is handed once nothing is owed: the one last settled, re-read where it
                            settled and quoted whole, and the pull request's head read with it for the subject. Refused
                            rather than reviewed -- parked under `report_undeliverable` with the debt recorded, so the
                            reply resumes the developer -- when no report is recorded at all, when the settled record
                            will not read, is about another pull request, disagrees with the handoff that settled it, or
                            reads ABSENT or CHANGED (removed, edited, cut short, or untrusted) -- and when a report that
                            reads intact is STALE: about another commit than the pull request's head, or written against
                            requirements the drift baseline has moved past, an `ACK:` of an edit included, which is the
                            rule the hold holds an owed report to. The baseline rather than the reviewer's own read,
                            since that read carries the reply that bought a retried or granted round -- while that read
                            has to be the revision the round was due to hand over: the baseline, or on a round a
                            control-only reply bought -- a bare grant or `/orchestrator continue` -- the thread through
                            that reply (`validating_reviewer_round_requirements`); a reply carrying words is a
                            requirements change, and records none. One that moved on after it is held, nothing parked,
                            the owed round stood down, for the next tick's drift check to resume the developer on the
                            new words. A reading nobody could take holds without a notice, and every hold writes what
                            the tick staged -- a cleared park, a cap grant and its notice -- so none of it is answered
                            twice. Nothing is decided or written until `review_comment.py` finds the pinned comment
                            carrying the report records the subject was resolved from. The reading itself posts and
                            parks nothing, so `review_coverage.py` takes it again
      review_comment.py     the pinned comment a review is bound to. The subject is resolved from the state the tick
                            read when it began, so the comment is read once it is resolved and has to carry the same
                            report records: a later report settled in between -- on the very head, by another road --
                            is there and nowhere in hand, while the report the tick resolved still reads intact. Where
                            it does not, the comment will not read or parse, or the fresh reading is another comment
                            than the one the state was read from -- replaced or gone, whose write would pin a second
                            one -- nothing is handed over and the tick ends WITHOUT writing, since any write would put
                            the replaced report back. The reading that agreed goes with the subject, and the comment
                            is read against it again as the reviewer returns and once more after an approval is
                            verified, before anything the run leaves is written: records that moved refuse the verdict
                            and everything the comment changed since is carried onto the state in hand, so every write
                            the run makes keeps that settlement current; another comment or an unread one carries
                            nothing and the tick writes nothing. Records are compared as the comment's JSON spells
                            them, so one written `null` where there was none, or a revision `true` where it was `1`,
                            is a move. The later roads that act on an approval after requests long enough for a
                            settlement -- the squash tail once its rewrite is published, and the in_review park and
                            ready ping -- ask the comment the same before they write, and act on nothing where it
                            moved. Nothing here parks or posts
      review_coverage.py    whether an approval still covers the subject standing when it is acted on. When the reviewer
                            returns -- approving or requesting changes -- and the report records on the pinned comment
                            stand (`review_comment.py`), the whole subject is resolved again over the issue read afresh
                            and has to EQUAL the one handed over -- pull request, head, requirements, and the report's
                            revision, digest, location, and words -- or the verdict is not acted on and the next round
                            resolves the subject for itself; asked again by `approval.py` once the verify gate has
                            passed, since a verification can run long enough for the report to be edited or replaced
                            under it. Later, once the pinned records agree the current report is the approved
                            one and its settlement handoff still describes it -- the pair a reviewer spawn refuses
                            otherwise -- the report is read at its location again, since no record sees a comment
                            edited or deleted in place; the issue is read afresh against the approval's own requirements
                            revision and the drift baseline both, since a baseline moved on to an edit says nothing
                            about what the reviewer read; and the pull request is read afresh against the commit the
                            move is owed over, since a push landing meanwhile is a commit nobody approved: the
                            squash tail asks all of it before its relabel, on either road into it, the settled
                            squash handoff before moving a label that tail left owed, and `in_review` before an
                            approval may stand behind a ready ping. Nothing here parks or posts
      review_records.py     what a reviewer round writes onto the pinned comment, through writers the round and the
                            report settlement's measurement share: the spec and the subject it is handed, written
                            ahead of the spawn -- onto the comment as `review_report.py` read it, since the launch
                            charge writes only its own fields and the state in hand carries what only the round's
                            own write may land -- and the session and return time it leaves; and the reservation of
                            the whole round at its widest (spec, subject, launch charge, session, return time, and
                            approval), so a report is never accepted into a comment its own reviewer cannot write
                            to. The usage meters the return folds are left out: running totals every run folds,
                            already on the comment from the developer run whose report it is wherever that run's
                            usage parsed
      recovery.py           the silent retry of a push race or dev timeout, both through the size gate -- the
                            timeout's commit is the one road to a published pull request nothing else measures.
                            A timed-out round is answered by the BRANCH rather than by the run on both its
                            shapes, and on every road rather than on the drift one alone: `pre_dev_fix_sha` says
                            only whether the killed run committed at all, since it is the head that round OPENED
                            at and a commit an earlier interrupted resume left can sit between it and the
                            publication. Level with its publication clears; a commit the pull request has not got
                            is published through the same gate, named by the commit the reading froze and leased
                            to the remote tip it counted that commit against -- pinned to the anchor instead, the
                            push names a head the publication never carried and is refused unmeasured, parking a
                            human over work the branch is holding. On the requirements-drift road that commit is
                            also work no report describes, and which run made it decides: one the KILLED run made
                            publishes with the debt staged into the write the push makes, since nothing here can
                            ask a session that is gone, and the review hold asks a human before any reviewer
                            reads that head, while one an earlier resume stranded leaves the park standing for
                            the reply that reports it. A reading nobody could take holds, because a clear taken
                            on one sends the next reviewer to a checkout with no receipt and no gate debt behind
                            it. Both holds answer in a word of their own rather than as a condition that has not
                            cleared, which is what keeps the branch reading out of the fixing stage's worktree-drift
                            reroute: relabelled there, the park comes down and the checkout is published by a road
                            that stages nothing for it -- the debt the push that lands pays, the round `rounds.py` says that push spends, which
                            is none where the park was delaying a publication an `in_review` hand-back had already
                            reset the budget for, the held outcome that owes the caller no follow-up and
                            no relabel, and the one sentence a park that healed itself owes the thread
      rounds.py             the `review_round` a fix pays for on the one event `MAX_REVIEW_ROUNDS` counts -- a head
                            the reviewer has not seen reaching the pull request, or the report of that head reaching
                            it, since the next reviewer reads both -- spent by the push that lands, by the hold that
                            sends the candidate to the adjudication, and by the write that settles a report no gate
                            ever saw, the frozen form handed to all three so the count is neither lost to a crash in
                            the relabel window nor taken twice; the pair a reviewer-requested round closes, which is
                            that round and the replay anchor its handover consumes; and the publications that spend
                            nothing -- one a drift park still owes, whose budget an `in_review` requirements edit
                            already reset and whose delayed landing would otherwise charge that edit twice, and one
                            whose own RECORD already carries the round, since a fixing round that finished on a
                            report froze its bookmarks and its round there precisely so the write completing the
                            publication is the only thing that spends them. The record is asked rather than the
                            debt, because the two part company: a drift resume records a report carrying no
                            bookkeeping at all, and read off the debt that reviewer would be handed a head no round
                            was ever spent on. Both are asked by the resume that answers such a park and by the
                            silent retry that finishes its push
      models.py             the frozen records several owners in this stage hand each other -- a record one
                            route builds and reads alone stays beside that route instead -- the park clear
                            every awaiting road takes, which drops the unanswered-edit claim with the park it was
                            written beside, the two settlements an awaiting road may take -- the whole batch, or
                            ONE control comment the orchestrator answered rather than delivered, with every other
                            comment held in as an omission so no mark crosses words nobody read -- the record
                            that such an answer already stands on the thread, and the note a reply's round is
                            owed by
      state.py              the pinned-state keys, park reasons, and outcome tokens they share, including the
                            three that outlive their own tick: the claim that a requirements edit this stage's
                            resume ended without answering is still outstanding, the note left for a reviewer
                            round still owed -- the park it was written beside is gone before that round runs
                            -- whose value says whether a reply bought the round, and so whether the round has
                            anything to record, and the comment a review-cap grant was written for, which is
                            how a grant already honored is told from one a refused round left still owed. Two
                            of the outcome tokens are about what a caller may do NEXT rather than about what
                            healed: the word a silent retry answers with when the BRANCH reading is what
                            withheld the clear -- told apart from a transient condition that merely has not
                            resolved, since only the second licenses the fixing stage's worktree-drift reroute
                            -- and the grouping of every outcome that healed nothing, which is what keeps a road
                            testing for the words it knows from reading a later addition as a recovery
```
