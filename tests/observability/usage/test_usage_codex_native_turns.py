# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The turns a Codex native session log opens, and the one each of an invocation's usage lines settles in."""

import dataclasses
import unittest
from types import MappingProxyType
from unittest.mock import patch

from orchestrator.observability.usage import request_coverage as coverage, request_scan
from orchestrator.observability.usage.request_codex_turns import UNPLACED, Turns
from tests.observability.usage import usage_codex_native_capture as capture, usage_codex_request_cases as codex

_REPEATS = 50
_PARENT_TURN = "parent_turn_id"
_ATTRIBUTION = "turn_attribution"
_PARENT = MappingProxyType({_PARENT_TURN: codex.APPENDED_TURN})
_USAGE_KEY = "usage"
_USAGE = codex.counters(codex.NEXT_REQUEST)
_STARTED = codex.event(codex.TASK_STARTED, turn_id=codex.APPENDED_TURN)
_COMPLETE = codex.event(codex.TASK_COMPLETE, turn_id=codex.APPENDED_TURN)
_NEXT = codex.token_count(codex.NEXT_RUNNING, codex.NEXT_REQUEST)
_SILENT = codex.APPENDED._replace(stdout="")
_CHILD_STARTED = codex.event(codex.TASK_STARTED, turn_id=codex.CHILD_TURN, turn_attribution=dict(_PARENT))
_CHILD_COMPLETE = codex.event(codex.TASK_COMPLETE, turn_id=codex.CHILD_TURN)
# A child turn's running sum is its own branch's, beginning at nothing.
_CHILD_REQUEST = codex.token_count(codex.NEXT_REQUEST, codex.NEXT_REQUEST)
# The usage record the CLI writes just before a request's report, naming the turn it settles in.
_CHILD_RECORD = codex.line(codex.USAGE_RECORD, {codex.TURN_ID: codex.CHILD_TURN, _USAGE_KEY: _USAGE})
_ROOT_RECORD = codex.line(codex.USAGE_RECORD, {codex.TURN_ID: codex.APPENDED_TURN, _USAGE_KEY: _USAGE})
_SECOND_CHILD = "01a1d020-0000-7000-8000-000000000003"
_SECOND_STARTED = codex.event(codex.TASK_STARTED, turn_id=_SECOND_CHILD, turn_attribution=dict(_PARENT))
_SECOND_RECORD = codex.line(codex.USAGE_RECORD, {codex.TURN_ID: _SECOND_CHILD, _USAGE_KEY: _USAGE})
_SECOND_COMPLETE = codex.event(codex.TASK_COMPLETE, turn_id=_SECOND_CHILD)
_OVERLAPPING = (_STARTED, _CHILD_STARTED, _SECOND_STARTED)
_CLOSING = (_SECOND_COMPLETE, _CHILD_COMPLETE, _COMPLETE)
# A notification carrying no usage, such as a rate-limit update, settles nothing, so it spends no record.
_NO_USAGE = codex.event(codex.TOKEN_COUNT, info=None)
# Reports among overlapping turns, each told apart by the record before it, or not; a record naming a turn closed since
# tells nothing, so the one turn left open, or a record naming one still open, places the report after it.
_EACH_NAMED = (*_OVERLAPPING, _CHILD_RECORD, _NEXT, _SECOND_RECORD, _NO_USAGE, _NEXT, *_CLOSING)
_CLOSED_NAMED = (_STARTED, _CHILD_STARTED, _CHILD_RECORD, _CHILD_COMPLETE, _NEXT, _COMPLETE)
_ROOT_NAMED = (_STARTED, _CHILD_STARTED, _CHILD_RECORD, _CHILD_COMPLETE, _ROOT_RECORD, _NEXT, _COMPLETE)
_SECOND_LEFT = (*_OVERLAPPING, _CHILD_RECORD, _SECOND_RECORD, _CHILD_COMPLETE, _NEXT, _SECOND_COMPLETE, _COMPLETE)
_TOLD = (
    ("records naming each child", _EACH_NAMED, (codex.CHILD_TURN, None, _SECOND_CHILD)),
    ("a record naming a turn closed since", _CLOSED_NAMED, (codex.APPENDED_TURN,)),
    ("a closed turn's record, then one naming the root", _ROOT_NAMED, (codex.APPENDED_TURN,)),
    ("records naming two turns, one closed since", _SECOND_LEFT, (_SECOND_CHILD,)),
)
_UNTOLD = (
    ("two child turns", (*_OVERLAPPING, _CHILD_REQUEST, *_CLOSING)),
    ("a parent and its child", (_STARTED, _CHILD_STARTED, _CHILD_REQUEST, _CHILD_COMPLETE, _COMPLETE)),
    ("records naming two turns", (*_OVERLAPPING, _CHILD_RECORD, _SECOND_RECORD, _CHILD_REQUEST, *_CLOSING)),
)
# Past a child turn's start cut short: a grandchild started from that child, a record naming the child, and one naming
# the root, none of which tells which turns are open or proves another process wrote it; then a root turn opened, which
# leaves itself alone open again.
_CUT_AT = _CHILD_STARTED.rindex(codex.APPENDED_TURN)
_CUT_CHILD_START = _CHILD_STARTED[:_CUT_AT]
_GRANDCHILD_PARENT = MappingProxyType({_PARENT_TURN: codex.CHILD_TURN})
_GRANDCHILD = "01a1d020-0000-7000-8000-000000000005"
_GRANDCHILD_STARTED = codex.event(codex.TASK_STARTED, turn_id=_GRANDCHILD, turn_attribution=dict(_GRANDCHILD_PARENT))
_LATER_ROOT = "01a1d020-0000-7000-8000-000000000004"
_LATER_STARTED = codex.event(codex.TASK_STARTED, turn_id=_LATER_ROOT)
_LATER_RECORD = codex.line(codex.USAGE_RECORD, {codex.TURN_ID: _LATER_ROOT, _USAGE_KEY: _USAGE})
_LATER_COMPLETE = codex.event(codex.TASK_COMPLETE, turn_id=_LATER_ROOT)
_TWO_TURNS_STDOUT = f"{codex.ONE_TURN_STDOUT}\n{codex.ONE_TURN_STDOUT}"
_TWO_TURNS = codex.APPENDED._replace(stdout=_TWO_TURNS_STDOUT)
_LOST_TURN = (_STARTED, _CUT_CHILD_START, _GRANDCHILD_STARTED, _CHILD_RECORD, _ROOT_RECORD, _NEXT, _NEXT, _COMPLETE)
_RECOVERED = (*_LOST_TURN, _LATER_STARTED, _LATER_RECORD, _NEXT, _LATER_COMPLETE)
# The fresh invocation's start with its parentage unproven -- an attribution that is no object, a parent named by no
# string, and one named past the metadata bound -- and the refusal its metadata counts.
_FRESH_LINES = capture.log_lines(capture.FRESH.end)
_FRESH_START = _FRESH_LINES[1]
_NO_PARENT = '"parent_turn_id":null'
_OVERSIZED_ID = "p" * (request_scan.MAX_METADATA_CHARS + 1)
_NO_OBJECT_START = _FRESH_START.replace('"turn_attribution":{', '"turn_attribution":["malformed"],"unread":{', 1)
_NO_STRING_START = _FRESH_START.replace(_NO_PARENT, '"parent_turn_id":7')
_OVERSIZED_START = _FRESH_START.replace(_NO_PARENT, f'"parent_turn_id":"{_OVERSIZED_ID}"')
_UNPLACED_STARTS = (
    ("an attribution no object", _NO_OBJECT_START, "malformed"),
    ("a parent no string", _NO_STRING_START, "malformed"),
    ("a parent past the bound", _OVERSIZED_START, "oversize"),
)
_FRESH_REST = _FRESH_LINES[2:]
# Records naming their turn by an id this reading refused -- one past the metadata bound, and one no string -- and the
# metadata refusal each counts.
_OVERSIZED_RECORD = codex.line(codex.USAGE_RECORD, {codex.TURN_ID: _OVERSIZED_ID, _USAGE_KEY: _USAGE})
_NO_STRING_RECORD = codex.line(codex.USAGE_RECORD, {codex.TURN_ID: 7, _USAGE_KEY: _USAGE})
_REFUSED_RECORDS = (
    ("an id past the bound", _OVERSIZED_RECORD, "oversize"),
    ("an id no string", _NO_STRING_RECORD, "malformed"),
)
# Usage in no turn the invocation opened, and a child it started from a turn it did not: a silent resume after the
# interrupted invocation settling usage in the turn that invocation left open, or starting a child from it; records
# naming the last captured turn, with or without a turn of the invocation's own; a request in no turn at all; and a
# child turn naming a parent never opened.
_AFTER_INTERRUPTED = codex.APPENDED._replace(start=capture.INTERRUPTED.end, stdout="")
_BEFORE_RESUME = capture.log_lines(capture.INTERRUPTED.end)
_INTERRUPTED_RECORD = codex.line(codex.USAGE_RECORD, {codex.TURN_ID: capture.INTERRUPTED_TURN, _USAGE_KEY: _USAGE})
_INTERRUPTED_PARENT = MappingProxyType({_PARENT_TURN: capture.INTERRUPTED_TURN})
_EARLIER_CHILD = codex.event(codex.TASK_STARTED, turn_id=codex.CHILD_TURN, turn_attribution=dict(_INTERRUPTED_PARENT))
_EARLIER_RECORD = codex.line(codex.USAGE_RECORD, {codex.TURN_ID: capture.LAST_TURN, _USAGE_KEY: _USAGE})
_ORPHAN_PARENT = MappingProxyType({_PARENT_TURN: _SECOND_CHILD})
_ORPHAN_CHILD = codex.event(codex.TASK_STARTED, turn_id=codex.CHILD_TURN, turn_attribution=dict(_ORPHAN_PARENT))
_FOREIGN = (
    ("usage settled in an earlier invocation's open turn", _AFTER_INTERRUPTED, (_INTERRUPTED_RECORD, _NEXT)),
    ("a child turn started from an earlier invocation's open turn", _AFTER_INTERRUPTED, (_EARLIER_CHILD,)),
    ("a record naming an earlier invocation's turn", codex.APPENDED, (_STARTED, _EARLIER_RECORD, _NEXT, _COMPLETE)),
    ("a silent resume's record naming an earlier turn", _SILENT, (_EARLIER_RECORD, _NEXT)),
    ("a silent resume's request in no turn at all", _SILENT, (_NEXT,)),
    ("a child turn naming a parent never opened", codex.APPENDED, (_STARTED, _ORPHAN_CHILD, _COMPLETE)),
)
_UNNAMED_CHILD = codex.event(codex.TASK_STARTED, turn_attribution=dict(_PARENT))
_CHILD_START = MappingProxyType({codex.TURN_ID: codex.CHILD_TURN, _ATTRIBUTION: dict(_PARENT)})
_UNNAMED_START = MappingProxyType({_ATTRIBUTION: dict(_PARENT)})
_CHILD_RUN = (_STARTED, _CHILD_STARTED, _CHILD_RECORD, _CHILD_REQUEST, _CHILD_COMPLETE, _NEXT, _COMPLETE)
_UNFINISHED_CHILD = (_STARTED, _CHILD_STARTED, _CHILD_RECORD, _CHILD_REQUEST, _COMPLETE)
_BRANCHES = "MAX_BRANCHES"
# Root turns one after another, each with a record and no report.
_ROOT_IDS = tuple(f"root-{index}" for index in range(_REPEATS))
# Each child turn bound, held to one child: on the child turns named, a second one started once the first finished,
# and on the ones open at once, a second one beside the first.
# Past each, a child started from the refused turn, and a record naming the root before a report: the refused turn
# could have made that request, so neither settles in the root.
_REFUSED_PARENT = MappingProxyType({_PARENT_TURN: _SECOND_CHILD})
_REFUSED_CHILD = codex.event(codex.TASK_STARTED, turn_id=_GRANDCHILD, turn_attribution=dict(_REFUSED_PARENT))
_PAST_REFUSED = (_ROOT_RECORD, _NEXT, _COMPLETE)
_SECOND_NAMED = (_STARTED, _CHILD_STARTED, _CHILD_COMPLETE, _SECOND_STARTED, _REFUSED_CHILD, *_PAST_REFUSED)
_SECOND_OPEN = (_STARTED, _CHILD_STARTED, _UNNAMED_CHILD, *_PAST_REFUSED)
_BOUNDS = (("child turns named", _SECOND_NAMED, 2), ("child turns open at once", _SECOND_OPEN, 1))


