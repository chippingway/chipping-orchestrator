# Usage parser

Pure-Python helpers that decode the JSONL stdout `agents.models.AgentResult` carries into a `UsageMetrics` dataclass —
backend, distinct model(s), turn count, input / output / cached / cache-read / cache-write token totals, `cost_usd`, a
`cost_source` tag of `reported` / `estimated` / `unknown-price` / `no-usage`, and the cost and token evidence that say
what those amounts and counters mean (below). No external dependency: the parser is jq-free.

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
holds the JSONL vocabulary and `event_stream.py` the resilient line decoder and the cost-precedence selection,
`cost_evidence.py` the cost basis, completeness, and reduction and `token_evidence.py` the token-counter semantics every
surface shares, `prices.py` the first-party API price
catalogue over the dated rows and bounded lookup on `price_catalogue.py`, and `model_names.py` the nested model-name
lookup, `claude_rows.py` / `claude_summary.py` and `codex_rows.py` /
`codex_summary.py` the per-provider frame decoding and run summary, with `claude_settlement.py` settling each Claude
message's final output count between the two and `claude_requests.py` holding each Claude usage row's scope, the
lifetime of each of its cache writes, and the estimate it is priced at, and `codex_requests.py` what one Codex usage
record establishes about the requests it sums and the estimate it is priced at, `shell_segments.py` /
`skill_commands.py` / `skills_claude.py` / `skills_codex.py` the skill-evidence classification, and
`trajectory_claude_blocks.py` /
`trajectory_claude_stream.py` / `trajectory_claude_turns.py` plus `trajectory_codex.py` and the per-item-type
`trajectory_codex_items.py` under it the timeline reconstruction. Antigravity's envelopes, tool lifecycles, and
completed-step usage live in `agy_events.py` / `agy_summary.py`, with `agy_requests.py` holding which Gemini API model
a run's CLI slug is priced as and the estimate its steps are priced at, and its text and tool timeline in
`trajectory_agy.py`. The
trajectory classifier reuses the same event decoder, pricing path, and skill evidence owners, so the resilience and
cost-precedence contracts are defined once. Tests intercept parsers on the module their caller imports. The package
initializer re-exports the public parsers and result types; callers name the defining owner so patches reach it.

**Provider parsing.** `parse_claude_usage(stdout)` consumes claude `--output-format stream-json` events, reads one
usage row per API message by grouping its `assistant` frames on `message.id`, and sums per-model. Every one of those
frames repeats the usage the message's `message_start` event opened with, so the output count it carries is the one at
the start of the message. The final count, thinking included, is only on the `message_delta` stream event that closes
the message, whose `stream_event` wrapper names it through `api_message_id`; that event settles the message's output
count. Input, cache-read, and cache-write counts are the same on every frame and stay the ones the `assistant` frames
carry. A subagent prints no stream events. The message that closes it prints no frame at all: its usage rides on the
lead thread's `tool_result` for the call that launched the subagent, as `tool_use_result.usage`, and that hand-back
adds a row carrying the message's output count alone, since the run's input and cache counts are its frames'. A
hand-back counts once per call it answers — the `tool_use_id` of its `tool_result` — since a resumed subagent returns
under the agent id it had before. The final count of any earlier subagent message is printed nowhere: the `result`
frame's `modelUsage` reports only the model's total, and what it holds beyond every output count the stream printed
settles that message only when it is the model's sole message no `message_delta` closed, only when `modelUsage`
reports the model's input, cache-read, cache-creation, and output totals — an absent one establishes nothing, never a
zero — and only when those input and cache totals equal the counts the stream printed, hand-backs included. Two or
more such messages share a total no frame divides, so each keeps its start count, as a
subagent's message does whenever `modelUsage` also covers usage no frame of the stream printed; a message whose frames
reported no output count and that nothing settles keeps no output count at all. A `message_delta` whose output is no
count closes nothing. A stream with no `message_delta` at all — printed without
`--include-partial-messages`, which the Claude backend always passes — settles nothing: every message keeps the count
its last frame carries, and neither hand-backs nor `modelUsage` are read. On the captures the run's output equals the
CLI's `modelUsage` total: 358 on the main run, and 450 on the subagent run, whose lead thread alone reports 314. A
stream with no `assistant` usage falls back to the `result` frame's `usage`. The sanitized Claude Code 2.1.295
captures this accounting is pinned to, and the frame-by-frame evidence behind it, are in
[`usage_claude_stream_capture.py`](../../tests/observability/usage/usage_claude_stream_capture.py).
`parse_codex_usage(stdout, fallback_model=None)` consumes codex `--json` events and treats
usage as cumulative across the session: the *last* non-zero usage record is the authoritative total. Codex prints usage
on `turn.completed` alone, and its block sums every API request of the thread — each request the turn made, and on
`exec resume` the requests of the invocations before it too, so a resumed run's counters include theirs. No frame names
the model, so the configured `-m` model the caller passes as `fallback_model` is what an estimate is priced as.
`parse_agent_usage(backend, stdout, fallback_model=None, span=None)` dispatches by backend string the same way
`agents.runner.run_agent` does, handing an Antigravity parse the `span` its dated Gemini rows are resolved over, as the
Antigravity usage span below describes.

