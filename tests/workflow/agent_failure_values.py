# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Agent final messages that are the provider's words, not the agent's.

Both stages that read a final message as an agent's own have to tell these
apart from an answer, so the samples they are told apart by live in one place:
the observed refusal, and the successful answer that merely writes about it.
"""


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
