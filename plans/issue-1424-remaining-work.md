# Issue #1424: remaining work after the open children

Prepared on 2026-09-11 against `main` at `e3a0b43407fad7c95a46f1300044719dd71ecd42`.

This is a working plan for the remaining requirements of
[#1424](https://github.com/chippingway/orchestrator/issues/1424). The issue remains the authoritative requirement.
The plan covers three work packages: remove the late-park replacement exemption, restore the WPS235 default,
and complete the parent acceptance audit. It creates no GitHub issues and changes no implementation.

## Implementation record

Implementation started on 2026-09-11 from `68f8fa73` on `reduce-flake8-exclusions`, in the separate
`chipping-orchestrator-reduce-flake8-exclusions` worktree. The original checkout stays on `main`.
At that point #1737 had merged and the other nine excluded children remained open. The user requested continuing
the remaining work now; changes here preserve those children's assigned scope, and final parent closeout still
depends on their integration. Necessary caller updates will be reconciled with the owners those children produce.

Baseline validation on Python 3.13.13: Ruff and configured WPS passed; pytest reported 6216 passed, 49 skipped,
and 29578 subtests passed. The skipped tests require the optional dashboard dependencies.

- [x] Establish the worktree and passing baseline.
- [x] Remove the late-park replacement exemption.
- [ ] Restore WPS235 defaults across production and test imports.
- [ ] Record the final exemption and acceptance audit.

The late-park split preserves all 15 function bodies apart from direct owner references. Its three owners pass
all isolated WPS defaults, and the configuration removes the replacement WPS202 mapping without adding one.
Full validation: 6216 passed, 49 skipped, 29704 subtests passed; collected test identities are unchanged.

Discussion test imports: 19 oversized statements replaced with qualified support-owner reads while retaining
explicit test classes and fixtures. Ruff, WPS, and the full suite pass (6216 passed, 49 skipped); all 6265 test
identities are unchanged.

Decomposition test imports: 43 oversized statements across 39 files now use their support owners directly.
Ruff, WPS, and the full suite pass (6216 passed, 49 skipped); all 6265 test identities are unchanged.

Other test support imports: 28 oversized statements across 27 files are resolved, with Ruff, WPS, and
the full suite passing (6216 passed, 49 skipped). Test identities remain unchanged. This completes 90 of
the original 102 oversized statements; the two remaining test cases concern explicit owner/export tables.

Value, model, and export imports: all test statements and seven of the ten production statements now fit
the default limit. Theme exports retain their owner objects; worktree guard tables retain every ownership
assertion. Ruff, WPS, and all 6265 collected test identities pass unchanged (6216 passed, 49 skipped).
Three production coordinators remain.

Implementing recovery now separates authorization-command handling from measurement/restored-candidate recovery,
with the original dispatcher preserving their order. All seven function bodies are unchanged apart from owner
references. All three owners pass isolated WPS defaults; full checks pass (6216 passed, 49 skipped).

## Scope and dependencies

All ten currently tracked children were still open when this plan was prepared. Their implementation, owner moves,
test updates, documentation updates, and eleven exemption removals are excluded from this plan:

| Existing child | Work already assigned |
|---|---|
| [#1728][child-1728] | Extract process-group operations from `agents/processes.py`. |
| [#1729][child-1729] | Extract streamed hardened git execution from `git/commands.py`. |
| [#1730][child-1730] | Extract worktree selection from `git/base_sync/refresh.py`. |
| [#1731][child-1731] | Extract flat-checkout attribution from `git/worktrees/attribution.py`. |
| [#1732][child-1732] | Extract commit publication claims from `git/worktrees/claims.py`. |
| [#1733][child-1733] | Split late revision obligations and candidate reconciliation from execution. |
| [#1734][child-1734] | Extract human-reply classification from decomposition content fingerprinting. |
| [#1735][child-1735] | Extract stranded discussion checkout evidence from round execution. |
| [#1736][child-1736] | Extract recorded plan-PR terminal handling from discussion closure recovery. |
| [#1737][child-1737] | Extract transfer telemetry from implementing exemption rotation. |

Start implementation on the resulting `main` after these children merge. Refresh their status and the diagnostics
before opening follow-up work, and drop any proposed change that another merged PR has already completed.
Updating a caller to use the park owners introduced below remains necessary; repeating a child's ownership split
does not. This particularly affects the owners and tests produced by #1733 and #1734.

The report-publication automation in the separately open
[#1702](https://github.com/chippingway/orchestrator/issues/1702) is also excluded. Preparing the final audit report
does not require implementing that automation here.

## Measured starting point

The earlier four batches account for 40 completed children with merged PRs. Of the original 100 exemption pairs,
50 are absent today; the current children target another five original pairs and six subsequently added pairs.
The snapshot numbers below are planning measurements, not a permanent inventory for the documentation.

| Point | Exact file paths | Production pairs | Test pairs | Total pairs |
|---|---:|---:|---:|---:|
| Original parent baseline, `4c384cba` | 75 | 100 | 0 | 100 |
| Inspected `main`, `e3a0b434` | 112 | 95 | 39 | 134 |
| After the ten open children, projected | 102 | 84 | 39 | 123 |
| After removing the late-park replacement, projected | 101 | 83 | 39 | 122 |

These projections assume the specified removals succeed and intervening work adds no exemptions. WPS235 is
currently controlled by a global setting, so restoring its default is a separate policy improvement and earns
no file/rule-pair reduction by itself. Subsequent cleanup may reduce the projected totals further.

An isolated run using the inspected `main` lockfile, including wemake-python-styleguide 1.8.0, found exactly
134 distinct diagnostic pairs matching all 134 configured pairs. There were no stale mappings or unmapped
diagnostic pairs for WPS201, WPS202, WPS204, WPS214, WPS410, and WPS412.

The [merged audit in PR #1697](https://github.com/chippingway/orchestrator/pull/1697) identified the two acceptance
gaps addressed below. Its broader exemption classifications are evidence to refresh during closeout.

## Work package 1: remove the late-park replacement exemption

**Result:** remove `orchestrator/workflow/stages/decomposition/late_parks.py:WPS202` without introducing a
replacement exemption or changing workflow behavior.

The current owner has 15 functions and a live WPS202 diagnostic. It combines park decisions, durable state
operations, and notice delivery/recovery. Its mapping was introduced by #1521 / PR #1559; documenting an invariant
does not satisfy the parent's separate prohibition on replacement exemptions.

### Ownership and implementation

Use the following proposed boundaries, verified against the functions present at the inspected commit:

All three owners live under `orchestrator/workflow/stages/decomposition/`:

- `late_parks.py` keeps `_park`, `_park_on_spent_budget`, `_stage_park`, `_release_unsuperseded_park`,
  `_retire_park`, and `_answer_park`.
- New `late_park_state.py` owns `_stands_already`, `_stands_for`, `_stands_parked`, `_mark_replies_read`,
  and `_persist`, alongside shared park reasons, pinned-key vocabulary, and the superseded-reason set.
- New `late_park_delivery.py` owns `_release_staged_park`, `_reconcile_notice_delivery`,
  `_redeliver_park_notice`, and `_audit_retry_cap`.

1. Keep the existing `late_notice.py` representation, rendering, and lookup responsibilities. Confirm its dependency
   direction before moving helpers; it must not import either park coordinator.
2. Put shared vocabulary below its callers. The decision owner may call the state and delivery owners; delivery
   may call state. Neither extracted owner may import back through `late_parks.py`.
3. Preserve `_park` as the ordered staging, persistence, and delivery operation. Post-run callers must still
   persist their result, perform their owner guard, and release the notice in their existing order.
4. Update every direct caller, test patch target, and constant reference to the actual owner. Follow the owners
   produced by the open children. Add no re-exports or compatibility forwarding functions.
5. Keep helper visibility private and use the established literal workflow logger name in each owner that logs.
6. Update the affected module docstrings, `docs/architecture/workflow-modules.md`, and decomposition import-owner
   tests. Describe why the boundaries preserve the ordering invariant; remove the existing claim that notice
   delivery must share a module with every park decision.
7. Remove the original mapping in the same change, once every resulting owner passes the existing WPS defaults.
   Check affected callers too: adding owner imports must not create a new exemption or recreate one removed by a child.

### Behavior to preserve and verify

Use the existing decomposition recovery, notice, retry-cap, settlement, transaction, and authorization tests.
Extend them only where the move exposes an uncovered behavior boundary:

- A failed initial pinned-state write prevents notice delivery; a failed comment cannot discard a persisted result.
- A comment delivered before a failed settling write is recognized on retry without duplicate delivery.
- Redelivery preserves the handling of cancelled or absent generations and superseded versus retained parks.
- Retiring and answering parks preserve their distinct effects and do not clear an unanswered retained park.
- Consumed-comment watermarks only advance for valid values and never move backwards.
- Retry-cap audit phases, messages, labels, pinned keys, and event fields keep their existing values and ordering.

**Completion evidence:** focused behavior tests pass, import/layering checks pass, all affected owners satisfy
WPS201/WPS202/WPS214/WPS235 defaults, and the configuration diff removes one path and one pair with no additions.

## Work package 2: restore the WPS235 default

**Result:** remove `max-import-from-members = 30` from `.flake8` and pass WPS235 at its default ceiling of eight.
This implements the parent's existing no-global-limit-increase requirement. No acceptance-criterion amendment
is assumed by this plan.

### Size and initial inventory

An AST scan of the inspected source found **102 `from ... import` statements exceeding eight members across
96 files**: ten statements in nine production files and 92 statements in 87 test files. Recompute the inventory
after the open children and work package 1, then use isolated WPS235 diagnostics as the implementation gate.

The nine currently affected production files are:

- `orchestrator/observability/dashboard/theme.py`
- `orchestrator/observability/dashboard/css.py`
- `orchestrator/observability/analytics/query/rollup_reads.py`
- `orchestrator/git/worktrees/maintenance.py`
- `orchestrator/workflow/stages/decomposition/run.py`
- `orchestrator/workflow/stages/decomposition/late_transaction.py`
- `orchestrator/workflow/stages/decomposition/late_coordinator.py`
- `orchestrator/workflow/stages/discussion/handler.py`
- `orchestrator/workflow/stages/implementing/late_recovery.py`

Most affected test files are in decomposition (39 files) and discussion (19 files); the other 29 are spread
across implementing, validating, conflicts, workflow engine/shared tests, and git tests. This is a repository-wide
import cleanup whose effort should not be estimated as a one-line configuration edit.

### 2A. Bring production imports within the default

1. Classify every diagnostic by what the import exposes: values/functions from one owner, sibling owner modules,
   or an intentional existing export surface. Record the current import count and relevant API/patch contracts.
2. For wide reads of one owner's symbols, prefer a direct import of that owner and qualified attribute access.
   Preserve object identity, annotations, and caller patch behavior. Do not introduce a dependency aggregation module.
3. Preserve the dashboard theme's existing exported names, identity with their source objects, and ability to
   import without optional dashboard dependencies. Treat its export contract explicitly rather than dropping
   bindings during a mechanical import rewrite. Keep any export-binding changes compatible with repository guards.
4. For groups of more than eight sibling modules, evaluate the actual responsibilities and direct-owner imports
   together. Accept an extraction only when it produces understandable owners, preserves transition ordering,
   and satisfies both WPS201 and WPS235 without replacement waivers. Verify this boundary before committing to
   a split; lowering one count by violating the other does not complete the work.
5. Keep Ruff's import sorting and `combine-as-imports` policy. Splitting one owner's names across repeated
   `from` statements is ineffective because the sorter recombines them. Do not disable sorting, widen a limit,
   add an exact-path WPS235 waiver, or use dynamic lookup to conceal the imports.
6. Check each changed area with configured lint, isolated WPS235, and its focused behavioral and import tests.
   Update architecture inventories only where a real owner moves.

If a coordinator cannot satisfy the existing requirements without breaking its invariant, record the concrete
conflict and leave the WPS235 acceptance gap open. An undocumented policy exception must not count as completion.

### 2B. Bring test imports within the default

1. Work in bounded groups: decomposition tests, discussion tests, then the remaining test areas. Rebase on the
   resulting owners rather than repeating test moves assigned to the open children.
2. Replace oversized imports of helpers and constants with direct imports of their existing support owner and
   qualified references where appropriate. Keep support functions with the stage or domain that owns them.
3. Preserve pytest fixture discovery, imported test-class collection, unittest mixins, and module-level entry
   points. Imported fixtures and mixins need explicit examination; a qualified helper call alone does not preserve
   every test discovery contract.
4. Preserve mock targets, hermetic agent/GitHub/git boundaries, and independent assertions. Avoid new fixture
   facades, copied helpers, global injection, or new exemptions to make the imports fit.
5. Compare collected test identities before and after each group, explain any intentional move, and run the
   affected tests. Existing tests should continue exercising the same behaviors without redundant new cases.

### 2C. Restore configuration and document the resulting policy

1. Once the complete isolated WPS235 run is clean, remove the setting and its supporting commentary from `.flake8`.
   Do not introduce any replacement global or per-file suppression.
2. Update `docs/configuration/operations.md` where it describes the raised ceiling. Preserve the stable exact-path,
   live-diagnostic, direct-owner, and no-replacement policies already documented there.
3. Update any stale rationale in `pyproject.toml` or existing repository tests only where the resulting import
   behavior requires it. Preserve the established Ruff rule selection and sorting checks.
4. Run configured WPS and Ruff across both trees, the complete test suite, and import/export/layering checks.
   Record the actual WPS235 before/after diagnostic counts and any independent exemption removals in the PR report.

**Completion evidence:** no raised WPS threshold remains, isolated WPS235 reports zero violations, the test suite
retains its coverage, and the work introduces no new WPS mapping, source suppression, or dependency facade.

## Work package 3: final exemption audit and parent closeout

**Result:** give every parent acceptance criterion an evidenced disposition at the final merged commit.
Run this after both work packages and all currently open children have landed.

1. Record the exact audited SHA, lockfile/tool versions, and interpreter. Recount paths and distinct file/rule
   pairs separately for production and tests.
2. Compare configured pairs with isolated diagnostics for every configured WPS code. Include WPS204, which was
   added after the original baseline, and check WPS235 separately at its default.
3. Remove any stale path or rule discovered at that commit. Investigate any diagnostic with no matching mapping;
   do not fill the mismatch by automatically adding an exemption.
4. Refresh the retain-or-refactor decision for every remaining structural exemption against its current owner
   and module rationale. Reuse valid evidence from #1697 and later PRs. A real new responsibility boundary or an
   unjustified replacement is a bounded follow-up; a live diagnostic alone is not a requirement to split a module.
5. Preserve all eight intentional package API paths and their sixteen WPS410/WPS412 pairs. After the projected
   park cleanup, the other 106 pairs need evidenced dispositions, not an automatic queue of 106 refactors.
6. Verify that no child or follow-up introduced a replacement WPS201/WPS202/WPS214 mapping, widened a global
   threshold, introduced a glob or source-level WPS suppression, or changed a live workflow contract.
7. Prepare a parent checklist that links each acceptance criterion to its implementing PR, justified retention,
   or a concrete unresolved gap. Report the original 75-path/100-pair baseline, the post-child baseline, and the
   actual final counts; distinguish new feature exemptions from removals delivered by this effort.
8. Publish the final report through the available issue/PR workflow and reconcile the parent's stale checklist
   as part of implementation closeout. Mark the parent complete only when every acceptance gap is resolved.

Counts belong in the final report. Durable configuration and architecture documentation should describe the
policy and ownership invariants without embedding the changing inventory.

## Delivery order and validation

Suggested sequence:

1. Wait for the existing children to merge and refresh the baseline.
2. Deliver the late-park split with its mapping removal and behavior coverage in one reviewable change.
3. Deliver WPS235 production changes, then test-area changes in bounded PRs. The existing configured lint gate
   stays green throughout; use isolated WPS235 to measure each group's progress toward the default.
4. Remove the global override and update its policy documentation once all affected imports comply.
5. Run the final audit and reconcile the parent report and checklist.

Before implementation, follow [the develop skill](../.agents/skills/develop/SKILL.md) and read the authoritative
[state-machine](../docs/state-machine.md) and [workflow](../docs/workflow.md) references for the park changes.
Each owner-moving change carries its own test and documentation updates.

Run focused tests during implementation and the following complete checks for each delivery as required by
the repository, using the locked environment:

```sh
uv sync --locked
uv run ruff check orchestrator tests
uv run flake8 orchestrator tests --select=WPS
uv run pytest tests
git diff --check origin/main...HEAD
```

The final structural inventory audit uses:

```sh
uv run flake8 --isolated orchestrator tests \
  --select=WPS201,WPS202,WPS204,WPS214,WPS410,WPS412
uv run flake8 --isolated orchestrator tests --select=WPS235
```

The first isolated command is expected to report retained violations and exit nonzero. Parse its output into
distinct path/rule pairs and compare those with `.flake8`; raw diagnostic-line counts are not exemption counts.
The WPS235 command must report no violations. Expand the inventory selection if additional WPS codes are
configured by the time the final audit runs.

## Completion checklist

- [ ] No refactor or exemption removal assigned to an open child was duplicated or credited to this plan.
- [ ] The late-park replacement mapping is removed, with no replacement waiver and all ordering contracts preserved.
- [ ] WPS235 passes at its default ceiling of eight and the global override is removed.
- [ ] Every retained exemption has both a live diagnostic and a current architectural justification.
- [ ] The intentional sixteen package API pairs remain exact-path.
- [ ] Required lint, behavior, test discovery, import/export, layering, and whitespace checks pass.
- [ ] The final report names its audited commit, gives reproducible counts, and resolves every parent criterion.

## Evidence

- [Parent requirements and decomposition history](https://github.com/chippingway/orchestrator/issues/1424)
- [Latest batch of ten children](https://github.com/chippingway/orchestrator/issues/1424#issuecomment-5630577390)
- [Merged audit and unresolved acceptance gaps](https://github.com/chippingway/orchestrator/pull/1697)
- [Original exemption configuration][original-config]
- [Inspected exemption configuration][inspected-config]
- [Inspected late-park owner][inspected-parks]

[child-1728]: https://github.com/chippingway/orchestrator/issues/1728
[child-1729]: https://github.com/chippingway/orchestrator/issues/1729
[child-1730]: https://github.com/chippingway/orchestrator/issues/1730
[child-1731]: https://github.com/chippingway/orchestrator/issues/1731
[child-1732]: https://github.com/chippingway/orchestrator/issues/1732
[child-1733]: https://github.com/chippingway/orchestrator/issues/1733
[child-1734]: https://github.com/chippingway/orchestrator/issues/1734
[child-1735]: https://github.com/chippingway/orchestrator/issues/1735
[child-1736]: https://github.com/chippingway/orchestrator/issues/1736
[child-1737]: https://github.com/chippingway/orchestrator/issues/1737
[original-config]:
  https://github.com/chippingway/orchestrator/blob/4c384cbad5b568e383fca115688a739551287e06/.flake8
[inspected-config]:
  https://github.com/chippingway/orchestrator/blob/e3a0b43407fad7c95a46f1300044719dd71ecd42/.flake8
[inspected-parks]:
  https://github.com/chippingway/orchestrator/blob/e3a0b43407fad7c95a46f1300044719dd71ecd42/orchestrator/workflow/stages/decomposition/late_parks.py
