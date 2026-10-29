# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What an agent run leaves durable whatever its stage makes of it: its launch's charge, and its accounting.

A held return -- a live pause, a shutdown kill, an accounting left unresolved
-- disposes of nothing, so the record it leaves differs from the one the run
was launched over only in the fields of those two writes, and its accounting
counts each invoked exit exactly once. Measured from the record as the process
was invoked (`RecordsTheLaunch`), the charge is already down, and only the
accounting may move.
"""
from __future__ import annotations

import unittest
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any

from orchestrator.github.pinned_state import SCHEMA_VERSION_KEY
from tests.workflow import state_values as _state_values

# Every field a held return may leave moved: the charge's and the accounting's,
# and the version a record the charge pinned first is stamped with.
_PERMITTED = _state_values.AGENT_RUN_CHARGE_KEYS | _state_values.AGENT_RUN_ACCOUNTING_KEYS | {SCHEMA_VERSION_KEY}

# What a validating tick records ahead of its reviewer's spawn, which no return
# writes either: the report the pull request carries, settled, and the launch's
# spec and subject.
REVIEWER_LAUNCH_KEYS = (
    "developer_report_current",
    "developer_report_handoff",
    "review_agent",
    "review_subject",
)

_RUNS = "issue_agent_runs"
_RECEIPTS = "issue_usage_receipts"
_RECENT = "recent"

# What a field the record does not carry reads as, apart from one it carries as `null`.
_UNSET = object()

# One pinned record, as its client reads it back.
_Record = Mapping[str, Any]


def assert_only_accounted(
    test_case: unittest.TestCase,
    before: Mapping[str, Any],
    after: Mapping[str, Any],
    *,
    runs: int = 1,
    beside: Iterable[str] = (),
) -> None:
    """`after` is `before` with only the charge and `runs` accounted exits moved: each counted once, receipted once.

    `beside` names the fields a write of the stage's own ahead of the spawn
    moved -- a reviewer's launch record -- which no return wrote either.
    """
    test_case.assertLessEqual(
        moved(before, after), _PERMITTED.union(beside), "a held return moved more than its charge and accounting",
    )
    counted, receipted = accounted(after)
    counted_before, receipted_before = accounted(before)
    test_case.assertEqual(
        (counted - counted_before, receipted - receipted_before),
        (runs, runs),
        "a held return's exits are each counted and receipted once",
    )


@dataclass(frozen=True)
class Launched:
    """One issue's pinned record, and the pinned writes its client had taken, as a run was launched over them."""

    record: Mapping[str, Any]
    writes: int

    @classmethod
    def over(cls, github, issue_number: int) -> Launched:
        """The record `issue_number` carries on `github` now, and the writes taken so far."""
        return cls(github.pinned_data(issue_number), github.write_state_calls)

    def held(
        self,
        test_case: unittest.TestCase,
        github,
        issue_number: int,
        *,
        writes: int = _state_values.AGENT_RUN_WRITES,
        beside: Iterable[str] = (),
    ) -> dict:
        """Assert one run's return was held: `writes` more pinned writes, and the record moved by them alone.

        Answers the record as it stands.
        """
        after = github.pinned_data(issue_number)
        test_case.assertEqual(github.write_state_calls - self.writes, writes, "a held return took other writes")
        assert_only_accounted(test_case, self.record, after, beside=beside)
        return after


class RecordsTheLaunch:
    """The runner seam: each process answers in turn, the issue's pinned record read as it is invoked.

    `launched_over` holds that record for every invocation, charge included,
    which is what a held return is measured from: nothing but the accounting
    may move behind it.
    """

    def __init__(self, github, issue_number: int, answers: Iterable[Any]) -> None:
        self._github = github
        self._issue_number = issue_number
        self._answers = iter(answers)
        self.launched_over: list[dict] = []

    def __call__(self, *_spawn_args, **_spawn_fields) -> Any:
        """Read the record the process is invoked over, and answer as the next process does."""
        self.launched_over.append(self._github.pinned_data(self._issue_number))
        return next(self._answers)


def moved(before: _Record, after: _Record) -> set[str]:
    """Every field `after` carries otherwise than `before`, one that either lacks included."""
    return {
        field for field in before.keys() | after.keys()
        if before.get(field, _UNSET) != after.get(field, _UNSET)
    }


def accounted(record: Mapping[str, Any]) -> tuple[int, int]:
    """How many exits `record` counts, and how many receipts it keeps above its floor."""
    receipts = record.get(_RECEIPTS) or {}
    return record.get(_RUNS, 0), len(receipts.get(_RECENT, []))
