# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""A handed request's developer launch that may have run is never made again: handed back, parked, or held.

Through `review_resume` on a `workflow:fixing` tick, over the launch the run
ledger cannot rule out (`review_handoffs.HandedLaunch.owed`). Where the
subject, the evidence the request claims, or the branch shows the developer's
work or a move, the verdict is dropped and the next tick's own road publishes
that work and hands the pull request back -- or, over loose work in the
checkout or a remote that moved past it, holds its bounce with a park of its
own -- nobody launched or charged either way. A branch nobody could read -- its
fetch refused, ahead of the park's notice or behind it, or its status or count
unread -- holds the verdict for a later tick. Anything else parks under
`agent_execution_failed` (`HandedLaunch.parks`) -- only behind the feedback
anchor the request was handed over with, put back where something cleared it,
and only where nothing moved behind the park's notice, the comment read behind
the branch so a verdict another road put in place there is kept -- and
`/orchestrator continue` replays that feedback to one fresh developer.
"""
from __future__ import annotations

import unittest
from dataclasses import replace
from functools import partial
from types import MappingProxyType
from unittest.mock import MagicMock, patch

from orchestrator.git.publication import probes as _publication_probes
from orchestrator.workflow.stages.validating import review_verdicts as _verdicts
from tests.workflow.fixtures import LABEL_FIXING, LABEL_VALIDATING, MEASURED_CANDIDATE_SHA
from tests.workflow.stages.validating import (
    disposed_verdict_test_support as _disposed,
    resumed_verdict_test_support as _resumed,
    review_handoff_test_support as _handoff,
    review_verdict_readings as _read,
    review_verdict_test_support as _world,
)

EXECUTION_FAILED = "agent_execution_failed"

CONTINUE = _resumed.CONTINUE

# The client request the park's notice goes out through.
COMMENT = "comment"

FIXING = (_world.ISSUE, LABEL_FIXING)

VALIDATING = (_world.ISSUE, LABEL_VALIDATING)

# The verdict a handed request left waiting, as `waiting` reads it.
_HANDED_REQUEST = "changes_requested"

_UNDELIVERABLE = "report_undeliverable"

_AHEAD_BEHIND = "branch_ahead_behind"

# The park the fixing stage's bounce holds over a branch it cannot place.
_UNPROVED = "stranded_unproved"

_HEAD_SHAS = "head_shas"

# A checkout standing on a commit of its own, which its pull request has not
# got once the branch counts it ahead.
_ON_THE_COMMIT = MappingProxyType({_HEAD_SHAS: (MEASURED_CANDIDATE_SHA,)})

# A checkout standing where its pull request's branch stands, every reading of
# it alike: proved to carry nothing unpublished, which is all a launch that may
# have run leaves where nothing shows its work.
_IN_SYNC = MappingProxyType({_HEAD_SHAS: (_world.HEAD,)})

# The run option the fetch of the pull request's branch answers through, and
# how it answers: landing, or refused.
_FETCH_RESULT = "authed_fetch_result"

_FETCHED = MagicMock(returncode=0, stdout="", stderr="")

_FETCH_REFUSED = MagicMock(returncode=1, stdout="", stderr="fatal: unable to access the remote")

# Each branch reading that may not have returned, as one fixing tick meets it:
# the fetch refused ahead of the park notice or behind it, a checkout status
# nobody could take, and a count git would not take.
_UNREAD_BRANCH = (
    ("a fetch refused ahead of the notice", MappingProxyType({_FETCH_RESULT: (_FETCH_REFUSED,)})),
    ("a fetch refused behind it", MappingProxyType({_FETCH_RESULT: (_FETCHED, _FETCH_REFUSED)})),
    ("an unread status", MappingProxyType({"tree_readable": False})),
    ("an uncounted divergence", MappingProxyType({"branch_divergence_readable": False})),
)

# The park of the launch as `parked` reads it: landed, its request dropped.
_PARKED = ((EXECUTION_FAILED, True), None, [EXECUTION_FAILED])

# No park standing, as `parked` reads its flags.
_UNPARKED = (None, False)

# Checkouts a launch that may have run left behind it: the pull request's
# branch moved onto a push, a commit of its own the branch counts ahead,
# loose work nothing has committed, and a remote that moved past it.
_PUSHED = MappingProxyType({_HEAD_SHAS: (_world.OTHER_HEAD,), "fetched_branch_tip": _world.OTHER_HEAD})

_AHEAD = MappingProxyType({**_ON_THE_COMMIT, _AHEAD_BEHIND: (1, 0)})

_LOOSE = MappingProxyType({**_IN_SYNC, "dirty_files": ("stray.py",)})

_BEHIND = MappingProxyType({**_IN_SYNC, _AHEAD_BEHIND: (0, 1)})

# What moves a handed request whose launch may have run on, the checkout the
# two fixing ticks behind it read, the park the second leaves, as `parked`
# reads it, and the head the pull request stands on: its push, a commit the
# pull request has not got, or a superseded claim, handed back; loose work in
# the checkout, or a remote that moved past it, held over by the bounce.
_MOVED_ON = (
    ("its push", _world.pushes, _PUSHED, _UNPARKED, _world.OTHER_HEAD),
    ("a stranded commit", None, _AHEAD, _UNPARKED, MEASURED_CANDIDATE_SHA),
    ("its claim superseded", _read.settles_evidence, _IN_SYNC, _UNPARKED, _world.HEAD),
    ("loose work", None, _LOOSE, (_UNPROVED, True), _world.HEAD),
    ("a moved remote", None, _BEHIND, (_UNPROVED, True), _world.HEAD),
)

# How a handed request's launch was left where nothing accounts for it, and
# what another write did to its pinned anchor meanwhile.
_UNACCOUNTED = (
    ("started", _resumed.STARTED, None),
    ("started, its anchor cleared", _resumed.STARTED, _resumed.clears_the_anchor),
    ("started under its identity", _resumed.SAME_IDENTITY, None),
    ("started under its identity, reserved ahead of the handoff", _resumed.RESERVED_AHEAD, None),
    ("an unreadable owed start", _resumed.UNREADABLE, None),
    ("an owed start spelled null", _resumed.NULL_START, None),
    ("started under no fingerprint", _resumed.NO_FINGERPRINT, None),
    ("started under a fingerprint no reader takes", _resumed.UNREAD_FINGERPRINT, None),
    ("under its identity, in a phase no reader takes", _resumed.UNREAD_PHASE, None),
    ("its run count unread and the other meter behind", _resumed.UNREAD_COUNT, None),
    ("reserved under a fingerprint no reader takes", _resumed.RESERVED_UNREAD, None),
)

# Where another write moves a handed request's pinned anchor ahead of the tick
# that parks its launch, and behind that park's notice, which holds the park.
_HELD_ANCHORS = (
    ("another comment pinned", "elsewhere", None),
    ("repointed behind the notice", None, "elsewhere"),
    ("cleared, then repointed behind the notice", "nowhere", "elsewhere"),
)


def _parks_over_its_report(case) -> None:
    """Another road's park over a report it cannot deliver, as the report reconciliation takes it."""
    state = case.github.read_pinned_state(case.issue)
    state.set("awaiting_human", True)
    state.set("park_reason", _UNDELIVERABLE)
    case.github.write_pinned_state(case.issue, state)


