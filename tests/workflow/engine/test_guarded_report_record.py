# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""A finished run's record lands over the pinned comment as it stands now.

The record is a guarded commit decided on the comment the tick read. Another
road may write the comment in between: what it wrote outside the record's own
fields survives, a record or field the record was decided on or writes moving
under it refuses it with nothing written, and the room every later write needs
is measured again on the comment the fresh reading finds.
"""

from __future__ import annotations

import unittest
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any

from orchestrator.github.pinned_state import MAX_PINNED_BODY, PinnedState, pinned_state_body
from orchestrator.workflow.engine import (
    pinned_commit as _pinned_commit,
    report_delivery as _delivery,
    report_delivery_state as _delivery_state,
    report_record_values as _record_values,
    report_records as _records,
)
from orchestrator.workflow.state import WorkflowLabel
from tests.workflow.engine import (
    report_commit_test_support as commit_support,
    report_delivery_test_support as delivery_support,
    report_record_test_support as support,
)
from tests.workflow.fixtures import _agent

# Fields other roads write that a report's record never decides on: another
# domain's evidence and verdict, a usage total, a feedback watermark, the
# ledger of this orchestrator's comments, and the session a run left.
_EVIDENCE = "verification_evidence_current"

_VERDICT = "review_returned_verdict"

_TOKENS = "issue_total_tokens"

_WATERMARK = "pr_last_comment_id"

_LEDGER = "orchestrator_comment_ids"

_SESSION = "dev_session_id"

# Evidence another road settles behind a write the tick could not confirm.
_EVIDENCE_SINCE = MappingProxyType({_EVIDENCE: {"revision": 4}})

# Room past the report for every write a record reserves, and then some.
_ROOMY = 20000

# What the tick reading the comment finds: the reply to an undeliverable-report
# park, which the report it brings retires.
_PARKED = MappingProxyType({
    delivery_support.BASELINE: support.REQUIREMENTS,
    delivery_support.AWAITING_HUMAN: True,
    delivery_support.PARK_REASON: _delivery.UNDELIVERABLE_REPORT,
    _delivery.OWED_REPORT: True,
})

# What the tick read of the fields two roads both move, what it staged on them
# since -- a run of its own folded, a shorter reading, a post, a session -- and
# what another road wrote meanwhile: evidence and a verdict of its own, a run
# folded, a further reading, a post. Kept, the totals add up, the watermark
# keeps the further reading, the ledger both posts, and every field one road
# alone wrote is that road's.
_TICK_READ = MappingProxyType({_TOKENS: 100, _WATERMARK: 40, _LEDGER: [5]})

_TICK_STAGED = MappingProxyType({
    _TOKENS: 130, _WATERMARK: 50, _LEDGER: [5, 7], _SESSION: "sess-tick",
})

_ANOTHER_ROAD = MappingProxyType({
    _EVIDENCE: {"revision": 3}, _VERDICT: {"round": 2},
    _TOKENS: 150, _WATERMARK: 60, _LEDGER: [5, 9],
})

_KEPT = MappingProxyType({
    _EVIDENCE: {"revision": 3}, _VERDICT: {"round": 2},
    _TOKENS: 180, _WATERMARK: 60, _SESSION: "sess-tick",
})

# The run a tick folds in itself.
_TICK_FOLD = 30

# What a park the tick takes writes beside its notice: its flags, the debt, and
# the work no report describes. And what posting that notice can write as
# well, at the widest: a ledger entry and the issue-thread watermark.
_PARK_FLAGS = MappingProxyType({
    delivery_support.AWAITING_HUMAN: True,
    delivery_support.PARK_REASON: _delivery.UNDELIVERABLE_REPORT,
    _delivery.OWED_REPORT: True,
    _delivery.UNREPORTED_WORK: True,
})

_NOTICE_WRITES = MappingProxyType({
    _LEDGER: [_record_values.MAX_RECORDED_NUMBER],
    "last_action_comment_id": _record_values.MAX_RECORDED_NUMBER,
})

# The widest id a ledger records, which another road may already have recorded
# by the time a park's notice is prepared: the id a reservation starts from.
_WIDEST = _record_values.MAX_RECORDED_NUMBER

# Each comment a park is prepared over, at the brim: what renders beside its
# flags to fill it exactly, the ledger another road recorded since the tick read
# it (None for none), and whether the notice goes out and the park lands. Room
# for the flags alone, then for the notice's writes too; then a ledger already
# holding the widest id, with room beside it for no further entry and for one.
_BRIMS = (
    (MappingProxyType({}), None, False),
    (_NOTICE_WRITES, None, True),
    (_NOTICE_WRITES, [_WIDEST], False),
    (MappingProxyType({**_NOTICE_WRITES, _LEDGER: [_WIDEST, _WIDEST - 1]}), [_WIDEST], True),
)

# A report past its ceiling, which its own reading refuses whatever room the
# comment has, so the park behind it is what the comment's room decides.
_PAST_THE_CEILING = delivery_support.FILLER * (_record_values.MAX_REPORT_TEXT + 1)

# The comment another road filled since the tick read it, by the room it left,
# and what the park then says could not be written: the record itself, and the
# binding it reserves.
_FILLED_SINCE = (
    (delivery_support.CROWDED_FOR_PARK, "the record of it would leave the pinned comment"),
    (
        delivery_support.CROWDED_FOR_RESERVATION,
        "the publication transaction it becomes once its code reaches a pull request",
    ),
)

# And the other way round: the room the tick read the comment with, too little
# for the record or the binding it reserves, given back since by another road.
_FREED_SINCE = (delivery_support.CROWDED_FOR_PARK, delivery_support.CROWDED_FOR_RESERVATION)

# Each room the tick read the comment with, the room another road left it since,
# and what the park then says -- None where the record lands.
_ROOM_SINCE = (
    *((_ROOMY, slack, said) for slack, said in _FILLED_SINCE),
    *((slack, _ROOMY, None) for slack in _FREED_SINCE),
)

# How the comment moves under a tick that has read it, each of which a record
# minted over that reading may not land on: a report record or the baseline it
# was minted from moved, a field the record writes moved another way, and a
# comment no longer the one the tick read -- replaced, unparseable, unreadable.
_MOVES_UNDER_IT = (
    ("a newer delivery", lambda github, issue, _state: commit_support.another_road(
        github, issue, **{_records.DELIVERED_REPORT: delivery_support.delivered_object(
            delivery_support.REDELIVERED,
        )},
    )),
    ("an outstanding transaction", lambda github, issue, _state: commit_support.another_road(
        github, issue, **{
            _records.PENDING_REPORT: delivery_support.outstanding_comment()[_records.PENDING_REPORT],
        },
    )),
    ("a settled report", lambda github, issue, _state: commit_support.another_road(
        github, issue, **{_records.CURRENT_REPORT: "settled since"},
    )),
    ("the requirements baseline", lambda github, issue, _state: commit_support.another_road(
        github, issue, **{delivery_support.BASELINE: "b" * len(support.REQUIREMENTS)},
    )),
    ("the park it retires", lambda github, issue, _state: commit_support.another_road(
        github, issue, **{delivery_support.PARK_REASON: "agent_timeout"},
    )),
    ("a usage total another road made a flag", lambda github, issue, state: (
        state.set(_TOKENS, _TICK_READ[_TOKENS] + _TICK_FOLD),
        commit_support.another_road(github, issue, **{_TOKENS: True}),
    )),
    ("a replaced comment", lambda github, issue, _state: github.seed_state(
        issue, **github.pinned_data(issue.number),
    )),
    ("an unparseable comment", lambda github, issue, state: github._pinned.update({
        issue.number: PinnedState(comment_id=state.comment_id, parsed=False),
    })),
    ("an unreadable comment", lambda github, issue, _state: github.pinned_failures.unreadable.add(
        issue.number,
    )),
)


@dataclass(frozen=True)
class _Tick:
    """An issue, and the state a tick read its pinned comment into."""

    github: Any
    issue: Any
    state: PinnedState

    @classmethod
    def over(cls, state: PinnedState) -> _Tick:
        """A tick that read `state` off a fresh issue's pinned comment."""
        return cls(*commit_support.pinned(delivery_support.seeded_issue(), state), state)

    def pinned(self) -> dict:
        """What the pinned comment carries now."""
        return self.github.pinned_data(self.issue.number)

    def crowded_since(self, slack: int) -> str:
        """Leave the comment as another road crowds it, `slack` past the report; what it was crowded with."""
        crowding = delivery_support.crowded_comment(slack, baselined=True).get(delivery_support.CROWDING)
        commit_support.another_road(self.github, self.issue, **{delivery_support.CROWDING: crowding})
        return crowding

    def notices_saying(self, said: str | None) -> list[bool]:
        """Whether each comment posted on the issue says `said`."""
        return [said in posted for _issue, posted in self.github.posted_comments]

    def records(self, report: str = delivery_support.DELIVERED.report) -> bool:
        """Record `report` as a finished implementation run wrote it; whether the tick ended."""
        return _delivery.recording_stops_the_tick(
            self.github, self.issue, self.state,
            _agent(last_message=delivery_support.ready(report)),
            WorkflowLabel.IMPLEMENTING,
        )


