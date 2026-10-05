# chipping-orchestrator — Future work and risks

Working notes for possible improvements and remaining operational risks.
For current behavior, see the [reference documentation](../docs/README.md);
for shipped milestones, see the [release timeline](../docs/release-timeline.md).

## Future work

The alias cleanup follows up existing code. The remaining entries are
proposals; expand one into a design document when it is picked up.

- **Retire the pre-PR rebase compatibility alias.** Confirm that no
  out-of-repo patch still imports `_merge_base_into_worktree`, then remove
  that forwarding function and its compatibility test. The source TODO in
  [`orchestrator/git/base_sync/pre_pr.py`](../orchestrator/git/base_sync/pre_pr.py)
  still tracks this cleanup.
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
  isolation remains proposed; the host is the current sandbox boundary.
  The [Docker deployment plan](docker-deployment.md) covers container setup
  and external runtime storage. Migration from per-repo PATs to a GitHub App
  installation token remains a separate proposal.
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

- **R1 — Codex / Claude / Antigravity CLI output format drift.** Isolated in the
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
  keep spawning agents. These limit run time and process starts rather than
  impose a token or cost ceiling; the lifetime cap can be disabled with `0`.
- **R4 — GitHub rate limits.** Idle per-repo polls and closed-issue
  sweeps can exhaust a token's request budget at the default cadence once
  enough repos are tracked. Label caching and
  `CLOSED_ISSUE_SWEEP_EVERY_N_TICKS` reduce the floor;
  `DEPENDENCY_POLL_EVERY_N_TICKS` reduces child reads for waiting parents.
  Operators can raise `POLL_INTERVAL` or split repos across tokens.
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
