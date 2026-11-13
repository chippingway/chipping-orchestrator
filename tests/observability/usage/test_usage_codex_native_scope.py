# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Which lines of a Codex native session log one invocation wrote, and why a scope attributes none of them."""

import json
import unittest
from datetime import UTC, datetime
from unittest.mock import patch

from orchestrator.observability.usage import request_coverage as coverage, request_scan
from orchestrator.observability.usage.request_codex_scope import stdout_turns
from orchestrator.observability.usage.request_codex_turns import UNPLACED
from tests.observability.usage import usage_codex_native_capture as capture, usage_codex_request_cases as codex

_LINES = "lines"
_TIMESTAMP = "timestamp"
_STARTED = codex.event(codex.TASK_STARTED, turn_id=codex.APPENDED_TURN)
_COMPLETE = codex.event(codex.TASK_COMPLETE, turn_id=codex.APPENDED_TURN)
_NEXT = codex.token_count(codex.NEXT_RUNNING, codex.NEXT_REQUEST)
_TURN_LINES = (_STARTED, _NEXT, _COMPLETE)
_CUT_SHORT = '{"timestamp":"2026-11-12T14:10:01.000Z","type":"event_msg","payload":{"type":"token_'
_FRESH_LINES = capture.log_lines(capture.FRESH.end)
_FIRST_PAYLOAD = json.loads(_FRESH_LINES[0])["payload"]
_SILENT = codex.APPENDED._replace(stdout="")
_APPENDED_TURN_LOG = (*capture.log_lines(), *_TURN_LINES)
# The captured log's lines decoded, each line's ordinal, and each line's stamp as the moment it reads as.
_EVENTS = tuple(json.loads(text) for text in capture.log_lines())
_ORDINALS = tuple(event["ordinal"] for event in _EVENTS)
_MOMENTS = tuple(datetime.fromisoformat(event[_TIMESTAMP]) for event in _EVENTS)
# The stamp of the line before each line, the first one's preceded by none.
_PREVIOUS = (datetime.min.replace(tzinfo=UTC), *_MOMENTS)
# Each captured invocation and the turn it opened, every usage line it wrote settling in it; the failed one wrote none.
_OWN_TURNS = (
    (capture.FRESH, {capture.FRESH_TURN}),
    (capture.RESUMED, {capture.RESUMED_TURN}),
    (capture.SWITCHED, {capture.SWITCH_TURN}),
    (capture.FAILED, set()),
    (capture.INTERRUPTED, {capture.INTERRUPTED_TURN}),
    (capture.LAST, {capture.LAST_TURN}),
)
# Logs never adopted: another session's, one whose first line cannot be read, an empty one, one opening otherwise, and
# one naming an empty session id as the run did, which names no session at all.
_UNNAMED_FIRST = (_FRESH_LINES[0].replace(capture.SESSION_ID, ""),)
_NOT_OWN = (
    ("another session", {"session_id": "01a1d00a-0000-7000-8000-000000000000"}),
    ("first line cut short", {_LINES: (_CUT_SHORT, *_FRESH_LINES[1:])}),
    ("empty log", {_LINES: ()}),
    ("no session_meta first", {_LINES: _FRESH_LINES[1:]}),
    ("an empty session id", {"session_id": "", _LINES: _UNNAMED_FIRST}),
)
_SHORTER = codex.APPENDED._replace(start=capture.LAST.end + 1, stdout="")
# The captured log with a line of its earlier history cut short, and a turn appended past it stdout never started.
_PAST_DAMAGE = capture.log_lines()[3:]
_DAMAGED = (*capture.log_lines(2), _CUT_SHORT, *_PAST_DAMAGE, *_TURN_LINES)
# A line stamped after the captured log and before the appended invocation's launch.
_EARLIER_SETTINGS = codex.line(codex.EVENT_MSG, {"type": "thread_settings_applied"}, "2026-11-12T14:05:00.000Z")
# A resume launched once the fresh invocation had exited, on a clock stepped back to before its last requests, that
# wrote no line and printed nothing.
_STEPPED_BACK = capture.Invocation(
    datetime.fromisoformat("2026-11-12T13:54:56.650+00:00"), capture.FRESH.end, True, "", capture.FRESH.end,
)
_RESUMED_STAMP = '"timestamp":"2026-11-12T13:55:10.322Z"'
_EARLY_STAMP = '"timestamp":"2026-11-12T13:50:00.000Z"'
_RESUMED_LINES = capture.log_lines(capture.RESUMED.end)
_BACKWARD = tuple(text.replace(_RESUMED_STAMP, _EARLY_STAMP) for text in _RESUMED_LINES)
_FOREIGN_TURN = codex.event(codex.TASK_STARTED, turn_id=codex.CHILD_TURN)
# An own line stamped after the launch, yet before the line ahead of it.
_STAMPED_BACK = (_STARTED, _NEXT.replace(codex.STAMP, "2026-11-12T14:10:00.500Z"), _COMPLETE)
# Counts that place no line of a resumed run's: none taken, none of a line, and one below that.
_UNUSABLE_COUNTS = (None, 0, -1)
# Placements nothing proves: a resume its launch counted more lines for than the log read whole holds; stamps the clock
# contradicts -- a fresh run's log stamped before its launch, earlier lines stamped after it, the silent resume after a
# clock step back that would have taken the fresh invocation's last requests, an own line stamped before the launch, a
# resume's lines restamped to before it, and a stamp earlier than the one ahead of it -- and turns stdout does not
# account for: one past damaged history, one another process appended meanwhile, one stdout counts that the log never
# opened, and one the log opened that stdout never printed.
_UNPROVEN = (
    ("a silent resume of a log shorter than its count", _SHORTER, None),
    ("fresh log begun before the launch", capture.FRESH._replace(launched_at=capture.RESUMED.launched_at), None),
    ("earlier lines stamped after the launch", capture.RESUMED._replace(launched_at=capture.FRESH.launched_at), None),
    ("a silent resume after a clock step back", _STEPPED_BACK, None),
    ("an own line stamped before the launch", codex.APPENDED, (*capture.log_lines(), _EARLIER_SETTINGS, *_TURN_LINES)),
    ("a resume's lines restamped to before its launch", capture.RESUMED, _BACKWARD),
    ("a stamp earlier than the one ahead of it", codex.APPENDED, (*capture.log_lines(), *_STAMPED_BACK)),
    ("a turn stdout never started, past damaged earlier history", _SILENT, _DAMAGED),
    ("another process's turn", codex.APPENDED, (*_APPENDED_TURN_LOG, _FOREIGN_TURN)),
    ("a turn the log never opened", codex.APPENDED, capture.log_lines()),
    ("a turn stdout never printed", _SILENT, _APPENDED_TURN_LOG),
)
# Lines placed past the count whatever their stamps: one in the launch's own millisecond, past an earlier line in it,
# and unstamped ones.
_UNSTAMPED = f'"timestamp":"{codex.STAMP}",'
_UNSTAMPED_TURN = tuple(text.replace(_UNSTAMPED, "") for text in _TURN_LINES)
_UNSTAMPED_LOG = (*capture.log_lines(), *_UNSTAMPED_TURN)
_FIRST_RESUMED_LINE = datetime.fromisoformat("2026-11-12T13:55:10.309+00:00")
_BESIDE_FRESH_END = datetime.fromisoformat("2026-11-12T13:54:56.703500+00:00")
_RESUMED_OWN = range(capture.RESUMED.start, capture.RESUMED.end)
_PLACED = (
    ("a launch in its first line's millisecond", capture.RESUMED._replace(launched_at=_FIRST_RESUMED_LINE), None),
    ("an earlier line in the launch's millisecond", capture.RESUMED._replace(launched_at=_BESIDE_FRESH_END), None),
    ("unstamped lines", codex.APPENDED, _UNSTAMPED_LOG),
)
_PLACED_OWN = (_RESUMED_OWN, _RESUMED_OWN, range(capture.LAST.end, len(_UNSTAMPED_LOG)))
# Stamps no UTC moment reads as: one its offset moves before the first moment, one it moves past the last, one naming
# no offset, and one no ISO moment at all.
_UNREADABLE_STAMPS = ("0001-01-01T00:00:00+01:00", "9999-12-31T23:59:59-01:00", "2026-11-12T14:10:01", "yesterday")
# Lines a native log holds no object on, and lines whose envelope nothing can be read off.
_NO_OBJECTS = ('[{"type":"event_msg"}]', "Codex ready", "   ", "")
_NO_ENVELOPES = (
    codex.line(codex.EVENT_MSG, [1]),
    codex.line(codex.EVENT_MSG, {"info": {}}),
    json.dumps({_TIMESTAMP: codex.STAMP, "payload": {}}),
)
# The longest line the captured log holds, a line one character longer, and a short one padded past it.
_LONGEST = max(map(len, capture.log_lines()))
_PADDING = _LONGEST + 1 - len(codex.event("item_completed", text=""))
_OVERSIZE_LINE = codex.event("item_completed", text="x" * _PADDING)
_PADDED_LINE = " " * (_LONGEST + 1 - len(_NEXT)) + _NEXT
# What leaves a reader's read short of the log, which it records in the scan it shares: a read bound, a read failing
# partway, and a line it passed over as too long to read, which it hands to no one.
_READER_STOPS = (coverage.SCAN_LIMIT, coverage.NATIVE_READ_INTERRUPTED, coverage.OVERSIZE_LINES)
_ALL_BUT_LAST = capture.log_lines()[:-1]
# A stdout its scan cannot read whole, and one printing a running sum but no turn started.
_UNREADABLE_STDOUT = codex.APPENDED._replace(stdout='{"type":"turn.')
_COMPLETED_LINE = capture.LAST.stdout.splitlines()[-1]
_USAGE_ONLY_STDOUT = codex.APPENDED._replace(stdout=_COMPLETED_LINE)
_FOREIGN_TURN_LOG = (*_APPENDED_TURN_LOG, _FOREIGN_TURN)


