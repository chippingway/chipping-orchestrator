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
`agent_execution_failed` (`review_launch_park.parks`) -- only behind the feedback
anchor the request was handed over with, put back where something cleared it,
and only where nothing moved behind the park's notice, the comment read behind
the branch so a verdict another road put in place there is kept, and its run
ledger still says the launch may have started -- and
`/orchestrator continue` replays that feedback to one fresh developer: a post
made before findings were formatted, its declaration raw, is replayed with its
findings concise and left on the pull request as it was posted.

The park (`review_launch_park.parks`), the write-back of a cleared anchor
ahead of an owed launch, and the drop of a request that moved on are each a
guarded commit: prepared before the park's notice, so a comment another road
filled posts nothing, and refused where another road writes right ahead of
them -- nothing written over that road's write, parked, reported, or
launched. The drop of a launch that may have run is decided on its run ledger
too, so a start written away ahead of it keeps the request for the developer
it owes. One GitHub took and lost the response to is finished once by the
next tick: no second notice, park, developer, or charge.
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
    raw_feedback_test_support as _raw,
    resumed_verdict_test_support as _resumed,
    review_handoff_test_support as _handoff,
    review_park_test_support as _parked,
    review_verdict_readings as _read,
    review_verdict_test_support as _world,
    review_write_test_support as _roads,
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

# Each request a tick persisted and posted before findings were formatted,
# and the findings a continue of its launch's park quotes of that post: a
# passing run's, the reviewer's words alone, or a failed run's, the failed
# check kept as their diagnostic.
_POSTED_RAW = (
    ("a passing run", _world.PASSED_REQUEST, _world.REQUESTED),
    ("a failed run", _world.FAILED_REQUEST, _world.CONCISE_FAILURE),
)

# Where another write points a handed request's pinned anchor: at another
# comment than the post the request was handed over with.
_ELSEWHERE = "elsewhere"

# How each guarded-commit case names another road's write.
_ANOTHER_VERDICT = "another round's verdict"

_A_PARK = "a park recorded"

_UNPARSED = "an unparsed comment"

# Where another write moves a handed request's pinned anchor ahead of the tick
# that parks its launch, and behind that park's notice, which holds the park.
_HELD_ANCHORS = (
    ("another comment pinned", _ELSEWHERE, None),
    ("repointed behind the notice", None, _ELSEWHERE),
    ("cleared, then repointed behind the notice", "nowhere", _ELSEWHERE),
)


def _takes_the_request_over(case) -> None:
    """Another road finishing the request its own way: its verdict dropped, its anchor cleared, the issue parked."""
    _disposed.parks_over_its_report(case)
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


# Another road's newer verdict, of a later round and never handed, in the
# place of a handed request; and its feedback anchor pointed at another comment.
_REPLACES = _parked.replaces_the_verdict

_REPOINTS_THE_ANCHOR = partial(_handoff.moves_the_anchor, to=_ELSEWHERE)

# The two requests of a park another road's write can go right ahead of: its
# preparation, which the notice waits on, and its commit, behind the notice.
_PREPARE = "prepare"

_COMMIT = "commit"

# Another road's write right ahead of the park of a launch that may have run,
# behind the last reading it was decided on, and which of its two requests it
# goes ahead of: a verdict put in the request's place, its anchor pointed at
# another comment, a run charged, a park of its own recorded, and the comment
# itself unparsed or replaced. Each refuses the park.
_AHEAD_OF_THE_PARK = (
    (_ANOTHER_VERDICT, _REPLACES, _PREPARE),
    (_A_PARK, _disposed.parks_over_its_report, _PREPARE),
    (_UNPARSED, _roads.unparses, _PREPARE),
    (_ANOTHER_VERDICT, _REPLACES, _COMMIT),
    ("the anchor repointed", _REPOINTS_THE_ANCHOR, _COMMIT),
    ("a run charged", partial(_handoff.charges_a_run, owed=False), _COMMIT),
    (_A_PARK, _disposed.parks_over_its_report, _COMMIT),
    (_UNPARSED, _roads.unparses, _COMMIT),
    ("a replaced comment", _roads.repins, _COMMIT),
)

