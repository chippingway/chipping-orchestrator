# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What a landed base rewrite's finish left on GitHub, read back the way the next tick reads it.

The pinned record, read through the evidence records' own owners rather than
as raw JSON, so a case compares what the next tick would believe; the labels a
finish wrote; and the notices it posted on the pull request, told apart from
the reports and artifacts beside them. The pinned keys are spelled literally,
since live issues already carry them.
"""
from __future__ import annotations

from types import MappingProxyType

from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.engine import (
    verification_record_state as _record_state,
    verification_settlement_state as _settlement,
)
from orchestrator.workflow.state import WorkflowLabel

KEY_PENDING_PUSH = "pending_auto_base_rebase_push_sha"
KEY_REWRITE_PR = "pending_auto_base_rebase_rewrite_pr"
KEY_REWRITE_STAGE = "pending_auto_base_rebase_rewrite_stage"
KEY_REWRITE_SHA = "pending_auto_base_rebase_rewrite_sha"
KEY_ANNOUNCED = "pending_auto_base_rebase_announced_sha"
KEY_REVIEW_ROUND = "review_round"
KEY_REVISION_FLOOR = "verification_evidence_revision"
KEY_FAILED_VERIFICATION = "auto_base_rebase_failed_verification"

# Every field one attempt puts on the comment, which a finish retires as one.
ATTEMPT_KEYS = (KEY_PENDING_PUSH, KEY_REWRITE_PR, KEY_REWRITE_STAGE, KEY_REWRITE_SHA, KEY_ANNOUNCED)

# The attempt as a finish leaves it: every member blanked rather than removed.
RETIRED = MappingProxyType(dict.fromkeys(ATTEMPT_KEYS))

ROUTED = (WorkflowLabel.VALIDATING,)

# Why settled evidence a rewrite moved past retired, as history spells it.
INVALIDATED = "invalidated"

# How the announcement of a landing and the notice of a failed run open.
_FINISH_NOTICES = (":mag:", ":x:")


def pinned(case) -> dict:
    """The record `case`'s issue's pinned comment carries now."""
    return case.gh.pinned_data(case.issue.number)


def attempt(record: dict) -> dict:
    """The attempt's members as `record` carries them."""
    return {key: record.get(key) for key in ATTEMPT_KEYS}


def records(durable: dict) -> tuple:
    """The pending transaction and current evidence `durable` carries, and each retired record's receipt and why."""
    reading = PinnedState(state_data=durable)
    history = _settlement.read_evidence_history(reading) or ()
    return (
        _record_state.read_pending_evidence(reading),
        _settlement.read_current_evidence(reading),
        tuple((entry.receipt, entry.retired.value) for entry in history),
    )


def pinned_records(case) -> tuple:
    """What `case`'s pinned comment carries now of the evidence records (`records`)."""
    return records(pinned(case))


def failure(durable: dict):
    """The failure notice `durable` records -- the head it is about and its text -- or what stands in its place."""
    return durable.get(KEY_FAILED_VERIFICATION)


def relabels(case) -> tuple:
    """Every workflow label written onto `case`'s issue, in order."""
    issue = case.issue.number
    return tuple(label for number, label in case.gh.label_history if number == issue)


def notices(case) -> list[str]:
    """Every notice a finish posted on `case`'s pull request, oldest first: no report or artifact."""
    return [
        body for number, body in case.gh.posted_pr_comments
        if number == case.pull_request.number and body.startswith(_FINISH_NOTICES)
    ]
