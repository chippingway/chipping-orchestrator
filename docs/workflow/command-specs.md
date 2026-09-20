# Command specs and the in-flight session lock

Each role env var (`DEV_AGENT` / `REVIEW_AGENT` / `DECOMPOSE_AGENT`) holds a **spec**: a backend selector followed by
the CLI args every spawn for that role is given. This page is the grammar those values are parsed by, and the rule
that decides when a change to one of them reaches a running issue. Which stage spawns which role is in
[`roles.md`](roles.md).

## Spec format

`config._parse_agent_spec` runs `shlex.split` over each role's env value and yields `(backend, extra_args)`:

- **First token rule** — must match `codex`, `claude`, or `agy` case-insensitively (`_parse_agent_spec` compares
  `tokens[0].lower()`, so `AGY` and `agy` both select Antigravity). The lowercased form is used
  only for dispatch (`agents.runner.run_agent` keys off it).

  Pinned state stores the **raw spec string verbatim** with its original casing — `DEV_AGENT=CODEX -m gpt-5.5` is
  persisted as the literal `"CODEX -m gpt-5.5"`, and the re-lowercase happens again on every resume when
  `_parse_agent_spec` re-parses the stored value.

  Anything else (full path, alias, typo, empty string, unbalanced quotes) aborts at import with a `SystemExit` so a
  misconfiguration cannot silently fall back to a default backend on the next restart. `DECOMPOSE_AGENT` is parsed at
  import even when `DECOMPOSE=off`, so toggling the kill switch back on never surfaces a fresh "that env var was
  always invalid" failure.
- **Remaining tokens** — forwarded verbatim as backend-CLI args on every spawn for that role. Quoting follows shell
  rules, so values containing `=`, spaces, or nested quotes survive (e.g.
  `codex -m gpt-5.5 -c 'model_reasoning_effort="xhigh"'`).

  For codex the args are placed before the `exec` subcommand (they are codex global options); for claude and agy they
  are placed right after the binary, before the orchestrator's own print / `--dangerously-skip-permissions` /
  `--output-format` flags. The safety/output flags and the prompt stay where they are so operator args cannot silently
  displace them.
- **`CODEX_BIN` / `CLAUDE_BIN` / `AGY_BIN` interaction** — the first token is only a backend selector. It picks the
  matching runner in `agents/backends/`; session-id parsing lives in `agents/session_ids.py`. The actual
  executable launched is `CODEX_BIN` for `codex`, `CLAUDE_BIN` for `claude`, and `AGY_BIN` for `agy`. Set those
  to a full path when the CLI is not on `$PATH`. Writing a full path as the first token of `DEV_AGENT` /
  `REVIEW_AGENT` / `DECOMPOSE_AGENT` is rejected (it would not match `codex` / `claude` / `agy`).

## Examples

All three backends accept model selection plus a reasoning-effort flag. Each example is a valid value for any
of the three role env vars.

```dotenv
# bare backends (defaults)
DEV_AGENT=claude
REVIEW_AGENT=codex
DECOMPOSE_AGENT=claude

# claude with model selection
DEV_AGENT=claude --model claude-opus-4-7
REVIEW_AGENT=claude --model claude-sonnet-4-6

# claude with model + effort
DEV_AGENT=claude --model claude-opus-4-7 --effort high
DECOMPOSE_AGENT=claude --model claude-opus-4-7 --effort medium

# codex with model + reasoning effort
DEV_AGENT=codex -m gpt-5.5 -c 'model_reasoning_effort="xhigh"'
REVIEW_AGENT=codex -m gpt-5.5-codex -c 'model_reasoning_effort="high"'

# Antigravity with model + effort
DEV_AGENT=agy --dangerously-skip-permissions --model gemini-3.8-flash-high --effort high
```

