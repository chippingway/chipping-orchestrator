# Issue 2177: Review usefulness analytics

## Approval and purpose

The architecture discussion on GitHub issue #2177, originally titled "Useful review comments", concluded with
@geserdugarov's explicit confirmation: "Yes, we agree on the design. Please write the plan."

This document records the agreed design and the implementation work that follows. This commit contains the plan
alone. The repository was researched at `8e04ff2c43b93aca474e90b98cc165c14249219a`; no implementation or runtime
configuration is part of this change. Implementation must update the authoritative contracts and specifications
with its behavior. Repository rules still prohibit citing working notes from code, tests, comments, docstrings,
or commit messages.

The objective is an analytics dataset for the automated implementation/review loop:

1. The developer implements the task and supplies a short description of it.
2. The automated reviewer supplies individually identifiable review findings.
3. The responding developer scores each finding from 1 to 5.
4. The next review and developer response append another cycle of observations.

The dataset must connect tasks, findings, responses, and the agent invocations that produced them. The scores are
developer judgments about usefulness; they are not verified defect severity, proof of a successful fix, or inputs
to workflow decisions.

## Decisions resolved on the thread

- **Collect structured analytics rather than only improving developer reports.**
  A prose-only report addition is insufficient. The data must be individually attributable and queryable.
- **Record each review comment separately and have the developer score it.**
  A batch-level score, an inferred score based on code changes, and a score supplied by another evaluator do not
  satisfy the requirement.
- **Use the exact five-point rubric below.**
  The earlier proposed score anchors are superseded. Incorrect advice and advice with no useful contribution are
  distinct values.
- **Allow bounded text in PostgreSQL.**
  Selected task, finding, and assessment text can accompany the numeric observations. They need not depend on
  the separate trajectory file.
- **Collect from the automated loop only.**
  Human PR comments and human review summaries are outside this dataset. A shared workflow label does not
  establish eligibility.
- **Follow existing analytics enablement.**
  There is no new opt-in flag. Collection does not require trajectory logging or an active PostgreSQL
  connection.
- **Provide best-effort recording and keep the codebase simple.**
  There is no durable export queue, additional analytics checkpoint, retry service, exactly-once promise, or
  recovery run solely to reconstruct lost analytics.
- **Record malformed output and continue.**
  Missing or invalid analytics does not cause a correction run, park, or rejection of an otherwise valid
  workflow outcome.
- **Use the existing event stream and PostgreSQL `extras` storage.**
  Initial storage needs no new service, database table, or promoted column. Dedicated semantic records avoid
  overloading run-cost records.
- **Keep old observations unchanged and version new payloads and the rubric.**
  There is no inferred-score backfill or guessed join for historical records lacking identity.

### Rubric version 1

| Score | Agreed meaning |
| --- | --- |
| 1 | Incorrect, wrong proposal |
| 2 | No useful contribution |
| 3 | Minor improvement, low-level rare edge case bug |
| 4 | Meaningful improvement, correction or simplification, found minor bug |
| 5 | High-value improvement, significant simplification, found critical bug |

Scores are integers in the inclusive range 1 through 5. Missing, malformed, ambiguous, and out-of-range values
remain unscored; they are never converted to 1, 2, or a synthetic zero. A brief explanation accompanies a valid
assessment. Future rubric changes must be distinguishable from version 1 in stored observations.

## Selected architecture

```text
Automated implementation -> review -> developer response -> repeat
  |
  +-- developer task description
  +-- review batch and individually identified findings
  +-- developer assessments referencing those findings
  +-- collection diagnostics and coverage
  |
  v
Existing analytics JSONL -> existing sync -> analytics_events.extras
  |
  +-- invocation identity joins to agent_exit and optional trajectories
```

The existing analytics envelope remains `ts`, `repo`, `issue`, `event`, and optional `stage`, with additional
context carried as appropriate. Semantic observations form a focused event family. Event and field spellings,
the exact attachment syntax, module names, and numerical size limits are implementation choices within the
boundaries below; they are not additional architecture questions.

