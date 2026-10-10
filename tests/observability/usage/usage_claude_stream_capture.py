# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Sanitized `claude -p` stream-json runs captured from Claude Code 2.1.295.

Two runs of `claude --model claude-opus-5-5 --effort xhigh`, captured on 2026-10-10 with the flags the Claude
backend adds -- `-p --dangerously-skip-permissions --output-format stream-json --include-partial-messages
--verbose` -- and the prompt last, in a scratch git repository holding `notes.txt` (three lines) and `calc.py` (a
two-line `add`). `MAIN_RUN_PROMPT` asks for one message with a text block and two parallel Bash calls, one Read
call, then a message that thinks before answering; `SUBAGENT_RUN_PROMPT` has the lead thread hand one Bash call
to a subagent. Kept as the raw lines the CLI printed, in their order, rather than as rebuilt dicts.

What the capture establishes about Claude's accounting:

- Every frame that belongs to an API message names it. A `stream_event` wrapper carries `api_message_id`, the
  `message.id` of the message's `message_start` event and of its `assistant` frames; the `message_delta` event
  inside carries no id of its own. A message prints one `assistant` frame per completed content block, all under
  one id, and the CLI runs a tool as soon as its block completes, so a `tool_result` can precede the
  `message_delta` of the message that called it.
- Every `assistant` frame repeats the usage of its message's `message_start` verbatim: the output count it holds
  is the one at the start of the message. The final per-message output count -- thinking included, broken out
  under `output_tokens_details` -- is only on the message's `message_delta`. Input, cache-read, and cache-write
  counts are the same on all three.
- The `result` frame's `usage` is the sum of the lead thread's `message_delta` counts; its `iterations` list holds
  only the last message, not a run breakdown. `modelUsage` adds the subagent's messages to that, and
  `total_cost_usd` matches its `costUSD`.
- A subagent prints its `assistant` frames under the `parent_tool_use_id` of the call that launched it, but no
  `stream_event` frames, and the message that closes it prints no frame at all. The lead thread's `tool_result`
  for that call carries the final usage of the subagent's last message under `tool_use_result.usage`; the
  final output count of any earlier subagent message is in no frame, only in the `modelUsage` difference.
- Each usage block carries both the flat `cache_creation_input_tokens` and the `cache_creation` split by TTL.
  The lead threads write one-hour cache entries and the subagent five-minute ones. A `message_delta` carries
  the TTL split only under `iterations`.

Keeping the last `assistant` frame per `message.id` sums the start counts: 31 output tokens on the main run,
where the CLI reports 358; 92 on the subagent run, where it reports 314 for the lead thread and 450 in all.

Sanitized means the session, message, request, tool-use, and agent ids were replaced by readable stand-ins,
used consistently so every correlation holds; the scratch path became `/workspace`; thinking signatures were
redacted; the `init` frame was cut to its identifying fields and the tools the runs call (it offers the subagent
tool as `Task`, which the call names `Agent`); the `uuid`, `timestamp`, timing, and rate-limit account fields
were dropped, along with `session_id` everywhere but `init` and `result`; the subagent hand-back text was cut to
its report and usage trailer; and each content block's run of text or tool-input deltas was merged into one
delta frame. Every usage block, result total, model name, and the order of the remaining frames is verbatim.
"""

from collections.abc import Iterable
from dataclasses import astuple, dataclass, replace
from typing import Any

CLI_VERSION = "2.1.295"
MODEL = "claude-opus-5-5"
MAIN_RUN_PROMPT = (
    "Think carefully before each step. First, in a single message, write one short sentence saying what you "
    "will check, then call the Bash tool twice in parallel: `wc -l notes.txt` and `wc -c calc.py`. After you "
    "see both results, use the Read tool to read calc.py. Then work out what add(17, 25) * 3 evaluates to and "
    "reply with one sentence giving that value, the line count of notes.txt, and the byte count of calc.py."
)
SUBAGENT_RUN_PROMPT = (
    'Use the Agent tool exactly once to launch a general-purpose subagent with this task: "Run `wc -l '
    'notes.txt` with the Bash tool and reply with only the number." After the subagent returns, use the Bash '
    "tool yourself to run `wc -c calc.py`. Then reply with one sentence giving both numbers."
)


CountsRow = tuple[int, int, int, int]
MessageRow = tuple[str, CountsRow, int]


@dataclass(frozen=True)
class TokenCounts:
    """Input, cache-read, cache-write, and output tokens, as one usage block counts them."""

    input_tokens: int
    cache_read_tokens: int
    cache_write_tokens: int
    output_tokens: int

    @classmethod
    def parsed(cls, usage: Any) -> "TokenCounts":
        """The counts a parsed `UsageMetrics` or `TurnUsage` holds."""
        return cls(usage.input_tokens, usage.cache_read_tokens, usage.cache_write_tokens, usage.output_tokens)


@dataclass(frozen=True)
class MessageCounts:
    """One API message: the counts its `message_start` and `assistant` frames carry, and its final output."""

    message_id: str
    start: TokenCounts
    final_output_tokens: int

    @property
    def final(self) -> TokenCounts:
        """The message's counts once it completed: only the output count moves past the start."""
        return replace(self.start, output_tokens=self.final_output_tokens)


