# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The Codex request fold's own state: the usage records it keeps awaiting a report, held to their bounds."""

import unittest
from collections.abc import Iterable
from types import MappingProxyType
from unittest.mock import patch

from orchestrator.observability.usage import request_coverage as coverage, request_scan
from orchestrator.observability.usage.request_codex_counters import Counters, usage_gaps
from orchestrator.observability.usage.request_codex_fold import Branch, NativeFold, Notes, Requests
from orchestrator.observability.usage.request_codex_scope import Invocation, NativeScope
from tests.observability.usage import (
    usage_codex_native_capture as capture,
    usage_codex_request_cases as codex,
    usage_request_cases as cases,
)

_PRIOR_STAMP = "2026-11-12T14:09:00.000Z"
_THREAD = codex.APPENDED_TURN
_CHILD = codex.CHILD_TURN
_THREAD_COUNTS = (300, 0, 0, 30, 0, 330)
_CHILD_COUNTS = (100, 0, 0, 10, 0, 110)
_CHILD_TWICE = tuple(2 * count for count in _CHILD_COUNTS)
_SESSION_META = capture.log_lines(1)[0]
_FRESH = Invocation(capture.SESSION_ID, False, None)


def _record(turn: str, counts: tuple[int, ...], stamp: str = codex.STAMP) -> str:
    """A usage record naming `turn`, repeating `counts`."""
    payload = {codex.TURN_ID: turn, "usage": codex.counters(counts)}
    return codex.line("token_usage_record", payload, stamp)


# A fresh run whose thread turn records a request and whose child turn records two, the child's turn staying open
# after the thread's closes; each of the child's requests then reported, and a third recorded after them.
_OPENED = (
    _SESSION_META,
    codex.event(codex.TASK_STARTED, turn_id=_THREAD),
    codex.event(codex.TASK_STARTED, turn_id=_CHILD, turn_attribution={"parent_turn_id": _THREAD}),
    _record(_THREAD, _THREAD_COUNTS),
    _record(_CHILD, _CHILD_COUNTS),
    _record(_CHILD, _CHILD_COUNTS),
    codex.event("task_complete", turn_id=_THREAD),
)
_REPORTED = (codex.token_count(_CHILD_COUNTS, _CHILD_COUNTS), codex.token_count(_CHILD_TWICE, _CHILD_COUNTS))
_LATER = (_record(_CHILD, _CHILD_COUNTS),)
# An earlier turn recording three requests of other counts, the first of them then reported, before a resume.
_EARLIER_COUNTS = (
    (10, 0, 0, 1, 0, 11),
    (20, 0, 0, 1, 0, 21),
    (30, 0, 0, 1, 0, 31),
)
_EARLIER_RECORDS = tuple(_record(capture.FRESH_TURN, counts, _PRIOR_STAMP) for counts in _EARLIER_COUNTS)
_EARLIER_START = MappingProxyType({"type": codex.TASK_STARTED, codex.TURN_ID: capture.FRESH_TURN})
_EARLIER_STARTED = codex.line(codex.EVENT_MSG, dict(_EARLIER_START), _PRIOR_STAMP)
_EARLIER = (_SESSION_META, _EARLIER_STARTED, *_EARLIER_RECORDS)
_FIRST_EARLIER = _EARLIER_COUNTS[0]
_EARLIER_REPORT = codex.token_count(_FIRST_EARLIER, _FIRST_EARLIER).replace(codex.STAMP, _PRIOR_STAMP)
_RESUMED = Invocation(capture.SESSION_ID, True, codex.APPENDED_AT, len(_EARLIER) + 1)
# A running sum, a request, and the sum it advances to by exactly that request -- still short of an input floor of 100.
_BEFORE_COUNTS = (10, 0, 0, 1, 0, 11)
_REQUEST_COUNTS = (1, 0, 0, 0, 0, 1)
_AFTER_COUNTS = (11, 0, 0, 1, 0, 12)
_BEFORE = Counters.of(codex.counters(_BEFORE_COUNTS))
_REQUEST = Counters.of(codex.counters(_REQUEST_COUNTS))
_AFTER = Counters.of(codex.counters(_AFTER_COUNTS))
_INPUT_FLOOR = MappingProxyType({"input_tokens": 100})
# An input floor earlier requests added up to the first number past any count -- which no report could give -- and
# a report whose running sum stands below it.
_PAST_ANY_FLOOR = MappingProxyType({"input_tokens": cases.PAST_ANY_COUNT})
_AFTER_INFO = MappingProxyType({"total_token_usage": codex.counters(_AFTER_COUNTS)})
_AFTER_REPORT = MappingProxyType({**_AFTER_INFO, "last_token_usage": codex.counters(_REQUEST_COUNTS)})
# A thread's first request, then a repeat of its sum beside a request past it -- or, after a compaction, beside the
# context estimate the CLI follows one with, a total past the sum beside parts all zero.
_THREAD_STARTED = codex.event(codex.TASK_STARTED, turn_id=_THREAD)
_FIRST = (_SESSION_META, _THREAD_STARTED, codex.token_count(_CHILD_COUNTS, _CHILD_COUNTS))
_REPEAT_PAST = (*_FIRST, codex.token_count(_CHILD_COUNTS, _CHILD_TWICE))
_ESTIMATE_COUNTS = (0, 0, 0, 0, 0, 9548)
_ESTIMATE = codex.token_count(_CHILD_COUNTS, _ESTIMATE_COUNTS)
_ESTIMATED = (*_FIRST, codex.line("compacted", {}), _ESTIMATE)
# What the fold keeps at each step: the invocation's records -- in all, on the thread, on the child turn, then counted
# without their counters on each -- and the earlier invocations' -- in all, on the thread, then on no branch.
_OPENED_KEPT = (2, 1, 1, 0, 1)
_REPORTED_KEPT = (1, 1, 0, 0, 0)
_LATER_KEPT = (2, 1, 1, 0, 0)
_EARLIER_TOLD = (2, 2, 1)
_ANSWERED_TOLD = (1, 1, 1)


