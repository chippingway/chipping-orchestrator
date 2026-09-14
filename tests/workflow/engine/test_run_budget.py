# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The record an agent-run budget transition leaves on both sinks.

What is pinned here is the contract a consumer reads rather than the roads
that reach it: one payload under two envelopes, the whole ledger reading on
every phase, an unlimited allowance that says so instead of counting, a
correlation that names a reservation only where one exists, a refusal that
explains itself from a closed vocabulary, and a record that survives the
Postgres replay with none of it dropped.
"""
from __future__ import annotations

import json
import unittest
from unittest.mock import patch

from orchestrator.observability.analytics.sync import columns, rows
from orchestrator.workflow.engine import run_budget as _run_budget, run_budget_fields as _run_budget_fields
from tests.support.fakes import FakeGitHubClient, make_issue
from tests.workflow.engine import run_budget_emission_support as _emission_support, run_budget_test_support as budget
from tests.workflow.fixtures import LABEL_IMPLEMENTING

_ISSUE_NUMBER = 1546

_NARROW = 3

# The four fields the sinks' own envelopes supply. Everything else in a record
# is the budget payload, which is what the ingestion check below measures.
_ENVELOPE = (_emission_support._TS, "repo", "issue", budget.EVENT_KEY)

_SINK_FAILURE = "sink refused"

_LABEL_FAILURE = "label read refused"

_FINGERPRINT_HEAD = _emission_support._FINGERPRINT[:_run_budget_fields.FINGERPRINT_HEAD_LENGTH]


# The charge every record below is about: the launch shape, and the count that
# charge moved. Two charges of one shape differ only in the second half.
_RESERVATION_ID = _run_budget_fields._reservation_id(_emission_support._LAUNCH, _emission_support._ledger())


def _issue_and_client():
    gh = FakeGitHubClient()
    issue = make_issue(_ISSUE_NUMBER, label=LABEL_IMPLEMENTING)
    gh.add_issue(issue)
    return gh, issue


# Every phase, and the one call that writes it. A case holding all four to one
# promise walks this rather than repeating the promise once per phase.
_EMITTERS = (
    (budget.RESERVED, _emission_support._charge),
    (budget.STARTED, _emission_support._started),
    (budget.EXHAUSTED, _emission_support._refusal),
    (budget.EXTENDED, _emission_support._extension),
)


class _RecordCase(unittest.TestCase):
    """One issue, and the budget records the audit sink was handed for it."""

    def setUp(self) -> None:
        client, issue = _issue_and_client()
        self.gh = client
        self.issue = issue

    def _audited(self) -> list[dict]:
        return budget.audited(self.gh)

    def _first(self) -> dict:
        return self._audited()[0]


class DualEmissionTest(_RecordCase):
    """One call writes both sinks, and neither can cost the other."""

    def test_the_two_records_are_the_same_record(self) -> None:
        # The audit copy has to answer offline what the database answers over
        # the analytics sink, so the two carry identical payloads under their
        # own envelopes and only the moment each was stamped can differ.
        appended = budget.analytics_of(lambda: _emission_support._charge(self.gh, self.issue))

        audited = self._audited()
        self.assertEqual(len(audited), 1)
        self.assertEqual(len(appended), 1)
        self.assertEqual(
            _emission_support._without_ts(audited[0]),
            _emission_support._without_ts(appended[0]),
        )
        self.assertEqual(audited[0][budget.EVENT_KEY], budget.EVENT)

    def test_a_failing_audit_write_keeps_the_record(self) -> None:
        # Two independent observability surfaces: one being unavailable is not
        # a reason to lose the other, and neither is a reason to break the
        # tick that already made the transition durable.
        with (
            patch.object(
                self.gh, "emit_event", side_effect=RuntimeError(_SINK_FAILURE),
            ),
            self.assertLogs(_run_budget.log, level="ERROR"),
        ):
            appended = budget.analytics_of(
                lambda: _emission_support._charge(self.gh, self.issue),
            )

        self.assertEqual(len(appended), 1)

    def test_a_failing_sink_write_keeps_the_record(self) -> None:
        with (
            patch(
                budget.ANALYTICS_APPEND,
                side_effect=RuntimeError(_SINK_FAILURE),
            ),
            self.assertLogs(_run_budget.log, level="ERROR"),
        ):
            _emission_support._charge(self.gh, self.issue)

        self.assertEqual(budget.phases(self._audited()), [budget.RESERVED])


class LedgerReadingTest(_RecordCase):
    """Every phase carries the whole reading it was taken on."""

    def test_each_phase_reports_the_whole_ledger(self) -> None:
        # A record naming only the field that moved is one an operator has to
        # join against a setting that may have changed since -- and offline,
        # against the audit copy alone, there is nothing to join to.
        for phase, emit in _EMITTERS:
            with self.subTest(phase=phase):
                client, issue = _issue_and_client()
                emit(client, issue)
                recorded = budget.audited(client)[0]
                self.assertEqual(recorded[budget.PHASE], phase)
                self.assertEqual(recorded[budget.CONFIGURED], _emission_support._CONFIGURED)
                self.assertEqual(recorded[budget.ALLOWANCE], _emission_support._CONFIGURED)
                self.assertIn(budget.USED, recorded)
                self.assertIn(budget.REMAINING, recorded)

    def test_an_issue_ceiling_sits_beside_the_setting(self) -> None:
        # They differ exactly where somebody decided something about this
        # issue, and a refusal explained by the deployment's number would name
        # a ceiling this issue was never held to.
        _emission_support._charge(self.gh, self.issue, allowance=9)

        recorded = self._first()
        self.assertEqual(recorded[budget.CONFIGURED], _emission_support._CONFIGURED)
        self.assertEqual(recorded[budget.ALLOWANCE], 9)
        self.assertEqual(recorded[budget.REMAINING], 9 - _emission_support._USED)

    def test_an_unlimited_ceiling_says_so_not_counts(self) -> None:
        # Any count written under a ceiling there is none of is one a query
        # could compare against zero and read as an issue about to stop -- and
        # a field left out instead is one nothing can tell from a count some
        # writer or replay lost. So the field is there and spells itself.
        _emission_support._charge(self.gh, self.issue, configured=0, allowance=0)

        recorded = self._first()
        self.assertEqual(recorded[budget.REMAINING], budget.UNLIMITED)
        self.assertEqual(recorded[budget.USED], _emission_support._USED)

    def test_a_count_past_the_ceiling_has_none_left(self) -> None:
        _emission_support._charge(self.gh, self.issue, allowance=_NARROW)

        self.assertEqual(self._first()[budget.REMAINING], 0)


class CorrelationTest(_RecordCase):
    """What a record names the work it is about by."""

    def test_a_charge_names_the_reservation_it_took(self) -> None:
        # The tick that reserves a run and the tick that spawns on it are two
        # records of one charge, and this is what joins them without either
        # naming the prompt or the worktree it was built out of.
        _emission_support._charge(self.gh, self.issue)
        _emission_support._started(self.gh, self.issue)

        correlated = {
            recorded[budget.RESERVATION_ID] for recorded in self._audited()
        }
        self.assertEqual(correlated, {_RESERVATION_ID})
        self.assertTrue(_RESERVATION_ID.startswith(_FINGERPRINT_HEAD))
        self.assertLess(len(_RESERVATION_ID), len(_emission_support._FINGERPRINT))

    def test_a_second_charge_is_a_second_reservation(self) -> None:
        # The fingerprint is stable across ticks on purpose -- that is what
        # lets a standing reservation be recognized -- so the same shape is
        # charged again whenever a launch that already started comes back.
        # The count each charge moved is what keeps the two apart.
        _emission_support._charge(self.gh, self.issue)
        _emission_support._charge(self.gh, self.issue, used=_emission_support._USED + 1)

        correlated = [
            recorded[budget.RESERVATION_ID] for recorded in self._audited()
        ]
        self.assertEqual(len(set(correlated)), 2)
        for named in correlated:
            with self.subTest(reservation_id=named):
                self.assertTrue(named.startswith(_FINGERPRINT_HEAD))

    def test_nothing_holding_a_reservation_claims_one(self) -> None:
        # A refused launch never took a charge and a grant is not a launch at
        # all, so a correlation on either would point at a reservation
        # nothing ever wrote.
        _emission_support._refusal(self.gh, self.issue)
        _emission_support._extension(self.gh, self.issue)

        for recorded in self._audited():
            with self.subTest(phase=recorded[budget.PHASE]):
                self.assertNotIn(budget.RESERVATION_ID, recorded)

    def test_a_launch_records_its_stage_and_role(self) -> None:
        _emission_support._charge(self.gh, self.issue)
        _emission_support._refusal(self.gh, self.issue)

        for recorded in self._audited():
            with self.subTest(phase=recorded[budget.PHASE]):
                self.assertEqual(recorded[budget.STAGE], _emission_support._STAGE)
                self.assertEqual(recorded[budget.AGENT_ROLE], _emission_support._ROLE)

    def test_an_unreadable_label_still_records(self) -> None:
        # The one field on this stream that costs a request to build, asked on
        # the far side of a durable grant: an exception here would break a
        # tick that had already taken the park down, and lose the transition
        # to both sinks on the way out.
        with (
            patch.object(
                self.gh,
                "workflow_label",
                side_effect=RuntimeError(_LABEL_FAILURE),
            ),
            self.assertLogs(_run_budget.log, level="ERROR"),
        ):
            appended = budget.analytics_of(
                lambda: _emission_support._extension(self.gh, self.issue),
            )

        recorded = self._first()
        self.assertEqual(recorded[budget.PHASE], budget.EXTENDED)
        self.assertNotIn(budget.STAGE, recorded)
        self.assertEqual(len(appended), 1)
        self.assertNotIn(budget.STAGE, appended[0])

    def test_a_grant_reads_the_label_not_a_role(self) -> None:
        # The ledger is spent by every role at every stage, so there is no one
        # role a human bought runs for; where the issue was standing is the
        # whole of what an extension can say about itself.
        _emission_support._extension(self.gh, self.issue)

        recorded = self._first()
        self.assertEqual(recorded[budget.STAGE], _emission_support._STAGE)
        self.assertNotIn(budget.AGENT_ROLE, recorded)


class ExhaustionReasonTest(_RecordCase):
    """A refusal explains itself from a closed vocabulary."""

    def test_the_reason_tells_the_two_endings_apart(self) -> None:
        # An issue standing exactly at its ceiling got there by running; one
        # already past it got there because the ceiling came down on it, and
        # an operator reading a park they did not expect needs to tell which.
        for used, reason in (
            (_emission_support._CONFIGURED, budget.ALLOWANCE_SPENT),
            (_emission_support._CONFIGURED + 1, budget.ALLOWANCE_EXCEEDED),
        ):
            with self.subTest(used=used):
                client, issue = _issue_and_client()
                _emission_support._refusal(client, issue, used=used)
                recorded = budget.audited(client)[0]
                self.assertEqual(recorded[budget.REASON], reason)

    def test_only_a_refusal_carries_one(self) -> None:
        _emission_support._charge(self.gh, self.issue)
        _emission_support._extension(self.gh, self.issue)

        for recorded in self._audited():
            with self.subTest(phase=recorded[budget.PHASE]):
                self.assertNotIn(budget.REASON, recorded)


class PostgresIngestionTest(unittest.TestCase):
    """The replay into the events table keeps every field of the record.

    The table has no column for a budget field and needs none: the two the
    schema already promotes are promoted, and everything else lands in
    `extras JSONB` -- which is what lets an operator ingest this family with
    no migration and no schema reapply.
    """

    def setUp(self) -> None:
        client, issue = _issue_and_client()
        self.gh = client
        self.issue = issue

    def test_a_charge_survives_as_columns_and_extras(self) -> None:
        recorded = self._recorded(_emission_support._charge)
        prepared, refused = rows.prepare_record(
            f"{json.dumps(recorded, sort_keys=True)}\n",
        )

        self.assertIsNone(refused)
        promoted = dict(prepared.columns)
        self.assertEqual(promoted[budget.STAGE], _emission_support._STAGE)
        self.assertEqual(promoted[budget.AGENT_ROLE], _emission_support._ROLE)
        self.assertEqual(prepared.extras, {
            budget.PHASE: budget.RESERVED,
            budget.CONFIGURED: _emission_support._CONFIGURED,
            budget.ALLOWANCE: _emission_support._CONFIGURED,
            budget.USED: _emission_support._USED,
            budget.REMAINING: _emission_support._CONFIGURED - _emission_support._USED,
            budget.RESERVATION_ID: _RESERVATION_ID,
        })

    def test_an_unlimited_remaining_reaches_extras(self) -> None:
        # The word is the whole point of spelling it: dropped by an envelope
        # or lost by the replay, an unbounded ceiling would reach the table as
        # a row with no capacity figure -- indistinguishable from one whose
        # count went missing.
        recorded = self._recorded(_emission_support._unlimited_charge)
        prepared, refused = rows.prepare_record(
            f"{json.dumps(recorded, sort_keys=True)}\n",
        )

        self.assertIsNone(refused)
        self.assertEqual(prepared.extras[budget.REMAINING], budget.UNLIMITED)
        self.assertEqual(prepared.extras[budget.ALLOWANCE], 0)

    def test_nothing_the_record_carries_is_dropped(self) -> None:
        # A field in neither half is one the replay silently loses, which is
        # the failure the JSONB column exists to make impossible.
        recorded = self._recorded(_emission_support._charge)
        promoted, extras = rows.split_row(recorded)

        self.assertEqual(set(promoted) | set(extras), set(recorded))
        self.assertEqual(
            set(promoted) - set(_ENVELOPE),
            {budget.STAGE, budget.AGENT_ROLE},
        )
        self.assertFalse(set(extras) & set(columns.PROMOTED_COLUMNS))

    def test_a_refusal_lands_its_reason_in_extras(self) -> None:
        promoted, extras = rows.split_row(self._recorded(_emission_support._refusal))

        self.assertEqual(extras[budget.REASON], budget.ALLOWANCE_SPENT)
        self.assertEqual(extras[budget.REMAINING], 0)
        self.assertEqual(promoted[budget.STAGE], _emission_support._STAGE)

    def _recorded(self, emit) -> dict:
        return budget.analytics_of(lambda: emit(self.gh, self.issue))[0]


if __name__ == "__main__":
    unittest.main()