### Logical records

- **Task description.**
  A short developer-authored description, the requirements revision actually handed to the run, and the
  originating developer invocation.
- **Review batch.**
  The review identity, reviewer invocation, task reference, reviewed head and report identity, verdict, and
  declared finding count.
- **Individual finding.**
  A stable finding reference within that review occurrence, review reference, position, bounded finding text,
  and optional source location.
- **Developer assessment.**
  The finding reference, responding developer invocation, score, rubric version, and a brief explanation.
  Response/head/report context is included where the producing boundary knows it.
- **Collection diagnostic.**
  The source invocation, affected attachment or item, error category, bounded malformed excerpt where available,
  and collection counts or completeness information.

Each finding and each assessment is a separate analytics record. The review batch and collection metadata
distinguish an explicitly empty review from missing collection, and a fully assessed batch from a partial one.
A task description is authored by the developer; it is not fabricated by copying the issue title or by an
additional summarizing agent. It is attached to the task/requirements context the developer actually saw, never
to a newer requirements reading obtained after the run returned.

These records describe what the agents returned and what feedback was delivered. They do not by themselves
assert that a report was published, a fix was accepted, checks passed, or a change was merged. Existing workflow
records remain authoritative for those questions.

### Identity and relationships

Use the existing `AgentInvocation` identity instead of creating another independent run-identity system. It
contains repository, issue, pinned-comment identity, cycle, charge ordinal, and nonce. Expose that identity on
the new observations and on the existing `agent_exit` and trajectory records so their relationships are exact
where the data exists. A session ID can cover several resumes, and a review-round counter can reset; neither
is a unique invocation key.

The orchestrator assigns finding references within a particular review occurrence. They travel with the same
feedback artifact the existing handoff already records, posts, and replays. A normal continuation or fresh
developer-session replacement must receive the same references for the same delivered findings without reading
analytics. This is correlation for the existing interaction, not a new telemetry ledger or export checkpoint.

The relationships are task snapshot -> review occurrence -> findings -> developer response/assessments. A later
review repeating a concern is a new occurrence. A later developer response is another observation; it does not
overwrite an earlier score. Do not silently merge occurrences through text similarity. The collector validates
assessment references against the findings handed to that response, rather than guessing a target from a round
number or a fresh scan of GitHub comments.

New observations reference run costs; they do not copy those costs onto every finding. Otherwise one review
with several comments would multiply its cost in downstream aggregates.

### Scope and enablement

Eligible producers are the initial developer implementation, the automated reviewer, and developer responses
to that review, including ordinary continuations of the same automated request. Route by the origin of the
feedback rather than by `workflow:fixing` alone: human PR feedback uses that label too. Human guidance that
unblocks an automated fix does not turn the human's own comment into a rated automated finding. Unrelated
conversation stages, documentation passes, and report-only refreshes do not become synthetic review cycles.

Collection follows the existing `ANALYTICS_LOG_PATH` setting through its existing configuration owner. An unset
variable uses `<LOG_DIR>/analytics.jsonl`; empty, `off`, `disabled`, and `none` disable the sink. There is no new
feature flag. The existing analytics retention policy applies to these records as it does to other analytics.

`TRAJECTORY_LOG_PATH` remains independently optional. Full prompts and execution transcripts remain in that
separate stream. `ANALYTICS_DB_URL` remains the existing downstream sync/read setting: observations can be
collected locally when PostgreSQL is absent. Default analytics enablement now deliberately includes the bounded
semantic text, which must be documented as part of the changed collection behavior.

## Reply contracts and module boundaries

Structured analytics attachments accompany the existing agent replies. They are interpreted independently
of the report, verdict, and verification outcomes. Prompts and their readers must change together under C-08.
An attachment must not add text after a developer report's required final outcome, leave framing that changes
how an existing reader interprets that outcome, or enter the ordinary published report as accidental metadata.
The exact framing is the implementer's responsibility; protocol-isolation checks are mandatory.