# Another road writing a handed launch's start away, its charge left standing
# unstarted under the launch's own fingerprint: the launch owed again.
_UNSTARTS = _roads.Writes({"agent_run_owed_started": ..., "agent_run_reservation": "reserved"})

# The subject's report re-read a validating recovery makes ahead of the comment
# a drop is read afresh from.
_REREAD = "reread_report_location"

# The two ticks a handed request's launch is recovered on.
_FIXES = _resumed.ResumedVerdictWorld.fixes

_VALIDATES = _resumed.ResumedVerdictWorld.validates

# Where another road writes a launch that may have run back to owed that way,
# and the tick that meets it: a fixing tick, behind the notice of the park it
# takes; or a validating tick a relabel from outside brought the request back
# to, which drops it as a launch that may have run -- behind the subject's
# report re-read, ahead of the comment the drop is read afresh from, or right
# ahead of the drop's commit.
_UNSTARTING = (
    (
        "behind the park's notice",
        _FIXES,
        lambda case: _world.AnotherRoadBehind(case, COMMENT, _resumed.asks_for_a_continue, _UNSTARTS).patched(),
    ),
    (
        "behind the subject's re-read",
        _VALIDATES,
        lambda case: _world.AnotherRoadBehind(case, _REREAD, bool, _UNSTARTS).patched(),
    ),
    ("ahead of the drop's commit", _VALIDATES, lambda case: _roads.AnotherRoadAhead(case, bool, _UNSTARTS).patched()),
)

# Another road's write right ahead of the commit dropping a request that moved
# on, and the verdict that leaves waiting: one of its own in the request's
# place refuses the drop and waits; a response GitHub lost drops it once.
_AHEAD_OF_THE_DROP = (
    (_ANOTHER_VERDICT, _REPLACES, _HANDED_REQUEST),
    ("a lost response", _roads.loses_the_responses, None),
)

# Another road's write around the commit writing back an owed launch's
# cleared anchor, and whether it goes right ahead of that commit: the anchor
# pointed at another comment, a verdict put in the request's place, a park of
# its own recorded, or the comment unparsed, there; or a park recorded behind
# the subject's re-read, which the reading the write-back is decided over
# carries. Each refuses the write-back.
_AROUND_THE_WRITE_BACK = (
    ("the anchor repointed", _REPOINTS_THE_ANCHOR, True),
    (_ANOTHER_VERDICT, _REPLACES, True),
    (_A_PARK, _disposed.parks_over_its_report, True),
    (_UNPARSED, _roads.unparses, True),
    ("a park behind the subject's re-read", _disposed.parks_over_its_report, False),
)


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
        road = _world.AnotherRoadBehind(self, COMMENT, _resumed.asks_for_a_continue, _disposed.parks_over_its_report)

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


