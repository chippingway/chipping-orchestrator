# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""One request's counters normalized under each provider's semantics, every field beside the evidence it rests on."""

import unittest
from collections.abc import Iterable
from decimal import Decimal
from types import MappingProxyType

from orchestrator.observability.usage import protocol, request_normalization as normalization

_Reading = normalization.Reading
_OBSERVED = normalization.OBSERVED
_MISSING = normalization.MISSING
_INVALID = normalization.INVALID
_CONFLICTING = normalization.CONFLICTING
_UNSUPPORTED = normalization.UNSUPPORTED

_CONTEXT = normalization.CONTEXT_INPUT_TOKENS
_OUTPUT = normalization.OUTPUT_TOKENS
_CACHE_READ = normalization.CACHE_READ_TOKENS
_CACHE_WRITE = normalization.CACHE_WRITE_TOKENS
_LIFETIMES = normalization.CACHE_WRITE_LIFETIMES
_REASONING = normalization.REASONING_TOKENS
_TOTAL = normalization.TOTAL_TOKENS
_SOURCE_TOTAL = normalization.SOURCE_TOTAL_TOKENS
_EVIDENCE = normalization.EVIDENCE

# The guide's cached Antigravity step: 278 ordinary input beside 30,214 cache reads, and a total of input and output.
_AGY_INPUT = 278
_AGY_CACHE_READ = 30_214
_AGY_OUTPUT = 4
_AGY_SOURCE_TOTAL = 282
_AGY_CONTEXT = 30_492
# A Codex request whose input already holds the 800 tokens the cache served.
_CODEX_INPUT = 1_000
_CODEX_CACHED = 800
_CODEX_OUTPUT = 50
_CODEX_REASONING = 20
# A Claude request writing 100 tokens to cache, 60 for five minutes and 40 for an hour.
_CLAUDE_INPUT = 10
_CLAUDE_CACHE_READ = 500
_CLAUDE_WRITE = 100
_CLAUDE_WRITE_FIVE_MIN = 60
_CLAUDE_WRITE_ONE_HOUR = 40
_CLAUDE_OUTPUT = 7
_CLAUDE_CONTEXT = _CLAUDE_INPUT + _CLAUDE_CACHE_READ + _CLAUDE_WRITE
# Ten to the thirtieth: the first count with more digits than any token count has.
_PAST_ANY_COUNT = 1_000_000_000_000_000_000_000_000_000_000
# A Codex write split in full, and one of its lifetimes alone, each past what the input holds beside its cache reads.
_HELD_LIFETIMES = (
    ("whole split", {"cache_write_5m": _CODEX_CACHED, "cache_write_1h": _CODEX_CACHED}),
    ("one lifetime so far", {"cache_write_5m": _CODEX_INPUT - _CODEX_CACHED + 1}),
)
# One past the largest integer every float holds exactly.
_PAST_FLOAT_PRECISION = 9_007_199_254_740_993


def _readings(**counts: int) -> MappingProxyType:
    readings = {counter: _Reading.of(count) for counter, count in counts.items()}
    return MappingProxyType(readings)


def _agy(**overrides: int) -> MappingProxyType:
    counts = {
        normalization.INPUT: _AGY_INPUT,
        normalization.CACHE_READ: _AGY_CACHE_READ,
        normalization.OUTPUT: _AGY_OUTPUT,
        normalization.REASONING: 0,
        normalization.SOURCE_TOTAL: _AGY_SOURCE_TOTAL,
        **overrides,
    }
    return _readings(**counts)


def _claude(**counts: int) -> MappingProxyType:
    ordinary = {normalization.INPUT: _CLAUDE_INPUT, normalization.OUTPUT: _CLAUDE_OUTPUT}
    return _readings(cache_read=_CLAUDE_CACHE_READ, **ordinary, **counts)


def _split() -> dict:
    return {
        normalization.CACHE_WRITE_FIVE_MIN: _CLAUDE_WRITE_FIVE_MIN,
        normalization.CACHE_WRITE_ONE_HOUR: _CLAUDE_WRITE_ONE_HOUR,
    }