def counts(row: CountsRow) -> TokenCounts:
    """Counts written as an `(input, cache read, cache write, output)` row."""
    return TokenCounts(*row)


def messages(*rows: MessageRow) -> tuple[MessageCounts, ...]:
    """Messages written as `(message id, start counts row, final output count)` rows."""
    return tuple(_message(*row) for row in rows)


def summed(token_counts: Iterable[TokenCounts]) -> TokenCounts:
    """Each count added up across the usage blocks."""
    columns = zip(*(astuple(counted) for counted in token_counts), strict=True)
    return TokenCounts(*(sum(column) for column in columns))


def _message(message_id: str, start: CountsRow, final_output_tokens: int) -> MessageCounts:
    return MessageCounts(message_id, counts(start), final_output_tokens)


MAIN_RUN_MESSAGES = messages(
    ("msg_main_0", (2, 12151, 9364, 7), 188),
    ("msg_main_1", (2, 21515, 281, 16), 63),
    # 60 of the final 107 output tokens are thinking.
    ("msg_main_2", (2, 21796, 112, 8), 107),
)
# `result.usage`, and `modelUsage` with it: the run has no subagent.
MAIN_RUN_TOTALS = counts((6, 55462, 9757, 358))
MAIN_RUN_COST_USD = 0.09633240000000001
MAIN_RUN_NUM_TURNS = 4

SUBAGENT_RUN_LEAD_MESSAGES = messages(
    ("msg_lead_0", (2, 12151, 7423, 17), 175),
    ("msg_lead_1", (2, 19574, 2426, 16), 96),
    ("msg_lead_2", (2, 22000, 143, 43), 43),
)
# The subagent's first message, seen only through its `assistant` frame. Its final output count is printed
# nowhere: 97 is what `modelUsage` leaves once the lead thread and the hand-back usage are taken out.
SUBAGENT_RUN_SUBAGENT_MESSAGES = messages(("msg_sub_0", (2, 0, 14561, 16), 97))
# `tool_use_result.usage` on the lead thread's `tool_result` for the subagent call: the subagent's last
# message, 36 of whose output tokens are thinking.
SUBAGENT_RUN_HANDBACK = counts((2, 14561, 1822, 39))
# `result.usage` covers the lead thread; `modelUsage` adds the subagent.
SUBAGENT_RUN_LEAD_TOTALS = counts((6, 53725, 9992, 314))
SUBAGENT_RUN_MODEL_TOTALS = counts((10, 68286, 26375, 450))
SUBAGENT_RUN_COST_USD = 0.18454820000000002
SUBAGENT_RUN_NUM_TURNS = 3

_STATUS_LINE = '{"type":"system","subtype":"status","status":"requesting"}'

