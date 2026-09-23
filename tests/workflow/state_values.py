# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Pinned-state keys, agent roles, and spawn charges shared by workflow tests.
"""


# The pinned writes every agent spawn takes before a process exists: the
# agent-run circuit charges the launch `reserved` and then marks it `started`,
# both durably, so a run that crashed or was killed mid-flight is still spent.
# They are the handler's writes only in the sense that its spawn earned them --
# a tick that returns without a write of its own still leaves these two.
AGENT_RUN_CHARGE_WRITES = 2

# The fields those two writes are about: the launch's own ledger, which no
# handler reads or writes. A case asserting that a tick left NOTHING of its
# own durable drops them rather than asserting around them.
AGENT_RUN_CHARGE_KEYS = frozenset((
    "agent_run_fingerprint",
    "agent_run_reservation",
    "agent_runs_used",
))

KEY_AWAITING_HUMAN = "awaiting_human"
KEY_ISSUE_AGENT_RUNS = "issue_agent_runs"
KEY_ISSUE_TOTAL_TOKENS = "issue_total_tokens"
KEY_LAST_ACTION_COMMENT_ID = "last_action_comment_id"
KEY_PARENT_NUMBER = "parent_number"
KEY_PARK_REASON = "park_reason"

ROLE_DEVELOPER = "developer"
ROLE_REVIEWER = "reviewer"
