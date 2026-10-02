# chipping-orchestrator — Roadmap

## Status as of 2026-09-11

Checked against `main` at `68f8fa73`, which declares version 0.11.1.
The fixed delivery lifecycle is wired end-to-end: pickup →
`workflow:decomposing` → `workflow:ready` / `workflow:blocked` /
`workflow:umbrella` → `workflow:implementing` → `workflow:validating` →
`workflow:documenting` (final-docs handoff) → `in_review` → terminal
`done` / `rejected`, with `workflow:fixing` and
`workflow:resolving_conflict` as the review-side loops back to
`workflow:validating`. The operator-applied `question` and `discussion`
labels provide read-only Q&A and design-conversation side branches; a
confirmed discussion publishes a plan PR. The `backlog` and `paused`
control labels hold fresh or in-flight work without changing the workflow
state. With the default `DECOMPOSE=on`, every new committed candidate is
measured against `MAX_ADDED_LINES` before its first publication and again,
cumulatively, before every later push onto its PR. Oversized work returns
to `workflow:decomposing` for a resumable single-or-split adjudication that
preserves and reuses the committed candidate. A late `single` verdict parks
for a human decision; a trusted `/orchestrator authorize-oversized <commit>`
authorizes that exact candidate, while guidance resumes the developer for a
revision. Every proposed split child declares its own addition budget below
the frozen ceiling, including tests and documentation. Turning decomposition
off does not bypass a candidate already recorded in a live generation or
still owed publication.

The orchestrator runs as a single long-lived Python process through
`chipping-orchestrator` or `python -m orchestrator`, with `run.sh` wrapping
it for self-restart. It polls one or more configured repos and delegates
coding to `codex` /
`claude` CLI subprocesses in per-issue git worktrees. State lives in
GitHub Issues themselves (one workflow label plus one pinned JSON
comment), so the loop stays stateless and progress is observable on
github.com. Per-repo ticks fan out concurrently; per-issue handlers
within each repo run in parallel up to configurable caps. A durable
per-issue circuit limits lifetime agent-process starts, and a host-wide
maintenance pass reclaims proven-safe terminal worktrees and branches on a
daily interval or on demand.

The observability stack is also in place: audit events, analytics JSONL
with Postgres rollups, repo skill catalogs, session-aware skill adoption
with confirmed / inferred / incidental evidence, the Streamlit analytics
dashboard, and an opt-in file-backed trajectory sink and viewer for
redacted agent run timelines. Agent token / cost usage is captured both
as run-level analytics and as per-issue pinned counters that produce a
terminal receipt comment. Both event streams also carry size-gate transitions,
completed exemption transfers, and agent-run-budget transitions; terminal
artifact cleanup contributes one bounded analytics record per candidate it
decides about.

For the authoritative behavior, see:

- [`docs/architecture.md`](../docs/architecture.md) — design, module
  map, process / agent / push model.
- [`docs/state-machine.md`](../docs/state-machine.md) — label set,
  per-tick flow, stage-handler semantics, pinned-state schema, label
  lifecycle diagram.
- [`docs/workflow.md`](../docs/workflow.md) — agent roles, command
  specs, session lifecycles.
- [`docs/observability.md`](../docs/observability.md) — audit event
  log, analytics and trajectory sinks, database, dashboards, usage
  parser.
- [`docs/configuration.md`](../docs/configuration.md) — env vars and
  knobs.
- [`docs/security.md`](../docs/security.md) — operator-owned controls.

This file tracks future work and risks. For released functionality and
milestones, see the [release timeline](../docs/release-timeline.md).

## Future work

Open as of 2026-09-11. The first two entries are follow-ups to existing
code. The remaining entries are feature proposals with no implementation
or public configuration surface; expand one into a design document when
it is picked up.

- **Complete authorization enforcement for existing publication records.**
  The size gate can recover an existing `late_unauthorized_exemption` park,
  but ordinary ticks do not create that park. Legacy exemption, approval,
  and publication records can still admit oversized work without human
  authorization. Apply that policy to oversized work entering through those
  records while preserving valid measured approvals and recovery for work
  already published. See
  [`orchestrator/workflow/stages/implementing/late_gate.py`](../orchestrator/workflow/stages/implementing/late_gate.py)
  and [the authorization contract][oversized-authorization].