**Claude cache lifetimes.** A Claude usage block reports its cache writes twice: `cache_creation_input_tokens` is
their aggregate, and the `cache_creation` object splits it by lifetime into `ephemeral_5m_input_tokens` and
`ephemeral_1h_input_tokens`, which the
[prompt-caching contract](https://platform.claude.com/docs/en/build-with-claude/prompt-caching) documents as summing to
the aggregate. Claude Code prints both on every `assistant`, hand-back, and `result` usage block; on the captures the
lead thread writes one-hour entries and the subagent five-minute ones. `claude_requests.cache_writes` counts each write
once, under the lifetime the block reports for it, and the estimate prices it at that lifetime's rate. A write the block
gives no lifetime is counted under an unknown one, which no rate prices, so the estimate states no amount instead of a
five-minute or one-hour guess: the whole of a nonzero aggregate printed with no split or with a split that is no object,
and the part of an aggregate a partial split leaves over. A lifetime field holding anything but a non-negative whole
number — a fraction, an infinite or NaN value, a string, a bool — is unreported, read before any coercion could round it
into a count; a float such as `600.0` is the whole number it spells. A split claiming more writes than its aggregate
holds, beside a zero aggregate too, contradicts it: the block establishes neither its write count nor its prompt, so it
keeps the aggregate as its cache-write count, all of it under the unknown lifetime, and the row records the conflict
apart from any token count (`conflicting_writes`) and has no price on any model. With no aggregate, a split reporting
both lifetimes is the whole write count, and one reporting a single lifetime counts those writes alone.
`cache_write_tokens` is the aggregate wherever a block reports one and the lifetimes summed otherwise, and an explicit
zero is a count like any other.

**Claude request pricing.** Each usage row carries a scope. A `message` row is one API message's usage block, so its
input, cache reads, and cache writes are that request's prompt; a `handback-output` row holds only the output count
of a subagent's closing message; a `result-total` row is the `result` frame's usage, a sum over the lead thread's
requests. Every row is priced on its own (`ClaudeUsageRow.estimate`) and the run's estimate is those prices summed,
one unpriced row leaving the whole estimate `unknown-price`; each turn is priced through the same call, and a
CLI-reported cost still outranks the run's estimate, as the cost precedence below says. A request-tiered model is
priced only on a row that establishes its prompt. Claude Haiku 5.5 charges its higher rates on every class, output
included, to a request whose input, cache reads, and cache writes together exceed 100,000 tokens, cache hits counted,
so each message is measured alone: a request at or under the threshold pays the base rates however far the run's
requests add up past it. A `handback-output` or `result-total` row, or a message missing its input, cache-read, or
whole cache-write count, establishes no prompt and leaves a Haiku 5.5 estimate `unknown-price`. A flat-rate model
prices such rows at its one set of rates, since summing requests changes nothing it charges. With the CLI's reported
cost cut from the captures, the main run's estimate equals that cost, and the subagent run's equals it less the
prompt of the subagent's closing message, whose input and cache counts the run leaves out.

**Claude output counts recorded before the correction.** The parser kept the last `assistant` frame's output count,
the one at the start of each message: 31 output tokens on the main capture, where the CLI reports 358, and 92 on the
subagent capture against 450. The correction is included in [v0.14.0](../release-timeline.md#v0140); v0.13.0 and every
earlier release record the start counts.
[Pull request #2199](https://github.com/chippingway/chipping-orchestrator/pull/2199) identifies the source-checkout
boundary: a checkout after the v0.13.0 tag can contain the correction while still
reporting `0.13.0`, so its history determines which accounting it uses. Records carry no orchestrator version: the
boundary for recorded usage is when the host started running the corrected build. Records already written keep their
values: `output_tokens` on `agent_exit` and `agent_trajectory`
lines, the analytics database rows synced from them, and the pinned `issue_total_tokens` an issue accumulated, along
with `issue_total_cost_usd` where a run's cost was `estimated` from the undercount. Nothing backfills them, and an
issue in flight across the upgrade mixes both in its counters. The correction leaves input and cache counts, and a
CLI-reported `cost_usd`, unchanged.

**Claude estimates recorded before the lifetime correction.** v0.14.0 and every earlier release price a block's
aggregate `cache_creation_input_tokens` at the five-minute rate whenever the block carries one, as Claude Code's always
do, so a one-hour write was priced at the five-minute rate, and they price each model's summed usage rather than each
request. A source checkout after the v0.14.0 tag still reports `0.14.0`, so its history, not its version, decides
which pricing it records, and records carry no orchestrator version. Records already written keep their values: an
`estimated` `cost_usd` on `agent_exit` lines, every trajectory turn's estimate, the analytics rows synced from them,
and the pinned issue totals those runs fed, as does an `unknown-price` an earlier build recorded for a Claude model
it did not price. Nothing reprices them. A CLI-reported `cost_usd` is unchanged.

**Codex cache writes.** What a Codex usage block establishes is pinned to codex-cli 0.166.0 captures, run with the
backend's own flags against a local stand-in for the Responses API whose scripted usage sits beside each stream in
[`usage_codex_usage_capture.py`](../../tests/observability/usage/usage_codex_usage_capture.py). The block carries five
flat counts: `input_tokens` is the whole input, `cached_input_tokens` the billed cache reads inside it,
`cache_write_input_tokens` the cache writes inside it, and `output_tokens` holds `reasoning_output_tokens`. The write
count is the responses' `input_tokens_details.cache_write_tokens`, with its `cache_write_tokens_details` split into
`ttl_30m_tokens` and `ttl_12h_tokens` dropped — the binary holds neither name — and printed as `0` where a response
reported no write count at all, so a zero there, the 0.148.0 capture's included, is no evidence that nothing was
written. `codex_rows.codex_usage_record` reads a positive count as that many writes of unknown lifetime and a zero or
an absent field as no write count, and keeps a negative count, which then prices the run on no model. No nested
lifetime field is parsed, since no CLI stream prints one.
`codex_requests.CodexUsageRow.estimate` prices the authoritative record on its own, following
[OpenAI's cache accounting](https://developers.openai.com/api/docs/guides/prompt-caching#monitor-cache-performance),
revalidated on 2026-10-31. A model whose row publishes cache-write rates — GPT-5.6 and later, a 30-minute write at
1.25× ordinary input and a 12-hour one at 2.5× — bills as ordinary input the input less its reads and writes, and each
write once, at its lifetime's rate, never the aggregate again. A write of unknown lifetime finds no rate there, and a
record establishing no whole write count cannot separate its ordinary input, so either leaves the run
`unknown-price`; on GPT-5.6 and later every run the CLI prints is one or the other. A model before GPT-5.6 charges no
cache write of its own, so there a write is ordinary input and the run prices its input less its reads at the input
rate. Reads and writes beyond the input, or a negative count, price nothing on any model.

**Codex request tiers.** A usage block sums the thread's requests, so it sizes none of them, and neither does a
difference between two blocks: repeated and cumulative blocks are priced once, on the last. The tiered rows — GPT-5.4
and GPT-5.5 with their pro models, and every GPT-5.6 and GPT-6 row — charge their long-context rates to a request
over 272,000 input tokens, so a run on one prices at the base rates only where its whole input is at or under 272,000,
which keeps every request it sums there too (`PriceRow.rates_for_requests_within`); past it the run is
`unknown-price`, however small each request was. The
captured turn of two requests, at 200,000 and 201,000 input tokens, prints 401,000 and is unpriced on GPT-5.5. The
long-context rates are never charged, since no stream sizes a request past the threshold, and a flat-rate model
prices any run.

**Codex estimates recorded before the request correction.** v0.14.0 and every earlier release price a Codex run's
whole cumulative input at the long-context rates, output included, once it passes 272,000 tokens, and price the input
a cache-read count exceeds at nothing. A source checkout after the v0.14.0 tag still reports `0.14.0`, so its history,
not its version, decides which pricing it records, and records carry no orchestrator version. Records already written
keep their values — an `estimated` `cost_usd` on `agent_exit` lines and trajectory `run_usage`, the analytics rows
synced from them, and the pinned issue totals they fed — as does the `unknown-price` an earlier build recorded for a
GPT-5.6 or GPT-6 row it held dormant. Nothing reprices them. A CLI-reported `cost_usd` is unchanged.

For `agy`, token totals come from the completed `step_update` events in this invocation, deduplicated by step index.
The terminal result's usage and turn counts include earlier conversation turns on a resume, so they are not added
to the per-run counters. `user_input` steps count this invocation's turns; `init.model` supplies the model, falling
back to the configured `--model`. The CLI supplies no USD cost. No completed usage frames means `no-usage`.

**Antigravity usage and its Gemini estimate.** What a step's usage counts is pinned to agy 1.4.10: a fresh run and
its `--conversation` resume, captured with the backend's own flags in
[`usage_agy_stream_capture.py`](../../tests/observability/usage/usage_agy_stream_capture.py) beside the stream
examples the [headless guide](https://antigravity.google/docs/cli/headless/) publishes, and the CLI's conversation
store on the capture host. `init.model` echoes the `--model` slug, only when one was given, and no other frame names
a model. A completed step carries one generation's usage, and every generation the store records, a response's and
each helper generation beside it, names the model the conversation selected, so a `checkpoint` step's usage is priced
as that model's like a response's. `input_tokens` is
the ordinary input alone, apart from `cache_read_tokens`: a step's cache reads exceed its input on nearly every step
the store holds that reads any, and the guide's second turn reads 30,214 cached tokens beside 278 of input. Output
tokens already include thinking tokens: a step's `total_tokens` is its input plus its output, `thinking_tokens`
inside the output. A resumed run's steps are its own, while its `result` usage counts the whole conversation, so the
estimate prices the same deduplicated steps the counters sum, each once.

`agy_requests.API_MODELS` maps a slug to the Gemini API model it is priced as only where the headless guide or the
CLI's model listing names it: `gemini-4-argon-high` and `-medium` to `gemini-4-argon`; `gemini-3.8-flash-high`,
`-medium`, and `-low` (the last from the 1.4.10 listing) to `gemini-3.8-flash`; and `gemini-3.6-flash-high` and
`-medium` to `gemini-3.6-flash`. A thinking level is a setting of the model, not another SKU. Nothing else maps.
Gemini 3.7 Flash stays unpriced: the Developer API
[routes its deprecated ID to 3.8 Flash](https://ai.google.dev/gemini-api/docs/models/gemini-3.7-flash) while
Antigravity still serves a 3.7 deployment, and neither is the other's price. Gemini 3.1 Pro stays unpriced too, since
nothing confirms that it is the `gemini-3.1-pro-preview` SKU or sizes the requests its 200,000-token tier is charged
on. So do the Claude and GPT-OSS models Antigravity also serves, a bare API ID, an unlisted thinking level, and any
other spelling. `agy_requests.estimate` prices a run attributed to exactly one mapped slug: ordinary input at the
input rate, cache reads at the cached-input rate, and output, thinking included, at the output rate, on the active row
in effect throughout the run's usage span (below). It states no amount for a run whose models are mixed or unnamed, a
run any of whose steps spawned a subagent (`subagent_info`), since that conversation's model and usage are not on the
stream, a step reporting a negative count or no count at all, and a run with no span or one a scheduled rate change
falls inside.

**Antigravity usage span.** Gemini 4 Argon and the Flash models change rates on a scheduled date, and the pricing
page names that date and no time zone. `parse_agent_usage` takes the run's `span` — a `price_catalogue.UsageSpan`
of the instants it started and ended — and `record_agent_exit` hands it the `duration_s` seconds that end as the
record is built, right after the run exits. A dated row prices the run only where the same row is in effect on every
calendar date the span touches in any time zone, UTC-12 through UTC+14 (`price_catalogue.active_row_throughout`): a
run ending by 09:59:59 UTC on 2026-11-30 pays Argon's first rates, one starting at or after 12:00 UTC on 2026-12-01
its second, and one touching both dates is `unknown-price`. A parse given no span prices no dated row, so every Gemini
estimate needs one; the Claude and OpenAI rows carry no dates and ignore it.

**Antigravity costs recorded before the estimate.** v0.14.0 and every earlier release record every Antigravity run as
`unknown-price`, and its cache reads with a cache overlap nothing establishes, so its token total is unknown wherever
it read from cache. A source checkout after the v0.14.0 tag still reports `0.14.0`, so its history, not its version,
decides which it records, and records carry no orchestrator version. Records already written keep their values: the
`agent_exit` lines and trajectory `run_usage`, the analytics rows synced from them, and the pinned issue totals they
fed. Nothing reprices them or reads their overlap again.

Antigravity trajectories join each response step's text deltas, retain tool parameters and outcomes, read offered
tools from `init`, and take the final answer only from a successful terminal result. Interrupted response text is
kept in the timeline without becoming a final answer. Skill evidence remains empty because this adapter does not
infer skill loads from Antigravity's tools; no per-turn pricing or source-item accounting is emitted.

Tool lifecycles fold repeated and sparse `step_update` frames by `step_index`, retaining tool identity across partial
updates and recording each step's latest state. The lifecycle reducer reports every indexed tool step whose latest
state is not `DONE`, ensuring earlier background commands remain authoritative even when later status checks finish
and emit terminal output.

**Cost precedence.** A `total_cost_usd` reported by the CLI itself always wins, an explicit `0` included
(`cost_source="reported"`, on the `cli-reported` basis); otherwise the parser prices the usage from an active row of the
price catalogue below and produces an estimate (`"estimated"`, on that provider's API basis). When usage is present but
its model resolves to no active row — or, for Claude, a cache write carries no lifetime, a lifetime split contradicts
its aggregate, or a request-tiered model's row establishes no prompt, as the Claude paragraphs above describe, and for
Codex, a GPT-5.6 or later run's cache writes carry no lifetime or no count, its reads and writes exceed its input, or a
request-tiered model's run passes 272,000 input tokens, as the Codex paragraphs describe, and for Antigravity, a run's
models are mixed or unnamed, a step spawned a subagent or reports no count or a negative one, or the run has no span
one dated row covers throughout, as the Antigravity paragraphs describe — the parser returns
`cost_source="unknown-price"` and `cost_usd=None` — an `incomplete` cost — rather than guess at zero, bill cached
tokens at the input rate, or choose a rate the usage does not establish. An empty stream — or one with
no usage frames at all — yields `"no-usage"`. One selection, `event_stream.select_cost`, builds the run's cost
evidence, and `UsageMetrics.apply_cost` reads `cost_usd` and `cost_source` off it, so the three never disagree.

**Cost basis and completeness.** `cost_evidence.py` defines the cost every surface records and folds. A
`CostEvidence` holds monetary contributions, at most one per basis and in basis order, beside a completeness, and
serializes as `cost_evidence` on `UsageMetrics.to_dict()` and on each Claude `TurnUsage`:

```json
{
  "completeness": "complete",
  "contributions": [
    {"basis": "anthropic-api-estimate", "amount_usd": 0.42, "rates_verified_on": ["2026-10-29"]}
  ]
}
```

A basis says what an amount is:

- `cli-reported` — the USD figure the agent CLI printed for the run (Claude's `total_cost_usd`). Its origin is the CLI;
  nothing here verifies it against an invoice, a subscription, or a credit balance, so it is never presented as a bill.
- `anthropic-api-estimate`, `openai-api-estimate`, `gemini-api-estimate` — a token-only list-price equivalent: the
  run's observable usage priced at that provider's Standard first-party API rates from active catalogue rows, with
  `rates_verified_on` naming each row's verification date. Claude estimates are on the Anthropic basis, Codex
  estimates on the OpenAI one, and Antigravity estimates on the Gemini one.
- `unknown` — an amount recorded with no basis. No parser writes it; a reader files under it the `cost_usd` of a record
  that carries no `cost_evidence`.

Completeness is `complete` (the contributions cover all the observable usage), `incomplete` (some usage carries no
amount, so the contributions are at most a subtotal — today an unpriced run states none), `no-usage` (the stream
showed nothing to price), or `unknown` (nothing states it). `complete_usd` is the total only when it is complete, which
is what `cost_usd` records, so an `unknown-price` cost never exposes a complete amount; `basis` is the sole
contribution's basis, `blended` across several. A complete zero keeps its contribution: spend of zero, not an absence.

An estimate excludes everything its token rates do not price: subscriptions, included quotas, credits, negotiated or
discounted prices, service-tier and regional adjustments outside the declared Standard basis (Batch, Flex, Priority,
data residency, and Claude's fast mode, which a usage block names in its `speed` field), cache storage, grounding and
search, and every other non-token charge. That matters most for Codex,
which can run on a ChatGPT plan's subscription or credits as well as on an API key:
[Codex pricing](https://developers.openai.com/codex/pricing) states that Codex credit billing has no separate
cache-write charge and that GPT-6.1 Sol usage drawn from a subscription has no long-context surcharge, while API-key
usage follows API pricing. An `openai-api-estimate` therefore prices usage on the API's terms, which charge GPT-5.6 and
later cache writes and long-context requests where the account's Codex billing may not; it is an API comparison basis,
never the subscription or credit charge. The
Gemini basis is the same kind of comparison: it prices Antigravity usage at the Gemini API's rates for the model a
slug maps to, and establishes no Antigravity charge — no plan, quota, or credit Antigravity draws on, and no proof
that Antigravity serves a request as the API would.

`recorded_cost(record)` reads the cost any serialized usage record states — an `agent_exit` line, a trajectory's
`run_usage`, or one of its `turns`. An amount is read only as a non-negative finite number a float holds, zero included,
so a negative amount or one too large for a float is no amount at all. A record without `cost_evidence`, or with
evidence this format does not serialize — an invalid amount in it included — is read as `unknown` completeness holding
its `cost_usd`, when that is a valid amount, under the `unknown` basis: nothing is inferred from its `cost_source`, its
backend, or its models, and nothing backfills a provider breakdown for records written before the field existed. The
parsers record a CLI-reported figure as the CLI printed it, so a run whose CLI printed a negative cost carries evidence
this reader refuses and reads back as `unknown` with no amount. `reduce_costs` folds many costs into one: each basis's
amounts are summed on their own, verification dates are unioned, and the result keeps the weakest completeness any input
states — `incomplete` over `unknown` over `complete` over `no-usage` — so a total holding unpriced usage or an amount
with no basis never reads as complete spend. An empty fold is `no-usage`; the reduced evidence serializes and reads back
in the same shape.

**Token-count semantics.** The raw counters keep each provider's own meaning, and `token_evidence.py` states it beside
them as `token_evidence` on `UsageMetrics.to_dict()` and each `TurnUsage`: `observed`, the counters the stream's usage
payloads reported a count for, and `cache_overlap`, how the cache counters relate to the input counter. A reported zero
is observed; a counter `observed` does not name is missing evidence rather than a zero, even though its raw field reads
`0`. The decoders keep the two apart by reading every field through `token_evidence.reported_count` / `first_count`,
which answer `None` for a field no spelling of it reported — an infinite or NaN value, never a count, included, so one
never stops a stream's parse — and keeping only the token classes a payload reported a count for. A missing class still
sums as zero and costs nothing, so no counter or flat-rate estimate changes with it; only a request-tiered Claude model
needs every input and cache class of a message to size its prompt.

| Backend | Counters a usage payload can report | `cache_overlap` |
| --- | --- | --- |
| `claude` | `input_tokens`, `output_tokens`, `cache_read_tokens`, `cache_write_tokens` | `disjoint` |
| `codex` | `input_tokens`, `output_tokens`, `cached_tokens` | `within-input` |
| `agy` | `input_tokens`, `output_tokens`, `cache_read_tokens` | `disjoint` |

A Claude run observes a counter once any usage row it sums reported one, and a turn what its own row reported. Claude's
usage blocks count ordinary input apart from cache reads and writes, and a block omitting a cache field observes none of
it. A subagent hand-back turn observes `output_tokens` alone, since the stream prints only that count for the closing
message, and its estimate prices that count alone where the model's rates are flat, while on Haiku 5.5, whose rate
depends on a request the stream does not size, it states no amount; a run's own input and cache counters still leave
that message out, as the provider parsing above describes. A Codex run observes what its authoritative record
reported: the last one reporting any tokens, or, when every one reports only zeros, the last record reporting a count
at all — those zeros were measured, so they are observed, while such a stream still has `no-usage` cost. Codex's
`cached_tokens` is the part of its input served from cache, and it records no cache-read or cache-write counter: its
`cache_write_input_tokens`, a part of its input too, is read by the estimate alone. An Antigravity run observes a
counter once any completed step reported one, and its cache reads sit beside its input, as the Antigravity paragraphs
above establish.

`non_overlapping_total(record)` is the shared way to add the counters up: every observed counter once, a cache counter
left out only where it sits `within-input` of an input count that was itself observed — a cache count with no
observed input to hold it is counted on its own. Beside an observed input, a nonzero cache counter of `unknown` overlap
leaves the total `None`, never guessed either way, and so does an observed counter holding no count `is_count` accepts
(a non-negative integer) — null, negative, a bool, or a number spelled as a string. `recorded_tokens(record)` is the
evidence a record is read with: the `token_evidence` it states, or, for a record without it, the counters it holds and
an unknown overlap, so such a record totals only when none of its cache counters is nonzero. The trajectory viewer
reads each `run_usage` and turn through `recorded_cost` and `recorded_tokens` alike, and each counter through
`is_count`, so the totals it shows are the ones this reader gives. The analytics sync reads each `agent_exit` record
through the same two readers and stores what they answer — the amount per basis, the completeness, the estimate dates,
and the non-overlapping total — as [columns the database sums](analytics-database.md#usage-evidence-columns).

**Price catalogue.** `prices.py` holds one table of rows per provider — Anthropic, OpenAI, and Gemini — at Standard
first-party API list rates in USD per million tokens, each row recording the date it was last checked against its
provider's page (`verified_on`, 2026-10-29 for every row):
[Claude pricing](https://platform.claude.com/docs/en/about-claude/pricing),
[OpenAI pricing](https://developers.openai.com/api/docs/pricing) with each model's page for its aliases and snapshots,
and [Gemini pricing](https://ai.google.dev/gemini-api/docs/pricing). A row answers to its canonical model ID, the
documented aliases, and the published snapshot IDs listed on it, each compared whole and case-sensitively. No prefix,
substring, or suffix resolves: an unknown version, an unpublished snapshot, a partner-platform ID such as Bedrock's
`anthropic.` form or a Google Cloud `@` snapshot, and an arbitrary suffix such as `[1m]` stay `unknown-price` rather
than inheriting a neighbour's rates. The retired Claude Opus 4 and 4.1, Sonnet 4, and 3.5 Haiku keep their rows and
their documented aliases (`claude-opus-4-0`, `claude-opus-4-1`, `claude-sonnet-4-0`, `claude-3-5-haiku-latest`), and the
shut-down `gpt-5-chat-latest` through `gpt-5.3-chat-latest` IDs keep the rates their model pages publish: a shut-down
model's `-latest` ID names that one model. Models the pages do not price (Claude 3 Opus and Haiku, the Claude 3.5 and
3.7 Sonnets, and a bare `gpt-5.3`) carry no row, nor does the bare `chat-latest`, which moves with OpenAI's current chat
model.

A row publishes each token class its page prices: Claude's five-minute and one-hour cache writes beside input, cache
reads, and output; OpenAI's input, cached input, and output, with 30-minute and 12-hour cache writes where the page
lists them; Gemini's input, cached input, and output including thinking tokens. A class the page leaves blank, such as
the pro models' cached input, has no rate, so tokens of that class leave the estimate unknown. A model-specific
request tier carries the whole set of rates a request pays once its prompt exceeds the threshold: Claude Haiku 5.5
above 100,000 prompt tokens, the GPT-5.4, GPT-5.5, GPT-5.6, and GPT-6 families above 272,000 input tokens, and Gemini
3.1 Pro Preview above 200,000. The Claude estimate applies Haiku 5.5's tier to each API message's own prompt, as
the request pricing above describes; the Codex estimate prices a tiered row's base rates only under a bound on every
request, and its tier never, as the Codex request tiers above describe; and the Antigravity estimate prices no tiered
row, since no slug it maps is one.

A provider-scheduled change is two rows over consecutive inclusive dates, and a dated row resolves only for a usage
date inside its interval, and prices a run only for a usage span it covers on every date the span touches in any time
zone, as the Antigravity usage span above describes: Gemini 4 Argon is $2 / $0.10 / $10 for input, cached input, and
output through 2026-11-30 and $4 / $0.20 / $20 from 2026-12-01; Gemini 3.8 Flash and 3.6 Flash are $0.75 / $0.075 /
$3.75 through 2026-12-31 and $1.50 / $0.15 / $7.50 from 2027-01-01, rates the Gemini page still listed when
revalidated on 2026-10-31. GPT-5.6 Sol's promotional rates are guaranteed at least through
2026-11-21; the row records that date as a review trigger (`review_after`), which changes no rate by itself.

Only active rows price a run: every Claude row — Opus 4 through 5.5, Sonnet 4 through 5.5, Fable 5 and 5.1, and Haiku
3.5, 4.5, and 5.5, since the Claude accounting prices each message's cache writes and request tier as billed — and
every OpenAI row: GPT-5 through GPT-5.5 with their Codex and chat models, GPT-5.6 Sol (also `gpt-5.6`), Terra, and
Luna, GPT-6 Astra, Sol, and Luna, and GPT-6.1 Sol and Terra, since the Codex accounting prices a cache write only at a
lifetime its record reports and a tier only under a bound on every request. The Gemini 4 Argon, 3.8 Flash, and 3.6
Flash rows are active too, since the Antigravity accounting prices a mapped slug's steps at them over a span one row
covers. Gemini 3.1 Pro Preview is the one dormant row — resolvable for its identity and rates, but priced by nothing,
since no Antigravity slug is established as that SKU — so nothing a parser reads is priced on it. No Gemini 3.7 row
exists: the Developer API routes that deprecated ID to 3.8. The restricted Claude Mythos and OpenAI Daybreak (cyber)
models carry no row, since no captured stream shows a harness emitting their IDs and `gpt-5.6-cyber` names whichever
cyber model is current; nor does any `gpt-5.6-pro`, which OpenAI does not publish.

**Resilience.** Malformed JSON lines (banner text, truncated frames, partial flushes) are silently skipped so a single
bad line never invalidates the rest of the stream. `_run_agent_tracked` (in `workflow/engine/usage.py`) calls
`parse_agent_usage` after every tracked agent run and appends the parsed counts to the
[analytics sink](event-streams.md#analytics-sink-analytics_log_path) under `event="agent_exit"`; a
parser exception is caught and downgraded to a `log.exception`.

**Terminal verdict surface.** Beyond the analytics sink, every invoked run's parsed `UsageMetrics` is counted on
per-issue totals on the pinned state (`issue_agent_runs` / `issue_total_tokens` /
`issue_total_tokens_unknown_runs` / `issue_total_cost_usd` / `issue_cost_sources` / `issue_cost_evidence` /
`issue_unevidenced_runs`; see [state-machine/labels-and-state.md][pinned-state]). Each run is read as its usage
record serializes it: its non-overlapping token total is added where its token evidence settles one, and the run is
counted among those whose total is unknown where it does not; its cost evidence is reduced into the issue's with
`reduce_costs`, one summed amount per basis beside the weakest completeness any run states. When an issue reaches a
terminal, `_format_issue_usage_verdict` renders those totals into one visible receipt line posted on the issue
thread, `:receipt: this issue: N agent runs · T tokens · <cost>`, its cost worded by the same `cost_text` owner the
dashboard and trajectory viewer use:

| Totals state | Receipt cost |
| --- | --- |
| A CLI-reported amount alone | `$0.87 (CLI-reported)` |
| Antigravity usage priced on Gemini's API rates alone | `$0.42 (Gemini API token estimate)` |
| Amounts on several bases | `$1.29 (blended: CLI-reported $0.87 + Gemini API token estimate $0.42)` |
| A known amount beside unpriced usage | `$0.87 (CLI-reported, incomplete subtotal)` |
| Unpriced usage alone | `unpriced` |
| Runs that printed no usage | `no usage` |
| An earlier build's totals, which keep no evidence | `$0.87 (basis unknown, completeness unknown)` |
| Runs counted after those | `$1.37 (blended: CLI-reported $0.50 + basis unknown $0.87, completeness unknown)` |

The token figure says which runs it settles no total for — `T tokens (subtotal: token total unknown for 1 run)` for
a run whose cache overlap nothing establishes, and `(2 runs counted without usage evidence)` for an earlier build's
runs, which stay unknown in basis, completeness, and overlap however many runs follow them. Nothing is inferred from
`issue_cost_sources`, and no receipt already posted is rewritten. The PR merged / rejected finalizers and the
closed-`question` terminal post it as a standalone tracked comment; the `umbrella` close comment appends it. It is a
read-only summary — nothing gates on the figure — and it is skipped when no run was ever counted.

**Accounting checkpoint.** The counters have one writer: the accounting checkpoint
(`workflow/engine/usage_checkpoint.py`), which `_run_agent_tracked` asks of every result a process returns, right
after the usage is parsed and before any pause, interruption, timeout, wrapper, or stage disposition can discard the
result. It lands one invoked run's increment on the usage totals exactly once, keyed by the identity
`_run_agent_tracked` stamps on each process's result (`AgentResult.invocation`) rather than by a request fingerprint
or a CLI session id, together with a bounded `issue_usage_receipts` ledger in one guarded commit, and refuses parsed
usage no total can take — a negative count, a negative cost or one no float holds, or cost evidence no usage record
carries. Every role is counted there — developer, reviewer, the initial and late decomposer, question, discussion,
documentation, and conflict runs — and so
is each attempt of a wrapper that hands its caller only the last: a poisoned session's fresh retry and an Antigravity
command-recovery continuation are two exits, each counted. An exit whose decision is withheld is counted all the same:
a live pause, a shutdown kill, a timeout, a failure, an incomplete run, a reviewer subject that moved, a refused
report, or a verdict with no room. The count buys none of those decisions a replay. The parser's meanings are
unchanged by it: a `None` usage adds nothing, a `no-usage` run counts one exit with no cost, and an unpriced run
leaves the cost total as it stands and the cost evidence an `incomplete` subtotal.

What the checkpoint landed is laid back onto the caller's state as the comment's, so the stage's own write behind it
neither counts the run again nor puts the totals back as the handler read them, and no other field the handler staged
is persisted by it. A held return writes that accounting and nothing else of the run. A checkpoint that neither landed
nor read back covered — refused, or sent and never confirmed — leaves the result `unaccounted` and the caller's state
withheld from every whole-state write, and holds the run's disposition and any further invocation its wrapper would
make, as a live pause does; the next tick reads the comment afresh, and a lost response is settled there by its
receipt rather than counted twice. So an observed exit is retained only where a usable checkpoint lands: a process
lost before its checkpoint, or one whose checkpoint is refused, is an exit this meter never counts, and nothing
reconstructs it from the analytics or audit sinks, which stay observational. See
[state-machine/labels-and-state.md][pinned-state] for its fields and refusals.

`issue_agent_runs` has one reader outside that receipt: the lifetime agent-run ledger on
`workflow/engine/run_ledger.py` never reads `agent_runs_used` below it, so a ledger count that is missing or
unreadable refunds nothing this meter counted. The two count the same unit but not the same set — the ledger
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
`TurnUsage` per turn: `model`, `input_tokens` / `output_tokens`, `cache_read_tokens` / `cache_write_tokens` (every
cache write, whatever its lifetime), and an always-*estimated* `cost_usd` / `cost_source` (`"estimated"`, or
`"unknown-price"` with `cost_usd=None` for an unpriced SKU, a cache write of no lifetime, a lifetime split
contradicting its aggregate, or a request-tiered model's turn whose prompt is unknown — a reported `total_cost_usd` is
a run-level figure and never reaches a turn). A turn's
`output_tokens` is settled exactly as in the run parser above — its message's final count where the stream shows one,
the start count its frames carry where it does not — while its input and cache counts are the frames'. Where hand-backs
are read, a subagent's closing message, which printed no frame and so stamped no step, becomes a turn of its own
numbered after every turn the steps carry, holding the hand-back's output count alone; the turns the frames gave keep
their indices. Both builders settle their rows through `claude_settlement.ClaudeSettlement`, and each turn is priced on
the same `claude_requests.ClaudeUsageRow.estimate` call the run estimate sums its rows through, each turn carrying its
own Anthropic-basis cost evidence and the token evidence above. Unless the run totals fall back to the `result` frame,
the per-turn token counts therefore sum to `parse_claude_usage`'s run totals, and the per-turn estimates to its estimate
wherever every turn is priced; a turn that is not leaves the run's estimate `unknown-price` too.
`parse_codex_trajectory(stdout)` normalizes each
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
