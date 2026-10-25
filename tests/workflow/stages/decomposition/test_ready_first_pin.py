# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The first record a `ready` decision pins on an issue that pinned nothing, on the production pinned-state roads.

The in-memory client keeps one record per issue apart from the thread, so a
second pin beside the first is a state it cannot hold. Here every reading and
write goes through the production reader and writers over the thread's own
comments, so a pin a human posts with the token account while the decision
runs is a real comment, ahead of whatever the handoff or the reroute would
create, and the record every later reader takes. Neither creates anything
beside it nor rests anything on a pin it shadows, and the next tick decides on
the record that stands.
"""
from __future__ import annotations

import itertools
import unittest
from functools import partial
from types import MappingProxyType
from unittest.mock import patch

from orchestrator.github.pinned_state import PINNED_STATE_MARKER, GitHubStateMixin, pinned_state_body
from tests.support.fakes import FakeGitHubClient, make_issue
from tests.workflow.fixtures import LABEL_READY, _PatchedWorkflowMixin
from tests.workflow.stages.decomposition import child_baseline_support as _baseline, ready_test_support as _support

# A split's child record a human pins by hand: linked to its parent, and with
# no baseline of the requirements it was created with.
_HAND_PINNED = MappingProxyType({"schema_version": 1, "parent_number": _support.PARENT})

# The pins that may appear: one admission refuses, and one it takes.
_APPEARING_PINS = ({"schema_version": 2}, {"schema_version": 1, "agent_runs_used": 1})

# The windows a pin can appear in ahead of the first pin's preparation and its
# creation, as the request it lands behind, and what the tick leaves: no agent
# run, no relabel or pinned write, and the thread told nothing behind the
# decision's reading, the pickup alone behind the pickup's own post.
_PIN_WINDOWS = MappingProxyType({
    "comments_after": (0, ((), _support.SAID_NOTHING, 0)),
    "comment": (0, ((), _support.SAID_PICKUP, 0)),
})

_READ_PIN = "read_pinned_state"

# The pinned readings a first pin's handoff takes before it creates the record:
# the handler's own, the preparation ahead of the pickup, and the one right
# before the creation, behind which a pin posted lands between that reading
# and the write.
_READINGS_BEFORE_THE_CREATE = 3


class ThreadPins(FakeGitHubClient):
    """The in-memory client, its pinned record read and written as the production client does, off the thread."""

    read_pinned_state = GitHubStateMixin.read_pinned_state
    write_pinned_state = GitHubStateMixin.write_pinned_state
    edit_pinned_state = GitHubStateMixin.edit_pinned_state
    _pinned_comment = GitHubStateMixin._pinned_comment
    _send_pinned_edit = GitHubStateMixin._send_pinned_edit


class ReadyFirstPinTest(unittest.TestCase, _PatchedWorkflowMixin, _support.ReadyTicks):
    """A pin a human posts while the handoff runs holds its first pin, and the next tick decides on it."""

    def test_a_pin_appearing_holds_the_first_pin(self) -> None:
        # Posted while the decision reads the thread, failing the pickup's
        # preparation so nothing is posted, or while the pickup goes out,
        # failing the reading right before the creation: one admission
        # refuses, or any pin at all, so nothing is pinned beside it,
        # relabelled, or launched, and its comment stands byte for byte.
        for request, pin in itertools.product(_PIN_WINDOWS, _APPEARING_PINS):
            with self.subTest(request=request, pin=pin):
                gh, issue = self._unpinned()
                lands = _support.LandsAfter(gh, request, 1, partial(_pins, pin))

                self.assertEqual(self.interleaved_tick(gh, issue, lands), _PIN_WINDOWS[request])
                self.assertEqual(self._pins(issue), [pinned_state_body(pin)])

    def test_a_pin_at_the_pickup_is_decided_on_next(self) -> None:
        # Posted while the pickup goes out: nothing is pinned beside it,
        # relabelled, or launched. The next tick decides on that record -- a
        # child carrying no baseline -- and reroutes it, the human's comment
        # the one record rewritten.
        gh, issue = self._unpinned()
        lands = _support.LandsAfter(gh, "comment", 1, partial(_pins, _HAND_PINNED))

        held = self.interleaved_tick(gh, issue, lands)
        self.assertEqual(held, (0, ((), _support.SAID_PICKUP, 0)))
        self.assertEqual(len(self._pins(issue)), 1)
        self.assertEqual(self.ready_tick(gh, issue), 0)

        owed = gh.read_pinned_state(issue).data.get(_support.KEY_REROUTE)
        self.assertEqual(gh.workflow_label(issue), _support.LABEL_DECOMPOSING)
        self.assertEqual(len(self._pins(issue)), 1)
        self.assertIs(owed["unbaselined"], True)

    def test_a_pin_before_the_create_holds_the_rest(self) -> None:
        # Posted between the reading right before the creation and the write:
        # the first pin is created behind it, shadowed by it, and read back as
        # no record of the issue's own, so nothing is relabelled or launched
        # and the human's record stays the one every reader takes.
        gh, issue = self._unpinned()
        landing = partial(_pins, _HAND_PINNED)
        lands = _support.LandsAfter(gh, _READ_PIN, _READINGS_BEFORE_THE_CREATE, landing)

        held = self.interleaved_tick(gh, issue, lands)

        self.assertEqual(held[0], 0)
        self.assertEqual(held[1][0], ())
        self.assertEqual(gh.read_pinned_state(issue).data, _HAND_PINNED)

    def test_a_pin_before_a_reroute_create_holds_it(self) -> None:
        # A trusted comment lands while the pickup goes out, so the handoff
        # hands the change back and the decision reroutes; a pin a human posts
        # between the reading right before the reroute's first pin and its
        # creation shadows that pin. Read back as no record of the issue's
        # own, it licenses nothing: nothing is relabelled and no reroute notice
        # is said, and the human's record stays the one every reader takes.
        # The next tick decides on that record and reroutes it there.
        gh, issue, held = self._shadowed_reroute()
        record = gh.read_pinned_state(issue)
        self.assertEqual(held, (0, ((), _support.SAID_PICKUP, 0)))
        self.assertEqual(record.data, _HAND_PINNED)
        self.assertIn(_support.KEY_REROUTE, self._pins(issue)[-1])

        self.assertEqual(self.ready_tick(gh, issue), 0)
        rerouted = gh.read_pinned_state(issue)
        self.assertEqual(
            (rerouted.comment_id, gh.workflow_label(issue), _support.notices(gh)),
            (record.comment_id, _support.LABEL_DECOMPOSING, (0, 1, 1)),
        )
        self.assertIs(rerouted.data[_support.KEY_REROUTE]["unbaselined"], True)

    def _unpinned(self) -> tuple:
        """A client on the production pinned roads, and an issue on `ready` that pinned nothing."""
        gh = ThreadPins()
        issue = make_issue(_support.CHILD, label=LABEL_READY)
        gh.add_issue(issue)
        return gh, issue

    def _shadowed_reroute(self) -> tuple:
        """The tick whose reroute a human's pin shadows: the client, the issue, and what the tick left."""
        gh, issue = self._unpinned()
        commented = _support.LandsAfter(gh, "comment", 1, _baseline.Commented(_support.TRUSTED))
        pinned = _support.LandsAfter(gh, _READ_PIN, _READINGS_BEFORE_THE_CREATE, partial(_pins, _HAND_PINNED))
        with patch.object(gh, commented.request, commented):
            return gh, issue, self.interleaved_tick(gh, issue, pinned)

    def _pins(self, issue) -> list:
        """The bodies of the pinned-state comments the issue's thread carries."""
        return [posted.body for posted in issue.comments if posted.body.startswith(PINNED_STATE_MARKER)]


def _pins(record, gh: FakeGitHubClient, issue) -> None:
    """Post `record` as a pinned-state comment, the way a human with the token account would."""
    issue.create_comment(pinned_state_body(dict(record)))


if __name__ == "__main__":
    unittest.main()
