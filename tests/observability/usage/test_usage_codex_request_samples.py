# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Codex request samples read off the captured native session log, one invocation at a time."""

import itertools
import json
import unittest

from orchestrator.observability.usage import request_coverage as coverage
from tests.observability.usage import (
    usage_codex_native_capture as capture,
    usage_codex_request_cases as codex,
    usage_request_cases as cases,
)

_ID = "id"
_KIND = "kind"
_POSITION = "position"
_FLAGS = "source_flags"
_REASONING = "last_usage_includes_reasoning"
_VERSION = "source_version"
_CACHE_WRITES = "cache_write_tokens"
_CONTEXT = "context_input_tokens"
_BASELINE = "invocation-baseline"
_RUNNING = "cumulative-total"
_NO_VERSION = "no-source-version"
# The fresh invocation's three requests -- the first two scripted with equal usage -- by the log line reporting each.
_FRESH_LINES = (13, 18, 22)
# The fresh run's usage records, one beside each of its requests.
_FRESH_RECORDS = len(_FRESH_LINES)
_FRESH_IDS = ("rollout-line:13", "rollout-line:18", "rollout-line:22")
# Each invocation, the log lines reporting its own requests -- none appears under two invocations -- its status, and
# the turn it opened.
_OWN = (
    (capture.FRESH, _FRESH_LINES, coverage.COMPLETE, capture.FRESH_TURN),
    (capture.RESUMED, (32,), coverage.COMPLETE, capture.RESUMED_TURN),
    (capture.SWITCHED, (40, 52), coverage.COMPLETE, capture.SWITCH_TURN),
    (capture.FAILED, (), coverage.COMPLETE_EMPTY, capture.FAILED_TURN),
    (capture.INTERRUPTED, (69,), coverage.INCOMPLETE, capture.INTERRUPTED_TURN),
    (capture.LAST, (78,), coverage.COMPLETE, capture.LAST_TURN),
)
# The fresh invocation's last request, whose response reported no cache-write count, which the CLI printed as 0.
_SAMPLE_COUNTS = (13000, 11000, 0, 70, 0, 13070)
# The fresh invocation's first request, normalized: context input, output, reasoning, cache reads and writes, the
# common total, and the source's own.
_FIRST_FIELDS = ("context_input_tokens", "output_tokens", "reasoning_tokens", "cache_read_tokens", "cache_write_tokens")
_FIRST_NORMALIZED = (12000, 500, 100, 4000, 7000)
_FIRST_TOTALS = (12500, 12500)
_SWITCHED_MARKERS = (
    {_KIND: "compaction", _POSITION: 41, "conversation_id": capture.SESSION_ID},
    {
        _KIND: "model-change",
        _POSITION: 43,
        "conversation_id": capture.SESSION_ID,
        cases.MODEL: capture.SWITCHED_MODEL,
        "previous_model": capture.FIRST_MODEL,
    },
)
# The cache writes the switch's compaction request reported.
_SWITCH_WRITES = 900
# What the captured log holds that no request usage may: transcript text, a credential, and the working directory.
_PRIVATE = (capture.TEXT_CANARY, capture.CREDENTIAL_CANARY, capture.WORKSPACE)


def _recounted(text: str) -> str:
    """`text`, where it is a usage record, with its input and total raised alike: valid, but no longer its report's."""
    if '"token_usage_record"' not in text:
        return text
    return text.replace('"input_tokens":', '"input_tokens":9').replace('"total_tokens":', '"total_tokens":9')