_MAIN_RUN_LINES = (
    (
        '{"type":"system","subtype":"init","cwd":"/workspace","session_id":"7d4c1e52-3b0a-4f6e-9a18-5c2e0b9d3f71",'
        '"tools":["Task","Bash","Read"],"model":"claude-opus-5-5","permissionMode":"bypassPermissions",'
        '"claude_code_version":"2.1.295"}'
    ),
    _STATUS_LINE,
    (
        '{"type":"stream_event","event":{"type":"message_start","message":{"model":"claude-opus-5-5",'
        '"id":"msg_main_0","type":"message","role":"assistant","content":[],"stop_reason":null,'
        '"usage":{"input_tokens":2,"cache_creation_input_tokens":9364,"cache_read_input_tokens":12151,'
        '"cache_creation":{"ephemeral_5m_input_tokens":0,"ephemeral_1h_input_tokens":9364},"output_tokens":7,'
        '"service_tier":"standard","inference_geo":"global"}}},"parent_tool_use_id":null,'
        '"api_message_id":"msg_main_0"}'
    ),
    (
        '{"type":"stream_event","event":{"type":"content_block_start","index":0,"content_block":{"type":"text",'
        '"text":""}},"parent_tool_use_id":null,"api_message_id":"msg_main_0"}'
    ),
    (
        '{"type":"stream_event","event":{"type":"content_block_delta","index":0,"delta":{"type":"text_delta",'
        '"text":"I\'ll check the line count of notes.txt and the byte count of calc.py."}},"parent_tool_use_id":null,'
        '"api_message_id":"msg_main_0"}'
    ),
    (
        '{"type":"assistant","message":{"model":"claude-opus-5-5","id":"msg_main_0","type":"message",'
        '"role":"assistant","content":[{"type":"text","text":"I\'ll check the line count of notes.txt and the byte coun'
        't of calc.py."}],"stop_reason":null,"usage":{"input_tokens":2,"cache_creation_input_tokens":9364,'
        '"cache_read_input_tokens":12151,"cache_creation":{"ephemeral_5m_input_tokens":0,'
        '"ephemeral_1h_input_tokens":9364},"output_tokens":7,"service_tier":"standard","inference_geo":"global"}},'
        '"parent_tool_use_id":null,"request_id":"req_main_0"}'
    ),
    (
        '{"type":"stream_event","event":{"type":"content_block_stop","index":0},"parent_tool_use_id":null,'
        '"api_message_id":"msg_main_0"}'
    ),
    (
        '{"type":"stream_event","event":{"type":"content_block_start","index":1,"content_block":{"type":"tool_use",'
        '"id":"toolu_main_0","name":"Bash","input":{},"caller":{"type":"direct"}}},"parent_tool_use_id":null,'
        '"api_message_id":"msg_main_0"}'
    ),
    (
        '{"type":"stream_event","event":{"type":"content_block_delta","index":1,"delta":{"type":"input_json_delta",'
        r'"partial_json":"{\"command\": \"wc -l notes.txt\", \"description\": \"Count lines in notes file\"}"}},'
        '"parent_tool_use_id":null,"api_message_id":"msg_main_0"}'
    ),
    (
        '{"type":"assistant","message":{"model":"claude-opus-5-5","id":"msg_main_0","type":"message",'
        '"role":"assistant","content":[{"type":"tool_use","id":"toolu_main_0","name":"Bash",'
        '"input":{"command":"wc -l notes.txt","description":"Count lines in notes file"},"caller":{"type":"direct"}}],'
        '"stop_reason":null,"usage":{"input_tokens":2,"cache_creation_input_tokens":9364,'
        '"cache_read_input_tokens":12151,"cache_creation":{"ephemeral_5m_input_tokens":0,'
        '"ephemeral_1h_input_tokens":9364},"output_tokens":7,"service_tier":"standard","inference_geo":"global"}},'
        '"parent_tool_use_id":null,"request_id":"req_main_0"}'
    ),
    (
        '{"type":"stream_event","event":{"type":"content_block_stop","index":1},"parent_tool_use_id":null,'
        '"api_message_id":"msg_main_0"}'
    ),
    (
        '{"type":"stream_event","event":{"type":"content_block_start","index":2,"content_block":{"type":"tool_use",'
        '"id":"toolu_main_1","name":"Bash","input":{},"caller":{"type":"direct"}}},"parent_tool_use_id":null,'
        '"api_message_id":"msg_main_0"}'
    ),
    (
        '{"type":"stream_event","event":{"type":"content_block_delta","index":2,"delta":{"type":"input_json_delta",'
        r'"partial_json":"{\"command\": \"wc -c calc.py\", \"description\": \"Count bytes in calc file\"}"}},'
        '"parent_tool_use_id":null,"api_message_id":"msg_main_0"}'
    ),
    (
        '{"type":"assistant","message":{"model":"claude-opus-5-5","id":"msg_main_0","type":"message",'
        '"role":"assistant","content":[{"type":"tool_use","id":"toolu_main_1","name":"Bash",'
        '"input":{"command":"wc -c calc.py","description":"Count bytes in calc file"},"caller":{"type":"direct"}}],'
        '"stop_reason":null,"usage":{"input_tokens":2,"cache_creation_input_tokens":9364,'
        '"cache_read_input_tokens":12151,"cache_creation":{"ephemeral_5m_input_tokens":0,'
        '"ephemeral_1h_input_tokens":9364},"output_tokens":7,"service_tier":"standard","inference_geo":"global"}},'
        '"parent_tool_use_id":null,"request_id":"req_main_0"}'
    ),
    (
        '{"type":"stream_event","event":{"type":"content_block_stop","index":2},"parent_tool_use_id":null,'
        '"api_message_id":"msg_main_0"}'
    ),
    (
        '{"type":"stream_event","event":{"type":"message_delta","delta":{"stop_reason":"tool_use",'
        '"stop_sequence":null,"stop_details":null,"container":null},"usage":{"input_tokens":2,'
        '"cache_creation_input_tokens":9364,"cache_read_input_tokens":12151,"output_tokens":188,'
        '"output_tokens_details":{"thinking_tokens":0},"iterations":[{"input_tokens":2,"output_tokens":188,'
        '"cache_read_input_tokens":12151,"cache_creation_input_tokens":9364,'
        '"cache_creation":{"ephemeral_5m_input_tokens":0,"ephemeral_1h_input_tokens":9364},"type":"message"}]},'
        '"context_management":{"applied_edits":[]}},"parent_tool_use_id":null,"api_message_id":"msg_main_0"}'
    ),
    (
        '{"type":"stream_event","event":{"type":"message_stop"},"parent_tool_use_id":null,'
        '"api_message_id":"msg_main_0"}'
    ),
    '{"type":"rate_limit_event","rate_limit_info":{"status":"allowed"}}',
    (
        '{"type":"user","message":{"role":"user","content":[{"tool_use_id":"toolu_main_1","type":"tool_result",'
        '"content":"32 calc.py","is_error":false}]},"parent_tool_use_id":null}'
    ),
    (
        '{"type":"user","message":{"role":"user","content":[{"tool_use_id":"toolu_main_0","type":"tool_result",'
        '"content":"3 notes.txt","is_error":false}]},"parent_tool_use_id":null}'
    ),
    _STATUS_LINE,
    (
        '{"type":"stream_event","event":{"type":"message_start","message":{"model":"claude-opus-5-5",'
        '"id":"msg_main_1","type":"message","role":"assistant","content":[],"stop_reason":null,'
        '"usage":{"input_tokens":2,"cache_creation_input_tokens":281,"cache_read_input_tokens":21515,'
        '"cache_creation":{"ephemeral_5m_input_tokens":0,"ephemeral_1h_input_tokens":281},"output_tokens":16,'
        '"service_tier":"standard","inference_geo":"global"}}},"parent_tool_use_id":null,'
        '"api_message_id":"msg_main_1"}'
    ),
    (
        '{"type":"stream_event","event":{"type":"content_block_start","index":0,"content_block":{"type":"tool_use",'
        '"id":"toolu_main_2","name":"Read","input":{},"caller":{"type":"direct"}}},"parent_tool_use_id":null,'
        '"api_message_id":"msg_main_1"}'
    ),
    (
        '{"type":"stream_event","event":{"type":"content_block_delta","index":0,"delta":{"type":"input_json_delta",'
        r'"partial_json":"{\"file_path\": \"/workspace/calc.py\"}"}},"parent_tool_use_id":null,'
        '"api_message_id":"msg_main_1"}'
    ),
    (
        '{"type":"assistant","message":{"model":"claude-opus-5-5","id":"msg_main_1","type":"message",'
        '"role":"assistant","content":[{"type":"tool_use","id":"toolu_main_2","name":"Read",'
        '"input":{"file_path":"/workspace/calc.py"},"caller":{"type":"direct"}}],"stop_reason":null,'
        '"usage":{"input_tokens":2,"cache_creation_input_tokens":281,"cache_read_input_tokens":21515,'
        '"cache_creation":{"ephemeral_5m_input_tokens":0,"ephemeral_1h_input_tokens":281},"output_tokens":16,'
        '"service_tier":"standard","inference_geo":"global"}},"parent_tool_use_id":null,"request_id":"req_main_1"}'
    ),
    (
        '{"type":"stream_event","event":{"type":"content_block_stop","index":0},"parent_tool_use_id":null,'
        '"api_message_id":"msg_main_1"}'
    ),
    (
        '{"type":"user","message":{"role":"user","content":[{"tool_use_id":"toolu_main_2","type":"tool_result",'
        r'"content":"1\tdef add(a, b):\n2\t    return a + b\n3\t"}]},"parent_tool_use_id":null}'
    ),
    (
        '{"type":"stream_event","event":{"type":"message_delta","delta":{"stop_reason":"tool_use",'
        '"stop_sequence":null,"stop_details":null,"container":null},"usage":{"input_tokens":2,'
        '"cache_creation_input_tokens":281,"cache_read_input_tokens":21515,"output_tokens":63,'
        '"output_tokens_details":{"thinking_tokens":0},"iterations":[{"input_tokens":2,"output_tokens":63,'
        '"cache_read_input_tokens":21515,"cache_creation_input_tokens":281,'
        '"cache_creation":{"ephemeral_5m_input_tokens":0,"ephemeral_1h_input_tokens":281},"type":"message"}]},'
        '"context_management":{"applied_edits":[]}},"parent_tool_use_id":null,"api_message_id":"msg_main_1"}'
    ),
    (
        '{"type":"stream_event","event":{"type":"message_stop"},"parent_tool_use_id":null,'
        '"api_message_id":"msg_main_1"}'
    ),
    _STATUS_LINE,
    (
        '{"type":"stream_event","event":{"type":"message_start","message":{"model":"claude-opus-5-5",'
        '"id":"msg_main_2","type":"message","role":"assistant","content":[],"stop_reason":null,'
        '"usage":{"input_tokens":2,"cache_creation_input_tokens":112,"cache_read_input_tokens":21796,'
        '"cache_creation":{"ephemeral_5m_input_tokens":0,"ephemeral_1h_input_tokens":112},"output_tokens":8,'
        '"service_tier":"standard","inference_geo":"global"}}},"parent_tool_use_id":null,'
        '"api_message_id":"msg_main_2"}'
    ),
    (
        '{"type":"stream_event","event":{"type":"content_block_start","index":0,"content_block":{"type":"thinking",'
        '"thinking":"","signature":""}},"parent_tool_use_id":null,"api_message_id":"msg_main_2"}'
    ),
    '{"type":"system","subtype":"thinking_tokens","estimated_tokens":50,"estimated_tokens_delta":50}',
    (
        '{"type":"stream_event","event":{"type":"content_block_delta","index":0,"delta":{"type":"thinking_delta",'
        '"thinking":"","estimated_tokens":50}},"parent_tool_use_id":null,"api_message_id":"msg_main_2"}'
    ),
    (
        '{"type":"stream_event","event":{"type":"content_block_delta","index":0,"delta":{"type":"thinking_delta",'
        '"thinking":"","estimated_tokens":null}},"parent_tool_use_id":null,"api_message_id":"msg_main_2"}'
    ),
    '{"type":"system","subtype":"thinking_tokens","estimated_tokens":161,"estimated_tokens_delta":111}',
    (
        '{"type":"stream_event","event":{"type":"content_block_delta","index":0,"delta":{"type":"signature_delta",'
        '"signature":"redacted"}},"parent_tool_use_id":null,"api_message_id":"msg_main_2"}'
    ),
    (
        '{"type":"assistant","message":{"model":"claude-opus-5-5","id":"msg_main_2","type":"message",'
        '"role":"assistant","content":[{"type":"thinking","thinking":"","signature":"redacted"}],"stop_reason":null,'
        '"usage":{"input_tokens":2,"cache_creation_input_tokens":112,"cache_read_input_tokens":21796,'
        '"cache_creation":{"ephemeral_5m_input_tokens":0,"ephemeral_1h_input_tokens":112},"output_tokens":8,'
        '"service_tier":"standard","inference_geo":"global"}},"parent_tool_use_id":null,"request_id":"req_main_2"}'
    ),
    (
        '{"type":"stream_event","event":{"type":"content_block_stop","index":0},"parent_tool_use_id":null,'
        '"api_message_id":"msg_main_2"}'
    ),
    (
        '{"type":"stream_event","event":{"type":"content_block_start","index":1,"content_block":{"type":"text",'
        '"text":""}},"parent_tool_use_id":null,"api_message_id":"msg_main_2"}'
    ),
    (
        '{"type":"stream_event","event":{"type":"content_block_delta","index":1,"delta":{"type":"text_delta",'
        '"text":"`add(17, 25) * 3` is 126, `notes.txt` has 3 lines, and `calc.py` is 32 bytes."}},'
        '"parent_tool_use_id":null,"api_message_id":"msg_main_2"}'
    ),
    (
        '{"type":"assistant","message":{"model":"claude-opus-5-5","id":"msg_main_2","type":"message",'
        '"role":"assistant","content":[{"type":"text","text":"`add(17, 25) * 3` is 126, `notes.txt` has 3 lines,'
        ' and `calc.py` is 32 bytes."}],"stop_reason":null,"usage":{"input_tokens":2,'
        '"cache_creation_input_tokens":112,"cache_read_input_tokens":21796,'
        '"cache_creation":{"ephemeral_5m_input_tokens":0,"ephemeral_1h_input_tokens":112},"output_tokens":8,'
        '"service_tier":"standard","inference_geo":"global"}},"parent_tool_use_id":null,"request_id":"req_main_2"}'
    ),
    (
        '{"type":"stream_event","event":{"type":"content_block_stop","index":1},"parent_tool_use_id":null,'
        '"api_message_id":"msg_main_2"}'
    ),
    (
        '{"type":"stream_event","event":{"type":"message_delta","delta":{"stop_reason":"end_turn",'
        '"stop_sequence":null,"stop_details":null,"container":null},"usage":{"input_tokens":2,'
        '"cache_creation_input_tokens":112,"cache_read_input_tokens":21796,"output_tokens":107,'
        '"output_tokens_details":{"thinking_tokens":60},"iterations":[{"input_tokens":2,"output_tokens":107,'
        '"cache_read_input_tokens":21796,"cache_creation_input_tokens":112,'
        '"cache_creation":{"ephemeral_5m_input_tokens":0,"ephemeral_1h_input_tokens":112},"type":"message"}]},'
        '"context_management":{"applied_edits":[]}},"parent_tool_use_id":null,"api_message_id":"msg_main_2"}'
    ),
    (
        '{"type":"stream_event","event":{"type":"message_stop"},"parent_tool_use_id":null,'
        '"api_message_id":"msg_main_2"}'
    ),
    (
        '{"stop_reason":"end_turn","session_id":"7d4c1e52-3b0a-4f6e-9a18-5c2e0b9d3f71",'
        '"total_cost_usd":0.09633240000000001,"usage":{"input_tokens":6,"cache_creation_input_tokens":9757,'
        '"cache_read_input_tokens":55462,"output_tokens":358,"output_tokens_details":{"thinking_tokens":60},'
        '"server_tool_use":{"web_search_requests":0,"web_fetch_requests":0},"service_tier":"standard",'
        '"cache_creation":{"ephemeral_1h_input_tokens":9757,"ephemeral_5m_input_tokens":0},"inference_geo":"global",'
        '"iterations":[{"input_tokens":2,"output_tokens":107,"cache_read_input_tokens":21796,'
        '"cache_creation_input_tokens":112,"cache_creation":{"ephemeral_5m_input_tokens":0,'
        '"ephemeral_1h_input_tokens":112},"type":"message"}],"speed":"standard","fallback_credit":null},'
        '"modelUsage":{"claude-opus-5-5":{"inputTokens":6,"outputTokens":358,"cacheReadInputTokens":55462,'
        '"cacheCreationInputTokens":9757,"webSearchRequests":0,"costUSD":0.09633240000000001,"contextWindow":1000000,'
        '"maxOutputTokens":128000,"thinkingTokens":60,"canonicalModel":"claude-opus-5-5","provider":"firstParty",'
        '"costBasis":"list"}},"is_error":false,"num_turns":4,"subtype":"success","result":"`add(17, 25) * 3` is 126,'
        ' `notes.txt` has 3 lines, and `calc.py` is 32 bytes.","type":"result"}'
    ),
)

