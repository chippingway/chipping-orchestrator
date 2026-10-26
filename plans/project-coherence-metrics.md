# Project coherence metrics and analytics integration

Status: proposed working plan, 2026-10-26. No collector, events, or dashboard changes are implemented by this document.
Repository inspection baseline: `507cf50bd98523fd58e8b6c8a8c65826271a313a`.

This is a human working note. The [contracts register](../docs/contracts.md) and the linked specifications remain
authoritative. Implementation must update the relevant specifications and checks with any changed guarantee.

## Objective

Detect whether comparable changes increasingly require understanding more mechanisms, touching more unrelated areas,
and repairing more interactions. Use that evidence to choose and evaluate simplification work before delivery stalls.

[Maevyn's decoherence essay](https://maevyn.codes/decoherence) motivates the concern: individually reasonable changes
can accumulate incompatible models. It does not establish a validated metric, an inevitable failure curve, or evidence
that this repository is approaching collapse. Treat coherence as a hypothesis to investigate through several signals.

Build a small measurement panel in the existing analytics stack. Start with change breadth, dependency reach,
co-change evidence, and unfinished policy transitions. Relate them to execution effort and rework as attribution
improves. Do not combine them into a single coherence score or use them as automatic workflow gates.

## Research basis and limits

| Evidence | Implication for this project |
| --- | --- |
| [SPACE](https://www.microsoft.com/en-us/research/publication/the-space-of-developer-productivity-theres-more-to-it-than-you-think/) treats productivity as multidimensional. | Use a panel; activity, volume, and speed alone cannot establish coherence. |
| [MacCormack, Rusnak, and Baldwin](https://pubsonline.informs.org/doi/10.1287/mnsc.1060.0552) measure architectural coupling through dependency matrices and propagation cost. | Measure potential change exposure, while keeping graph extraction assumptions visible. |
| [SEI's propagation-cost study](https://www.sei.cmu.edu/documents/1437/2013_021_001_88727.pdf) examines limitations across architectural transformations. | A normalized coupling number can move misleadingly when the system's size or structure changes. |
| [Decoupling Level](https://ranmo.github.io/papers/icse2016-DL.pdf) investigates architectural maintainability across many systems. | Structural metrics are useful candidates, but results do not validate an equivalent Python coherence score. Defer this more involved measure. |
| [Hassan and Holt](https://research.cs.queensu.ca/home/ahmed/home/pubs/wcre2003.pdf) study the distribution of modifications over time. | Change dispersion can reveal trends; activity spread and entropy are not direct evidence of semantic inconsistency. |
| [Zimmermann and colleagues](https://www.cs.kent.edu/~jmaletic/cs63902/Papers/Zimmermann04.pdf) mine version histories for recurring change relationships. | Co-change can expose relationships absent from an import graph; every surprising relationship still needs interpretation. |
| [SEI's architectural-debt case study](https://www.sei.cmu.edu/blog/a-case-study-in-locating-the-architectural-roots-of-technical-debt/) connects structural problems and maintenance history. | Prioritize frequently changed, costly relationships over isolated structural warnings. |
| [Research on refining SZZ](https://link.springer.com/article/10.1007/s10664-024-10511-2) documents difficulties identifying bug-inducing changes. | Use reviewed corrective links; commit prefixes and blame are insufficient causal attribution. |
| [DORA's delivery metrics](https://dora.dev/guides/dora-metrics/) separate delivery throughput and instability. | Pair structural signals with outcomes. Issue and PR events are not deployment events and must not be presented as DORA measurements. |
| [DevEx](https://www.michaelagreiler.com/wp-content/uploads/2024/06/DevEx-WhatDrivesProductivity.pdf) combines system evidence with developer feedback. | Validate whether people can find and explain the governing model; token consumption cannot substitute for that evidence. |

The proposal combines established techniques with project-specific hypotheses. In particular, counting competing policy
mechanisms is a custom diagnostic, not an externally validated coherence metric. Correlation with rework would support
its usefulness here, without proving architectural causation.

### Recent research scan: October 2024–October 2026

Searched on 2026-10-26 for work published between 2024-10-26 and 2026-10-26 on agentic software engineering,
long-term maintainability, architectural degradation, review quality, and evaluation cost. This is a targeted selection
of relevant primary sources, not a systematic literature review. Dates below distinguish the original paper from the
version inspected; a recent publication can analyze much older tools and repository activity. The foundational work
above remains relevant even where it predates this window.

There is now direct research on this direction. The strongest additions are measurements across successive changes to
an agent's own code, explicit structural checks alongside functional tests, and evaluation of the complete development
and review process. None of the sources below establishes a generally validated project-coherence score.

#### Benchmarks and measurable constructs

| Research and date | What it measures | Use here and limits |
| --- | --- | --- |
| [SlopCodeBench — Orlanski et al.](https://arxiv.org/html/2603.24755v2), first posted 2026-03-25; inspected v2, 2026-05-07; preprint. | Agents extend their own implementations across 36 problems and 196 checkpoints. Measures functional success, concentration of complexity, and redundant/duplicated code. | Pilot M7 below alongside M1–M2 and later rework. These are structural proxies, not semantic coherence. Its evolving tasks and comparison repositories are not a randomized comparison of equivalent human and agent work. Earlier summaries describe a smaller benchmark; do not mix versions. |
| [SWE-Milestone — Deng et al.](https://arxiv.org/html/2603.13428v4), first posted 2026-03-13; inspected v4, 2026-07-21; ICML 2026. | Carries agent changes through 98 dependent milestones in seven repositories. Separates newly satisfied tests from broken existing tests, with continuous and independent-task evaluation settings. | Basis for M8 and a sequential validation experiment. Keep progress and regressions separate rather than adopting its combined score. Results depend on test coverage and the reconstructed milestone sequence. |
| [SWE-CI — Chen et al.](https://arxiv.org/html/2603.03823v4), first posted 2026-03-04; inspected v4, 2026-04-01; preprint. | Uses 100 repository evolution tasks and an architect/programmer loop. EvoScore weights a trajectory of normalized test progress toward a target revision; regression frequency and magnitude are also analyzed. | Supports observing the whole sequence, including setbacks. Its test-derived score and agent-generated intermediate requirements do not independently establish architectural quality. Do not relabel ordinary CI pass rates as EvoScore. |
| [Needle in the Repo (NITR) — Zhu et al.](https://arxiv.org/html/2603.27745v1), 2026-03-29; preprint. | Pairs functional tests with structural checks in 21 C++ probes covering nine maintainability dimensions. Some outputs satisfy behavior while violating the targeted structure. | Make a small subset of M4 observations repeatable through checks for this repository's documented ownership and dependency rules. The small C++ benchmark is not validation of a Python-wide metric; each local check needs an explicit contract and reviewed applicability. |
| [Spread–Novelty–Centrality (SNC) profile — Shayanfar et al.](https://arxiv.org/html/2609.01271v1), 2026-09-01; preprint. | Characterizes reference patches using edit dispersion, addition/deletion balance, dependency position, history, and complexity; studies five benchmarks and 14,922 agent trajectories. | Strengthens M1–M2 and cohort design: a bug/feature label alone is weak scope control. Reference-patch measurements are retrospective. This repository has no independent gold patch for ordinary work, so observed agent footprint must not masquerade as initial task difficulty. |
| [CRBugBench — Yang et al.](https://arxiv.org/html/2610.13668v1), 2026-10-09; preprint; and [GitHub ReviewBench](https://github.blog/ai-and-ml/reviewbench-an-open-benchmark-for-ai-code-review/), 2026-10-05; industry research preview. | CRBugBench measures discovery of known bugs within a limited comment budget on public and proprietary PRs. ReviewBench measures precision and recall against reviewed findings, with severity/category slices and separate treatment of newly discovered findings. | Basis for M9: review rounds and approval rates cannot show whether reviewers detect defects. Known findings are incomplete ground truth; validate novel findings and preserve a common reference set for comparisons. Vendor benchmarks and model judges require local calibration. |

#### Field evidence and evaluation practice

| Research and date | Finding relevant to measurement | Use here and limits |
| --- | --- | --- |
| [AI IDEs or Autonomous Agents? — Agarwal, He, and Vasilescu](https://arxiv.org/html/2601.13597v2), first posted 2026-01-20; inspected v2, 2026-01-27; MSR 2026. | A matched longitudinal study measures repository activity, static-analysis warnings, duplication, and cognitive complexity. Estimated velocity effects differ with prior AI-tool exposure, while quality indicators can worsen. | Track outcomes and structure together, and record prior exposure where known. Adoption is observational and imperfectly detected; aggregate warning counts and commits are neither direct maintenance cost nor proof of an effect in this repository. |
| [Mining Architectural Quality Under Agentic AI Adoption — Larsen and Moghaddam](https://arxiv.org/html/2606.13298v1), 2026-06-11; accepted manuscript, SEAA 2026. | In 151 Java repositories, estimated smell density falls while raw smell counts are essentially unchanged and code volume grows. | Direct support for displaying every normalized measure's numerator and denominator, including M2. Java-specific tooling, adoption proxies, missing repositories, and sensitivity to sample filtering limit generalization. The result does not establish either architectural improvement or inevitable degradation. |
| [Not All Agents Are Equal — Kraishan](https://arxiv.org/html/2609.17598v1), 2026-09-12; preprint. | Studies 37,623 agent/human PRs, with maintenance follow-up, review activity, and differences between agent products. The contribution window is December 2024–July 2025. | Supports M5–M6 follow-up and provenance, not current vendor rankings. Follow-up edits concern the most-changed file and reverts are detected from messages; these are candidate signals, not verified corrective links. Preserve the stronger attribution rule already specified in M5. |
| [METR developer-productivity RCT — Becker et al.](https://arxiv.org/abs/2507.09089v2), July 2025; and [experiment-design update](https://metr.org/blog/2026-02-24-uplift-update/), 2026-02-24. | The original randomized study of 16 experienced developers and 246 tasks found 19% longer completion time with early-2025 tools despite perceived speedups. The follow-up warns that participant/task selection and concurrent agent use make its newer time estimates unreliable. | Measure human effort, agent effort, and elapsed time separately. Record sampling and concurrency; do not generalize the original slowdown to current autonomous agents or treat self-reported speedup as measured benefit. |
| [Holistic Agent Leaderboard — Kapoor et al.](https://arxiv.org/abs/2510.11977v1), 2025-10-13; [ICLR 2026 project](https://hal.cs.princeton.edu/). | Standardizes evaluation across models, agent scaffolds, and benchmarks, including software engineering, while recording cost and execution traces. | Extend M6 with cost across all attempts and compare success/cost trade-offs under recorded budgets. A model name alone does not identify the evaluated system; harness, prompts, tool access, and reasoning settings matter. Public-benchmark performance is not production productivity. |
| [How Do Coding Agents Optimize Software and Report Performance Validation? — Peng et al.](https://arxiv.org/html/2610.03969v1), 2026-10-02; preprint extending an MSR 2026 study. | Compares 1,130 agent and 1,130 human performance PRs. About half of PRs reporting validation omit a quantitative performance metric; resource trade-offs are seldom quantified. | For simplification or performance claims, retain measured baselines, outcomes, and costs. The study analyzes reported evidence and does not reproduce the claimed improvements: a report saying that a benchmark ran is not execution evidence. |

These studies motivate the extensions below; adopting them locally is a proposal, not a reproduced research result.
Retain the small initial panel. Add more expensive structural, test-transition, and review-quality measurements only
after a local pilot shows useful evidence beyond M1–M6. Public datasets, preprints, and leaderboards should supply
methods and comparison tasks, not thresholds or model rankings imported into the workflow.

## Repository evidence to use for calibration

The October 20 cleanup in PRs #2324 and #2326 removed dormant recovery and finish machinery built around a second writer
inside an exclusive issue claim. [C-05](../docs/contracts.md#c-05-writer-claims-and-artifact-maintenance) excludes that
model. This is a useful example of reducing conceptual inconsistency that line counts or coupling alone may miss.

A preliminary AST import-graph experiment produced the following observations. It included production Python files,
including package initializers, and imports inside functions and type guards. It did not resolve dynamic imports.

| Snapshot | Modules | Import edges | Propagation cost, including self | Mean other transitive dependents |
| --- | ---: | ---: | ---: | ---: |
| Before the cleanup interval: `1cac599635b190debfff67d7bad9e920ed0f82cf` | 971 | 5,927 | 8.552% | 82.04 |
| End of the interval: `6a15cfe6ce9cd64fc30bcd4882afa6adc8899d09` | 959 | 5,768 | 8.563% | 81.12 |
| Inspection baseline: `507cf50bd98523fd58e8b6c8a8c65826271a313a` | 978 | 5,999 | 8.668% | 83.77 |

Mean reach fell across the cleanup interval while normalized propagation cost slightly rose. The interval includes
other changes, so this is not an isolated causal experiment. These exploratory values must be reproduced by the
versioned collector before becoming dashboard baselines; they do not establish a trend toward failure.

Also use the documentation/review loop discussed in issue #2379 as a rework case. Distinguish unnecessary repetition
from required verification and legitimate changes in requirements. Evaluate any proposed fix only after its integration
and actual subsequent runs; an unused helper or an open PR does not establish changed runtime behavior.

## Measurement definitions

### Shared units and comparison rules

- A change is a confirmed merged implementation PR, with explicit base and final revisions. Define merge, squash, and
  rebase handling consistently so unrelated base updates do not become the PR's footprint. Exclude synthetic merge
  commits as additional changes.
- Keep PR-level observations and a separate root-work-item view that unions the footprints of related changes and sums
  their execution effort. Splitting an issue must not make the whole task appear narrower. Do not count both a parent
  umbrella and its children as independent deliveries.
- Map source files to a small set of stable architectural ownership domains using existing architecture documentation.
  Examples include report publication, verification, base synchronization, stage routing, and analytics. Record unmapped
  files explicitly. Version the mapping and preserve rename lineage.
- Measure production, test, and documentation footprints separately. Required test and contract updates must not be
  interpreted as harmful production coupling. Label mechanical refactors, migrations, and generated changes separately.
- Compare tasks by initial scope and work category, then by available backend, model, agent specification, verification
  configuration, and orchestrator version. Record classification provenance and unknown values.
- Record observed human-only, assisted, or autonomous execution and prior AI-tool exposure where evidence supports
  them. A configuration file or an absent agent signature does not establish actual usage or a human-only baseline.
  Record the agent harness/version and relevant prompt, tool-access, and budget settings alongside model identity.
- Display raw numerators and denominators with normalized structural measures. Code growth can lower a density without
  removing any problem. Keep within-project trends distinct from comparisons between unrelated repositories.
- Show both calendar time and cumulative merged changes. Start with a rolling window of roughly 30 comparable changes
  and a longer calendar view, such as 90 days; display sample size and coverage. These are starting settings to calibrate.

### M1. Change breadth

For change `c`, let `D(c)` be its affected production ownership domains:

```text
breadth(c) = |D(c)|
```

Show the median and p90 within comparable cohorts, the affected domains, and the root-work-item union. Track file and
line counts as context, not targets. A rise in breadth for similar tasks suggests growing coordination or understanding
cost; a planned cross-cutting migration may explain the same pattern.

The domain view is primary because splitting one file into many helpers should not automatically worsen this metric.
Entropy of changed domains may be explored later, but broad project activity alone is not a warning.

The SNC study suggests a retrospective companion view: edit dispersion, additions as a share of additions plus
deletions, and the dependency position of affected modules. These describe different change demands; none is a target
to minimize. Keep final-patch descriptors separate from scope recorded before work begins.

### M2. Dependency reach and frequently changed dependencies

Build a directed graph from importer to dependency. For module `m`, define `dependents(m)` as the distinct other modules
that can transitively reach it. This is potential exposure if `m` changes, not a prediction that every dependent needs
an edit.

```text
reach(m) = |dependents(m)|
propagation_cost = (N + sum(reach(m) for all m)) / N²
```

For a nonempty graph, report module count `N`, mean and p90 reach, and propagation cost together. Empty graphs have an
unknown/not-applicable ratio. List modules with both high reach and frequent recent changes, with their consumers and
supporting PRs. A stable shared utility is not automatically a problem.

Distinguish ordinary, deferred, and type-only edges; publish the selected edge policy. Report parse failures, unresolved
imports, and detected dynamic import sites. A dynamic import site count is not a count of missing edges. Keep source
scope and extraction policy fixed across a displayed comparison. Read source as data; never import application modules
to discover dependencies.

### M3. Unexpected co-change

For an eligible window of `W` changes, let `n(A)` count changes touching domain `A`, and `n(A,B)` count those touching both:

```text
confidence(A → B) = n(A,B) / n(A)
lift(A → B) = confidence(A → B) / (n(B) / W)
```

Show support, confidence, lift, and the contributing changes. Require meaningful support before ranking a pair; five
co-changes is a provisional exploration setting, not a validated threshold. Compute only with nonzero denominators.

Review cross-domain candidates against intended dependencies. Classify them as expected, temporary migration,
unreviewed, or confirmed undesirable coupling. Code/test/documentation pairs have their own views. Absence of a static
dependency is not proof of a defect, and a high lift based on rare events is not enough to prioritize work.

### M4. Competing policy mechanisms and unfinished transitions

Start with a few policy families already governed by contracts: pinned-state writes, report binding/publication,
verification/readiness, session identity, and artifact ownership. For each reviewed observation, record:

- The intended model, its authoritative contract, and concrete code or issue evidence.
- Alternative mechanisms and their current consumers, with classification and review date.
- Whether coexistence is intentional, a planned transition, dormant prerequisite work, or a confirmed contradiction.
- The introduction and retirement evidence, remaining consumers, and age in days and merged changes when known.

Display extra mechanisms awaiting retirement, remaining consumers, and changes touching a family during its transition.
Separate observed age from a verified introduction date. Missing retirement evidence is not proof that a path is still
live; a path removal is not proof that every consumer has migrated.

This is the closest measure of the essay's semantic concern and requires human interpretation. Reuse contracts and
issue evidence; do not create another authoritative policy registry or let an LLM's unsupported rating determine status.

Following the NITR approach, pilot explicit structural checks for a few existing contracts where the rule is executable.
Record the exact revision, applicable checks, violations, and unassessed cases separately from functional-test results.
A passing structural check covers its stated rule, not the whole policy family or project coherence.

### M5. Rework

Keep two outcomes separate:

1. Within-workflow repetition: additional implementation, review, report, or documentation runs under unchanged
   requirements, classified by observed purpose and cause. Show the affected-work-item fraction and repeated execution
   time. Repetition without enough attribution remains an unclassified observation.
2. Post-merge correction: the fraction of mature merged changes with an explicitly linked corrective change within a
   chosen horizon, initially 28 days. Also show corrective execution effort when attributable.

For the second measure, a change enters the denominator only after its full follow-up horizon is observed. Show newer
changes separately as incomplete follow-up. Missing corrective links limit coverage; they do not establish no rework.
Requirement changes, external branch updates, provider failures, and quota interruptions need separate categories.
Do not infer causation from `fix:` subjects, retry maxima, repeated polling, or blame alone.

If enough history exists, compare the initial 28-day correction horizon with a separate 90-day view. Subsequent edits
and revert-like messages may nominate cases for review; they do not count as corrections until their relationship is
confirmed. Publish each horizon's own mature denominator and attribution coverage.

### M6. Delivery effort and elapsed time

Show median and p90 per comparable work item for total agent execution seconds, invocation count by role and purpose,
time to first confirmed readiness, time to confirmed merge, and priced cost with pricing coverage. Show unfinished
work's age and accumulated effort beside completed work to avoid hiding stalled tasks.

Count `agent_exit.duration_s` once per observed run. Never add enclosing `stage_evaluation` durations to those runs;
that would double count overlapping work. Agent execution time is neither human effort nor wall-clock delivery time.
Separate human waiting only where entry and exit evidence supports the interval. Sessions may span multiple invocations;
a session ID is not a unique run ID. Do not use dollars or tokens per line of code as a coherence measure.

For a fixed cohort of started root work items and a stated observation cutoff, also report total compute cost divided
by the number reaching verified readiness. Include spend on failed, abandoned, and unfinished work in that cohort;
show those outcomes and their ages beside the ratio. If any included spend is unpriced, show the known subtotal and
coverage rather than a complete-cost ratio. A zero-success denominator is not applicable. Human review/intervention
minutes need their own observations; comment counts and review latency cannot supply them. Concurrent agent durations
may legitimately sum above elapsed time, while overlapping human-attention intervals must not be counted twice.

### Research-informed metric pilots

These candidates extend the panel only after validation in Phase 3. Their names and definitions are provisional;
no benchmark execution, new analysis dependency, or additional runtime event family is implied by this research update.

**M7 candidate: concentration of complexity and redundancy.**
[SlopCodeBench v2](https://arxiv.org/html/2603.24755v2#S2.SS3) defines:

```text
mass(f) = cyclomatic_complexity(f) * sqrt(source_lines(f))
erosion = sum(mass(f) for f with cyclomatic_complexity(f) > 10) / sum(mass(f) for all f)
verbosity = count(distinct lines flagged by redundancy rules or clone detection) / analyzed_lines
```

Keep the two measures separate. Pin extractor semantics, rule sets, and scope; display raw masses, flagged-line counts,
denominators, and example locations. Empty denominators are not applicable. The cutoff and redundancy rules are
benchmark choices, not repository quality limits. Review legitimate defensive code and extraction/file-split effects.
Compare trajectories with later M5–M6 outcomes before promoting either measure; a local approximation must have a
different definition/version rather than claim to reproduce the paper's metric.

**M8 candidate: progress and retained behavior across changes.** Adapt
[SWE-Milestone's](https://arxiv.org/html/2603.13428v4#S5.SS1) separation of new work and regressions, with SWE-CI
motivating trajectory views:

```text
new_behavior_completion = passing required-new tests / eligible required-new tests
retained_behavior = still-passing required-existing tests / eligible required-existing tests
```

Eligible new tests fail on the step's input revision and must pass after the requested change; eligible existing tests
pass on that input and must remain passing. Carry inherited failures separately so they cannot disappear from the
trajectory when the next step starts. Record broken-test counts and full-task success separately.
Pin the requirements, test identities, baseline/head,
environment, and evaluation budget. Validate baseline behavior and distinguish infrastructure failures, flaky tests,
skips, and unknown results from code regressions. A changed test suite needs explicit reconciliation; deleting tests
cannot improve retention. Empty eligible sets are not applicable. These are coverage-dependent local measures, not
SWE-Milestone's combined score or SWE-CI's EvoScore. Start with controlled offline sequences; ordinary historic pass/fail
events cannot reconstruct test transitions. The static collector must continue to read code as data.

**M9 candidate: review usefulness and missed known defects.** Following
[CRBugBench](https://arxiv.org/html/2610.13668v1) and
[ReviewBench](https://github.blog/ai-and-ml/reviewbench-an-open-benchmark-for-ai-code-review/), measure on a
maintainer-adjudicated sample:

```text
finding_precision = confirmed actionable findings / adjudicated findings
known_defect_recall = known defects correctly identified / eligible known defects
```

Deduplicate findings about the same defect, retain unresolved judgments, and slice by severity and review budget.
Freeze a common reference set when comparing configurations; separately adjudicate valid new discoveries. Report
annotation coverage and disagreement. Recall is limited to known defects, and a developer applying a suggestion is
not proof that it was correct. Empty denominators are not applicable. Use these observations with M5 repetition and
M6 human effort: fewer review rounds are beneficial only if review effectiveness is preserved.

## Existing analytics fit

The [observability overview](../docs/observability.md), [database reference](../docs/observability/analytics-database.md),
and [dashboard reference](../docs/observability/analytics-dashboard.md) describe the current pipeline:

- Runtime producers append JSONL. A separate sync command replays records into Postgres; the polling tick does not
  depend on the database.
- `analytics_events` promotes known fields and preserves additional fields in `extras JSONB`. Its content hash deduplicates
  exact records. The daily rollup loses event order, identities, and distributions needed for several proposed measures.
- Existing `agent_exit` records provide execution duration, usage, model/session evidence, and review/retry context.
  They do not consistently provide the requirements revision, run correlation, PR head, and purpose needed to explain
  every repetition. `review_verdict` and `pr_merged` are currently audit events, not baseline analytics events.
- The typed query layer is separate from Streamlit. Dashboard reads are cached and staged through the existing page
  composition. Optional visualization imports must remain optional.

Proposed flow:

```text
Immutable Git revisions + available PR metadata + reviewed policy observations
                                  |
                         Offline coherence collector
                                  |
                           Separate coherence.jsonl
                                  |
Runtime analytics.jsonl ---- existing JSONL sync ---- analytics_events + extras
                                                               |
                                                    Typed coherence queries
                                                               |
                                                    Existing Streamlit dashboard
```

### Collector and event records

Add a small offline collector under the analytics ownership boundary, provisionally
`orchestrator/observability/analytics/coherence/`. Keep execution outside the polling tick. Use Git and the Python
standard library for the first extractor; this plan requires no new dependency, service, or framework.

Write a separate `coherence.jsonl` with one collector writer. The existing analytics sink's lock is process-local;
an independent collector must not append to the runtime file while its retention code can rewrite it. Replay the new
file through the existing sync's `--log-path` input. Define collector output retention separately from runtime retention.

Introduce three event families, with names finalized alongside their event specification:

| Proposed event | Scope and payload |
| --- | --- |
| `repo_coherence_snapshot` | Repository scope, `issue: 0`; source revision/tree, measurement versions, graph summaries, coverage, and bounded hotspot evidence. |
| `change_footprint` | Exact PR/change identity, base/final revisions, merge time, known issue/root relationships, production/test/doc domains, and category provenance. |
| `policy_observation` | Policy family, reviewed classification, mechanisms/consumers, evidence references, observation time, and introduction/retirement evidence when known. |

Retain the current required envelope (`ts`, `repo`, `issue`, `event`). Use explicit scope and attribution status;
unattributed changes use `issue: 0` without inventing an issue relationship. Do not attach repository observations to a
real issue just to make them appear in an issue-filtered chart. Store bounded evidence references, not full source,
prompts, trajectories, or an unbounded graph in every database row.

Every measurement needs an analyzer version, metric-definition version, scope/mapping hash, extraction settings, source
identity, and stable logical measurement ID. For Git-derived measurements, identity includes immutable revisions; for
policy observations, it includes the observation/evidence revision. Keep a small explicit record-schema version.

Separate collection time `ts` from source/effective time. Historical footprint charts use confirmed merge time;
snapshots use a documented source-order/time policy. A backfill collected today must not appear as today's historical
activity. Unknown historical times stay unknown.

The existing content hash does not deduplicate equivalent recomputations with new timestamps. Queries must select one
valid observation per logical measurement ID, using an explicit deterministic selection rule, and expose conflicting
payloads instead of counting both. Never blend different definitions into one trend without a compatible backfill.

Initially use `extras` without DDL. Add indexes or derived materializations only after representative query profiling.

### Queries and dashboard

Add typed reads through the existing [query package](../orchestrator/observability/analytics/query/), following strict
row-shape and unknown-value handling. Read base events for distributions, logical deduplication, and evidence joins;
the daily rollup cannot reconstruct them. Preserve the dependency direction in the
[observability architecture](../docs/architecture/observability-modules.md).

Add a project-coherence section through the existing dashboard composition, loading expensive reads in the later wave
or on demand. It should contain:

- Trends for the metric families with baseline comparison, sample size, scope, version, and coverage.
- A table of frequently changed dependencies with large reach, and a co-change matrix with supporting PR links.
- Unfinished policy transitions with remaining consumers and age.
- Work-item drilldowns connecting footprints, repeated runs, known waiting intervals, and reviewed corrections.
- Visible gaps for missing identity, incomplete follow-up, unresolved imports, and unpriced runs.

Repository metrics use repository/time scope even when the page has issue or stage filters; label that scope clearly.
Use source/effective time for historical coherence views. Issue drilldowns show related observations while retaining
repository context.

Audit existing general event reads before adding the families. Repository observations and backfill timestamps must
not inflate issue counts, change runtime activity rankings, or become deliveries. Preserve existing KPI meaning with
explicit event/scope selection. An event-volume view may count the new families only when clearly presented as such.

### Runtime attribution improvements

After the static panel works, add missing context to existing run observations where producers actually know it:
requirements revision, PR/head identity, role/purpose, orchestrator/configuration identity, and run correlation. Reuse
the existing budget reservation identity when applicable rather than introducing another durable workflow ledger.

Selectively mirror or normalize confirmed review verdict and merge observations into analytics. Define evidence for
first readiness and, if needed, park resolution; park entry alone does not establish waiting duration. Avoid bulk audit
replay that duplicates families already written to both sinks. Historical records lacking these fields remain unknown.
Second-resolution timestamps and ingestion order alone cannot establish every historical event sequence.

## Delivery sequence and acceptance criteria

These are implementation phases, not sized issues or a decomposition manifest. Apply the repository's development and
decomposition instructions when turning an accepted phase into implementation work.

### Phase 1 — Definitions, reproducible collection, and first dashboard panel

1. Freeze the initial source scope, ownership map, PR footprint rule, cohort categories, and versioned record shapes.
2. Implement immutable Git collection, JSONL output, logical deduplication, and coverage reporting.
3. Backfill six to eight weeks where history and metadata are available. Mark gaps; do not infer unavailable PR or
   issue relationships from ambiguous commit text.
4. Add breadth, dependency reach, co-change evidence, and a small reviewed set of policy transitions to the dashboard.
5. Reproduce the exploratory snapshots and review the October cleanup against all four signals.

Accept when repeated collection leaves the displayed sample count unchanged, every plotted observation has source and
version provenance, and a maintainer can follow a warning to its affected domains and supporting changes. Existing
analytics KPIs must retain their documented meaning. If a source cannot support a metric, the panel must say so.

### Phase 2 — Outcome attribution

1. Present existing execution effort and incomplete work with current coverage limits.
2. Add the producer-known correlation fields and selected review/merge/readiness observations.
3. Introduce classified repetition and reviewed post-merge corrections, with mature follow-up denominators.
4. Compare the documentation/review loop before and after an integrated change, separating required verification,
   requirement changes, and provider interruptions.

Accept when a sample of work items reconciles to observed runs and confirmed PR outcomes without duplicated execution
time, synthetic session/run identity, or guessed causes. Expose unattributed cases as a separate group.

### Phase 3 — Prospective validation and simplification decisions

Collect several weeks of subsequent outcomes; extend the window if samples are small. Use structural measurements from
the pre-work base revision to examine later effort and corrections. Compare against a simple baseline using task type
and initial scope. Use nonoverlapping evaluation windows and group related child changes to avoid treating them as
independent samples. Post-work footprint is descriptive evidence, not a pre-work predictor.

Review a small sample with maintainers: can they locate the governing invariant, identify its owner, and correctly
explain the lifecycle? Track the explanation and unresolved ambiguity rather than inventing a cognitive-load score.
Keep useful measures, revise noisy ones, and remove measures that repeatedly produce unhelpful warnings. This phase
validates usefulness; it does not promise enough observations for strong statistical or causal claims.

Pilot M7–M9 selectively. For a controlled evolution experiment, preserve each run's own code across successive tasks;
compare with an independent-task baseline starting from a known reference revision at each step. Hold requirements,
model/harness configuration, and budgets fixed across compared conditions, retain failed and unfinished runs, and use
repeated runs where affordable. A historical task whose solution may be in training data is not an uncontaminated
capability test. Keep these experiments separate from normal delivery metrics and the collector.

Before promoting a candidate, verify reproducibility on pinned revisions, inspect false positives with maintainers,
and establish whether it adds useful information beyond initial task scope and M1–M6. Record sample size, uncertainty,
and evaluator versions. No pilot score overrides existing verification, review, or merge authority.

## How the measurements should change development

Use a short recurring review of the strongest evidence, not a numerical quota:

| Observed pattern | Investigation and possible response |
| --- | --- |
| Comparable work touches more domains and consumes more effort. | Inspect concrete dependencies and restore a clear owner for the affected responsibility. |
| A frequently modified dependency has broad reach and recurring corrective work. | Examine its interface and callers; simplify the unstable contract and measure later work. |
| A policy transition accumulates consumers, age, and changes without retirement. | Finish or explicitly abandon the transition before building more mechanisms on it. |
| Review/report/docs runs repeat under the same requirements. | Trace the observed reason and remove redundant transitions while preserving approval and verification guarantees. |
| A graph metric improves but explanation difficulty and rework do not. | Revisit the metric or the intervention; avoid declaring success from graph shape alone. |

For each intervention, name the intended invariant, obsolete mechanism, affected consumers, and expected measurable
outcome. Link the implementation issue and compare subsequent similar work. Set investigation thresholds only after a
baseline exists. Alerts invite review; they do not establish a defect or authorize workflow changes.

For claimed improvements, retain the baseline and candidate revisions, workload, measurement procedure, raw results,
and relevant resource trade-offs. Separate reported validation from independently observed execution and later outcomes.
A changed prompt, passing suite, or lower static warning count alone does not demonstrate reduced maintenance effort.

## Verification and operating boundaries

Implementation checks should cover meaningful failure modes:

- Renames and file splits preserve domain interpretation; adding isolated modules cannot masquerade as a reduction in
  raw dependency reach merely by diluting a normalized ratio.
- Ordinary, deferred, type-only, unresolved, and dynamic imports produce the documented graph and coverage answers.
- Legitimate cross-domain migrations and code/test/doc co-changes remain distinguishable from reviewed coupling risks.
- Recollection, replay, corrected observations, changed analyzer versions, and historical timestamps preserve counts
  and provenance; conflicting observations are visible.
- Root-work-item aggregation does not double count child deliveries or run durations. Incomplete follow-up and unknown
  causes do not become zero corrections. Session reuse does not collapse separate invocations.
- Any promoted pilot preserves raw counts and denominators, reconciles changed test identities, and distinguishes
  adjudicated review findings from unreviewed claims. Cost per successful outcome includes the cohort's failed attempts
  and cannot silently omit unknown prices.
- Repository scope, issue filters, absent database configuration, and collector failures preserve existing dashboard
  behavior and workflow operation.

Run focused collector, sync/query, and dashboard checks with each behavioral change, plus the repository's required
checks. Update event, analytics, and architecture specifications where their guarantees change.

[C-12](../docs/contracts.md#c-12-observation-and-the-audit-recovery-exception) keeps analytics out of workflow decisions.
The collector and dashboard must not read as workflow authority, gate stages, mutate pinned state, or trigger automatic
refactors. [C-03](../docs/contracts.md#c-03-persisted-and-externally-consumed-formats) requires deliberate event changes
and honest unknown values. Runtime recording stays fail-open, and collection/sync remain outside the polling tick.

Use the documented database connection for any later analytics investigation. Never traverse or access
`analytics-db/data/`. The initial research used repository history and source inspection, not the operator's live
analytics database; actual outcome coverage remains to be measured.