class FreshInvocationTest(unittest.TestCase):
    """A fresh invocation's log is its own: every request it settled, each once, in the shared format."""

    def test_every_request_is_a_sample(self) -> None:
        collection = codex.collected()
        samples = collection.samples
        self.assertEqual(cases.column(samples, _ID), list(_FRESH_IDS))
        self.assertEqual(cases.column(samples, _POSITION), list(_FRESH_LINES))
        self.assertEqual(set(cases.column(samples, "id_kind")), {"native-position"})
        self.assertEqual(cases.column(samples, "branch_order"), [0, 1, 2])
        # Two requests reporting equal counts stay two: the running sum beside each advanced by its own counters.
        first, second, _ = samples
        self.assertEqual(first[cases.RAW], second[cases.RAW])
        self.assertEqual(collection.status, coverage.COMPLETE)
        self.assertEqual(collection.reasons, {})
        self.assertEqual(collection.coverage["scan_scope"], coverage.INVOCATION_SCOPE)
        self.assertEqual(collection.coverage["scanned_lines"], capture.FRESH.end)

    def test_samples_carry_what_the_log_reported(self) -> None:
        sample = codex.collected().samples[0]
        expected = {
            "session_id": capture.SESSION_ID,
            "conversation_id": capture.SESSION_ID,
            "turn_id": capture.FRESH_TURN,
            "model": capture.FIRST_MODEL,
            "model_source": "stream",
            "context_capacity": capture.CONTEXT_WINDOW,
            _VERSION: capture.CLI_VERSION,
            "source_timestamp": "2026-11-12T13:54:56.625Z",
            "scope": "request",
            "status": "final",
            "settlement": "token-count",
            _FLAGS: {_REASONING: False},
        }
        self.assertEqual({name: sample.get(name) for name in expected}, expected)
        self.assertNotIn("parent_turn_id", sample)

    def test_counters_keep_the_codex_semantics(self) -> None:
        # The input already holds the cache reads and writes; the reasoning is a part of the output, never added.
        first, _, unreported = codex.collected().samples
        self.assertEqual(cases.picked(first, *_FIRST_FIELDS), _FIRST_NORMALIZED)
        self.assertEqual(cases.picked(first, "total_tokens", "source_total_tokens"), _FIRST_TOTALS)
        self.assertEqual(first["overlap"], "input-includes-cache")
        # A raw write count of zero is kept as reported, but establishes neither no writes nor a lifetime.
        evidence = unreported[cases.EVIDENCE]
        self.assertEqual(codex.raw_sums([unreported]), _SAMPLE_COUNTS)
        self.assertNotIn(_CACHE_WRITES, unreported)
        self.assertEqual(evidence[_CACHE_WRITES], "missing")
        self.assertEqual(evidence["cache_write_lifetimes"], "missing")
        self.assertEqual(unreported[_CONTEXT], _SAMPLE_COUNTS[0])

    def test_samples_reconcile_with_running_sums(self) -> None:
        # The fresh thread's last running sum is the sum of its samples; no checkpoint is a request.
        collection = codex.collected()
        checkpoints = collection.checkpoints
        self.assertEqual(set(cases.column(checkpoints, _KIND)), {_RUNNING})
        self.assertEqual(cases.column(checkpoints, _POSITION), list(_FRESH_LINES))
        summed = codex.raw_sums(collection.samples)
        self.assertEqual(codex.raw_sums(checkpoints[-1:]), summed)
        self.assertEqual(set(cases.column(checkpoints, "scope")), {"conversation"})


