# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""`codex exec --json` usage frames captured from codex-cli 0.166.0, beside the API usage each run was answered with.

Four runs captured on 2026-10-31 with the flags the Codex backend passes -- `codex -m <model> exec -C <checkout>
--dangerously-bypass-approvals-and-sandbox --json -o <file> <prompt>`, and `exec resume` with the same flags, the
thread id, and the prompt for the resumed run -- in a scratch git repository, with `CODEX_HOME` a scratch directory.
`-c model_provider=...` pointed the CLI at a local endpoint standing in for the OpenAI Responses API, which answered
each request with one scripted streamed response: the `response.completed` usage of each is listed below in request
order. The counts are therefore scripted. What the capture establishes is the CLI's own handling of them, which no
API page or synthetic fixture shows:

- The only usage frame is `turn.completed`, whose block carries five flat counts: `input_tokens`,
  `cached_input_tokens`, `cache_write_input_tokens`, `output_tokens`, and `reasoning_output_tokens`. No frame names
  the model.
- `input_tokens` is the response's whole `input_tokens`, and `cached_input_tokens` and `cache_write_input_tokens`
  copy `input_tokens_details.cached_tokens` and `input_tokens_details.cache_write_tokens`. The
  `cache_write_tokens_details` split by lifetime never reaches stdout: the 0.166.0 binary holds no `ttl_30m_tokens`
  or `ttl_12h_tokens` name at all.
- A response reporting no `cache_write_tokens` prints `cache_write_input_tokens` as 0, the zero a response reporting
  no writes prints too.
- A turn's block sums its requests: the turn that ran one command made two requests, of 200,000 and 201,000 input
  tokens, and prints 401,000, with nothing on stdout saying how many requests it made or how large any one was.
- A resumed invocation's block sums the whole thread: the earlier invocation's 12,000 input tokens and the resumed
  request's 13,000 print as 25,000.
- No request set `prompt_cache_options` or `prompt_cache_retention`, so the stream is the only source of a write's
  lifetime, and it states none.