Antigravity must already be authenticated on the host; run `agy` interactively once to sign in. The orchestrator
uses its [headless stream-json protocol](https://antigravity.google/docs/cli/headless/), passes the prompt as the
value of `--print`, and resumes the captured `conversation_id` with `--conversation`. It supplies
`--dangerously-skip-permissions` even for a bare `agy` spec and sets `--print-timeout` from the role's orchestrator
timeout (`AGENT_TIMEOUT`, or `REVIEW_TIMEOUT` for review), overriding the CLI's five-minute default.

## In-flight session lock

The parsed spec is persisted to pinned state as the **durable role identity** for an issue. The point of pinning the
full spec (backend AND args, not just the backend) is that the orchestrator can resume mid-flight without losing the
model / reasoning-effort the session was started with — a `DEV_AGENT` flip between ticks cannot silently retarget the
next resume at a different backend, and it cannot silently drop the args either.

How it works per role:

- **Implementer (`DEV_AGENT`).** `_handle_implementing` writes the current spec verbatim to `dev_agent` (e.g.
  `"codex -m gpt-5.5 -c 'model_reasoning_effort=\"xhigh\"'"`) BEFORE invoking `run_agent`. The write happens
  unconditionally on every fresh spawn, so a backend hiccup that produces commits without surfacing a session id
  (empty codex `-o` file, unparseable claude JSONL line) still anchors the role for the next tick.

  On a resume, `_read_dev_session` re-parses `dev_agent` via `config._parse_agent_spec` to recover `(backend,
  extra_args)` and passes the args through to `run_agent`. `_handle_documenting`, `_handle_validating`,
  `_handle_fixing`, and `_handle_resolving_conflict` all resume the dev session via the same path, so the locked spec
  applies to every dev-side resume for the lifetime of the issue. `_handle_in_review` resumes it on exactly one road,
  the requirements-drift resume its own drift owner runs; fresh PR feedback is routed to `workflow:fixing` instead of
  being resumed there.
- **Decomposer (`DECOMPOSE_AGENT`).** Same mechanic in `_handle_decomposing`: the spec is persisted to
  `decomposer_agent` before the spawn and re-parsed via `_read_decomposer_session` on every resume. The same backend
  (not the same session) also drives the question stage — `_handle_question` reads `DECOMPOSE_AGENT_SPEC` as the
  *fallback* on the first-ever question spawn, then pins what it ran under to `question_agent` (a separate key, parsed
  by `_read_question_session`). The discussion stage pins its own pair the same way (see
  [`conversations.md`](conversations.md)), and the late adjudication of an oversized committed candidate pins a fourth
  to `late_agent`, read back by `_read_late_run`. That fourth pin locks the backend the way the others do, and
  resumes its session for one run in three: a substantive trusted answer to the categorized question the adjudicator
  asked continues the conversation that asked it, while every other late run is a fresh one against the frozen
  candidate (see [`roles.md`](roles.md#what-a-late-adjudication-is-asked-and-what-it-may-answer)).
- **Reviewer (`REVIEW_AGENT`).** Spawned **fresh every round** by `_handle_validating`, so changes to `REVIEW_AGENT`
  take effect on the next validating tick (no migration step needed). The current value is recorded in `review_agent`
  for traceability only; it is not used for resumes.

**Net effect:** a flip of `DEV_AGENT` or `DECOMPOSE_AGENT` reaches a spawn that has no pin to read yet, and nothing
else — the unit the lock protects is the session, not the issue. A live dev session keeps the backend AND args it was
started with until the issue reaches a terminal label (`done` / `rejected`), since every dev-side resume reads the one
`dev_agent` key. The four decomposer-role pins are independent, so an issue whose decomposing session is already
locked can still open its first question or discussion round under the new spec; what a flip cannot do is retarget a
conversation that already pinned one. Flipping `REVIEW_AGENT` takes effect on the next round of any issue in
`workflow:validating`.

### Backward compatibility

- Legacy bare-backend values written before the spec rewrite (`"codex"` / `"claude"` in `dev_agent` /
  `decomposer_agent`) round-trip to `(backend, ())` — no args, matching what those deployments had at the time.
  Persisting them again is a no-op rewrite.
- The pre-spec key `codex_session_id` (written before `dev_agent` existed) is still honored on read and yields
  `spec="codex"`. A config flip to claude cannot strand that session — it stays on codex with no args.

## Quick reference

- The spec format is parsed once at import (`config._parse_agent_spec`) and again at resume time from pinned state, so
  the same validation rules apply to both paths.
- `CODEX_BIN` / `CLAUDE_BIN` / `AGY_BIN` set the executable path; the spec's first token is a backend selector.
- The reviewer is fresh per round; the implementer and decomposer are pinned for the life of the issue session.
- For per-stage handler internals (worktree management, prompt construction, post-spawn branching) see
  [`../state-machine.md#stage-handlers`](../state-machine.md#stage-handlers).
