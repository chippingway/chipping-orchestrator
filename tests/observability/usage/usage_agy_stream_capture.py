# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Antigravity headless streams: two runs captured from agy 1.4.10, and the usage examples its headless guide publishes.

The captures ran on 2026-10-31 with the flags the Antigravity backend passes -- `agy --output-format stream-json
--input-format text --print-timeout <budget> --model gemini-3.8-flash-medium --print <prompt>`, the second adding
`--conversation <id>` to resume the first -- in an empty scratch directory. What they establish beside the guide
(https://antigravity.google/docs/cli/headless/):

- `init.model` echoes the `--model` slug, and no other frame names a model.
- A completed `agent_response` step carries one usage block whose `total_tokens` is its `input_tokens` plus its
  `output_tokens`: the `thinking_tokens` sit inside `output_tokens` (31 of the first run's 32), never beside them.
- The resumed run prints only its own steps, numbered after the first run's, while its `result` usage and `num_turns`
  count the whole conversation: 13,899 input tokens, the first run's 6,827 and its own 7,072.

Neither capture read from cache. The guide's examples carry what they do not: a `checkpoint` step reporting usage of
its own beside the response's, and a second turn reading 30,214 cached tokens beside 278 of input -- more than any
input holding them could, so the input counts only what the cache did not serve.

The captured lines are verbatim but for three edits: the conversation id is a stand-in, `cwd` is `/workspace`, and
the `tools` array keeps three of the 60 names the CLI listed. The guide's lines are as it publishes them.
"""

CLI_VERSION = "1.4.10"
MODEL = "gemini-3.8-flash-medium"

_FRESH_INIT = (
    '{"event":"init","conversation_id":"5f0c1d2e-3a4b-4c5d-8e6f-7a8b9c0d1e2f",'
    '"init":{"model":"gemini-3.8-flash-medium","cwd":"/workspace","tools":["run_command","view_file",'
    '"write_to_file"],"permission_mode":"always-proceed"}}'
)
_FRESH_PROMPT = (
    '{"event":"step_update","step_update":{"conversation_id":"5f0c1d2e-3a4b-4c5d-8e6f-7a8b9c0d1e2f",'
    '"step_index":0,"state":"DONE","step_type":"user_input"}}'
)
_FRESH_DELTA = (
    '{"event":"step_update","step_update":{"conversation_id":"5f0c1d2e-3a4b-4c5d-8e6f-7a8b9c0d1e2f",'
    '"step_index":1,"state":"ACTIVE","step_type":"agent_response","text_delta":"apple"}}'
)
FRESH_DONE = (
    '{"event":"step_update","step_update":{"conversation_id":"5f0c1d2e-3a4b-4c5d-8e6f-7a8b9c0d1e2f",'
    r'"step_index":1,"state":"DONE","step_type":"agent_response","text_delta":"\n",'
    '"duration_seconds":2.8614652449999998,"usage":{"input_tokens":6827,"output_tokens":32,'
    '"thinking_tokens":31,"cache_read_tokens":0,"total_tokens":6859}}}'
)
_FRESH_RESULT = (
    '{"event":"result","result":{"conversation_id":"5f0c1d2e-3a4b-4c5d-8e6f-7a8b9c0d1e2f","status":"SUCCESS",'
    r'"response":"apple\n","duration_seconds":2.933862876,"num_turns":1,"usage":{"input_tokens":6827,'
    '"output_tokens":32,"thinking_tokens":31,"cache_read_tokens":0,"total_tokens":6859}}}'
)
FRESH_RUN = (_FRESH_INIT, _FRESH_PROMPT, _FRESH_DELTA, FRESH_DONE, _FRESH_RESULT)

_RESUMED_INIT = (
    '{"event":"init","conversation_id":"5f0c1d2e-3a4b-4c5d-8e6f-7a8b9c0d1e2f",'
    '"init":{"model":"gemini-3.8-flash-medium","cwd":"/workspace","tools":["run_command","view_file",'
    '"write_to_file"],"permission_mode":"always-proceed"}}'
)
_RESUMED_PROMPT = (
    '{"event":"step_update","step_update":{"conversation_id":"5f0c1d2e-3a4b-4c5d-8e6f-7a8b9c0d1e2f",'
    '"step_index":2,"state":"DONE","step_type":"user_input"}}'
)
_RESUMED_SYSTEM = (
    '{"event":"step_update","step_update":{"conversation_id":"5f0c1d2e-3a4b-4c5d-8e6f-7a8b9c0d1e2f",'
    '"step_index":3,"state":"DONE","step_type":"system_message","duration_seconds":0.000079407}}'
)
_RESUMED_DELTA = (
    '{"event":"step_update","step_update":{"conversation_id":"5f0c1d2e-3a4b-4c5d-8e6f-7a8b9c0d1e2f",'
    '"step_index":4,"state":"ACTIVE","step_type":"agent_response","text_delta":"apple"}}'
)
RESUMED_DONE = (
    '{"event":"step_update","step_update":{"conversation_id":"5f0c1d2e-3a4b-4c5d-8e6f-7a8b9c0d1e2f",'
    r'"step_index":4,"state":"DONE","step_type":"agent_response","text_delta":"\n",'
    '"duration_seconds":1.83116047,"usage":{"input_tokens":7072,"output_tokens":37,"thinking_tokens":36,'
    '"cache_read_tokens":0,"total_tokens":7109}}}'
)
_RESUMED_RESULT = (
    '{"event":"result","result":{"conversation_id":"5f0c1d2e-3a4b-4c5d-8e6f-7a8b9c0d1e2f","status":"SUCCESS",'
    r'"response":"apple\n","duration_seconds":14.937123348,"num_turns":2,"usage":{"input_tokens":13899,'
    '"output_tokens":69,"thinking_tokens":67,"cache_read_tokens":0,"total_tokens":13968}}}'
)
RESUMED_RUN = (
    _RESUMED_INIT,
    _RESUMED_PROMPT,
    _RESUMED_SYSTEM,
    _RESUMED_DELTA,
    RESUMED_DONE,
    _RESUMED_RESULT,
)

# The guide's stream-json example: a run with no `--model`, so its `init` names none.
_GUIDE_INIT = (
    '{"event":"init","conversation_id":"c3b66b04-872b-4fbe-a3a4-058a026ef20a",'
    '"init":{"cwd":"/home/user/project","tools":["ask_permission","run_command","write_to_file","..."],'
    '"permission_mode":"request-review"}}'
)
_GUIDE_PROMPT = (
    '{"event":"step_update","step_update":{"conversation_id":"c3b66b04-872b-4fbe-a3a4-058a026ef20a",'
    '"step_index":0,"state":"DONE","step_type":"user_input"}}'
)
_GUIDE_RESPONSE = (
    '{"event":"step_update","step_update":{"conversation_id":"c3b66b04-872b-4fbe-a3a4-058a026ef20a",'
    '"step_index":3,"state":"DONE","step_type":"agent_response","text_delta":"Git rebase destructively '
    "rewrites a branch's commit history by systematically detaching its unique commits and sequentially "
    r'reapplying them onto a new base commit.\n","duration_seconds":6.28,"usage":{"input_tokens":10302,'
    '"output_tokens":582,"thinking_tokens":551,"cache_read_tokens":8113,"total_tokens":10884}}}'
)
_GUIDE_CHECKPOINT = (
    '{"event":"step_update","step_update":{"conversation_id":"c3b66b04-872b-4fbe-a3a4-058a026ef20a",'
    '"step_index":4,"state":"DONE","step_type":"checkpoint","duration_seconds":0.53,'
    '"usage":{"input_tokens":116,"output_tokens":7,"thinking_tokens":0,"cache_read_tokens":0,'
    '"total_tokens":123}}}'
)
_GUIDE_RESULT = (
    '{"event":"result","result":{"conversation_id":"c3b66b04-872b-4fbe-a3a4-058a026ef20a","status":"SUCCESS",'
    '"response":"Git rebase destructively rewrites a branch\'s commit history by systematically detaching its '
    r'unique commits and sequentially reapplying them onto a new base commit.\n","duration_seconds":6.88,'
    '"num_turns":1,"usage":{"input_tokens":10418,"output_tokens":589,"thinking_tokens":551,'
    '"cache_read_tokens":8113,"total_tokens":11007}}}'
)
GUIDE_RUN = (_GUIDE_INIT, _GUIDE_PROMPT, _GUIDE_RESPONSE, _GUIDE_CHECKPOINT, _GUIDE_RESULT)

# The second turn of the guide's stdin example, read from cache beside its input.
GUIDE_CACHED_STEP = (
    '{"event":"step_update","step_update":{"conversation_id":"9ec58bfd-4d67-4f5e-83a5-9d907e9c6b1f",'
    r'"step_index":4,"state":"DONE","step_type":"agent_response","text_delta":"apple\n",'
    '"duration_seconds":0.895679386,"usage":{"input_tokens":278,"output_tokens":4,"thinking_tokens":0,'
    '"cache_read_tokens":30214,"total_tokens":282}}}'
)