def _takes_the_request_over(case) -> None:
    """Another road finishing the request its own way: its verdict dropped, its anchor cleared, the issue parked."""
    _parks_over_its_report(case)
    state = case.github.read_pinned_state(case.issue)
    state.set(_world.RETURNED_VERDICT, None)
    state.set(_disposed.ANCHOR, None)
    case.github.write_pinned_state(case.issue, state)


def _commits_on_the_branch(_case) -> None:
    """A commit reaching the checkout's branch that its pull request has not got, as the next reading counts it."""
    _publication_probes._branch_divergence.return_value = _publication_probes._BranchDivergence(
        tip=_world.HEAD, ahead=1, behind=0, readable=True,
    )


def _fetches_while_replaced(case, *_asked, **_named):
    """The branch fetched, during which -- once the park notice is out -- another road replaces the waiting verdict.

    Its newer verdict, of a later round and never handed, is kept on `case`
    as `replacement`, as the comment spells it.
    """
    if CONTINUE in _disposed.last_notice(case) and not hasattr(case, "replacement"):
        state = case.github.read_pinned_state(case.issue)
        waited = _verdicts.read_returned_verdict(state)
        newer = replace(waited, round_n=waited.round_n + 1, handed=None, anchor=None)
        case.replacement = newer.recorded()
        state.set(_world.RETURNED_VERDICT, case.replacement)
        case.github.write_pinned_state(case.issue, state)
    return _FETCHED


