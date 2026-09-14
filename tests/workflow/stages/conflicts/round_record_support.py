# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Recorded conflict-round outcomes and the settlement receipt a held tick leaves."""
from __future__ import annotations

CONFLICT_ISSUE = 200

CONFLICT_ROUND = "conflict_round"
SETTLED_OUTCOME = "conflict_settled_outcome"
SETTLED_SHA = "conflict_settled_sha"

OUTCOME = "outcome"
SHA = "sha"


def _rounds_of(github) -> list[dict]:
    """Every `conflict_round` increment this run recorded."""
    return [
        event for event in github.recorded_events
        if event["event"] == CONFLICT_ROUND
    ]


def _outcomes_of(github) -> list[str]:
    """What each recorded round says put the branch where it is."""
    return [round_[OUTCOME] for round_ in _rounds_of(github)]


def _receipt_of(github) -> tuple:
    """The round a hold left for a later tick, as the pair it is written as."""
    pinned = github.pinned_data(CONFLICT_ISSUE)
    return (pinned.get(SETTLED_OUTCOME), pinned.get(SETTLED_SHA))


def _settlements_of(github) -> list[tuple]:
    """The same, with the head each round was recorded against."""
    return [(round_[OUTCOME], round_[SHA]) for round_ in _rounds_of(github)]