class CapturedInvocationTest(unittest.TestCase):
    """Each captured invocation's own lines are exactly the ones its launch places, every one in a turn it opened."""

    def test_each_invocation_owns_its_lines(self) -> None:
        for invocation, turn_ids in _OWN_TURNS:
            with self.subTest(start=invocation.start):
                scoped = codex.scoped(invocation)
                self.assertIsNone(scoped.refusal)
                self.assertEqual(scoped.own, list(range(invocation.start, invocation.end)))
                self.assertEqual(scoped.usage_turns, turn_ids)
                self.assertEqual(scoped.scope.turns.root_turns, 1)
                scoped.scope.turns.abandon()
                # The interrupted invocation's turn is the one no line closed.
                self.assertEqual(scoped.scope.turns.unclosed, int(invocation is capture.INTERRUPTED))

    def test_stdout_counts_turns_alone(self) -> None:
        # Each invocation's stdout started one turn, whatever running sum its `turn.completed` printed, and that sum is
        # never a turn: a stdout printing it alone started none, so a turn the log opened is no proven one of its own.
        for invocation in capture.INVOCATIONS:
            with self.subTest(start=invocation.start):
                self.assertEqual(stdout_turns(invocation.stdout, request_scan.current_limits()), 1)
        usage_only = codex.scoped(_USAGE_ONLY_STDOUT, _APPENDED_TURN_LOG)
        self.assertEqual(usage_only.refusal, coverage.INVOCATION_UNATTRIBUTED)

    def test_only_a_fresh_run_wrote_its_version(self) -> None:
        for invocation in (capture.FRESH, capture.RESUMED):
            with self.subTest(resumed=invocation.resumed):
                scope = codex.scoped(invocation).scope
                version = scope.timeline.writer_version(_FIRST_PAYLOAD, scope.metadata)
                self.assertEqual(version, None if invocation.resumed else capture.CLI_VERSION)

    def test_the_capture_keeps_its_provenance(self) -> None:
        # Every line of the log is numbered by its ordinal and stamped no earlier than the one before it, the last
        # invocation ends the log, and each inferred launch falls after the line before it and before its own first.
        self.assertEqual(_ORDINALS, tuple(range(capture.LAST.end)))
        self.assertEqual(list(_MOMENTS), sorted(_MOMENTS))
        self.assertEqual(capture.log_text().splitlines(), list(capture.log_lines()))
        for invocation in capture.INVOCATIONS:
            with self.subTest(start=invocation.start):
                self.assertLess(_PREVIOUS[invocation.start], invocation.launched_at)
                self.assertLess(invocation.launched_at, _MOMENTS[invocation.start])
        # The transcript text and credential the capture holds are canaries; its working directory is a placeholder.
        for canary in (capture.TEXT_CANARY, capture.CREDENTIAL_CANARY, capture.WORKSPACE):
            self.assertIn(canary, capture.log_text())