def _evidence(provider: str, readings: MappingProxyType, names: Iterable[str]) -> dict[str, str]:
    """The evidence `readings` normalize to under `provider`, for each field named."""
    fields = normalization.normalize(provider, readings).fields
    return {name: fields[name].state for name in names}


# A source total beside a part it sums that is missing, with the total's evidence and that of the field the missing
# part leaves unknown: the parts that are known still bound the total from below.
_TOTALS_BESIDE_A_MISSING_PART = (
    (
        "below the output alone",
        protocol.AGY,
        _readings(output=2, source_total=1),
        MappingProxyType({_SOURCE_TOTAL: _CONFLICTING, _CONTEXT: _MISSING}),
    ),
    (
        "within what the output allows",
        protocol.AGY,
        _readings(output=2, source_total=5),
        MappingProxyType({_SOURCE_TOTAL: _OBSERVED, _CONTEXT: _MISSING}),
    ),
    (
        "below the input alone",
        protocol.CODEX,
        _readings(input=_CODEX_INPUT, source_total=_CODEX_INPUT - 1),
        MappingProxyType({_SOURCE_TOTAL: _CONFLICTING, _OUTPUT: _MISSING}),
    ),
)


class ProfileSemanticsTest(unittest.TestCase):
    """Each provider's input is read for what it holds, so the context input means one thing for all three."""

    def test_antigravity_input_adds_its_cache_reads(self) -> None:
        usage = normalization.normalize(protocol.AGY, _agy())
        self.assertEqual(usage.to_dict(), {
            _CONTEXT: _AGY_CONTEXT,
            _OUTPUT: _AGY_OUTPUT,
            _CACHE_READ: _AGY_CACHE_READ,
            _REASONING: 0,
            _TOTAL: _AGY_CONTEXT + _AGY_OUTPUT,
            _SOURCE_TOTAL: _AGY_SOURCE_TOTAL,
            normalization.OVERLAP: "input-excludes-cache-reads",
            _EVIDENCE: {
                _CONTEXT: _OBSERVED,
                _OUTPUT: _OBSERVED,
                _CACHE_READ: _OBSERVED,
                _CACHE_WRITE: _UNSUPPORTED,
                _REASONING: _OBSERVED,
                _TOTAL: _OBSERVED,
                _SOURCE_TOTAL: _OBSERVED,
                _LIFETIMES: _UNSUPPORTED,
            },
        })

    def test_codex_input_holds_its_cache_reads(self) -> None:
        usage = normalization.normalize(protocol.CODEX, _readings(
            input=_CODEX_INPUT,
            cache_read=_CODEX_CACHED,
            output=_CODEX_OUTPUT,
            reasoning=_CODEX_REASONING,
            source_total=_CODEX_INPUT + _CODEX_OUTPUT,
        ))
        self.assertEqual(
            [usage.count(field) for field in (_CONTEXT, _CACHE_READ, _REASONING, _TOTAL, _SOURCE_TOTAL)],
            [_CODEX_INPUT, _CODEX_CACHED, _CODEX_REASONING, _CODEX_INPUT + _CODEX_OUTPUT, _CODEX_INPUT + _CODEX_OUTPUT],
        )
        self.assertEqual(usage.overlap, "input-includes-cache")
        # Codex can report cache writes, so one it left out is missing rather than unsupported.
        self.assertEqual(usage.fields[_CACHE_WRITE].state, _MISSING)

    def test_claude_counts_each_cache_write_once(self) -> None:
        cases = (
            ("aggregate and split", _claude(cache_write=_CLAUDE_WRITE, **_split()), _OBSERVED),
            ("split alone", _claude(**_split()), _OBSERVED),
            ("aggregate alone", _claude(cache_write=_CLAUDE_WRITE), _MISSING),
        )
        for name, readings, lifetime_state in cases:
            with self.subTest(name):
                usage = normalization.normalize(protocol.CLAUDE, readings)
                self.assertEqual(usage.count(_CACHE_WRITE), _CLAUDE_WRITE)
                self.assertEqual(usage.count(_CONTEXT), _CLAUDE_CONTEXT)
                self.assertEqual(usage.count(_TOTAL), _CLAUDE_CONTEXT + _CLAUDE_OUTPUT)
                self.assertEqual(
                    (usage.lifetimes_state, usage.fields[_REASONING].state), (lifetime_state, _UNSUPPORTED),
                )
        self.assertEqual(
            normalization.normalize(protocol.CLAUDE, cases[0][1]).to_dict()[_LIFETIMES],
            _split(),
        )

    def test_totals_are_held_to_their_known_parts(self) -> None:
        # Where a profile's total sums counters, one smaller than those of them that are known contradicts them, another
        # part missing or not; the part left out stays missing either way, never established by the total.
        for name, provider, readings, states in _TOTALS_BESIDE_A_MISSING_PART:
            with self.subTest(name):
                self.assertEqual(_evidence(provider, readings, states), dict(states))

    def test_contradicted_split_leaves_writes_unknown(self) -> None:
        readings = _claude(cache_write=_CLAUDE_WRITE, **{**_split(), normalization.CACHE_WRITE_ONE_HOUR: 1})
        usage = normalization.normalize(protocol.CLAUDE, readings)
        evidence = usage.to_dict()[_EVIDENCE]
        for field in (_CACHE_WRITE, _LIFETIMES, _CONTEXT, _TOTAL):
            with self.subTest(field=field):
                self.assertEqual(evidence[field], _CONFLICTING)
        self.assertNotIn(_CONTEXT, usage.to_dict())
        self.assertEqual(usage.count(_OUTPUT), _CLAUDE_OUTPUT)


