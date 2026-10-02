# chipping-orchestrator release timeline

Source material for a public timeline of `chipping-orchestrator`: all **14 published releases**, from `v0.1.0` through
`v0.12.0`, checked against the [GitHub release history][releases] and tagged changes on **2026-10-02**. The table gives
each milestone a date, version, and suggested title; the lists below supply its functionality and supporting sources.

Dates are GitHub release publication dates in **UTC**, rather than commit or tag dates. Each list describes what shipped
at that tag. Changes made after `v0.12.0` are outside this timeline. Historical names and controls are retained where
they explain a release; use the [documentation index](README.md) for current operation and configuration.

## Timeline milestones

| Published date | Release | Suggested timeline title |
|---|---|---|
| 2026-05-19 | [v0.1.0](#v010) | GitHub issues become reviewed pull requests |
| 2026-05-26 | [v0.2.0](#v020) | Documentation, Q&A, verification, and parallel work |
| 2026-06-03 | [v0.3.0](#v030) | Analytics dashboard and scheduled issue processing |
| 2026-06-09 | [v0.4.0](#v040) | Faster analytics and guarded workflow transitions |
| 2026-06-23 | [v0.5.0](#v050) | Repository context and resilient agent sessions |
| 2026-06-30 | [v0.6.0](#v060) | Agent trajectories and skill telemetry |
| 2026-07-09 | [v0.7.0](#v070) | Trusted conversations, pause controls, and issue usage |
| 2026-07-23 | [v0.8.0](#v080) | Session adoption analytics and a modular runtime |
| 2026-08-10 | [v0.9.0](#v090) | Installable CLI and canonical package entrypoints |
| 2026-08-19 | [v0.10.0](#v0100) | Architecture discussions and skill provenance |
| 2026-08-20 | [v0.10.1](#v0101) | Visible automatic recovery and stranded-fix publication |
| 2026-08-26 | [v0.11.0](#v0110) | Size-gated publication and reusable implementation splits |
| 2026-08-31 | [v0.11.1](#v0111) | Cumulative PR limits and the chipping-orchestrator name |
| 2026-09-15 | [v0.12.0](#v0120) | Human size approval, lifetime budgets, and artifact cleanup |

## v0.1.0

Published **2026-05-19**. Sources: [release notes][v0.1.0] and [tagged history][history-0.1.0].

**Added functionality**

- GitHub issue processing through workflow labels and a pinned JSON state comment, allowing progress to survive
  orchestrator restarts without a workflow database.
- Configurable local `codex` and `claude` backends for implementation, review, and decomposition, with reusable agent
  sessions and human notifications.
- Isolated per-issue git worktrees, branch publication, idempotent PR creation, and branch cleanup after merge.
- Manifest-based decomposition into child issues, dependency ordering, umbrella parents, and a final documentation
  child for split work.
- A bounded reviewer/developer loop, approval squashing, conflict-resolution handling, and `done` / `rejected` outcomes.
- Optional automatic merging after approval and green CI, disabled by default. This option was removed in `v0.3.0`.
- Multi-repository operation through `REPOS`, separate target clones, repository-specific credentials, and worktrees
  namespaced by repository.
- Configurable daily implementation retries and review/conflict round limits, issue-author allowlisting, and multiple
  human handles for requests requiring intervention.
- Token storage outside `.env`, credential stripping from agent environments, authenticated pushes hardened against
  repository-controlled Git configuration, and lease-protected push retries.
- A polling launcher with self-update/restart behavior, file logs, and GitHub Actions lint and test checks.

## v0.2.0

Published **2026-05-26**. Sources: [release notes][v0.2.0] and [tagged changes][changes-0.2.0].

**Added functionality**

- A dedicated `documenting` stage for documentation passes after implementation and later code-changing fixes.
- A `fixing` stage that waits for a quiet feedback window, tracks unread PR feedback, and resumes the developer session.
- Read-only issue Q&A through the `question` label, including follow-up conversations without opening a pull request.
- Local verification through `VERIFY_COMMANDS` and `VERIFY_TIMEOUT` before approved work reaches `in_review`.
- Concurrent work within and across repositories, bounded by per-repository and global issue limits.
- `backlog` to postpone pickup, plus the historical `hold_base_sync` control to suspend base synchronization. The latter
  was removed in `v0.7.0`.
- Automatic base refresh into issue worktrees and routing or session resumption when humans edit issue requirements.
- `/orchestrator add-review-rounds N` to extend an exhausted review allowance, and one human notification when a PR is
  ready for merging.
- Shell-like agent command specifications with model/effort arguments, persisted across session resumes, and
  configurable Git remote names globally or per repository.
- Audit events and an analytics JSONL sink with retention, stage evaluation timing, agent-run records, parsed token
  usage, and estimated costs.

**Improvements and changes**

- Stage-specific workflow modules and tests, expanded operator documentation, stale Claude-session replacement,
  rejected-branch cleanup, authenticated target fetches, and correct launcher shutdown on Ctrl+C or SIGTERM.

## v0.3.0

Published **2026-06-03**. Sources: [release notes][v0.3.0] and [tagged changes][changes-0.3.0].

**Added functionality**

- A Streamlit analytics dashboard with Plotly charts, shared styling, and views focused on analyzing workflow behavior.
- JSONL-to-Postgres synchronization and a bundled Docker Compose Postgres service for local analytics storage.
- A Postgres dashboard read model with aggregate queries, an agent-run view, hot-path indexes, and GPT-5.5 pricing.
- A process-local issue scheduler with family-aware dispatch and completion reaping once per polling pass.

**Improvements and changes**

- Reviewer approval hands work to a final documentation pass before the human merge handoff. Linked PRs already merged
  are reconciled to `done`.
- Automatic merging was removed: `in_review` became permanently dependent on a human merge decision.
- Agent and verification subprocesses receive environments stripped of production secrets.
- Lockfile-based installation, Dependabot, dependency review, and read-only CI permissions strengthened dependency
  handling.
- Git and analytics responsibilities were split into focused modules; basic and advanced environment templates were
  separated. Launcher pull-failure handling and documentation-stage base synchronization were corrected.

## v0.4.0

Published **2026-06-09**. Sources: [release notes][v0.4.0] and [tagged changes][changes-0.4.0].

**Added functionality**

- Dashboard timezone selection, agent-role cost splits, and cached versus uncached cost breakdowns by review round and
  workflow stage.
- Daily analytics rollups, batched sync inserts, existing-record hash checks, and sync progress/timing output.
- Typed workflow labels, typo detection, and a transition-table guard against invalid workflow-state changes.
- Community-contribution PR labeling and routing to human reviewers.

**Improvements and changes**

- Dashboard layout and styling were redesigned. Reused database connections, parallel reads, consolidated queries,
  static metadata caching, and rollup-backed widgets reduced dashboard work.
- Reviewer-requested developer changes use `fixing`, with recovery for stuck, unacknowledged, and nothing-to-fix rounds.
- PR branches gained repository namespaces; backlog, umbrella, and no-agent family buckets received corrected capacity
  accounting. Closed sweep-labeled issues can finish as `done`.

## v0.5.0

Published **2026-06-23**. Sources: [release notes][v0.5.0] and [tagged changes][changes-0.5.0].

**Added functionality**

- Prompts can expose tracked sibling repositories, local roots, and base branches for read-only cross-repository
  reference. `EXPOSE_TRACKED_REPOS` disables this context globally; single-repository deployments do not receive it.
- `DEV_SESSION_MAX_RESUMES` proactively rotates long-lived developer sessions. Claude context-overflow failures get one
  immediate replacement session, grounded in the issue, comments, branch state, and available repository context.
- Commit-producing prompts, PR titles, and squash commits follow the target repository's recent commit style, including
  repository-specific prefixes and a documentation pass without a mandatory `docs:` prefix.

**Improvements and changes**

- Clean committed fixes stranded locally are published even when a resumed developer makes no additional commit; this
  recovery takes priority over a fixing acknowledgment.
- Commit-producing agents receive foreground-execution guidance for builds, tests, and servers.
- Bot-authored PRs are excluded from community-contribution routing; locked dependencies and operator references were
  refreshed.

## v0.6.0

Published **2026-06-30**. Sources: [release notes][v0.6.0] and [tagged changes][changes-0.6.0].

**Added functionality**

- Opt-in agent trajectory recording through `TRAJECTORY_LOG_PATH`, with redaction and truncation, separate from
  analytics.
- A Streamlit trajectory viewer for tool calls/results, text turns, outputs, run selection, and fixture-marked runs.
- Opt-in `TRACK_SKILL_TRIGGERS` parsing for Claude and Codex, skill fields on agent-exit records, and `skill_triggered`
  audit events.
- Repository skill-catalog records, dashboard skill-trigger rates, and a per-skill trigger matrix with run totals.
- Bounded shutdown through `SHUTDOWN_GRACE_SECONDS`, including process-group cleanup of agents and verification
  commands. Shutdown-killed runs are classified as interrupted, and resume stages ignore their partial results.

**Improvements and changes**

- Clean implementation commits stranded after an agent timeout can be recovered and published.
- Cached label objects and `CLOSED_ISSUE_SWEEP_EVERY_N_TICKS` reduce GitHub reads in multi-repository operation.
- Dashboard analytics default to seven days; truncated PR output is identified, and Claude message fallback is safer.

## v0.7.0

Published **2026-07-09**. Sources: [release notes][v0.7.0] and [tagged changes][changes-0.7.0].

**Added functionality**

- The `paused` label freezes an in-flight issue, with checks after agent runs across delivery and conversation stages.
- `/orchestrator continue` retries recoverable session failures across stages; session-limit messages become
  retryable parks.
- Per-issue accumulated agent usage in pinned state and usage verdict comments when an issue ends.
- Run-level trajectory token/cost summaries and Claude per-turn usage detail in recorded trajectories and the viewer.
- Local Codex skill-catalog discovery, trigger-rate columns, and sortable per-skill matrix views.
- Decomposer explanations are surfaced when an issue is judged to be a single task.

**Improvements and changes**

- Issue-author allowlisting becomes a comment trust boundary for prompts, requirement drift, resume signals,
  PR feedback, and retry controls. Only orchestrator-authored pinned comments supply durable state.
- Authenticated Git operations reject local proxy/TLS overrides, and the launcher keeps running when self-update fails.
- `hold_base_sync` was removed. Workflow and observability internals were refactored, and CI gained line-length checks.

## v0.8.0

Published **2026-07-23**. Sources: [release notes][v0.8.0] and [tagged changes][changes-0.8.0].

**Added functionality**

- Skill observations distinguish confirmed Claude loads, inferred Codex `SKILL.md` reads, and incidental references.
- Skill adoption is aggregated by logical agent session, preventing repeated resumes from inflating adoption counts.
- Session adoption becomes the dashboard's primary skill metric, with sortable availability, adoption, invocation-load,
  and incidental-reference columns. Invocation trigger rates and the matrix remain available as diagnostics.

**Improvements and changes**

- Corrected adoption counts, availability metadata, legacy fallback, reporting windows, and developer-fix attribution.
- Dirty-worktree checks and squash/reset/rollback operations were hardened against agent-planted `core.fsmonitor`
  helpers.
- Runtime, workflow, GitHub, Git, agents, and observability were split into focused modules behind compatibility
  facades, preserving imports, patch points, state fields, labels, and the existing module launcher.
- Wemake Python Styleguide became a required development and CI check, alongside expanded module-boundary tests.

## v0.9.0

Published **2026-08-10**. Sources: [release notes][v0.9.0] and [tagged changes][changes-0.9.0].

**Added functionality**

- A Hatchling package build and an installed `agent-orchestrator` console command, the project's name at this release.
- `python -m orchestrator` as the canonical module launcher, sharing CLI composition with the installed command.
- Canonical analytics-dashboard and trajectory-viewer app entrypoints under `orchestrator/apps/`.

**Improvements and changes**

- Responsibility-owned packages replace the legacy flat modules and compatibility facades retained in `v0.8.0`.
  Workflow, configuration, pinned-state, and event contracts are preserved through the source-layout migration.
- Operator commands and downstream imports must use canonical owners; `run.sh` adopts the new module launcher.
- The trajectory viewer explicitly shows an empty skills result. Pytest discovery is restricted to `tests/`, avoiding
  the operator-owned analytics database volume.
- Tests and documentation follow the package layout, with repository checks for import boundaries and public APIs.

## v0.10.0

Published **2026-08-19**. Sources: [release notes][v0.10.0] and [tagged changes][changes-0.10.0].

**Added functionality**

- The operator-applied `discussion` stage supports multi-round architecture conversations through `DECOMPOSE_AGENT`,
  including when ordinary decomposition is disabled.
- A confirmed discussion can produce one validated Markdown plan and a plan PR, with publication and crash recovery
  handled by the orchestrator. Merging the plan ends the issue as `done`; closing it unmerged yields `rejected`.
- Explicit handoff from discussion into implementation reuses the reviewed plan branch and PR.
- Codex trajectories cover MCP calls, web search, patches/file changes, todo-list lifecycles, assistant messages, and
  terminal outcomes. Bounded item accounting and metadata placeholders expose unsupported or excluded items.
- Skill analytics preserve source provenance (`project`, `user`, `harness`, or `unknown`), separating same-named skills
  by level in event records, read models, and dashboard sections.
- A dashboard `30D` date preset and sortable skill-level columns.

**Improvements and changes**

- Machine-driven labels gain the `workflow:` namespace. Startup migrates legacy labels, compatibility reads remain,
  and human-facing controls retain their bare names. Analytics stage identifiers remain unchanged.
- Trusted-reply and relabel guards protect question/discussion work from accidental implementation publication.
- The README becomes an operator guide, and `docs/README.md` indexes focused reference pages. Documentation-link checks
  join the repository suite.

## v0.10.1

Published **2026-08-20**. Sources: [release notes][v0.10.1] and [tagged changes][changes-0.10.1].

**Added functionality**

- An automatic-recovery follow-up on issues after transient push, developer-timeout, or reviewer failures heal under
  validating/fixing. It is crash-safe, at most once per park episode, and sends no additional human mention.

**Improvements and changes**

- The fixing stage publishes clean commits stranded by interrupted or live-paused runs before returning to validation
  without new feedback. Review accounting changes only when publication succeeds.
- Hardened Git status/index/reset operations use absolute worktree paths, supporting relative `WORKTREES_DIR` settings.
- No label, configuration, or dependency migration is required for this patch.

## v0.11.0

Published **2026-08-26**. Sources: [release notes][v0.11.0] and [tagged changes][changes-0.11.0].

**Added functionality**

- A pre-publication size gate through `MAX_ADDED_LINES`, defaulting to `4000` when decomposition is enabled. It measures
  additions over a frozen remote base across all paths; exactly the limit is allowed, and binary content adds no lines.
- Clean committed publication and recovery paths freeze the candidate/base before measurement; failed measurements hold
  the work without rerunning the developer unnecessarily.
- Oversized work returns to the decomposer for `single`, `question`, or `split` adjudication. At this release, `single`
  permits only the exact accepted commit; questions invite revisions, and recursive splits have a lineage-depth bound.
- Immutable late-split snapshot refs preserve committed implementation before child creation. Children receive the exact
  snapshot and lineage so they can reuse the work; refs remain until their recorded direct consumers end.
- Durable plan-PR holds and recovery across child creation, umbrella conversion, superseded branches/worktrees, notices,
  and snapshot reclamation.
- Closed-owner cancellation and cleanup, followed by an explicitly authorized fresh cycle when the issue is reopened and
  `rejected` is removed.
- Correlated audit/analytics events for late measurement, verdicts, failures, snapshots, cleanup, cancellation,
  and restart.

**Improvements and changes**

- Exact approved commit and tree checks before and after pushing protect the final publication handoff.
- SHA-pinned CI actions, CodeQL, OpenSSF Scorecard, scheduled lockfile vulnerability scans, test coverage reporting, and
  a private vulnerability-reporting policy expand repository security checks.

## v0.11.1

Published **2026-08-31**. Sources: [release notes][v0.11.1] and [tagged changes][changes-0.11.1].

**Added functionality**

- Cumulative size measurement of the complete prospective PR before every orchestrator-owned update, including fixes,
  recovery pushes, rebases, conflict resolutions, approval squashes, and final documentation.
- Oversized updates stay local while the existing implementation PR receives a durable do-not-merge hold. Frozen stage,
  PR, and prior-head records preserve feedback, review counters, documentation completion, and conflict state.
- A `single` decision publishes to the same PR and resumes the originating stage. A split snapshots the work, closes the
  superseded PR, creates children, and converts the parent to an umbrella, with recovery across each handoff.
- Late-split telemetry distinguishes `pre_publication` and `post_publication`, with originating stage/PR/head context.

**Improvements and changes**

- The distribution and installed command are renamed from `agent-orchestrator` to `chipping-orchestrator`; repository
  references and default agent identity are updated. The module launcher and `run.sh` remain valid.
- Transient provider overload/refusal is retryable: developer runs use the continue control, while reviewers recover
  automatically. Unclassified skills resolve against the repository catalog when exactly one source level matches.
- CI covers Python 3.12 and 3.13, cancels superseded PR runs, applies job timeouts, and smoke-tests the built wheel
  in isolation.

## v0.12.0

Published **2026-09-15**. Sources: [release notes][v0.12.0] and [tagged changes][changes-0.12.0].

**Added functionality**

- Oversized `single` verdicts require human approval and an explanation of why no safe split exists. The exact candidate
  is authorized with `/orchestrator authorize-oversized <commit>`, preserving the decision through publication retries.
- Authorized exemptions can follow orchestrator-owned squashes and clean rebases only when contribution fingerprints
  prove the full contribution unchanged. Added fixes, documentation, descendants, and split children are measured
  normally.
- Durable recovery of interrupted squashes/rebases and already-landed pushes, verified against recorded commits, PR,
  remote base, and lease. Uncertain evidence remains parked for a human decision.
- Late-split children must each own implementation, tests, and documentation and declare an all-path added-line estimate
  strictly below the frozen ceiling. Estimates survive recovery and are shown on child issues.
- `MAX_AGENT_RUNS_PER_ISSUE` introduces a durable lifetime allowance, defaulting to `50`, charged before each launch
  across roles, fresh runs, resumes, replacements, timeouts, and interruptions. Resets and restarted cycles retain
  spent runs.
- `/orchestrator add-agent-runs N` grants 1 to 50 more runs after a lifetime-budget park; `0` in the global setting
  disables enforcement while accounting continues.
- Exhausted daily retry budgets require a trusted `/orchestrator continue` for one fresh attempt, including across new
  days, requirement edits, and configuration changes. It does not override the lifetime allowance.
- Finished-issue artifact cleanup runs daily or on demand with `--cleanup-terminal-artifacts`, reclaiming eligible local
  worktrees and local/remote branches only on a quiet host with closed terminal issues and preserved, inactive,
  clean work.
- New `agent_run_budget` and `late_transfer` observability records, plus analytics results for terminal artifact
  cleanup.

**Improvements and changes**

- Base read/fetch failures retry silently for three consecutive misses; the fourth asks for human intervention.
  Measurement failures identify the step and scrubbed diagnostic, suppressing repeated notices for the same cause.
- Publication receipts are bound to their PR, and pushes to merged or closed PRs are refused. Completed splits release
  their children without stale measurement parks.
- CI adds Python 3.14; analytics Compose requires existing bind-source directories; lint coverage and locked tooling
  are refreshed without adding runtime dependencies.

[releases]: https://github.com/chippingway/chipping-orchestrator/releases
[v0.1.0]: https://github.com/chippingway/chipping-orchestrator/releases/tag/v0.1.0
[v0.2.0]: https://github.com/chippingway/chipping-orchestrator/releases/tag/v0.2.0
[v0.3.0]: https://github.com/chippingway/chipping-orchestrator/releases/tag/v0.3.0
[v0.4.0]: https://github.com/chippingway/chipping-orchestrator/releases/tag/v0.4.0
[v0.5.0]: https://github.com/chippingway/chipping-orchestrator/releases/tag/v0.5.0
[v0.6.0]: https://github.com/chippingway/chipping-orchestrator/releases/tag/v0.6.0
[v0.7.0]: https://github.com/chippingway/chipping-orchestrator/releases/tag/v0.7.0
[v0.8.0]: https://github.com/chippingway/chipping-orchestrator/releases/tag/v0.8.0
[v0.9.0]: https://github.com/chippingway/chipping-orchestrator/releases/tag/v0.9.0
[v0.10.0]: https://github.com/chippingway/chipping-orchestrator/releases/tag/v0.10.0
[v0.10.1]: https://github.com/chippingway/chipping-orchestrator/releases/tag/v0.10.1
[v0.11.0]: https://github.com/chippingway/chipping-orchestrator/releases/tag/v0.11.0
[v0.11.1]: https://github.com/chippingway/chipping-orchestrator/releases/tag/v0.11.1
[v0.12.0]: https://github.com/chippingway/chipping-orchestrator/releases/tag/v0.12.0
[history-0.1.0]: https://github.com/chippingway/chipping-orchestrator/commits/v0.1.0/
[changes-0.2.0]: https://github.com/chippingway/chipping-orchestrator/compare/v0.1.0...v0.2.0
[changes-0.3.0]: https://github.com/chippingway/chipping-orchestrator/compare/v0.2.0...v0.3.0
[changes-0.4.0]: https://github.com/chippingway/chipping-orchestrator/compare/v0.3.0...v0.4.0
[changes-0.5.0]: https://github.com/chippingway/chipping-orchestrator/compare/v0.4.0...v0.5.0
[changes-0.6.0]: https://github.com/chippingway/chipping-orchestrator/compare/v0.5.0...v0.6.0
[changes-0.7.0]: https://github.com/chippingway/chipping-orchestrator/compare/v0.6.0...v0.7.0
[changes-0.8.0]: https://github.com/chippingway/chipping-orchestrator/compare/v0.7.0...v0.8.0
[changes-0.9.0]: https://github.com/chippingway/chipping-orchestrator/compare/v0.8.0...v0.9.0
[changes-0.10.0]: https://github.com/chippingway/chipping-orchestrator/compare/v0.9.0...v0.10.0
[changes-0.10.1]: https://github.com/chippingway/chipping-orchestrator/compare/v0.10.0...v0.10.1
[changes-0.11.0]: https://github.com/chippingway/chipping-orchestrator/compare/v0.10.1...v0.11.0
[changes-0.11.1]: https://github.com/chippingway/chipping-orchestrator/compare/v0.11.0...v0.11.1
[changes-0.12.0]: https://github.com/chippingway/chipping-orchestrator/compare/v0.11.1...v0.12.0
