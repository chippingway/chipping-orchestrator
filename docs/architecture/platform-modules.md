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
- **Over every scope, declared per module.** A base sync runs in the git layer but reports to the
  issue it was started for: `base_sync/conflicts.py`, `base_sync/recovery_notices.py`, and `base_sync/publication.py`
  reach `workflow/engine/comments.py`; `persistence` reaches `workflow/engine/guards.py` and
  `workflow/stages/implementing/late_approval_reading.py` and `late_approval_state.py`, to read and drop the debt
  the size gate recorded when a refused push sends the branch back to where it started;
  `base_sync/attempt_records.py` reaches `workflow/late_split/formats.py`, for the
  shape a recorded commit is held to, which spelled twice would let a pinned comment accept what every other reader
  refuses; the base-sync transfer owners read the higher-layer records only inside their calls:
  `transfers.py` reads `workflow/late_split/exemption_reading.py`, `rewrite_reading.py`, and `rewrite_values.py`;
  `transfer_values.py` reads the phase value, `transfer_evidence.py` reads the exemption and rewrite value,
  `transfer_attempts.py` reads the exemption, and `transfer_publication.py` reads
  `workflow/stages/implementing/late_approval_reading.py` and `late_publication_state.py` for the debt and
  receipt and rejects debts belonging to another attempt. `transfer_permits.py` loads the publication permit and
  frozen entry through `late_overflow.py`, `late_records.py`, `late_transfer.py`, and `late_gate_models.py`.
  Base-sync `publication` also reads
  `workflow/stages/implementing/late_push.py` and `late_records.py` — the gated push the rebase it is about to
  force-push goes through, since a base that moved changes what the branch adds to it and a pull request may not be
    grown past the ceiling by a refresh either. Both base-sync `publication` and `recovery_push` load the frozen
  `_Entered`
  value from `late_gate_models.py` inside that call. `publication/rewrite.py` reaches `late_rewrite.py` to enter
  a squash on its existing publication and publish through the size gate. Its reset and push steps also load
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
  `codex.run_codex` / `claude.run_claude`; and only the two
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
  `orchestrator.base_sync` (`git/base_sync/state.py`), `orchestrator.worktree_lifecycle` (the
  `git/worktrees/` owners that log, plus `runtime/artifacts.py`, `runtime/artifact_schedule.py`, and
  `runtime/artifact_records.py` above them — when a maintenance pass ran, why it did not (including a window that
  closed before its pass could start), and the record one candidate's answer could not be written as are facts about
  the same artifacts the owners under it report on, so an operator filtering for what
  happened to a finished issue's checkout is told about the day the host was too busy to attempt one), and
  `orchestrator.branch_publication` (`git/publication/rewrite.py`). A
  module moved between packages does not take its channel with it, and each of the four names is asserted where
  its owner is tested —
  `tests/git/test_branch_transport.py`, `tests/git/test_credentials.py`, `tests/git/test_ref_discovery.py`,
  and `tests/git/test_ref_transport.py`,
  `tests/git/base_sync/test_state.py`, `tests/git/worktrees/test_imports.py`,
  `tests/runtime/test_artifacts.py`, `tests/runtime/test_artifact_records.py`, and
  `tests/git/publication/test_imports.py`.
- **Import cost.** `import orchestrator` costs the root module and no owner behind it, and importing a `runtime/`
  owner plants neither the CLI nor an app — `tests/runtime/test_imports.py` and `tests/apps/test_imports.py`.
- **Direction inside `skills/`.** Neither owner may reach the workflow engine, a stage, or an application entry
  point: a catalog is observation the tick drives, not state a handler consults — `tests/skills/test_imports.py`.
- **Secrets.** `GITHUB_TOKEN` is read from the process environment or a token file outside `REPO_ROOT`, never from
  the `.env` an agent with sandbox bypass could read out of a sibling worktree: `config/_dotenv.py` skips every
  secret key it finds there and warns instead of loading it — see
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
    startup.py          which launch mode a run is and how loud, one client per configured repo -- in the
                        bootstrapping form a tick needs and the read-only form a run that will not tick may have,
                        which is the one write a connect makes -- and the scheduler every tick shares
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
                        does not work is nobody's and waiting on one would never end. The only coordination in the
                        tree that is not between
                        threads, and the only thing that can answer for a process whose scheduler this one cannot
                        read; a lock rather than a marker, so a host that died mid-pass comes back with a stale
                        file and no claim
    self_update.py      the git probes behind the self-restart guard
    shutdown.py         the signal handler, the bounded-drain watchdog, and the forced exit it ends at
  config/               publishes resolved settings and `RepoSpec`, with parsing owned by its leaves
    __init__.py         reloadable settings bindings, their diagnostic funnel, and the default repo-spec accessor
    environment.py      the env-value parsers and the `_SettingsResolver` that reads and validates every knob
    _dotenv.py          the non-secret `.env` loader
    credentials.py      process / token-file credential resolution and the secret redactor the verify output, the
                        agent stderr diagnostics, and the trajectory writer mask with
    models.py           the `RepoSpec` / `RepoEnvEntry` repository-config types
    repositories.py     `REPOS` entry parsing, validation, and default-spec construction
  github/               publishes `GitHubClient` and `PinnedState` from their defining owners
    client.py           authenticated PyGithub setup, worker-thread clones, paired stage-entry records, and canonical
                        repository identity; a clone reuses the parent's token and bot login on a requester of its
                        own and fetches its repository only on the first read of repository metadata, while
                        number, label, and commit operations stay eager at the call; ownership checks complete that
                        repository first, use GitHub's repository name case-insensitively, and reject a head with no
                        repository
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
                        and a comment reads back as a report only when it is ours and re-renders byte for byte
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
                        every reader of it asks through, the every-state, no-label walk that finds the one
                        issue carrying a marker -- the reading a receipt lookup needs and the only one that
                        sees an issue a human has since closed or relabelled -- and the labels whose CLOSED
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
                        reader after conversation and wrong for one after a receipt it posted itself. A field is
                        asked about two ways and the model answers both -- what one HOLDS, and whether the
                        comment CARRIES it at all -- because every fail-closed reader in this repository turns a
                        value nothing can act on into an absence, so a caller asking whether the record CLAIMS
                        something could not otherwise tell an issue that never wrote a field from one whose
                        field a hand edit truncated
    pull_request_reads.py
                        PR status, open and commit-pinned lookup, branch enumeration, and unreadable-publication
                        evidence; a caller choosing its publication thread can narrow to a base, while a caller
                        proving any publication leaves the base unrestricted
    pull_request_reports.py
                        finding, posting, and rereading developer reports on a pull request's conversation; every
                        reading is present, absent, changed, or unconfirmed, and only absent is posted onto, so a
                        retry finds the comment an earlier attempt landed -- scoped by its transaction receipt, so a
                        later report on the same commit is a comment of its own -- while a pasted copy is not ours
                        and a post whose response was lost stays unconfirmed until a read settles it. A human's
                        report is reread by its exact pull request and comment (or description) against the
                        content digest somebody verified, and the description is never written
    pull_request_retirement.py
                        idempotent supersession notices followed by closure; an authenticated marker read can travel
                        from the caller so no extra request intervenes between its final proof and the write
    pull_requests.py    PR creation, comments, body edits, labels, SHA-pinned merge, and remote-branch deletion;
                        the mutation mixin includes the read, developer-report, and retirement owners in the client's
                        inheritance chain
    reviews.py          current-head review aggregation: approval verdicts and unread-feedback watermarks
  agents/               publishes the run/result models, runner entry point, and process shutdown hook
    models.py           the agent result, run-option, and subprocess-result models
    environment.py      credential filtering and the injected git identity
    session_ids.py      the backend-agnostic session-id walk: a UUID-shaped value at a known key, anywhere in
                        either CLI's event tree, so a resume is issued against what the run actually reported
    sessions.py         Claude final-message JSONL parsing, including the terminal result event the final
                        message is taken from, published whole for the reader of the flags beside it
    provider_failures.py
                        the transient-provider verdict every stage that reads a final message as the agent's
                        own asks first: the backend's `is_error` flag where the run gave one, and the
                        server-refusal message prefix beside a non-zero exit where it did not
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
    base_sync/          the per-tick base fetch and the auto-rebase of every worktree behind it
      refresh.py        the authenticated base fetch, the walk of the repository's worktrees root that hands
                        each entry to the selection owner below, the scheduler-active guard that keeps a
                        worktree out from under a live worker, the dirty-tree refusal a pre-PR rebase owes,
                        the base-lag probe, and the pre-PR versus PR-aware route -- including the one road a lag
                        that cannot be counted does not end: over a pinned auto-rebase anchor it is itself the
                        answer, and the checkout is reset and parked rather than left for a handler the
                        dispatcher holds back
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
                        is another owner's work rather than this refresh's own -- the two parks that freeze one
                        with no record behind them at all
                        (a size reading nobody could take, and an implementer timeout whose watermark names a
                        commit not yet made), and the two no write ever ends (the accepted commit and the
                        published one), which freeze only while the checkout still stands on the commit they
                        name and only while the stage that has to act on it still holds the issue
      eligibility.py    the label, park, open-PR, recovery, and clean-tree gates one PR sync clears, and whether a
                        park a stage left still owes a standing anchor its recovery; a terminal PR ends an anchored
                        attempt's whole handoff through `terminal_handoff`
      pre_pr.py         the hardened rebase / merge probes and the aborting pre-PR local rebase
      pr.py             the order a PR-having worktree's gates, rebase, and publication are asked in, a terminal
                        pull request asked for ahead of any park an anchor stands under, the recovery alone an
                        anchor a stage's park stands over is answered with, and the same gates in front of the
                        abort a checkout whose lag cannot be counted takes
      startup.py        the pre-rebase HEAD guard, and the anchor and the attempt's terms persisted before git
                        runs
      attempts.py       the replay and announcement checkpoints, their presence checks, and the whole-record
                        clear that ends an auto-rebase attempt. Both publication and recovery record their
                        announcement while the anchor still stands and before relabeling
      attempt_records.py
                          validate interrupted replay terms and head as absent, declared, recorded, or damaged,
  sharing the replay
                        field group with the lifecycle clear. Commit validation uses the late domain's format
                        reader through a call-time import
      publication.py    the post-rebase checks, the size gate the rebase passes before it publishes -- reached
                        through a call-time import, since it sits in the workflow layer above this one, and named
                        against the head this owner read, so a checkout something moved between that read and the
                        gate's own refuses rather than publishing one commit while the notice, the event, and the
                        `validating` route name another -- the lease-pinned force-push, and what an accepted push
                        writes. The rewrite evidence it hands that gate beside the candidate is assembled by
                        `transfer_evidence`, since the tick that makes the rewrite is not the only one
                        that needs it
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
                        freeze the current publication entry and ask its transfer permit ahead of a recovered push
                        or the leased no-op that receipts a landed one; both require the same permit again inside
                        the publication gate
      conflicts.py      the counter, notice, event, and relabel a genuinely conflicted rebase is handed to its stage
                        with
      guards.py         the no-op completion and the unreadable-HEAD, dirty-tree, and failed-push refusals
      snapshot.py       the branch fetch, the local / remote head reads and divergence counts, and the abort an
                        unreadable one takes
      recovery.py       the crash-recovery entry the refresh calls: its keyword adapter binds the caller's
                        arguments, the attempt record included, into the recovery context and enters
                        `replay_recovery`
      recovery_push.py  the shared dirty-guarded retry, bound to the exact verified checkout. Ordinary recovery uses
                        the measured gate; a replay carrying a verdict may require a transfer permit before and inside
                        the gate, then verify that the verdict rotated before finalizing the push
      landed_recovery.py
                        the route for a head the pull request already carries: a foreign publication, a
                        foreign mark, a landing nothing of the attempt's vouches for, a tree not provably clean under
                        a verdict, and an unaccounted transfer park without a reset; past them a lost settlement
                        record is reported, best effort, from the proof it kept, and an announced route is only
                        written, an outstanding permission is settled, and anything else takes the ordinary finish
      landed_settlement.py
                        the permitted, leased no-op that receipts an outstanding permission over a landed rewrite and
                        reads the rotation back; every unsettled outcome parks with HEAD and the anchor kept
      terminal_handoff.py
                        the end of an attempt whose PR merged or closed: the attempt and its debt dropped, a
                        shipped rewrite's permission settled with its receipt, any other dropped on the rollback's
                        rule, in one write
      replay_recovery.py
                        the record-based coordinator the refresh enters through `recovery`. Label and unmoved
                        cleanup precede comparison, a published head goes to `landed_recovery` ahead of retry
                        checks, and proven replay evidence precedes the divergence fallback
      replay_cleanup.py the clear-or-park decision for an ineligible label or a checkout back on the anchor. Records
                        that describe a replay, announcement, or unspent transfer prevent a silent clear
      replay_evidence.py
                        pure readings tying the checkout and recorded publication to this attempt, including the
                        grant-vouched window before a replay head was recorded and the finish's own relabel
      replay_refusals.py the ordered preflight before a replay retry: foreign publication, announcement,
                        rollback, unvouched transfer, and unclaimed checkout. Every refusal stays ahead of publication
      outcomes.py       ordinary recovery's already-published, unknown-comparison, diverged, dirty, and failed-push
                        answers; successful notices are formatted by recovery_notices
      replay_transfer_parks.py
                        permit and transfer refusals: reset an unlicensed replay through the guarded rollback, or
                        retain a push that landed without the verdict's rotation for human reconciliation
      replay_checkout_parks.py
                        guarded rollback for unrecorded work, an out-of-band remote rollback, an announced publication
                        the remote lost, or an undone rebase whose abandoned bookkeeping must be retired
      replay_publication_parks.py
                        keep the checkout and pinned evidence when the issue's publication or label changed; a
                        stranded park is recorded once so repeated ticks do not advance the reply watermark
      recovery_holds.py
                        what no recovery road reaches: the reset and park over a checkout whose base lag cannot
                        be counted, and the dispatch hold -- whether a standing anchor keeps a stage handler back,
                        which every label the refresh does not drive does, and one it drives does unless a late
                        claim the reconciliation answers freezes the refresh out -- with a missing checkout
                        restored where the refresh drives the label and the ineligible answer taken where it does
                        not
      persistence.py    the parks, the reset-and-park tail -- which drops the whole attempt and the debt it
                        abandons, and the permission a transfer granted for the same commit, only once the reset
                        has actually landed, since a refused one may leave the branch still standing on the
                        approved commit -- and the recovery finalization that orders notice delivery, the
                        durable announcement checkpoint, routing, and the final state write, beside the write that
                        finishes an announced route without announcing it again
      recovery_notices.py
                        format and deliver the successful recovery notices and audit event before the announcement
                        checkpoint; a failed comment is reported while the recovered publication can still be recorded
      models.py         the frozen contexts, requests, snapshots, and decisions
      state.py          the pinned-state keys, park reasons, refresh detour labels, and the shared logger
    publication/        what a branch becomes before review reads it
      models.py         the record a squash hands back, in the three shapes it can end in -- published, refused, or
                        held by the size gate for the adjudication -- with a refusal NAMING which of four places
                        it left the branch: the approved commits at HEAD, off the tip and reachable only from the
                        head a record names, still in the branch's own history under work committed on top of a
                        recorded head it grew PAST, or none of them shown. The last is not a hedge but the honest
                        answer to a record this build cannot read whole, a recorded head no object here answers
                        to, or a checkout that would not report its own head -- and an operator sent by any of the
                        others would be looking for commits that are not where the notice says
      planning.py       the merge-base, HEAD, dirty, commit-count, and subject preconditions plus the squash
                        message they select -- the count WALKED rather than taken from the subjects beside it,
                        since a commit written with no message contributes no subject and still contributes one
                        commit, and a count short by those decides both whether there is anything to collapse at
                        all and what a human is told their history was collapsed from --
                        and the pre-squash head pinned beside them -- the rollback target, the head the entry takes
                        its lease from, and the commit the gate is told this rewrite collapsed, none of which a
                        reading taken past the reset could recover
      pr_references.py  the ` (#N)` pull-request reference a published commit subject ends in, formatted once for
                        every publisher: a subject already ending in the same reference comes back unchanged, so a
                        retried or repeated publication never doubles it, and one naming any other number is
                        ordinary text the current reference is appended after. Only the subject line comes back,
                        never a body, trailer, or closing keyword, and a pure function reading no git, GitHub, or
                        configuration. The PR title `titles` selects never carries it, since that title is picked
                        before the request has a number
      probes.py         the two branch-geometry reads, and nothing about what a commit SAYS -- `titles` beside it owns
                        that. One is the divergence reading -- the fetched ref resolved ONCE and HEAD counted against
                        that immutable commit, since the counts are a claim about the tip and a ref something moves
                        between two readings would leave a branch proved against one head and its push pinned to
                        another. A reading that did not happen says so (`readable`) rather than answering `(0, 0)`,
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
                        calls, over the gate subject that handler builds, and the owner of `SQUASH_ON_APPROVAL`:
                        the switch decides whether a NEW collapse is made, and one an earlier tick already made
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
                        before the commit count is read as a verdict, since a collapsed branch and a branch with
                        nothing to collapse carry the same one commit; the record goes down between the entry and
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
                        the regex that recognizes it or from the title a caller picks with it. The subject reads
                        honor the spec's own remote and base branch, so a deployment with mixed default branches
                        samples the right history
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
      models.py         the `VerifyResult` statuses and fields, and the output budget
      output.py         the redact-then-truncate pass over captured verify output
      probes.py         HEAD and branch identity, committed-path and regular-file reads, object presence and
                        ancestry. Object presence accepts caller-owned environment pins so a partial clone can
                        distinguish objects already in its store from those a promisor remote could supply
      status.py         the porcelain status in both its answers (the paths, whether git could be
                        asked, and the `is_clean` a caller whose next step is a push asks instead of truth-testing
                        the list) -- taken without optional locks, so asking what a tree holds does not refresh
                        and rewrite its index -- the ignored-path read beside it, which is what git leaves out of
                        every one of those and out of its own refusal to remove a dirty worktree, so a caller
                        about to DELETE a tree can be told about the `.env` a caller about to publish rightly
                        passes over. Suppressed index entries make the status unproven even when porcelain
                        reports no paths; NUL-delimited parsing preserves rename sources and unusual filenames
      process.py        one command's group spawn / kill / drain and its verdict
      runner.py         the stripped child environment and the fail-fast command sequencing
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

- `publication/` — `pr_references` calls nothing; `probes` and `titles` each call `commands` and neither calls the
  other; `planning` calls `commands`, `titles`, and the verification probes; `rewrite` calls `commands`,
  `branch_transport`, and those same verification probes; `resume` calls `rewrite` and reaches the gate through the
  one hop that owner spells; `standing` calls `resume` for the ancestry read and reaches the gate through that same
  hop; `squash` calls `planning`, `resume`, `rewrite`, and `standing`.
- `verification/` — `output` calls `models`, `process` calls `output` and `status`, and `runner` calls `process`.
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
- `base_sync/` — `models` and `state` carry only data. On the sync side `refresh` calls `refresh_selection` before
  `pre_pr` and `pr`, `refresh_selection` asks `frozen` alone, `pr` asks `eligibility`, `startup`, and `publication` in
    that order, and `guards` ends in `persistence`. On the recovery side `recovery` enters `replay_recovery`,
  which uses `replay_cleanup` before comparison, then
  `replay_refusals` and `replay_evidence` before selecting that shared push. Its refusal owners separate checkout
  rollback, publication identity, and transfer accounting. `recovery_push` coordinates the gate and `persistence`
    finalization, and `transfer_permits` freezes the entry for the permit it re-asks. `attempts` is under both: it
  owns the record one rebase attempt leaves of itself, and every owner
  that writes a member of that record or ends it calls through it rather than spelling a key of its own.
  `attempt_records` owns interrupted-replay validation; `recovery_notices` delivers the notice and audit event in
  the order `persistence` coordinates with its checkpoint and routing. `transfer_evidence` assembles the rewrite
  the publisher or recovery hands to the size gate. `transfers` classifies the interrupted permission through
  `transfer_attempts` and `transfer_publication`, using the bounded handoff values in `transfer_values`.
  `recovery_holds` reads the refusals the dispatch hold releases for off `refresh_selection` and `frozen`, and
  answers a held anchor through `replay_cleanup` and `replay_publication_parks`. The three keyword-call adapters — the
  PR sync, the conflict route, and the crash recovery — still take the argument lists their callers spell and
  normalize each into the typed context entry point beside it.
