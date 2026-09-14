# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The launch identity and closed event vocabularies of the lifetime run budget."""
from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class BudgetPhase(StrEnum):
    """Which durable step of an issue's agent-run budget one record is.

    Four rather than two, because a charge and the spawn it paid for are not
    the same event to anybody counting them: the window between them is where
    a tick can die, and an issue whose runs were all reserved and never
    started is a crash loop rather than a workload. The other two are the ends
    of the lifetime -- the launch the ceiling turned away, and the human who
    decided the ceiling was wrong.
    """

    RESERVED = "reserved"
    STARTED = "started"
    EXHAUSTED = "exhausted"
    EXTENDED = "extended"


class ExhaustionReason(StrEnum):
    """Which way the allowance a refused launch met had run out.

    The park has one reason of its own -- a lifetime is spent once -- so the
    thing that tells two refusals apart is the arithmetic behind them. An
    issue standing exactly at its ceiling got there by running; one already
    past it got there because the ceiling moved, and an operator reading a
    park they did not expect needs to be able to tell which.
    """

    ALLOWANCE_SPENT = "allowance_spent"
    ALLOWANCE_EXCEEDED = "allowance_exceeded"


@dataclass(frozen=True)
class AgentRunLaunch:
    """The launch a charge is taken for, as a record may name it.

    The fingerprint is what the ledger charges under, so it is what correlates
    two ticks of one launch; the stage and the role are what an operator reads
    a launch BY, and they are the same two the `agent_spawn` pair records, so
    a budget record and the spawn beside it agree on where a run happened
    without either re-reading the label.
    """

    fingerprint: str
    stage: str
    agent_role: str
