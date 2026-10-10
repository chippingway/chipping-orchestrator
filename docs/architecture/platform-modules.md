# Platform modules

This page maps the packages the workflow layer runs on: the package root and its two launch forms, the polling
`runtime/`, and the `config/`, `github/`, `agents/`, `scheduler/`, `git/`, and `skills/` domains. It is split out of
[`../architecture.md#top-level-layout`](../architecture.md#top-level-layout), which keeps the top-level map and the
naming rules that hold for the tree as a whole. The `workflow/` package is in
[`workflow-modules.md`](workflow-modules.md).

Each entry below is the responsibility its module owns, and it answers there and on no second site. What a stage does
with these owners is in [`../state-machine.md`](../state-machine.md).

## Enforced boundaries

Each rule below names what holds it, so a module that breaks one fails the suite rather than the next reader. The
last is held by the loader itself rather than by a check.

- **Layer position.** `config/` is the bottom layer and names nothing above itself; `github/`, `git/`, `agents/`,
  `scheduler/`, and `skills/` sit above it and below `workflow/`; `runtime/` and the two launch forms compose the
  lot. `tests/repository/test_layering.py` reads that direction twice, because deferring an import weakens where it
  lands but not whether it belongs.
- **At module scope, the workflow vocabulary.** Only `github/` and `git/` may bind the exact workflow owners
  `state.py`, `label_reading.py`, `transitions.py`, and `transition_guard.py`. They read and write the label vocabulary
  through those owners, which load no engine or stages. The check matches module boundaries, so a sibling cannot
  inherit this permission by wearing the same prefix.
- **Over every scope, declared per module.** Each remaining reach is a responsibility the workflow has not taken
  over. A base sync runs in the git layer but reports to the issue it was started for: `base_sync/conflicts.py`
  reaches `workflow/engine/comments.py` for the notice a conflicted rebase is handed to its stage with;
  `persistence` reaches `workflow/engine/guards.py` for the park every failure takes and
  `workflow/stages/implementing/late_approval_reading.py`, `late_approval_state.py`, `late_records.py`, and
  `late_transfer.py`, to read and drop the debt and the permission a rollback abandons when a refused push sends the
  branch back to where it started; `base_sync/terminal_handoff.py` ends an attempt a closed pull request strands;
  `base_sync/attempt_records.py` reaches `workflow/late_split/formats.py`, for the
  shape a recorded commit is held to, which spelled twice would let a pinned comment accept what every other reader
  refuses; `replay_publication_parks.py` reads `workflow/stages/decomposition/late_relabel.py`'s answer for whether
  a live adjudication holds the label, so its stranded park never asks for a label back that guard restores; the
  base-sync transfer owners read the higher-layer records only inside their calls:
  `transfers.py` reads `workflow/late_split/exemption_reading.py`, `rewrite_reading.py`, and `rewrite_values.py`;
  `transfer_values.py` reads the phase value, `transfer_evidence.py` reads the exemption and rewrite value,
  `transfer_attempts.py` reads the exemption, and `transfer_publication.py` reads
  `workflow/stages/implementing/late_approval_reading.py` and `late_publication_state.py` for the debt and
  receipt and rejects debts belonging to another attempt. `transfer_permits.py` loads the publication permit and
  frozen entry through `late_overflow.py`, `late_records.py`, `late_transfer.py`, and `late_gate_models.py`.
  Nothing in `base_sync` enters the size gate, stages report debt, or announces or routes a landing: the ordinary
  publication of a rebase, the crash recovery's retry of an unpublished replay, and its settlement and finish of a
  push already landed enter the gate and the finish from the workflow (`workflow/engine/rewrite_publication.py`,
  `rewrite_retry.py`, `rewrite_landed.py`, `rewrite_finish.py`), so no git owner reaches up for either.
  `publication/rewrite.py` reaches `late_rewrite.py` to enter a squash on its existing publication and publish through
  the size gate. Its reset and push steps also load
  `late_collapse_state.py` and `late_squash_proof.py`; `publication/resume.py` reads both, and `squash.py` and
  `standing.py` read the collapse state. These preserve the claim written before a destructive reset and prove
  whether a resumed squash may publish or roll back. Each import waits for the call that needs it. The same check
  declares them per module: an undeclared hop fails wherever it is written, and one of these fails if it is bound
  at module scope after all — where it would be a cycle, since the workflow imports the Git owners back.
- **Package boundaries.** Most initializers are markers; declared publishers retain explicit `__all__` surfaces.
  Other operations are reached on their defining modules. `config/__init__.py` binds each resolved setting and is
  the reload and patch target. Package import checks and `tests/config/test_surface.py` hold those boundaries;
  `tests/repository/test_package_exports.py` checks every initializer's source and namespace.
- **No second site.** No domain here sits behind a facade. Where a package replaced flat modules — `git/` and four of
  its six subpackages, `runtime/`, `skills/` — its own `test_imports.py` asserts that nothing resolves at the retired
  spelling, that no inventory or resolver hook names one as a target, and that no aggregate over the git domains sits
  above them — `tests/git/publication/test_imports.py` carries that last one. `git/measurement/` and `git/snapshots/`
  replaced nothing and hold the surface assertion anyway, and the same list carries `git/authentication.py`, the
  module the two transports were split out of, so no facade settles back at that spelling. The rule also holds one
  name at a time where a second binding would be invisible: each transport and the namespace listing reach the token
  lookup, the askpass session, and the session record through `credentials`; the branch transport reaches the
  `ls-remote` read a lease is taken from through `ref_transport`; the artifact discovery reaches the pattern
  listing nothing is leased to through `ref_discovery`; and the streamed runner reaches the hardened argv prefix and
  the environment assembler through `commands`, rather than importing any of them by name.
  `tests/git/test_imports.py` asserts each is bound on the owner that defines it and nowhere in the module that
  spends it — a copy beside the caller would read as the patch target a test aims at while the session, the read,
  or the listing a call actually takes stayed the owner's, and a copy of the hardening beside the streamed runner
  would be free to lose a protection the two runners it was taken from still have.
- **One road to a process.** The `agents/` chain is reached at one point from above and one per hop below it: only
  `workflow/engine/usage.py` names and calls `runner.run_agent`; only `runner.py` names
  `codex.run_codex` / `claude.run_claude` / `agy.run_agy`; and only the three
  backends name `processes.run_subprocess`. That is what makes the lifetime agent-run charge taken around that single
  call a charge every role pays, since a second caller anywhere would be runs nothing counts.
  `tests/repository/test_agent_spawn_boundary.py` reads the whole chain off the source, counting a reference rather
  than a call so a spawn bound into a variable is caught where its name is written, and holds the call itself to
  `_run_agent_tracked`'s own body with the circuit asked on a line above it.
- **Operator log channels.** Four names are spelled literally rather than derived from `__name__`, because an
  operator's level and handler selection is keyed on them: `orchestrator.git_plumbing` (`git/branch_transport.py`,
  `git/credentials.py`, `git/ref_discovery.py`, `git/ref_transport.py`, `git/snapshots/refs.py`,
  `git/snapshots/mirrors.py`, and the three
  `git/measurement/` owners that log, which all report on the same token, `ls-remote`, fetch, push, and diff
  plumbing),
  `orchestrator.base_sync` (`git/base_sync/state.py`, and the workflow's per-tick refresh on
  `workflow/engine/base_refresh.py`, so one filter follows a refresh into the owners here),
  `orchestrator.worktree_lifecycle` (the `git/worktrees/` owners that log, plus `runtime/artifacts.py`,
  `runtime/artifact_schedule.py`, and `runtime/artifact_records.py` above them — when a maintenance pass ran, why it
  did not (including a window that closed before its pass could start), and the record one candidate's answer could
  not be written as are facts about the same artifacts the owners under it report on, so an operator filtering for what
  happened to a finished issue's checkout is told about the day the host was too busy to attempt one), and
  `orchestrator.branch_publication` (`git/publication/rewrite.py`). A
  module moved between packages does not take its channel with it, and each of the four names is asserted where
  its owner is tested —
  `tests/git/test_branch_transport.py`, `tests/git/test_credentials.py`, `tests/git/test_ref_discovery.py`,
  and `tests/git/test_ref_transport.py`,
  `tests/git/base_sync/test_state.py` and `tests/workflow/test_imports.py`, `tests/git/worktrees/test_imports.py`,
  `tests/runtime/test_artifacts.py`, `tests/runtime/test_artifact_records.py`, and
  `tests/git/publication/test_imports.py`.
- **Import cost.** `import orchestrator` costs the root module and no owner behind it, and importing a `runtime/`
  owner plants neither the CLI nor an app — `tests/runtime/test_imports.py` and `tests/apps/test_imports.py`.
- **Direction inside `skills/`.** Neither owner may reach the workflow engine, a stage, or an application entry
  point: a catalog is observation the tick drives, not state a handler consults — `tests/skills/test_imports.py`.
- **Secrets.** `GITHUB_TOKEN` is read from the process environment or a token file outside `REPO_ROOT` — one per
  configured repository unless `ORCHESTRATOR_TOKEN_FILE` names one for all — never from a `.env` an agent with
  sandbox bypass could read: `config/_dotenv.py` skips every secret key it finds in either location and warns instead
  of loading it — see
  [`../configuration.md#github-personal-access-token`](../configuration.md#github-personal-access-token).

## The map

The entries below name defining owners and the deliberate public package surfaces over them.

```
orchestrator/
  __init__.py           the distribution version, published as `__version__`, without loading runtime owners
  cli.py                the `chipping-orchestrator` console script: the polling process's composition point
  __main__.py           the `python -m orchestrator` launch form over `cli.main`, and what `run.sh` starts
  runtime/              the polling process's own owners
    state.py            the mutable state one run carries -- the stop flag, the signal, the scheduler a handler may
                        close, the host claim a pass turns into exclusive ownership, and the drain's event -- plus
                        the shell-style code a signal stop exits with
    logs.py             the stderr and rotating-file destinations a run settles before its first client
    options.py          which launch mode a run is and how loud, read without loading any configuration -- the one
                        owner here `cli.py` imports before the command line is parsed, so `--help` answers on a
                        host with no settings or a malformed `REPOS`
    startup.py          the stop of every launch whose author allowlist names nobody, one client per configured
                        repo -- in the bootstrapping form a tick needs and the read-only form a run that will not
                        tick may have, which is the one write a connect makes -- and the scheduler every tick shares
    ticks.py            one pass over the configured repos: the per-repo tick, the fan-out, and the reap / prune
                        drains
    loop.py             one-shot vs recurring polling, the interruptible wait, the artifact-maintenance step the
                        recurring form fits between passes, and the guaranteed scheduler drain
    artifacts.py        whether the artifacts of finished issues may be reclaimed now and what the pass is allowed to
                        see: the gates a pass defers whole without -- a claim on this host at all, then the scheduler
                        hold over this process's own workers, and only inside that the exclusive hold on the host,
                        since a presence may only be handed over by a process that has already gone quiet and has to
                        be back before admission reopens, and last a scheduled pass's own due gate asked again from
                        inside both -- and the split of one host-wide discovery back
                        into the client of the repository each candidate belongs to. Two of this process's own
                        readings go down with it, asked per candidate: whether anything is running for that issue,
                        and whether the run may still act at all -- the run's stop flag, the scheduler's close, and
                        the budget bounding how long one pass may hold the host, which is what the process waiting
                        for it is owed
    artifact_schedule.py when a polling run owes itself that pass: the in-memory due gate between polling passes,
                        on the monotonic interval or -- taking precedence where set -- the local window, named by the
                        date it opened on and read again from inside both holds, so only a pass that starts spends
                        it, a deferral before that is retried no sooner than 15 elapsed minutes later, and nothing is
                        caught up outside the window
    artifact_records.py the one bounded record each of those candidates is reported to the analytics sink as, and the
                        only thing the pass leaves anywhere but the log: exactly one per candidate DECIDED about --
                        never one per artifact, phase, or deletion step -- carrying the repository, the issue, the
                        outcome, the closed reason that fixes it, the layout it was published under, and a branch
                        only where the reason names one this repository itself publishes that issue under. Which
                        KIND of artifact a subject is comes off the reason rather than the string, since a checkout
                        path and a branch name are the same text on a host whose `WORKTREES_DIR` is `orchestrator`,
                        and what is written is the derived name rather than the one that arrived. Every
                        vocabulary is proved again as the record is built, so a lookalike value writes no record
                        rather than a record nobody should have written, and nothing a teardown touched -- a command,
                        its output, an exception, a checkout path, a tree's contents -- can reach a sink through it.
                        Built from results the pass has already produced and written behind a boundary per candidate,
                        so a record it cannot build costs one line and changes no decision; the sink's own two
                        answers never reach it, being silent when it is off and reported on the analytics channel
                        when the filesystem refuses the line
    host_lock.py        the artifact lock's descriptor operations and interruptible acquisition wait. Only
                        contention is retried; other lock errors report that the host cannot be coordinated on
      exclusion.py        which process on this host may take the artifacts: one `host_lock.py` claim under
  `WORKTREES_DIR`,
                        held shared for a polling run's whole life and exclusively for as long as any pass acts --
                        including a polling run's own pass, which hands its presence over and takes it back, so a
                        second daemon cannot be submitting while this one deletes. A pass never waits for it and a
                        poller always does, without a deadline, because there is no length of wait that makes
                        polling through a teardown safe -- and only for a lock somebody HOLDS, since a lock that
                        does not work is nobody's and waiting on one would never end. Beside the scheduler's issue
                        writer claim, the only coordination in the tree that is not between threads, and the only
                        thing that can answer for the artifacts of a process whose scheduler this one cannot read;
                        a lock rather than a marker, so a host that died mid-pass comes back with a stale file and
                        no claim
    self_update.py      the git probes behind the self-restart guard
    shutdown.py         the signal handler, the bounded-drain watchdog, and the forced exit it ends at
  config/               publishes resolved settings and `RepoSpec`, with parsing owned by its leaves
    __init__.py         reloadable settings bindings, their diagnostic funnel, and the default repo-spec accessor
    environment.py      the env-value parsers and the `_SettingsResolver` that reads and validates every knob
    _dotenv.py          the non-secret `.env` loader, reading a source checkout's own file or else the user location
    checkouts.py        whether a directory is the top of a git checkout, answered by git itself: a read-only
                        `git rev-parse` about its own `.git`, never a discovered one, then one discovering it from
                        inside for git's ownership check; it starts git as a program and imports nothing from `git/`
    layout.py           whether the package runs from this project's own source checkout or an installed
                        distribution, and the worktree root's default beside the first configured target
    credentials.py      process / token-file credential resolution per repository and the secret redactor the verify
                        output, the agent stderr diagnostics, and the trajectory writer mask with
    models.py           the `RepoSpec` / `RepoEnvEntry` repository-config types
    repositories.py     `REPOS` entry parsing and validation, the choice between `REPOS` and the developer fallback
                        only a source checkout is offered, and the refusal of every selected target that is not a
                        checkout
  github/               publishes `GitHubClient` and `PinnedState` from their defining owners
    client.py           authenticated PyGithub setup, worker-thread clones, paired stage-entry records, and canonical
                        repository identity; a clone reuses the parent's token and bot login on a requester of its
                        own and fetches its repository only on the first read of repository metadata, while
                        number, label, and commit operations stay eager at the call; ownership checks complete that
                        repository first, use GitHub's repository name case-insensitively, and reject a head with no
                        repository; `repo_id` answers the numeric id no rename changes, completing a clone's
                        repository the same way, with no fallback to any name, for the writer claims to key on
    aliases.py          the descriptor a stateless helper is bound onto the client with, so class, instance, and
                        module access all answer alike
    checks.py           status / check-run normalization, failure-before-pending folding, and the fail-closed check
                        reads
    comments.py         the `ALLOWED_ISSUE_AUTHORS` trust policy a caller filters a thread or gates one author
                        through, whether a comment on a thread was written by US -- the author check the marker
                        lookup here and both park-notice reconciliations gate on, since a receipt recognized by a
                        hidden marker and one recognized by its whole sentence are alike text anybody may post and
                        so alike text anybody may use to suppress what it stands for -- and the reserved prefix
                        every receipt this orchestrator hides shares, so content somebody else wrote can be refused
                        before it is embedded, plus the ordinary marker every comment this orchestrator posts
                        carries, defined here so a GitHub-layer owner can render a whole comment body; the
                        low-level comment and review readers stay raw
    developer_reports.py
                        the developer-report comment format: a report is appended as its own comment rather than
                        written into a description that carries closing references, attribution, a legacy
                        `_Last agent message:_` tail, and human text; it names its commit, requirements revision,
                        report revision, and what it supersedes, and ends with a hidden header carrying that
                        identity, the transaction receipt, and the text digest. A report the header cannot carry,
                        one quoting a receipt marker, and one past a comment's length are refused rather than cut,
                        and a comment reads back as a report only when it is ours and re-renders byte for byte --
                        never one whose header claims a count of more digits than Python converts
    events.py           audit event record construction and the optional JSONL sink
    issue_polling.py    the one walk over a repository's issues a tick is served from: the open poll, the
                        cadenced closed sweep beside it, and the shared number set both filter through so an
                        issue two queries return is dispatched once, and which drops the pull requests those
                        queries also list by the `_pull_request` slot PyGithub filled from the page, since the
                        public property would spend a detail GET on every real issue to answer, asking that
                        property only of a row whose slot is missing or in a shape it does not recognize -- plus
                        the pairing of every swept label with
                        its pre-namespace spelling and with whether a miss on that spelling is the expected
                        answer, since a closed issue is the one case no other pass revisits and a repository the
                        rename did not reach has nothing else left to find it by. Sits directly above `issues`
                        in the client's mixin chain, which is the owner it reads its label sets and its
                        issue-state spellings from
    issues.py           issue writes, the query options, the wire issue-state vocabulary, the closed predicate
                        every reader of it asks through, the every-state, no-label walk that finds the first
                        issue carrying a marker -- the reading a receipt lookup needs and the only one that
                        sees an issue a human has since closed or relabelled -- or every one of them, for a
                        caller that has to know its match is the only one, and the labels whose CLOSED
                        issues a sweep still owes a pass: the recovery set whose terminal arc has not drained,
                        and the cleanup set, which is where a late adjudication runs plus where an interrupted
                        cancellation can be left -- read from here by the poller that queries them and by the
                        dispatcher that routes a closed issue on them alike; plus the one question about an
                        issue's PAST this client answers -- which workflow label THIS orchestrator applied to
                        it LAST -- which is what a removed label leaves no other trace of, and what tells one
                        attempt at a state from an earlier one, since every state this workflow moves an issue
                        to is itself an application; the actor is filtered on the same account the pinned
                        comment is authenticated under, so a name a collaborator applied by hand is not a
                        write of this orchestrator's; control labels are excluded, and no account, no
                        evidence, and an unreadable walk all answer alike
    labels.py           label vocabulary, bootstrap specs, in-place legacy-label renames, and cached reads; confirmed
                        absences expire after a bounded number of closed sweeps, request failures stay retryable,
                        and each sweep reports only the absent legacy spellings it observed
    pinned_state.py     the pinned durable-state model, the comment body it is written as -- with the wrapper's own
                        terminator escaped in the SERIALIZED payload and never in the value, since a recorded
                        explanation or a preserved pull-request body carrying `-->` would close that comment early
                        and leave the rest of the record as visible issue text, and with that escape stood down for a
                        payload it would put past the limit, since the record is what a later tick reads while the
                        escape only decides how the comment LOOKS, and a write refused for a rendering takes whatever
                          park, notice or outcome it was carrying with it -- and the length GitHub takes, its parser
  -- which identifies a state-only comment whatever payload it carries
                        and keeps the one carrying no readable state, whether it would not parse or parsed
                        into anything but an object, apart from an issue that recorded nothing, since both read
                        back as `{}` -- and the comment watermarks beside it, whose thread read tells the pinned
                        comment by the ID a caller can name where it has one and by the marker in a body
                        otherwise: the marker also hides every comment merely QUOTING it, which is right for a
                        reader after conversation and wrong for one after a receipt it posted itself. That cut is
                        taken over a read the CALLER already holds wherever one is handed in, and over a read of
                        its own otherwise, because a stage deriving several answers from one batch -- the prompt,
                        the watermarks that batch settles, the requirements it fingerprints -- owes every one of
                        them to the same read: a second read is newer, so a comment landing between the two enters
                        some of those answers and not the others. A field is
                        asked about two ways and the model answers both -- what one HOLDS, and whether the
                        comment CARRIES it at all -- because every fail-closed reader in this repository turns a
                        value nothing can act on into an absence, so a caller asking whether the record CLAIMS
                        something could not otherwise tell an issue that never wrote a field from one whose
                        field a hand edit truncated. The record is written two ways. The legacy write lands a state
                        wherever it can -- in place, or as a new comment where none is named or the named one is
                        gone -- which every caller owning the whole record relies on. The strict edit a guarded
                        commit lands through rewrites the named comment in place only while the walk that finds it
                        still reads it, parsed, as the payload the rewrite was derived over, compared as the
                        comment's JSON spells both (`PinnedState.reads_as`); it never recreates a comment that is
                        gone or no longer the authenticated state-only one, and answers EDITED only where GitHub's
                        response carries the body sent -- a lost response, a refused request, and an answer carrying
                        another body are all UNCONFIRMED, since the record may read either way. Its two requests
                        are primitives the in-memory double overrides, so the double answers through this policy.
                        A state read from the comment or written over it remembers what the comment carried then
                        (`PinnedState.synced`), spelled as its JSON is and outside the record itself, so what a
                        tick staged on it since can be told from what it read; a state the guarded commits taken
                        through `workflow/engine/report_commits.py` -- the developer report's, a validating
                        reviewer round's, a change request's handoff and its recovery's, and an approval tail's --
                        did not land over -- refused over a comment that moved, or sent and never confirmed -- or
                        whose report post or re-read left its transaction owed over a comment another road wrote
                        meanwhile, or whose approval tail's records the comment moved, is marked `withheld`, and
                        the legacy write
                        writes nothing for it, since written whole it would put back what another road wrote past it
    pull_request_reads.py
                        PR status, open and commit-pinned lookup, branch enumeration, and unreadable-publication
                        evidence; a caller choosing its publication thread can narrow to a base, while a caller
                        proving any publication leaves the base unrestricted
    pull_request_reports.py
                        finding, posting, and rereading developer reports on a pull request's conversation; every
                        reading is present, absent, changed, or unconfirmed, and only absent is posted onto, so a
                        retry finds the comment an earlier attempt landed -- scoped by its transaction receipt, so a
                        later report on the same commit is a comment of its own -- while a pasted copy is not ours
                        and a post whose response was lost stays unconfirmed until a read settles it, as does a
                        thread whose comment authors would not read, since those tell ours from a copy. A human's
                        report is reread by its exact pull request and comment (or description) against the
                        content digest somebody verified, and the description is never written. A reading also
                        carries the identity of what it found, resolved ONCE when the reading is taken rather
                        than answered afresh to whoever asks: the id is a member of an object GitHub handed
                        back, so it is a request that can fail once and succeed the next time -- and the
                        publication road asks twice, to write the comment ledger and to record where the settled
                        report sits. Two answers there leave a report recorded at a comment nothing recorded
                        posting. The read is guarded for the same reason every reading here is, since its
                        callers run inside a dispatch guard where a raise leaves by an exception rather than by
                        an answer
    pull_request_retirement.py
                        idempotent supersession notices followed by closure; an authenticated marker read can travel
                        from the caller so no extra request intervenes between its final proof and the write
    pull_request_verification.py
                        finding and posting the workflow verification artifacts on a pull request's conversation,
                        over the same road the developer report takes and with that owner's own readings rather
                        than a second vocabulary saying the same thing: every reading is present, absent, changed,
                        or unconfirmed, only absent is posted onto, and the lookup is scoped by the transaction
                        receipt, so a retry finds the comment GitHub already accepted and a later artifact on the
                        same commit is a comment of its own. What a retry finds is an artifact rather than a body:
                        a comment of ours under the receipt is present only where it reads back, validated in its
                        own format, as an artifact equal to the one asked for -- the whole identity, every command
                        with its status and transcript, and so the evidence digest -- and changed where it reads
                        back as anything else or as nothing. It is never compared with the body the writer would
                        post now, and the writer is asked only once a reading is absent, so a comment an earlier
                        attempt landed is recovered as it stands, neither rewritten nor posted again, even where
                        the writer's body for it would now differ or not fit in one comment; an artifact that
                        would not fit is refused there, before the post. A pasted copy is not ours; a post whose
                        response was lost stays unconfirmed until a read settles it; an artifact for another pull
                        request is refused before any request is made. `reread_verification_artifact` scans this
                        owner's own thread read for the one comment an evidence settlement recorded and answers
                        with the artifact of ours it still is -- our author and an exact rendering in the
                        comment's own format -- or why it is not; it does not go through the report owner's
                        digest-based `reread_report_location`.
                        The thread read and the post are this owner's own seams, so the in-memory double answers
                        them for artifacts without inheriting whatever a case arranged for reports.
                        Recording the comment an artifact landed as belongs above this layer, since the ledger of
                        this orchestrator's own comments is pinned state: a caller publishes through
                        `workflow/engine/verification_comments.py`, which takes that id off the reading returned
                        here
    pull_requests.py    PR creation, comments, body edits, labels, SHA-pinned merge, and remote-branch deletion;
                        the mutation mixin includes the read, retirement, and both evidence owners --
                        developer-report and verification-artifact, grouped because they are one kind of thing
                        reached one way -- in the client's inheritance chain
    reviews.py          current-head review aggregation: approval verdicts and unread-feedback watermarks, and the
                        pull request's conversation read whole (`pr_conversation_thread`), a body quoting the pinned
                        state's marker included, for a caller finding words it posted itself
    verification_artifacts.py
                        the workflow verification artifact: the workflow's own evidence about a tested tree, appended
                        as its own comment beside the developer report rather than into it and never into the
                        description, so the report keeps its own source identity and no human-authored sentence is
                        rewritten. It names the repository and pull request, the commit and tree the commands ran on,
                        the head the pull request carried when it was written, the review subject and requirements
                        revision it answers for, and the verification-context revision it ran under -- four object
                        ids rather than one, because evidence carried forward, the round it answers, and the head
                        that has moved since are three different commits. Each artifact carries its own revision, so
                        several on one commit read as an ordered history; the hidden header repeats that identity
                        beside the transaction receipt and the digest of the evidence, and the ordinary
                        orchestrator marker closes the body, which is what keeps a generated artifact from ever
                        being read back as a human's fresh feedback. An identity the header cannot carry and a body
                        past a comment's length are refused rather than cut. The writer publishes the compact format
                        (`verification_compact_artifacts.py`); the reader is format-aware: a comment carrying the
                        hidden payload is held to the compact format's canonical body and any other to the legacy
                        format's (`verification_legacy_artifacts.py`), byte for byte either way, and both read back
                        as the same artifact under the same evidence digest, so a historical comment is never
                        rewritten, re-digested, or refused for what the current format would make of it. A comment
                        reads back as an artifact only when it is ours and re-renders exactly -- never one whose
                        payload was tampered with, whose summary or header disagrees with its evidence, whose header
                        claims a witness this format does not name or a count of more digits than Python converts,
                        or whose evidence reconstructs past what a comment holds, which a body short enough to have
                        been posted still claims once its own presentation is replaced. Every such claim is ANSWERED
                        rather than raised: the question is asked of somebody else's comment, on a thread anybody can
                        post to, so nothing a comment says about itself may leave the scan that asked by an
                        exception. The writer lays the one-comment bound over the canonical body only on the way to
                        a post, so whether a published comment is an artifact never turns on what the writer would
                        post now
    verification_compact_artifacts.py
                        the compact format every artifact is published in: a concise visible summary -- whether the
                        recorded checks passed (at least one, every one exiting 0), failed, or never ran, said in
                        words so an absence never passes for a pass; the artifact revision and the `sha256:`
                        evidence revision; the witness; the tested commit and tree; and the target head, named an
                        equivalent-tree carry where the checks never ran on it -- and no command inventory or
                        transcript. The commands, their statuses, and their whole output travel in the hidden
                        payload `verification_payloads.py` encodes, in an HTML comment of its own ahead of the
                        header; that comment's opener is what tells this format from the legacy one, whose evidence
                        could never carry a marker of ours. It reads a body's commands back out of the payload and
                        spells the canonical body a comment claiming this format is held to
    verification_evidence.py
                        what an artifact reports and who witnessed it: one command, the status it exited, and
                        whatever bounded transcript the artifact carries for it, rendered once here so the digest
                        an artifact publishes is taken over one spelling of them -- the spelling a reviewer handed
                        the evidence is quoted and a legacy artifact showed, whichever presentation carries the
                        commands. Orchestrator-executed evidence is this process reporting commands it spawned
                        itself; reviewer-reported evidence is a reviewer run's account of commands nobody here
                        observed, and the witness travels with the commands rather than being a footnote to them. A
                        command carrying the backtick that delimits it, a transcript carrying the fence that closes
                        it, and either carrying a receipt marker of ours are refused where they are declared, which
                        is the only place they can still be told apart from a rendering. No command at all renders
                        as an explicit absence, since a section that simply listed nothing would read as a run that
                        passed. The content revision is taken here too, over that rendering, so every presentation
                        of the commands names them by one revision
    verification_legacy_artifacts.py
                        the format artifacts were published in before their evidence was hidden -- a prose preamble
                        naming the witness and the whole identity, a rule, and every command with its status and
                        transcript in view -- kept for reading alone: the commands its visible section reads back
                        as, and the exact body it spelled an artifact as. Frozen rather than derived from the
                        current writer, so a historical comment keeps re-rendering as it reads; its digest was
                        taken over the rendering `verification_evidence.py` still hashes, so evidence settled on
                        one stays settled
    verification_payloads.py
                        the versioned codec for an artifact's hidden evidence: every command, the status it
                        exited, and its whole transcript, in order and with repeats, spelled as one JSON object
                        that can sit inside an HTML comment, beside the content revision `verification_evidence`
                        takes over the rendered section -- never one taken over the payload, so evidence keeps
                        the revision it was settled under however an artifact presents it. JSON escapes every
                        character past printable ASCII, and both angle brackets are escaped in the serialized
                        text, so the payload is one line that cannot end its comment early, render a
                        transcript's tail as visible content, or open a receipt marker of ours. Decoding answers
                        rather than raises, since it is asked of text on a thread anybody can post to: a payload
                        is evidence only when it is the one spelling written for the commands it decodes to,
                        each read through the evidence model's own constructor, so a malformed payload, another
                        version, a member of the wrong type or shape, a command the model refuses, or a revision
                        the commands do not hash to all read as none. It owns the payload text alone; the
                        comment around it and where it sits in a body are the compact format's
                        (`verification_compact_artifacts.py`)
  agents/               publishes the run/result models, runner entry point, and process shutdown hook
    models.py           the agent result and unfinished-step diagnostics, run-option, and subprocess-result models
    environment.py      credential and virtualenv filtering and the injected git identity
    session_ids.py      the backend-agnostic session-id walk: a UUID-shaped value at a known key, anywhere in
                        any CLI's event tree, so a resume is issued against what the run actually reported
    sessions.py         Claude final-message JSONL parsing, including the terminal result event the final
                        message is taken from, published whole for the reader of the flags beside it
    codex_events.py     Codex `exec --json` terminal-turn parsing: the error the `turn.failed` closing the last
                        turn the stream started carried -- its message, and the `codex_error_info` code in
                        either serialized shape when the CLI printed one -- read off stdout, since a failed
                        turn leaves the `-o` file empty. A last turn that completed or never closed, its
                        closing line undecodable included, reports no failure, mid-turn `error` events never
                        decide, and lines that are not JSON objects are skipped wherever they sit
    provider_failures.py
                        the transient-provider verdict every stage that reads a final message as the agent's
                        own asks first: the backend's `is_error` flag where the run gave one, and the
                        server-refusal message prefix beside a non-zero exit where it did not; the wider
                        verdict of any provider refusal, 4xx included, for a caller settling whether a run got
                        to its prompt at all, where the prefix alone decides when no flag was given; and the
                        Codex usage-limit stop, returned as a `CodexUsageLimitFailure` diagnostic carrying
                        the provider message verbatim (unredacted and unbounded, for its consumer to redact
                        and bound) and the reset time as phrased: a `usage_limit_exceeded` code on the
                        closing turn's error decides it, any other code rules it out, and a code-less error
                        falls back to the provider's opening words only beside a non-zero exit. No workflow
                        stage asks it yet
    process_groups.py   what a child started into its own process group costs to tear down, apart from any
                        record of which ones are in flight: the bounded drain that reports a pipe a descendant
                        still holds open rather than blocking on it, the `killpg(_, 0)` probe that answers
                        whether the group kept anybody after its leader is gone, the wait-then-SIGKILL
                        escalation that reads it, and the per-timeout SIGTERM over that escalation
    processes.py        the shared process registry, the agent runs spawned into it, and the shutdown sweep
                        that SIGTERMs every registered group before spending the escalation beside it under
                        one deadline
    runner.py           `run_agent`: backend dispatch, result assembly, and spawn logging
    backends/
      codex.py          Codex command construction, scratch output, and execution
      claude.py         Claude command construction and execution
      agy.py            Antigravity command construction, terminal-result gating, and conversation resumes
  scheduler/            publishes `IssueScheduler` and `SubmissionRequest` from their defining owners
    models.py           the typed submission, the historical `submit` binding, and field normalization
    service.py          the concrete scheduler: the caps, the tracked claims, the family mutex, dispatch, and
                        shutdown, plus the reversible maintenance barrier -- both admission paths closed, the
                        already-admitted work waited out within one finite bound, and the hold given back around
                        the body whatever the body did. The closed reading beside it is what a caller spending a
                        granted hold comes back for: the grant was true when it was given, and a signal lands a
                        line later. What a refused submission MEANT is the caller's -- a cleanup
                        refused because a worker holds the issue costs an observation rather than a turn, and the
                        workflow keeps that reading where its own stage handlers can reach it; a submission refused
                        by a held barrier costs the caller its next polling pass, which is why it is reported apart
                        from a closed scheduler
    writer_claims.py    the host-local writer claim every dispatch path takes for one repository issue, a family
                        handler takes for each child it writes, and the base refresh takes for each worktree it syncs,
                        all on the one key in the one namespace. An exclusive `flock` per
                        issue in `WORKTREES_DIR/.issue-writer-claims/`, keyed by the repository's numeric id as the
                        client answers it -- never a name, which a rename changes under a running poller -- and the
                        issue number, and taken without waiting. A contender is refused rather than kept waiting, and a
                        claim that cannot be worked -- an unopenable namespace, a filesystem without `flock` -- is
                        refused too, where the artifact presence would let a poller go on unclaimed. Exclusive between
                        this process's threads as well: one lock per key is held for the process and its holders
                        counted, a second writer here is refused as `held_here`, and a holder asking `alongside` -- a
                        close receipt, a consumer notice -- is let in beside a writer of this process's own. The last
                        holder to leave unlocks and closes the descriptor, and the kernel drops it with a dead process;
                        no claim file is ever unlinked, since a path recreated over a held inode would let two processes
                        each hold the claim. Every acquisition reads what the last hold left -- its token, and the
                        moment it let go on the host's monotonic clock -- notes when that hold ended where it was
                        another process's (when it is found, for a holder killed holding it, which stamped nothing;
                        never, for a stamp from before the host last started), then empties the file and signs it with
                        this process's own token; the last holder here stamps its release before it unlocks. Every
                        record is a whole line or nothing: a write that lands short is cut back and fails, and what a
                        reader cannot take for whole -- a line with no end, a file nobody signed, an empty one included
                        -- reads as a hold that ended when found, never as a stamp or a note. An empty file is no proof
                        nobody held the key, even one this process just created: between its open and its lock, others
                        can have held the key and emptied the file. It coordinates the pollers sharing one checkout root
                        on one host and nothing beyond them, imports nothing of the runtime, and is not the artifact
                        presence: neither says anything about the other
    claim_notes.py      what the holds on an issue's writer claim tell the pollers sharing it: the moment a poll reads
                        before it lists anything, and whether every hold by another poller this process has found on the
                        key had let go before such a moment -- asked under the claim, no other poller wrote the record
                        since the poll read it, while a hold that ended earlier, a restarted poller's predecessor's
                        included, costs the reading nothing -- and the late cycle a hold notes it is retiring, written
                        by a writer holding the key and read by a contender it refuses. A note is its own hold's, and
                        read only off a file that hold signed and has not stamped as released: the next holder has the
                        lock a moment before it empties the file, and the stamp keeps a released hold's note from being
                        read in that moment. A hold killed holding the claim, or whose release stamp could not be
                        written, leaves no stamp, so its note is read until the next holder empties the file -- the last
                        hold to write the issue until then. One that cannot be written whole, or parsed from a whole
                        line, reads as no note
  git/
    branch_transport.py the authenticated fetches, the remote read that answers what a branch is at without trusting
                        a local ref -- in the plain form a caller acts on and the form that also carries why a read
                        established nothing -- and the lease-pinned branch push, each spending one credential
                        session
    commands.py         plain / hardened git execution in a decoded and an undecoded form over one shared
                        environment, the argv hardening and no-prompt environment every hardened call is spawned
                        under -- the streaming owner's included -- the per-call environment pin every hardened
                        form takes over that envelope, the absolute `--work-tree` argument a working-tree
                        operation names its tree with, the unsafe local-transport probe, and the one line of a
                        failed call's output a caller carries away from it
    credentials.py      the per-repo token lookup, the owner-only askpass script that outlives no operation, the
                        session record a token-bearing call is spawned from -- the detached environment, the URL
                        naming only the `x-access-token` username, and the token itself -- and the redaction every
                        token-bearing caller puts that token's own output through before logging or handing it
                        back
    locks.py            the per-target-root re-entrant lock registry and its accessor
    ref_discovery.py    the one remote question that starts from no name at all: every refname a remote
                        carries under one pattern, which is the only way a branch this host holds no copy of is
                        found. Its own owner because nothing is leased to what it says -- the empty tuple is a
                        remote holding nothing under the namespace and `None` is a remote nobody could ask, and
                        a caller that collapsed the two would read a repository it could not reach as one with
                        no artifacts left
    ref_transport.py    the remote read of one refname -- with the scrubbed line saying why nothing was
                        established -- and the lease-pinned write and delete an immutable ref namespace is owned
                        through, the delete spent as well on a terminal issue's branch once the artifact pass
                        has proved the commit it stands on; the single-ref read the branch transport spends for
                        its own lease too
    streaming.py        the hardened form for an answer this process may not hold whole: the request handed
                        in on stdin, stdout passed to a consumer a chunk at a time and assembled nowhere, and
                        stderr captured to a file rather than a pipe nobody drains, so the peak is one chunk
                        however large an agent made the content behind it. Reads the argv prefix and the
                        environment off `commands` rather than restating either
    base_sync/          the auto-rebase of every worktree the workflow's per-tick refresh walks
                        (`workflow/engine/base_refresh.py`): the selection it asks first, the pre-PR rebase it
                        runs, and the gates, rebase, candidate, push or observation, and recovery readings and
                        parks its base-rewrite coordinator (`workflow/engine/base_rewrite.py`) and the workflow's
                        publication, recovery, and finish beside it (`workflow/engine/rewrite_publication.py`,
                        `rewrite_recovery.py`, `rewrite_retry.py`, `rewrite_landed.py`, `rewrite_finish.py`) order
                        for a pushed branch
      refresh_selection.py
                        which discovered directories name an issue, whether that issue reads at all, and the
                        order the refusals that end a sync before any rewrite are asked in: the hard-skip, the
                        records the `frozen` owner answers for, the read-only stages and the parks they leave
                        behind, and last -- because it is the only one that costs a read of the checkout -- the
                        commit a stage still owes a step, which is also where the label scope on the two
                        freezes no write ever ends is applied. Beside an auto-rebase anchor only the late claims
                        the reconciliation answers freeze the walk and a read-only park is set aside: the
                        dispatcher holds every handler that would end the rest, so none of them may freeze the
                        recovery out as well
      frozen.py         which records hold a checkout still and what ends each freeze: the ones that freeze a
                        branch by their presence -- the late reading, the approval, and the terms of a squash
                        mid-rewrite among them, each read as the whole GROUP its write puts down rather than as
                        its commit alone, since a record carrying part of one is what the dispatcher parks on a
                        tick LATER and a hold keyed to the commit would rebase and push it first; with one
                        exception, an approval leased to an auto-rebase anchor still pinned here, which is this
                        refresh's own interrupted work and may not freeze the branch out of the recovery that
                        anchor exists for. The collapse group is read one step stricter still -- the key being on
                        the comment AT ALL, `null` included -- because that is what the squash's own reader counts
                        as a claim it must refuse to resume, and what a rebase there destroys is the tree
                        relationship the recovery proves the collapse by; nothing sets that group aside, since it
                        is another owner's work rather than this refresh's own. A developer report recorded and
                        not yet settled -- `developer_report_delivery` or `developer_report_pending` anything but
                        `null` -- freezes it too, since a delivery binds to whichever head the receipt names and a
                        transaction names the head it was written about, so a rewrite between would bind a report
                        to a head no developer read or strand it on one the pull request left; the binding and
                        the settlement write each `null`, which ends that freeze -- the two parks that freeze one
                        with no record behind them at all
                        (a size reading nobody could take, and an implementer timeout whose watermark names a
                        commit not yet made), and the two no write ever ends (the accepted commit and the
                        published one), which freeze only while the checkout still stands on the commit they
                        name and only while the stage that has to act on it still holds the issue
      eligibility.py    the label, park, open-PR, and clean-tree gates one PR sync clears, the clear or park an
                        anchor under a label the refresh does not drive takes, and whether a park a stage left
                        still owes a standing anchor its recovery -- which the workflow's recovery coordinator
                        runs; a terminal PR ends an anchored attempt's whole handoff through `terminal_handoff`
      pre_pr.py         the hardened rebase / merge probes and the aborting pre-PR local rebase
      startup.py        the pre-rebase HEAD guard, and the anchor and the attempt's terms persisted before git
                        runs -- the write that spends the reply a park of the refresh's let the rebase start on, and
                        carries the retry the workflow staged read from it (`workflow/engine/rewrite_replies.py`)
      attempts.py       the replay checkpoint, the announcement mark's presence checks, and the whole-record clear
                        that ends an auto-rebase attempt. The workflow's publication records its replay here; the
                        workflow's finish of every landing puts the mark down through its own guarded checkpoint,
                        while the anchor still stands and before relabeling, and reads it back here; the
                        workflow's handoff of an unpublished replay to a late generation
                        (`workflow/engine/rewrite_takeover.py`) retires the whole record through the same clear,
                        and with it any `auto_base_rebase_*` park the attempt's own road left (`_retires_its_park`)
      attempt_records.py
                          validate interrupted replay terms and head as absent, declared, recorded, or damaged,
  sharing the replay
                        field group with the lifecycle clear. Commit validation uses the late domain's format
                        reader through a call-time import
      rewrite_handoffs.py
                        the frozen, data-only handoffs an automatic PR base rewrite crosses the git boundary as:
                        the candidate -- original and rewritten heads and their trees, the branch, the base and
                        remote readings, the worktree status, and the attempt's anchor, pull request, and stage --
                        and the landed record of one lease-pinned publication of it, an uncertain answer included;
                        and where a landed head stands against the base it was counted against (`_BaseStanding`).
                        None carries a GitHub client, an issue, pinned state, or a callback. The workflow's
                        ordinary publication of a clean rebase, its retry of a replay a crash kept off the pull
                        request, and its recovery of a push already landed read, publish or observe, and finish
                        through them
      rewrite_facts.py  reads a candidate off the checkout and the remote -- or carries a remote reading its caller
                        already decided on, the head a recovery's fetch verified -- and reads both again before a
                        push: a head that left the candidate, a tree dirtied or made unreadable, a base ref rewound
                        so it no longer contains the tip the replay sits over, or a remote off the anchor --
                        already on the candidate included, which excuses none of the others -- refuses, while a
                        base that only advanced does not. For a landed head it also answers whether the head
                        still stands on its base (`_standing_on_the_remote_base`): the remote's base still on the
                        tip the head was counted against, read without a fetch, and the head carrying over it no
                        more than a rebase of the anchor onto it replays -- standing, moved, dropped by a base
                        rewound under it, or unread
      rewrite_transport.py
                        publishes exactly the candidate's rewritten head, leased to its original one, through the
                        branch transport once that fresh reading refuses nothing, so a publication that landed is
                        never sent again, even for the same frozen candidate. The reading and the push are separate
                        calls, so a caller asks whatever it must between them; a remote the candidate was prepared
                        standing on is read again too, and a landing the fresh reading shows is proved, where a
                        caller asks, by a push leased to the candidate itself that sends nothing. A push git answered
                        with a failure is classified by reading the remote again -- elsewhere is a rejection, on the
                        candidate or unreadable is uncertain; observing a landing reads the remote afresh and
                        pushes nothing, which is how the workflow's recovery of a push already landed
                        (`workflow/engine/rewrite_landed.py`) finishes an accepted push whose answer was lost
      transfer_values.py
                        the bounded transfer handoff vocabulary and settled-phase reading, loaded lazily from the
                        workflow record when needed
      transfer_evidence.py
                        rebase contribution and publication evidence over the remote-frozen base; recovery requires
                        the pending attempt to vouch for its actual checkout before reconstructing a grant
      transfer_attempts.py
                        agreement between the authorization's lease, pending publication, and adjudicated pair;
                        settled permissions name the rewritten pair and outstanding ones name the accepted pair
      transfer_publication.py
                        whole debt and receipt proofs for recovered publication and rollback; an unreadable approval
                        or a receipt for another head or PR cannot prove this attempt settled, and a leased no-op's
                        receipt, leased against the commit itself, accounts only for a settled transfer on that PR
      transfers.py      classify the exact attempt's missing, unrecorded, outstanding, settled, or unvouched handoff,
                        and require a published rotation to agree with the issue's current exemption. Its outstanding
                        transfer reading passes over settled history when deciding whether an attempt can be cleared
      transfer_permits.py
                        freeze the current publication entry and ask its transfer permit ahead of the workflow's
                        retry of a recovered replay or the leased no-op that receipts a landed one
                        (`workflow/engine/rewrite_retry.py`, `rewrite_landed.py`); both require the same permit
                        again inside the publication gate where it held. The retry measures past one refusal: a
                        replay its record names with no grant made before the crash, whose contribution the base
                        advance changed, enters the gate unrestricted as the publication would have
      conflicts.py      the counter, notice, event, and relabel a genuinely conflicted rebase is handed to its stage
                        with, dropping the handed head an earlier episode's counted round left claimed and the
                        publication record a body edit's resume left beside a report since settled
      guards.py         the no-op completion and the unreadable-HEAD, dirty-tree, and failed-push refusals the
                        workflow's publication ends an attempt with -- the last also for a candidate the git owner
                        refused for what moved since it was read
      snapshot.py       the branch fetch, the local / remote head reads and divergence counts, and the abort an
                        unreadable one takes
      recovery.py       the recovery context an interrupted attempt is resumed in: the refresh's inputs, the
                        anchor, and the attempt record read off the comment, for the workflow's recovery
                        coordinator (`workflow/engine/rewrite_recovery.py`) and the ineligible-label road in
                        `eligibility`
      recovery_push.py  the git half of the workflow's two recovery roads (`workflow/engine/rewrite_retry.py`,
                        `rewrite_landed.py`): the candidate an interrupted attempt left, read in its own terms --
                        the anchor as the lease, the recorded publication and stage (the tick's own for an attempt
                        from before that record) -- over the remote head the recovery's fetch verified, and the
                        reason a landing that left the verdict behind may not be finished. No workflow import
      landed_recovery.py
                        why a head the pull request already carries may not be finished, for the workflow's
                        recovery of it (`workflow/engine/rewrite_landed.py`) to park on: a foreign mark, a landing
                        nothing of the attempt's vouches for, a tree not provably clean under a verdict -- read off
                        the candidate's own status reading -- and a transfer the receipt and debt do not account
                        for, plus the two ways the leased no-op settling an outstanding permission fails to. Reasons
                        only: nothing here parks, pushes, announces, or routes, and no workflow import
      terminal_handoff.py
                        the end of an attempt whose PR merged or closed: the attempt and its debt dropped, a
                        shipped rewrite's permission settled with its receipt, any other dropped on the rollback's
                        rule, in one write
      replay_cleanup.py the clear-or-park decision for an ineligible label or a checkout back on the anchor. Records
                        that describe a replay, announcement, or unspent transfer prevent a silent clear
      replay_evidence.py
                        pure readings tying the checkout and recorded publication to this attempt, including the
                        grant-vouched window before a replay head was recorded and the finish's own relabel
      replay_refusals.py the ordered preflight before a replay retry: foreign publication, announcement,
                        rollback, unvouched transfer, and unclaimed checkout. Every refusal stays ahead of publication
      outcomes.py       ordinary recovery's unknown-comparison, diverged, dirty, and failed-push parks
      replay_transfer_parks.py
                        permit and transfer refusals: reset an unlicensed replay through the guarded rollback, or
                        retain a push that landed without the verdict's rotation for human reconciliation
      replay_checkout_parks.py
                        guarded rollback for unrecorded work, an out-of-band remote rollback, an announced publication
                        the remote lost, or an undone rebase whose abandoned bookkeeping must be retired
      replay_publication_parks.py
                        keep the checkout and pinned evidence when the issue's publication or label changed; a
                        stranded park is recorded once so repeated ticks do not advance the reply watermark, and
                        beside a live adjudication it asks for the record to be reconciled by hand rather than for
                        a label that adjudication's guard restores
      recovery_holds.py
                        what no recovery road reaches: the reset and park over a checkout whose base lag cannot
                        be counted, and the dispatch hold -- whether a standing anchor keeps a stage handler back,
                        which every label the refresh does not drive does, and one it drives does unless a late
                        claim the reconciliation answers freezes the refresh out -- with a missing checkout
                        restored where the refresh drives the label and the ineligible answer taken where it does
                        not. An anchor beside a live adjudication reaches it only once the dispatcher's handoff
                        (`workflow/engine/rewrite_takeover.py`) has refused the pair
      persistence.py    the parks and the reset-and-park tail -- which drops the whole attempt and the debt it
                        abandons, and the permission a transfer granted for the same commit, only once the reset
                        has actually landed, since a refused one may leave the branch still standing on the
                        approved commit. The finish of a landing -- its report debt, notice, event, announcement
                        mark, and route -- is the workflow's (`workflow/engine/rewrite_finish.py`)
      recovery_notices.py
                        how a recovery's park notices name the commits they are about
      models.py         the frozen contexts, requests, snapshots, and decisions
      state.py          the pinned-state keys, park reasons, refresh detour labels, and the shared logger
    publication/        what a branch becomes before review reads it
      commits.py        the commits the orchestrator creates on a branch itself -- the squash, and the documenting
                        stage's replacement of its docs commit with one whose subject names the pull request --
                        under one hardened envelope: detached global and system config, hooks, fsmonitor, and
                        signing off, and `AGENT_GIT_*` as the identity. The replacement is bound to the commit it
                        replaces rather than to HEAD: rebuilt from that commit's own tree, parents, and author with
                        `git commit-tree`, so only its message and committer differ and the index is never read,
                        then swapped onto HEAD by `git update-ref` against that commit, so a checkout something
                        committed on meanwhile refuses instead of having the newer commit rewritten. The
                        whole-message read it starts from is taken off the commit object under the hardened
                        command envelope -- a `git log` rendering is what a repository-local config could change --
                        with None for a read that did not happen rather than an empty message, and both that read
                        and the rebuild carry the bytes git stored, since text capture would turn a CR LF body into
                        an LF one on the way back in
      models.py         the record a squash hands back, in the three shapes it can end in -- published, refused, or
                        held by the size gate for the adjudication -- with a refusal NAMING which of four places
                        it left the branch: the approved commits at HEAD, off the tip and reachable only from the
                        head a record names, still in the branch's own history under work committed on top of a
                        recorded head it grew PAST, or none of them shown. The last is not a hedge but the honest
                        answer to a record this build cannot read whole, a recorded head no object here answers
                        to, or a checkout that would not report its own head -- and an operator sent by any of the
                        others would be looking for commits that are not where the notice says
      planning.py       the merge-base, HEAD, dirty, commit-count, and subject preconditions plus the squash
                        message they select, normalized by `pr_references` against the pull request the squash is
                        handed and the tracked issue it is being published for, where a pull request is named --
                        the count WALKED rather than taken from the
                        subjects beside it, since a commit written with no message contributes no subject and still
                        contributes one commit, and a count short by those decides both which rewrite the branch is
                        owed and what a human is told their history was collapsed from -- and the DECISION those
                        come to, which the count alone does not make: more than one commit is a collapse whatever
                        the subjects say, exactly one is a rewrite of its SUBJECT and only where that normalization
                        would write the line differently -- a subject missing the reference, and one still carrying
                        the tracked issue's beside one an earlier publication appended -- asked through
                        `pr_references`' own idempotent answer, so what counts as already published cannot drift
                        from what the rewrite would write -- and
                        anything else is a branch left alone, which the plan says by carrying no message at all.
                        And the pre-squash head pinned beside them -- the rollback target, the head the entry takes
                        its lease from, and the commit the gate is told this rewrite replaced, none of which a
                        reading taken past the reset could recover
      pr_references.py  which ` (#N)` references a published commit subject is left ending in, decided once for
                        every publisher. The trailing RUN of references is what it reads: the tracked ISSUE's
                        reference, where the caller names one, is dropped from anywhere in that run -- alone, or
                        ahead of a pull-request reference an earlier publication appended, which is the
                        `subject (#issue) (#pr)` a developer commit and the orchestrator each wrote half of --
                        every other number stays where it stands, since that is somebody else's link, and the line
                        ends in exactly one reference to this pull request, so a second approval round, a retried
                        tick, or a recovered commit never doubles it. A number inside the subject's own text, or
                        one written without the space the orchestrator puts before its own, is text rather than a
                        reference. Only the subject line comes back, never a body, trailer, or closing keyword,
                        and reapplying the normalization changes nothing. The tracked-issue removal is exposed on
                        its own as well, for the title selection `titles` owns: it strips that number and appends
                        nothing, since a PR title is picked before the request has a number. Whether a subject is
                        still OWED a rewrite answers here too, and it is the same rule read backwards -- the
                        normalization is asked whether it would change the line, so a publisher deciding WHETHER
                        to rewrite cannot disagree with what the rewrite would write and then double a reference,
                        leave a missing one alone, or call a subject carrying both numbers finished. No pull
                        request at all owes nothing, and nothing is stripped on the way to a rewrite that is never
                        made. Pure functions reading no git, GitHub, or configuration
      probes.py         the two branch-geometry reads, and nothing about what a commit SAYS -- `titles` beside it owns
                        that. One is the divergence reading -- the fetched ref resolved ONCE and the local end counted
                        against that immutable commit, since the counts are a claim about the tip and a ref something
                        moves between two readings would leave a branch proved against one head and its push pinned to
                        another. That local end is the checkout's symbolic `HEAD` unless the caller names a commit,
                        which a caller whose next step is a PUBLICATION does: `HEAD` is re-resolved by every command
                        that reads it, so counting against it and naming a commit afterwards can describe two. A reading that did not happen says so (`readable`) rather than answering `(0, 0)`,
                        which is what an in-sync branch answers and what every caller acting on it would rebase, spawn
                        over, and force-push on. The other is the FORK POINT one revision left the base at, which is
                        the commit a three-dot contribution resolves to and therefore the base a fingerprint is taken
                        over: a rebase reads it at both ends, since the pre-replay one is off the branch the moment
                        the replay lands. An unfetched base, a revision this host does not hold, and two histories
                        with no ancestor between them each answer "" -- evidence the caller cannot produce, never a
                        base to fingerprint over
      rewrite.py        the soft reset, the orchestrator-identity commit, the gated publication of the commit it
                        just made -- measured, then named against it and pinned to the head the entry froze, with
                        the plan's pre-squash head and merge base handed over beside it, since a rewrite of the
                          exact commit an authorized settlement accepted may carry that exemption over and both ends
  of both
                        contributions are what says so -- and
                        the rollback a post-reset failure takes -- the ref and the index, never the working tree,
                        since a squash has the same tree as the head it replaces and the only thing taking the
                        worktree too would restore is an edit somebody made while the rewrite ran -- which drops the
                        approval it abandons, and the permission a granted transfer will never spend, only once the
                        reset has actually landed -- a reset that failed may
                        leave the branch still standing on the approved commit, and the approval is the only record
                        naming the one commit this issue may publish. A push that did not go out is rolled back
                        with ONE exception, and it is the resumed collapse the pull request already carries: that
                        push sends nothing, so a request that fails there is a transport failure over work the
                        remote has, and a reset would take the checkout off it, the count the handoff still owes
                        a notice with it, and leave the next tick a remote that moved for reasons nothing on the
                        comment explains. Two readings say so and the ENTRY is the stronger, since it is a
                        reading of the pull request taken this tick -- a tip it froze equal to the commit about
                        to be pushed, which it admits only where a durable record accounts for it, so it covers
                        the crash between a push and its receipt where the receipt is exactly what is missing;
                        the receipt dated to this attempt is asked beside it for the road that read no remote at
                        all. Neither can fire on a fresh squash, whose entry was frozen before the commit
                        existed. The approval the gate wrote before the push, and the permission a transfer
                          held, are records a reset is SUPPOSED to drop, so neither is asked there. A HELD candidate
  is spared that rollback only
                        where the squash is somebody's: a
                        live record naming it -- oversized, or a pair still owed its count -- already on the remote,
                        named by the approval as a push this issue still owes -- a reset there leaves the
                        reconciliation ahead of every later handler asking for a commit only the reflog has, and it
                        is where a transfer whose grant landed and whose push the remote took ends up, its receipt
                        still naming the head the squash replaced -- or under a commit something else made. A hold
                        the gate REFUSED is none of those, and froze
                        nothing to say otherwise -- a pull request closed or moved in the window the reset and the
                        commit sit in -- and the branch goes back there, since a squash nobody measured, published,
                        or recorded is the one commit a retry finds, and one commit is the nothing-to-squash road
                        reporting success
      resume.py         the squash an earlier tick did not finish, told apart from a branch with nothing to
                        squash by the record that squash wrote before it ran. Nothing is decided by comparing
                        that record to the branch until the record has proved itself, the road that DROPS it
                        included: a head edited onto the commit a finished collapse left reads as a rewrite that
                        never happened, so a shortcut for one would drop the record and hand on a branch of ONE
                        commit -- the nothing-to-squash road reporting success over a remote still carrying the
                        history the record names. Proved first, exactly ONE branch drops it and lets the ordinary
                        squash run: the one the record still describes exactly, standing on the head it names
                        over the commits it counted, which is safe to hand on because that road cannot report
                        success without pushing the very commits an approval was given for. A branch carrying
                        NOTHING over its base refuses, since that is the shape the nothing-to-squash road would
                        call success over a remote still holding the history the record names -- and so does one
                        that MOVED off the recorded head, whichever way it went: this recovery owns the tick from
                        the moment a record goes down, ahead of every route that could resume a developer, so
                        work committed over the collapse is work nobody here made and squashing afresh would
                        force-push it onto the pull request as history a reviewer approved. The two are still
                        told apart in the notice, since a recorded head still REACHABLE has the approved commits
                          under the stray work and one the branch REPLACED has them only in the reflog. A collapse
  that landed locally, one the
                        gate authorized, one the remote already carries, and one whose handoff never finished are
                        all finished through the same leased publication -- entered on the head the record names,
                        or on the rewritten commit itself where a receipt dates that tip to this attempt, so an
                        already-landed collapse is a leased no-op rather than a fresh reading. Nothing is resumed
                        on the record's SHAPE, and none of the roads above is either: the tree is proved clean,
                        both recorded ends are peeled as objects
                        this host really holds, the base has to be one the head was really built on -- a walk
                        between two histories that never met reports a number like any other, so the count is no
                        ancestry proof -- the history between them is walked against the recorded count, and the
                        commit on the branch has to carry both the TREE the recorded head left and that base as
                        its ONE parent, which is what a squash produces by construction: the same tree re-parented
                        onto a base that has since advanced is a commit that REVERTS whatever that base added, and
                        a tree comparison alone would publish it. A record failing any of those leaves the branch
                        untouched and refuses, since a reset would be a guess taken with a destructive step; and
                        one this build cannot read WHOLE refuses rather than being waved past, since the branch
                        behind it is exactly the one commit that reads as nothing to squash
      squash.py         the plan-then-resume-then-enter-then-record-then-rewrite entry point a stage handler
                        calls, over the gate subject that handler builds and the pull request number it hands in --
                        which the plan's message is normalized against, together with the tracked issue that gate
                        carries, only while `PR_REF_IN_SUBJECT` is on, and which on a one-commit branch is what
                        decides whether there is a rewrite at all, for `count=1` and no
                        `:package:` notice -- and the owner
                        of `SQUASH_ON_APPROVAL`:
                        the switch decides whether a NEW rewrite is made, and one an earlier tick already made
                        is finished either way, since the commits are off the branch and the remote either has
                        the object that replaced them or does not. An issue with nothing recorded costs an
                        install with the switch off no probe, no reading, and no write -- but one that CLAIMED a
                        collapse still owes the entry the rewrite would have taken, since the recovery may drop
                        that record on the way past and with the switch off there is no rewrite behind the drop
                        to read the pull request: a tick that engaged the recovery, found the reset never ran,
                        threw the only evidence away, and reported success would hand `documenting` a branch
                        whose remote had moved out from under it. That reading is taken whatever `DECOMPOSE` says,
                        which is the one place the size gate's switch does not reach: everywhere else a push
                        follows and the lease answers a moved remote, and here nothing does. The checkout is then
                        proved AGAIN once the reading comes back, because the read is a REQUEST and the worktree
                        is writable for the whole of it -- a commit landing there is work no reviewer saw, and
                        this road reports the head it planned over. The resume is asked
                        before what is on the branch is read as a verdict, since a rewritten branch and a branch
                        with nothing left to rewrite carry the same one commit under the same kind of subject;
                        the record goes down between the entry and
                        the reset, so no write is spent on a publication the entry refuses and none is owed once
                        the evidence is gone -- and a write GitHub refuses stops the squash rather than leaving a
                        rewrite nothing could account for. Every failure is stamped on the way out with WHERE
                        it left the branch, which `standing` beside it reads
      standing.py       which of the four places a refused squash left the branch in, read off the pinned
                        record AND the checkout rather than assumed. The terms go down before the reset, so an
                        outstanding record whose head is the head the checkout stands on is a rewrite that did
                        not happen and the approved commits are exactly where a human will look for them. A
                        recorded head the branch moved OFF is two answers rather than one, and the ancestry
                        separates them: still reachable from HEAD it is buried, so the notice sends an operator
                        into the branch's own history under the stray work rather than past it to the reflog,
                        and one the branch REPLACED is the collapse a reflog entry resolves. A record this
                        build cannot read whole, a recorded head no object here answers to, and a checkout that
                        would not report its own head are none of them shown. The same owner answers whether a
                        collapse is CLAIMED at all -- the reading the stamp is gated on, and the one an install
                        with the switch off decides its entry from. Nothing here resets, writes, or pushes, so
                        the classification costs a publication that succeeded nothing
      titles.py         everything a published subject line turns on: the Conventional type list and the
                        compiled prefix patterns, the two predicates read against them, the first-commit and
                        recent-base subject reads those predicates are applied to, and the prefix inference and
                        PR-title selection above them -- one owner, so a type added to the list cannot drift from
                        the regex that recognizes it or from the title a caller picks with it. That selection
                        appends no reference, since a title is picked before the pull request has a number, but it
                        does ask `pr_references` to DROP the tracked issue's reference from every line it reuses.
                        A subject written under the commit-subject contract carries none and comes back untouched;
                        the removal covers the lines that contract does not reach -- a commit made before it, one
                        a human wrote by hand, an issue title with the number typed onto the end -- so the one
                        owner that decides references decides this too and a title cannot disagree with the commit
                        published under it; any other number is somebody else's link and survives. The subject
                        reads honor the spec's own remote and base branch, so a deployment with mixed default
                        branches samples the right history
    measurement/        how large a committed candidate is, which contribution it is, and why either is
                        sometimes unknown
      models.py         the two typed failure vocabularies -- one per reading, spelled apart so a park reason
                        says which one stopped -- the four records a reading hands around: one frozen end of
                        a diff, the measurement over both ends, the fingerprint over the same pair -- each of
                        those three carrying the failing step's own scrubbed line beside the typed reason it
                        stands next to -- and the readback saying whether an end this host was supposed to hold
                        is really here, plus the version the digest scheme is at, which every caller that
                        PERSISTS a fingerprint records beside it because two ids taken under different rules are
                        not comparable and nothing about the ids says so
      commits.py        the remote-authoritative base freeze (fetched once when the object is missing) and the
                        candidate proof that an id resolves, is held here, and peels to the commit it names --
                        each handing back whatever id it did establish beside the failure, so a retry has one
                        exact object to ask for, and the freeze naming what the read or the fetch reported for
                        itself
      additions.py      the `--numstat` added-line count over the frozen pair — read under the candidate's own
                        attributes and a named algorithm, pinned where git consults the environment last, and
                        refusing outright on the attribute file and diff-driver config no pin reaches — and the
                        measurement composing the three steps
      fingerprint.py    the SHA-256 digest of the whole prospective contribution over the same three-dot range, taken
                        behind a label carrying the scheme version the record owner publishes, over git's `--raw -z`
                        listing (modes, unabbreviated object ids, status, and path bytes) and
                        then over the content of every object that listing names, so nothing that decides how content
                        would be RENDERED decides the id and no id has to be taken on trust — git serves a substituted
                        loose object under the name its file sits at, and only `fsck` ever says otherwise. Renames are
                        left undetected for a representation that does not move with a similarity threshold, the record
                        order is pinned against `diff.orderFile`, the shallow file and lazy fetching are pinned in the
                        environment so a planted history boundary cannot move the range and no step of a reading over a
                        partial clone reaches its promisor remote — the ends included, since a commit made after such a
                        clone is exactly what a lazy fetch would supply and what an absent end means — both commits are
                        proven present before the listing is asked for, the listing is refused unless every field it
                        has is terminated, and the objects are read in one `--batch` whose protocol is checked as it
                        arrives — every id asked for, in order, a blob of the length its header claims — since a store
                        that lost one answers `missing` on the very stdout the digest is taken over and exits 0, so a
                        check standing in front of the read would only widen the window it left. A typed failure and no
                        digest for any of those, since a failed listing writes the empty stdout an unchanged candidate
                        writes; a gitlink is exempt from the object read, its commit being the submodule repository's
                        to hold
    snapshots/          the immutable remote copy a superseded candidate is preserved as
      namespace.py      the one `refs/orchestrator/late-split/...` namespace a snapshot may occupy, built from a
                        generation's own identity and refused for anything else, plus the
                        `refs/orchestrator/late-split-local/<repository>/...` name this host's copy of one lands
                        under -- qualified because several configured repositories may share a clone, and bounded
                        because configuration bounds a slug at nothing
      refs.py           create-or-verify against the exact commit with no overwrite, the fetch-and-resolve that
                        proves a child could obtain it (one locked step, onto this repository's own local name),
                        the read-only ask a caller spends when it must know whether a ref is still there without
                        being allowed to take it, named against the commit it was promised like every other read
                        here, and the absent-is-success delete -- leased at the preserved
                        commit, so a re-pointed ref is refused rather than reclaimed, and taking this host's copy
                        down BEFORE the remote one, since a mirror is what a child reads as "nothing has been
                        reclaimed": one that will not go -- or that a failed read cannot tell from one already
                        gone -- refuses the whole reclamation rather than outliving the ref it mirrors
      mirrors.py        the repository-qualified local name, its hardened presence and commit probes, and the
                        verified mirror removal that remote reclamation requires. A child reads identity here:
                        the store is one the agents write, so the copy must resolve to the promised commit
    verification/       what a verify run is, and the reads a checkout is judged by
      models.py         the `VerifyResult` evidence record (tested commit and tree, the ordered configured commands,
                        the transcript of `VerifyCommandOutcome`s for the commands attempted, timeout, and context
                        revision), when that record is reusable passing evidence, the context revision digest
                        minted from the commands and timeout, the statuses, and the output budget
      output.py         the redact-then-truncate pass over captured verify output, cut to the budget in UTF-8 bytes
                        and never inside a character
      probes.py         HEAD, branch, and tree identity, committed-path and regular-file reads, object presence
                        and ancestry. Object presence accepts caller-owned environment pins so a partial clone
                        can distinguish objects already in its store from those a promisor remote could supply,
                        and is peeled unless asked not to be: unpeeled, only an id that is itself a commit
                        answers yes, never an annotated tag pointing at one
      status.py         the porcelain status in both its answers (the paths, whether git could be
                        asked, and the `is_clean` a caller whose next step is a push asks instead of truth-testing
                        the list) -- taken without optional locks, so asking what a tree holds does not refresh
                        and rewrite its index -- the ignored-path read beside it, which is what git leaves out of
                        every one of those and out of its own refusal to remove a dirty worktree, so a caller
                        about to DELETE a tree can be told about the `.env` a caller about to publish rightly
                        passes over. Suppressed index entries make the status unproven even when porcelain
                        reports no paths; NUL-delimited parsing preserves rename sources and unusual filenames
      process.py        one command's group spawn / kill / drain and its `VerifyCommandOutcome` verdict
      runner.py         the commit and tree a run verifies, read before any command and refused when unreadable or
                        when the worktree is not proven clean; the stripped child environment, the fail-fast
                        command sequencing, and the result that records the run -- for the validating approval
                        gate, and for the base-rewrite evidence policy (`workflow/engine/rewrite_evidence.py`)
    worktrees/          the per-issue checkouts an agent runs in, the read-only inventory of which issues they
                        and the branches beside them name, the classification of which of those may be
                        reclaimed, and the bounded pass that spends one of those classifications
      naming.py         slug sanitization, git-ref-safe branch segments, and pinned or legacy branch resolution:
                        the exact set of names one issue's branch can be published under
      paths.py          the two paths an issue can have been checked out at -- the per-repository one and the flat
                        one that predates the slug in the path -- and the
                        `issue-<n>` read that runs back the other way -- canonical spellings only, so a padded or
                        signed number is no issue at all
      creation.py       issue and PR worktree creation, stale-worktree reuse and the unpushed-commit probe it turns on
      anchoring.py      the shared restore fetch and the guarded move that re-anchors a reused checkout onto a PR
                        head or its merged base, with the target-root lock held across refresh and movement
      cleanup.py        lock-held worktree removal and local branch deletion, each behind its best-effort boundary,
                        plus the fail-closed read a caller that has to RECORD the teardown asks afterwards
      recovery.py       candidate-branch discovery, the unpushed-commit probe, and the tip read a recorded SHA is
                        compared against
      decomposition.py  the decomposer scratch path, its detached creation, and its best-effort removal
      terminal.py       question-stage teardown and terminal local and remote branch cleanup
      candidates.py     local issue artifacts, the inventory's refused and withheld claims, candidate layout,
                        and the combined maintenance scan. These records describe what discovery established
      models.py         the three answers a fail-closed probe can give, branch and proven commit identities,
                        retention reasons and subjects, and the eligibility verdict over a discovered candidate
      maintenance_results.py
                        the pass's closed outcome and reason vocabularies and the result constructor carrying
                        them beside its candidate, artifact subject, and retained eligibility evidence
      branch_probes.py  the branch read a scan is built from: the `refs/heads/orchestrator/` listing in one clone,
                        named as the derivations spell it rather than as git's shortest unambiguous form, and
                        answering "could not read" -- a listing that warned about a ref it skipped included, since
                        what came back is then short by exactly that branch -- apart from "nothing here"
      probes.py         the checkout reads a scan is built from: the directories under both roots -- the spec's own
                        and, once for the whole host, the flat `WORKTREES_DIR` every entry shared before
                        namespacing -- a real directory under the exact name, never a symlink into a tree the
                        creators never wrote, read through the `lstat` that reports what the `is_dir` predicates
                        suppress -- each answering "could not read", listing and entry alike, apart from "nothing
                        here"; and the one read that is not a listing, which git directory a checkout and a clone
                        share, since a flat checkout's name says nothing about whose it is and a named one's claim
                        has to be tested. Both halves of the domain ask that one, so it is defined once and here
      attribution.py    which configured repository a local branch belongs to, by re-deriving each spec's own
                        name for it; a name several entries could own -- every legacy flat branch on a shared
                        clone, every namespaced one two lossily-sanitized slugs are handed -- is attributed to
                        none of them, since a branch charged to the wrong repository is one a caller acts on
                        against the wrong GitHub issue
      checkout_attribution.py
                        the same question for a checkout directory, which carries even less of a name. The flat
                        pre-namespacing one no name can settle, since every entry derived it identically, is
                        attributed by the clone the directory turns out to be a worktree of -- which answers every
                        host whose entries keep their own clones and leaves the shared-clone case ambiguous. An
                        entry whose OWN clone would not answer claims it too, since nothing ruled that entry out
                        and dropping it is how a shared checkout reads as uniquely owned; a flat path that is some
                        entry's worktrees root is not a checkout at all. The per-repository parent is the
                        configuration's own ambiguity beside it: two entries the path sanitizer cannot tell apart
                        are handed one directory, and both are refused outright. Every unsettled shape names its
                        claimants rather than nobody, because a tree none of them may take is standing on one of
                        that issue's branches: the scan has to withhold the issue, not just the directory
      inventory_roots.py
                        group configured repositories by their resolved clone, retaining unresolved claimants
                        so an unreadable root cannot make another repository appear to own a shared branch
      legacy_inventory.py
                        attribute the host's flat checkout listing by clone identity and record both owned and
                        ambiguous issue claims; identity reads are spent only where the listing found checkouts
      inventory.py      combine those claims with per-repository checkout listings and one branch listing per
                        clone. Deduplicate each issue's artifacts, withhold ambiguous issues on every claimant,
                        and refuse unreadable or colliding roots rather than report an empty inventory
      evidence_reads.py
                        hardened local reads, with clone reads serialized under the target-root lock so they
                        cannot land between a worktree mutation and the ref it creates; spawn failures stay unread
      tip_evidence.py   local branch tips, checkout HEAD commits, authenticated remote tips, and containment in
                        the base the remote names. Every read distinguishes absence from an unreadable answer.
                        Tracking refs cannot prove publication because a per-issue checkout can rewrite them;
                        the remote answer therefore comes over authenticated transport without fetching
      evidence.py       checkout ownership, symbolic HEAD identity, status, and ignored-file evidence. Identity
                        compares the clone and the issue's branch names before content can justify removing it.
                        Loose and ignored files are separate reads because git refuses removal for only the first;
                        either kind keeps the tree, as does a status or identity read that could not be taken
      activity_evidence.py
                        when the checkout directory, its index, and its HEAD reflog were last touched. The index
                        and reflog see edits and commits that leave the directory timestamp alone. Quiet requires
                        every timestamp to be readable and none to be newer than the caller's cutoff
      checkout_listing.py
                        which branches any worktree of this clone has checked out, with the porcelain listing
                        counted against the clone's registered worktree entries. Git can silently omit an entry
                        whose backlink is missing, so an incomplete count refuses deletion rather than treating
                        the branches it could not list as unused
      claims.py         the GitHub side of the same question, asked about the issue: the issue fetch, the
                        authenticated pinned read and the two checks that its payload is a state at all, the
                        exactly-one-terminal-label rule an ending has to pass, and the open pull requests still
                        standing on a branch or on the recorded number. The branch claims are asked of both
                        layouts this orchestrator publishes an issue under whether or not the host still holds
                        them, and they name no base, since a thread retargeted onto another base stands on the
                        branch just as squarely. Every read is behind its own boundary, the lazy fields
                        included, and every boundary answers with a retention rather than a default
      commit_claims.py  the same side asked about one commit: whether a terminal pull request exactly accounts
                        for a branch tip the base does not carry. The lookup is by object id rather than by
                        branch name, so a pull request that used this branch for some earlier round does not
                        account for what is on it now, and it names no base either -- what makes the commit
                        safe to delete is that GitHub holds it, wherever the thread carrying it is pointed.
                        Only a pull request that has ended reclaims: a lookup that could not be taken is
                        retained on rather than read as an absence, and one still open is retained on too,
                        since a disagreement between two readings of the same remote is not one to settle in
                        favour of deleting
      retention_tips.py
                        branch-tip retention proofs: ask the remote before base ancestry can clear a commit,
                        since a merged local tip can still sit under a branch the remote has been pushed past.
                        A branch absent locally is proven through its remote copy; a commit outside the base
                        survives only when an ended pull request accounts for that exact tip
      retention_checkouts.py
                        ownership and cleanliness gates for each checkout, followed by the proof for its own
                        HEAD. A deleted branch can leave the checkout holding the only copy through its reflog;
                        it is excused only when a reported branch stands on the same commit and proves it too
      eligibility.py    the side-effect-free classifier: issue state and open pull-request claims first, then
                        checkout and branch retention proofs with one base reading for the whole candidate.
                        Returns every retention reason or the exact commit each artifact was cleared at, so
                        two checkout layouts with different HEADs are each proven before either may be removed
      remote_inventory.py
                        list the orchestrator branch namespace once per reachable repository and attribute it
                        against every spec sharing the clone. An unreachable remote refuses its whole repository
      candidate_layout.py
                        classify the complete artifact names as current, legacy, mixed, or remote-only; both
                        checkout paths and branch names contribute to that classification
      discovery.py      merge local and remote evidence into one ordered candidate per issue. A withheld local
                        claim stays withheld on both halves, so a remote branch cannot revive a refused candidate
      reclaim.py        the three commit-pinned teardown steps, each behind a total boundary and each refused
                        by git or by the remote rather than
                        by the reading in front of it: the removal that does not force, so a tree written in
                        since the proof stands; the remote delete leased to the proved commit, so a branch
                        pushed past it is turned down there; and the local `update-ref -d` naming that commit and
                        refusing to dereference, so a branch an agent committed onto survives and a symbolic ref
                        planted under a branch name is deleted as itself rather than followed onto the base. A
                        checkout already gone is the removal's own success; the two branch steps leave that to
                        the caller, which reads what each host carries before it decides there is a deletion to
                        attempt at all -- so the pinned local delete reports a ref that is not there as the
                        refusal git gave it rather than papering over it
      maintenance_guards.py
                        injected activity and continuation guards, and the quiet period every checkout must
                        satisfy. Unreadable guards refuse action. Continuation is asked before each candidate
                        and again immediately before its first mutation, after the costly eligibility reads
      checkout_removal.py
                        remove each checkout only after re-reading the exact HEAD the classification cleared.
                        A moved or unreadable tip, missing proof, or failed removal stops the candidate
      branch_removal.py
                        require a complete checkout listing and refuse any branch still checked out. Delete on
                        the remote before the clone, re-reading each tip against its proof immediately before
                        the mutation. A failed remote delete leaves the local branch discoverable for another pass
      maintenance.py    the bounded pass: active claim, classification, quiet period, final continuation guard,
                        then all checkouts before any branch. Records one result per candidate through
                        `maintenance_results`; a candidate not reached has no result. No retry queue, issue label,
                        pinned state, comment, or session is changed, so an interrupted pass can be rediscovered
  skills/
    catalog.py          the per-tick `git ls-tree` of a repo's `SKILL.md` definitions, the `project` level it
                        classifies every one of them at, and the one `repo_skill_catalog` record it appends
    discovery.py        the per-run scan of what a codex run was loaded with and the `project` / `user` /
                        `harness` level that defined each name, plus the skill roots, marker, and level
                        vocabulary `catalog.py` reads back
```

## Inside `git/`

The six subpackages bind their collaborators directly, so the dependency direction reads off the owner rather than
off a facade:

- `publication/` — `pr_references` calls nothing; `commits` and `probes` each call `commands` and none calls
  another; `titles` calls `commands` and `pr_references`, for the tracked-issue strip its selection borrows;
  `planning` calls `commands`, `titles`, `pr_references`, and the verification probes; `rewrite` calls
  `commands`, `commits`, `branch_transport`, and those same verification probes; `resume` calls `rewrite` and reaches
  the gate through the one hop that owner spells; `standing` calls `resume` for the ancestry read and reaches the gate
  through that same hop; `squash` calls `planning`, `resume`, `rewrite`, and `standing`.
- `verification/` — `output` calls `models`, `process` calls `output`, `probes`, and `status`, and `runner` calls
  `process`, `probes`, `status`, and `models`: the baseline commit, tree, and clean status before the first command,
  and the context revision the result records.
  `status` shares the NUL framing and submodule arguments defined on `probes` so both path reads agree.
  Both subprocess owners reach the agent package for what a spawned child costs rather than keeping a second copy:
  `process` takes the bounded drain from `agents/process_groups.py`, and `runner` takes that same drain, the
  registry the shutdown sweep reads from `agents/processes.py`, and the stripped child environment a verify shell
  is spawned under from `agents/environment.py`.
- `measurement/` — `models` carries only data. `commits` calls `commands`, `branch_transport`, and the verification
  probes for the two object reads, and `commands` once more for the one line it keeps off a fetch that brought
  nothing back; `additions` calls `commands` and `commits`; `fingerprint` calls `commands`, `streaming` for the
  object content it hashes without holding, and those same probes and nothing else in the package, since it is handed
  two ends already proven rather than establishing them. Nothing here reaches the workflow layer, so the ceiling a
  count is compared against, the verdict that comparison earns, and what two equal digests license all stay with the
  caller.
- `snapshots/` — `namespace` is string policy and reaches nothing, which is what lets the late domain's lineage
  record consult it on every pinned read without paying for the transport; `refs` calls `ref_transport` for the
  remote read and the lease-pinned write and delete, `branch_transport` for the fetch, and `mirrors` for the
  hardened local resolution that proves what the fetch brought. `mirrors` reaches `commands`, `locks`, and
  `worktrees.paths` for the local copy and its repository-qualified name. The workflow decides WHEN a snapshot is
  taken and what its absence costs; this package decides only what a snapshot ref IS and refuses everything outside it.
- `worktrees/` — the creators call `commands`, `locks`, `branch_transport`, and their `paths`, `naming`, `anchoring`,
  and `recovery` siblings. `anchoring` reads branch transport and moves the checkout under the target-root lock;
  `decomposition` resolves its own path helper; `terminal` composes its local teardown from `cleanup`. The read-only
  scan sits on the same owners: `inventory` combines `inventory_roots` and `legacy_inventory` with `branch_probes`,
  `probes`, `attribution`, `checkout_attribution`, and `paths`. `legacy_inventory` uses checkout attribution and
  identity reads; `inventory_roots` resolves and groups clone roots. `probes`, `attribution`, and
  `checkout_attribution` reach `paths` and `naming` for the names they compare against. Only the two probe owners
  reach `commands` — `branch_probes` the `locks` its listing is taken under as well.
  `candidates` and `models` carry only data; `maintenance_results` constructs the bounded record for an outcome.
  Nothing in the scan writes, fetches, or names GitHub. Classification keeps that split visible:
  `evidence_reads` owns hardened and locked git reads; `tip_evidence` adds authenticated remote answers;
  `evidence` checks checkout identity and the verification status/ignored-path readings; `activity_evidence`
  reads timestamps, and `checkout_listing` proves its list is complete. `claims` asks GitHub about the issue,
  and `commit_claims` about one exact commit. The two retention owners compose those proofs, and `eligibility`
  returns the candidate verdict. None of these owners writes on the host or on GitHub.
  `discovery` combines `inventory`, `remote_inventory`, and `candidate_layout`. `remote_inventory` uses
  `ref_discovery` for namespace listings and `attribution` for claims against the clone groups.
  Mutations live on `reclaim`, which calls `commands`, `locks`, and `ref_transport`. `checkout_removal` and
  `branch_removal` spend the verdict's tips immediately before those mutations; `maintenance` orders their work
  after eligibility and the injected guards on `maintenance_guards`. The workflow layer is never imported here.
  `runtime/artifacts.py` schedules the pass, takes the scheduler hold, and injects those guards; through
  `runtime/exclusion.py`, it claims the host against processes no scheduler hold can see.
- `base_sync/` — `models` and `state` carry only data. On the sync side the workflow's refresh calls
  `refresh_selection` before `pre_pr` and its base-rewrite coordinator, `refresh_selection` asks `frozen` alone, the
  coordinator asks `eligibility` and `startup` in that order and hands a clean rebase to the workflow's publication,
  which reads its candidate through `rewrite_facts`, pushes it through `rewrite_transport`, records its replay through
  `attempts`, and ends an attempt it refuses through `guards`, which ends in `persistence`.
  On the recovery side the workflow's recovery coordinator resumes the attempt in the context `recovery` binds, and
  asks `replay_cleanup` before comparison, `snapshot` and `transfers` for the comparison, and `replay_refusals` and
  `replay_evidence` before its retry. Those refusal owners separate checkout rollback, publication identity, and
  transfer accounting. The workflow's retry reads its candidate through `recovery_push`, asks `transfer_evidence`
  and `transfer_permits` before the gate -- the latter freezes the entry for the permit it re-asks -- and takes its
  parks from `outcomes` and `replay_transfer_parks`. Its recovery of a head already published reads the same
  candidate, asks `replay_evidence` and `landed_recovery` why the landing may not be finished and parks through
  `replay_publication_parks` and `replay_transfer_parks`, asks `transfer_permits` ahead of the leased no-op an
  outstanding permission is settled through, and observes anything else through `rewrite_transport`. `attempts` is
  under both: it owns the record one rebase attempt leaves of itself, and every owner
  that writes a member of that record or ends it calls through it rather than spelling a key of its own.
  `attempt_records` owns interrupted-replay validation, and `recovery_notices` names the commits a recovery's parks
  are about. Every finish of a landing -- the report debt, the notice and audit event, the announcement mark, and the
  route -- is the workflow's (`workflow/engine/rewrite_finish.py`). `transfer_evidence` assembles
  the rewrite the publisher or recovery hands to the size gate. `transfers` classifies the interrupted permission
  through `transfer_attempts` and `transfer_publication`, using the bounded handoff values in `transfer_values`.
  `recovery_holds` reads the refusals the dispatch hold releases for off `refresh_selection` and `frozen`, and
  answers a held anchor through `replay_cleanup` and `replay_publication_parks`. `rewrite_handoffs` carries only data
  as well; `rewrite_facts` reads it through the verification, measurement, and publication probes and the branch
  transport, and `rewrite_transport` publishes or observes it through `rewrite_facts` and the branch transport. Only
  `recovery_push` calls one of the three, to read a recovery's candidate: the workflow's publication, retry, and
  recovery of a landed push read, publish, and observe through them. The keyword-call adapter here
  — the conflict route — like the PR sync on the workflow's coordinator, still takes the argument list its caller
  spells and normalizes it into the typed context entry point beside it.
