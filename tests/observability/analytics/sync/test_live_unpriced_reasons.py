# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Why unpriced runs have no amount, as a real Postgres counts and lists them from the records the sync replayed.

The hermetic tests hold the reason count to the fragments it selects; only a real database can say what its JSON
reads, lateral joins, and distinct counts answer. The runs replayed here are the observed GPT-6 Astra selection --
eight runs, each giving both reasons, one repeating an entry -- beside a run an earlier build recorded without
reasons, a run giving one reason on each of two models, a run holding only entries the vocabulary does not write and
naming no model, a CLI-reported run carrying reasons it was never given, and a run with no cost evidence at all.
"""
from __future__ import annotations

import unittest
from types import MappingProxyType

from orchestrator.observability.analytics.query import breakdown_reads, raw_reads
from orchestrator.observability.analytics.query.cost_models import UnpricedReasonRow
from orchestrator.observability.analytics.sync import run
from orchestrator.observability.usage import unpriced as usage_unpriced
from tests.observability.analytics import analytics_usage_cases as cases
from tests.observability.analytics.sync import live_evidence_support as live
from tests.observability.analytics.sync.sync_test_support import jsonl_log

_ISSUE = 22

_ASTRA = "gpt-6-astra"

_OPUS = "claude-opus-4-7"

_UNKNOWN_MODEL = "third-party-model-x"

_ASTRA_RUNS = 8

_ASTRA_TIER = MappingProxyType({
    usage_unpriced.MODEL: _ASTRA,
    usage_unpriced.REASON: usage_unpriced.INDETERMINATE_REQUEST_TIER,
})

_ASTRA_COUNT = MappingProxyType({**_ASTRA_TIER, usage_unpriced.REASON: usage_unpriced.MISSING_CACHE_WRITE_COUNT})

_OPUS_LIFETIME = MappingProxyType({
    usage_unpriced.MODEL: _OPUS,
    usage_unpriced.REASON: usage_unpriced.MISSING_CACHE_WRITE_LIFETIME,
})

_UNKNOWN_PRICE = MappingProxyType({
    usage_unpriced.MODEL: _UNKNOWN_MODEL,
    usage_unpriced.REASON: usage_unpriced.MISSING_MODEL_PRICE,
})

_BOTH = (_ASTRA_TIER, _ASTRA_COUNT)

# What each observed run's record gives, the last repeating an entry.
_ASTRA_GIVEN = (*(_BOTH,) * (_ASTRA_RUNS - 1), (*_BOTH, _ASTRA_TIER))

# The observed runs, each told apart by its session so none is a replay of another.
_ASTRA_RECORDS = tuple(
    cases.usage_record(
        _ISSUE,
        cases.UNPRICED,
        cases.WITHIN_INPUT,
        models=[_ASTRA],
        session_id=f"astra-{position}",
        unpriced_reasons=list(map(dict, given)),
    )
    for position, given in enumerate(_ASTRA_GIVEN)
)

_BESIDE_RECORDS = (
    cases.usage_record(_ISSUE, cases.UNPRICED, cases.WITHIN_INPUT, models=[_ASTRA], session_id="earlier"),
    cases.usage_record(
        _ISSUE,
        cases.UNPRICED,
        cases.DISJOINT,
        models=[_OPUS, _UNKNOWN_MODEL],
        unpriced_reasons=[dict(_OPUS_LIFETIME), dict(_UNKNOWN_PRICE)],
    ),
    cases.usage_record(
        _ISSUE,
        cases.UNPRICED,
        cases.UNSETTLED,
        models=[],
        unpriced_reasons=[{**_UNKNOWN_PRICE, usage_unpriced.MODEL: ""}, usage_unpriced.SUBAGENT_USAGE],
    ),
    cases.usage_record(
        _ISSUE,
        cases.REPORTED,
        cases.WITHIN_INPUT,
        models=[_ASTRA],
        unpriced_reasons=[dict(_ASTRA_TIER)],
    ),
    cases.unevidenced_record(_ISSUE, models=[_ASTRA]),
)

_RECORDS = (*_ASTRA_RECORDS, *_BESIDE_RECORDS)

# What the count answers, in the order SQL ranks it: the most affected first, then by model, a missing reason last.
_COUNTED = (
    UnpricedReasonRow(_ASTRA, usage_unpriced.INDETERMINATE_REQUEST_TIER, _ASTRA_RUNS),
    UnpricedReasonRow(_ASTRA, usage_unpriced.MISSING_CACHE_WRITE_COUNT, _ASTRA_RUNS),
    UnpricedReasonRow(_OPUS, usage_unpriced.MISSING_CACHE_WRITE_LIFETIME, 1),
    UnpricedReasonRow(_ASTRA, None, 1),
    UnpricedReasonRow(_UNKNOWN_MODEL, usage_unpriced.MISSING_MODEL_PRICE, 1),
    UnpricedReasonRow("unknown", None, 1),
)

# How many reasons each listed run reads back, whatever its cost: none for the run recorded without them, the run of
# unwritten entries, and the run with no evidence; one for the CLI-reported run; two for every other.
_LISTED = (0, 0, 0, 1, *(2,) * (_ASTRA_RUNS + 1))


class LiveUnpricedReasonsTest(unittest.TestCase):
    """Opted into with `ANALYTICS_TEST_DB_URL=<libpq URL>` naming a disposable database."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.database = live.LiveDatabase.from_environment()

    def setUp(self) -> None:
        self.database.reset()
        with jsonl_log(list(_RECORDS)) as path:
            run.sync_jsonl_to_postgres(log_path=path, db_url=self.database.db_url)

    def test_runs_are_counted_and_listed_by_reason(self) -> None:
        # A run counts under each pair its record gives, a run recorded without
        # reasons counts under each model it names with none, and neither a
        # CLI-reported run nor one with no evidence is counted; each listed
        # run reads back its own reasons off the same JSONB cell.
        db_url = self.database.db_url
        counted = breakdown_reads.get_unpriced_reasons(db_url=db_url, issue=_ISSUE)
        self.assertEqual(counted, list(_COUNTED))
        listed = raw_reads.get_recent_agent_exits(db_url=db_url, issue=_ISSUE, limit=len(_RECORDS))
        held = sorted(len(exit_row.unpriced_reasons) for exit_row in listed)
        self.assertEqual(tuple(held), _LISTED)


if __name__ == "__main__":
    unittest.main()
