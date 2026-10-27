# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Fenced adjudication replies and proposed slices for late-split tests."""
from __future__ import annotations

import json

from orchestrator.workflow.stages.decomposition.late_budget import ESTIMATE

LATE_FENCE = "orchestrator-late-manifest"

DEPENDS_ON = "depends_on"

# The two ways a slice can leave its prerequisites unsaid: the key left off,
# and the key stated as JSON null. A fresh reply is refused for either, each
# under its own diagnostic; a recorded manifest reads both as no prerequisites.
OMITTED = "omitted"
NULL = "null"


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
    what a recorded manifest is read back as no manifest for.
    """
    proposed = {"title": title, "body": body, DEPENDS_ON: list(depends_on)}
    if estimated is not None:
        proposed[ESTIMATE] = estimated
    return proposed


def unstated(proposed: dict, how: str) -> dict:
    """The same slice with its dependency list `OMITTED`, or stated as `NULL`."""
    kept = {field: declared for field, declared in proposed.items() if field != DEPENDS_ON}
    if how == NULL:
        kept[DEPENDS_ON] = None
    return kept


def split_reply_of(*declared: object) -> str:
    """A split reply whose children declare exactly these budgets."""
    return late_block(json.dumps({
        "decision": "split",
        "children": [
            proposed_slice(f"A{index}", "a", budget)
            for index, budget in enumerate(declared)
        ],
    }))
