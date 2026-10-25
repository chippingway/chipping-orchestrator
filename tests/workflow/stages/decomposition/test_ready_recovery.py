# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""A `ready` checkpoint refused, never confirmed, or read back edited stops what depends on it; a later tick recovers.

The decision lands its reroute, or its handoff, as one guarded write before
any relabel, notice past the pickup, consumption, or launch. Each case here
leaves that write refused, accepted with its answer lost, edited by hand right
behind it, or unreadable when it is read back, and drives the tick after it:
nothing is said, relabelled, or launched twice, and a reroute whose reset
landed never reads as requirements nobody changed. Others land an operator's relabel between two ticks, or a
post GitHub refuses, and hold the notice to what it already said and how often
it is tried. The edits are a human's, made on GitHub between two readings --
never a second orchestrator writer inside a claim. Operator holds are
`test_ready_holds`'s, readings GitHub answers apart from the dispatched issue
`test_ready_readings`'s, and a first pin's production readings
`test_ready_first_pin`'s.
"""
from __future__ import annotations

import unittest
from unittest.mock import patch

from orchestrator.github.pinned_refusal import RecordRefused
from tests.support.fakes import FakeGitHubClient
from tests.workflow.fixtures import LABEL_READY, _PatchedWorkflowMixin
from tests.workflow.stages.decomposition import ready_test_support as _support

# What a hand edit writes over a field the decision read.
_HAND_WRITTEN = "written by hand"




class ReadyRerouteRecoveryTest(unittest.TestCase, _PatchedWorkflowMixin, _support.ReadyTicks):
    """A reroute's checkpoint, refused, lost, or read back unreadable."""

    def test_a_refused_reroute_says_and_moves_nothing(self) -> None:
        # A human edits the record between the handler's claimed read and the
        # reroute's commit: refused, with nothing relabelled, said, or
        # written. The next tick decides afresh on what the record says now.
        gh = FakeGitHubClient()
        child = _support.ready_child(gh, edited=True)

        refused = self.edited_tick(gh, child, 1, user_content_hash=_HAND_WRITTEN)
        decided = self.ready_tick(gh, child)

        self.assertEqual(refused, (0, _support.UNMOVED))
        self.assertEqual(
            (decided, *_support.seen(gh)[:2]),
            (0, _support.REROUTED, _support.SAID_CHANGED),
        )
        self.assertEqual(self.recorded(gh, _support.KEY_BASELINE), _support.reading(child))

    def test_a_lost_reroute_finishes_from_its_marker(self) -> None:
        # The tick after a reroute whose answer was lost reads the marker back
        # -- the reset in place, its baseline reading as nothing changed -- and
        # finishes the relabel, saying the notice once with nothing written or
        # launched. The decomposing tick drops the marker before its
        # decomposer runs, and says nothing more.
        gh, child = self._lost_reroute()
        writes = gh.write_state_calls

        recovered = self.ready_tick(gh, child)
        finished = _support.seen(gh)

        self.assertEqual(
            (recovered, finished),
            (0, (_support.REROUTED, _support.SAID_CHANGED, writes)),
        )
        self.assertEqual(self.decomposing_tick(gh, child), 1)
        self.assertEqual(_support.notices(gh), _support.SAID_CHANGED)
        self.assertIsNone(self.recorded(gh, _support.KEY_REROUTE))

    def test_an_edit_behind_the_reroute_holds_it(self) -> None:
        # A human edits the record right behind the reroute's write: read back
        # as another record than the one landed, it licenses nothing, so
        # nothing is relabelled or said. The next tick finishes the reroute
        # from the marker that stands, saying its notice once.
        gh = FakeGitHubClient()
        child = _support.ready_child(gh, edited=True)
        edit = _support.InPlace(user_content_hash=_HAND_WRITTEN)

        held = self.interleaved_tick(gh, child, _support.LandsAfter(gh, "edit_pinned_state", 1, edit))
        finished = self.ready_tick(gh, child)

        self.assertEqual(held, (0, ((), _support.SAID_NOTHING, 1)))
        self.assertEqual(
            (finished, *_support.seen(gh)[:2]),
            (0, _support.REROUTED, _support.SAID_CHANGED),
        )
        self.assertEqual(self.reroute(gh), _support.CHANGED_REROUTE)

    def test_an_unreadable_record_holds_the_recovery(self) -> None:
        # The tick after a lost reroute cannot read the record, or reads one a
        # human edited into a version admission refuses: nothing is
        # relabelled, said, or written, and the marker stays for a later tick.
        for hold in ("unreadable", "refused"):
            with self.subTest(hold=hold):
                gh, child = self._lost_reroute()
                writes = gh.write_state_calls
                _held_record(gh, hold)

                with self.assertRaises((RuntimeError, RecordRefused)):
                    self.ready_tick(gh, child)

                self.assertEqual(_support.seen(gh), ((), _support.SAID_NOTHING, writes))
                self.assertIn(_support.KEY_REROUTE, gh.pinned_data(_support.CHILD))

    def test_a_relabel_back_says_the_notice_once(self) -> None:
        # The reroute landed, relabelled, and said its notice; an operator puts
        # the issue back on `ready` before the decomposing tick retires the
        # marker. The tick finishing the reroute again finds that notice by its
        # receipt and says nothing more, whatever the label had read.
        gh = FakeGitHubClient()
        child = _support.ready_child(gh, edited=True)
        self.ready_tick(gh, child)
        gh.set_workflow_label(child, LABEL_READY, guarded=False)

        again = self.ready_tick(gh, child)

        self.assertEqual((again, _support.notices(gh)), (0, _support.SAID_CHANGED))
        self.assertEqual(gh.workflow_label(child), _support.LABEL_DECOMPOSING)
        self.assertEqual(self.reroute(gh), _support.CHANGED_REROUTE)

    def test_a_failed_notice_is_retried_once(self) -> None:
        # A reroute notice whose post GitHub refuses is left to the decomposing
        # tick, which tries it once more ahead of retiring the marker; refused
        # there too, it is abandoned with the retirement. The decomposer runs
        # either way, and nothing tries the notice again after it.
        for refusals, said in ((1, _support.SAID_CHANGED), (2, _support.SAID_NOTHING)):
            with self.subTest(refusals=refusals):
                gh = FakeGitHubClient()
                child = _support.ready_child(gh, edited=True)
                refused = _RefusedNotices(gh, refusals)

                with patch.object(gh, "comment", refused):
                    self.ready_tick(gh, child)
                    self.assertEqual(self.decomposing_tick(gh, child), 1)

                self.assertEqual((refused.attempts, _support.notices(gh)), (2, said))
                self.assertIsNone(self.recorded(gh, _support.KEY_REROUTE))

    def _lost_reroute(self) -> tuple:
        """A child whose body was edited, its reroute landed with the answer lost: nothing said or relabelled yet."""
        gh = FakeGitHubClient()
        child = _support.ready_child(gh, edited=True)
        gh.pinned_failures.lost.add(_support.CHILD)
        lost = self.ready_tick(gh, child)
        gh.pinned_failures.lost.clear()
        self.assertEqual(
            (lost, *_support.seen(gh)[:2]),
            (0, (), _support.SAID_NOTHING),
        )
        self.assertEqual(self.reroute(gh), _support.CHANGED_REROUTE)
        return gh, child


