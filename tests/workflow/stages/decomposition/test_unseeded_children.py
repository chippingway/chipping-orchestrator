# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""A child its split never seeded runs nothing, whatever label it wears.

A crash can leave a split's child created and never recorded, or recorded and
never seeded behind a parent that parked short of its count. Either carries
the split's receipt in its body and no parent link on its pinned comment, so
nothing has proved the lineage it was owed. The dispatcher holds it ahead of
every stage handler -- an edit's reroute into its own decomposition and a
human's relabel straight to `ready` included -- until a seed lands.
"""
from __future__ import annotations

import contextlib
import itertools
import unittest
from types import MappingProxyType

from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.engine import issue_processing as _issue_processing
from orchestrator.workflow.late_split import lineage as _lineage
from orchestrator.workflow.state import WorkflowLabel
from tests.workflow.stages.decomposition import (
    late_crash_support as _crash,
    replacement_lineage_support as _support,
    replacement_split_support as _split,
)

KEY_PARENT_NUMBER = "parent_number"
KEY_AWAITING_HUMAN = "awaiting_human"

PARK_HOLD = "replacement_lineage_unproved"

RUN_AGENT = "run_agent"

# What the implementer a released child is handed answers with.
IMPLEMENTED_MESSAGE = "implemented"

# How the child was left, beside whether its parent's next tick recovered the
# split: created and never recorded, or adopted -- recorded and never seeded
# -- behind a parent parked short of its count.
_LEFT = MappingProxyType({
    "created and never recorded": False,
    "adopted and never seeded": True,
})

# The labels a human or an edit can put it under, each naming a handler that
# would run it: the implementer's two, its own decomposition, and its poll.
_RUNNABLE = (WorkflowLabel.READY, WorkflowLabel.IMPLEMENTING, WorkflowLabel.DECOMPOSING, WorkflowLabel.BLOCKED)


def _dispatch(github, spec, issue) -> None:
    """Route one issue the way a tick does, guards and all."""
    _issue_processing._route_issue_to_handler(github, spec, issue, github.workflow_label(issue))


def _crashed(recovered: bool) -> tuple:
    """A two-child split dead behind its first create, recovered where asked; the client and that child."""
    github, issue = _split.late_parent(_support.own_split())
    dying = _crash.killed_after(github, "create_child_issue")
    with dying, contextlib.suppress(KeyboardInterrupt):
        _split.redecompose(github, issue, _split.REPLACEMENT_MANIFEST)
    if recovered:
        _split.redecompose(github, issue)
    return github, github.created_child_issues[0]


def _parks(github, number: int) -> tuple:
    """What every park on one issue was filed under."""
    return tuple(
        event.get("reason") for event in github.recorded_events
        if event.get("event") == _split.PARK_EVENT and event.get("issue") == number
    )


class UnseededChildTest(unittest.TestCase):
    """The dispatcher holds a receipted child with no parent link, and lets it go once seeded."""

    def test_no_label_runs_it(self) -> None:
        # Ticked twice under each label: no agent runs, no issue is opened,
        # the label stays where it was put, and the hold is said once.
        for left, label in itertools.product(_LEFT, _RUNNABLE):
            with self.subTest(left=left, label=label):
                github, child = _crashed(_LEFT[left])
                github.set_workflow_label(child, label, guarded=False)

                ticks = [_split.redecompose(github, child, tick=_dispatch) for _ in range(2)]

                self.assertEqual([mocks[RUN_AGENT].call_count for mocks in ticks], [0, 0])
                self.assertEqual(_split.replacements(github), [child.number])
                self.assertEqual(github.workflow_label(child), label)
                self.assertEqual(_parks(github, child.number), (PARK_HOLD,))

    def test_a_seed_lets_it_run(self) -> None:
        # Held under `ready`, then seeded as its parent's recovery would seed
        # it -- the parent link, the lineage, and the park lifted with them --
        # the next tick hands it to its implementer.
        github, child = _crashed(recovered=True)
        github.set_workflow_label(child, WorkflowLabel.READY, guarded=False)
        _split.redecompose(github, child, tick=_dispatch)
        seed = PinnedState()
        _lineage.write_late_ancestry(seed, _support.ROOT_LINEAGE)
        seed.set(KEY_PARENT_NUMBER, _support.PARENT)
        seed.set(KEY_AWAITING_HUMAN, False)
        held = github.pinned_data(child.number)
        github.seed_state(child.number, **{**held, **seed.data})

        mocks = _split.redecompose(github, child, IMPLEMENTED_MESSAGE, tick=_dispatch)

        self.assertEqual(mocks[RUN_AGENT].call_count, 1)


if __name__ == "__main__":
    unittest.main()