def _turn_ids(turns: list) -> list:
    return [turn and turn.turn_id for turn in turns]


class TurnPlacementTest(unittest.TestCase):
    """A report settles in the turn its record names, or the one turn open, and in none where nothing tells which."""

    def test_overlapping_turns_told_apart_by_records(self) -> None:
        for name, lines, turn_ids in _TOLD:
            with self.subTest(name):
                scoped = codex.appended(*lines)
                self.assertEqual(_turn_ids(scoped.reports), list(turn_ids))
                self.assertIsNone(scoped.refusal)

    def test_untold_reports_settle_in_no_turn(self) -> None:
        # With several turns open at once -- two child turns, or a parent and its child -- and no record naming one,
        # or records naming two, any of them could have made the request, so it is placed in none.
        for name, lines in _UNTOLD:
            with self.subTest(name):
                scoped = codex.appended(*lines)
                self.assertEqual(scoped.reports, [UNPLACED])
                self.assertIsNone(scoped.refusal)

    def test_refused_record_ids_settle_nowhere(self) -> None:
        # A record naming its turn by an id this reading refused names a turn nothing can tell -- never the one a record
        # naming none falls to -- so neither it nor the report after it settles in any, and neither proves anything.
        for name, record, refusal in _REFUSED_RECORDS:
            with self.subTest(name):
                scoped = codex.appended(_STARTED, record, _NEXT, _COMPLETE)
                self.assertEqual(scoped.settled(codex.USAGE_RECORD), [UNPLACED])
                self.assertEqual(scoped.reports, [UNPLACED])
                self.assertEqual(getattr(scoped.scope.metadata, refusal), 1)
                self.assertIsNone(scoped.refusal)

    def test_turn_knowledge_returns_with_a_root_turn(self) -> None:
        # Past a line no reading could place, which turns are open is unknown until a root turn opens, alone: no record
        # or report settles in any, and no child start or record naming a turn not known open is another process's.
        scoped = codex.scoped(_TWO_TURNS, (*capture.log_lines(), *_RECOVERED))
        records = scoped.settled(codex.USAGE_RECORD)
        reports = scoped.reports
        self.assertEqual(records[:2], [UNPLACED, UNPLACED])
        self.assertEqual(_turn_ids(records[2:]), [_LATER_ROOT])
        self.assertEqual(reports[:2], [UNPLACED, UNPLACED])
        self.assertEqual(_turn_ids(reports[2:]), [_LATER_ROOT])
        self.assertFalse(scoped.scope.turns.intruded)
        self.assertEqual(scoped.scope.turns.root_turns, 2)
        self.assertIsNone(scoped.refusal)