class UnaccountedLaunchTest(_resumed.ResumedVerdictWorld, unittest.TestCase):
    """A launch that may have run is handed back where it left work, held over a branch nobody could read, and parked.

    Parked for a continue where the branch is proved to carry nothing, and
    nothing else says whether it ran.
    """

    def test_a_launch_nothing_accounts_for_parks(self) -> None:
        # Started, or read as a start the ledger cannot tell apart: nobody is
        # launched and nothing is spent. The request parks with its anchor --
        # written back from the verdict's own where something cleared it -- and
        # `/orchestrator continue` replays the reviewer's feedback to one fresh
        # developer, who hands the pull request back.
        for name, how, meanwhile in _UNACCOUNTED:
            with self.subTest(name):
                self.setUp()
                self._parks_and_replays(how, meanwhile)

    def test_a_moved_on_launch_is_left_to_the_stage(self) -> None:
        # Its developer pushed, or left a commit the pull request has not got,
        # loose work in the checkout, or a remote that moved past it, or the
        # evidence its request claims was superseded since: the verdict is
        # retired for good, with nobody launched, nothing spent, and nobody
        # parked, and the next tick's own road takes the branch as it stands
        # -- publishing that work and handing the pull request back, or
        # holding its bounce over a branch it cannot place, with a park of its
        # own -- still launching and charging nobody.
        for name, meanwhile, checkout, park, head in _MOVED_ON:
            with self.subTest(name):
                self.setUp()
                self.assertEqual(
                    self._hands_back(meanwhile, checkout),
                    (
                        (0, (_UNPARKED, None, [])),
                        (0, True),
                        [FIXING] if park[1] else [FIXING, VALIDATING],
                        park,
                        head,
                    ),
                )

    def test_an_unread_branch_holds_the_launch(self) -> None:
        # The fetch of the pull request's branch is refused, ahead of the park
        # notice or behind it, or the checkout's status or its count against
        # that branch will not read: a reading that did not return proves
        # nothing either way, so no park lands, nothing is launched or
        # charged, and the verdict waits, and the next tick, whose reading
        # lands, parks the launch for a continue.
        for name, unread in _UNREAD_BRANCH:
            with self.subTest(name):
                self.setUp()
                self._hands_over_started()
                charged = _read.spent(self)

                held = (
                    self.fixes(**{**_disposed.fixing(), **_IN_SYNC, **unread}).call_count,
                    self.parked(),
                )
                ran = self.fixes(**{**_disposed.fixing(), **_IN_SYNC})

                self.assertEqual(
                    (held, ran.call_count, self.parked(), _read.spent(self)),
                    ((0, (_UNPARKED, _HANDED_REQUEST, [])), 0, _PARKED, charged),
                )

    def test_a_replacement_during_the_probe_is_kept(self) -> None:
        # Another road records a newer verdict, never handed, while the branch
        # is read again behind the park notice: the comment is read behind
        # that reading, so no park lands over the replacement, which waits.
        self._hands_over_started()
        fetch = partial(_fetches_while_replaced, self)

        ran = self.fixes(**{**_disposed.fixing(), **_IN_SYNC, _FETCH_RESULT: fetch})

        self.assertEqual(
            (ran.call_count, self.parked()[0], self.pinned()[_world.RETURNED_VERDICT]),
            (0, _UNPARKED, self.replacement),
        )

    def _hands_over_started(self) -> None:
        """The tick handing a request over, its developer's launch started behind it: one that may have run."""
        self.hands_over_unstarted()
        _resumed.starts(self, _resumed.STARTED)

    def _hands_back(self, meanwhile, checkout: dict) -> tuple:
        """A started launch whose request `meanwhile` moves on, over `checkout`, across two fixing ticks.

        What the first left -- the developers it ran and the park -- and what
        the second did: the developers it ran, whether no run was charged and
        no usage folded across both -- a round the bounce's own publication
        spends aside -- every relabel, the park it left, and the head the pull
        request stands on.
        """
        self.hands_over_unstarted(_resumed.DECLARED_REQUEST)
        _resumed.starts(self, _resumed.STARTED)
        if meanwhile is not None:
            meanwhile(self)
        charged = _read.spent(self)[:-1]
        ticks = {**_disposed.fixing(), **checkout}
        retired = (self.fixes(**ticks).call_count, self.parked())
        ran = self.fixes(**ticks)
        return (
            retired,
            (ran.call_count, _read.spent(self)[:-1] == charged),
            self.github.label_history,
            self.parked()[0],
            self.pull_request.head.sha,
        )

    def _parks_and_replays(self, how: str, meanwhile) -> None:
        """Leave the handed launch as `how` says and the anchor to `meanwhile`, then park it and answer the park."""
        self.hands_over_unstarted()
        _resumed.starts(self, how)
        spent = (_read.spent(self), self.pinned()[_disposed.ANCHOR])
        if meanwhile is not None:
            meanwhile(self)

        parked = (
            self.fixes(**{**_disposed.fixing(), **_IN_SYNC}).call_count,
            (_read.spent(self), self.pinned()[_disposed.ANCHOR]),
            self.parked(),
            CONTINUE in _disposed.last_notice(self),
            tuple(self.github.label_history),
        )
        self.asks_to_continue()
        replayed = self.fixes(**_disposed.fixing())

        self.assertEqual(
            (
                parked,
                replayed.call_count,
                _world.REQUESTED in replayed.call_args.args[1],
                self.github.label_history[-1],
            ),
            ((0, spent, _PARKED, True, (FIXING,)), 1, True, VALIDATING),
        )


