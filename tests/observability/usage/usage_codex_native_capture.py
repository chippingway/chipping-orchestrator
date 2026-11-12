# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""A sanitized codex-cli 0.167.1 native session log, written by six invocations of one session, beside their stdout.

Captured on 2026-11-12 with the flags the Codex backend passes -- `codex -m <model> exec -C <checkout>
--dangerously-bypass-approvals-and-sandbox --json -o <file> <prompt>`, and `exec resume` with the same flags, the
session id, and a prompt -- in a scratch git repository, with `CODEX_HOME` a scratch directory and `-c
model_provider=...` pointing the CLI at a local endpoint standing in for the OpenAI Responses API, which answered each
request with one scripted streamed response. The counts are therefore scripted; what the capture establishes is what
the CLI writes to `sessions/2026/11/12/rollout-2026-11-12T20-54-56-<session id>.jsonl` around them:

- `FRESH` (`-m gpt-5.5`) ran two commands and answered: three requests, the first two scripted with equal usage.
- `RESUMED` answered in one request.
- `SWITCHED` resumed under `-m gpt-5.6-sol`. The CLI first compacted the thread with one request on gpt-5.5 -- the
  endpoint saw that model -- and wrote the `compacted` line and the turn's `turn_context` naming gpt-5.6-sol only
  after it, then answered in one request on gpt-5.6-sol.
- `FAILED` met a 500 from the endpoint: the turn completes with an error, and no request settles usage.
- `INTERRUPTED` was sent SIGTERM while waiting on its second request: one request settled, and no `task_complete` or
  `turn_aborted` closes the turn.
- `LAST` resumed after it and answered in one request.

What the log shows: every invocation appends to the one file under the date the session began, and a resume writes
no `session_meta` -- only `thread_settings_applied` and a `task_started` naming `turn_trigger` `exec`. Each request
settles as one `event_msg` `token_count` whose `last_token_usage` is that response's usage -- the whole input, the
cache reads and writes within it, a write the response did not report printed as 0 -- and whose `total_token_usage` is
the thread's running sum, earlier invocations included. A `token_usage_record` line beside each repeats the response's
counters under its response id. The switched turn opens with a `token_count` repeating the running sum the resumed
invocation left (line 37), and follows its compaction with one whose running sum does not move and whose
`last_token_usage` is zero but for a `total_tokens` of 9548 (line 45): neither is a request.
`last_usage_includes_reasoning` is false up to the compaction and true after it, and `model_context_window` is
258400 throughout. Every line carries a `timestamp`, never decreasing, and an `ordinal` equal to its line number.

The invocations' stdout is verbatim. The CLI's own launch moments were not recorded, so each `launched_at` below is a
moment between the previous invocation's last line and the invocation's own first line, where a moment read just
before the launch would fall.

