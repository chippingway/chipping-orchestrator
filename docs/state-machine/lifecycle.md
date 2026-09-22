# Label lifecycle diagram

The compact reference for every arc the state machine can take, node by node. It is a summary of the handlers rather
than a second source of truth: where the two disagree, the handler pages are authoritative —
[`delivery-stages.md`](delivery-stages.md) for pickup through the PR loop,
[`conversation-stages.md`](conversation-stages.md) for `question` and `discussion`, and
[`labels-and-state.md`](labels-and-state.md) for the label vocabulary the nodes are spelled in.

```
   Legend: a node is the workflow label the issue carries. `in_review`,
   `question`, `discussion`, `done`, and `rejected` are unprefixed; every
   state the orchestrator drives itself is namespaced `workflow:<tag>`. Route,
   handler, and manifest names below are the bare tag, not a label.

   Forward (single-task happy path):
     (none) ──► workflow:decomposing ──► workflow:ready
            ──► workflow:implementing ──► workflow:validating
            ──► workflow:documenting (final-docs handoff)
            ──► in_review ──► done | rejected

   Decompose:
     decision='single' ─► label=workflow:ready  (parent itself implements)
     decision='split'  ─► create children, parent=workflow:blocked
                          (or workflow:umbrella when manifest umbrella=true);
                          child[i] = workflow:ready if no deps
                                     else workflow:blocked
     manifest invalid / question / timeout ─► park HITL

   Late size gate (every clean committed candidate, before it is published):
     tree not provably clean      ─► never reaches the gate. A dirty one
                                     parks naming its paths; one `git status`
                                     could not report on parks as
                                     unreadable_worktree, since a read that
                                     established nothing is not a clean tree
     a finished run's report      ─► recorded on the pinned comment between
                                     the tree and the gate; one that will not
                                     record, a completed run that reported
                                     nothing, any recovery whose commits no
                                     record describes, and a run that did
                                     not finish over a report an earlier
                                     one recorded all park
                                     report_undeliverable with nothing
                                     measured, pushed or opened
     additions <= MAX_ADDED_LINES ─► publish as usual (push, PR, the report
                                     bound and posted on it, then
                                     workflow:validating -- withheld, unparked,
                                     while the report is still owed, and
                                     parked report_undeliverable while the
                                     description, never rewritten, does not
                                     close the issue and name the session);
                                     the generation is dropped, its cycle
                                     recorded retired, and the commit still
                                     owed a push recorded as late_approved_sha
                                     until it lands
     additions >  MAX_ADDED_LINES ─► NOTHING pushed, no PR opened;
                                     label=workflow:decomposing, where the
                                     late coordinator owns every later tick
                                     and an adjudicator's `single` parks the
                                     candidate for a human's decision rather
                                     than publishing it unsplit -- one
                                     trusted /orchestrator
                                     authorize-oversized <commit> settles it
     candidate == late_exempt_sha ─► publish unmeasured, but only where the
       AND late_override_*           late_override_* terms an operator
                                     authorized name the same commit and the
                                     contribution between the pair that record
                                     names still fingerprints to what it says:
                                     the exemption is an adjudicator's answer
                                     and half a bypass. Only the exemption ─►
                                     the ordinary reading, and past the
                                     ceiling a park late_unauthorized_exemption
                                     the same authorize-oversized command ends
     candidate == late_approved_sha ► publish unmeasured, named against it:
                                     the commit this gate approved and has
                                     still to push, brought back by a crash
                                     between the two
     candidate == the published sha ► publish unmeasured: the branch is
                                     already pushed and its PR already open,
                                     and only the relabel this tick finishes
                                     was ever owed
     an authorized rewrite of it  ─► publish unmeasured on a permit earned
                                     this tick by the owner that RAN the
                                     rewrite -- a squash on approval, the
                                     clean rebase the base refresh publishes,
                                     or the clean replay resolving_conflict
                                     runs -- whose contribution fingerprints
                                     to the digest the adjudication recorded,
                                     over a clean checkout, an unmoved
                                     publication, a base the remote reaches,
                                     and an issue re-read unchanged. What goes
                                     down before the push is the PERMISSION
                                     (late_rewrite_phase authorized); the
                                     exemption stays on the commit a human
                                     ruled on, and the receipt of the landed
                                     push carries it, its identity, and the
                                     authorization over in ONE write
                                     (published), reported as one
                                     late_transfer and no second verdict
     ... any other commit         ─► measured as the fresh candidate it is:
                                     a descendant, a developer or reviewer
                                     fix, the docs pass, an agent's conflict
                                     resolution, and a replay that changed
                                     one covered byte earn no waiver, and no
                                     count, subject, similarity score, or
                                     patch-id stands in for the fingerprint
     DECOMPOSE=off, no generation ─► publish unmeasured; a candidate already
                                     recorded is measured with the switch
                                     either way
     ... and no commit nameable   ─► park late_candidate_moved, publishing
                                     nothing: on that road the CHECKOUT names
                                     what goes out, and a push named against
                                     nothing sends whatever the branch has
                                     become, records no receipt, and leaves
                                     both proofs around it nothing to compare
     no reading at all            ─► park late_measurement_failed with the
                                     frozen pair kept -- including the id a
                                     revision that would not peel resolved to;
                                     a trusted bare `/orchestrator continue`
                                     re-measures that exact pair and spawns
                                     nothing. The park freezes the branch out
                                     of base sync until answered. The notice
                                     names the typed step AND the line an
                                     operator acts on it by -- which of a
                                     remote, a token, a checkout, or a planted
                                     attribute file this is, and, for the
                                     remote read, the fetch and the two diff
                                     steps, the orchestrator.git_plumbing
                                     channel their invocation is logged under
                                     -- with whatever the step wrote for
                                     itself, scrubbed, beside it. It is made
                                     once per STEP: late_measurement_failure
                                     records which one was named, so a reading
                                     retaken with nobody asked holds silently
                                     while it stops there, and one stopping
                                     at a DIFFERENT member is announced once
                                     and takes its place. Which readings those
                                     are is the gate's own road: HERE the park
                                     owns every tick until the continue above
                                     arrives, and its own miss is a fresh
                                     answer that says so, while past
                                     publication the reconciliation below
                                     re-reads the pair once a poll and is what
                                     the silence is for
     ... the base was unreachable ─► counted instead, for the first three in a
                                     row: base_unreadable and base_absent are
                                     the transport rather than the work, so the
                                     pair and the incremented
                                     late_measurement_miss_count go on the
                                     record, the typed late_failure is
                                     emitted, and the tick stops with nothing
                                     parked, nothing said, and no step on the
                                     PINNED record --
                                     that field is what a NOTICE named, not
                                     what a reading stopped at, and the record
                                     emitted here names the step regardless,
                                     since a stream is counted by cause.
                                     Nothing stands in the way of the next
                                     tick, so it re-enters that same pair with
                                     no agent and no reply; the fourth miss
                                     takes the park above, records the step it
                                     names in the same write as the count, and
                                     mentions once. A reading retaken past it
                                     holds silently as above, though each
                                     still reports its typed late_failure, and
                                     a base id the remote finally names is
                                     recorded even then. A
                                     base REACHED puts the COUNT back to zero
                                     and leaves the member alone, since
                                     reaching the base is not the last step a
                                     reading can stop at; what retires the
                                     park, dropping the member with the count,
                                     is the reading it lets through, settled
                                     one owner on, since a base in hand is not
                                     yet a measurement
     no commit ever named         ─► the same park, and its bare continue is
                                     refused: no pair was frozen, so a retry
                                     would take a FIRST reading of a head
                                     nothing ties to this issue. Guidance
                                     resumes the developer instead
     late_approved_sha recorded   ─► before any spawn, the approved commit
                                     owns the tick: published from a checkout
                                     standing on it, or parked
                                     late_candidate_moved where it is not --
                                     never re-measured, re-decided, or
                                     re-implemented. It is also a floor a
                                     resumed run has to clear, the durable
                                     record of what a push is about to carry,
                                     and is spent ahead of the validating
                                     relabel
     checkout moved after the push ─► park late_candidate_moved: the branch
                                     and its PR are right, the CHECKOUT is
                                     not, and every stage past the handoff
                                     rewrites what it stands on
     tree dirtied around either    ─► the same park. Loose work can appear
     boundary                        with HEAD never moving, so the commit
                                     proofs pass while the checkout stops
                                     being what was measured -- and nothing
                                     past the handoff reads it again

   Late size gate (a fix, before it joins a PR the remote already carries;
   the same questions above, over what the PR would COME TO -- the count is
   three-dot from the frozen remote base to the candidate, so it is the whole
   pull request rather than the commit this run made):
     entered from                 ─► workflow:validating / workflow:
                                     documenting / in_review /
                                     workflow:fixing / workflow:resolving_
                                     conflict -- every state that pushes onto
                                     a pull request the remote already has:
                                     the shared dev-fix publication and the
                                     no-feedback bounce behind it, the
                                     validating push/timeout recoveries, the
                                     three conflict publications, the base
                                     sync's auto-rebase and crash recovery,
                                     and the final docs pass
     the push it allows           ─► named against the commit the gate
                                     measured and leased against the head the
                                     entry froze, so a checkout that moved
                                     publishes the measured commit and a pull
                                     request somebody pushed to in the same
                                     window rejects the push instead of being
                                     overwritten
     a pair frozen and never      ─► measured ahead of the handler on the next
     counted                         tick, by the stage the record names --
                                     the freeze is durable and the count is
                                     not, so a crash in between is a step to
                                     resume rather than a record nothing
                                     goes back for
     ... unless the split settled ─► nothing is owed. A candidate the
                                     adjudication made into children keeps
                                     the publication group -- the umbrella
                                     re-asks it before each release and each
                                     branch delete -- and drops the count, so
                                     the tick goes to the label's own handler
                                     on workflow:umbrella, and a stale
                                     late_measurement_failed standing over it
                                     is retired rather than held
     ... with no checkout here    ─► park late_measurement_failed and stop the
                                     tick, announced once: the commit is on a
                                     host this one is not, and letting the
                                     stage run would bounce a candidate
                                     nobody read back to the reviewer
     additions <= MAX_ADDED_LINES ─► push onto the branch as usual; the
                                     generation is dropped and the
                                     late_approved_sha the push paid with it
     additions >  MAX_ADDED_LINES ─► NOTHING pushed; the PR stays on the head
                                     it was standing on and the record naming
                                     that head, its number, and the stage it
                                     came from goes down before
                                     label=workflow:decomposing
                                     ... unless an exemption nothing
                                     authorized names the candidate, where
                                     the same record goes down and the issue
                                     parks late_unauthorized_exemption
                                     instead: the change was ruled one change
                                     already, so what it waits for is the
                                     operator rather than a second
                                     adjudicator. A commit the PR is already
                                     standing on is never held that way --
                                     the push moves nothing and only the
                                     bookkeeping is owed
     tree not provably clean      ─► park late_measurement_failed. A dirty
                                     tree parks naming its paths one step
                                     earlier; the gate refuses the reading a
                                     `git status` that established nothing
                                     would have been taken beside
     PR unreadable, closed, merged ► the same park: nothing to measure
                                     against, and nowhere for the push to land
     PR open on another branch,   ─► the same park. The number and the branch
     or with its head in a fork      are two fields on one pinned comment: an
                                     entry frozen on the head alone would
                                     settle against a publication the push
                                     never touches, and a fork carries these
                                     ref names over these commits, so nothing
                                     else tells one from this issue's own
     a receipt group nothing can  ─► parked at the gate's own door, of the
     read whole                      record and of no candidate: a member
                                     whose key is gone, one carrying a value
                                     nothing here can use, and one naming no
                                     publication at all. The write behind any
                                     push puts a fresh group down, so damage
                                     is retained rather than completed --
                                     including on the two roads with no gate
                                     door of their own, DECOMPOSE=off with no
                                     named candidate and the accepted
                                     settlement
     a receipt naming this        ─► published without a reading only where
     candidate                       the remote agrees: the PR the receipt
                                     itself names, open here, on the branch
                                     this seam would push, standing on that
                                     exact commit, over a receipt recording no
                                     LEASE -- this seam froze no publication
                                     for one to be about. Anything short of it
                                     parks with the receipt, the recorded
                                     number and any debt left as they stand --
                                     an exemption or an approval naming the
                                     same commit included, since neither says
                                     where the work went. Proved, the number
                                     is carried: the push is leased to that
                                     commit and the bookkeeping re-reads that
                                     PR by number -- open, here, on the branch
                                     and on the commit -- rather than
                                     searching the branch for one
     work that ENDED before the   ─► handed back to the stage terminal, which
     reconciliation opened           marks the issue done or rejected with the
                                     record, the branch and the debt left as
                                     they are. Two facts: the issue object,
                                     and the PR the record names -- a merge
                                     leaves the issue open until a terminal
                                     reads it, and there is nowhere for this
                                     push to land. The PR reading falls
                                     through where the remote will not answer,
                                     so a blink costs a poll rather than
                                     stranding the issue
     work that ENDS after it      ─► refused immediately before the push and
                                     nowhere else: everything above that line
                                     spends a reading, a diff or a request. A
                                     merged or closed PR still has its branch
                                     at the frozen head, so the lease would
                                     SUCCEED and the force-push would walk
                                     terminal work backwards -- so this
                                     reading fails CLOSED, is taken whatever
                                     DECOMPOSE says, and a latched close is
                                     asked after it, since the reading itself
                                     is a window. Nothing pushed, nothing
                                     relabelled, nothing announced. The
                                     initial publication and the settled
                                     adjudication's own push each carry the
                                     same barrier
     a pr_number nothing can read ─► the same refusal, with no reading spent.
                                     A field the comment CARRIES and no reader
                                     here will type is not an issue with
                                     nothing to check: read as one, no request
                                     is made and the push lands on whatever
                                     the branch's pull request has become. On
                                     these roads an ABSENT one refuses too --
                                     each publishes onto a pull request the
                                     remote already carries -- while at the
                                     implementing seam absent is the first
                                     publication and goes out as ever
     a settled `discussion` plan   ► not an ending for the push that follows:
     PR the record still names        a merged plan is an agreement, and what
                                      it licenses is an implementation with a
                                      pull request of its own. The stage's own
                                      terminals make the same carve-out, and
                                      for the same reason -- finalizing there
                                      would close the issue `done` with no
                                      developer having run
     PR head moved off the frozen  ► the same park, the record left naming the
     one                             head it froze -- somebody pushed in
                                     between, so the frozen pair no longer
                                     says what the PR would come to
     DECOMPOSE=off, no generation ─► push unmeasured, and no pull request is
                                     read for the MEASUREMENT: the switch is
                                     asked ahead of everything the entry would
                                     cost. The terminal-safety barrier above
                                     still reads one, since what the switch
                                     decides is what enters the reading and
                                     not whether a merged pull request may be
                                     force-moved

   Validating fix loop:
     workflow:validating --(CHANGES_REQUESTED)──► label=workflow:fixing
       (pre-spawn flip; dev runs with stage="fixing")
         ──► pushed fix: report recorded before the gate, ++review_round,
              label=workflow:validating, report bound behind the relabel
         ──► report with no commit (a reviewer item naming report content):
              nothing pushed, report recorded for the head the branch and the
              publication receipt are PROVED to agree on, label=workflow:
              validating — the same road a pushed fix takes, since the next
              reviewer reads the report too. ++review_round is the SETTLEMENT's
              here, not this tick's: a handover nothing confirmed has bought no
              round, so a refused post or a crash leaves it unspent
         ──► report with no commit whose head nothing could prove (a reading
              that failed, or a branch carrying an unpublished commit):
              nothing pushed, nothing recorded, review_round unchanged, park
              report_undeliverable on workflow:fixing
         ──► committed with no usable report (an unfinished run included):
              nothing pushed, review_round unchanged, park
              report_undeliverable on workflow:fixing
         ──► REPORTED over a checkout this host proves it cannot publish from
              (gone, or carrying uncommitted changes), whether the round
              committed or not: nothing pushed, review_round unchanged, park
              report_undeliverable on workflow:fixing with the record RELEASED
              and the pairs that round consumed applied in the park's own
              write — one notice for one condition, since the recovery behind
              it would otherwise find the same refusal and post a second
         ──► crash anywhere past the report's own write: label still
              workflow:fixing, park already cleared, the triggering reply
              unread, and — where the round committed — the commit its report
              describes still in the checkout. The next fixing tick finishes
              that round rather than resuming a developer, ahead of its own
              scan: it re-proves the CHECKOUT (a tree provably clean, a head
              it could name) and binds the report against the pull request it
              reads afresh, never the persistent publication receipt, which
              on a tick that pushed nothing names an older round's commit.
              Settled, the round the record froze is closed and the issue
              moves to workflow:validating on the mark that settlement raised;
              a post that did not land relabels nothing and leaves the
              transaction to the reconciliation
         ──► that same crash over a checkout this host PROVED it cannot
              publish from (gone, or carrying uncommitted changes): nothing
              pushed, nothing published, review_round unchanged, park
              report_undeliverable on workflow:fixing, and the recorded report
              RELEASED with it — left on the comment, merely restoring or
              cleaning the checkout would publish it and send the issue to
              review, which is the decision the notice is asking a human to
              make. The debt outlives that release, so the review stays held
         ──► that same crash over a reading nobody could TAKE (a status that
              established nothing, a head that would not resolve, a pull
              request this poll could not fetch): nothing pushed, nothing
              released, nothing said — the tick ends where it stands and the
              first poll that can read them publishes. A head the pull request
              has MOVED off is neither: the bounce re-proves the remote and
              republishes the commit, binding the report to that push. It
              hands the round back on a mark of THIS route's and on nothing
              weaker: a delivery another route recorded settles that route's
              bookkeeping and raises none here, so the bounce writes its own
              pending_fix_* clear and review_round before relabelling
         ──► park (timeout / no-commit / dirty / push fail):
              label stays workflow:fixing, awaiting_human=True; the
              fixing handler owns the awaiting-human cycle and on a
              human-reply handover — a pushed fix, or the report of the head
              already there — BUMPS review_round (validating
              route) or RESETS it to 0 (in_review route), and an ordinary
              non-actionable ACK: still returns to in_review —
              discriminator is `pending_fix_at`
     workflow:validating --(awaiting-human resume / drift / transient-
       recovery push)──► ++review_round, label stays workflow:validating
     the same push for a publication an in_review hand-back already reset
       the budget for ─► no round spent (developer_report_owed_round_reset),
       label stays workflow:validating
     workflow:validating --(drift report with no commit)──► report posted
       on the unchanged head, review_round unchanged, label stays
       workflow:validating
     a developer report still owed ─► no reviewer spawned; bound and
       settled where the receipt and checkout prove it, else parked
       report_undeliverable once no retry can settle it
     workflow:validating --(APPROVED, verify ok, squash ok)──►
       label=workflow:documenting (final-docs) ──► in_review
     MAX_REVIEW_ROUNDS exhausted ─► park HITL
     squash failure ─► park HITL on workflow:validating, no relabel

   implementing / validating / documenting (no PR-state arc of their own, so
   the three terminals are asked at entry, ahead of every gate, push and
   spawn; implementing asks its two behind the plan-PR question):
     pr merged externally               ─► done (external merge)
     pr closed unmerged                 ─► rejected. The ISSUE stays open, so
                                            the closed-issue terminal beside
                                            it never sees one -- and the size
                                            gate below would measure the
                                            committed candidate again and push
                                            it, opening a SECOND pull request
                                            over work a human turned down,
                                            while validating and documenting
                                            would spawn over it
     issue closed, PR also closed       ─► rejected (+ branch cleanup)
     a PR fetch that failed             ─► nothing written, and the tick
                                            carries ON to the stage: nothing
                                            about a failed read says which
                                            ending it was hiding, and answered
                                            as one every issue whose remote
                                            blinked would stop advancing. The
                                            one exception is implementing with
                                            discussion_plan_sha recorded,
                                            where the HEAD is what tells the
                                            plan from a delivery: a reading
                                            that established none cannot say
                                            which, so that tick is held
                                            unfinalized and unspawned instead

   in_review (orchestrator never merges; merged arc always external):
     pr merged externally               ─► done (close + cleanup)
     pr closed unmerged                 ─► rejected (close + cleanup)
     issue closed manually, PR open     ─► rejected (no branch cleanup;
                                            operator may salvage)
     fresh PR feedback on any of the    ─► label=workflow:fixing (record
       four comment surfaces                pending_fix_at + bookmarks,
                                            clear stale park; no debounce
                                            wait, no dev spawn here)
     a stale approval: a report owed    ─► workflow:validating
       (failed drift push, held             (review_round=0 and the handoff
       candidate, a tick that died), or     marker written before the
       the handoff marker an ACK left       relabel; asked first, ahead of
       when its relabel did not land        feedback and the ping)
     user-content drift (pushed, ACK,    ─► workflow:validating
       or a report with no commit)          (review_round=0; no docs hop;
                                            the report is settled there
                                            before any reviewer runs)
     mergeable + final-docs-complete or ─► HITL ping (no relabel,
       GitHub-approved current head        awaiting_human stays false)
       + no human CHANGES_REQUESTED
       + head SHA not yet pinged
     unmergeable                        ─► park (unmergeable); a
                                            subsequent human comment
                                            routes to workflow:fixing

   workflow:fixing (terminals mirror in_review; merged arc always external):
     pr merged externally / closed unmerged ─► done / rejected
     Otherwise rescan all four surfaces, each past the readers it
     answers to (the issue thread past last_action_comment_id as well
     as pr_last_comment_id). If awaiting_human with no new feedback,
     branch on park_reason + pending_fix_at. For a stuck
     validating-route transient park
     (`_VALIDATING_TRANSIENT_PARK_REASONS` with
     pending_fix_at unset, _try_recover_validating_transient_park
     returns "stuck"), route to workflow:resolving_conflict when the
     clean worktree is out of sync with the PR -- behind base, OR
     already on base but local HEAD != the live pr.head.sha (an
     unpushed local rebase) -- the dead-lock breaker base sync can't
     reach while parked. Every other awaiting-human shape (real agent
     question / dirty park / silent-crash / in_review-route transient)
     stays parked silently to preserve HITL. If no unread feedback at
     all, publish any commit an earlier round stranded in the worktree
     (`validating/stranded.py`'s clean-and-strictly-ahead probe, the
     one the fix disposition and the ACK fast path ask too, through the
     same size gate every push onto an open PR passes; a push that
     lands adjusts review_round per pending_fix_at), then
     clear pending_fix_* and bounce to workflow:validating. A candidate
     the gate HELD stops the bounce instead: the issue is already on
     workflow:decomposing and this tick relabels nothing;
     otherwise honour IN_REVIEW_DEBOUNCE_SECONDS. Past the window,
     resume the dev with a `_build_pr_comment_followup` prompt and apply
     the validating fix-loop disposition. A launch nothing invoked, a
     shutdown kill, and a live pause settle nothing and write nothing;
     the next tick re-feeds the same batch. Every other outcome
     delivered that prompt and is settled ahead of the disposition,
     ONLY to the max id fed to the dev and against the reader each
     surface owns -- the issue thread moves last_action_comment_id
     beside pr_last_comment_id, the PR conversation and both review
     surfaces move their own in_review watermarks alone. A report
     outcome settles nothing either: the publication it owes is not
     this tick's to promise. On a pushed fix, adjust review_round per
     pending_fix_at (in_review->fixing route resets to 0; validating->
     fixing route bumps by 1) and flip directly to workflow:validating.
     Docs do not run on this exit.

   workflow:resolving_conflict (operator relabel, base-sync flow on
       actual rebase conflicts, or the fixing worktree-drift breaker;
       capped by MAX_CONFLICT_ROUNDS):
     clean rebase, HEAD moved      ─► push, workflow:validating
                                      (++conflict_round)
     base up-to-date no-op         ─► workflow:validating
                                      (++conflict_round, no push)
     conflicts ─► dev resumes      ─► push, workflow:validating
                                      (++conflict_round)
     ahead-of-remote recovered     ─► push, workflow:validating
                                      (++conflict_round)
     already-rebased, behind stale ─► force-publish, workflow:validating
       orchestrator-produced head     (++conflict_round); else
                                      diverged_branch park
     awaiting-human resume push    ─► push, workflow:validating
                                      (++conflict_round)
     drift pushed fix              ─► push, workflow:validating
                                      (++conflict_round)
     any pushed content update     ─► workflow:decomposing (nothing pushed
       above, past MAX_ADDED_LINES    and no round counted; the round it
                                      owed and the head it produced are
                                      recorded as conflict_settled_outcome
                                      / conflict_settled_sha)
     settlement handed back        ─► workflow:validating for the recorded
                                      round (++conflict_round, receipt
                                      dropped); an adjudicator's own `single`
                                      parks for a human's decision and hands
                                      nothing back, and a `split` closes the
                                      PR and never re-enters this label
     drift ACK / drift _on_question park ─► no relabel; rebase still
                                            unfinished, next tick
                                            re-enters the same label
     conflict_round >= MAX_CONFLICT_ROUNDS ─► park awaiting human
     pr merged externally / closed unmerged ─► done / rejected (terminal)

   any dispatched issue, ahead of every handler (the reuse guard):
     ancestry names a snapshot ─► the RECEIPT first, and it is authoritative:
       ref                         one comment of ours on this child marked
                                   with the owner|cycle|generation its
                                   ancestry names. It outranks every reading
                                   of the ref -- a mirror nobody dropped and a
                                   ref pushed again at the same commit both
                                   look untouched -- so a thread that could
                                   not be READ holds the dispatch rather than
                                   falling through to them. Where the thread
                                   answered and carries none, ask this
                                   host's mirror, resolved and compared
                                   against the recorded commit (free: a
                                   reclamation drops it BEFORE the remote ref
                                   and refuses to take the remote while it
                                   survives; a copy at another commit is an
                                   agent's write and reads as no copy) -- and
                                   only
                                   where the ancestry carries
                                   late_ancestry_mirror_first, since a pointer
                                   written before that ordering may have a
                                   mirror standing beside a reclaimed ref --
                                   and then one read-only ls-remote for the
                                   exact ref and commit. Three answers: absent
                                   is reclaimed and parks; mismatch is the ref
                                   under somebody else's commit and parks
                                   (late_snapshot_repointed), touching the ref
                                   itself no more than the reclamation would;
                                   unreadable is an outage, which parks
                                   nothing and writes nothing -- the dispatch
                                   is HELD and asked again next dispatch.
                                   A park -> drop the pointer, say so
                                   (late_snapshot_reclaimed) naming the ref
                                   and the owner, and return before the
                                   label's handler is reached -- INCLUDING a
                                   reopened done|rejected child, which is
                                   otherwise a dispatch no-op, and a relabel
                                   straight to another stage. Evaluated on the
                                   child's own dispatch, so no other writer
                                   can undo it
     no ancestry, but the body ─► the same receipt, matched against the lineage
       carries the split's own      the BODY claims: the split records a child
       child marker                 before it seeds one, so a failed seed
                                    leaves exactly this. No receipt is not
                                    permission -- the ref goes before any
                                    receipt does -- but a body is not
                                    authority either, so the OWNER's
                                    generation is read fresh and has to vouch:
                                    same cycle and generation, this issue
                                    among late_consumers. Unvouched -> nothing
                                    (a marker anyone can paste parks nobody);
                                    unreadable, opaque, or no recorded
                                    candidate -> HOLD; vouched -> the ref that
                                    identity names, asked against the commit
                                    the owner recorded, and the same four
                                    answers as above. A park -> write the
                                    claimed lineage back (never the pointer),
                                    which repairs the record and stops it
                                    being asked again
     no ancestry and no marker ─► nothing, and no request
       in the body
     ancestry present, no ref  ─► nothing: this guard has already answered for
       on it                       this child
     label=workflow:decomposing ─► stepped aside, with the adjudication guard
       AND a live generation on    beside it: an issue under adjudication is
       the record                  working from its own candidate, not an
                                   ancestor's. The label alone is not enough
                                   -- a consumer closed while it was being
                                   decomposed reopens on it with no
                                   generation at all, and is asked like any
                                   other child

   the same dispatch, on the same pinned read (the pair below is asked
       AHEAD of the reuse guard above, since both RUN rather than merely
       answer; the agent-run-limit hold sits between them and the reuse
       guard, the developer-report reconciliation sits between that hold
       and the reuse guard, and the greeting refusal is asked behind it):
     late cycle a close ended, ─► the closed-owner ending below, run from
       cleanup unfinished          wherever the owner was left: reaches no
                                   handler, and writes that cycle's rejected
                                   once nothing is owed
     the same cycle settled,   ─► the RESTART. Mint cycle+1 behind a pending
       its rejected PROVED         marker, post one notice scoped to it, apply
       applied, and an operator    label=workflow:decomposing (DECOMPOSE=on)
       has reopened the issue      or workflow:implementing (off), then retire
       and taken the label off     the marker -- which projects the pinned
                                   comment onto the fresh cycle. Asked one
                                   step ahead of the ending above, since a
                                   restart writes its label BEFORE it retires
                                   its marker and the ending would otherwise
                                   hand the issue rejected again.
                                   ALLOWED_ISSUE_AUTHORS is not asked: taking
                                   a label off is a write only a repository's
                                   own people may make. backlog|paused defer
                                   the whole of it; a refused notice or label
                                   keeps the marker and resumes next tick
     awaiting_human +          ─► the HOLD: reaches no handler, says the
       park_reason=                sentence the park still owes if nothing
       agent_run_limit, and        ever did, and records a standing phase.
       the issue is OPEN           The issue has spent every agent run
                                   MAX_AGENT_RUNS_PER_ISSUE allows, and a
                                   lifetime total is spent once -- no window
                                   elapses under this park, so every stage
                                   road below (a resume on the next reply, a
                                   hold waiting on words, a continue
                                   classifier) would answer a park it was not
                                   written for. Work that has ENDED is let
                                   past instead: what it reaches below is a
                                   terminal that ENDS the issue rather than a
                                   road that spends anything on it. A CLOSED
                                   issue is the free half, and the poll's own
                                   closed reading counts beside the object's;
                                   the recorded PULL REQUEST having merged or
                                   closed is the half the flag cannot show,
                                   costs a request per parked poll, and fails
                                   OPEN -- a remote that would not answer
                                   lifts nothing. What that second one MEANS
                                   turns on the label: a settled `discussion`
                                   plan is the agreement that licensed the
                                   build, so it is carved out on
                                   workflow:implementing and nowhere else --
                                   `discussion` drains the same PR itself. Nothing let past can spend a
                                   run: the circuit every launch goes through
                                   reads the same ledger and refuses on it
       + a trusted, bounded    ─► allowance = used + N, this park taken down
       /orchestrator               and the park it displaced put back, the
       add-agent-runs N on         command consumed with the receipt that
       the unread thread           acknowledges it (unless a reply the
                                   refused resume was handed sits under it),
                                   a granted phase, and the tick goes on to
                                   the stage its label names. Every other request --
                                   malformed, zero, negative, past the
                                   per-command maximum -- keeps the park and
                                   earns one marker-scoped receipt; an
                                   untrusted one is answered with nothing.
                                   Neither ending returns a spent run
     developer_report_pending  ─► the RECONCILIATION: prove the world the
       on the pinned comment       record froze, then publish the report it
                                   carries (idempotent by its receipt, so a
                                   retry finds what an earlier attempt landed)
                                   or re-read the exact location it names,
                                   and settle one current report, one handoff,
                                   the watermarks the run consumed, the
                                   bookkeeping its route owed and the drop of
                                   the record in ONE write. The record is
                                   durable and the publication is not, so a
                                   tick that died between them leaves a pull
                                   request without the report the next
                                   reviewer reads, and no stage goes back for
                                   it. Asked LAST of the reconciliations --
                                   behind the size gate's, whose settlement
                                   is the very question this owner's evidence
                                   asks, and behind the auto-rebase anchor on
                                   both sides of it -- and ahead of the reuse
                                   guard and the handler, which are roads that
                                   carry on over a report nobody published.
                                   Short of proof: a read nobody could take
                                   HOLDS; a dirty tree, a moved head, an
                                   unpublished commit, edited requirements, an
                                   edited or deleted report, an untrusted
                                   author, and a settlement the comment no
                                   longer has room for all stand DOWN onto the
                                   routes that fix them, with the transaction
                                   still owed; a merged or closed pull request
                                   RETIRES it; and a record this build may not
                                   act on parks once
                                   (report_record_damaged) -- unless another
                                   route's park already stands, where it
                                   stands down rather than overwrite one or
                                   hold in front of the handler that answers
                                   it. Work that has ENDED is handed back
                                   untouched: a closed issue, or an open one
                                   already wearing done|rejected, since a
                                   terminal label resolves to no handler and
                                   the no-op below would protect nothing.
                                   The record itself is left by a publication
                                   that bound its run's report and could not
                                   put it on the thread, so reaching this
                                   guard is the retry, not the first attempt
     no workflow label, a      ─► nothing, logged once a tick. Pickup GREETS
       pinned comment already      an issue and mints its pinned comment, so a
       on the issue, and no        second greeting writes a second one every
       restart authorized          later read shadows. Apply a workflow label
                                   by hand to drive such an issue again

   workflow:blocked (each due dependency poll, open issues only; DEPENDENCY_POLL_EVERY_N_TICKS):
     all children = done       ─► parent=workflow:ready
     any child = rejected      ─► park HITL on parent
     dep_graph walk: any workflow:blocked child with all deps=done
                               ─► child=workflow:ready

   workflow:umbrella (each due dependency poll, open issues only; DEPENDENCY_POLL_EVERY_N_TICKS):
     all children = done       ─► settle what the late split still owes the
                                  remote, THEN parent=done, issue closed
                                  (no implementation). The branch is retried
                                  unconditionally; a held snapshot ref is
                                  deleted once every recorded direct consumer
                                  has ENDED -- read off the consumer's issue
                                  state, not its label, since reopening keeps
                                  done/rejected. Whether the list names ALL of
                                  them is read off the record's PHASE: while
                                  `splitting` stands it may be short by a
                                  child already on GitHub, empty or not, so
                                  nothing is reclaimed; either side of the
                                  loop it is whole, which is also what lets an
                                  EMPTY list settle a ref no child was cut
                                  from.
                                  EVERY obligation that is not
                                  `reconciled` holds the terminal (a RETAINED
                                  ref included), as does an opaque RESOURCE
                                  ledger or a damaged cycle identity -- the
                                  label stays, which IS the retry, and the
                                  reason is logged on each due dependency
                                  poll that holds.
                                  An opaque CONSUMER list keeps the ref and
                                  frees the branch: the two ledgers are
                                  written apart and refused apart
     snapshot delete           ─► entry=`reclaiming` BEFORE the delete, then
                                  RE-READ every recorded consumer past that
                                  write and act only if all still ended (a
                                  reopen inside the window keeps the ref and
                                  leaves the entry `reclaiming`); delete --
                                  this host's MIRROR first, and one that will
                                  not go leaves the remote ref alone, so a
                                  surviving mirror can never mean a reclaimed
                                  remote (a transport that raises reads as
                                  REFUSED and emits snapshot_delete_failed);
                                  TELL every consumer, then
                                  entry=`reconciled`. The ref
                                  is never recreated; a refused delete tells
                                  nobody
     telling one consumer      ─► one COMMENT and nothing else, carrying a
                                  marker naming this owner/cycle/generation so
                                  it is said once. This owner never writes a
                                  consumer's pinned state: that is written
                                  whole by whoever writes it, a finalize sets
                                  its terminal label BEFORE its last write,
                                  and closed ready|blocked are swept by
                                  nothing. A consumer it could not reach
                                  leaves the entry `reclaiming`
     `reclaiming` | `failed`   ─► retried past the consumer proof ONLY for a
       whose consumers are no      ref the remote no longer has: one read-only
       longer all ended            ask decides, and a surviving ref is kept
     any child = rejected      ─► park HITL on parent -- and settle the same
       | closed without a          ledger on the way out, from the same fresh
       terminal label              scan: both dispositions CLOSED the child
                                   they name, which is what the reclamation
                                   rule reads, and nothing revisits an OPEN
                                   umbrella either. It decides no terminal:
                                   the park stands, and the issue stays open
                                   on the label its next dependency poll
                                   comes back for
     dep_graph walk: any workflow:blocked child with all deps=done
                               ─► child=workflow:ready

   closed on workflow:decomposing | workflow:umbrella | workflow:ready |
   workflow:blocked (cleanup sweep, on the CLOSED_ISSUE_SWEEP_EVERY_N_TICKS
   cadence; the ONE case where the label does not choose the handler -- routed
   by being closed, fanned out cap-exempt so an open decomposer cannot starve
   it, with that route BOUND into the submit so a reopen before the worker
   refetches cannot reach a stage handler. The first two are where an
   adjudication runs; the other two are where a decomposition outcome that
   landed after the close can leave its ending, and only their CLOSED issues
   are asked about):
     any generation            ─► mark the cycle cancelled, once, before any
                                   external call; emit one late_cancellation
                                   from that write
     held pull request         ─► release the hold, one marked notice, close
                                   it; re-asked every visit, recorded only
                                   where the state moved
     opaque ledger             ─► nothing more but a warning; no entry on it
                                   may be reclaimed around one nobody can type
     branch / ref              ─► the umbrella terminal's rules, verbatim, on
                                   a scan this pass takes itself: retry the
                                   branch, and delete a held ref once every
                                   consumer has ended. Reopened-before-delete
                                   or an unreadable consumer keeps the ref;
                                   the branch settles either way. No consumer
                                   is written to, commented on, or relabelled:
                                   a cancelled cycle owes its children nothing
     nothing left owed         ─► label=rejected, which ends the cycle and
                                   takes the issue out of this sweep. Never
                                   spawns, activates a child, or closes
                                   anything; `rejected` is the one label it
                                   writes, and a reopened owner reaches the
                                   same ending through the dispatcher's guard.
                                   The write is recorded in two phases -- the
                                   cycle it is owed for before it, the proof
                                   it LANDED after -- and that proof is what
                                   makes an operator's later REMOVAL of the
                                   label the restart arc above

   question (operator-applied; no automatic in/out transitions):
     fresh spawn          ─► DECOMPOSE_AGENT runs read-only in issue-N
                             worktree, posts answer, park awaiting human
                             (question_answer)
     human reply          ─► resume locked session, post follow-up,
                             park again
     commits / dirty /    ─► park (question_commits / question_dirty /
       timeout              question_timeout); worktree PRESERVED for
                             operator inspection; base sync skipped
                             while label is question
     agent silent         ─► park (question_silent); worktree torn down
     issue closed         ─► label=done, stamp question_closed_at,
                             cleanup (terminal)
     relabel to           ─► implementing's guard: clean worktree AND
       workflow:implementing  branch ─► drop question park, resume dev;
                             dirty or branch has commits ─► park
                             (question_unsafe_relabel)

   discussion (operator-applied; nothing routes IN, and the only automatic
   ways out are the terminals below: the verdict the humans leave on the plan
   PR, and a close of the issue before one exists):
     first tick           ─► decomposer agent opens the design discussion in
                             the issue-N worktree; response posted, park
                             (discussion_response); worktree PRESERVED
     plan PR recorded,    ─► nothing: no agent, no comment, no write, no
       still open            teardown; the design is with the humans and the
       (plan path +          label stays `discussion` -- which is also what
        pr_number)           keeps a manually CLOSED issue in the closed-issue
                             sweep until that PR resolves. A PR that could not
                             be fetched holds the same way
     plan PR merged       ─► label=done, stamp merged_at, usage receipt, emit
                             pr_merged (stage=discussion), close the issue,
                             then cleanup (worktree + local + remote branch)
     plan PR closed       ─► label=rejected, stamp closed_without_merge_at,
       without merging       usage receipt, emit pr_closed_without_merge
                             (stage=discussion), close the issue, then cleanup
     issue closed with    ─► label=rejected, stamp closed_without_merge_at,
       no plan PR            usage receipt; no event and NO teardown -- the
                             branch may hold an unpublished plan commit or a
                             PR the issue arrived here carrying
     HEAD moved off the  ─► the commit is judged WITHOUT spawning: the agreed
       recorded round SHA    plan is published as the ended round would have,
       on entry              anything else parks (discussion_plan_invalid), so
                             no round inherits it as its baseline
     dirty tree on entry  ─► park (discussion_stranded) WITHOUT spawning; the
                             checkout is left untouched for inspection
     unreadable tree on   ─► park (discussion_unreadable_worktree) WITHOUT
       entry                 spawning; nothing proved it empty, so nothing
                             recreates over it
     the plan's own PR    ─► record its number WITHOUT pushing and WITHOUT a
       already decided        park: the branch a merge deleted is not recreated,
       (merged, or closed     no second pull request is asked for, and no
        without merging)      replacement is opened over a design a human turned
                              down. The humans have decided, so nothing tells
                              them to go and review it -- the terminal above
                              reads those records next tick and finishes the
                              issue `done` or `rejected`
     issue closed inside  ─► the same lookup, run by the terminal instead: a
       that window            decided PR finalizes the issue (pr_number and
                              branch recorded first), an open one holds with the
                              label and checkout intact, and no PR at all falls
                              through to the pre-PR close above
     agent commits the   ─► record the tip being published, push, find-or-open
       agreed plan alone     the plan PR, record plan path + branch +
                             pr_number, re-anchor on the published tip, park
                             (discussion_plan_published); LABEL KEPT
     agent commits        ─► park (discussion_plan_invalid) naming the paths;
       anything else         a run that wrote outranks how it ended. "Anything
                             else" includes a deleted plan and an unreadable
                             worktree: neither proves the artifact is there
     push fails           ─► park (discussion_push_failed); the commit stays,
                             and a reply retries the publication the recorded
                             tip still marks as in flight -- settled before any
                             local probe, so a host that has lost the checkout
                             and the ref retries it from the remote too
     plan-shaped commit   ─► park (discussion_commits) via the blocked resume:
       under a park, with    a commit no round of this stage was running for,
       no round open and     and no publication of its own began, is not this
       no recorded tip       stage's to publish
     recorded tip the     ─► park (discussion_stale_publication) once: while a
       branch has moved      publication is in flight it answers for the
       off                   branch, so a second plan-shaped commit is refused
                             rather than published in the first one's name.
                             A branch back at the round's anchor spends the
                             marker instead -- but only once the remote is
                             shown not to carry the commit it names, or a plan
                             already pushed would be dropped from the record
                             with its pull request left open
     plan committed by a  ─► park (discussion_plan_unattributed): a PR body
       round that recorded    that cannot name the conversation the plan came
       no session             out of is not published
     resumed round paused ─► published on the next tick: the open-round flag
       or cut short after    written before the spawn is what attributes the
       committing the plan   commit under a park that is still durable
     recorded tip under a ─► the publication is finished on the spot, before
       park that is not      the turn-taking gate: its own write already spent
       discussion_push_      the reply that would otherwise carry the tick
       failed                there
     agent timeout        ─► park (discussion_timeout)
     dirty tree after the ─► park (discussion_dirty); the response is NOT
       run                   published as a design
     agent silent         ─► park (discussion_silent)
     paused mid-run       ─► nothing published; the pre-spawn round SHA is
                             what the next tick classifies by
     parked by discussion ─► nothing: no agent, no comment, no write
     parked by any other  ─► the first round opens anyway; that park is not
       stage                 waiting on a reply this stage will ever get
     relabel to           ─► implementing's guard: clean worktree, and a
       workflow:implementing  branch still at the round's recorded SHA (so its
                             commits are the ones the issue arrived with) ─►
                             drop discussion park, resume dev; dirty or a
                             moved/uncertified branch ─► park
                             (discussion_unsafe_relabel)
     human relabel        ─► done | rejected

   any stage ──► [park: awaiting_human=true]
                       (timeout, dirty tree, question, push fail,
                        unknown verdict, max rounds, retry budget
                        exhausted, failed checks, conflict-rounds
                        exhausted, invalid manifest)
                 wait for new human comment ──► resume locked
                                                 session (backend + args)
                 except a spent spawn budget under decomposing
                 or implementing (three holds: the initial
                 decomposition, the late adjudication under the
                 same label, and implementing):
                   no reply resumes it ──► held, keeping the manifest,
                                           children, session, commits,
                                           and PR -- and, on the late
                                           road, the frozen candidate and
                                           the hold on the pull request it
                                           stands under -- until a trusted
                                           /orchestrator continue renews
                                           the budget for one fresh spawn
                                           (a fresh conversation either
                                            way: the two initial roads
                                            retire the locked session as
                                            they buy the attempt, and the
                                            late one's pre-spawn record
                                            opens a new one)
```