class BehindTheNoticeTest(_resumed.ResumedVerdictWorld, unittest.TestCase):
    """The park notice is a request of its own: what moves behind it lands no park; a cleared anchor is put back."""

    def test_a_move_behind_the_notice_parks_nobody(self) -> None:
        # The notice is a request of its own. A push or a later evidence
        # revision landing during it drops the verdict for the stage's own
        # road, and a pull request that stops answering holds it: no park
        # either way, the notice kept as the orchestrator's own.
        for name, road, left in (
            ("a push", _world.pushes, None),
            ("later evidence", _read.settles_evidence, None),
            ("an unread thread", _world.stops_answering, _HANDED_REQUEST),
        ):
            with self.subTest(name):
                self.setUp()
                self.hands_over_unstarted(_resumed.DECLARED_REQUEST)
                _resumed.starts(self, _resumed.STARTED)
                behind = _world.AnotherRoadBehind(self, COMMENT, _resumed.asks_for_a_continue, road)

                with patch.object(self.github, COMMENT, behind):
                    ran = self.fixes(**{**_disposed.fixing(), **_IN_SYNC})

                self.assertEqual(
                    (ran.call_count, self.parked(), _disposed.last_notice(self).count(CONTINUE)),
                    (0, (_UNPARKED, left, []), 1),
                )

    def test_a_moved_anchor_holds_the_park(self) -> None:
        # Another comment pinned as the anchor holds the launch with nothing
        # posted, and one pointed there behind the park notice -- over an
        # anchor already cleared, too -- lands no park and is kept as that road
        # wrote it: either way the request waits, since no continue could
        # replay its feedback.
        for name, ahead, behind in _HELD_ANCHORS:
            with self.subTest(name):
                self.setUp()
                anchor = self._parks_under_an_anchor(ahead, behind)

                self.assertEqual(
                    (
                        self.parked(),
                        self.waiting(),
                        _disposed.last_notice(self).count(CONTINUE),
                        self.pinned().get(_disposed.ANCHOR) in {None, anchor},
                    ),
                    ((_UNPARKED, _HANDED_REQUEST, []), _HANDED_REQUEST, int(behind is not None), False),
                )

    def test_a_cleared_anchor_is_put_back(self) -> None:
        # Cleared behind the park notice, the anchor is written back by the
        # park's own write, so the park lands and its continue replays the
        # reviewer's feedback to one fresh developer.
        anchor = self._parks_under_an_anchor(None, "nowhere")
        parked = (self.parked(), self.pinned()[_disposed.ANCHOR])
        self.asks_to_continue()

        replayed = self.fixes(**_disposed.fixing())

        self.assertEqual(
            (parked, replayed.call_count, _world.REQUESTED in replayed.call_args.args[1]),
            ((_PARKED, anchor), 1, True),
        )

    def test_another_park_behind_the_notice_is_kept(self) -> None:
        # Another road parks the issue while the notice is posted -- over a
        # report it cannot deliver -- and that park is its own to answer: no
        # park lands over it, its reason is kept, and the request waits.
        self.hands_over_unstarted()
        _resumed.starts(self, _resumed.STARTED)
        road = _world.AnotherRoadBehind(self, COMMENT, _resumed.asks_for_a_continue, _parks_over_its_report)

        with patch.object(self.github, COMMENT, road):
            ran = self.fixes(**{**_disposed.fixing(), **_IN_SYNC})

        self.assertEqual(
            (ran.call_count, self.parked()),
            (0, ((_UNDELIVERABLE, True), _HANDED_REQUEST, [])),
        )

    def test_a_verdict_dropped_behind_the_notice(self) -> None:
        # Another road drops the verdict, clears its anchor, and parks the
        # issue while the notice is posted: no park lands, and the anchor is
        # left cleared as that road wrote it, not put back beside its park.
        self.hands_over_unstarted()
        _resumed.starts(self, _resumed.STARTED)
        road = _world.AnotherRoadBehind(self, COMMENT, _resumed.asks_for_a_continue, _takes_the_request_over)

        with patch.object(self.github, COMMENT, road):
            ran = self.fixes(**{**_disposed.fixing(), **_IN_SYNC})

        self.assertEqual(
            (ran.call_count, self.parked(), self.pinned().get(_disposed.ANCHOR)),
            (0, ((_UNDELIVERABLE, True), None, []), None),
        )

    def test_a_commit_behind_the_notice_is_published(self) -> None:
        # The checkout carried nothing unpublished as the park was measured,
        # and a commit reaches the branch while its notice is posted: that is
        # the developer's work, so no park lands and the verdict is dropped,
        # and the next tick's bounce publishes the commit and hands the pull
        # request back.
        self.hands_over_unstarted()
        _resumed.starts(self, _resumed.STARTED)
        road = _world.AnotherRoadBehind(self, COMMENT, _resumed.asks_for_a_continue, _commits_on_the_branch)
        with patch.object(self.github, COMMENT, road):
            self.fixes(**{**_disposed.fixing(), **_IN_SYNC})
        dropped = self.parked()

        ahead = {**_disposed.fixing(), **_ON_THE_COMMIT, _AHEAD_BEHIND: (1, 0)}
        published = self.fixes(**ahead)

        self.assertEqual(
            (dropped, published.call_count, self.github.label_history[-1], self.pull_request.head.sha),
            ((_UNPARKED, None, []), 0, VALIDATING, MEASURED_CANDIDATE_SHA),
        )

    def _parks_under_an_anchor(self, ahead: str | None, behind: str | None) -> int:
        """A started launch parked with its anchor moved `ahead` of the tick and `behind` its notice; the anchor it had.

        Each is where `review_handoff_test_support.moves_the_anchor` moves it
        to, or None for no move.
        """
        self.hands_over_unstarted()
        _resumed.starts(self, _resumed.STARTED)
        anchor = self.pinned()[_disposed.ANCHOR]
        if ahead is not None:
            _handoff.moves_the_anchor(self, to=ahead)
        road = _world.AnotherRoadBehind(
            self, COMMENT, _resumed.asks_for_a_continue, partial(_handoff.moves_the_anchor, to=behind),
            times=int(behind is not None),
        )
        with patch.object(self.github, COMMENT, road):
            self.fixes(**{**_disposed.fixing(), **_IN_SYNC})
        return anchor


if __name__ == "__main__":
    unittest.main()
