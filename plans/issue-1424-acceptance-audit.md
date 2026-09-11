# Issue #1424: branch acceptance audit

Audited implementation: `0918fbafcd6f9f16547b771a115dc3f569dec9e4` on `reduce-flake8-exclusions`, 2026-09-11.
The audit report commit changes working notes only; the source and lint configuration are those of this SHA.

Both implementation gaps identified by [PR #1697](https://github.com/chippingway/orchestrator/pull/1697) are
resolved on this branch: the late-park replacement exemption is removed, and WPS235 uses its default ceiling
of eight. The coordinator cleanup also removes two existing exemptions. Final merged-parent closeout remains
pending the excluded children and integration; this report does not close or modify the GitHub parent.

## Measured progress

| Snapshot | Exact paths | Production pairs | Test pairs | Total pairs |
|---|---:|---:|---:|---:|
| Original parent, `4c384cba` | 75 | 100 | 0 | 100 |
| Planning snapshot, `e3a0b434` | 112 | 95 | 39 | 134 |
| Implementation base, `68f8fa73` | 111 | 94 | 39 | 133 |
| Integrated `main`, `3d22380d` | 110 | 93 | 39 | 132 |
| Audited implementation, `0918fbaf` | 108 | 90 | 39 | 129 |
| After integrating all tracked children, projected | 100 | 81 | 39 | 120 |

- Compared with integrated `main`, this branch removes **3 pairs across 2 paths** and adds **0 pairs**.
- The current inventory has **0 stale or unmapped pairs**. #1736 separately removes one pair from the initial base.
- WPS235: **102 violations across 96 files → 0**. The global `max-import-from-members = 30` override is gone.
- **53 of the original 100 pairs are absent**; 47 remain. Another 82 current pairs were absent from that original
  snapshot. These are path/rule measurements, not a percentage of implementation effort or credit for later additions.
- The projected 120 pairs assume the remaining assigned removals land with no intervening additions.

The three removals delivered here are:

- `orchestrator/workflow/stages/decomposition/late_parks.py`: WPS202.
- `orchestrator/workflow/stages/decomposition/late_coordinator.py`: WPS201 and WPS202.

| Rule | Current live/configured pairs |
|---|---:|
| WPS201 | 8 |
| WPS202 | 94 |
| WPS204 | 3 |
| WPS214 | 8 |
| WPS410 | 8 |
| WPS412 | 8 |

## Excluded work and integration

Child status snapshot: 2026-09-11 09:25 UTC. Eight children remain open: #1728–#1735. #1736 and #1737 have merged.
The initial branch base includes #1737. The audited implementation also integrates #1736 through
[PR #1739](https://github.com/chippingway/orchestrator/pull/1739), merged into `main` at `3d22380d`.
Neither child removal is credited to this branch's three removals. The eight open children target nine pairs.
No process-group, streamed-command, worktree-selection/attribution/claims, late-revision, late-content, stranded
discussion-evidence, or plan-terminal extraction assigned to those children was duplicated.

The original checkout remains on `main`. The implementation worktree is
`/home/d00838679/git/chipping-orchestrator-reduce-flake8-exclusions`.

## Parent acceptance disposition

The [parent](https://github.com/chippingway/orchestrator/issues/1424) remains authoritative. Existing merged
deliveries and their prior audit evidence are retained; the two known gaps now have local implementation evidence.

| Criterion | Evidence and disposition |
|---|---|
| Twenty identified WPS201 removals | Existing #1516 / PR #1526; all twenty mappings remain absent. |
| No stale paths or rules | All 129 configured pairs equal isolated diagnostic pairs. |
| Snapshot namespace WPS202 removal | Existing #1517 / PR #1528; still absent. |
| Named large owners split or justified | Prior merged deliveries plus the owner disposition index below. |
| No raised global WPS limit | Override removed here; all WPS limits use defaults. |
| No blanket/glob/facade/source suppression | Exact paths only; no replacement mechanism added. |
| No replacement structural exemption | Late-park mapping removed; all eleven new production owners need no exemption. |
| Workflow contracts preserved | Function comparisons and existing behavior/crash/ordering tests pass. |
| Docs and patches match owners | Architecture, state-machine references, package docs, and patch targets updated. |
| Before/after counts reported | Tables above identify the original, branch, and projected integrated snapshots. |

Remaining closeout: integrate the excluded children, rerun this inventory and validation at the merged SHA,
refresh each disposition changed by those children, and publish/reconcile the parent checklist through the PR/issue
workflow. Report-publication automation #1702 remains excluded. A local checklist is not merged-parent completion.

## Validation and reproducibility

Locked environment: CPython 3.13.13, Ruff 0.16.5, Flake8 7.3.0, wemake-python-styleguide 1.8.0.
Ruff, import sorting, configured WPS, whitespace checks, and the complete pytest suite pass.
Pytest: **6216 passed, 49 skipped, 29924 subtests passed**. Of the skips, 45 need optional dashboard dependencies and
four need a configured live Postgres test database.
All **6265 collected test identities** are unchanged from the implementation baseline. Import-owner subtest counts
vary as the owner/import inventory changes; no test case or independent assertion was removed.

The worktree ownership table still asserts the same 193 name/owner pairs, and the theme retains its source objects.
The park split preserves all 15 function bodies apart from owner references; the implementing recovery split does
the same for all seven. The coordinator's six owners preserve all 19 original function bodies, including the
explicit admission predicate. The transaction preserves 34 of 36 bodies; its two restructured branches retain
the snapshot-before-children sequence and guarded publication order.
Existing tests cover notice persistence/retry, budget/latch accounting, publication guards, and crash recovery.

```sh
uv sync --locked --python 3.13
uv run ruff check orchestrator tests
uv run ruff check orchestrator tests --select=I001
uv run flake8 orchestrator tests --select=WPS
uv run pytest tests
git diff --check 3d22380d...HEAD
uv run flake8 --isolated orchestrator tests --select=WPS235
uv run flake8 --isolated orchestrator tests \
  --select=WPS201,WPS202,WPS204,WPS214,WPS410,WPS412
```

The last command deliberately exits nonzero for retained violations. Compare distinct path/rule pairs, not raw
diagnostic lines, with `.flake8`. The WPS235 command exits zero. The baseline WPS235 run used an archive of
`68f8fa73` containing only `orchestrator/` and `tests/` and the same locked Flake8 environment.

## Disposition of every configured path

The groups below are disjoint and cover every configured pair. Approved retention from #1697 remains applicable
where responsibilities are unchanged; the current owner docstrings were checked against those responsibilities.
The links point to each current owner and its invariant. Assigned child work is kept separate from retention.
The remaining transaction WPS202 covers ordered publication guards, receipt recovery, and failure-ledger writes;
preparation and retirement have their own clean owners. This does not claim that future useful splits are exhausted.

| Disposition | Paths | Pairs |
|---|---:|---:|
| Intentional package API | 8 | 16 |
| Assigned child work | 8 | 9 |
| Retained production | 61 | 65 |
| Retained tests | 31 | 39 |

### Intentional package API

- [orchestrator/__init__.py](../orchestrator/__init__.py)
  WPS410; WPS412. Retain the intentional package API/metadata surface required by the parent.
- [orchestrator/agents/__init__.py](../orchestrator/agents/__init__.py)
  WPS410; WPS412. Retain the intentional package API/metadata surface required by the parent.
- [orchestrator/config/__init__.py](../orchestrator/config/__init__.py)
  WPS410; WPS412. Retain the intentional package API/metadata surface required by the parent.
- [orchestrator/github/__init__.py](../orchestrator/github/__init__.py)
  WPS410; WPS412. Retain the intentional package API/metadata surface required by the parent.
- [orchestrator/observability/analytics/recording/__init__.py](../orchestrator/observability/analytics/recording/__init__.py)
  WPS410; WPS412. Retain the intentional package API/metadata surface required by the parent.
- [orchestrator/observability/usage/__init__.py](../orchestrator/observability/usage/__init__.py)
  WPS410; WPS412. Retain the intentional package API/metadata surface required by the parent.
- [orchestrator/scheduler/__init__.py](../orchestrator/scheduler/__init__.py)
  WPS410; WPS412. Retain the intentional package API/metadata surface required by the parent.
- [orchestrator/workflow/__init__.py](../orchestrator/workflow/__init__.py)
  WPS410; WPS412. Retain the intentional package API/metadata surface required by the parent.

### Assigned child work

- [orchestrator/agents/processes.py](../orchestrator/agents/processes.py)
  WPS202. Assigned to [#1728](https://github.com/chippingway/orchestrator/issues/1728); pending integration here.
- [orchestrator/git/base_sync/refresh.py](../orchestrator/git/base_sync/refresh.py)
  WPS202. Assigned to [#1730](https://github.com/chippingway/orchestrator/issues/1730); pending integration here.
- [orchestrator/git/commands.py](../orchestrator/git/commands.py)
  WPS202. Assigned to [#1729](https://github.com/chippingway/orchestrator/issues/1729); pending integration here.
- [orchestrator/git/worktrees/attribution.py](../orchestrator/git/worktrees/attribution.py)
  WPS202. Assigned to [#1731](https://github.com/chippingway/orchestrator/issues/1731); pending integration here.
- [orchestrator/git/worktrees/claims.py](../orchestrator/git/worktrees/claims.py)
  WPS202. Assigned to [#1732](https://github.com/chippingway/orchestrator/issues/1732); pending integration here.
- [orchestrator/workflow/stages/decomposition/late_content.py](../orchestrator/workflow/stages/decomposition/late_content.py)
  WPS202. Assigned to [#1734](https://github.com/chippingway/orchestrator/issues/1734); pending integration here.
- [orchestrator/workflow/stages/decomposition/late_revision.py](../orchestrator/workflow/stages/decomposition/late_revision.py)
  WPS201; WPS202. Assigned to [#1733](https://github.com/chippingway/orchestrator/issues/1733); pending integration
  here.
- [orchestrator/workflow/stages/discussion/run.py](../orchestrator/workflow/stages/discussion/run.py)
  WPS202. Assigned to [#1735](https://github.com/chippingway/orchestrator/issues/1735); pending integration here.

### Retained production

- [orchestrator/git/base_sync/persistence.py](../orchestrator/git/base_sync/persistence.py)
  WPS202. Retain. Durable writes, notices, and audit events a recovered rebase leaves behind.
- [orchestrator/git/snapshots/refs.py](../orchestrator/git/snapshots/refs.py)
  WPS202. Retain. Creating, proving, and reclaiming one immutable snapshot ref.
- [orchestrator/git/verification/probes.py](../orchestrator/git/verification/probes.py)
  WPS202. Retain. HEAD, worktree-state, and committed-path probes over what a run left behind.
- [orchestrator/git/worktrees/creation.py](../orchestrator/git/worktrees/creation.py)
  WPS202. Retain. Issue and PR worktree creation plus the unpushed-work probe they gate on.
- [orchestrator/git/worktrees/discovery.py](../orchestrator/git/worktrees/discovery.py)
  WPS202. Retain. One issue's whole contribution: the host's scan, widened by the remote.
- [orchestrator/git/worktrees/eligibility.py](../orchestrator/git/worktrees/eligibility.py)
  WPS202. Retain. Which discovered artifacts may be reclaimed, and why the rest are kept.
- [orchestrator/git/worktrees/evidence.py](../orchestrator/git/worktrees/evidence.py)
  WPS202. Retain. The reads an artifact has to survive before it can be reclaimed.
- [orchestrator/git/worktrees/inventory.py](../orchestrator/git/worktrees/inventory.py)
  WPS202. Retain. The read-only scan that derives issue candidates from local artifacts.
- [orchestrator/git/worktrees/maintenance.py](../orchestrator/git/worktrees/maintenance.py)
  WPS202. Retain. The bounded pass that spends a classification on a finished issue's artifacts.
- [orchestrator/git/worktrees/models.py](../orchestrator/git/worktrees/models.py)
  WPS202. Retain. What a scan of this host's per-issue artifacts found, and what it decided.
- [orchestrator/git/worktrees/paths.py](../orchestrator/git/worktrees/paths.py)
  WPS202. Retain. Slug sanitization plus worktree path and branch-name derivation.
- [orchestrator/github/pull_requests.py](../orchestrator/github/pull_requests.py)
  WPS214. Retain. Pull-request lookup, labeling, status helpers, and merge-side mutations.
- [orchestrator/observability/usage/trajectory_codex_items.py](../orchestrator/observability/usage/trajectory_codex_items.py)
  WPS202. Retain. What one `codex exec --json` stream item normalizes to.
- [orchestrator/runtime/exclusion.py](../orchestrator/runtime/exclusion.py)
  WPS202. Retain. Which process on this host may take its artifacts, and which one is live.
- [orchestrator/workflow/engine/comments.py](../orchestrator/workflow/engine/comments.py)
  WPS202. Retain. Every comment the orchestrator posts, and every comment it reads back.
- [orchestrator/workflow/engine/dispatch.py](../orchestrator/workflow/engine/dispatch.py)
  WPS201; WPS202. Retain. How a tick's pollable issues become handler calls.
- [orchestrator/workflow/engine/drift.py](../orchestrator/workflow/engine/drift.py)
  WPS202. Retain. What counts as the human's requirements, and what a change to them costs.
- [orchestrator/workflow/engine/observations.py](../orchestrator/workflow/engine/observations.py)
  WPS202. Retain. The closes a poll saw that the run holding the issue could not.
- [orchestrator/workflow/engine/prompts.py](../orchestrator/workflow/engine/prompts.py)
  WPS202. Retain. The prompt builders the workflow stages share, and the notes folded in.
- [orchestrator/workflow/engine/retry_budget.py](../orchestrator/workflow/engine/retry_budget.py)
  WPS202. Retain. The day's spawn budget an issue has, and the park an empty one leaves.
- [orchestrator/workflow/engine/run_budget.py](../orchestrator/workflow/engine/run_budget.py)
  WPS202. Retain. What an agent-run budget transition tells both observability sinks.
- [orchestrator/workflow/engine/run_circuit.py](../orchestrator/workflow/engine/run_circuit.py)
  WPS202. Retain. What one launch pays before a process exists, and what turns it away.
- [orchestrator/workflow/engine/run_ledger.py](../orchestrator/workflow/engine/run_ledger.py)
  WPS202. Retain. What one issue may spend on agent runs, what it has spent, and on what.
- [orchestrator/workflow/engine/run_limit.py](../orchestrator/workflow/engine/run_limit.py)
  WPS202. Retain. Where an issue stops once its lifetime agent-run ledger is spent.
- [orchestrator/workflow/engine/terminals.py](../orchestrator/workflow/engine/terminals.py)
  WPS202. Retain. How an issue stops being worked.
- [orchestrator/workflow/engine/usage.py](../orchestrator/workflow/engine/usage.py)
  WPS201; WPS202. Retain. The accounting a tracked agent run is bookended by.
- [orchestrator/workflow/late_split/lineage.py](../orchestrator/workflow/late_split/lineage.py)
  WPS202. Retain. What a child born of a late split inherits, and where it reads it back.
- [orchestrator/workflow/late_split/models.py](../orchestrator/workflow/late_split/models.py)
  WPS214. Retain. The typed vocabularies a late generation is described by, and its record.
- [orchestrator/workflow/late_split/rewrites.py](../orchestrator/workflow/late_split/rewrites.py)
  WPS202. Retain. What authorized an exemption to move from one commit to the one that replaced it.
- [orchestrator/workflow/stages/conflicts/divergence.py](../orchestrator/workflow/stages/conflicts/divergence.py)
  WPS202. Retain. What to do with a worktree that does not match its remote PR head.
- [orchestrator/workflow/stages/conflicts/evidence.py](../orchestrator/workflow/stages/conflicts/evidence.py)
  WPS202. Retain. What a rebase this stage published tells the gate about what it replaced.
- [orchestrator/workflow/stages/conflicts/transitions.py](../orchestrator/workflow/stages/conflicts/transitions.py)
  WPS202. Retain. The two shapes every state-changing exit of this stage shares.
- [orchestrator/workflow/stages/decomposition/late_authorize.py](../orchestrator/workflow/stages/decomposition/late_authorize.py)
  WPS202. Retain. The one decision that publishes an oversized candidate a human has read.
- [orchestrator/workflow/stages/decomposition/late_cancellation.py](../orchestrator/workflow/stages/decomposition/late_cancellation.py)
  WPS202. Retain. What a late cycle owes once the issue it belongs to is gone.
- [orchestrator/workflow/stages/decomposition/late_children.py](../orchestrator/workflow/stages/decomposition/late_children.py)
  WPS202. Retain. The children a late split creates, and what each is born knowing.
- [orchestrator/workflow/stages/decomposition/late_cleanup.py](../orchestrator/workflow/stages/decomposition/late_cleanup.py)
  WPS201; WPS202. Retain. What a split still owes a remote, and the one boundary that can settle it.
- [orchestrator/workflow/stages/decomposition/late_guidance.py](../orchestrator/workflow/stages/decomposition/late_guidance.py)
  WPS202. Retain. What the humans have said since the candidate was frozen, and what it earns.
- [orchestrator/workflow/stages/decomposition/late_hold.py](../orchestrator/workflow/stages/decomposition/late_hold.py)
  WPS202; WPS204. Retain. The cycle-marked hold a pull request wears while adjudication runs.
- [orchestrator/workflow/stages/decomposition/late_models.py](../orchestrator/workflow/stages/decomposition/late_models.py)
  WPS202. Retain. The carriers one late adjudication hands between its owners.
- [orchestrator/workflow/stages/decomposition/late_notice.py](../orchestrator/workflow/stages/decomposition/late_notice.py)
  WPS202. Retain. The sentence a park owes the issue, until it has actually been said.
- [orchestrator/workflow/stages/decomposition/late_owner.py][late-owner]
  WPS202. Retain. The fresh read that stands between a finished run and what it earns.
- [orchestrator/workflow/stages/decomposition/late_reply.py][late-reply]
  WPS202. Retain. One fenced block at the end of a LATE reply, or a reason it is not one.
- [orchestrator/workflow/stages/decomposition/late_restart.py](../orchestrator/workflow/stages/decomposition/late_restart.py)
  WPS202. Retain. The fresh attempt an operator authorizes once a cancelled cycle has ended.
- [orchestrator/workflow/stages/decomposition/late_reuse.py][late-reuse]
  WPS202. Retain. What a child born of a split proves before it starts on what it was cut from.
- [orchestrator/workflow/stages/decomposition/late_session.py](../orchestrator/workflow/stages/decomposition/late_session.py)
  WPS202. Retain. The late run one issue is locked to: read back, recorded, and spawned.
- [orchestrator/workflow/stages/decomposition/late_transaction.py](../orchestrator/workflow/stages/decomposition/late_transaction.py)
  WPS202. Retain. What a guarded split does, in the one order every crash in it is safe in.
- [orchestrator/workflow/stages/decomposition/split.py](../orchestrator/workflow/stages/decomposition/split.py)
  WPS202. Retain. The order a `split` manifest becomes child issues in, and why it is that order.
- [orchestrator/workflow/stages/decomposition/umbrella.py](../orchestrator/workflow/stages/decomposition/umbrella.py)
  WPS202. Retain. A parent whose whole intent is covered by its children.
- [orchestrator/workflow/stages/decomposition/validation.py][validation]
  WPS202. Retain. What a `split` payload must satisfy before any child issue is created.
- [orchestrator/workflow/stages/implementing/disposition.py][disposition]
  WPS202. Retain. What a finished dev run leaves behind, and the timeout's second chance.
- [orchestrator/workflow/stages/implementing/late_command.py](../orchestrator/workflow/stages/implementing/late_command.py)
  WPS202. Retain. The one reply a park for an authorization is ever ended by.
- [orchestrator/workflow/stages/implementing/late_consent.py](../orchestrator/workflow/stages/implementing/late_consent.py)
  WPS202. Retain. The park an adjudicated candidate with nobody behind it waits on.
- [orchestrator/workflow/stages/implementing/late_freeze.py][late-freeze]
  WPS202. Retain. The pair a count is taken over, and what a record has to carry to be one.
- [orchestrator/workflow/stages/implementing/late_gate.py](../orchestrator/workflow/stages/implementing/late_gate.py)
  WPS202. Retain. The size question a committed candidate answers before it is published.
- [orchestrator/workflow/stages/implementing/late_parks.py](../orchestrator/workflow/stages/implementing/late_parks.py)
  WPS202. Retain. What a refusal costs, and the two sinks every one of them reaches.
- [orchestrator/workflow/stages/implementing/late_records.py](../orchestrator/workflow/stages/implementing/late_records.py)
  WPS202. Retain. What one gate call is about, and the identities its records carry.
- [orchestrator/workflow/stages/implementing/late_rewrite.py](../orchestrator/workflow/stages/implementing/late_rewrite.py)
  WPS202. Retain. The push a squash-on-approval makes over the branch it just rewrote.
- [orchestrator/workflow/stages/implementing/late_transfer.py](../orchestrator/workflow/stages/implementing/late_transfer.py)
  WPS202. Retain. Whether a rewrite may carry an adjudicated change onto the commit replacing it.
- [orchestrator/workflow/stages/implementing/late_verdict.py](../orchestrator/workflow/stages/implementing/late_verdict.py)
  WPS202. Retain. What a measured candidate earns, and what the record owes on the way.
- [orchestrator/workflow/stages/implementing/parks.py](../orchestrator/workflow/stages/implementing/parks.py)
  WPS202. Retain. Why a run that produced no publishable commit stopped, and what that costs.
- [orchestrator/workflow/state.py](../orchestrator/workflow/state.py)
  WPS202. Retain. Typed workflow state: the label vocabulary, its graph, and the write guard.

### Retained tests

- [tests/git/publication/squash_recovery_support.py](../tests/git/publication/squash_recovery_support.py)
  WPS202. Retain. The crash boundaries one squash-on-approval can be interrupted at.
- [tests/git/worktrees/artifact_test_support.py](../tests/git/worktrees/artifact_test_support.py)
  WPS214. Retain. Clones, checkouts, and specs the local artifact scan is read from.
- [tests/git/worktrees/candidate_host_test_support.py](../tests/git/worktrees/candidate_host_test_support.py)
  WPS202; WPS214. Retain. The host a terminal-artifact classification reads: clone, remote, checkouts.
- [tests/git/worktrees/discovery_test_support.py](../tests/git/worktrees/discovery_test_support.py)
  WPS214. Retain. The host and remote a candidate discovery is read off, both of them real.
- [tests/git/worktrees/maintenance_test_support.py](../tests/git/worktrees/maintenance_test_support.py)
  WPS202; WPS214. Retain. The finished issue a maintenance pass runs over, on a real host and remote.
- [tests/git/worktrees/test_artifact_eligibility.py](../tests/git/worktrees/test_artifact_eligibility.py)
  WPS202. Retain. Which discovered candidates may be reclaimed, over a real host and a double.
- [tests/git/worktrees/test_artifact_evidence.py](../tests/git/worktrees/test_artifact_evidence.py)
  WPS202; WPS214. Retain. The reads a terminal artifact is judged by, one answer at a time.
- [tests/git/worktrees/test_local_inventory.py](../tests/git/worktrees/test_local_inventory.py)
  WPS202. Retain. The read-only scan: which issues a host's own artifacts name, and which it refuses.
- [tests/git/worktrees/test_maintenance_pass.py](../tests/git/worktrees/test_maintenance_pass.py)
  WPS202. Retain. What one maintenance pass takes, what it refuses, and what it leaves behind.
- [tests/runtime/test_exclusion.py](../tests/runtime/test_exclusion.py)
  WPS202. Retain. Which process on this host may take its artifacts, across processes.
- [tests/workflow/engine/lifetime_test_support.py](../tests/workflow/engine/lifetime_test_support.py)
  WPS202. Retain. One issue's whole life under a small allowance, driven a tick at a time.
- [tests/workflow/engine/run_circuit_test_support.py](../tests/workflow/engine/run_circuit_test_support.py)
  WPS202. Retain. Fixtures for driving one launch through the agent-run circuit.
- [tests/workflow/engine/run_limit_test_support.py](../tests/workflow/engine/run_limit_test_support.py)
  WPS202. Retain. Fixtures and protocol values the agent-run-limit park tests read against.
- [tests/workflow/engine/test_run_budget.py](../tests/workflow/engine/test_run_budget.py)
  WPS202. Retain. The record an agent-run budget transition leaves on both sinks.
- [tests/workflow/engine/test_run_grant.py](../tests/workflow/engine/test_run_grant.py)
  WPS202. Retain. What one add-agent-runs request moves, and what it leaves exactly alone.
- [tests/workflow/engine/test_run_limit.py](../tests/workflow/engine/test_run_limit.py)
  WPS202. Retain. The park a spent lifetime agent-run ledger leaves, and what it says once.
- [tests/workflow/engine/usage_test_support.py](../tests/workflow/engine/usage_test_support.py)
  WPS202. Retain. Wire payloads, constants, and fixtures for agent analytics tests.
- [tests/workflow/late_split/generation_test_support.py](../tests/workflow/late_split/generation_test_support.py)
  WPS202. Retain. The late generation the domain's tests read state and events off.
- [tests/workflow/late_split/test_events.py](../tests/workflow/late_split/test_events.py)
  WPS202. Retain. What each family may say, and the closed vocabulary a verdict says it in.
- [tests/workflow/patch_models.py](../tests/workflow/patch_models.py)
  WPS202. Retain. Typed inputs and basic mock builders for workflow test runs.
- [tests/workflow/stages/conflicts/test_replay_real_git.py](../tests/workflow/stages/conflicts/test_replay_real_git.py)
  WPS201. Retain. A conflict-stage replay decided over a real repository and real bytes.
- [tests/workflow/stages/conflicts/test_settled_round.py](../tests/workflow/stages/conflicts/test_settled_round.py)
  WPS202. Retain. The round a resolution earns when the size gate holds it off the PR.
- [tests/workflow/stages/decomposition/late_content_support.py](../tests/workflow/stages/decomposition/late_content_support.py)
  WPS202. Retain. The issue thread the late content, guidance, and revision tests read.
- [tests/workflow/stages/decomposition/late_test_support.py][late-test-support]
  WPS202. Retain. The one oversized candidate the late-mode tests adjudicate.
- [tests/workflow/stages/decomposition/test_late_authorize.py](../tests/workflow/stages/decomposition/test_late_authorize.py)
  WPS201; WPS202; WPS204. Retain. What publishes an oversized candidate a human read, and what does not.
- [tests/workflow/stages/decomposition/test_late_cleanup_publication.py](../tests/workflow/stages/decomposition/test_late_cleanup_publication.py)
  WPS201. Retain. The branch a split superseded, and the change that may come back for it.
- [tests/workflow/stages/decomposition/test_late_unsplit_notice.py](../tests/workflow/stages/decomposition/test_late_unsplit_notice.py)
  WPS202; WPS204. Retain. The sentence an unsplit park owes, and what it is allowed to name.
- [tests/workflow/stages/implementing/late_consent_test_support.py](../tests/workflow/stages/implementing/late_consent_test_support.py)
  WPS201; WPS202; WPS214. Retain. One adjudicated candidate parked for the person nobody can show.
- [tests/workflow/stages/implementing/late_transfer_test_support.py](../tests/workflow/stages/implementing/late_transfer_test_support.py)
  WPS202. Retain. The one rewrite the transfer's tests grant, refuse, or settle a permit for.
- [tests/workflow/stages/implementing/test_late_gate_retry.py](../tests/workflow/stages/implementing/test_late_gate_retry.py)
  WPS202. Retain. What a human's reply to a measurement park buys, and what it may not.
- [tests/workflow/stages/implementing/test_late_transfer.py][test-late-transfer]
  WPS202. Retain. What a rewrite of an adjudicated commit may carry, and what it may not.

[late-owner]: ../orchestrator/workflow/stages/decomposition/late_owner.py
[late-reply]: ../orchestrator/workflow/stages/decomposition/late_reply.py
[late-reuse]: ../orchestrator/workflow/stages/decomposition/late_reuse.py
[validation]: ../orchestrator/workflow/stages/decomposition/validation.py
[disposition]: ../orchestrator/workflow/stages/implementing/disposition.py
[late-freeze]: ../orchestrator/workflow/stages/implementing/late_freeze.py
[late-test-support]: ../tests/workflow/stages/decomposition/late_test_support.py
[test-late-transfer]: ../tests/workflow/stages/implementing/test_late_transfer.py