For a valid structured review, the finding sequence is the source for both the feedback delivered to the
developer and the individual analytics records. Do not ask the reviewer to author an independently worded
analytics copy. If analytics extraction fails, preserve the existing ordinary feedback/outcome handling and
record that extraction failure; do not invent a valid empty finding sequence.

"Record malformed output and continue" applies to the analytics payload. It does not turn a missing verdict,
invalid verification declaration, malformed developer report, unfinished process, or genuine disagreement into
a successful workflow outcome. Existing report identities and approval requirements remain intact under C-09.

- **Request task descriptions, identifiable findings, and scored responses; isolate attachments from workflow
  outcomes.**
  Workflow prompt and reply-contract owners. Keep automatic fixes and their continuations consistent.
- **Supply issue, requirements, review subject, invocation, and delivered-finding context.**
  Existing workflow/run owners. Preserve finding references in the existing feedback artifact.
- **Interpret the observation payload and produce typed observations/diagnostics.**
  A focused observation boundary with one shared contract; callers must not implement competing parsers.
- **Validate, redact, bound, serialize, and emit observations.**
  Focused analytics recording ownership. It receives context and never imports workflow stages or makes their
  decisions.
- **Write files and apply retention.**
  Existing analytics sink and retention owners.
- **Ingest records into PostgreSQL.**
  Existing sync envelope/column routing, retaining new fields in `extras`.
- **Join observations and expose scores with coverage.**
  A focused analytics read model. Keep database and dashboard dependencies outside the recording path.
- **Preserve optional execution detail.**
  Existing trajectory writers/readers, linked by invocation identity. Provider parsers remain about CLI streams.

This preserves the enforced dependency direction: workflow producers can call observability, but observability
does not import the workflow engine, a stage, or application entry points. It also avoids a generalized plugin
or event-processing framework for this one event family.

## Malformed output, bounds, and best-effort delivery

### Interpretation

- Valid, independently attributable entries survive a partially valid attachment.
- Missing attachments and rejected entries produce diagnostic observations when collection can record them.
- Invalid syntax, unsupported payload versions, invalid score types/ranges, unknown finding references, and
  conflicting duplicate assessments in one response are explicit failures rather than guessed data.
- Conflicting duplicate assessments leave that finding unscored for the affected response. Unrelated valid
  entries can still be retained.
- A diagnostic is a valid analytics event whose payload contains the error and an excerpt. Never append broken
  JSONL as the diagnostic: the existing sync would skip it.
- Keep collection coverage beside analytical results. An average over scored findings must not imply every
  delivered finding was scored, and an incomplete/failed attempt must not masquerade as a completed response.

### Sanitization and resource limits

Apply the existing credential redactor before truncation and before JSON serialization can obscure multiline
secret values. Reuse that policy; do not create a divergent secret detector. Redaction does not anonymize
repository content, and storing bounded task/finding text in analytics is an intentional decision of this issue.

Bound descriptions, finding text, explanations, malformed excerpts, attachment/record size, and item counts.
State truncation or omitted items explicitly. Preserve identifiers and scores as whole validated values rather
than truncating them into another apparent identity. Bounds affect the telemetry copy; they must not silently
shorten the review feedback the developer is required to address. Numerical limits should be selected from
representative outputs during implementation, with tests at and beyond each boundary.

### Delivery and failure containment

Emit on genuine returned agent runs. A workflow recovery that finishes an existing report or feedback handoff
does not manufacture a new observation, rescore a finding, or launch an agent to fill missing analytics. Do not
add analytics payloads to durable developer-completion captures solely to guarantee later export.