class GuardedRecoveryTest(_resumed.ResumedVerdictWorld, unittest.TestCase):
    """A launch's park, an anchor's write-back, and a drop land through guarded commits, each finished once.

    Every case's road goes ahead of the first guarded commit -- or the first
    preparation -- the fixing tick makes, which on these ticks is the
    recovery's own.
    """

    def test_a_write_ahead_of_the_park_lands_none(self) -> None:
        # Another road writes right ahead of the park of a launch that may
        # have run. Ahead of its preparation, which its notice waits on,
        # nothing is posted; ahead of its commit, the park is refused behind
        # its one notice. Either way the comment stays exactly as that road
        # left it, and nothing is reported or launched.
        for name, road, request in _AHEAD_OF_THE_PARK:
            with self.subTest(name, request=request):
                self.setUp()
                self.hands_over_unstarted()
                _resumed.starts(self, how=_resumed.STARTED)
                ahead = _roads.AnotherRoadAhead(self, bool, partial(_roads.leaves, road), request=request)

                with ahead.patched():
                    ran = self.fixes(**{**_disposed.fixing(), **_IN_SYNC})

                self.assertEqual(
                    (
                        ran.call_count,
                        self.pinned(),
                        _parked.reported(self),
                        _disposed.last_notice(self).count(CONTINUE),
                    ),
                    (0, self.left_behind, [], int(request == _COMMIT)),
                )

    def test_a_lost_park_is_answered_once(self) -> None:
        # GitHub takes the park's commit and loses its response, so its event
        # never goes out and nothing is launched. The next tick finds the park
        # standing, posts no second notice and launches nobody, and
        # `/orchestrator continue` replays the feedback to one fresh
        # developer, who hands the pull request back.
        self.hands_over_unstarted()
        _resumed.starts(self, how=_resumed.STARTED)
        with _roads.AnotherRoadAhead(self, bool, _roads.loses_the_responses).patched():
            parked = self.fixes(**{**_disposed.fixing(), **_IN_SYNC}).call_count
        self.github.pinned_failures.lost.discard(_world.ISSUE)
        held = (parked, self.parked(), len(self.github.posted_comments))

        again = (
            self.fixes(**{**_disposed.fixing(), **_IN_SYNC}).call_count,
            len(self.github.posted_comments),
        )
        self.asks_to_continue()
        replayed = self.fixes(**_disposed.fixing())

        self.assertEqual(
            (held, again, replayed.call_count, self.github.label_history[-1]),
            (
                (0, ((EXECUTION_FAILED, True), None, []), held[2]),
                (0, held[2]),
                1,
                VALIDATING,
            ),
        )

    def test_a_lost_start_is_launched_once(self) -> None:
        # The run circuit's write starting the developer a handed request owes
        # lands and its response is lost, so no developer is spawned behind a
        # start nobody confirmed. The next tick reads that start, launches it
        # never again, and parks it, and `/orchestrator continue` replays the
        # feedback to one fresh developer: one launch in all.
        loses = _handoff.RefusesTheStart(self.github.write_pinned_state, lands=True)
        with patch.object(self.github, "write_pinned_state", loses):
            returned = self.returns(_resumed.UNDECLARED_REQUEST, **_disposed.fixing())
        parked = self.fixes(**{**_disposed.fixing(), **_IN_SYNC}).call_count
        held = (returned[_world.RUN_AGENT].call_count, parked, self.parked())
        self.asks_to_continue()

        replayed = self.fixes(**_disposed.fixing())

        self.assertEqual(
            (held, replayed.call_count),
            ((0, 0, _PARKED), 1),
        )

    def test_a_write_around_the_write_back(self) -> None:
        # The anchor of a handed request whose launch is still owed was
        # cleared, and another road writes right ahead of the commit writing it
        # back, or parks the issue behind the subject's re-read that write-back
        # is decided behind: the write-back is refused or never made, the
        # comment -- that road's park included -- stays exactly as that road
        # left it, and nothing is relabelled or launched.
        for name, road, ahead in _AROUND_THE_WRITE_BACK:
            with self.subTest(name):
                self.setUp()
                self.hands_over_unstarted()
                _resumed.clears_the_anchor(self)
                around = (
                    _roads.AnotherRoadAhead(self, bool, partial(_roads.leaves, road)) if ahead
                    else _world.AnotherRoadBehind(self, _REREAD, bool, partial(_roads.leaves, road))
                )

                with around.patched():
                    ran = self.fixes(**_disposed.fixing())

                self.assertEqual(
                    (ran.call_count, (self.pinned(), self.github.label_history)),
                    (0, (self.left_behind, [FIXING])),
                )

    def test_a_lost_write_back_launches_once(self) -> None:
        # GitHub takes the commit writing a cleared anchor back and loses its
        # response, so nothing is launched behind it. The next tick finds the
        # anchor written, writes nothing over it, and launches the one
        # developer the request owes, honoring the charge its handoff
        # reserved: no second post, and no second run charged.
        self.hands_over_unstarted()
        _resumed.clears_the_anchor(self)
        anchor = self.pinned()[_world.RETURNED_VERDICT]["anchor"]
        with _roads.AnotherRoadAhead(self, bool, _roads.loses_the_responses).patched():
            lost = self.fixes(**_disposed.fixing()).call_count
        self.github.pinned_failures.lost.discard(_world.ISSUE)
        written = self.pinned()

        ran = self.fixes(**_disposed.fixing()).call_count

        pinned = self.pinned()
        self.assertEqual(
            (
                lost,
                written[_disposed.ANCHOR],
                ran,
                len(self.feedback_posts()),
                pinned[_world.AGENT_RUNS_USED] - written[_world.AGENT_RUNS_USED],
                self.waiting(),
            ),
            (0, anchor, 1, 1, 0, None),
        )

    def test_a_drop_is_refused_or_settled_once(self) -> None:
        # A launch that may have run pushed, so its request is dropped for the
        # stage's own road. Another road putting its own verdict in that
        # request's place right ahead of the drop refuses it, and the comment
        # stays exactly as that road left it, the newer verdict waiting;
        # GitHub taking the drop and losing its response drops it once. The
        # next tick launches nobody either way.
        for name, road, waits in _AHEAD_OF_THE_DROP:
            with self.subTest(name):
                self.setUp()
                self.hands_over_unstarted()
                _resumed.starts(self, how=_resumed.STARTED)
                _world.pushes(self)
                with _roads.AnotherRoadAhead(self, bool, partial(_roads.leaves, road)).patched():
                    dropped = self.fixes(**_disposed.fixing()).call_count
                self.github.pinned_failures.lost.discard(_world.ISSUE)
                left = (dropped, self.pinned() == self.left_behind, self.waiting())

                self.assertEqual(
                    (left, self.fixes(**{**_disposed.fixing(), **_PUSHED}).call_count),
                    ((0, waits is not None, waits), 0),
                )

    def test_a_launch_owed_again_stays_owed(self) -> None:
        # Another road writes the launch's start away after the reading the
        # recovery decided on -- while the park's notice is posted, or around
        # the drop a validating tick makes of a request a relabel from outside
        # brought back -- leaving its charge standing unstarted under the
        # launch's own fingerprint: the run ledger read behind it says the
        # launch is owed again, so no park lands and nothing is dropped, and
        # the request waits handed beside that charge. The next tick launches
        # its one developer, honoring the charge rather than charging a second
        # run or a fresh reviewer.
        for name, tick, unstarting in _UNSTARTING:
            with self.subTest(name):
                self.setUp()
                self.hands_over_unstarted()
                _resumed.starts(self, how=_resumed.STARTED)
                if tick is _VALIDATES:
                    self.github.set_workflow_label(self.issue, LABEL_VALIDATING)
                with unstarting(self):
                    held = tick(self, **{**_disposed.fixing(), **_IN_SYNC}).call_count
                parked = (held, self.parked(), self.pinned()[_world.AGENT_RUNS_USED])

                self.assertEqual(
                    (
                        parked,
                        tick(self, **_disposed.fixing()).call_count,
                        self.pinned()[_world.AGENT_RUNS_USED],
                        self.waiting(),
                    ),
                    (
                        (0, (_UNPARKED, _HANDED_REQUEST, []), parked[2]),
                        1,
                        parked[2],
                        None,
                    ),
                )