class UnattributedLogTest(unittest.TestCase):
    """A scope that cannot prove what the invocation wrote attributes nothing, and says why."""

    def test_a_log_not_the_sessions_own(self) -> None:
        for name, options in _NOT_OWN:
            with self.subTest(name):
                self.assertEqual(codex.scoped(**options).refusal, coverage.NATIVE_IDENTITY_UNPROVEN)

    def test_an_unprovable_boundary(self) -> None:
        for name, invocation, lines in _UNPROVEN:
            with self.subTest(name):
                scoped = codex.scoped(invocation, lines)
                self.assertEqual(scoped.refusal, coverage.INVOCATION_UNATTRIBUTED)
                self.assertGreater(scoped.scope.scan.scanned_lines, 0)

    def test_an_unusable_count_places_no_line(self) -> None:
        # A resume continues a log that held at least one line, so a count of fewer places none of it as the
        # invocation's, however much of the log would otherwise be taken for its own.
        for counted in _UNUSABLE_COUNTS:
            with self.subTest(counted=counted):
                scoped = codex.scoped(capture.RESUMED._replace(start=counted))
                self.assertEqual(scoped.refusal, coverage.INVOCATION_UNATTRIBUTED)
                self.assertEqual(scoped.own, [])
                self.assertIsNone(scoped.scope.timeline.boundary)

    def test_an_invocation_that_wrote_nothing(self) -> None:
        # A resume that wrote no line, and whose stdout started no turn, crossed no boundary and is refused nothing.
        scoped = codex.scoped(_SILENT)
        self.assertIsNone(scoped.refusal)
        self.assertEqual(scoped.own, [])
        self.assertIsNone(scoped.scope.timeline.boundary)