class GuardedRecordingTest(unittest.TestCase):
    """A record lands over the comment as it stands, decided on what the tick read.

    Another road may write the comment between the tick's reading and its
    record. What it wrote outside the record's own fields survives the record;
    what the record was decided on, or writes itself, moving under it refuses
    it with nothing written and nothing published; and the room every later
    write needs is measured again on the comment the fresh reading finds.
    """

    def test_another_road_s_fields_survive_the_record(self) -> None:
        # Another road settles evidence, returns a verdict, folds a run, reads
        # further, and posts; the tick folds its own run, reads less far,
        # posts, and starts a session. The record lands beside all of it: the
        # totals add up, the watermark keeps the further reading, the ledger
        # both posts, and the tick's own staging rides the write.
        tick = self._tick(**_TICK_READ)
        tick.state.data.update(_TICK_STAGED)
        commit_support.another_road(tick.github, tick.issue, **_ANOTHER_ROAD)

        self.assertFalse(tick.records())

        pinned = tick.pinned()
        self.assertEqual(
            (
                {field: pinned[field] for field in _KEPT},
                sorted(pinned[_LEDGER]),
                pinned[delivery_support.PARK_REASON],
                _delivery_state.read_delivered_report(PinnedState(state_data=pinned)),
            ),
            (_KEPT, [5, 7, 9], None, delivery_support.DELIVERED),
        )
        self.assertEqual(tick.state.data, pinned)

    def test_a_fold_laid_over_the_tick_counts_once(self) -> None:
        # A road that lays another's fold over the tick's state says so, and
        # the record counts that fold as the comment's: only the tick's own run
        # is added to it.
        tick = self._tick(**{_TOKENS: _TICK_READ[_TOKENS]})
        folded = commit_support.another_road(
            tick.github, tick.issue, **{_TOKENS: _ANOTHER_ROAD[_TOKENS]},
        )
        tick.state.set(_TOKENS, folded[_TOKENS])
        _pinned_commit.takes_in(tick.state, folded, (_TOKENS,))
        tick.state.set(_TOKENS, _ANOTHER_ROAD[_TOKENS] + _TICK_FOLD)

        self.assertFalse(tick.records())

        self.assertEqual(tick.pinned()[_TOKENS], _ANOTHER_ROAD[_TOKENS] + _TICK_FOLD)

    def test_a_comment_moved_under_it_writes_nothing(self) -> None:
        # The tick ends with nothing written, posted, or parked, and its own
        # state as it was: the next tick decides afresh over the comment.
        for described, moves in _MOVES_UNDER_IT:
            with self.subTest(moved=described):
                tick = self._tick()
                moves(tick.github, tick.issue, tick.state)
                found = (tick.pinned(), dict(tick.state.data), [])

                self.assertTrue(tick.records())

                self.assertEqual(
                    (tick.pinned(), tick.state.data, tick.github.posted_comments), found,
                )

    def test_the_fresh_comment_s_room_decides(self) -> None:
        # Room is the comment's the record lands on, not the one the tick read.
        # Filled by another road since, the record's own write or the binding
        # it reserves no longer fits there, and the park says which; given
        # back since, the record lands with nothing parked or posted. Either
        # way the other road's write is kept.
        for read, since, said in _ROOM_SINCE:
            with self.subTest(read=read, since=since):
                tick = _Tick.over(delivery_support.crowded_comment(read, baselined=True))
                crowding = tick.crowded_since(since)

                self.assertEqual(
                    (
                        tick.records(),
                        tick.pinned()[delivery_support.CROWDING],
                        tick.pinned().get(delivery_support.PARK_REASON),
                        _delivery_state.carries_delivered_report(tick.state),
                        tick.notices_saying(said),
                    ),
                    (True, crowding, _delivery.UNDELIVERABLE_REPORT, False, [True]) if said
                    else (False, crowding, None, True, []),
                )

    def test_a_lost_answer_leaves_the_record(self) -> None:
        # GitHub took the record and its answer never came back, so nothing is
        # done on the strength of it this tick: nothing posted, the tick's
        # state left as it read it and withheld, so a whole-state write behind
        # it keeps what another road wrote meanwhile. What the next tick reads
        # is that very record, at its own revision.
        tick = self._tick()
        held = dict(tick.state.data)
        tick.github.pinned_failures.lost.add(tick.issue.number)

        self.assertTrue(tick.records())

        tick.github.pinned_failures.lost.discard(tick.issue.number)
        commit_support.another_road(tick.github, tick.issue, **_EVIDENCE_SINCE)
        tick.github.write_pinned_state(tick.issue, tick.state)
        landed = tick.github.read_pinned_state(tick.issue)
        self.assertEqual(
            (
                _delivery_state.read_delivered_report(landed),
                landed.get(_EVIDENCE),
                landed.get(delivery_support.PARK_REASON),
                (tick.state.data, tick.state.withheld),
                tick.github.posted_comments,
            ),
            (delivery_support.DELIVERED, _EVIDENCE_SINCE[_EVIDENCE], None, (held, True), []),
        )

    def test_growth_under_the_edit_writes_nothing(self) -> None:
        # Another road fills the comment after the commit read it and before
        # its edit lands. The edit is refused as moved, so nothing the tick
        # decided goes out -- no record, no park -- and the comment is that
        # road's alone.
        tick = _Tick.over(delivery_support.crowded_comment(_ROOMY, baselined=True))
        crowding = delivery_support.crowded_comment(
            delivery_support.CROWDED_FOR_RESERVATION, baselined=True,
        ).get(delivery_support.CROWDING)

        with commit_support.under_the_edit(
            tick.github, tick.issue, **{delivery_support.CROWDING: crowding},
        ):
            self.assertTrue(tick.records())

        self.assertEqual(
            (
                tick.pinned()[delivery_support.CROWDING],
                tick.pinned().get(_records.DELIVERED_REPORT),
                tick.github.posted_comments,
                tick.state.withheld,
            ),
            (crowding, None, [], True),
        )

    def _tick(self, **fields) -> _Tick:
        """An issue parked for its report, plus `fields`, and the state a tick read it into."""
        return _Tick.over(PinnedState(state_data={**_PARKED, **fields}))

