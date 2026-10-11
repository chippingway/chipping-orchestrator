# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Agent final messages that are the provider's words, not the agent's.

Both stages that read a final message as an agent's own have to tell these
apart from an answer, so the samples they are told apart by live in one place:
the observed refusal, and the successful answer that merely writes about it.
Beside them is the quota stop that never reaches a final message at all: an
Antigravity run whose failure record alone names the exhausted quota.
"""
from orchestrator.agents import models as _agent_models
from orchestrator.agents.backends import agy as _agy
from tests.support import agy_stream as _agy_stream

# The process return a timed-out run carries: the runner's sentinel, not one
# the killed CLI gave.
_TIMED_OUT_EXIT = -1
_ACTIVE_TOOL = _agy_stream.ToolStream.tool_step(1, state="ACTIVE", args={"CommandLine": "pytest"})


# The #1408 shape, verbatim: the CLI hands a server-side refusal back through
# the same non-empty final-message field a real agent question arrives on.
PROVIDER_OVERLOAD_MESSAGE = (
    "API Error: 529 Overloaded. This is a server-side issue, usually temporary."
)

# A run that SUCCEEDED and wrote ABOUT the refusal. The marker is matched as a
# prefix, so this stays an ordinary answer.
PROVIDER_OVERLOAD_MENTION = (
    "I added a retry path for the API Error: 529 Overloaded case and "
    "documented it."
)

PROVIDER_UNAVAILABLE_PHRASE = "temporarily unavailable"

SESSION_LIMIT_MESSAGE = "You've hit your session limit · resets 7pm (Asia/Novosibirsk)"

# The #1796 shape, verbatim: a weekly quota arrives on the same final-message
# field, and resets days rather than hours away.
WEEKLY_LIMIT_MESSAGE = "You've hit your weekly limit · resets Sep 25, 12pm (Asia/Novosibirsk)"

SESSION_LIMIT_PHRASE = "session/usage limit"


def agy_quota_stop(*, timed_out: bool = False, unfinished: bool = False) -> _agent_models.AgentResult:
    """A synthetic Antigravity run the account quota stopped, normalized the way a stage receives it.

    Its final message is empty and only the failure record names the quota.
    `timed_out` has the timeout fire as well, and `unfinished` leaves a tool
    step active beside the error terminal.
    """
    events = [_agy_stream.terminal(_agy_stream.FAILURE, response=None, error=_agy_stream.QUOTA_MESSAGE)]
    if unfinished:
        events.insert(0, _ACTIVE_TOOL)
    exit_code = _TIMED_OUT_EXIT if timed_out else 1
    return _agy.agy_result(_agent_models.AgentRunOptions(), _agent_models.SubprocessResult(
        "\n".join(events), _agy_stream.QUOTA_PLAIN_STDERR, exit_code, timed_out, False,
    ))