class TurnParentageTest(unittest.TestCase):
    """A child turn keeps the turn it was started from, and only the invocation's own turns hold its usage."""

    def test_a_child_turn_exposes_its_parent(self) -> None:
        scoped = codex.appended(*_CHILD_RUN)
        child, thread = scoped.reports
        self.assertEqual((child.parent_turn_id, child.branch), (codex.APPENDED_TURN, codex.CHILD_TURN))
        self.assertEqual((thread.turn_id, thread.branch), (codex.APPENDED_TURN, None))
        self.assertEqual(scoped.scope.turns.children, {codex.CHILD_TURN: codex.APPENDED_TURN})
        self.assertEqual(scoped.scope.turns.own_children, {codex.CHILD_TURN})
        self.assertIsNone(scoped.refusal)

    def test_a_child_turn_its_parent_finished_without(self) -> None:
        # It never finished, whatever requests it settled.
        scoped = codex.appended(*_UNFINISHED_CHILD)
        self.assertEqual(_turn_ids(scoped.reports), [codex.CHILD_TURN])
        scoped.scope.turns.abandon()
        self.assertEqual(scoped.scope.turns.unclosed, 1)

    def test_an_unproven_parentage_settles_nothing(self) -> None:
        # A start whose parent cannot be read is malformed metadata, abandons nothing, and settles no request; it is
        # counted as a root turn of the invocation's or not, so stdout's one turn is no contradiction.
        for name, started, refusal in _UNPLACED_STARTS:
            with self.subTest(name):
                scoped = codex.scoped(lines=(_FRESH_LINES[0], started, *_FRESH_REST))
                turns = scoped.scope.turns
                self.assertEqual(set(scoped.reports), {UNPLACED})
                self.assertEqual(turns.root_turns, 0)
                self.assertEqual(turns.uncertain, 1)
                self.assertEqual(getattr(scoped.scope.metadata, refusal), 1)
                self.assertIsNone(scoped.refusal)

    def test_usage_outside_the_invocations_turns(self) -> None:
        # The invocation opens its own turns before it settles usage in them or starts a child from them, so usage in
        # any other turn, or a child of one, was written by another process: nothing in the log is attributed.
        for name, invocation, lines in _FOREIGN:
            with self.subTest(name):
                before = _BEFORE_RESUME if invocation is _AFTER_INTERRUPTED else capture.log_lines()
                scoped = codex.scoped(invocation, (*before, *lines))
                self.assertTrue(scoped.scope.turns.intruded)
                self.assertEqual(scoped.refusal, coverage.INVOCATION_UNATTRIBUTED)