class EvidenceTest(unittest.TestCase):
    """Missing is never zero, and nothing invalid or contradictory adds up to a count."""

    def test_missing_cache_reads_are_not_zero(self) -> None:
        # A step that left its cache reads out establishes no context input; one reporting zero does.
        missing = normalization.normalize(protocol.AGY, _readings(input=_AGY_INPUT, output=_AGY_OUTPUT))
        zero = normalization.normalize(protocol.AGY, _agy(cache_read=0))
        established = set(missing.to_dict())
        self.assertFalse(established & {_CONTEXT, _TOTAL})
        self.assertEqual(missing.fields[_CONTEXT].state, _MISSING)
        zero_counts = [zero.count(_CONTEXT), zero.count(_TOTAL)]
        self.assertEqual(zero_counts, [_AGY_INPUT, _AGY_INPUT + _AGY_OUTPUT])

    def test_contradictions_leave_the_rest_known(self) -> None:
        cases = (
            ("reasoning beyond its output", _agy(reasoning=_AGY_OUTPUT + 1), _REASONING),
            ("source total beyond its parts", _agy(source_total=_AGY_SOURCE_TOTAL + 1), _SOURCE_TOTAL),
        )
        for name, readings, field in cases:
            with self.subTest(name):
                usage = normalization.normalize(protocol.AGY, readings)
                self.assertEqual(usage.fields[field].state, _CONFLICTING)
                self.assertIsNone(usage.count(field))
                self.assertEqual(usage.count(_CONTEXT), _AGY_CONTEXT)

    def test_parts_past_their_whole_conflict(self) -> None:
        past_input = _readings(input=_CODEX_CACHED, cache_read=_CODEX_INPUT, output=_CODEX_OUTPUT)
        cached = normalization.normalize(protocol.CODEX, past_input)
        self.assertEqual(cached.fields[_CACHE_READ].state, _CONFLICTING)
        lifetime = {normalization.CACHE_WRITE_FIVE_MIN: _CLAUDE_WRITE + 1}
        written = normalization.normalize(protocol.CLAUDE, _claude(cache_write=_CLAUDE_WRITE, **lifetime))
        self.assertEqual(written.fields[_CACHE_WRITE].state, _CONFLICTING)
        self.assertEqual(written.lifetimes_state, _CONFLICTING)

    def test_cache_parts_the_input_holds_add_up(self) -> None:
        # Codex's input holds its cache reads and writes at once, so each fitting alone is not enough.
        within = _readings(input=_CODEX_INPUT, cache_read=_CODEX_CACHED, output=_CODEX_OUTPUT)
        fitting_write = {normalization.CACHE_WRITE: _Reading.of(_CODEX_INPUT - _CODEX_CACHED)}
        past_write = {normalization.CACHE_WRITE: _Reading.of(_CODEX_CACHED)}
        fitting = normalization.normalize(protocol.CODEX, {**within, **fitting_write})
        past = normalization.normalize(protocol.CODEX, {**within, **past_write})
        self.assertNotIn(_CONFLICTING, fitting.states())
        self.assertEqual(past.fields[_CACHE_READ].state, _CONFLICTING)
        self.assertEqual(past.fields[_CACHE_WRITE].state, _CONFLICTING)
        self.assertEqual(past.count(_CONTEXT), _CODEX_INPUT)

    def test_derived_cache_writes_are_held_too(self) -> None:
        # Writes settled from their lifetime split are held to the input like reported ones, and so is the part of
        # them a lifetime reported so far: a lower bound already past the input contradicts it.
        for name, lifetimes in _HELD_LIFETIMES:
            with self.subTest(name):
                readings = _readings(input=_CODEX_INPUT, cache_read=_CODEX_CACHED, **lifetimes)
                usage = normalization.normalize(protocol.CODEX, readings)
                self.assertEqual(usage.fields[_CACHE_WRITE].state, _CONFLICTING)
                self.assertEqual(usage.fields[_CACHE_READ].state, _CONFLICTING)
                self.assertEqual(usage.lifetimes_state, _CONFLICTING)

    def test_values_read_as_the_run_accounting_does(self) -> None:
        cases = (
            (None, None, _MISSING),
            (0, 0, _OBSERVED),
            ("10", 10, _OBSERVED),
            (float(10), 10, _OBSERVED),
            (-1, -1, _INVALID),
            # A value no count is: judged before it is truncated, never read as the count truncating it makes.
            (-0.5, None, _INVALID),
            (10.5, None, _INVALID),
            ("10.5", None, _INVALID),
            # A string is read exactly: no float rounds a fraction whole or moves a count past 2**53.
            ("1.0000000000000001", None, _INVALID),
            ("9007199254740993", _PAST_FLOAT_PRECISION, _OBSERVED),
            ("1e3", 1000, _OBSERVED),
            ("1e40", None, _INVALID),
            # A count with more digits than any token count has is none, reported as a number or spelled.
            (_PAST_ANY_COUNT, None, _INVALID),
            (str(_PAST_ANY_COUNT), None, _INVALID),
            # Thirty digits is still a count; the first number past it is ten to the thirtieth, above.
            (_PAST_ANY_COUNT - 1, _PAST_ANY_COUNT - 1, _OBSERVED),
            (str(_PAST_ANY_COUNT - 1), _PAST_ANY_COUNT - 1, _OBSERVED),
            (float("inf"), None, _INVALID),
            # A number literal a decoder kept exact is judged as the number it spells, not the float nearest it.
            (Decimal("2.0"), 2, _OBSERVED),
            (Decimal("1E+3"), 1000, _OBSERVED),
            (Decimal("1E-400"), None, _INVALID),
            (Decimal("1.0000000000000000001"), None, _INVALID),
            (Decimal("-2.0"), -2, _INVALID),
            (Decimal("1E+40"), None, _INVALID),
            (Decimal("NaN"), None, _INVALID),
            (True, None, _INVALID),
            ("ten", None, _INVALID),
            ({}, None, _INVALID),
        )
        for raw, count, state in cases:
            with self.subTest(raw=raw):
                self.assertEqual(_Reading.of(raw), _Reading(count, state))

    def test_derived_fields_take_the_weakest_part(self) -> None:
        observed = _Reading(1, _OBSERVED)
        parts = (observed, _Reading(state=_MISSING), _Reading(state=_INVALID))
        self.assertEqual(_Reading.summed(parts), _Reading(state=_INVALID))
        contradicted = (*parts, _Reading(state=_CONFLICTING))
        self.assertEqual(_Reading.summed(contradicted).state, _CONFLICTING)
        fields = normalization.normalize(protocol.AGY, _agy(input=-1)).fields
        states = {fields[field].state for field in (_CONTEXT, _TOTAL)}
        self.assertEqual(states, {_INVALID})