- **Retire the pre-PR rebase compatibility alias.** Confirm that no
  out-of-repo patch still imports `_merge_base_into_worktree`, then remove
  that forwarding function and its compatibility test. The source TODO in
  [`orchestrator/git/base_sync/pre_pr.py`](../orchestrator/git/base_sync/pre_pr.py)
  named 2026-08-24 as the removal point.
- **Spec-first split.** Insert a `specifying` stage between `ready` and
  `implementing` so a separate spec agent writes failing tests first
  (scoped to test paths) and the orchestrator verifies they fail
  against `origin/<base>` before the implementer runs. Add a
  `spec_skip: true` opt-out to the decomposer manifest for docs /
  refactor work that cannot be expressed as failing tests.
- **Repo memory across issues.** Add a per-target-repo
  `<target_root>/.agent-orchestrator/repo-memory.json` (schema_version,
  verify_commands, top touched files, capped recent failures) updated
  best-effort on merge and folded into decomposer / implementer
  prompts with strict caps. Treat as orchestrator-owned context, not
  PR content.
- **Container / VM isolation + GitHub App migration.** Container or VM
  isolation around the orchestrator host remains an open deployment
  question (the host is currently the real sandbox boundary). Migrate
  from per-repo PATs to a GitHub App installation token.
- **Architectural review at `validating`.** Optional reviewer pass that
  flags structural issues (oversized files, layering violations) that
  the correctness reviewer ignores.
- **Symphony-inspired hooks and policy overrides.** Narrow
  `<target_root>/.agent-orchestrator/policy.toml` overrides (verify
  commands, retry / review-round budgets) with hot-reload, plus three
  workspace lifecycle hooks (`after_create`, `before_run`,
  `after_run`) under `<target_root>/.agent-orchestrator/hooks/`. Both
  opt-in; absent = identical behavior. Full review in
  [`plans/symphony-spec-review.md`](symphony-spec-review.md).

## Risks

- **R1 — Codex / Claude CLI output format drift.** Isolated in the
  provider-specific leaves under `orchestrator/agents/backends/` and
  `orchestrator/observability/usage/`; failures surface as
  `session_id=None` (logged) or empty `last_message` (park with stderr
  quoted via `workflow.engine.agent_diagnostics._format_stderr_diagnostics`).
- **R2 — Self-mutation while running.** Per-issue worktrees +
  ancestry-aware self-update detection in
  `runtime.self_update.self_modifying_merge_happened` + the `run.sh`
  self-restart wrapper.
- **R3 — Runaway agent loops / token cost.** Wall-clock timeouts
  (`AGENT_TIMEOUT`, `REVIEW_TIMEOUT`), per-issue retry budget
  (`MAX_RETRIES_PER_DAY`), review / fix cap (`MAX_REVIEW_ROUNDS`),
  conflict-resolution cap (`MAX_CONFLICT_ROUNDS`), and the durable lifetime
  circuit (`MAX_AGENT_RUNS_PER_ISSUE`) bound the separate ways an issue can
  keep spawning agents.
- **R4 — GitHub rate limits.** Idle per-repo polls and closed-issue
  sweeps can exhaust a PAT's 5000 requests/hour at the default cadence
  once enough repos are tracked. Label caching and
  `CLOSED_ISSUE_SWEEP_EVERY_N_TICKS` reduce the floor; operators can
  raise `POLL_INTERVAL` or split repos across tokens.
- **R5 — Race between human controls and orchestrator action.** Trusted
  comment filters, per-surface watermarks, content hashes, and fresh
  post-agent label reads keep late comments from being silently consumed
  and keep agent output from being published after a mid-run pause. An
  oversized candidate's authorization names the exact commit and is retired
  when its adjudication or generation is replaced; checkout checks bracket
  publication and the handoff to review.
- **R6 — Destructive terminal cleanup.** Artifact reclamation is bounded
  to derived orchestrator names and fails closed on every ambiguous read;
  it also drains scheduler work, takes the host maintenance lock, rechecks
  tips, and uses non-forced / leased deletes. Those are application guards,
  not an OS isolation boundary: arbitrary processes running as the same
  user remain outside the lock's protection.

[oversized-authorization]: ../docs/workflow/roles.md#authorizing-one-oversized-candidate-to-publish
