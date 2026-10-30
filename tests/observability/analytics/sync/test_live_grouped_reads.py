# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What the stage, backend, repository, and review-round reads fold real runs to, against a real Postgres.

The hermetic tests hold each grouped read to the fragments it selects; only a real database can say what those
fragments sum to. The runs replayed here are the reported-only, AGY-only, mixed-provider, incomplete, and
missing-basis cohorts spread across groups, so each read's cohort for a group has to equal the Python fold of that
group's records -- each basis's amount and rate dates apart, the weakest completeness, a subtotal and an amount with
no basis kept as such -- its tokens the declared non-overlapping totals with a Codex run's cached input counted once,
and its token-share bands the per-run split of each stated amount, adding back up to that amount with the amount of
runs whose total is unknown left unsplit.
"""
from __future__ import annotations

import unittest
from dataclasses import dataclass
from operator import itemgetter

from orchestrator.observability.analytics.query import breakdown_reads, cost_cohorts, rollup_reads
from orchestrator.observability.analytics.query.cache_shares import TokenShareBands
from orchestrator.observability.analytics.sync import run
from tests.observability.analytics.sync import live_evidence_support as live, live_grouped_support as grouped
from tests.observability.analytics.sync.sync_test_support import jsonl_log

# The two roles a review round files its runs under.
_REVIEWED_ROLES = frozenset((grouped.DEVELOPER, grouped.REVIEWER))


@dataclass(frozen=True)
class _RoleRead:
    """One role's cohort and bands in one round, keyed as the Python grouping keys its runs."""

    key: tuple[str, str]
    cost: cost_cohorts.CostCohort
    bands: TokenShareBands


def _role_reads(rounds) -> list[_RoleRead]:
    return [
        _RoleRead((row.bucket, role), cost, bands)
        for row in rounds
        for role, cost, bands in (
            (grouped.DEVELOPER, row.developer_cost, row.developer_bands),
            (grouped.REVIEWER, row.reviewer_cost, row.reviewer_bands),
        )
    ]


def _round_key(record: dict) -> tuple[str, str]:
    return grouped.review_bucket(record), record["agent_role"]


def _assert_cohort(test_case: unittest.TestCase, cost: cost_cohorts.CostCohort, records: tuple) -> None:
    """A read's cohort is what the Python readers fold its group's records to."""
    folded = live.folded_answer(records)
    test_case.assertEqual(grouped.cohort_answer(cost), folded[:2])


def _assert_bands(test_case: unittest.TestCase, bands: TokenShareBands, records: tuple, cost) -> None:
    """The bands are the per-run split of the stated amounts, and add back up to what the group states."""
    read = (bands.cache_usd, bands.no_cache_usd, bands.unsplit_usd)
    for band, expected in zip(read, grouped.token_share_answer(records), strict=True):
        test_case.assertAlmostEqual(band, expected, places=9)
    test_case.assertAlmostEqual(sum(read), cost.evidence.total_usd or 0, places=9)


class LiveGroupedReadsTest(unittest.TestCase):
    """Opted into with `ANALYTICS_TEST_DB_URL=<libpq URL>` naming a disposable database."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.database = live.LiveDatabase.from_environment()

    def setUp(self) -> None:
        self.database.reset()
        with jsonl_log(list(grouped.RECORDS)) as path:
            run.sync_jsonl_to_postgres(log_path=path, db_url=self.database.db_url)

    def test_each_stage_folds_its_runs(self) -> None:
        stages = {row.stage: row for row in rollup_reads.get_stage_breakdown(db_url=self.database.db_url)}
        for stage, records in grouped.grouped(itemgetter(grouped.STAGE)).items():
            row = stages[stage]
            with self.subTest(stage=stage):
                _assert_cohort(self, row.cost, records)
                self.assertEqual(row.runs, len(records))
                known = grouped.declared_tokens(records)[:2]
                self.assertEqual((row.total_tokens, row.unknown_token_runs), known)
                _assert_bands(self, row.bands, records, row.cost)
        # A stage row is an event of its stage, never a run of it.
        self.assertEqual(stages[grouped.IMPLEMENTING].count, 2)

    def test_each_backend_counts_declared_tokens(self) -> None:
        backends = rollup_reads.get_backend_efficiency(db_url=self.database.db_url)
        expected = grouped.grouped(lambda record: record.get("backend") or "unknown")
        self.assertEqual({row.backend for row in backends}, set(expected))
        for row in backends:
            records = expected[row.backend]
            with self.subTest(backend=row.backend):
                _assert_cohort(self, row.cost, records)
                tokens = (row.total_tokens, row.unknown_token_runs, row.cache_tokens, row.output_tokens)
                self.assertEqual(tokens, grouped.declared_tokens(records))

    def test_each_repository_folds_its_runs(self) -> None:
        repos = rollup_reads.get_repo_breakdown(db_url=self.database.db_url)
        expected = grouped.grouped(itemgetter("repo"))
        self.assertEqual({row.repo for row in repos}, set(expected))
        for row in repos:
            records = expected[row.repo]
            with self.subTest(repo=row.repo):
                _assert_cohort(self, row.cost, records)
                self.assertEqual(row.agent_exits, len(records))

    def test_each_round_role_folds_its_runs(self) -> None:
        # Only development and review runs are filed under a round, each role's
        # apart; a role with no run in a round reads as the empty cohort.
        reads = _role_reads(breakdown_reads.get_review_round_breakdown(db_url=self.database.db_url))
        expected = grouped.grouped(
            _round_key,
            (record for record in grouped.RUNS if record["agent_role"] in _REVIEWED_ROLES),
        )
        drawn = {read.key for read in reads if not read.cost.is_empty}
        self.assertEqual(drawn, set(expected))
        for role_read in reads:
            records = expected.get(role_read.key, ())
            with self.subTest(round_role=role_read.key):
                _assert_cohort(self, role_read.cost, records)
                _assert_bands(self, role_read.bands, records, role_read.cost)

    def test_a_round_folds_both_roles(self) -> None:
        for row in breakdown_reads.get_review_round_breakdown(db_url=self.database.db_url):
            records = tuple(
                record for record in grouped.RUNS if _round_key(record) in {
                    (row.bucket, grouped.DEVELOPER), (row.bucket, grouped.REVIEWER),
                }
            )
            with self.subTest(bucket=row.bucket):
                _assert_cohort(self, row.cost, records)


if __name__ == "__main__":
    unittest.main()