_SUBAGENT_RUN_LINES = (
    (
        '{"type":"system","subtype":"init","cwd":"/workspace","session_id":"2e9f6a03-8c41-4b7d-b5e2-91d0c7a4f6e8",'
        '"tools":["Task","Bash","Read"],"model":"claude-opus-5-5","permissionMode":"bypassPermissions",'
        '"claude_code_version":"2.1.295"}'
    ),
    _STATUS_LINE,
    (
        '{"type":"stream_event","event":{"type":"message_start","message":{"model":"claude-opus-5-5",'
        '"id":"msg_lead_0","type":"message","role":"assistant","content":[],"stop_reason":null,'
        '"usage":{"input_tokens":2,"cache_creation_input_tokens":7423,"cache_read_input_tokens":12151,'
        '"cache_creation":{"ephemeral_5m_input_tokens":0,"ephemeral_1h_input_tokens":7423},"output_tokens":17,'
        '"service_tier":"standard","inference_geo":"global"}}},"parent_tool_use_id":null,'
        '"api_message_id":"msg_lead_0"}'
    ),
    (
        '{"type":"stream_event","event":{"type":"content_block_start","index":0,"content_block":{"type":"tool_use",'
        '"id":"toolu_lead_0","name":"Agent","input":{},"caller":{"type":"direct"}}},"parent_tool_use_id":null,'
        '"api_message_id":"msg_lead_0"}'
    ),
    (
        '{"type":"stream_event","event":{"type":"content_block_delta","index":0,"delta":{"type":"input_json_delta",'
        r'"partial_json":"{\"description\": \"Count lines in notes.txt\", \"subagent_type\": \"general-purpose\",'
        r' \"prompt\": \"In the directory /workspace, run `wc -l notes.txt` with the Bash tool and reply with only the '
        r'number.\", \"run_in_background\": false}"}},"parent_tool_use_id":null,"api_message_id":"msg_lead_0"}'
    ),
    (
        '{"type":"assistant","message":{"model":"claude-opus-5-5","id":"msg_lead_0","type":"message",'
        '"role":"assistant","content":[{"type":"tool_use","id":"toolu_lead_0","name":"Agent",'
        '"input":{"description":"Count lines in notes.txt","subagent_type":"general-purpose",'
        '"prompt":"In the directory /workspace, run `wc -l notes.txt` with the Bash tool and reply with only the numbe'
        'r.","run_in_background":false},"caller":{"type":"direct"}}],"stop_reason":null,"usage":{"input_tokens":2,'
        '"cache_creation_input_tokens":7423,"cache_read_input_tokens":12151,'
        '"cache_creation":{"ephemeral_5m_input_tokens":0,"ephemeral_1h_input_tokens":7423},"output_tokens":17,'
        '"service_tier":"standard","inference_geo":"global"}},"parent_tool_use_id":null,"request_id":"req_lead_0"}'
    ),
    (
        '{"type":"stream_event","event":{"type":"content_block_stop","index":0},"parent_tool_use_id":null,'
        '"api_message_id":"msg_lead_0"}'
    ),
    (
        '{"type":"system","subtype":"task_started","task_id":"agent_lead_0","tool_use_id":"toolu_lead_0",'
        '"description":"Count lines in notes.txt","subagent_type":"general-purpose",'
        '"prompt":"In the directory /workspace, run `wc -l notes.txt` with the Bash tool and reply with only the numbe'
        'r."}'
    ),
    (
        '{"type":"user","message":{"role":"user","content":[{"type":"text","text":"In the directory /workspace,'
        ' run `wc -l notes.txt` with the Bash tool and reply with only the number."}]},'
        '"parent_tool_use_id":"toolu_lead_0","agent_id":"agent_lead_0"}'
    ),
    (
        '{"type":"stream_event","event":{"type":"message_delta","delta":{"stop_reason":"tool_use",'
        '"stop_sequence":null,"stop_details":null,"container":null},"usage":{"input_tokens":2,'
        '"cache_creation_input_tokens":7423,"cache_read_input_tokens":12151,"output_tokens":175,'
        '"output_tokens_details":{"thinking_tokens":0},"iterations":[{"input_tokens":2,"output_tokens":175,'
        '"cache_read_input_tokens":12151,"cache_creation_input_tokens":7423,'
        '"cache_creation":{"ephemeral_5m_input_tokens":0,"ephemeral_1h_input_tokens":7423},"type":"message"}]},'
        '"context_management":{"applied_edits":[]}},"parent_tool_use_id":null,"api_message_id":"msg_lead_0"}'
    ),
    (
        '{"type":"stream_event","event":{"type":"message_stop"},"parent_tool_use_id":null,'
        '"api_message_id":"msg_lead_0"}'
    ),
    '{"type":"rate_limit_event","rate_limit_info":{"status":"allowed"}}',
    (
        '{"type":"system","subtype":"task_progress","task_id":"agent_lead_0","tool_use_id":"toolu_lead_0",'
        '"usage":{"total_tokens":14603,"tool_uses":1,"duration_ms":1875},"last_tool_name":"Bash"}'
    ),
    (
        '{"type":"assistant","message":{"model":"claude-opus-5-5","id":"msg_sub_0","type":"message",'
        '"role":"assistant","content":[{"type":"tool_use","id":"toolu_sub_0","name":"Bash",'
        '"input":{"command":"wc -l notes.txt","description":"Count lines in notes file"},"caller":{"type":"direct"}}],'
        '"stop_reason":null,"usage":{"input_tokens":2,"cache_creation_input_tokens":14561,"cache_read_input_tokens":0,'
        '"cache_creation":{"ephemeral_5m_input_tokens":14561,"ephemeral_1h_input_tokens":0},"output_tokens":16,'
        '"service_tier":"standard","inference_geo":"global"}},"parent_tool_use_id":"toolu_lead_0",'
        '"agent_id":"agent_lead_0","request_id":"req_sub_0"}'
    ),
    (
        '{"type":"user","message":{"role":"user","content":[{"tool_use_id":"toolu_sub_0","type":"tool_result",'
        '"content":"3 notes.txt","is_error":false}]},"parent_tool_use_id":"toolu_lead_0","agent_id":"agent_lead_0"}'
    ),
    '{"type":"system","subtype":"task_updated","task_id":"agent_lead_0","patch":{"status":"completed"}}',
    (
        '{"type":"system","subtype":"task_notification","task_id":"agent_lead_0","tool_use_id":"toolu_lead_0",'
        '"status":"completed","summary":"3","usage":{"total_tokens":16571,"tool_uses":1,"duration_ms":3482}}'
    ),
    (
        '{"type":"user","message":{"role":"user","content":[{"tool_use_id":"toolu_lead_0","type":"tool_result",'
        r'"content":[{"type":"text","text":"[Subagent hand-back]\n  3\n<usage>subagent_tokens: 16424\ntool_uses: 1\ndur'
        'ation_ms: 3484</usage>"}]}]},"parent_tool_use_id":null,"tool_use_result":{"status":"completed",'
        '"agentId":"agent_lead_0","resolvedModel":"claude-opus-5-5","totalTokens":16424,"totalToolUseCount":1,'
        '"usage":{"output_tokens_details":{"thinking_tokens":36},"input_tokens":2,"cache_creation_input_tokens":1822,'
        '"cache_read_input_tokens":14561,"output_tokens":39,"server_tool_use":{"web_search_requests":0,'
        '"web_fetch_requests":0},"service_tier":"standard","cache_creation":{"ephemeral_1h_input_tokens":0,'
        '"ephemeral_5m_input_tokens":1822},"inference_geo":"global","iterations":[{"input_tokens":2,'
        '"output_tokens":39,"cache_read_input_tokens":14561,"cache_creation_input_tokens":1822,'
        '"cache_creation":{"ephemeral_5m_input_tokens":1822,"ephemeral_1h_input_tokens":0},"type":"message"}],'
        '"speed":"standard","fallback_credit":null}}}'
    ),
    _STATUS_LINE,
    (
        '{"type":"stream_event","event":{"type":"message_start","message":{"model":"claude-opus-5-5",'
        '"id":"msg_lead_1","type":"message","role":"assistant","content":[],"stop_reason":null,'
        '"usage":{"input_tokens":2,"cache_creation_input_tokens":2426,"cache_read_input_tokens":19574,'
        '"cache_creation":{"ephemeral_5m_input_tokens":0,"ephemeral_1h_input_tokens":2426},"output_tokens":16,'
        '"service_tier":"standard","inference_geo":"global"}}},"parent_tool_use_id":null,'
        '"api_message_id":"msg_lead_1"}'
    ),
    (
        '{"type":"stream_event","event":{"type":"content_block_start","index":0,"content_block":{"type":"tool_use",'
        '"id":"toolu_lead_1","name":"Bash","input":{},"caller":{"type":"direct"}}},"parent_tool_use_id":null,'
        '"api_message_id":"msg_lead_1"}'
    ),
    (
        '{"type":"stream_event","event":{"type":"content_block_delta","index":0,"delta":{"type":"input_json_delta",'
        r'"partial_json":"{\"command\": \"wc -c /workspace/calc.py\", \"description\": \"Count bytes in calc.py\"}"}},'
        '"parent_tool_use_id":null,"api_message_id":"msg_lead_1"}'
    ),
    (
        '{"type":"assistant","message":{"model":"claude-opus-5-5","id":"msg_lead_1","type":"message",'
        '"role":"assistant","content":[{"type":"tool_use","id":"toolu_lead_1","name":"Bash",'
        '"input":{"command":"wc -c /workspace/calc.py","description":"Count bytes in calc.py"},'
        '"caller":{"type":"direct"}}],"stop_reason":null,"usage":{"input_tokens":2,"cache_creation_input_tokens":2426,'
        '"cache_read_input_tokens":19574,"cache_creation":{"ephemeral_5m_input_tokens":0,'
        '"ephemeral_1h_input_tokens":2426},"output_tokens":16,"service_tier":"standard","inference_geo":"global"}},'
        '"parent_tool_use_id":null,"request_id":"req_lead_1"}'
    ),
    (
        '{"type":"stream_event","event":{"type":"content_block_stop","index":0},"parent_tool_use_id":null,'
        '"api_message_id":"msg_lead_1"}'
    ),
    (
        '{"type":"stream_event","event":{"type":"message_delta","delta":{"stop_reason":"tool_use",'
        '"stop_sequence":null,"stop_details":null,"container":null},"usage":{"input_tokens":2,'
        '"cache_creation_input_tokens":2426,"cache_read_input_tokens":19574,"output_tokens":96,'
        '"output_tokens_details":{"thinking_tokens":0},"iterations":[{"input_tokens":2,"output_tokens":96,'
        '"cache_read_input_tokens":19574,"cache_creation_input_tokens":2426,'
        '"cache_creation":{"ephemeral_5m_input_tokens":0,"ephemeral_1h_input_tokens":2426},"type":"message"}]},'
        '"context_management":{"applied_edits":[]}},"parent_tool_use_id":null,"api_message_id":"msg_lead_1"}'
    ),
    (
        '{"type":"stream_event","event":{"type":"message_stop"},"parent_tool_use_id":null,'
        '"api_message_id":"msg_lead_1"}'
    ),
    (
        '{"type":"user","message":{"role":"user","content":[{"tool_use_id":"toolu_lead_1","type":"tool_result",'
        '"content":"32 /workspace/calc.py","is_error":false}]},"parent_tool_use_id":null}'
    ),
    _STATUS_LINE,
    (
        '{"type":"stream_event","event":{"type":"message_start","message":{"model":"claude-opus-5-5",'
        '"id":"msg_lead_2","type":"message","role":"assistant","content":[],"stop_reason":null,'
        '"usage":{"input_tokens":2,"cache_creation_input_tokens":143,"cache_read_input_tokens":22000,'
        '"cache_creation":{"ephemeral_5m_input_tokens":0,"ephemeral_1h_input_tokens":143},"output_tokens":43,'
        '"service_tier":"standard","inference_geo":"global"}}},"parent_tool_use_id":null,'
        '"api_message_id":"msg_lead_2"}'
    ),
    (
        '{"type":"stream_event","event":{"type":"content_block_start","index":0,"content_block":{"type":"text",'
        '"text":""}},"parent_tool_use_id":null,"api_message_id":"msg_lead_2"}'
    ),
    (
        '{"type":"stream_event","event":{"type":"content_block_delta","index":0,"delta":{"type":"text_delta",'
        '"text":"notes.txt has 3 lines (the subagent\'s count) and calc.py is 32 bytes (my own `wc -c`)."}},'
        '"parent_tool_use_id":null,"api_message_id":"msg_lead_2"}'
    ),
    (
        '{"type":"assistant","message":{"model":"claude-opus-5-5","id":"msg_lead_2","type":"message",'
        '"role":"assistant","content":[{"type":"text","text":"notes.txt has 3 lines (the subagent\'s count) and calc.py'
        ' is 32 bytes (my own `wc -c`)."}],"stop_reason":null,"usage":{"input_tokens":2,'
        '"cache_creation_input_tokens":143,"cache_read_input_tokens":22000,'
        '"cache_creation":{"ephemeral_5m_input_tokens":0,"ephemeral_1h_input_tokens":143},"output_tokens":43,'
        '"service_tier":"standard","inference_geo":"global"}},"parent_tool_use_id":null,"request_id":"req_lead_2"}'
    ),
    (
        '{"type":"stream_event","event":{"type":"content_block_stop","index":0},"parent_tool_use_id":null,'
        '"api_message_id":"msg_lead_2"}'
    ),
    (
        '{"type":"stream_event","event":{"type":"message_delta","delta":{"stop_reason":"end_turn",'
        '"stop_sequence":null,"stop_details":null,"container":null},"usage":{"input_tokens":2,'
        '"cache_creation_input_tokens":143,"cache_read_input_tokens":22000,"output_tokens":43,'
        '"output_tokens_details":{"thinking_tokens":0},"iterations":[{"input_tokens":2,"output_tokens":43,'
        '"cache_read_input_tokens":22000,"cache_creation_input_tokens":143,'
        '"cache_creation":{"ephemeral_5m_input_tokens":0,"ephemeral_1h_input_tokens":143},"type":"message"}]},'
        '"context_management":{"applied_edits":[]}},"parent_tool_use_id":null,"api_message_id":"msg_lead_2"}'
    ),
    (
        '{"type":"stream_event","event":{"type":"message_stop"},"parent_tool_use_id":null,'
        '"api_message_id":"msg_lead_2"}'
    ),
    (
        '{"stop_reason":"end_turn","session_id":"2e9f6a03-8c41-4b7d-b5e2-91d0c7a4f6e8",'
        '"total_cost_usd":0.18454820000000002,"usage":{"input_tokens":6,"cache_creation_input_tokens":9992,'
        '"cache_read_input_tokens":53725,"output_tokens":314,"output_tokens_details":{"thinking_tokens":0},'
        '"server_tool_use":{"web_search_requests":0,"web_fetch_requests":0},"service_tier":"standard",'
        '"cache_creation":{"ephemeral_1h_input_tokens":9992,"ephemeral_5m_input_tokens":0},"inference_geo":"global",'
        '"iterations":[{"input_tokens":2,"output_tokens":43,"cache_read_input_tokens":22000,'
        '"cache_creation_input_tokens":143,"cache_creation":{"ephemeral_5m_input_tokens":0,'
        '"ephemeral_1h_input_tokens":143},"type":"message"}],"speed":"standard","fallback_credit":null},'
        '"modelUsage":{"claude-opus-5-5":{"inputTokens":10,"outputTokens":450,"cacheReadInputTokens":68286,'
        '"cacheCreationInputTokens":26375,"webSearchRequests":0,"costUSD":0.18454820000000002,"contextWindow":1000000,'
        '"maxOutputTokens":128000,"thinkingTokens":36,"canonicalModel":"claude-opus-5-5","provider":"firstParty",'
        '"costBasis":"list"}},"is_error":false,"num_turns":3,"subtype":"success",'
        '"result":"notes.txt has 3 lines (the subagent\'s count) and calc.py is 32 bytes (my own `wc -c`).",'
        '"type":"result"}'
    ),
)

MAIN_RUN_STDOUT = "\n".join(_MAIN_RUN_LINES)
SUBAGENT_RUN_STDOUT = "\n".join(_SUBAGENT_RUN_LINES)