Sanitized means the base instructions, the message, tool-call, tool-output, item, and final-answer text are
`transcript canary` -- the user messages also carrying a credential-shaped `CREDENTIAL_CANARY` -- the working directory
is `/workspace`, the git and permission fields, the rate-limit and settings detail beyond the model, and every other
field the collector does not read were dropped. Every id, timestamp, ordinal, counter, model, flag, and the order and
number of the lines are verbatim.
"""

from __future__ import annotations

from datetime import datetime
from typing import NamedTuple

SESSION_ID = "01a1d00a-4509-7b61-a64b-4e8cef36a311"
CLI_VERSION = "0.167.1"
FIRST_MODEL = "gpt-5.5"
SWITCHED_MODEL = "gpt-5.6-sol"
TEXT_CANARY = "transcript canary"
CREDENTIAL_CANARY = "sk-proj-CANARY0123456789abcdefCANARY"
WORKSPACE = "/workspace"
LOG_NAME = f"rollout-2026-11-12T20-54-56-{SESSION_ID}.jsonl"
DAY = ("2026", "11", "12")
CONTEXT_WINDOW = 258400

FRESH_TURN = "01a1d00a-4517-7a62-bcc4-bdb2b510c4aa"
RESUMED_TURN = "01a1d00a-7b63-7f32-b1d1-aa39ec9ecdd4"
SWITCH_TURN = "01a1d010-af94-7fa0-b242-df747cc40630"
FAILED_TURN = "01a1d011-c208-7fb1-afe3-45757b59beb7"
INTERRUPTED_TURN = "01a1d011-d411-7733-89f3-3f97c9a80dea"
LAST_TURN = "01a1d012-2815-78f1-988f-8024684d2e9d"

# The log's lines, in order; a line's place in the tuple is its line number in the file.
_LOG_LINES = (
    (
        '{"timestamp":"2026-11-12T13:54:56.412Z","ordinal":0,"type":"session_meta",'
        '"payload":{"session_id":"01a1d00a-4509-7b61-a64b-4e8cef36a311",'
        '"id":"01a1d00a-4509-7b61-a64b-4e8cef36a311","timestamp":"2026-11-12T13:54:56.398Z","cwd":"/workspace",'
        '"originator":"codex_exec","cli_version":"0.167.1","source":"exec","thread_source":"user",'
        '"model_provider":"fake","base_instructions":{"text":"transcript canary"},"history_mode":"paginated",'
        '"context_window":{"window_id":"01a1d00a-450b-7b01-ae38-41525808ed93"}}}'
    ),
    (
        '{"timestamp":"2026-11-12T13:54:56.412Z","ordinal":1,"type":"event_msg","payload":{"type":"task_started",'
        '"turn_attribution":{"turn_id":"01a1d00a-4517-7a62-bcc4-bdb2b510c4aa","turn_trigger":"exec",'
        '"parent_turn_id":null,"initiating_agent_path":null,"root_turn_id":"01a1d00a-4517-7a62-bcc4-bdb2b510c4aa"},'
        '"turn_id":"01a1d00a-4517-7a62-bcc4-bdb2b510c4aa","root_turn_id":"01a1d00a-4517-7a62-bcc4-bdb2b510c4aa",'
        '"started_at":1794491696,"model_context_window":258400,"collaboration_mode_kind":"default"}}'
    ),
    (
        '{"timestamp":"2026-11-12T13:54:56.485Z","ordinal":2,"type":"response_item","payload":{"type":"message",'
        '"id":"msg_01a1d00a-4564-71c0-982a-2cbf4f7cdaca","role":"developer","content":[{"type":"input_text",'
        '"text":"transcript canary"}]}}'
    ),
    (
        '{"timestamp":"2026-11-12T13:54:56.485Z","ordinal":3,"type":"response_item","payload":{"type":"message",'
        '"id":"msg_01a1d00a-4564-71c0-982a-2ccbede4946d","role":"user","content":[{"type":"input_text",'
        '"text":"transcript canary sk-proj-CANARY0123456789abcdefCANARY"}]}}'
    ),
    (
        '{"timestamp":"2026-11-12T13:54:56.489Z","ordinal":4,"type":"world_state","payload":{"full":true,'
        '"state":{}}}'
    ),
    (
        '{"timestamp":"2026-11-12T13:54:56.493Z","ordinal":5,"type":"turn_context",'
        '"payload":{"turn_id":"01a1d00a-4517-7a62-bcc4-bdb2b510c4aa",'
        '"root_turn_id":"01a1d00a-4517-7a62-bcc4-bdb2b510c4aa","cwd":"/workspace","model":"gpt-5.5"}}'
    ),
    (
        '{"timestamp":"2026-11-12T13:54:56.493Z","ordinal":6,"type":"event_msg",'
        '"payload":{"type":"thread_settings_applied","thread_id":"01a1d00a-4509-7b61-a64b-4e8cef36a311",'
        '"thread_settings":{"model":"gpt-5.5","cwd":"/workspace"}}}'
    ),
    (
        '{"timestamp":"2026-11-12T13:54:56.505Z","ordinal":7,"type":"response_item","payload":{"type":"message",'
        '"id":"msg_01a1d00a-4579-7500-bbf1-c37211f7bfaa","role":"user","content":[{"type":"input_text",'
        '"text":"transcript canary sk-proj-CANARY0123456789abcdefCANARY"}]}}'
    ),
    (
        '{"timestamp":"2026-11-12T13:54:56.508Z","ordinal":8,"type":"event_msg","payload":{"type":"item_completed",'
        '"thread_id":"01a1d00a-4509-7b61-a64b-4e8cef36a311","turn_id":"01a1d00a-4517-7a62-bcc4-bdb2b510c4aa",'
        '"item":{"type":"UserMessage","id":"01a1d00a-4579-7500-bbf1-c38f0662d434","text":"transcript canary"}}}'
    ),
    (
        '{"timestamp":"2026-11-12T13:54:56.570Z","ordinal":9,"type":"response_item",'
        '"payload":{"type":"function_call","id":"fc_0","name":"exec_command","arguments":"transcript canary",'
        '"call_id":"call_0"}}'
    ),
    (
        '{"timestamp":"2026-11-12T13:54:56.572Z","ordinal":10,"type":"token_usage_record",'
        '"payload":{"thread_id":"01a1d00a-4509-7b61-a64b-4e8cef36a311",'
        '"turn_id":"01a1d00a-4517-7a62-bcc4-bdb2b510c4aa","session_id":"01a1d00a-4509-7b61-a64b-4e8cef36a311",'
        '"root_turn_id":"01a1d00a-4517-7a62-bcc4-bdb2b510c4aa","response_id":"resp_0000",'
        '"usage":{"input_tokens":12000,"cached_input_tokens":4000,"cache_write_input_tokens":7000,'
        '"output_tokens":500,"reasoning_output_tokens":100,"total_tokens":12500}}}'
    ),
    (
        '{"timestamp":"2026-11-12T13:54:56.621Z","ordinal":11,"type":"event_msg",'
        '"payload":{"type":"item_completed","thread_id":"01a1d00a-4509-7b61-a64b-4e8cef36a311",'
        '"turn_id":"01a1d00a-4517-7a62-bcc4-bdb2b510c4aa","item":{"type":"CommandExecution","id":"call_0",'
        '"text":"transcript canary"}}}'
    ),
    (
        '{"timestamp":"2026-11-12T13:54:56.624Z","ordinal":12,"type":"response_item",'
        '"payload":{"type":"function_call_output","id":"fco_01a1d00a-45f0-79c1-ab70-fcc704466ddf",'
        '"call_id":"call_0","output":"transcript canary"}}'
    ),
    (
        '{"timestamp":"2026-11-12T13:54:56.625Z","ordinal":13,"type":"event_msg","payload":{"type":"token_count",'
        '"info":{"total_token_usage":{"input_tokens":12000,"cached_input_tokens":4000,'
        '"cache_write_input_tokens":7000,"output_tokens":500,"reasoning_output_tokens":100,"total_tokens":12500},'
        '"last_token_usage":{"input_tokens":12000,"cached_input_tokens":4000,"cache_write_input_tokens":7000,'
        '"output_tokens":500,"reasoning_output_tokens":100,"total_tokens":12500},'
        '"last_usage_includes_reasoning":false,"model_context_window":258400},"rate_limits":{"limit_id":"codex",'
        '"limit_name":null,"primary":null,"secondary":null,"credits":null,"individual_limit":null,'
        '"spend_control_reached":null,"plan_type":null,"rate_limit_reached_type":null}}}'
    ),
    (
        '{"timestamp":"2026-11-12T13:54:56.640Z","ordinal":14,"type":"response_item",'
        '"payload":{"type":"function_call","id":"fc_1","name":"exec_command","arguments":"transcript canary",'
        '"call_id":"call_1"}}'
    ),
    (
        '{"timestamp":"2026-11-12T13:54:56.642Z","ordinal":15,"type":"token_usage_record",'
        '"payload":{"thread_id":"01a1d00a-4509-7b61-a64b-4e8cef36a311",'
        '"turn_id":"01a1d00a-4517-7a62-bcc4-bdb2b510c4aa","session_id":"01a1d00a-4509-7b61-a64b-4e8cef36a311",'
        '"root_turn_id":"01a1d00a-4517-7a62-bcc4-bdb2b510c4aa","response_id":"resp_0001",'
        '"usage":{"input_tokens":12000,"cached_input_tokens":4000,"cache_write_input_tokens":7000,'
        '"output_tokens":500,"reasoning_output_tokens":100,"total_tokens":12500}}}'
    ),
    (
        '{"timestamp":"2026-11-12T13:54:56.683Z","ordinal":16,"type":"event_msg",'
        '"payload":{"type":"item_completed","thread_id":"01a1d00a-4509-7b61-a64b-4e8cef36a311",'
        '"turn_id":"01a1d00a-4517-7a62-bcc4-bdb2b510c4aa","item":{"type":"CommandExecution","id":"call_1",'
        '"text":"transcript canary"}}}'
    ),
    (
        '{"timestamp":"2026-11-12T13:54:56.685Z","ordinal":17,"type":"response_item",'
        '"payload":{"type":"function_call_output","id":"fco_01a1d00a-462d-7402-bac1-690694e00a60",'
        '"call_id":"call_1","output":"transcript canary"}}'
    ),
    (
        '{"timestamp":"2026-11-12T13:54:56.686Z","ordinal":18,"type":"event_msg","payload":{"type":"token_count",'
        '"info":{"total_token_usage":{"input_tokens":24000,"cached_input_tokens":8000,'
        '"cache_write_input_tokens":14000,"output_tokens":1000,"reasoning_output_tokens":200,"total_tokens":25000},'
        '"last_token_usage":{"input_tokens":12000,"cached_input_tokens":4000,"cache_write_input_tokens":7000,'
        '"output_tokens":500,"reasoning_output_tokens":100,"total_tokens":12500},'
        '"last_usage_includes_reasoning":false,"model_context_window":258400},"rate_limits":{"limit_id":"codex",'
        '"limit_name":null,"primary":null,"secondary":null,"credits":null,"individual_limit":null,'
        '"spend_control_reached":null,"plan_type":null,"rate_limit_reached_type":null}}}'
    ),
    (
        '{"timestamp":"2026-11-12T13:54:56.698Z","ordinal":19,"type":"event_msg",'
        '"payload":{"type":"item_completed","thread_id":"01a1d00a-4509-7b61-a64b-4e8cef36a311",'
        '"turn_id":"01a1d00a-4517-7a62-bcc4-bdb2b510c4aa","item":{"type":"AgentMessage","id":"msg_2",'
        '"text":"transcript canary"}}}'
    ),
    (
        '{"timestamp":"2026-11-12T13:54:56.699Z","ordinal":20,"type":"response_item","payload":{"type":"message",'
        '"id":"msg_2","role":"assistant","content":[{"type":"output_text","text":"transcript canary"}]}}'
    ),
    (
        '{"timestamp":"2026-11-12T13:54:56.700Z","ordinal":21,"type":"token_usage_record",'
        '"payload":{"thread_id":"01a1d00a-4509-7b61-a64b-4e8cef36a311",'
        '"turn_id":"01a1d00a-4517-7a62-bcc4-bdb2b510c4aa","session_id":"01a1d00a-4509-7b61-a64b-4e8cef36a311",'
        '"root_turn_id":"01a1d00a-4517-7a62-bcc4-bdb2b510c4aa","response_id":"resp_0002",'
        '"usage":{"input_tokens":13000,"cached_input_tokens":11000,"cache_write_input_tokens":0,"output_tokens":70,'
        '"reasoning_output_tokens":0,"total_tokens":13070}}}'
    ),
    (
        '{"timestamp":"2026-11-12T13:54:56.701Z","ordinal":22,"type":"event_msg","payload":{"type":"token_count",'
        '"info":{"total_token_usage":{"input_tokens":37000,"cached_input_tokens":19000,'
        '"cache_write_input_tokens":14000,"output_tokens":1070,"reasoning_output_tokens":200,"total_tokens":38070},'
        '"last_token_usage":{"input_tokens":13000,"cached_input_tokens":11000,"cache_write_input_tokens":0,'
        '"output_tokens":70,"reasoning_output_tokens":0,"total_tokens":13070},'
        '"last_usage_includes_reasoning":false,"model_context_window":258400},"rate_limits":{"limit_id":"codex",'
        '"limit_name":null,"primary":null,"secondary":null,"credits":null,"individual_limit":null,'
        '"spend_control_reached":null,"plan_type":null,"rate_limit_reached_type":null}}}'
    ),
    (
        '{"timestamp":"2026-11-12T13:54:56.704Z","ordinal":23,"type":"event_msg","payload":{"type":"task_complete",'
        '"root_turn_id":"01a1d00a-4517-7a62-bcc4-bdb2b510c4aa","turn_id":"01a1d00a-4517-7a62-bcc4-bdb2b510c4aa",'
        '"last_agent_message":"transcript canary","started_at":1794491696,"completed_at":1794491696,'
        '"duration_ms":294,"time_to_first_token_ms":160}}'
    ),
    (
        '{"timestamp":"2026-11-12T13:55:10.309Z","ordinal":24,"type":"event_msg",'
        '"payload":{"type":"thread_settings_applied","thread_id":"01a1d00a-4509-7b61-a64b-4e8cef36a311",'
        '"thread_settings":{"model":"gpt-5.5","cwd":"/workspace"}}}'
    ),
    (
        '{"timestamp":"2026-11-12T13:55:10.319Z","ordinal":25,"type":"event_msg","payload":{"type":"task_started",'
        '"turn_attribution":{"turn_id":"01a1d00a-7b63-7f32-b1d1-aa39ec9ecdd4","turn_trigger":"exec",'
        '"parent_turn_id":null,"initiating_agent_path":null,"root_turn_id":"01a1d00a-7b63-7f32-b1d1-aa39ec9ecdd4"},'
        '"turn_id":"01a1d00a-7b63-7f32-b1d1-aa39ec9ecdd4","root_turn_id":"01a1d00a-7b63-7f32-b1d1-aa39ec9ecdd4",'
        '"started_at":1794491710,"model_context_window":258400,"collaboration_mode_kind":"default"}}'
    ),
    (
        '{"timestamp":"2026-11-12T13:55:10.322Z","ordinal":26,"type":"turn_context",'
        '"payload":{"turn_id":"01a1d00a-7b63-7f32-b1d1-aa39ec9ecdd4",'
        '"root_turn_id":"01a1d00a-7b63-7f32-b1d1-aa39ec9ecdd4","cwd":"/workspace","model":"gpt-5.5"}}'
    ),
    (
        '{"timestamp":"2026-11-12T13:55:10.325Z","ordinal":27,"type":"response_item","payload":{"type":"message",'
        '"id":"msg_01a1d00a-7b75-7032-97c2-f57d503c97f2","role":"user","content":[{"type":"input_text",'
        '"text":"transcript canary sk-proj-CANARY0123456789abcdefCANARY"}]}}'
    ),
    (
        '{"timestamp":"2026-11-12T13:55:10.326Z","ordinal":28,"type":"event_msg",'
        '"payload":{"type":"item_completed",'
        '"thread_id":"01a1d00a-4509-7b61-a64b-4e8cef36a311",'
        '"turn_id":"01a1d00a-7b63-7f32-b1d1-aa39ec9ecdd4","item":{"type":"UserMessage",'
        '"id":"01a1d00a-7b75-7032-97c2-f587c707fb92","text":"transcript canary"}}}'
    ),
    (
        '{"timestamp":"2026-11-12T13:55:10.341Z","ordinal":29,"type":"event_msg",'
        '"payload":{"type":"item_completed",'
        '"thread_id":"01a1d00a-4509-7b61-a64b-4e8cef36a311",'
        '"turn_id":"01a1d00a-7b63-7f32-b1d1-aa39ec9ecdd4","item":{"type":"AgentMessage",'
        '"id":"msg_3","text":"transcript canary"}}}'
    ),
    (
        '{"timestamp":"2026-11-12T13:55:10.342Z","ordinal":30,"type":"response_item","payload":{"type":"message",'
        '"id":"msg_3","role":"assistant","content":[{"type":"output_text","text":"transcript canary"}]}}'
    ),
    (
        '{"timestamp":"2026-11-12T13:55:10.343Z","ordinal":31,"type":"token_usage_record","payload":{"thread_id":"0'
        '1a1d00a-4509-7b61-a64b-4e8cef36a311","turn_id":"01a1d00a-7b63-7f32-b1d1-aa39ec9ecdd4","session_id":"01a1d0'
        '0a-4509-7b61-a64b-4e8cef36a311","root_turn_id":"01a1d00a-7b63-7f32-b1d1-aa39ec9ecdd4","response_id":"resp_'
        '0003","usage":{"input_tokens":14000,"cached_input_tokens":12800,"cache_write_input_tokens":0,"output_token'
        's":40,"reasoning_output_tokens":8,"total_tokens":14040}}}'
    ),
    (
        '{"timestamp":"2026-11-12T13:55:10.344Z","ordinal":32,"type":"event_msg",'
        '"payload":{"type":"token_count","info":{"total_token_usage":{"input_tokens":51000,'
        '"cached_input_tokens":31800,"cache_write_input_tokens":14000,"output_tokens":1110,'
        '"reasoning_output_tokens":208,"total_tokens":52110},"last_token_usage":{"input_tokens":14000,'
        '"cached_input_tokens":12800,"cache_write_input_tokens":0,"output_tokens":40,'
        '"reasoning_output_tokens":8,"total_tokens":14040},"last_usage_includes_reasoning":false,'
        '"model_context_window":258400},"rate_limits":{"limit_id":"codex","limit_name":null,"primary":null,'
        '"secondary":null,"credits":null,"individual_limit":null,"spend_control_reached":null,"plan_type":null,'
        '"rate_limit_reached_type":null}}}'
    ),
    (
        '{"timestamp":"2026-11-12T13:55:10.347Z","ordinal":33,"type":"event_msg","payload":{"type":"task_complete",'
        '"root_turn_id":"01a1d00a-7b63-7f32-b1d1-aa39ec9ecdd4","turn_id":"01a1d00a-7b63-7f32-b1d1-aa39ec9ecdd4",'
        '"last_agent_message":"transcript canary","started_at":1794491710,"completed_at":1794491710,'
        '"duration_ms":27,"time_to_first_token_ms":22}}'
    ),
    (
        '{"timestamp":"2026-11-12T14:01:56.868Z","ordinal":34,"type":"event_msg",'
        '"payload":{"type":"thread_settings_applied","thread_id":"01a1d00a-4509-7b61-a64b-4e8cef36a311",'
        '"thread_settings":{"model":"gpt-5.6-sol","cwd":"/workspace"}}}'
    ),
    (
        '{"timestamp":"2026-11-12T14:01:56.885Z","ordinal":35,"type":"event_msg",'
        '"payload":{"type":"thread_settings_applied",'
        '"thread_id":"01a1d00a-4509-7b61-a64b-4e8cef36a311","thread_settings":{"model":"gpt-5.6-sol",'
        '"cwd":"/workspace"}}}'
    ),
    (
        '{"timestamp":"2026-11-12T14:01:56.888Z","ordinal":36,"type":"event_msg","payload":{"type":"task_started",'
        '"turn_attribution":{"turn_id":"01a1d010-af94-7fa0-b242-df747cc40630","turn_trigger":"exec",'
        '"parent_turn_id":null,"initiating_agent_path":null,"root_turn_id":"01a1d010-af94-7fa0-b242-df747cc40630"},'
        '"turn_id":"01a1d010-af94-7fa0-b242-df747cc40630","root_turn_id":"01a1d010-af94-7fa0-b242-df747cc40630",'
        '"started_at":1794492116,"model_context_window":258400,"collaboration_mode_kind":"default"}}'
    ),
    (
        '{"timestamp":"2026-11-12T14:01:56.902Z","ordinal":37,"type":"event_msg",'
        '"payload":{"type":"token_count","info":{"total_token_usage":{"input_tokens":51000,'
        '"cached_input_tokens":31800,"cache_write_input_tokens":14000,"output_tokens":1110,'
        '"reasoning_output_tokens":208,"total_tokens":52110},"last_token_usage":{"input_tokens":14000,'
        '"cached_input_tokens":12800,"cache_write_input_tokens":0,"output_tokens":40,'
        '"reasoning_output_tokens":8,"total_tokens":14040},"last_usage_includes_reasoning":false,'
        '"model_context_window":258400},"rate_limits":{"limit_id":"codex","limit_name":null,"primary":null,'
        '"secondary":null,"credits":null,"individual_limit":null,"spend_control_reached":null,"plan_type":null,'
        '"rate_limit_reached_type":null}}}'
    ),
    (
        '{"timestamp":"2026-11-12T14:01:56.904Z","ordinal":38,"type":"response_item",'
        '"payload":{"type":"function_call","id":"fc_0","name":"exec_command","arguments":"transcript canary",'
        '"call_id":"call_0"}}'
    ),
    (
        '{"timestamp":"2026-11-12T14:01:56.904Z","ordinal":39,"type":"token_usage_record","payload":{"thread_id":"0'
        '1a1d00a-4509-7b61-a64b-4e8cef36a311","turn_id":"01a1d010-af94-7fa0-b242-df747cc40630","session_id":"01a1d0'
        '0a-4509-7b61-a64b-4e8cef36a311","root_turn_id":"01a1d010-af94-7fa0-b242-df747cc40630","response_id":"resp_'
        '0000","usage":{"input_tokens":15000,"cached_input_tokens":13900,"cache_write_input_tokens":900,"output_tok'
        'ens":30,"reasoning_output_tokens":10,"total_tokens":15030}}}'
    ),
    (
        '{"timestamp":"2026-11-12T14:01:56.905Z","ordinal":40,"type":"event_msg",'
        '"payload":{"type":"token_count","info":{"total_token_usage":{"input_tokens":66000,'
        '"cached_input_tokens":45700,"cache_write_input_tokens":14900,"output_tokens":1140,'
        '"reasoning_output_tokens":218,"total_tokens":67140},"last_token_usage":{"input_tokens":15000,'
        '"cached_input_tokens":13900,"cache_write_input_tokens":900,"output_tokens":30,'
        '"reasoning_output_tokens":10,"total_tokens":15030},"last_usage_includes_reasoning":false,'
        '"model_context_window":258400},"rate_limits":{"limit_id":"codex","limit_name":null,"primary":null,'
        '"secondary":null,"credits":null,"individual_limit":null,"spend_control_reached":null,"plan_type":null,'
        '"rate_limit_reached_type":null}}}'
    ),
    (
        '{"timestamp":"2026-11-12T14:01:56.907Z","ordinal":41,"type":"compacted",'
        '"payload":{"message":"transcript canary","replacement_history":[],"window_number":1,'
        '"first_window_id":"01a1d00a-450b-7b01-ae38-41525808ed93",'
        '"previous_window_id":"01a1d00a-450b-7b01-ae38-41525808ed93",'
        '"window_id":"01a1d010-afaa-7761-a4c5-f6531e1671b8"}}'
    ),
    (
        '{"timestamp":"2026-11-12T14:01:56.907Z","ordinal":42,"type":"world_state","payload":{"full":true,'
        '"state":{}}}'
    ),
    (
        '{"timestamp":"2026-11-12T14:01:56.907Z","ordinal":43,"type":"turn_context",'
        '"payload":{"turn_id":"01a1d010-af94-7fa0-b242-df747cc40630",'
        '"root_turn_id":"01a1d010-af94-7fa0-b242-df747cc40630","cwd":"/workspace","model":"gpt-5.6-sol"}}'
    ),
    (
        '{"timestamp":"2026-11-12T14:01:56.907Z","ordinal":44,"type":"event_msg",'
        '"payload":{"type":"thread_settings_applied",'
        '"thread_id":"01a1d00a-4509-7b61-a64b-4e8cef36a311","thread_settings":{"model":"gpt-5.6-sol",'
        '"cwd":"/workspace"}}}'
    ),
    (
        '{"timestamp":"2026-11-12T14:01:56.909Z","ordinal":45,"type":"event_msg",'
        '"payload":{"type":"token_count","info":{"total_token_usage":{"input_tokens":66000,'
        '"cached_input_tokens":45700,"cache_write_input_tokens":14900,"output_tokens":1140,'
        '"reasoning_output_tokens":218,"total_tokens":67140},"last_token_usage":{"input_tokens":0,'
        '"cached_input_tokens":0,"cache_write_input_tokens":0,"output_tokens":0,"reasoning_output_tokens":0,'
        '"total_tokens":9548},"last_usage_includes_reasoning":true,"model_context_window":258400},'
        '"rate_limits":{"limit_id":"codex","limit_name":null,"primary":null,"secondary":null,"credits":null,'
        '"individual_limit":null,"spend_control_reached":null,"plan_type":null,"rate_limit_reached_type":null}}}'
    ),
    (
        '{"timestamp":"2026-11-12T14:01:56.910Z","ordinal":46,"type":"event_msg",'
        '"payload":{"type":"item_completed",'
        '"thread_id":"01a1d00a-4509-7b61-a64b-4e8cef36a311",'
        '"turn_id":"01a1d010-af94-7fa0-b242-df747cc40630","item":{"type":"ContextCompaction",'
        '"id":"01a1d010-af9d-7050-b6c1-0a66822f65c6","text":"transcript canary"}}}'
    ),
    (
        '{"timestamp":"2026-11-12T14:01:56.916Z","ordinal":47,"type":"response_item",'
        '"payload":{"type":"message","id":"msg_01a1d010-afb4-7832-b22c-0bbe1cf3a314","role":"user",'
        '"content":[{"type":"input_text","text":"transcript canary sk-proj-CANARY0123456789abcdefCANARY"}]}}'
    ),
    (
        '{"timestamp":"2026-11-12T14:01:56.917Z","ordinal":48,"type":"event_msg","payload":{"type":"item_completed"'
        ',"thread_id":"01a1d00a-4509-7b61-a64b-4e8cef36a311","turn_id":"01a1d010-af94-7fa0-b242-df747cc40630","item'
        '":{"type":"UserMessage","id":"01a1d010-afb4-7832-b22c-0bc4df7b0569","text":"transcript canary"}}}'
    ),
    (
        '{"timestamp":"2026-11-12T14:01:56.933Z","ordinal":49,"type":"event_msg","payload":{"type":"item_completed"'
        ',"thread_id":"01a1d00a-4509-7b61-a64b-4e8cef36a311","turn_id":"01a1d010-af94-7fa0-b242-df747cc40630","item'
        '":{"type":"AgentMessage","id":"msg_1","text":"transcript canary"}}}'
    ),
    (
        '{"timestamp":"2026-11-12T14:01:56.935Z","ordinal":50,"type":"response_item","payload":{"type":"message",'
        '"id":"msg_1","role":"assistant","content":[{"type":"output_text","text":"transcript canary"}]}}'
    ),
    (
        '{"timestamp":"2026-11-12T14:01:56.935Z","ordinal":51,"type":"token_usage_record","payload":{"thread_id":"0'
        '1a1d00a-4509-7b61-a64b-4e8cef36a311","turn_id":"01a1d010-af94-7fa0-b242-df747cc40630","session_id":"01a1d0'
        '0a-4509-7b61-a64b-4e8cef36a311","root_turn_id":"01a1d010-af94-7fa0-b242-df747cc40630","response_id":"resp_'
        '0001","usage":{"input_tokens":15500,"cached_input_tokens":15000,"cache_write_input_tokens":0,"output_token'
        's":60,"reasoning_output_tokens":0,"total_tokens":15560}}}'
    ),
    (
        '{"timestamp":"2026-11-12T14:01:56.936Z","ordinal":52,'
        '"type":"event_msg","payload":{"type":"token_count",'
        '"info":{"total_token_usage":{"input_tokens":81500,'
        '"cached_input_tokens":60700,"cache_write_input_tokens":14900,'
        '"output_tokens":1200,"reasoning_output_tokens":218,'
        '"total_tokens":82700},"last_token_usage":{"input_tokens":15500,'
        '"cached_input_tokens":15000,"cache_write_input_tokens":0,'
        '"output_tokens":60,"reasoning_output_tokens":0,'
        '"total_tokens":15560},"last_usage_includes_reasoning":true,'
        '"model_context_window":258400},"rate_limits":{"limit_id":"codex",'
        '"limit_name":null,"primary":null,"secondary":null,"credits":null,'
        '"individual_limit":null,"spend_control_reached":null,'
        '"plan_type":null,"rate_limit_reached_type":null}}}'
    ),
    (
        '{"timestamp":"2026-11-12T14:01:56.939Z","ordinal":53,"type":"event_msg","payload":{"type":"task_complete",'
        '"root_turn_id":"01a1d010-af94-7fa0-b242-df747cc40630","turn_id":"01a1d010-af94-7fa0-b242-df747cc40630",'
        '"last_agent_message":"transcript canary","started_at":1794492116,"completed_at":1794492116,'
        '"duration_ms":51,"time_to_first_token_ms":45}}'
    ),
    (
        '{"timestamp":"2026-11-12T14:03:07.146Z","ordinal":54,"type":"event_msg",'
        '"payload":{"type":"thread_settings_applied",'
        '"thread_id":"01a1d00a-4509-7b61-a64b-4e8cef36a311","thread_settings":{"model":"gpt-5.6-sol",'
        '"cwd":"/workspace"}}}'
    ),
    (
        '{"timestamp":"2026-11-12T14:03:07.149Z","ordinal":55,"type":"event_msg","payload":{"type":"task_started",'
        '"turn_attribution":{"turn_id":"01a1d011-c208-7fb1-afe3-45757b59beb7","turn_trigger":"exec",'
        '"parent_turn_id":null,"initiating_agent_path":null,"root_turn_id":"01a1d011-c208-7fb1-afe3-45757b59beb7"},'
        '"turn_id":"01a1d011-c208-7fb1-afe3-45757b59beb7","root_turn_id":"01a1d011-c208-7fb1-afe3-45757b59beb7",'
        '"started_at":1794492187,"model_context_window":258400,"collaboration_mode_kind":"default"}}'
    ),
    (
        '{"timestamp":"2026-11-12T14:03:07.153Z","ordinal":56,"type":"turn_context",'
        '"payload":{"turn_id":"01a1d011-c208-7fb1-afe3-45757b59beb7",'
        '"root_turn_id":"01a1d011-c208-7fb1-afe3-45757b59beb7","cwd":"/workspace","model":"gpt-5.6-sol"}}'
    ),
    (
        '{"timestamp":"2026-11-12T14:03:07.155Z","ordinal":57,"type":"response_item",'
        '"payload":{"type":"message","id":"msg_01a1d011-c213-7941-ab41-e0dbf83138d9","role":"user",'
        '"content":[{"type":"input_text","text":"transcript canary sk-proj-CANARY0123456789abcdefCANARY"}]}}'
    ),
    (
        '{"timestamp":"2026-11-12T14:03:07.155Z","ordinal":58,"type":"event_msg","payload":{"type":"item_completed"'
        ',"thread_id":"01a1d00a-4509-7b61-a64b-4e8cef36a311","turn_id":"01a1d011-c208-7fb1-afe3-45757b59beb7","item'
        '":{"type":"UserMessage","id":"01a1d011-c213-7941-ab41-e0e0d090de53","text":"transcript canary"}}}'
    ),
    (
        '{"timestamp":"2026-11-12T14:03:07.169Z","ordinal":59,"type":"event_msg","payload":{"type":"task_complete",'
        '"root_turn_id":"01a1d011-c208-7fb1-afe3-45757b59beb7","turn_id":"01a1d011-c208-7fb1-afe3-45757b59beb7",'
        '"last_agent_message":null,"error":{"message":"transcript canary",'
        '"codex_error_info":"internal_server_error"},"started_at":1794492187,"completed_at":1794492187,'
        '"duration_ms":20}}'
    ),
    (
        '{"timestamp":"2026-11-12T14:03:11.763Z","ordinal":60,"type":"event_msg","payload":{"type":"thread_settings'
        '_applied","thread_id":"01a1d00a-4509-7b61-a64b-4e8cef36a311","thread_settings":{"model":"gpt-5.6-sol","cwd'
        '":"/workspace"}}}'
    ),
    (
        '{"timestamp":"2026-11-12T14:03:11.765Z","ordinal":61,"type":"event_msg","payload":{"type":"task_started",'
        '"turn_attribution":{"turn_id":"01a1d011-d411-7733-89f3-3f97c9a80dea","turn_trigger":"exec",'
        '"parent_turn_id":null,"initiating_agent_path":null,"root_turn_id":"01a1d011-d411-7733-89f3-3f97c9a80dea"},'
        '"turn_id":"01a1d011-d411-7733-89f3-3f97c9a80dea","root_turn_id":"01a1d011-d411-7733-89f3-3f97c9a80dea",'
        '"started_at":1794492191,"model_context_window":258400,"collaboration_mode_kind":"default"}}'
    ),
    (
        '{"timestamp":"2026-11-12T14:03:11.769Z","ordinal":62,"type":"turn_context",'
        '"payload":{"turn_id":"01a1d011-d411-7733-89f3-3f97c9a80dea",'
        '"root_turn_id":"01a1d011-d411-7733-89f3-3f97c9a80dea","cwd":"/workspace","model":"gpt-5.6-sol"}}'
    ),
    (
        '{"timestamp":"2026-11-12T14:03:11.772Z","ordinal":63,"type":"response_item",'
        '"payload":{"type":"message","id":"msg_01a1d011-d41c-7512-8deb-c9ffb4208c8f","role":"user",'
        '"content":[{"type":"input_text","text":"transcript canary sk-proj-CANARY0123456789abcdefCANARY"}]}}'
    ),
    (
        '{"timestamp":"2026-11-12T14:03:11.773Z","ordinal":64,"type":"event_msg","payload":{"type":"item_completed"'
        ',"thread_id":"01a1d00a-4509-7b61-a64b-4e8cef36a311","turn_id":"01a1d011-d411-7733-89f3-3f97c9a80dea","item'
        '":{"type":"UserMessage","id":"01a1d011-d41c-7512-8deb-ca00c9a8b6b4","text":"transcript canary"}}}'
    ),
    (
        '{"timestamp":"2026-11-12T14:03:11.788Z","ordinal":65,"type":"response_item",'
        '"payload":{"type":"function_call","id":"fc_0","name":"exec_command","arguments":"transcript canary",'
        '"call_id":"call_0"}}'
    ),
    (
        '{"timestamp":"2026-11-12T14:03:11.789Z","ordinal":66,"type":"token_usage_record","payload":{"thread_id":"0'
        '1a1d00a-4509-7b61-a64b-4e8cef36a311","turn_id":"01a1d011-d411-7733-89f3-3f97c9a80dea","session_id":"01a1d0'
        '0a-4509-7b61-a64b-4e8cef36a311","root_turn_id":"01a1d011-d411-7733-89f3-3f97c9a80dea","response_id":"resp_'
        '0000","usage":{"input_tokens":16000,"cached_input_tokens":15400,"cache_write_input_tokens":0,"output_token'
        's":25,"reasoning_output_tokens":5,"total_tokens":16025}}}'
    ),
    (
        '{"timestamp":"2026-11-12T14:03:11.838Z","ordinal":67,"type":"event_msg","payload":{"type":"item_completed"'
        ',"thread_id":"01a1d00a-4509-7b61-a64b-4e8cef36a311","turn_id":"01a1d011-d411-7733-89f3-3f97c9a80dea","item'
        '":{"type":"CommandExecution","id":"call_0","text":"transcript canary"}}}'
    ),
    (
        '{"timestamp":"2026-11-12T14:03:11.843Z","ordinal":68,"type":"response_item",'
        '"payload":{"type":"function_call_output","id":"fco_01a1d011-d463-7182-9c25-e9cbe1f68447",'
        '"call_id":"call_0","output":"transcript canary"}}'
    ),
    (
        '{"timestamp":"2026-11-12T14:03:11.844Z","ordinal":69,'
        '"type":"event_msg","payload":{"type":"token_count",'
        '"info":{"total_token_usage":{"input_tokens":97500,'
        '"cached_input_tokens":76100,"cache_write_input_tokens":14900,'
        '"output_tokens":1225,"reasoning_output_tokens":223,'
        '"total_tokens":98725},"last_token_usage":{"input_tokens":16000,'
        '"cached_input_tokens":15400,"cache_write_input_tokens":0,'
        '"output_tokens":25,"reasoning_output_tokens":5,'
        '"total_tokens":16025},"last_usage_includes_reasoning":true,'
        '"model_context_window":258400},"rate_limits":{"limit_id":"codex",'
        '"limit_name":null,"primary":null,"secondary":null,"credits":null,'
        '"individual_limit":null,"spend_control_reached":null,'
        '"plan_type":null,"rate_limit_reached_type":null}}}'
    ),
    (
        '{"timestamp":"2026-11-12T14:03:33.271Z","ordinal":70,"type":"event_msg","payload":{"type":"thread_settings'
        '_applied","thread_id":"01a1d00a-4509-7b61-a64b-4e8cef36a311","thread_settings":{"model":"gpt-5.6-sol","cwd'
        '":"/workspace"}}}'
    ),
    (
        '{"timestamp":"2026-11-12T14:03:33.283Z","ordinal":71,"type":"event_msg","payload":{"type":"task_started",'
        '"turn_attribution":{"turn_id":"01a1d012-2815-78f1-988f-8024684d2e9d","turn_trigger":"exec",'
        '"parent_turn_id":null,"initiating_agent_path":null,"root_turn_id":"01a1d012-2815-78f1-988f-8024684d2e9d"},'
        '"turn_id":"01a1d012-2815-78f1-988f-8024684d2e9d","root_turn_id":"01a1d012-2815-78f1-988f-8024684d2e9d",'
        '"started_at":1794492213,"model_context_window":258400,"collaboration_mode_kind":"default"}}'
    ),
    (
        '{"timestamp":"2026-11-12T14:03:33.290Z","ordinal":72,"type":"turn_context",'
        '"payload":{"turn_id":"01a1d012-2815-78f1-988f-8024684d2e9d",'
        '"root_turn_id":"01a1d012-2815-78f1-988f-8024684d2e9d","cwd":"/workspace","model":"gpt-5.6-sol"}}'
    ),
    (
        '{"timestamp":"2026-11-12T14:03:33.293Z","ordinal":73,"type":"response_item","payload":{"type":"message","i'
        'd":"msg_01a1d012-282d-7343-b57e-b7102423816d","role":"user","content":[{"type":"input_text","text":"transc'
        'ript canary sk-proj-CANARY0123456789abcdefCANARY"}]}}'
    ),
    (
        '{"timestamp":"2026-11-12T14:03:33.294Z","ordinal":74,"type":"event_msg","payload":{"type":"item_completed"'
        ',"thread_id":"01a1d00a-4509-7b61-a64b-4e8cef36a311","turn_id":"01a1d012-2815-78f1-988f-8024684d2e9d","item'
        '":{"type":"UserMessage","id":"01a1d012-282d-7343-b57e-b72b1e16c0cc","text":"transcript canary"}}}'
    ),
    (
        '{"timestamp":"2026-11-12T14:03:33.308Z","ordinal":75,"type":"event_msg","payload":{"type":"item_completed"'
        ',"thread_id":"01a1d00a-4509-7b61-a64b-4e8cef36a311","turn_id":"01a1d012-2815-78f1-988f-8024684d2e9d","item'
        '":{"type":"AgentMessage","id":"msg_0","text":"transcript canary"}}}'
    ),
    (
        '{"timestamp":"2026-11-12T14:03:33.309Z","ordinal":76,"type":"response_item","payload":{"type":"message",'
        '"id":"msg_0","role":"assistant","content":[{"type":"output_text","text":"transcript canary"}]}}'
    ),
    (
        '{"timestamp":"2026-11-12T14:03:33.310Z","ordinal":77,"type":"token_usage_record","payload":{"thread_id":"0'
        '1a1d00a-4509-7b61-a64b-4e8cef36a311","turn_id":"01a1d012-2815-78f1-988f-8024684d2e9d","session_id":"01a1d0'
        '0a-4509-7b61-a64b-4e8cef36a311","root_turn_id":"01a1d012-2815-78f1-988f-8024684d2e9d","response_id":"resp_'
        '0000","usage":{"input_tokens":16500,"cached_input_tokens":16000,"cache_write_input_tokens":0,"output_token'
        's":25,"reasoning_output_tokens":5,"total_tokens":16525}}}'
    ),
    (
        '{"timestamp":"2026-11-12T14:03:33.311Z","ordinal":78,'
        '"type":"event_msg","payload":{"type":"token_count",'
        '"info":{"total_token_usage":{"input_tokens":114000,'
        '"cached_input_tokens":92100,"cache_write_input_tokens":14900,'
        '"output_tokens":1250,"reasoning_output_tokens":228,'
        '"total_tokens":115250},"last_token_usage":{"input_tokens":16500,'
        '"cached_input_tokens":16000,"cache_write_input_tokens":0,'
        '"output_tokens":25,"reasoning_output_tokens":5,'
        '"total_tokens":16525},"last_usage_includes_reasoning":true,'
        '"model_context_window":258400},"rate_limits":{"limit_id":"codex",'
        '"limit_name":null,"primary":null,"secondary":null,"credits":null,'
        '"individual_limit":null,"spend_control_reached":null,'
        '"plan_type":null,"rate_limit_reached_type":null}}}'
    ),
    (
        '{"timestamp":"2026-11-12T14:03:33.313Z","ordinal":79,"type":"event_msg","payload":{"type":"task_complete",'
        '"root_turn_id":"01a1d012-2815-78f1-988f-8024684d2e9d","turn_id":"01a1d012-2815-78f1-988f-8024684d2e9d",'
        '"last_agent_message":"transcript canary","started_at":1794492213,"completed_at":1794492213,'
        '"duration_ms":30,"time_to_first_token_ms":25}}'
    ),
)

_THREAD_STARTED = f'{{"type":"thread.started","thread_id":"{SESSION_ID}"}}'
_TURN_STARTED = '{"type":"turn.started"}'
_COMMAND = '"type":"command_execution","command":"/bin/bash -lc true","aggregated_output":""'
_DONE = '"type":"agent_message","text":"Done."}}'
_HIGH_DEMAND = "We\u2019re currently experiencing high demand, which may cause temporary errors."


def _command(item_id: str) -> tuple[str, str]:
    """The two lines one command printed: started, then completed."""
    return (
        f'{{"type":"item.started","item":{{"id":"{item_id}",{_COMMAND},"exit_code":null,"status":"in_progress"}}}}',
        f'{{"type":"item.completed","item":{{"id":"{item_id}",{_COMMAND},"exit_code":0,"status":"completed"}}}}',
    )


_FRESH_STDOUT = (
    _THREAD_STARTED,
    _TURN_STARTED,
    *_command("item_0"),
    *_command("item_1"),
    f'{{"type":"item.completed","item":{{"id":"item_2",{_DONE}',
    (
        '{"type":"turn.completed","usage":{"input_tokens":37000,"cached_input_tokens":19000,'
        '"cache_write_input_tokens":14000,"output_tokens":1070,"reasoning_output_tokens":200}}'
    ),
)
_RESUMED_STDOUT = (
    _THREAD_STARTED,
    _TURN_STARTED,
    f'{{"type":"item.completed","item":{{"id":"item_0",{_DONE}',
    (
        '{"type":"turn.completed","usage":{"input_tokens":51000,"cached_input_tokens":31800,'
        '"cache_write_input_tokens":14000,"output_tokens":1110,"reasoning_output_tokens":208}}'
    ),
)
_SWITCHED_STDOUT = (
    _THREAD_STARTED,
    (
        '{"type":"item.completed","item":{"id":"item_0","type":"error","message":"This session was recorded with '
        'model `gpt-5.5` but is resuming with `gpt-5.6-sol`. Consider switching back to `gpt-5.5` as it may affect '
        'Codex performance."}}'
    ),
    _TURN_STARTED,
    f'{{"type":"item.completed","item":{{"id":"item_1",{_DONE}',
    (
        '{"type":"turn.completed","usage":{"input_tokens":81500,"cached_input_tokens":60700,'
        '"cache_write_input_tokens":14900,"output_tokens":1200,"reasoning_output_tokens":218}}'
    ),
)
_FAILED_STDOUT = (
    _THREAD_STARTED,
    _TURN_STARTED,
    f'{{"type":"error","message":"{_HIGH_DEMAND}"}}',
    f'{{"type":"turn.failed","error":{{"message":"{_HIGH_DEMAND}"}}}}',
)
_INTERRUPTED_STDOUT = (
    _THREAD_STARTED,
    _TURN_STARTED,
    *_command("item_0"),
)
_LAST_STDOUT = (
    _THREAD_STARTED,
    _TURN_STARTED,
    f'{{"type":"item.completed","item":{{"id":"item_0",{_DONE}',
    (
        '{"type":"turn.completed","usage":{"input_tokens":114000,"cached_input_tokens":92100,'
        '"cache_write_input_tokens":14900,"output_tokens":1250,"reasoning_output_tokens":228}}'
    ),
)


class Invocation(NamedTuple):
    """One captured invocation: when it was launched, the log line it ended before, whether it resumed, its stdout,
    and the whole lines the log held when it was launched, its own beginning past them."""

    launched_at: datetime
    end: int
    resumed: bool
    stdout: str
    start: int = 0


# Each invocation: its launch moment, the line it ended before, whether it resumed, and its stdout.
_CAPTURED = (
    ("2026-11-12T13:54:56.000+00:00", 24, False, _FRESH_STDOUT),
    ("2026-11-12T13:55:10.000+00:00", 34, True, _RESUMED_STDOUT),
    ("2026-11-12T14:01:56.000+00:00", 54, True, _SWITCHED_STDOUT),
    ("2026-11-12T14:03:07.000+00:00", 60, True, _FAILED_STDOUT),
    ("2026-11-12T14:03:11.000+00:00", 70, True, _INTERRUPTED_STDOUT),
    ("2026-11-12T14:03:33.000+00:00", 80, True, _LAST_STDOUT),
)
# Each invocation begins where the one before it ended.
_ENDS = tuple(captured[1] for captured in _CAPTURED)
_STARTS = (0, *_ENDS[:-1])
INVOCATIONS = tuple(
    Invocation(datetime.fromisoformat(launched_at), end, resumed, "\n".join(stdout), start)
    for (launched_at, end, resumed, stdout), start in zip(_CAPTURED, _STARTS, strict=True)
)
FRESH, RESUMED, SWITCHED = INVOCATIONS[:3]
FAILED, INTERRUPTED, LAST = INVOCATIONS[3:]


def log_lines(end: int | None = None) -> tuple[str, ...]:
    """The log's lines as they stood when the invocation ending before line `end` exited -- the whole log by default."""
    return _LOG_LINES[:end]


def log_text(end: int | None = None) -> str:
    """The log file's text as it stood when the invocation ending before line `end` exited, each line ended."""
    return "".join(f"{line}\n" for line in log_lines(end))