class ResumedInvocationTest(unittest.TestCase):
    """Each resume of the one log keeps its own requests, never an earlier invocation's."""

    def test_each_invocation_keeps_only_its_own(self) -> None:
        for invocation, lines, status, turn in _OWN:
            with self.subTest(end=invocation.end):
                collection = codex.collected(invocation)
                self.assertEqual(tuple(cases.column(collection.samples, _POSITION)), lines)
                self.assertEqual(collection.status, status)
                self.assertLessEqual(set(cases.column(collection.samples, "turn_id")), {turn})

    def test_resumes_reconcile_against_their_baseline(self) -> None:
        # A resumed run's samples are what its running sums advanced past the baseline the earlier runs left.
        for previous, invocation in itertools.pairwise(capture.INVOCATIONS):
            with self.subTest(end=invocation.end):
                collection = codex.collected(invocation)
                baseline = collection.checkpoints[0]
                self.assertEqual(baseline[_KIND], _BASELINE)
                # The baseline is the last running sum the earlier invocations left, before this one's first line.
                self.assertLess(baseline[_POSITION], previous.end)
                summed = codex.raw_sums(collection.samples)
                self.assertEqual(self._advance(collection), summed)

    def test_a_model_switch_is_marked_and_attributed(self) -> None:
        # The compaction the switch runs first is a request on the model the thread had; the turn's own requests
        # after its `turn_context` ran on the new one. The repeated running sum opening the turn and the context
        # estimate after the compaction are no requests.
        collection = codex.collected(capture.SWITCHED)
        compaction, answer = collection.samples
        self.assertEqual(compaction[cases.MODEL], capture.FIRST_MODEL)
        self.assertEqual(compaction[_CACHE_WRITES], _SWITCH_WRITES)
        self.assertEqual(compaction[_FLAGS], {_REASONING: False})
        self.assertEqual(answer[cases.MODEL], capture.SWITCHED_MODEL)
        self.assertEqual(answer[_FLAGS], {_REASONING: True})
        self.assertEqual(tuple(collection.markers), _SWITCHED_MARKERS)

    def test_a_resume_names_no_version(self) -> None:
        # The log's `session_meta` was written by the process that created it, so a resume's version is unknown.
        fresh = codex.collected()
        resumed = codex.collected(capture.RESUMED)
        self.assertNotIn(_NO_VERSION, fresh.coverage["limitations"])
        self.assertIn(_NO_VERSION, resumed.coverage["limitations"])
        self.assertNotIn(_VERSION, resumed.samples[0])

    def test_failed_and_interrupted_resumes(self) -> None:
        # A resume no request settled usage for is complete with nothing; one interrupted mid-turn keeps the request
        # it settled and says its turn never ended; the resume after it is whole again.
        failed = codex.collected(capture.FAILED)
        interrupted = codex.collected(capture.INTERRUPTED)
        last = codex.collected(capture.LAST)
        self.assertEqual(failed.samples, [])
        self.assertEqual(cases.column(failed.checkpoints, _KIND), [_BASELINE])
        self.assertEqual(interrupted.reasons, {coverage.NO_TERMINAL_RESULT: 1})
        self.assertEqual(len(interrupted.samples), 1)
        settled = interrupted.samples[0]
        self.assertEqual(last.checkpoints[0][_POSITION], settled[_POSITION])
        self.assertEqual(last.status, coverage.COMPLETE)

    def _advance(self, collection: cases.Collected) -> tuple[int, ...]:
        """How far a collection's last running sum moved past its baseline, counter by counter."""
        after = codex.raw_sums(collection.checkpoints[-1:])
        before = codex.raw_sums(collection.checkpoints[:1])
        pairs = zip(after, before, strict=True)
        return tuple(moved - start for moved, start in pairs)


class NativeSourceTest(unittest.TestCase):
    """Only `token_count` usage is a request: no other line's counters, nor stdout's, reach a sample."""

    def test_other_usage_reaches_no_sample(self) -> None:
        # The counters of a `token_usage_record` beside each request -- valid, but other than its report's -- and
        # stdout's cumulative `turn.completed` are never read as a request: the samples and checkpoints are the reports'
        # alone, while a record no report repeats still awaits one, usage this collection could not observe.
        changed = [_recounted(text) for text in capture.log_lines(capture.FRESH.end)]
        stdout = capture.FRESH.stdout.replace("37000", "1")
        unread = codex.collected(lines=changed, stdout=stdout)
        read = codex.collected()
        self.assertEqual((unread.samples, unread.checkpoints), (read.samples, read.checkpoints))
        self.assertEqual(unread.reasons, {coverage.UNSUPPORTED_USAGE_SOURCE: _FRESH_RECORDS})

    def test_no_text_or_credential(self) -> None:
        # Only allowlisted counters and correlation metadata reach a collection, whatever the lines beside them hold.
        for invocation in capture.INVOCATIONS:
            serialized = json.dumps(codex.collected(invocation).serialized)
            for private in _PRIVATE:
                with self.subTest(end=invocation.end, private=private):
                    self.assertNotIn(private, serialized)


if __name__ == "__main__":
    unittest.main()