class ParkCapacityTest(unittest.TestCase):
    """The park a refused record takes is prepared with room for the notice it posts."""

    def test_a_park_is_prepared_with_its_notice(self) -> None:
        # Comments at the brim: one with exactly the room the park's own flags
        # take, and one with room for those and for what posting its notice
        # writes -- a ledger entry and a watermark, reserved at their widest.
        # On the first nothing is posted and nothing written; on the second
        # the notice goes out and the park is recorded. The entry is reserved
        # on the ledger the park lands beside, so one another road filled with
        # the widest id since the tick read it is measured with a further
        # entry: posted only where there is room for that one as well.
        for beside, since, parks in _BRIMS:
            with self.subTest(since=since, parks=parks):
                tick = _Tick.over(_at_the_brim(beside))
                found = tick.pinned() if since is None else commit_support.another_road(
                    tick.github, tick.issue, **{_LEDGER: since},
                )

                self.assertTrue(tick.records(_PAST_THE_CEILING))

                self.assertEqual(
                    (
                        len(tick.github.posted_comments),
                        tick.pinned().get(delivery_support.PARK_REASON),
                        tick.pinned().get(_delivery.OWED_REPORT),
                    ),
                    (1, _delivery.UNDELIVERABLE_REPORT, True) if parks else (0, None, None),
                )
                if not parks:
                    self.assertEqual(tick.pinned(), found)


def _at_the_brim(beside: MappingProxyType) -> PinnedState:
    """A comment whose park, with `beside` written next to it, renders exactly as long as one comment holds."""
    record = {delivery_support.BASELINE: support.REQUIREMENTS, delivery_support.CROWDING: ""}
    rendered = len(pinned_state_body({**record, **_PARK_FLAGS, **beside}))
    record[delivery_support.CROWDING] = delivery_support.FILLER * (MAX_PINNED_BODY - rendered)
    return PinnedState(state_data=record)


if __name__ == "__main__":
    unittest.main()