One failure boundary must cover observation parsing, sanitization, serialization, and append. The current sink
only catches filesystem errors around file operations; its JSON serialization happens before that catch.
Therefore relying on the sink's `OSError` handling alone is insufficient. A collector error records a diagnostic
where possible and otherwise produces a warning. A failed diagnostic is not recursively retried. The ordinary
run result, usage accounting, report settlement, and workflow disposition continue under their own contracts.

No outbox, pending-export flag, durable retry queue, transactional multi-event append, or exactly-once protocol
is part of the design. A crash can lose an observation or leave a batch incomplete. Batch metadata can expose
some partial collection, but cannot prove that an entire missing batch never existed.

The existing content hash deduplicates replay of the same saved JSONL record into PostgreSQL. It hashes the
whole record, timestamp included, and is not semantic deduplication of separately emitted events. Stable source
references provide correlation; there is no new runtime deduplication database or promise to recover losses.

## Storage, reads, and compatibility

Store semantic payloads in `analytics_events.extras` through the existing generic sync. Its unpromoted-field
routing already preserves new keys. Do not add usage counters, run durations, or exit-status totals to every
finding record: those remain the run record's and are joined once where needed.

Add a focused read model for task/review/finding/assessment relationships and collection diagnostics. It should
make unscored and truncated data visible, keep rubric versions distinguishable, and retain independent review
occurrences. The existing cost rollup does not become the owner of usefulness semantics. A new dashboard,
reviewer-ranking policy, or adaptive reviewer selection is outside this storage-focused change.

Version the new observation contract and rubric. Older analytics rows and in-flight feedback without the new
metadata remain uncollected; do not infer their scores or invent invocation links. Records already stored are
not rewritten. Initial event storage requires no new table, promoted columns, database service, or historical
migration. Any parser/format contract deliberately changed by implementation must be documented and checked
together under C-03 and C-08; there is no blanket permission to reinterpret unsupported workflow state.

The report/approval contract remains the current one. Analytics attachments are independent observations, not
new reasons to replace an approved report or trigger another review. Workflows never read the analytics file,
PostgreSQL, or trajectory records to determine whether to advance, launch, park, or publish.

## Repository evidence and prior decisions

Paths below refer to the researched baseline `8e04ff2c43b93aca474e90b98cc165c14249219a`. The linked commits explain
the prior decisions the design preserves or deliberately extends.

- Workflow authority, deliberate formats, reply-parser alignment, report-bound approvals, observation-only
  analytics, and owner imports.
  [Contracts](../docs/contracts.md), especially C-01, C-03, C-08, C-09, C-12, C-13.
