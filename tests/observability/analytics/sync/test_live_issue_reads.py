# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""How the issue ranking orders real rows, and what a run's details read back, against a real Postgres.

The hermetic tests hold the issues read to an `ORDER BY` that runs ahead of its `LIMIT`; only a real database can say
what that ordering does. The issues here are spread over a month so that the costliest is the oldest and the newest
states no amount at all: a cost ranking cut to one row still finds the oldest, two issues stating the same amount on
different bases tie exactly and fall back to the newer one, two equal at the same instant fall back to the pair naming
them, a subtotal ranks at its known part, an amount an earlier build stored with no basis at its stated figure, a
complete zero above every issue stating nothing, and the issues stating nothing last. The dashboard draws those rows
where SQL put them -- a tie between two repositories whose names a punctuation-skipping collation orders differently
from Python's code points included. The recent-runs and trace reads then hand each run back with the evidence its
record stated -- a CLI-reported amount as reported, an estimate with its rate dates -- never re-priced.
"""
from __future__ import annotations

import unittest
from operator import itemgetter

from orchestrator.observability.analytics.query import issue_summaries, raw_reads
from orchestrator.observability.analytics.sync import run
from orchestrator.observability.dashboard import kpis
from orchestrator.observability.usage import cost_evidence as usage_cost, token_evidence as usage_tokens
from tests.observability.analytics import analytics_usage_cases as cases
from tests.observability.analytics.sync import live_evidence_support as live
from tests.observability.analytics.sync.sync_test_support import jsonl_log

_OTHER_REPO = "owner/a-repo"

_COSTLIEST = 41

_EARLIER_TIE = 43

_LATER_TIE = 44

_PAIR_TIE = 45

_FIRST_SUBTOTAL = 46

_SECOND_SUBTOTAL = 47

_MISSING_BASIS = 48

_UNPRICED = 49

_NO_USAGE = 50

_COMPLETE_ZERO = 51

_COLLATED_TIE = 61

# Two issues tying on amount and activity whose repositories the `postgres:16` image's default `en_US.utf8` collation
# orders by their letters, skipping the dot -- `owner/ab` first -- where Python's code-point order puts `owner/a.c`
# first. They are replayed on their own, so the full ranking above stays collation-independent.
_COLLATED_RECORDS = tuple(
    cases.usage_record(_COLLATED_TIE, cases.REPORTED, cases.DISJOINT, ts="2026-10-02T09:00:00+00:00", repo=repo)
    for repo in ("owner/ab", "owner/a.c")
)

# A CLI-reported amount that, beside an OpenAI estimate, adds up to exactly an Anthropic estimate's amount.
_REPORTED_PART = cases.cost(
    usage_cost.COMPLETE,
    cases.contribution(usage_cost.CLI_REPORTED, cases.BLENDED_OPENAI_USD),
)

_LATER_TIE_RUNS = (
    cases.usage_record(_LATER_TIE, cases.OPENAI_ESTIMATE, cases.WITHIN_INPUT, ts="2026-10-15T09:00:00+00:00"),
    cases.usage_record(_LATER_TIE, _REPORTED_PART, cases.DISJOINT, ts="2026-10-15T08:00:00+00:00"),
)

# What each of those runs stated, in the newest-first order the recent-runs read lists them.
_LATER_TIE_COSTS = tuple(map(usage_cost.recorded_cost, _LATER_TIE_RUNS))

_LATER_TIE_TOKENS = tuple(map(usage_tokens.non_overlapping_total, _LATER_TIE_RUNS))

_RECORDS = (
    cases.usage_record(_COSTLIEST, cases.REPORTED, cases.DISJOINT, ts="2026-10-01T09:00:00+00:00"),
    cases.usage_record(_EARLIER_TIE, cases.ANTHROPIC_ESTIMATE, cases.DISJOINT, ts="2026-10-10T09:00:00+00:00"),
    *_LATER_TIE_RUNS,
    cases.usage_record(_PAIR_TIE, cases.GEMINI_ESTIMATE, cases.UNSETTLED, ts="2026-10-05T09:00:00+00:00"),
    cases.usage_record(
        _PAIR_TIE, cases.GEMINI_ESTIMATE, cases.UNSETTLED, ts="2026-10-05T09:00:00+00:00", repo=_OTHER_REPO,
    ),
    cases.usage_record(_FIRST_SUBTOTAL, cases.INCOMPLETE_SUBTOTAL, cases.DISJOINT, ts="2026-10-06T09:00:00+00:00"),
    cases.usage_record(_SECOND_SUBTOTAL, cases.INCOMPLETE_SUBTOTAL, cases.DISJOINT, ts="2026-10-06T09:00:00+00:00"),
    cases.unevidenced_record(_MISSING_BASIS, cost_usd=cases.LEGACY_USD, ts="2026-10-07T09:00:00+00:00"),
    cases.usage_record(_UNPRICED, cases.UNPRICED, cases.DISJOINT, ts="2026-10-29T09:00:00+00:00"),
    cases.usage_record(_NO_USAGE, cases.NO_USAGE, cases.NOTHING_OBSERVED, ts="2026-10-28T09:00:00+00:00"),
    cases.usage_record(_COMPLETE_ZERO, cases.COMPLETE_ZERO, cases.DISJOINT, ts="2026-10-27T09:00:00+00:00"),
    # A stage row states no usage: it moves no issue's ranking and is traced with no cost.
    {**cases.stage_record(_LATER_TIE), "ts": "2026-10-15T10:00:00+00:00"},
)

# The cost order, each issue beside the amount it ranks on: the two equal amounts on different bases newest first, the
# two at the same instant by the pair, and the two stating nothing last, newest first.
_RANKED = (
    ((cases.REPO, _COSTLIEST), cases.REPORTED_USD),
    ((cases.REPO, _LATER_TIE), cases.ANTHROPIC_USD),
    ((cases.REPO, _EARLIER_TIE), cases.ANTHROPIC_USD),
    ((cases.REPO, _FIRST_SUBTOTAL), cases.SUBTOTAL_USD),
    ((cases.REPO, _SECOND_SUBTOTAL), cases.SUBTOTAL_USD),
    ((_OTHER_REPO, _PAIR_TIE), cases.GEMINI_USD),
    ((cases.REPO, _PAIR_TIE), cases.GEMINI_USD),
    ((cases.REPO, _MISSING_BASIS), cases.LEGACY_USD),
    ((cases.REPO, _COMPLETE_ZERO), 0),
    ((cases.REPO, _UNPRICED), None),
    ((cases.REPO, _NO_USAGE), None),
)


_RUN_RECORDS = tuple(record for record in _RECORDS if record["event"] == cases.AGENT_EXIT)


_ISSUE_PAIR = itemgetter("repo", "issue")


def _runs_of(pair: tuple[str, int]) -> tuple[dict, ...]:
    """The `agent_exit` records one `(repo, issue)` pair holds."""
    return tuple(record for record in _RUN_RECORDS if _ISSUE_PAIR(record) == pair)


def _rounded(part: usage_cost.CostContribution) -> tuple:
    """One contribution with its amount rounded past the float noise a NUMERIC sum and a Python sum differ by."""
    amount = round(part.amount_usd, 9)
    return part.basis, amount, part.rates_verified_on


def _answer(row) -> tuple:
    """An issue row in the shape `folded_answer` reads its records in."""
    evidence = row.cost.evidence
    parts = tuple(map(_rounded, evidence.contributions))
    tokens = (row.total_tokens, row.unknown_token_runs)
    return row.cost.runs, (evidence.completeness, parts), tokens


class LiveIssueReadsTest(unittest.TestCase):
    """Opted into with `ANALYTICS_TEST_DB_URL=<libpq URL>` naming a disposable database."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.database = live.LiveDatabase.from_environment()

    def setUp(self) -> None:
        self.database.reset()
        with jsonl_log(list(_RECORDS)) as path:
            run.sync_jsonl_to_postgres(log_path=path, db_url=self.database.db_url)

    def test_the_cost_ranking_orders_before_its_cap(self) -> None:
        ranked = self._issues(limit=len(_RANKED) + 1)
        self.assertEqual(
            [((row.repo, row.issue), row.stated_cost_usd) for row in ranked],
            list(_RANKED),
        )
        # The dashboard draws the rows in SQL's order, ties included.
        self.assertEqual(kpis.top_expensive_issues(ranked, limit=len(ranked)), ranked)
        # Cut to one row, the cost ranking still finds the oldest issue, which
        # a ranking applied after a recency-bounded cap would have dropped.
        cut = self._issues(limit=1)
        self.assertEqual([row.issue for row in cut], [_COSTLIEST])
        newest = raw_reads.get_issues(db_url=self.database.db_url, limit=1)
        self.assertEqual([row.issue for row in newest], [_UNPRICED])

    def test_a_collated_tie_is_drawn_as_ranked(self) -> None:
        with jsonl_log(list(_COLLATED_RECORDS)) as path:
            run.sync_jsonl_to_postgres(log_path=path, db_url=self.database.db_url)
        ranked = raw_reads.get_issues(
            db_url=self.database.db_url, issue=_COLLATED_TIE, sort_by=issue_summaries.SORT_BY_COST,
        )
        self.assertEqual(len(ranked), len(_COLLATED_RECORDS))
        drawn = kpis.top_expensive_issues(ranked)
        self.assertEqual([row.repo for row in drawn], [row.repo for row in ranked])

    def test_each_issue_carries_its_runs_fold(self) -> None:
        ranked = self._issues(limit=len(_RANKED))
        by_issue = {(row.repo, row.issue): row for row in ranked}
        for pair, _amount in _RANKED:
            with self.subTest(issue=pair):
                folded = live.folded_answer(_runs_of(pair))
                self.assertEqual(_answer(by_issue[pair]), folded)

    def test_a_run_keeps_the_cost_its_record_stated(self) -> None:
        runs = raw_reads.get_recent_agent_exits(db_url=self.database.db_url, issue=_LATER_TIE, repo=cases.REPO)
        self.assertEqual(tuple(run_row.cost for run_row in runs), _LATER_TIE_COSTS)
        self.assertEqual(tuple(run_row.total_tokens for run_row in runs), _LATER_TIE_TOKENS)
        trace = raw_reads.get_issue_events(db_url=self.database.db_url, issue=_LATER_TIE, repo=cases.REPO)
        self.assertEqual(
            [(event.event, event.cost) for event in trace],
            [
                (cases.AGENT_EXIT, _REPORTED_PART),
                (cases.AGENT_EXIT, cases.OPENAI_ESTIMATE),
                ("stage_enter", None),
            ],
        )
        legacy = raw_reads.get_recent_agent_exits(db_url=self.database.db_url, issue=_MISSING_BASIS, repo=cases.REPO)
        self.assertEqual([run_row.cost for run_row in legacy], [cases.ABSENT_BASIS])

    def _issues(self, *, limit: int) -> list:
        return raw_reads.get_issues(db_url=self.database.db_url, limit=limit, sort_by=issue_summaries.SORT_BY_COST)


if __name__ == "__main__":
    unittest.main()
