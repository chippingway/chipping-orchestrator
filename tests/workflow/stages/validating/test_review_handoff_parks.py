# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""A park another road records while a change request is handed over stays that road's, and launches nobody.

The handoff's commit is decided on the park's flags as the tick read them, and
every reading behind its requests -- the one behind the feedback post, the one
ahead of the launch, and each the run circuit charges and starts the launch
from -- holds the request where another road parked the issue meanwhile. A
park awaiting a human, its report undeliverable say, is that human's to
answer: a developer launched under it would answer nobody's ask, and the writes
behind its run would settle the park away. So nothing is relabelled behind it,
charged, or launched, nothing is written over it, and it stays as that road
wrote it -- in the tick the reviewer returned and on a later one, which hands
nothing over while it stands. Once a reply clears it, the next tick hands the
request to its one developer behind its one post.
"""
from __future__ import annotations

import unittest
from functools import partial
from itertools import product
from types import MappingProxyType

from tests.workflow.fixtures import LABEL_FIXING, LABEL_VALIDATING
from tests.workflow.stages.validating import (
    review_handoff_test_support as _support,
    review_verdict_test_support as _world,
    review_write_test_support as _roads,
)

HANDED_BACK = ((_world.ISSUE, LABEL_FIXING), (_world.ISSUE, LABEL_VALIDATING))

# Another road's park of the issue awaiting a human, the report it owed
# undeliverable; and that park as a human's reply leaves it, cleared.
_PARKED = MappingProxyType({"awaiting_human": True, "park_reason": "report_undeliverable"})

_ANSWERED = MappingProxyType({"awaiting_human": False, "park_reason": None})

_PARKS = _roads.Writes(_PARKED)


def _ahead(request: str, case):
    """A patch landing the park right ahead of the handoff's guarded `request`: its preparation, or its commit."""
    return _roads.AnotherRoadAhead(case, bool, _PARKS, request).patched()


def _behind(request: str, when, case):
    """A patch landing the park behind the client's `request` that `when`, asked with `case`, names."""
    return _world.AnotherRoadBehind(case, request, partial(when, case), _PARKS).patched()


def _the_feedback_post(_case, body: str) -> bool:
    """Whether a pull-request post is the reviewer's feedback."""
    return _support.FEEDBACK_NOTICE in body


def _the_relabel(_case, label) -> bool:
    """Whether a relabel is the one announcing the developer's launch."""
    return label == LABEL_FIXING


def _behind_the_relabel(case, _issue) -> bool:
    """Whether a reading of the comment is the first behind the relabel: the one the launch is last held to."""
    return bool(case.github.label_history)


def _the_charge(_case, state) -> bool:
    """Whether a pinned-comment write is the run circuit's charge, reserved and not yet started."""
    return state.get(_support.RESERVATION) == "reserved"


# Where another road's park lands among the handoff's requests, and what the
# tick it lands in leaves: whether it relabelled the issue, whether the request
# is written as handed, and how many feedback posts the pull request carries.
# Right ahead of the handoff's preparation, which posts nothing; ahead of its
# commit, or behind the feedback post, which hand nothing over; and behind
# the relabel to `workflow:fixing`, the last reading the launch is held to,
# or the run circuit's charge, which launch nobody.
_PARKED_AT = (
    ("ahead of the handoff's preparation", partial(_ahead, "prepare"), ((), False, 0)),
    ("ahead of the handoff's commit", partial(_ahead, "commit"), ((), False, 1)),
    ("behind the feedback post", partial(_behind, "pr_comment", _the_feedback_post), ((), False, 1)),
    ("behind the relabel", partial(_behind, "set_workflow_label", _the_relabel), ((True,), True, 1)),
    (
        "behind the launch's last reading",
        partial(_behind, "read_pinned_state", _behind_the_relabel),
        ((True,), True, 1),
    ),
    ("behind the charge", partial(_behind, "write_pinned_state", _the_charge), ((True,), True, 1)),
)


class HandoffParkTest(_support.HandoffWorld, unittest.TestCase):
    """Another road's park is kept as written, and nobody is launched under it until a reply clears it."""

    def test_a_park_recorded_meanwhile_is_kept(self) -> None:
        # Another road parks the issue awaiting a human somewhere among the
        # handoff's requests -- in the tick its reviewer returned, or on a
        # later tick handing the request over from the pinned comment alone.
        # Nobody is launched, nothing is relabelled behind the park, and the
        # park stays exactly as that road wrote it, the request waiting behind
        # its one post; a later tick hands nothing over while it stands. Once
        # a reply clears it, the next tick hands the request to its one
        # developer behind that same post.
        for (name, parks, left), fresh in product(_PARKED_AT, (True, False)):
            with self.subTest(name, fresh=fresh):
                self.setUp()
                held = self._parked_while(parks, fresh=fresh)
                _roads.Writes(_ANSWERED)(self)

                self.assertEqual(
                    (
                        held,
                        self.hands_over().call_count,
                        len(self.feedback_posts()),
                        tuple(self.github.label_history[-2:]),
                    ),
                    ((0, left, True, 0), 1, 1, HANDED_BACK),
                )

    def _parked_while(self, parks, *, fresh: bool) -> tuple:
        """Hand a fresh request over while `parks` lands another road's park; what that leaves.

        The developers that tick launches; whether it relabelled the issue,
        whether the request is written as handed, and how many feedback posts
        there are; whether the park stands as that road wrote it; and the
        developers a later tick launches while it stands.
        """
        decision = self.seeds()
        with parks(self):
            launched = self.hands_over(decision if fresh else None).call_count
        left = (
            tuple(bool(label) for label in self.github.label_history),
            self.waiting()["handed"] is not None,
            len(self.feedback_posts()),
        )
        kept = self.pinned().items() >= _PARKED.items()
        return launched, left, kept, self.hands_over().call_count


if __name__ == "__main__":
    unittest.main()