- One-way dependencies and keeping recording independent of the database/query/dashboard graph.
  [Observability boundaries](../docs/architecture/observability-modules.md#enforced-boundaries).
- Existing envelope, default-on analytics, disable vocabulary, append/retention locks, and filesystem-error
  containment.
  [Analytics sink](../orchestrator/observability/analytics/sink.py),
  [environment](../orchestrator/observability/analytics/environment.py),
  [recorders](../orchestrator/observability/analytics/recording/events.py).
- Generic `extras` routing, valid-envelope admission, and canonical whole-record content-hash deduplication.
  [Sync records](../orchestrator/observability/analytics/sync/records.py),
  [columns](../orchestrator/observability/analytics/sync/columns.py),
  [rows](../orchestrator/observability/analytics/sync/rows.py),
  [schema](../analytics-db/init/01-schema.sql).
- Optional per-run text, head/tail truncation, a nominal 200,000-byte record budget, and the existing separation
  from PostgreSQL. New semantic text deliberately extends the analytics boundary without copying full
  trajectories.
  [Trajectory models](../orchestrator/observability/analytics/trajectories/models.py),
  [serializer](../orchestrator/observability/analytics/trajectories/serialize.py),
  [trajectory reference](../docs/observability/trajectories.md).
- Redact before truncating or serializing; use the existing configured-token and secret-shaped-environment
  policy.
  [Sanitization](../orchestrator/observability/analytics/trajectories/sanitize.py),
  [credentials](../orchestrator/config/credentials.py).
- A true process identity already exists on `AgentResult`; session IDs and logical request fingerprints are
  insufficient. Current numeric and trajectory writers do not export that identity.
  [Agent models](../orchestrator/agents/models.py),
  [invocations](../orchestrator/workflow/engine/invocations.py),
  [tracked runs](../orchestrator/workflow/engine/usage.py),
  [run reporting](../orchestrator/workflow/engine/run_reporting.py).
- Usage parsing currently controls baseline `agent_exit` emission, and trajectory recording follows it before
  stage interpretation. Semantic collection must not depend on either usage parsing or trajectory availability.
  [Agent-exit recording](../orchestrator/observability/analytics/recording/agent_exit.py),
  [recording inputs](../orchestrator/observability/analytics/recording/models.py).
- Reports are concise final-state prose, outcome markers must close the reply, and malformed surrounding framing
  can interfere with their recognition.
  [Developer prompt notes](../orchestrator/workflow/engine/prompt_notes.py),
  [report outcomes](../orchestrator/workflow/engine/report_outcomes.py),
  [report fences](../orchestrator/workflow/engine/report_fences.py).
- Existing review findings are requested as numbered prose and persisted as one feedback string, not as an
  independently identified item collection.
  [Reviewer prompt](../orchestrator/workflow/engine/review_prompts.py),
  [verdict parser](../orchestrator/workflow/engine/completion_verdicts.py),
  [returned verdict](../orchestrator/workflow/stages/validating/review_verdicts.py).
- Ordinary automation already stores/posts feedback and replays it by its recorded comment anchor. Finding
  references should follow this artifact.
  [Feedback posts](../orchestrator/workflow/stages/validating/feedback_posts.py),
  [handoffs](../orchestrator/workflow/stages/validating/review_handoffs.py),
  [bookmarks](../orchestrator/workflow/stages/fixing/bookmarks.py),
  [continue replay](../orchestrator/workflow/stages/fixing/continue_command.py).
- Automated and human feedback share a label but have different origins; automatic continuations must remain
  eligible without collecting human findings.
  [Automated fix road](../orchestrator/workflow/stages/validating/fix_road.py),
  [resume road](../orchestrator/workflow/stages/fixing/resume_road.py),
  [human-feedback road](../orchestrator/workflow/stages/fixing/feedback_road.py).

Relevant history:

- [02772ff12](https://github.com/chippingway/chipping-orchestrator/commit/02772ff1200a69c96a5999b04d22f921dfbd24db)
  defined developer-report outcomes and prompt contracts.
- [cdb551c43](https://github.com/chippingway/chipping-orchestrator/commit/cdb551c43c20df871fb97573e3c6e4aa9fb7d6c4)
  made reports concise, and
  [ab391d904](https://github.com/chippingway/chipping-orchestrator/commit/ab391d9049e7a525d934620f8ece40c5be764a15)
  restricted their scope to the final change, rationale, and risks.
- [ebbf6616d](https://github.com/chippingway/chipping-orchestrator/commit/ebbf6616d66a9038a495d1e19e1fc2ea5eee60aa)
  bound automated review and approval to the developer report being reviewed.
- [51fb4857c](https://github.com/chippingway/chipping-orchestrator/commit/51fb4857ca172d7fbe86ee1312b5d9bf89ebebb4)
  introduced process invocation identity;
  [35832a200](https://github.com/chippingway/chipping-orchestrator/commit/35832a2009c3a3566d8ff2d42476966768600195)
  connected once-per-invocation usage accounting to the tracked run.
- [3c0d3fd83](https://github.com/chippingway/chipping-orchestrator/commit/3c0d3fd83ed4d4ef21aefdafdd4ae757f49ff701)
  established guarded change-request handoffs;
  [570dafae0](https://github.com/chippingway/chipping-orchestrator/commit/570dafae04849a0e18ac6c137447651e15d1a683)
  captured automatic fixes and their resumed rounds;
  [131ef4ccc](https://github.com/chippingway/chipping-orchestrator/commit/131ef4ccc89773f446f8e490ecfbae7ca9608750)
  captured the distinct human-feedback route.
- [56323337e](https://github.com/chippingway/chipping-orchestrator/commit/56323337e3ed11a9b22372f0019285314f04599e)
  aligned the findings shown in fresh, recovered, and replayed review feedback.
- [15ac71cb1](https://github.com/chippingway/chipping-orchestrator/commit/15ac71cb152659f583ec56d54cb8be01c03aaa3f)
  kept absent analytical evidence unknown rather than inferred.
- [2706c8ca6](https://github.com/chippingway/chipping-orchestrator/commit/2706c8ca6f204be3d024452cb2943e7af5f6c3d7)
  retained structured usage evidence in `extras` while adding dedicated columns for demonstrated aggregation
  needs; this feature initially needs only the existing generic storage.
- [46c703e5a](https://github.com/chippingway/chipping-orchestrator/commit/46c703e5aeaf6ee5e8b63f8f985b895097d83b7b)
  established explicit request-usage coverage and bounded observations, a precedent for distinguishing missing
  collection from a measured empty result without turning observations into workflow authority.

## Alternatives considered

- **Brief qualitative feedback only in developer reports.**
  The human changed the objective to a scored analytics dataset. Report-only content also couples assessment
  edits to approval freshness.
- **One usefulness score per review batch.**
  The agreed unit is each individual finding. One valuable finding must not conceal several incorrect or
  unhelpful ones.
- **Extract scores later from prose or full trajectories.**
  Trajectories are optional, redacted, and truncated. Extraction would lose evidence and could infer judgments
  the developer never supplied.
- **Keep all semantic text in trajectories and only numbers in PostgreSQL.**
  Bounded text was explicitly allowed in PostgreSQL. A two-stream dependency would make finding inspection
  depend on independent enablement and retention.
- **Put finding and assessment arrays into `agent_exit`.**
  The records belong to different invocations and need references anyway. Semantic extraction would become
  coupled to run-cost emission and its usage-parser failure behavior.
- **Have agents write separate analytics files.**
  This adds file creation, discovery, stale-output handling, and cleanup rather than using the existing reply
  exchange.
- **Replace all report/verdict outcomes with one mandatory analytics envelope.**
  That would make telemetry validity a prerequisite for workflow progress, contrary to the agreed
  malformed-output policy.
- **Guaranteed delivery through a durable outbox/checkpoint.**
  The human explicitly chose best-effort recording and code simplicity.
- **Add an independent observer or counterfactual agent experiment.**
  It adds agent runs and an evaluation lifecycle; inferred or third-party ratings are not the developer scores
  requested here. Counterfactual calibration remains a possible separate research project.
- **Include human review comments or add another enablement flag.**
  Both were explicitly excluded in the final scope/activation decisions.
- **Use scores to select reviewers, suppress findings, or gate publication.**
  The agreed feature collects observations. Such policy would need a separate design and must not read analytics
  as workflow state.

## Risks and how they appear

- **Best-effort loss or partial append**
  - Symptom — Missing batches, orphan references, or fewer recorded items than declared.
  - Handling — Expose available collection counts and gaps; accept that complete loss can remain undetectable.
    Do not add export recovery.
- **Incorrect correlation through sessions or reset rounds**
  - Symptom — A score appears under another review or cost is attributed to the wrong run.
  - Handling — Use invocation and delivered-finding identities; do not guess joins for records lacking them.
- **Analytics framing interferes with workflow parsing**
  - Symptom — Extra parks, missing verdicts, report rejection, or accidental analytics text in published
    reports.
  - Handling — Isolate the attachment contract and test malformed framing alongside valid and invalid ordinary
    outcomes.
- **Malformed payloads distort the score distribution**
  - Symptom — Missing values appear as low scores, conflicting scores count twice, or foreign finding IDs
    acquire ratings.
  - Handling — Keep invalid entries unscored and diagnostic; retain unrelated valid entries and expose coverage.
- **Truncation hides important text**
  - Symptom — A finding or explanation looks complete although content was omitted.
  - Handling — Record truncation and counts; bound only the telemetry copy, not the delivered review.
- **Wrong route selection**
  - Symptom — Human findings or unrelated developer runs enter the dataset.
  - Handling — Select the automated origin and its continuations rather than the stage label alone.
- **Default-enabled text collection exposes secrets or excessive content**
  - Symptom — Credentials in diagnostic excerpts, unexpectedly large files, or repository text in configured
    PostgreSQL.
  - Handling — Document the intentionally expanded bounded-text collection, redact before truncation, and apply
    explicit field and collection limits.
- **Coupled observer failure**
  - Symptom — A serialization or parser error interrupts usage accounting or delivery.
  - Handling — Guard the whole observation path, not only filesystem writes; warning-only fallback when a
    diagnostic cannot be recorded.
- **Cost multiplication**
  - Symptom — Cost rises with the number of findings from one review.
  - Handling — Keep costs on the run record and join once; semantic events carry references.
- **Subjective and selectively missing ratings**
  - Symptom — High agreement in one model pair but not another, or missing ratings concentrated on difficult
    rounds.
  - Handling — Preserve explanations, source runs, rubric version, and coverage. Treat ratings as developer
    judgments, not verified effectiveness.

## Research and validation basis

The repository investigation was read-only: contracts, implementation paths, behavioral tests, and commit
history were inspected. No production dataset was sampled and no implementation tests were run for this plan.

The publication summary for Bosu, Greiler, and Bird's
[Characteristics of Useful Code Reviews: An Empirical Study at Microsoft](https://www.microsoft.com/en-us/research/publication/characteristics-of-useful-code-reviews-an-empirical-study-at-microsoft/)
(MSR 2015) was consulted as prior art. It describes qualitative investigation of developer-perceived usefulness
and a subsequent classification study. It motivates explicit judgments and calibration, but does not validate
this five-point rubric for agent developers. The rubric here is the human's decision, not a claim derived from
that study.

Useful implementation-time measurements remain:

- Sample finding counts and text lengths to choose concrete bounds. High counts should inform limits and
  explicit partial-collection reporting, not silently change the per-finding requirement.
- Exercise identity joins over reused sessions, reset round counters, and ordinary continuations. A failed
  join should remain missing evidence and identify the attribution defect.
- Compare a sample of developer scores with human judgments under rubric version 1. Disagreement informs a
  future explicitly versioned rubric or interpretation of results, not retrospective relabeling.
- Measure the focused queries before adding promoted columns, indexes, or additional projections. Existing
  `extras` storage is the initial choice; hypothetical query demands do not justify schema expansion now.

These are validation and calibration activities, not unanswered architecture choices or prerequisites for
reopening the agreed design.

## Implementation plan

The steps below are a sequence of work, not an issue-sizing or child-issue manifest. Before changing source,
tests, or authoritative documentation, read the repository's
[development guidance](../.agents/skills/develop/SKILL.md) and the current contracts again.

1. **Define the observation contract and pure readers.** Specify the versioned task/review/finding/assessment
   and diagnostic shapes, the exact agreed rubric, identity/reference validation, partial validity, coverage,
   and bounds. Keep observation parsing distinct from workflow-outcome parsing. Choose attachment framing
   that preserves final report/verdict and verification contracts, including malformed-attachment cases.
2. **Connect automated-loop prompts and provenance.** Request the task description, one identifiable finding
   sequence, and per-finding developer scores. Supply requirements and reviewed-subject context from existing
   owners. Carry finding references through the existing feedback artifact and normal continuation/respawn
   paths. Respect the automated origin; do not collect human review items or unrelated stages.
3. **Add the focused best-effort recorder.** Normalize one returned run's observations, preserve valid entries,
   emit valid diagnostic envelopes for malformed entries, redact and bound all text, and call the existing
   append path under a failure guard. Follow existing analytics enablement. Do not make this collector depend
   on successful usage parsing, full-trajectory parsing, PostgreSQL, or any export-recovery state.
4. **Expose invocation correlation.** Serialize the existing invocation identity on observations, `agent_exit`,
   and optional trajectory records. Update the relevant readers without inventing identities for older rows.
   Keep baseline usage/accounting semantics and provider-specific trajectory parsing unchanged.
5. **Add focused dataset reads.** Use `analytics_events` plus `extras` for task/finding/assessment relationships,
   diagnostics, and coverage. Test the generic sync round trip and repeat-sync behavior. Avoid new storage
   infrastructure and copying per-run costs onto findings.
6. **Update authoritative documentation and behavioral checks together.** Describe the event family, changed
   bounded-text collection, enablement, best-effort loss, rubric, reply protocol, and module ownership. Update
   affected contracts deliberately, preserving observation-only decisions and report-bound approvals. Run
   focused tests and the repository-required checks before implementation publication.

### Acceptance checks

- An automated implementation/review/response cycle records the developer's task description, individual
  findings, individual valid scores, and correct source relationships across another cycle.
- The five scores retain the exact agreed meanings; invalid types, missing scores, invalid ranges, unknown
  references, and conflicting duplicates do not become valid assessments.
- Malformed attachments produce bounded diagnostic events while ordinary valid workflow outcomes remain
  valid. Ordinary invalid workflow outcomes are not rescued by analytics.
- Unrelated valid entries in a partially invalid attachment survive, with counts that expose partial coverage.
- Automatic fix continuations preserve finding references; human-feedback routes do not emit rated human
  findings. A reconstructed workflow completion does not emit a fictitious new agent observation.
- Reused sessions and reset rounds still join by invocation identity. Missing historical identity stays absent.
- Collection follows the existing analytics setting, works with trajectories and PostgreSQL disabled, and
  introduces no database dependency into the run/recording path.
- Parser, sanitizer, serializer, and append failures cannot interrupt the ordinary workflow or its usage
  accounting. Diagnostic failures do not initiate retries or further agent runs.
- Secret redaction precedes truncation, field and collection limits are enforced, and truncation is visible.
- New fields survive the existing JSONL-to-`extras` mapping. Replaying the same saved records remains
  idempotent under existing content-hash deduplication. Missing batch records remain possible by design.
- Baseline run costs and counters are not multiplied by per-finding records; new reads report unscored and
  incomplete observations separately from the score distribution.

Existing nearby checks to extend or use as patterns include
[prompt contracts](../tests/workflow/engine/test_prompts_developer_report.py),
[invocation identity](../tests/workflow/engine/test_invocation_identity.py),
[trajectory isolation](../tests/workflow/engine/test_usage_trajectory.py),
[automated captures](../tests/workflow/stages/validating/test_captured_fixes.py),
[resumed captures](../tests/workflow/stages/fixing/test_captured_resumes.py),
[human-feedback captures](../tests/workflow/stages/fixing/test_captured_feedback.py),
[feedback batches](../tests/workflow/stages/fixing/test_batch.py),
[row mapping](../tests/observability/analytics/sync/test_row_mapping.py),
[malformed-line handling](../tests/observability/analytics/sync/test_ingest_malformed.py),
[repeat sync](../tests/observability/analytics/sync/test_replay_idempotency.py), and
[trajectory records](../tests/observability/analytics/trajectories/test_record.py).

No architecture questions remain. Implementation details must stay within the resolved scope rather than
introducing human-review collection, another feature flag, or failure-resistant analytics delivery.
