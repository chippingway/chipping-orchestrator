# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The report debt a rewritten pull-request head leaves on the pinned comment.

The record is a compatibility contract, so its pinned shape is asserted as a
literal. What a reader may do with it follows from three readings kept apart:
an issue that never carried it and one whose debt was paid claim nothing, a
record nobody can describe is still a claim, and only a whole record names a
head. A later rewrite of the head a debt names carries the debt onto the head
that rewrite published, keeping the head the settled report is about -- or,
where a report of the head it names has settled since, is recorded in its
place, a rewind onto the debt's first head included. A rewrite onto the head the
claim names is a replay whatever head it says it replaced; every other rewrite
is refused and leaves the standing claim exactly where it was.

What pays a debt is a report PUBLISHED about the head the pinned pull request
stands on, against the requirements baseline the issue carries now; a settled
report of either head the debt names that pays nothing is owed a fresh report
of the head the rewrite published.
"""
from __future__ import annotations

import unittest
from dataclasses import replace

from orchestrator.github.pinned_state import MAX_PINNED_BODY, PinnedState
from orchestrator.github.pull_request_reports import ReportLocation
from orchestrator.workflow.engine import (
    report_records as _records,
    report_rewrite_debt as _rewrite_debt,
    report_settlement_state as _settlement,
)
from orchestrator.workflow.late_split import formats as _formats
from tests.workflow.fixtures import SHA_LENGTH

PR = 21

BRANCH = "orchestrator/chippingway__orchestrator/issue-7"

# The head the settled report is about, and the heads two successive rebases
# of this orchestrator's published over it.
REPORTED = "a" * SHA_LENGTH

FIRST = "b" * SHA_LENGTH

SECOND = "c" * SHA_LENGTH

# A head somebody else pushed.
FOREIGN = "d" * SHA_LENGTH

DEBT = _rewrite_debt.RewriteDebt(
    pr_number=PR, branch=BRANCH, previous_head=REPORTED, rewritten_head=FIRST,
)

KEY = _rewrite_debt.REWRITE_DEBT

# Every claim nobody can describe: not an object, a member short, a member
# over, a member that will not type, and two heads that are one commit.
DAMAGED = (
    ("not an object", []),
    ("empty", {}),
    ("truncated", {"pr": PR, "branch": BRANCH}),
    ("extra member", {**DEBT.recorded(), "sha": FIRST}),
    ("abbreviated head", {**DEBT.recorded(), "rewritten_head": FIRST[:-1]}),
    ("no pull request", {**DEBT.recorded(), "pr": 0}),
    ("multi-line branch", {**DEBT.recorded(), "branch": "one\ntwo"}),
    ("one head", {**DEBT.recorded(), "rewritten_head": REPORTED}),
)


# A whole digest, for the settled report's requirements and content alike.
DIGEST = "e" * max(_formats.DIGEST_LENGTHS)

# The rewrite that follows `DEBT`, from the head it published.
NEXT = replace(DEBT, previous_head=FIRST, rewritten_head=SECOND)


def _reported_on(head: str) -> PinnedState:
    """A pinned pull request carrying `DEBT`, whose settled report is about `head`."""
    state = _carrying(DEBT.recorded(), pr_number=PR)
    _settlement.record_current_report(state, _records.CurrentReport(
        subject=_records.ReportSubject(
            repo_slug="chippingway/orchestrator",
            pr_number=PR,
            branch=BRANCH,
            source_sha=head,
            requirements_revision=DIGEST,
        ),
        report_revision=1,
        content_revision=DIGEST,
        location=ReportLocation(pr_number=PR, comment_id=1),
        mode=_records.ReportMode.PUBLISH,
    ))
    return state


def _settled_on(
    head: str,
    mode: _records.ReportMode | None = _records.ReportMode.PUBLISH,
    requirements: str = DIGEST,
    pinned: int = PR,
) -> PinnedState:
    """`_reported_on(head)` settled by `mode` against `requirements`, pinning `pinned`, over a `DIGEST` baseline."""
    state = _reported_on(head)
    settled = _settlement.read_current_report(state)
    _settlement.record_current_report(state, replace(
        settled,
        subject=replace(settled.subject, requirements_revision=requirements),
        mode=mode,
    ))
    state.set("pr_number", pinned)
    state.set("user_content_hash", DIGEST)
    return state


def _carrying(recorded=None, **fields) -> PinnedState:
    """A pinned state whose debt field holds `recorded`, where one is given."""
    pinned = dict(fields)
    if recorded is not None:
        pinned[KEY] = recorded
    return PinnedState(comment_id=1, state_data=pinned)


class RewriteDebtReadingTest(unittest.TestCase):
    """What the record claims, and what it names."""

    def test_a_recorded_debt_reads_back(self) -> None:
        state = _carrying()

        self.assertTrue(_rewrite_debt.records_rewrite(state, DEBT))

        self.assertEqual(
            state.get(KEY),
            {"pr": PR, "branch": BRANCH, "previous_head": REPORTED, "rewritten_head": FIRST},
        )
        self.assertEqual(
            (_rewrite_debt.carries_rewrite_debt(state), _rewrite_debt.read_rewrite_debt(state)),
            (True, DEBT),
        )

    def test_legacy_and_paid_states_claim_nothing(self) -> None:
        for name, state in (
            ("legacy", _carrying()),
            ("paid", PinnedState(state_data={KEY: None})),
        ):
            with self.subTest(name):
                self.assertEqual(
                    (_rewrite_debt.carries_rewrite_debt(state), _rewrite_debt.read_rewrite_debt(state)),
                    (False, None),
                )

    def test_a_damaged_record_names_nothing(self) -> None:
        for name, recorded in DAMAGED:
            with self.subTest(name):
                state = _carrying(recorded)

                self.assertEqual(
                    (_rewrite_debt.carries_rewrite_debt(state), _rewrite_debt.read_rewrite_debt(state)),
                    (True, None),
                )

    def test_a_dropped_debt_leaves_null(self) -> None:
        # A drop keeps the key, so a paid debt is told apart from an issue
        # that never carried one -- which a drop leaves as it found it.
        paid = _carrying(DEBT.recorded())
        legacy = _carrying()

        dropped = (
            _rewrite_debt.drops_rewrite_debt(paid),
            _rewrite_debt.drops_rewrite_debt(paid),
            _rewrite_debt.drops_rewrite_debt(legacy),
        )

        self.assertEqual(dropped, (True, False, False))
        self.assertEqual((paid.data, legacy.data), ({KEY: None}, {}))


class RewriteDebtRecordingTest(unittest.TestCase):
    """Which rewrites the record accepts, and what each leaves."""

    def test_a_later_rewrite_retargets_the_debt(self) -> None:
        # A rewrite of the head the debt names moves it on while keeping the
        # head the settled report is about, and the replay of either write --
        # the one that recorded it, and the one that retargeted it -- leaves
        # the debt as it stands.
        state = _carrying(DEBT.recorded())

        accepted = (
            _rewrite_debt.records_rewrite(state, DEBT),
            _rewrite_debt.records_rewrite(state, NEXT),
            _rewrite_debt.records_rewrite(state, NEXT),
        )

        self.assertEqual(accepted, (True, True, True))
        self.assertEqual(
            _rewrite_debt.read_rewrite_debt(state), replace(DEBT, rewritten_head=SECOND),
        )

    def test_a_replay_is_known_by_its_published_head(self) -> None:
        # A rewrite onto the head the debt names is the debt unchanged whatever
        # head it says it replaced -- the debt's own first head, or one it
        # never recorded -- since the debt already records that head as this
        # orchestrator's and a replay moves nothing the settled report is about.
        for source in (REPORTED, FOREIGN):
            with self.subTest(source=source):
                state = _carrying(DEBT.recorded())

                self.assertTrue(_rewrite_debt.records_rewrite(state, replace(DEBT, previous_head=source)))

                self.assertEqual(state.get(KEY), DEBT.recorded())

    def test_a_rewind_is_a_debt_only_once_paid(self) -> None:
        # A rewrite back onto the debt's first head, while the settled report
        # is still about that head, owes nothing: it is refused and the debt
        # left for the validating hold to pay. Once a report of the head the
        # debt names has settled, the same rewind leaves a head no report is
        # about, and its own debt -- which that report explains -- is recorded.
        rewind = replace(DEBT, previous_head=FIRST, rewritten_head=REPORTED)
        unpaid, paid = _reported_on(REPORTED), _reported_on(FIRST)

        recorded = (
            _rewrite_debt.records_rewrite(unpaid, rewind),
            _rewrite_debt.records_rewrite(paid, rewind),
        )

        self.assertEqual(recorded, (False, True))
        self.assertEqual(
            (_rewrite_debt.read_rewrite_debt(unpaid), _rewrite_debt.read_rewrite_debt(paid)),
            (DEBT, rewind),
        )
        self.assertTrue(rewind.explains(paid, REPORTED))

    def test_a_paid_debt_is_succeeded_by_its_rewrite(self) -> None:
        # Where a report of the head the debt names settled before the next
        # rebase, that report paid it, and the next rewrite's own debt takes
        # its place; where the settled report is still the one before the
        # debt, the debt is carried on. Either way the claim explains the
        # settled report against the head the pull request is left on.
        cases = (
            (FIRST, NEXT),
            (REPORTED, replace(DEBT, rewritten_head=SECOND)),
        )
        for reported, recorded in cases:
            with self.subTest(reported=reported):
                state = _reported_on(reported)

                self.assertTrue(_rewrite_debt.records_rewrite(state, NEXT))

                claim = _rewrite_debt.read_rewrite_debt(state)
                self.assertEqual((claim, claim.explains(state, SECOND)), (recorded, True))


class RewriteDebtRefusalTest(unittest.TestCase):
    """Every rewrite the record refuses, leaving the claim exactly as it was."""

    def test_an_unchained_rewrite_is_refused(self) -> None:
        # A rewrite from a head somebody else pushed onto one the debt does
        # not name, of another pull request or branch, or back onto the head a
        # debt nothing has paid was recorded against, would say this
        # orchestrator made a head it did not -- or lose the debt.
        refused = (
            ("foreign head", replace(DEBT, previous_head=FOREIGN, rewritten_head=SECOND)),
            ("another pull request", replace(DEBT, pr_number=PR + 1, previous_head=FIRST, rewritten_head=SECOND)),
            ("another branch", replace(DEBT, branch="elsewhere", previous_head=FIRST, rewritten_head=SECOND)),
            ("back onto the report", replace(DEBT, previous_head=FIRST, rewritten_head=REPORTED)),
        )
        for name, rewrite in refused:
            with self.subTest(name):
                state = _carrying(DEBT.recorded())

                self.assertFalse(_rewrite_debt.records_rewrite(state, rewrite))

                self.assertEqual(state.get(KEY), DEBT.recorded())

    def test_a_damaged_claim_is_never_written_over(self) -> None:
        for name, recorded in DAMAGED:
            with self.subTest(name):
                state = _carrying(recorded)

                self.assertFalse(_rewrite_debt.records_rewrite(state, DEBT))

                self.assertEqual(state.get(KEY), recorded)

    def test_an_unreadable_rewrite_is_not_recorded(self) -> None:
        # A rewrite that moved nothing, one naming a head that is no commit,
        # and one the comment has no room for leave the state untouched.
        full = {"filler": "x" * MAX_PINNED_BODY}
        for name, rewrite, fields in (
            ("no move", replace(DEBT, rewritten_head=REPORTED), {}),
            ("no commit", replace(DEBT, rewritten_head="HEAD"), {}),
            ("no room", DEBT, full),
        ):
            with self.subTest(name):
                state = _carrying(**fields)

                self.assertFalse(_rewrite_debt.records_rewrite(state, rewrite))

                self.assertFalse(state.carries(KEY))


class RewriteDebtPaymentTest(unittest.TestCase):
    """What pays a debt, and what a debt nothing pays is owed."""

    def test_only_a_fresh_report_of_the_head_pays(self) -> None:
        # A report published about the head the pinned pull request stands
        # on, against the baseline the issue carries now, pays. One verified
        # where it stood -- the report before the rewrite carried forward --
        # one settled before settlements named their mode, one of older
        # requirements, and one of another head pay nothing.
        for name, settled, paid in (
            ("published", _settled_on(FIRST), True),
            ("verified", _settled_on(FIRST, mode=_records.ReportMode.VERIFY), False),
            ("no mode", _settled_on(FIRST, mode=None), False),
            ("older requirements", _settled_on(FIRST, requirements="f" * len(DIGEST)), False),
            ("another head", _settled_on(REPORTED), False),
            ("another pull request pinned", _settled_on(FIRST, pinned=PR + 1), False),
        ):
            with self.subTest(name):
                self.assertEqual(_rewrite_debt.pays_the_debt(settled, FIRST), paid)

    def test_either_head_is_owed_a_refresh(self) -> None:
        # The report of the head the rewrite replaced, and one of the head it
        # published that pays nothing, are each owed a fresh report of the
        # head the debt names. A report of neither head, a head the debt does
        # not name, and a pull request it is not about are owed nothing.
        for name, settled, head, owed in (
            ("the replaced head", _settled_on(REPORTED), FIRST, True),
            ("a verified published head", _settled_on(FIRST, mode=_records.ReportMode.VERIFY), FIRST, True),
            ("neither head", _settled_on(FOREIGN), FIRST, False),
            ("another head standing", _settled_on(REPORTED), FOREIGN, False),
            ("another pull request pinned", _settled_on(REPORTED, pinned=PR + 1), FIRST, False),
        ):
            with self.subTest(name):
                self.assertEqual(DEBT.owes_a_refresh(settled, head), owed)


if __name__ == "__main__":
    unittest.main()