class TurnBoundTest(unittest.TestCase):
    """The turn state stays bounded however a log repeats or multiplies its child turns."""

    def test_repeated_child_starts_open_one_turn(self) -> None:
        scoped = codex.appended(_STARTED, *(_CHILD_STARTED,) * _REPEATS, _CHILD_RECORD, _CHILD_REQUEST)
        turns = scoped.scope.turns
        self.assertEqual(_turn_ids(scoped.reports), [codex.CHILD_TURN])
        self.assertEqual(len(turns.open), 2)
        self.assertEqual(len(turns.children), 1)
        self.assertFalse(turns.overflowed)
        limits = dataclasses.replace(request_scan.current_limits(), branches=1)
        turns = Turns(limits, request_scan.Metadata(limits.metadata_chars))
        turns.start({codex.TURN_ID: codex.APPENDED_TURN}, own=True)
        for start in (*(_CHILD_START,) * _REPEATS, _UNNAMED_START):
            turns.start(dict(start), own=True)
        self.assertEqual(len(turns.open), 2)
        self.assertEqual(turns.unnamed, 0)
        self.assertTrue(turns.overflowed)

    def test_child_turns_past_the_bound_are_refused(self) -> None:
        # A child turn the invocation starts past the bound is refused, whether or not a request follows it, and could
        # make any request after it, its parent's included: no usage line settles in any turn from there on, and no
        # child start -- one of the refused turn's included -- is taken for another process's.
        for name, lines, refused in _BOUNDS:
            with self.subTest(name), patch.object(request_scan, _BRANCHES, 1):
                scoped = codex.appended(*lines)
                turns = scoped.scope.turns
                self.assertTrue(turns.overflowed)
                self.assertEqual(turns.refused, refused)
                self.assertEqual(scoped.settled(codex.USAGE_RECORD), [UNPLACED])
                self.assertEqual(scoped.reports, [UNPLACED])
                self.assertFalse(turns.intruded)
                self.assertIsNone(scoped.refusal)

    def test_records_keep_only_open_turns(self) -> None:
        # A record whose turn closed since tells nothing, so however many turns come and go between two reports, the
        # records kept for the next one name only turns still open.
        limits = request_scan.current_limits()
        turns = Turns(limits, request_scan.Metadata(limits.metadata_chars))
        for turn_id in _ROOT_IDS:
            turns.start({codex.TURN_ID: turn_id}, own=True)
            turns.current(own=True, turn_id=turn_id)
        self.assertEqual(turns.records.named, turns.open)

    def test_a_child_turn_naming_no_id(self) -> None:
        # It is open, and never closed, but no branch can keep its requests, and beside its parent a report is untold.
        scoped = codex.appended(_STARTED, _UNNAMED_CHILD, _NEXT, _COMPLETE)
        turns = scoped.scope.turns
        self.assertEqual(scoped.reports, [UNPLACED])
        self.assertEqual(turns.unnamed, 1)
        self.assertTrue(turns.open[-1].unnamed_child)
        turns.abandon()
        self.assertEqual(turns.unclosed, 1)


if __name__ == "__main__":
    unittest.main()