class LaunchPlacementTest(unittest.TestCase):
    """A resumed run's own lines are the ones past its launch's count, its stamps only able to contradict that."""

    def test_lines_placed_by_the_count(self) -> None:
        # A line in the launch's own millisecond is placed by the count, and an unstamped one too.
        for (name, invocation, lines), own in zip(_PLACED, _PLACED_OWN, strict=True):
            with self.subTest(name):
                scoped = codex.scoped(invocation, lines)
                self.assertIsNone(scoped.refusal)
                self.assertEqual(scoped.own, list(own))

    def test_stamps_that_place_nothing(self) -> None:
        # An unstamped line keeps no stamp, and a stamp no UTC moment reads as -- its offset carrying it out of range
        # included -- is malformed metadata kept as written; neither places anything.
        unstamped = codex.scoped(codex.APPENDED, _UNSTAMPED_LOG)
        self.assertEqual({line.stamp for line in unstamped.lines if line.own}, {None})
        for stamp in _UNREADABLE_STAMPS:
            with self.subTest(stamp):
                scoped = codex.appended(_STARTED, _NEXT.replace(codex.STAMP, stamp), _COMPLETE)
                self.assertIsNone(scoped.refusal)
                self.assertEqual(scoped.scope.metadata.malformed, 1)
                self.assertIn(stamp, {line.stamp for line in scoped.lines})


class PartialReadTest(unittest.TestCase):
    """Lines the scan could not read are counted where they stand, and a read cut short proves no extent."""

    def test_unreadable_lines_lose_turn_knowledge(self) -> None:
        # A line holding no object, or whose envelope nothing can be read off, is scanned where it stands; it could
        # have opened or closed any turn, so the next line read loses track of which are open.
        for unread in (*_NO_OBJECTS, *_NO_ENVELOPES):
            with self.subTest(unread=unread):
                scoped = codex.appended(_STARTED, unread, _NEXT, _COMPLETE)
                self.assertEqual(scoped.settled(codex.TOKEN_COUNT), [UNPLACED])
                self.assertTrue(any(line.lost for line in scoped.lines if line.own))
                self.assertIsNone(scoped.refusal)
                self.assertEqual(scoped.scope.scan.scanned_lines, capture.LAST.end + 4)

    def test_an_oversize_line_is_skipped(self) -> None:
        # A line past the line bound is counted and skipped however it was handed over, cutting the read short of the
        # whole log, and it could have opened another turn, so the report after it is placed in none.
        for oversize in (_OVERSIZE_LINE, _PADDED_LINE):
            bound = patch.object(request_scan, "MAX_LINE_CHARS", _LONGEST)
            with self.subTest(padded=oversize.startswith(" ")), bound:
                scoped = codex.appended(_STARTED, oversize, _NEXT, _COMPLETE)
                self.assertEqual(len(oversize), _LONGEST + 1)
                self.assertEqual(scoped.scope.scan.gaps, {coverage.OVERSIZE_LINES: 1})
                self.assertEqual(scoped.settled(codex.TOKEN_COUNT), [UNPLACED])
                self.assertIsNone(scoped.refusal)

    def test_a_read_stopped_short(self) -> None:
        # A reader a bound or a failing read stopped records why in the scan it shares, counting only the lines read;
        # the lines past the cut prove nothing, so neither a turn stdout printed and the read never reached nor a read
        # ending short of the lines the launch counted refuses anything -- as the same lines read whole would.
        self.assertEqual(codex.scoped(codex.APPENDED, _ALL_BUT_LAST).refusal, coverage.INVOCATION_UNATTRIBUTED)
        for gap in _READER_STOPS:
            with self.subTest(gap):
                scan = request_scan.EventScan(request_scan.current_limits())
                scan.gaps[gap] += 1
                scoped = codex.scoped(codex.APPENDED, _ALL_BUT_LAST, scan=scan)
                self.assertIsNone(scoped.refusal)
                self.assertEqual(scan.gaps, {gap: 1})
                self.assertEqual(scan.scanned_lines, len(_ALL_BUT_LAST))

    def test_an_unreadable_stdout_counts_nothing(self) -> None:
        # A stdout line the scan could not read could have started a turn, so the turns the log opened are held to none.
        self.assertIsNone(stdout_turns(_UNREADABLE_STDOUT.stdout, request_scan.current_limits()))
        self.assertIsNone(codex.scoped(_UNREADABLE_STDOUT, _FOREIGN_TURN_LOG).refusal)


if __name__ == "__main__":
    unittest.main()