class RawReplayTest(_resumed.ResumedVerdictWorld, unittest.TestCase):
    """A launch handed over behind a post made before findings were formatted parks; a continue replays it concise."""

    def test_a_continue_replays_a_raw_post_concise(self) -> None:
        # A request persisted and posted with its declaration raw, its
        # developer's launch started: the launch parks, and `/orchestrator
        # continue` hands one fresh developer the anchored post's findings
        # formatted -- the declaration set aside, a failed check kept as its
        # diagnostic -- while the post stays on the pull request as posted.
        for name, reply, concise in _POSTED_RAW:
            with self.subTest(name):
                self.setUp()
                parked = self._parks_raw(reply)
                self.asks_to_continue()

                replayed = self.fixes(**_disposed.fixing())

                self.assertEqual(
                    (
                        parked,
                        replayed.call_count,
                        _raw.posted(self),
                        _raw.quotes(replayed.call_args.args[1], concise),
                        self.github.label_history[-1],
                    ),
                    ((0, _PARKED), 1, (_raw.as_persisted(reply),), (True, False), VALIDATING),
                )

    def _parks_raw(self, reply: str) -> tuple:
        """Hand over the request `reply` asks for as a tick before formatting did, start its launch, and park it.

        What the fixing tick that parks it left: the developers it ran, and
        the park as `parked` reads it.
        """
        _raw.leaves_raw(self, _resumed.ResumedVerdictWorld.hands_over_unstarted, reply)
        _resumed.starts(self, how=_resumed.STARTED)
        ran = self.fixes(**{**_disposed.fixing(), **_IN_SYNC})
        return ran.call_count, self.parked()

if __name__ == "__main__":
    unittest.main()