The lines are verbatim: no frame of these runs carries a path, a credential, or account data, and the thread ids are
the ones the CLI generated.
"""

CLI_VERSION = "0.166.0"
GPT_FIVE_FIVE = "gpt-5.5"
GPT_FIVE_SIX_SOL = "gpt-5.6-sol"

ONE_REQUEST_MODEL = GPT_FIVE_FIVE
TWO_REQUEST_MODEL = GPT_FIVE_FIVE
RESUMED_MODEL = GPT_FIVE_FIVE
UNREPORTED_WRITES_MODEL = GPT_FIVE_SIX_SOL

ONE_REQUEST_PROMPT = "Say done."
TWO_REQUEST_PROMPT = "Run true, then say done."
RESUMED_PROMPT = "Continue."
UNREPORTED_WRITES_PROMPT = ONE_REQUEST_PROMPT

ONE_REQUEST_THREAD_ID = "01a18fd7-db43-7c71-b03b-74aa533214a2"
TWO_REQUEST_THREAD_ID = "01a18fd7-e2f3-7d70-893a-1fbacf8a2da0"
UNREPORTED_WRITES_THREAD_ID = "01a18fd7-f212-7a20-9ec9-440b6112f8a0"

_TURN_STARTED_LINE = '{"type":"turn.started"}'

_INPUT = "input_tokens"
_INPUT_DETAILS = "input_tokens_details"
_CACHED = "cached_tokens"
_WRITES = "cache_write_tokens"
_OUTPUT = "output_tokens"
_OUTPUT_DETAILS = "output_tokens_details"
_REASONING = "reasoning_tokens"
_TOTAL = "total_tokens"

# The usage each scripted response reported, one entry per request the run made.
ONE_REQUEST_PROVIDER_USAGE = (
    {
        _INPUT: 12000,
        _INPUT_DETAILS: {
            _CACHED: 4000,
            _WRITES: 7000,
            "cache_write_tokens_details": {"ttl_30m_tokens": 3000, "ttl_12h_tokens": 4000},
        },
        _OUTPUT: 500,
        _OUTPUT_DETAILS: {_REASONING: 100},
        _TOTAL: 12500,
    },
)
TWO_REQUEST_PROVIDER_USAGE = (
    {
        _INPUT: 200000,
        _INPUT_DETAILS: {_CACHED: 150000, _WRITES: 30000},
        _OUTPUT: 40,
        _OUTPUT_DETAILS: {_REASONING: 10},
        _TOTAL: 200040,
    },
    {
        _INPUT: 201000,
        _INPUT_DETAILS: {_CACHED: 180000, _WRITES: 1000},
        _OUTPUT: 60,
        _OUTPUT_DETAILS: {_REASONING: 20},
        _TOTAL: 201060,
    },
)
RESUMED_PROVIDER_USAGE = (
    {
        _INPUT: 13000,
        _INPUT_DETAILS: {_CACHED: 11000, _WRITES: 1500},
        _OUTPUT: 70,
        _OUTPUT_DETAILS: {_REASONING: 0},
        _TOTAL: 13070,
    },
)
UNREPORTED_WRITES_PROVIDER_USAGE = (
    {
        _INPUT: 9000,
        _INPUT_DETAILS: {_CACHED: 2048},
        _OUTPUT: 300,
        _OUTPUT_DETAILS: {_REASONING: 64},
        _TOTAL: 9300,
    },
)

_ONE_REQUEST_LINES = (
    f'{{"type":"thread.started","thread_id":"{ONE_REQUEST_THREAD_ID}"}}',
    _TURN_STARTED_LINE,
    '{"type":"item.completed","item":{"id":"item_0","type":"agent_message","text":"Done."}}',
    (
        '{"type":"turn.completed","usage":{"input_tokens":12000,"cached_input_tokens":4000,'
        '"cache_write_input_tokens":7000,"output_tokens":500,"reasoning_output_tokens":100}}'
    ),
)
_TWO_REQUEST_LINES = (
    f'{{"type":"thread.started","thread_id":"{TWO_REQUEST_THREAD_ID}"}}',
    _TURN_STARTED_LINE,
    (
        '{"type":"item.started","item":{"id":"item_0","type":"command_execution",'
        '"command":"/bin/bash -lc true","aggregated_output":"","exit_code":null,'
        '"status":"in_progress"}}'
    ),
    (
        '{"type":"item.completed","item":{"id":"item_0","type":"command_execution",'
        '"command":"/bin/bash -lc true","aggregated_output":"","exit_code":0,"status":"completed"}}'
    ),
    '{"type":"item.completed","item":{"id":"item_1","type":"agent_message","text":"Done."}}',
    (
        '{"type":"turn.completed","usage":{"input_tokens":401000,"cached_input_tokens":330000,'
        '"cache_write_input_tokens":31000,"output_tokens":100,"reasoning_output_tokens":30}}'
    ),
)
# `exec resume` reports the thread it resumed as the one it started.
_RESUMED_LINES = (
    f'{{"type":"thread.started","thread_id":"{ONE_REQUEST_THREAD_ID}"}}',
    _TURN_STARTED_LINE,
    '{"type":"item.completed","item":{"id":"item_0","type":"agent_message","text":"Resumed."}}',
    (
        '{"type":"turn.completed","usage":{"input_tokens":25000,"cached_input_tokens":15000,'
        '"cache_write_input_tokens":8500,"output_tokens":570,"reasoning_output_tokens":100}}'
    ),
)
_UNREPORTED_WRITES_LINES = (
    f'{{"type":"thread.started","thread_id":"{UNREPORTED_WRITES_THREAD_ID}"}}',
    _TURN_STARTED_LINE,
    '{"type":"item.completed","item":{"id":"item_0","type":"agent_message","text":"Done."}}',
    (
        '{"type":"turn.completed","usage":{"input_tokens":9000,"cached_input_tokens":2048,'
        '"cache_write_input_tokens":0,"output_tokens":300,"reasoning_output_tokens":64}}'
    ),
)

ONE_REQUEST_STDOUT = "\n".join(_ONE_REQUEST_LINES)
TWO_REQUEST_STDOUT = "\n".join(_TWO_REQUEST_LINES)
RESUMED_STDOUT = "\n".join(_RESUMED_LINES)
UNREPORTED_WRITES_STDOUT = "\n".join(_UNREPORTED_WRITES_LINES)
