# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""A child whose seed is not the one its split owed it runs nothing, whatever label it wears.

A crash can leave a split's child created and never recorded, or recorded and
never seeded behind a parent that parked short of its count. Either carries
the split's receipt in its body and no parent link on its pinned comment, so
nothing has proved the lineage it was owed. A seed that did land can lose its
late ancestry, or part of it, or come to name another place in the lineage
afterwards. The dispatcher holds every one of them ahead of every stage
handler -- an edit's reroute into its own decomposition and a human's relabel
straight to `ready` included -- until the seed the receipt names is there. A
receipt copied into an issue this orchestrator did not open holds nothing.
"""
from __future__ import annotations

import contextlib
import itertools
import unittest
from dataclasses import dataclass
from types import MappingProxyType

from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.engine import issue_processing as _issue_processing
from orchestrator.workflow.late_split import lineage as _lineage
from orchestrator.workflow.state import WorkflowLabel
from tests.support.fakes import make_issue
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

# Everything a human or an edit can leave it under: every label whose handler
# runs something -- all but the two terminals -- and none, which reaches pickup.
_RUNNABLE = (
    *(label for label in WorkflowLabel if label not in {WorkflowLabel.DONE, WorkflowLabel.REJECTED}),
    None,
)

# An issue a human opened, carrying a receipt copied out of a child's body.
_OUTSIDER = 990

_FOREIGN_REF = "refs/orchestrator/late-split/issue-4/cycle-2/gen-1"

# Another split's receipt, quoted in a slice that copied the body of a child of that split.
_QUOTED_RECEIPT = f"<!--orchestrator-split-child:issue={_OUTSIDER}:attempt=0123456789abcdef:index=0:lineage=none-->"


@dataclass(frozen=True)
class _Lapse:
    """What becomes of a seed that landed whole: the pinned keys taken off it, and the ones written over it.

    `ordinary` splits an issue no late split charged, which owes its child no
    lineage at all.
    """

    stripped: tuple[str, ...] = ()
    added: tuple[tuple[str, object], ...] = ()
    ordinary: bool = False

    def seeded(self) -> tuple:
        """Split once, then change the child's seed this way; the client and that child."""
        github, child = _split_once(self.ordinary)
        kept = {
            key: carried
            for key, carried in github.pinned_data(child.number).items()
            if key not in self.stripped
        }
        github.seed_state(child.number, **{**kept, **dict(self.added)})
        return github, child


# The late ancestry taken off, part of it taken off, the depth or the parent
# link naming another place, the pointer moved to a snapshot that split never
# preserved or cut down to its ref alone, and a lineage written onto a child
# owed none.
_LAPSED_SEEDS = MappingProxyType({
    "its late ancestry taken off": _Lapse(stripped=_lineage.LATE_ANCESTRY_KEYS),
    "part of its late ancestry taken off": _Lapse(stripped=("late_ancestry_cycle_id",)),
    "its depth rewritten": _Lapse(added=(("late_ancestry_depth", 0),)),
    "its parent link naming another issue": _Lapse(added=((KEY_PARENT_NUMBER, _OUTSIDER),)),
    "its pointer moved to another snapshot": _Lapse(added=(("late_ancestry_snapshot_ref", _FOREIGN_REF),)),
    "its pointer's commit taken off": _Lapse(stripped=("late_ancestry_snapshot_sha",)),
    "a late ancestry on an ordinary split's child": _Lapse(added=(("late_ancestry_depth", 1),), ordinary=True),
})


def _dispatch(github, spec, issue) -> None:
    """Route one issue the way a tick does, guards and all."""
    _issue_processing._route_issue_to_handler(github, spec, issue, github.workflow_label(issue))


def _put_under(github, issue, label) -> None:
    """Leave one issue under `label`, or under none."""
    if label is None:
        issue.labels = []
        return
    github.set_workflow_label(issue, label, guarded=False)


def _split_once(ordinary: bool) -> tuple:
    """A one-child split that ran whole; the client and its child.

    Of a late root holding the snapshot its own split preserved, unless
    `ordinary` splits an issue no late split charged.
    """
    github, issue = _split.late_parent(None if ordinary else _support.own_split())
    _split.redecompose(github, issue, _split.ONE_REPLACEMENT_MANIFEST)
    return github, github.created_child_issues[0]


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
    """The dispatcher holds a receipted child whose seed is not the one owed, and lets it go once it is."""

    def test_no_label_runs_it(self) -> None:
        # Never seeded at all, under each label.
        for left, label in itertools.product(_LEFT, _RUNNABLE):
            with self.subTest(left=left, label=label):
                github, child = _crashed(_LEFT[left])
                _put_under(github, child, label)

                self._assert_held(github, child, label)

    def test_a_lapsed_seed_runs_nowhere(self) -> None:
        # Seeded whole by the split, then changed: the receipt still says what
        # was owed, so the seed is held to it under every label.
        for shape, label in itertools.product(_LAPSED_SEEDS, _RUNNABLE):
            with self.subTest(shape=shape, label=label):
                github, child = _LAPSED_SEEDS[shape].seeded()
                _put_under(github, child, label)

                self._assert_held(github, child, label)

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

    def test_a_copied_receipt_holds_nothing(self) -> None:
        # A human pastes a child's body, receipt and all, into an issue of
        # their own: it is no split's child, and its implementer runs.
        github, child = _split_once(ordinary=False)
        copy = make_issue(_OUTSIDER, label=WorkflowLabel.READY, body=child.body)
        github.add_issue(copy)

        mocks = _split.redecompose(github, copy, IMPLEMENTED_MESSAGE, tick=_dispatch)

        self.assertEqual(mocks[RUN_AGENT].call_count, 1)
        self.assertNotIn(PARK_HOLD, _parks(github, _OUTSIDER))

    def test_a_quoted_receipt_is_not_the_one_owed(self) -> None:
        # A slice that quoted its parent's own body carries that body's receipt
        # ahead of the one the split stamped after it; the stamp is what the
        # seed is held to, and a whole seed runs.
        github, child = _split_once(ordinary=True)
        child.body = f"{_QUOTED_RECEIPT}\n\n{child.body}"
        github.set_workflow_label(child, WorkflowLabel.READY, guarded=False)

        mocks = _split.redecompose(github, child, IMPLEMENTED_MESSAGE, tick=_dispatch)

        self.assertEqual(mocks[RUN_AGENT].call_count, 1)
        self.assertNotIn(PARK_HOLD, _parks(github, child.number))

    def _assert_held(self, github, child, label) -> None:
        """Ticked twice: no agent runs, no issue is opened, the label stays, and the hold is said once."""
        ticks = [_split.redecompose(github, child, tick=_dispatch) for _ in range(2)]

        self.assertEqual([mocks[RUN_AGENT].call_count for mocks in ticks], [0, 0])
        self.assertEqual(_split.replacements(github), [child.number])
        self.assertEqual(github.workflow_label(child), label)
        self.assertEqual(_parks(github, child.number), (PARK_HOLD,))


if __name__ == "__main__":
    unittest.main()