class ReadyHandoffRecoveryTest(unittest.TestCase, _PatchedWorkflowMixin, _support.ReadyTicks):
    """An unchanged issue's handoff checkpoint, lost or refused, and the thread it asks about its pickup."""

    def test_a_lost_handoff_starts_once(self) -> None:
        # The handoff's write lands and its answer is lost: the pickup is out,
        # and nothing is relabelled or launched. The next tick reads its anchor
        # back, announces nothing more, and starts the implementer once.
        gh = FakeGitHubClient()
        child = _support.ready_child(gh)
        gh.pinned_failures.lost.add(_support.CHILD)
        lost = self.ready_tick(gh, child)
        gh.pinned_failures.lost.clear()
        told = _support.notices(gh)

        started = self.ready_tick(gh, child)

        self.assertEqual((lost, told), (0, _support.SAID_PICKUP))
        self.assertEqual((started, gh.label_history[0]), (1, _support.STARTED))
        self.assertEqual(_support.notices(gh), _support.SAID_PICKUP)

    def test_a_refused_preparation_announces_nothing(self) -> None:
        # A human edits the record between the handler's claimed read and the
        # handoff's preparation: refused before the pickup is posted, so
        # nothing is announced, written, relabelled, or launched. The next
        # tick hands the issue on, announcing it once.
        gh = FakeGitHubClient()
        child = _support.ready_child(gh)

        refused = self.edited_tick(gh, child, 1, observed_user_content_hash="")
        started = self.ready_tick(gh, child)

        self.assertEqual(refused, (0, _support.UNMOVED))
        self.assertEqual((started, _support.notices(gh)), (1, _support.SAID_PICKUP))

    def test_a_refused_handoff_anchors_its_pickup(self) -> None:
        # A human edits the record after the handoff was prepared and its
        # pickup posted: the write is refused, and nothing is relabelled or
        # launched. The next tick finds that pickup on the thread rather than
        # posting another, anchors it, and starts the implementer once.
        gh = FakeGitHubClient()
        child = _support.ready_child(gh)

        refused = self.edited_tick(gh, child, 2, observed_user_content_hash="")
        started = self.ready_tick(gh, child)

        self.assertEqual(refused, (0, ((), _support.SAID_PICKUP, 0)))
        self.assertEqual((started, _support.notices(gh)), (1, _support.SAID_PICKUP))
        self.assertEqual(
            self.recorded(gh, _support.KEY_PICKUP),
            next(posted.id for posted in child.comments if _support.PICKUP in posted.body),
        )

    def test_an_unreadable_thread_holds_the_decision(self) -> None:
        # The thread the decision compares, consumes, and finds its receipts on
        # cannot be read: nothing is announced, written, relabelled, or
        # launched.
        gh = FakeGitHubClient()
        child = _support.ready_child(gh)

        with patch.object(gh, "comments_after", side_effect=RuntimeError("github did not answer")):
            self.assertEqual(self.ready_tick(gh, child), 0)

        self.assertEqual(_support.seen(gh), _support.UNMOVED)


class _RefusedNotices:
    """The client's comment post, GitHub refusing the first `times` changed-requirements reroute notices."""

    def __init__(self, gh: FakeGitHubClient, times: int) -> None:
        self._post = gh.comment
        self._left = times
        self.attempts = 0

    def __call__(self, issue, body: str):
        """Post `body`, unless it is a reroute notice GitHub still refuses."""
        if _support.CHANGED_NOTICE in body:
            self.attempts += 1
            if self._left:
                self._left -= 1
                raise RuntimeError("GitHub refused the reroute notice")
        return self._post(issue, body)


def _held_record(gh: FakeGitHubClient, hold: str) -> None:
    """Leave the child's record unreadable, or edited by hand into a version admission refuses."""
    if hold == "unreadable":
        gh.pinned_failures.unreadable.add(_support.CHILD)
        return
    edited = dict(gh.pinned_data(_support.CHILD), schema_version=2)
    gh.seed_state(_support.CHILD, raw=True, **edited)


if __name__ == "__main__":
    unittest.main()
