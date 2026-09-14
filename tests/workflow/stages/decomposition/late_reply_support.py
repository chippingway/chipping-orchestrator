# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Fenced adjudication replies and proposed slices for late-split tests."""
from __future__ import annotations

import json

from orchestrator.workflow.stages.decomposition.late_budget import ESTIMATE

LATE_FENCE = "orchestrator-late-manifest"


def late_block(payload: str) -> str:
    """Wrap a payload in the fence a late reply is read out of."""
    return f"```{LATE_FENCE}\n{payload}\n```"


def proposed_slice(
    title: str,
    body: str,
    estimated: object = None,
    depends_on: tuple = (),
) -> dict:
    """One child as a split proposes it: scope, dependencies, and a budget.

    The one builder every late-mode fixture proposes a child through, so a
    case declaring a budget nothing estimated -- a string, a bool, a zero --
    hands the parser the shape an agent would really have sent. `None` is the
    slice that declared no budget at all: what the reply contract refuses, and
    what a manifest recorded before this domain kept budgets reads back as.
    """
    proposed = {"title": title, "body": body, "depends_on": list(depends_on)}
    if estimated is not None:
        proposed[ESTIMATE] = estimated
    return proposed


def split_reply_of(*declared: object) -> str:
    """A split reply whose children declare exactly these budgets."""
    return late_block(json.dumps({
        "decision": "split",
        "children": [
            proposed_slice(f"A{index}", "a", budget)
            for index, budget in enumerate(declared)
        ],
    }))
