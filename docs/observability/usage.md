# Usage parser

Pure-Python helpers that decode the JSONL stdout `agents.models.AgentResult` carries into a `UsageMetrics` dataclass —
backend, distinct model(s), turn count, input / output / cached / cache-read / cache-write token totals, `cost_usd`, and
a `cost_source` tag of `reported` / `estimated` / `unknown-price` / `no-usage`. No external dependency: the parser is
jq-free.

The pass runs once the audit `agent_exit` event has already fired, and `record_agent_exit` writes what it returns as
the token / cost detail on the analytics [`agent_exit` record](event-streams.md#agent_exit-records) and the
`run_usage` summary on the [trajectory record](trajectories.md#trajectory-sink-trajectory_log_path). Two siblings ride
the same stream under the same resilience contract: the opt-in skill-trigger extractor and the trajectory classifier
below. None of the three reads or writes a file — redaction, truncation, and the append itself belong to the writers
downstream of them.

Where the parser sits in the package tree, and what it is responsible for beside the surfaces around it, is in
[`architecture/observability-modules.md`](../architecture/observability-modules.md); the knobs are in
[`configuration/observability.md`](../configuration/observability.md).

**Module layout.** Callers import the parsers directly from `metrics.py`, `skills.py`, and `trajectory.py`.
Each dispatches across Codex, Claude, and Antigravity. The six result types come from their defining modules:
`UsageMetrics` and `SkillTriggers` from the first two, and `AgentTrajectory` / `TrajectoryStep` /
`SourceItem` / `TurnUsage` from `trajectory_models.py`. Provider payload handling is split behind them: `protocol.py`
holds the JSONL vocabulary and `event_stream.py` the resilient line decoder, `prices.py` the first-party price tables
and `model_names.py` the nested model-name lookup, `claude_rows.py` / `claude_summary.py` and `codex_rows.py` /
`codex_summary.py` the per-provider frame decoding and run summary, `shell_segments.py` / `skill_commands.py` /
`skills_claude.py` / `skills_codex.py` the skill-evidence classification, and `trajectory_claude_blocks.py` /
`trajectory_claude_stream.py` / `trajectory_claude_turns.py` plus `trajectory_codex.py` and the per-item-type
`trajectory_codex_items.py` under it the timeline reconstruction. Antigravity's envelopes, tool lifecycles, and
completed-step usage live in `agy_events.py` / `agy_summary.py`, with its text and tool timeline in
`trajectory_agy.py`. The
trajectory classifier reuses the same event decoder, pricing path, and skill evidence owners, so the resilience and
cost-precedence contracts are defined once. Tests intercept parsers on the module their caller imports. The package
initializer re-exports the public parsers and result types; callers name the defining owner so patches reach it.

**Provider parsing.** `parse_claude_usage(stdout)` consumes claude `--output-format stream-json` events,
groups assistant frames by `message.id` so the final-frame usage wins (claude streams partial counts on intermediate
frames), and sums per-model. `parse_codex_usage(stdout, fallback_model=None)` consumes codex `--json` events and treats
usage as cumulative across the session: the *last* non-zero usage record is the authoritative total.
`parse_agent_usage(backend, stdout, fallback_model=None)` dispatches by backend string the same way
`agents.runner.run_agent` does.

For `agy`, token totals come from the completed `step_update` events in this invocation, deduplicated by step index.
The terminal result's usage and turn counts include earlier conversation turns on a resume, so they are not added
to the per-run counters. `user_input` steps count this invocation's turns; `init.model` supplies the model, falling
back to the configured `--model`. Output tokens already include thinking tokens. The CLI supplies no USD cost;
usage has `unknown-price`, with no estimated amount. No completed usage frames means `no-usage`.

Antigravity trajectories join each response step's text deltas, retain tool parameters and outcomes, read offered
tools from `init`, and take the final answer only from a successful terminal result. Interrupted response text is
kept in the timeline without becoming a final answer. Skill evidence remains empty because this adapter does not
infer skill loads from Antigravity's tools; no per-turn pricing or source-item accounting is emitted.

Tool lifecycles fold repeated and sparse `step_update` frames by `step_index`, retaining tool identity across partial
updates and recording each step's latest state. The lifecycle reducer reports every indexed tool step whose latest
state is not `DONE`, ensuring earlier background commands remain authoritative even when later status checks finish
and emit terminal output.

**Cost precedence.** A `total_cost_usd` reported by the CLI itself always wins (`cost_source="reported"`); otherwise the
parser walks first-party Anthropic / OpenAI price tables baked into the module and produces an estimate (`"estimated"`).
When usage is present but the model SKU does not match any priced family, the parser returns
`cost_source="unknown-price"` and `cost_usd=None` rather than guess at zero or bill cached tokens at the input rate. An
empty stream — or one with no usage frames at all — yields `"no-usage"`.

**Resilience.** Malformed JSON lines (banner text, truncated frames, partial flushes) are silently skipped so a single
bad line never invalidates the rest of the stream. `_run_agent_tracked` (in `workflow/engine/usage.py`) calls
`parse_agent_usage` after every tracked agent run and appends the parsed counts to the
[analytics sink](event-streams.md#analytics-sink-analytics_log_path) under `event="agent_exit"`; a
parser exception is caught and downgraded to a `log.exception`.

**Terminal verdict surface.** Beyond the analytics sink, `_accumulate_issue_usage` (in `workflow/engine/usage.py`,
beside `_run_agent_tracked`) folds each run's
`UsageMetrics` into per-issue counters on the pinned state (`issue_agent_runs` / `issue_total_tokens` /
`issue_total_cost_usd` / `issue_cost_sources`; see [state-machine/labels-and-state.md][pinned-state]). When an
issue reaches a terminal, `_format_issue_usage_verdict` renders those counters into one visible receipt line
posted on the issue thread — `:receipt: this issue: N agent runs · T tokens · $X.XX`, with `(est.)` appended when any
run's cost was `estimated` and the figure collapsed to `unknown` when an `unknown-price` run leaves the total
incomplete. The PR merged / rejected finalizers and the closed-`question` terminal post it as a standalone tracked
comment; the `umbrella` close comment appends it. It is a read-only summary — nothing gates on the figure — and it is
skipped when no run was ever counted.

`issue_agent_runs` has one reader outside that receipt: the lifetime agent-run ledger on
`workflow/engine/run_ledger.py` seeds a missing `agent_runs_used` from it and never reads below it, so an issue
already in flight keeps what it has already spent. The two count the same unit but not the same set — the ledger
charges the launch and so also holds the runs whose usage never parsed, while this meter counts the parsed exits —
which is why the ledger's total is the larger of the pair. Nothing turns a run away against THIS meter — the ledger
is the one that is judged, at the tracked spawn boundary (`workflow/engine/run_circuit.py`), and where an issue that
has spent it all STOPS is the durable `agent_run_limit` park on `workflow/engine/run_limit.py` and the dispatcher
hold over it. What that ledger DOES, as opposed to what it currently holds, is its own record:
`workflow/engine/run_budget.py` writes one
[`agent_run_budget`](event-streams.md#agent-run-budget-records-both-sinks) event to both sinks per durable
transition — a run charged, the spawn it paid for, the ceiling that refused one, and the ceiling an operator widened
— each carrying the configured limit, the allowance in force, the spend, and what is left. That is the stream to
count charges on; `agent_exit` records, and this meter behind them, count the runs whose usage parsed.
See [`configuration.md`](../configuration.md#cadence-and-budgets) for `MAX_AGENT_RUNS_PER_ISSUE` and
[state-machine/labels-and-state.md][pinned-state] for the ledger's and the park's own keys.

**Skill-trigger extractor (opt-in).** A sibling trio mirrors the usage parsers' two-parsers-one-dispatcher shape and
resilience contract to record which agent *skills* a run loaded, gated behind `TRACK_SKILL_TRIGGERS` (default off;
see [`agent_exit` records](event-streams.md#agent_exit-records)). The result is a names-only
evidence model on `SkillTriggers`: `triggered` / `trigger_counts` are the loaded skills, `evidence` maps each to its
tier (`confirmed` / `inferred`), and `incidental` / `incidental_counts` are path-only references that never become
loads. The two buckets are independent —
a skill both read and inspected is recorded in both — the only exclusion is structural: an incidental reference never
enters `triggered` / `trigger_counts` or the `skill_triggered` audit events. `parse_claude_skills(stdout)` reads the
firm **confirmed** signal — `tool_use`
content blocks named `Skill` in the `assistant` stream — and returns `input.skill` in first-seen order, de-duplicating
per invocation by the block `id`. (A captured real stream showed that under `--include-partial-messages` each completed
content block lands in its own `assistant` frame — the content array is partitioned across frames, not a cumulative
snapshot that repeats earlier blocks the way the `usage` sub-object does — so the parser walks every frame and de-dups
by `id` rather than keeping the last frame per message id.) Claude has no dedicated file mechanism, so it produces no
incidental references. `parse_codex_skills(stdout)` recognizes the codex shape: codex has no dedicated `Skill` tool, so
its file-based skill mechanism surfaces only as a `command_execution` item whose shell `command` opens a skill's
`skills/<name>/SKILL.md` file (codex's own "open its SKILL.md" instruction). A captured reviewer run pinned this — codex
both registered-under-`$CODEX_HOME/skills/` and project-local `.agents/skills/` reads match. The command is first
unwrapped (peeling the `bash -lc "…"` shell) and split into sub-commands on **unquoted, unescaped** operators —
quote- and backslash-aware, so a metacharacter inside a quoted argument (`rg 'foo|bar' path`) or a backslash-escaped one
(`rg foo\|cat path`) does not fabricate a spurious segment — then each `SKILL.md` match is routed by its sub-command's
leading verb (skipping any `NAME=value` env prefix). Only a verb
established as a **direct reader** (`cat` / `sed` / `head` / …) makes the reference an **inferred** load; every other
verb — an inspection / search (`git diff` / `git status` / `rg`), an env-prefixed inspection (`GIT_PAGER=cat git
diff …`), or a generic path-only command (`echo …`) — makes it an **incidental** reference. Even a reader verb is
demoted to incidental when the `SKILL.md` is *written* rather than read: an output-redirect target
(`cat t > .agents/skills/x/SKILL.md`) or a non-reading mode (`sed -i` / `--in-place`) is an incidental reference, so a
skill file a run only writes is never miscounted as a load. So a read chained after an inspection still counts, and a
bystander `git diff` over a changed SKILL.md does not fabricate a load. Started/completed
echo the same command, so the parser dedups by the shared `item.id` (last-frame-wins, as for usage) — for inferred
loads and incidental references alike. It reads only the `<name>` path segment and the routing verb — never the command
text or its `aggregated_output` (the file's contents), both of which can echo user content (names-only Privacy). The
inferred signal stays **heuristic** within the reader allowlist: a reader that opens a SKILL.md for an unrelated reason
would still register as an inferred load, while defaulting non-readers to incidental keeps an unrecognized command from
fabricating a trigger. `parse_agent_skills(backend, stdout)` dispatches by backend exactly as `parse_agent_usage` does.
The offered-skills set (`SkillTriggers.available`) is
**confirmed on claude** — read from the dedicated `skills` array in the `system`/`init` frame, captured against a real
stream — and
stays **empty on codex** at the parser layer: a captured `codex exec --json` stream (v0.142.5) carries no offered-skills
frame at all, so `record_agent_exit` backfills the codex offered set out-of-band from the filesystem via
`skills.discovery.discover_local_skill_sources(cwd)` instead — a scan that also reports the source level each name was
defined at, which the `agent_exit` record keeps beside the names as `skill_levels`. The *triggered* set does not
depend on it either way. As with the usage parsers, malformed JSONL lines are skipped and a missing / renamed field
yields an empty result rather than an exception. Only the skill *name* is ever read — never the `Skill` tool's `args`
(Privacy).

**Trajectory classifier.** A third sibling trio mirrors the same two-parsers-one-dispatcher shape and resilience
contract to reconstruct a run's *trajectory* — the ordered timeline of tool calls / results interleaved with the
assistant / user text turns — into an `AgentTrajectory` dataclass: `backend`, a best-effort `system_prompt` / `tools`,
the names-only `skills` (`SkillTriggers`), an ordered `steps` tuple of `TrajectoryStep` (`kind` is `"tool_call"` /
`"tool_result"` / `"assistant_message"` / `"user_message"`, with `name` / `tool_id` / raw `content` — `name` /
`tool_id` empty on the text turns — plus a `turn` index tying each billed step back to the assistant turn that
produced it), a `source_items` tuple of `SourceItem` accounting for every item the provider stream identified
(codex-only today), `final_output`, and a best-effort `turns` tuple of per-turn token usage (`TurnUsage`, parallel to
`tools` / `skills` and claude-only today). `parse_claude_trajectory(stdout)` reads the offered tools from the
`system`/`init` frame's `tools` array, then the ordered timeline: assistant `text` blocks become `assistant_message`
turns and `tool_use` blocks `tool_call` steps; user `text` blocks become `user_message` turns and `tool_result` blocks
`tool_result` steps — calls / results joined by `tool_use_id` and de-duplicated per id the same way
`parse_claude_skills` is, while id-less text blocks ride claude's per-completed-block framing — and the final answer
from the `result` frame's `result` string. It also groups those assistant frames by `message.id` in first-seen order to
assign each a 0-based `turn` index — stamped onto the `assistant_message` / `tool_call` steps that frame produced (a
`tool_result` / `user_message` step is a turn *input*, not billed output, so its `turn` stays `None`) — and emits one
`TurnUsage` per turn: `model`, `input_tokens` / `output_tokens`, `cache_read_tokens` / `cache_write_tokens` (the 5m + 1h
cache-creation buckets summed), and an always-*estimated* `cost_usd` / `cost_source` (`"estimated"`, or
`"unknown-price"` with `cost_usd=None` for an unpriced SKU — a reported `total_cost_usd` is a run-level figure and
never reaches a turn). The per-turn estimate reuses the same `claude_estimate_cost` price path on
`observability/usage/prices.py` as the run aggregate, so the per-turn figures stay in lock-step with
`parse_claude_usage`'s run totals. `parse_codex_trajectory(stdout)` normalizes each
operational item codex reports into one `tool_call` and, when the stream actually carried an outcome, one
`tool_result` beneath it, and each `agent_message` item into one `assistant_message` turn (its `text`). Codex emits
several frames per item — `item.started`, any `item.updated`, then `item.completed` — so every item is correlated by
its `item.id` and a frame contributes only the fields it carried, which is what collapses a started/completed pair
into a single pair of steps and lets the completing frame name what the started one had not resolved yet — except
where the item type says otherwise: an item codex republishes whole on every frame is invoked once, by the frame that
opened it, so a revision moves its result rather than its call. Every item also keeps the position its *first* frame
took, so folding a later frame into it fills that pair in place rather than moving it behind the operations that
started after it, and the timeline reads in the order the run started its operations. A frame the stream left without
an `item.id` correlates with nothing, so each one stands on its own and its steps trail the ordered items rather than
claiming a position between two of them. The supported item types and the fields each pair is
built from are: `command_execution` (its `command`, then the
`aggregated_output` of the frame that completed it — a *running* command already reports that field, empty, so
presence alone would credit a command still running with a result it never produced), `mcp_tool_call` (its
`arguments`, then its `result` — or its `error` when the server filled that instead — under a `<server>.<tool>` step
name), `web_search` (its `query`, then the `action` it resolved to — a search announces itself with an empty query
and names itself only on the frame that completes it, so that frame is both what the query is read from and the only
one that reports an outcome, and that `action` is the whole of the outcome the stream carries: the pages a search read
and the answers it got are absent from the stream and are never reconstructed for the record), `file_change` (its
`changes`, kept as the structured one-entry-per-path list codex reports them as, then the `status` once it is terminal
— `completed` or `failed`, on whichever frame carries it, since a patch reports `in_progress` until it has ended, so a
patch that failed stays distinguishable from one the run left half applied, and a patch still `in_progress` when the
stream stopped keeps its call with no result under it), and `todo_list` (the plan `items` of the
frame that opened it, then the plan `items` of the frame that completed it — codex republishes the whole plan on every
revision, so one plan is one pair however often it is rewritten: every `item.updated` between the two folds into that
same pair instead of adding a step of its own, and a plan the stream never completed keeps its call with no result
under it, since where a plan stood when the stream stopped is not where it ended). `file_change` is codex's
**custom** (freeform) tool surface: the model calls `apply_patch`, and the stream reports the call and its outcome as
a `file_change` item, so a custom tool call normalizes to a pair
like any other. `codex exec --json` publishes no separate custom / dynamic tool item type — its whole item vocabulary
is `agent_message`, `reasoning`, `command_execution`, `file_change`, `mcp_tool_call`, `collab_tool_call`,
`web_search`, `todo_list`, and `error` (verified against codex-cli 0.148.0), and `custom_tool_call` is a raw
model-response / rollout spelling that never reaches this stream. A `web_search` item serializes `id` twice, the
provider's own `exec-…` call id last, so that call id is what the decoder hands the parser and what a search is
correlated and recorded under; every other item is correlated under the synthetic `item_N` the exec stream numbers
its items with. The id is also what keeps one operation one item: a wrapper frame reporting the id of the call
nested inside it merges into that call rather than doubling it, and a wrapper of a type nothing normalizes neither
replaces the normalized pair with a placeholder nor adds one beside it — nor survives inside one: a placeholder is
named after the wrapper's own item type and payloaded with the wrapper's own `status`, so the normalized frame
replaces it whole rather than merging into it, and an item that frame reported no invocation for is left with none
instead of reading back as the wrapper's `in_progress`. The final answer is read from the last
`agent_message` `text`; `turns` stays empty with every `step.turn` `None`, since codex usage frames are cumulative
across the session rather than per-turn. Both reuse the
matching skill extractor for the `skills` field. `parse_agent_trajectory(backend, stdout)` dispatches by backend exactly
as the usage / skill dispatchers do. `system_prompt` stays `None` and `tools` stays empty in the classifier whenever a
backend's stream does not expose them (codex exposes neither); the analytics writer backfills codex `tools` out-of-band
from `skills.discovery.discover_codex_tools()`. Malformed JSONL lines are skipped and a missing / renamed field
yields an empty section rather than an exception. Unlike the skill extractor, this classifier records the **raw** stream
payload — tool inputs, tool outputs, and the final text — verbatim: it deliberately does **not** redact, truncate,
or write any file. Those concerns belong to its downstream writer,
`observability/analytics/trajectories/`'s `persistence.maybe_record_trajectory`
(called from `record_agent_exit`), which redacts every free-text field, applies the head/tail and total-record
truncation caps, and appends the `agent_trajectory` record to the
[trajectory sink](trajectories.md#trajectory-sink-trajectory_log_path) — only when
`TRAJECTORY_LOG_PATH` is enabled and always behind its own fail-open guard.

**Codex item types beyond those five.** Nothing is dropped silently. An item type the classifier does not normalize —
codex's non-fatal `error` items and its `collab_tool_call` today, whatever a later release adds tomorrow — becomes one
bounded `unsupported_item` placeholder step naming the item `type`, its id, and the `status` it reported (`null` for a
type that reports none, `error` among them), deduplicated by
`item.id` the same way a tool pair is and carrying no payload of its own. `reasoning` is the one deliberate
exclusion: its text is hidden model content that never enters a record, and a placeholder per reasoning item would be
noise rather than a diagnostic — but the exclusion is named rather than silent, in the per-item accounting below.
Nothing fabricates an outcome either — a call that failed, or one the stream never
completed, keeps its `tool_call` with no `tool_result` under it unless a frame actually reported one.

**Every identified codex item is accounted for.** Beside the steps, `parse_codex_trajectory` returns one `SourceItem`
per `item.id` the stream carried, in first-seen order across every identified frame — the ones that contribute no
step at all included — and deduplicated across the started / updated / completed frames the same way a tool pair is.
Each names the `item_id`, the `item_type` the classification settled on, and a
`disposition`: `stored` (the item's own steps are in `steps`), `unsupported` (nothing normalized its type, so the
placeholder step above is what names it), `excluded` (the `reasoning` the classifier keeps out whole — the accounting
records the id and the type and nothing else, never the hidden text or any other field of the item), or `empty` (its
frames carried no payload to store — an `agent_message` with no text, a call whose fields never arrived, or an item
too malformed to name a type at all, whose `item_type` is then the empty string). A normalized frame outranks an
unsupported wrapper sharing its id whichever of the two arrives first — and renames it in place, since an id holds the
position its first frame took either way — so the wrapper that adds no step renames nothing either and leaves no
payload of its own behind. The accounting is also what carries an `agent_message` item's
id: a text turn is not a tool call, so its step's `tool_id` stays empty and the provider id lands here rather than in
the field a downstream reader joins a result to its invocation by. A frame the stream left without an id is the one
thing not accounted — there is no name to account it under, and every such frame would otherwise share one — so it
contributes its steps and nothing else. `AgentTrajectory.to_dict()` carries the tuple as `source_items`, and the
`agent_trajectory` sink record serializes it under that same key — bounded, counted, and flagged when truncated, as
[`trajectories.md`](trajectories.md#trajectory-sink-trajectory_log_path) describes.

[pinned-state]: ../state-machine/labels-and-state.md#pinned-state
