# Issue #1424: branch acceptance audit

## Zero-exclusion continuation (2026-09-14)

The current user request requires **zero exclusions in `.flake8`**. The retention decisions in the historical
audit below do not close that goal. The continuation began at `660a0bb6` with 129 pairs across 107 paths; the
current working implementation removes 40 pairs and leaves 89 pairs across 74 paths. Its remaining
62 production pairs and 27 test pairs all match isolated diagnostics, with no stale or unmapped pair.

The detailed batch record and outstanding scope are in `issue-1424-remaining-work.md`. All remaining pairs,
including the package initializer rules, still require implementation. Both notes remain until every exclusion
has been removed and the repository-wide lint, test, and whitespace checks pass.

## Historical branch audit

Audited implementation: `fac15168ecee46cc6775c97964eea40f90956ed5` on `reduce-flake8-exclusions`, 2026-09-14.
Rebased onto `main` at `277100dd2664563cb4881f3cf6b51bd70da91fe0`. The following report commit changes working
notes only; the source and lint configuration are those of the audited implementation.

Both implementation gaps identified by [PR #1697](https://github.com/chippingway/orchestrator/pull/1697) are
resolved on this branch: the late-park replacement exemption is removed, and WPS235 uses its default ceiling
of eight. The coordinator cleanup removes two more existing exemptions. All ten tracked children have landed
and are included in the rebase. Parent closeout still requires this branch to merge and its final SHA to be audited.

## Measured progress

| Snapshot | Exact paths | Production pairs | Test pairs | Total pairs |
|---|---:|---:|---:|---:|
| Original parent, `4c384cba` | 75 | 100 | 0 | 100 |
| Planning snapshot, `e3a0b434` | 112 | 95 | 39 | 134 |
| Previous integrated `main`, `3d22380d` | 110 | 93 | 39 | 132 |
| Previous branch, `d1c5df0a` | 108 | 90 | 39 | 129 |
| Current `main`, `277100dd` | 109 | 90 | 42 | 132 |
| Rebased implementation, `fac15168` | 107 | 87 | 42 | 129 |

- Compared with current `main`, this branch removes **3 pairs across 2 paths** and adds **0 pairs**.
- All **129 configured pairs** match isolated diagnostics: **0 stale or unmapped pairs**.
- WPS235 at its default: **107 violations across 101 files on current main → 0 on this branch**.
  The earlier implementation resolved 102; the rebase also resolves five imports added since that baseline.
  The global `max-import-from-members = 30` override is removed.
- **57 of the original 100 pairs are absent**; 43 remain. Another 86 current pairs were absent from that original
  snapshot. These are path/rule measurements, not percentages of implementation effort.
- The prior projection of 120 retained pairs assumed no intervening additions. The eight formerly pending children
  removed their nine assigned pairs, while subsequent main changes added nine pairs. The resulting total is 129.

The three removals delivered here are:

- `orchestrator/workflow/stages/decomposition/late_parks.py`: WPS202.
- `orchestrator/workflow/stages/decomposition/late_coordinator.py`: WPS201 and WPS202.

| Rule | Current live/configured pairs |
|---|---:|
| WPS201 | 8 |
| WPS202 | 92 |
| WPS204 | 4 |
| WPS214 | 8 |
| WPS215 | 1 |
| WPS410 | 8 |
| WPS412 | 8 |

## Child integration

Status checked on 2026-09-14. All ten tracked children are closed as completed. Each listed PR is merged, and
its merge commit is an ancestor of `277100dd`. Their eleven removals are credited to those PRs, separately from
this branch's three removals. Owner moves assigned to the children were preserved rather than repeated.

| Child | Merged PR | Assigned pairs removed |
|---|---|---:|
| [#1728][child-1728] | [#1755][pr-1755] | 1 |
| [#1729][child-1729] | [#1754][pr-1754] | 1 |
| [#1730][child-1730] | [#1752][pr-1752] | 1 |
| [#1731][child-1731] | [#1749][pr-1749] | 1 |
| [#1732][child-1732] | [#1747][pr-1747] | 1 |
| [#1733][child-1733] | [#1744][pr-1744] | 2 |
| [#1734][child-1734] | [#1743][pr-1743] | 1 |
| [#1735][child-1735] | [#1740][pr-1740] | 1 |
| [#1736][child-1736] | [#1739][pr-1739] | 1 |
| [#1737][child-1737] | [#1738][pr-1738] | 1 |

The rebase carries the cleanup into the new late-revision owners and preserves the updated content, handoff,
authorization, and transfer tests. The race test now reads its checkout constants from their defining support
owner. The original checkout remains clean on `main`; implementation stays in the separate worktree at
`/home/d00838679/git/chipping-orchestrator-reduce-flake8-exclusions`.

## Exemptions added by other main changes

These nine pairs were added after `3d22380d` by publication-safety and rebase-evidence work. They are present
on current main and unchanged by this branch. The owner index below records their current retention reasons.
They are not replacement mappings introduced by the ten cleanup children or by this branch.

| Owner | Added rules | Main change |
|---|---|---|
| `git/base_sync/attempts.py` | WPS202 | `b91ec5a1`: durable rebase-attempt evidence |
| `git/base_sync/transfers.py` | WPS201, WPS202 | `21b2949f`: interrupted-transfer classification |
| `github/client.py` | WPS215 | `c825fb59`: repository identity in publication proofs |
| `workflow/engine/observations.py` | WPS204 | `162d7938`: observation receipts and settlement |
| `workflow/late_split/exemption.py` | WPS202 | `21b2949f`: exemption presence classification |
| `tests/support/github/models.py` | WPS202 | `c825fb59`: pull-request repository identity |
| `tests/workflow/late_split/test_exemption.py` | WPS202 | `21b2949f`: exemption presence cases |
| `tests/workflow/stages/implementing/test_late_receipt.py` | WPS202 | `c825fb59`: publication-receipt proofs |

Production paths in this table are relative to `orchestrator/`.

## Parent acceptance disposition

The [parent](https://github.com/chippingway/orchestrator/issues/1424) remains authoritative. This is evidence
for the rebased branch; it does not close the parent or claim that unmerged changes are already on main.

| Criterion | Evidence and disposition |
|---|---|
| Twenty identified WPS201 removals | Existing #1516 / PR #1526; all twenty mappings remain absent. |
| No stale paths or rules | All 129 configured pairs equal isolated diagnostic pairs, including WPS215. |
| Snapshot namespace WPS202 removal | Existing #1517 / PR #1528; still absent. |
| Named large owners split or justified | All tracked children landed; every retained owner is indexed below. |
| No raised global WPS limit | Override removed here; all WPS limits use defaults on the branch. |
| No blanket/glob/facade/source suppression | Exact paths only; no replacement mechanism added. |
| No replacement structural exemption | Late-park mapping removed; all eleven new production owners pass defaults. |
| Workflow contracts preserved | Latest-main behavior, race, and crash tests pass; function comparisons agree. |
| Docs and patches match owners | Child ownership changes and direct patch targets survive the rebase. |
| Before/after counts reported | Tables distinguish original, previous, current-main, and rebased snapshots. |

Remaining parent closeout: merge the implementation PR, verify the inventory and checks at that merged SHA,
and reconcile the parent checklist. There are no outstanding dependencies among the ten tracked children.
Report-publication automation #1702 remains outside this branch's scope.

## Validation and reproducibility

Locked environment: CPython 3.13.13, pytest 9.1.1, Ruff 0.16.5, Flake8 7.3.0, wemake-python-styleguide 1.8.0.
Ruff, import sorting, configured WPS, isolated WPS235, whitespace checks, and the complete pytest suite pass.
Both current main and the rebased branch report **6431 passed, 49 skipped**. Of the skips, 45 need optional
dashboard dependencies and four need a configured live Postgres test database.
All **6480 collected test identities** are identical to current main. Test assertions were retained.

The worktree ownership table preserves all 195 current-main name/owner pairs and all 15 reporting owners.
Fourteen conflict-resolution and import-cleanup files have identical executable syntax trees after resolving
import aliases and moved park references. All eleven production owners created by this branch retain their
pre-rebase contents. The four source owners they were extracted from did not change on main in the meantime.

The existing extraction comparisons therefore still apply: all 15 park functions, seven recovery functions,
and 19 coordinator functions retain their bodies apart from owner references. The transaction preserves 34 of
36 bodies; its preparation and retirement branches preserve the snapshot-before-children sequence and guarded
publication order. Current tests also cover main's added authorization, receipt, and rebase-evidence behavior.

```sh
uv sync --locked --python 3.13
uv run ruff check orchestrator tests
uv run ruff check orchestrator tests --select=I001
uv run flake8 orchestrator tests --select=WPS
uv run pytest tests
git diff --check 277100dd...HEAD
uv run flake8 --isolated orchestrator tests --select=WPS235
uv run flake8 --isolated orchestrator tests \
  --select=WPS201,WPS202,WPS204,WPS214,WPS215,WPS410,WPS412
```

The last command deliberately exits nonzero for retained violations. Compare distinct path/rule pairs, not raw
diagnostic lines, with `.flake8`. The isolated WPS235 selection is clean on this branch. At `277100dd`, the same
locked environment reports 132 configured/live pairs and 107 WPS235 diagnostics at the default threshold.

## Disposition of every configured path

The groups below are disjoint and cover every configured pair. Retention evidence from #1697 remains applicable
where responsibilities are unchanged; updated main owners have the reasons described above and in their docstrings.
The transaction's remaining WPS202 covers ordered publication guards, receipt recovery, and failure-ledger writes;
preparation and retirement have their own clean owners. This does not claim that future useful splits are exhausted.

| Disposition | Paths | Pairs |
|---|---:|---:|
| Intentional package API | 8 | 16 |
| Retained production | 65 | 71 |
| Retained tests | 34 | 42 |

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

### Retained production

- [orchestrator/git/base_sync/attempts.py](../orchestrator/git/base_sync/attempts.py)
  WPS202. Retain. One rebase-attempt record: its writers, presence readings, and whole-record clear share validation
  rules.
- [orchestrator/git/base_sync/persistence.py](../orchestrator/git/base_sync/persistence.py)
  WPS202. Retain. Durable writes, notices, and audit events a recovered rebase leaves behind.
- [orchestrator/git/base_sync/transfers.py](../orchestrator/git/base_sync/transfers.py)
  WPS201; WPS202. Retain. A closed set of transfer outcomes over the same exemption, permission, debt, and receipt
  evidence.
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
- [orchestrator/github/client.py](../orchestrator/github/client.py)
  WPS215. Retain. The concrete client composes four independent domain mixins; merging them would couple unrelated
  owners.
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
  WPS202; WPS204. Retain. One owner observation spans several registries under one lock; settlement must clear them
  together.
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
- [orchestrator/workflow/late_split/exemption.py](../orchestrator/workflow/late_split/exemption.py)
  WPS202. Retain. Exemption and contribution identity share fail-closed readers, writers, and presence rules.
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
- [orchestrator/workflow/stages/decomposition/late_owner.py][owner-1]
  WPS202. Retain. The fresh read that stands between a finished run and what it earns.
- [orchestrator/workflow/stages/decomposition/late_reply.py][owner-2]
  WPS202. Retain. One fenced block at the end of a LATE reply, or a reason it is not one.
- [orchestrator/workflow/stages/decomposition/late_restart.py](../orchestrator/workflow/stages/decomposition/late_restart.py)
  WPS202. Retain. The fresh attempt an operator authorizes once a cancelled cycle has ended.
- [orchestrator/workflow/stages/decomposition/late_reuse.py][owner-3]
  WPS202. Retain. What a child born of a split proves before it starts on what it was cut from.
- [orchestrator/workflow/stages/decomposition/late_session.py](../orchestrator/workflow/stages/decomposition/late_session.py)
  WPS202. Retain. The late run one issue is locked to: read back, recorded, and spawned.
- [orchestrator/workflow/stages/decomposition/late_transaction.py](../orchestrator/workflow/stages/decomposition/late_transaction.py)
  WPS202. Retain. What a guarded split does, in the one order every crash in it is safe in.
- [orchestrator/workflow/stages/decomposition/split.py](../orchestrator/workflow/stages/decomposition/split.py)
  WPS202. Retain. The order a `split` manifest becomes child issues in, and why it is that order.
- [orchestrator/workflow/stages/decomposition/umbrella.py](../orchestrator/workflow/stages/decomposition/umbrella.py)
  WPS202. Retain. A parent whose whole intent is covered by its children.
- [orchestrator/workflow/stages/decomposition/validation.py][owner-4]
  WPS202. Retain. What a `split` payload must satisfy before any child issue is created.
- [orchestrator/workflow/stages/implementing/disposition.py][owner-5]
  WPS202. Retain. What a finished dev run leaves behind, and the timeout's second chance.
- [orchestrator/workflow/stages/implementing/late_command.py](../orchestrator/workflow/stages/implementing/late_command.py)
  WPS202. Retain. The one reply a park for an authorization is ever ended by.
- [orchestrator/workflow/stages/implementing/late_consent.py](../orchestrator/workflow/stages/implementing/late_consent.py)
  WPS202. Retain. The park an adjudicated candidate with nobody behind it waits on.
- [orchestrator/workflow/stages/implementing/late_freeze.py][owner-6]
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
- [tests/support/github/models.py](../tests/support/github/models.py)
  WPS202. Retain. Shared in-memory GitHub entities include repository identity so fork and branch claims are testable.
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
- [tests/workflow/late_split/test_exemption.py](../tests/workflow/late_split/test_exemption.py)
  WPS202. Retain. Record-shape cases and their writer-based seeds cover intact, absent, and damaged exemption
  identities.
- [tests/workflow/patch_models.py](../tests/workflow/patch_models.py)
  WPS202. Retain. Typed inputs and basic mock builders for workflow test runs.
- [tests/workflow/stages/conflicts/test_replay_real_git.py](../tests/workflow/stages/conflicts/test_replay_real_git.py)
  WPS201. Retain. A conflict-stage replay decided over a real repository and real bytes.
- [tests/workflow/stages/conflicts/test_settled_round.py](../tests/workflow/stages/conflicts/test_settled_round.py)
  WPS202. Retain. The round a resolution earns when the size gate holds it off the PR.
- [tests/workflow/stages/decomposition/late_content_support.py](../tests/workflow/stages/decomposition/late_content_support.py)
  WPS202. Retain. The issue thread the late content, guidance, and revision tests read.
- [tests/workflow/stages/decomposition/late_test_support.py][owner-7]
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
- [tests/workflow/stages/implementing/test_late_receipt.py](../tests/workflow/stages/implementing/test_late_receipt.py)
  WPS202. Retain. One publication-receipt contract is tested against changed PR identity, state, branch, head, and
  lease.
- [tests/workflow/stages/implementing/test_late_transfer.py][owner-8]
  WPS202. Retain. What a rewrite of an adjudicated commit may carry, and what it may not.

[owner-1]: ../orchestrator/workflow/stages/decomposition/late_owner.py
[owner-2]: ../orchestrator/workflow/stages/decomposition/late_reply.py
[owner-3]: ../orchestrator/workflow/stages/decomposition/late_reuse.py
[owner-4]: ../orchestrator/workflow/stages/decomposition/validation.py
[owner-5]: ../orchestrator/workflow/stages/implementing/disposition.py
[owner-6]: ../orchestrator/workflow/stages/implementing/late_freeze.py
[owner-7]: ../tests/workflow/stages/decomposition/late_test_support.py
[owner-8]: ../tests/workflow/stages/implementing/test_late_transfer.py

[child-1728]: https://github.com/chippingway/orchestrator/issues/1728
[pr-1755]: https://github.com/chippingway/orchestrator/pull/1755
[child-1729]: https://github.com/chippingway/orchestrator/issues/1729
[pr-1754]: https://github.com/chippingway/orchestrator/pull/1754
[child-1730]: https://github.com/chippingway/orchestrator/issues/1730
[pr-1752]: https://github.com/chippingway/orchestrator/pull/1752
[child-1731]: https://github.com/chippingway/orchestrator/issues/1731
[pr-1749]: https://github.com/chippingway/orchestrator/pull/1749
[child-1732]: https://github.com/chippingway/orchestrator/issues/1732
[pr-1747]: https://github.com/chippingway/orchestrator/pull/1747
[child-1733]: https://github.com/chippingway/orchestrator/issues/1733
[pr-1744]: https://github.com/chippingway/orchestrator/pull/1744
[child-1734]: https://github.com/chippingway/orchestrator/issues/1734
[pr-1743]: https://github.com/chippingway/orchestrator/pull/1743
[child-1735]: https://github.com/chippingway/orchestrator/issues/1735
[pr-1740]: https://github.com/chippingway/orchestrator/pull/1740
[child-1736]: https://github.com/chippingway/orchestrator/issues/1736
[pr-1739]: https://github.com/chippingway/orchestrator/pull/1739
[child-1737]: https://github.com/chippingway/orchestrator/issues/1737
[pr-1738]: https://github.com/chippingway/orchestrator/pull/1738