def _opened(invocation: Invocation) -> NativeFold:
    """A fold over `invocation`'s log, opened as the collector opens one."""
    scope = NativeScope.of(invocation)
    requests = Requests(invocation.session_id, scope.scan, scope.metadata, None)
    notes = Notes(invocation.session_id, scope.scan.limits, scope.metadata)
    return NativeFold(scope, requests, notes)


def _fed(fold: NativeFold, lines: Iterable[str]) -> Requests:
    """The requests `fold` keeps once `lines` are folded in after the ones it already scanned."""
    for position, raw_line in enumerate(lines, fold.scope.scan.scanned_lines):
        fold.feed(position, raw_line)
    return fold.requests


def _awaiting(requests: Requests) -> tuple[int, ...]:
    """The invocation's records `requests` keeps with their counters, in all and branch by branch, then the ones each
    branch counts without them."""
    branches = requests.branches.values()
    kept = [len(branch.pending) for branch in branches]
    unkept = [branch.unkept for branch in branches]
    return (requests.recorded, *kept, *unkept)


def _told_apart(requests: Requests) -> tuple[int, ...]:
    """The earlier invocations' records `requests` keeps with their counters, in all and on the thread, then the ones
    on no branch."""
    thread = requests.branches[None]
    return (requests.held, len(thread.earlier), len(requests.unplaced))


class RetainedRecordsTest(unittest.TestCase):
    """What the fold keeps of the records awaiting a report, across every branch, as reports answer them."""

    def test_own_records_held_to_the_request_bound(self) -> None:
        # Past the request bound a record of the invocation's is counted without its counters, as is every one behind
        # it on its branch, so no more are kept than the bound across branches; reports answer the kept ones first,
        # freeing room a record written after them takes again.
        with patch.object(request_scan, "MAX_TRACKED_STEPS", 2):
            fold = _opened(_FRESH)
            requests = _fed(fold, _OPENED)
            self.assertEqual(_awaiting(requests), _OPENED_KEPT)
            self.assertEqual(requests.gaps[coverage.CORRELATION_LIMIT], 1)
            self.assertEqual(_awaiting(_fed(fold, _REPORTED)), _REPORTED_KEPT)
            self.assertEqual(_awaiting(_fed(fold, _LATER)), _LATER_KEPT)

    def test_a_move_below_the_floor_proves_nothing(self) -> None:
        # A running sum moving by exactly a request's counters proves it only where the sum holds the least its
        # branch's earlier reports establish, a request reported beside an earlier sum included.
        self.assertTrue(_AFTER and _AFTER.advanced_by(_BEFORE, _REQUEST, {}))
        self.assertFalse(_AFTER and _AFTER.advanced_by(_BEFORE, _REQUEST, _INPUT_FLOOR))

    def test_a_floor_past_any_count_still_holds(self) -> None:
        # A floor is the whole number earlier reports add up to, never read again as a count one report gave, so one
        # past the digits a count may have still holds the running sum: no move proves a request below it, the sum
        # contradicts it, and the branch is left unproven.
        branch = Branch(floor=dict(_PAST_ANY_FLOOR))
        branch.hold(_AFTER, None)
        self.assertFalse(branch.proven)
        self.assertFalse(_AFTER and _AFTER.advanced_by(_BEFORE, _REQUEST, _PAST_ANY_FLOOR))
        gaps = usage_gaps(dict(_AFTER_REPORT), _AFTER, floor=_PAST_ANY_FLOOR)
        self.assertEqual(gaps, {coverage.CONFLICTING_COUNTERS})

    def test_a_repeat_held_to_the_request_beside_it(self) -> None:
        # A repeat is no request, but its sum holds the request reported beside it, so one past the sum contradicts it
        # and leaves the branch unproven -- but for the context estimate after a compaction, which is no request.
        self.assertFalse(_fed(_opened(_FRESH), _REPEAT_PAST).branches[None].proven)
        self.assertTrue(_fed(_opened(_FRESH), _ESTIMATED).branches[None].proven)

    def test_earlier_records_held_to_the_branch_bound(self) -> None:
        # Past the branch bound an earlier invocation's record is no longer told apart, and one ruling nothing out
        # stands, on no branch, for every one dropped; a report answering a kept one frees its place.
        with patch.object(request_scan, "MAX_BRANCHES", 2):
            fold = _opened(_RESUMED)
            self.assertEqual(_told_apart(_fed(fold, _EARLIER)), _EARLIER_TOLD)
            self.assertEqual(_told_apart(_fed(fold, (_EARLIER_REPORT,))), _ANSWERED_TOLD)
