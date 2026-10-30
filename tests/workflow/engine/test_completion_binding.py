# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""A delivery a captured completion was handed off as, bound only to the commit its run reported on.

The report describes the commit the captured run left, so the binding holds a
publication of that branch and commit to it: its own source binds and is
published as any delivery is, and any other parks once with the delivery
exactly as it stood -- and so does any publication beside a capture nobody can
read, which may be the one the delivery came from. Until the transaction the
delivery becomes settles, the handed-off capture is the one record of that
commit, so neither a later capture nor a retirement takes it, and a delivery
claim nobody can read holds it the same way; once settled, it gives way to
both. A captured report is bound and settled only where the comment carries it
with every terminator escaped, as it was captured and transferred.
"""
from __future__ import annotations

import dataclasses
import unittest

from orchestrator.agents.models import AgentInvocation
from orchestrator.github.pinned_state import MAX_PINNED_BODY, pinned_state_body
from orchestrator.workflow.engine import (
    completion_checkpoint as _checkpoint,
    completion_handoff as _handoff,
    completion_records as _records,
    completion_spelling as _spelling,
    report_commits as _report_commits,
    report_delivery_state as _delivery_state,
    report_record_state as _record_state,
    report_settling as _settling,
)
from orchestrator.workflow.engine.report_binding import ReportPublication, binds_and_publishes, binds_the_delivery
from orchestrator.workflow.engine.report_delivery import UNDELIVERABLE_REPORT
from orchestrator.workflow.engine.report_records import DELIVERED_REPORT, PENDING_REPORT, DeliveredReport
from tests.support.fakes import FakePR, FakePRRef
from tests.workflow.engine import (
    completion_test_support as support,
    report_commit_test_support as commit_support,
    report_delivery_test_support as delivery_support,
    report_transaction_test_support as transaction_support,
)

_STAGE = support.STAGE
_STATUS = support.STATUS
_REASON = _records.RetirementReason
_NONCE = "0123456789abcdef"
_SOURCE = "source"

# A publication the capture's source is held against, the notice that holds
# it, and whether the capture beside it is one nobody can read.
_HELD = (
    (transaction_support.MOVED_SHA, False, "captured from a run"),
    (transaction_support.SOURCE_SHA, True, "cannot be read"),
)

# A delivery claim nobody can read.
_DAMAGED_DELIVERY = (1,)

# A run of terminators the comment carries five characters wider each once
# escaped, and how close to the ceiling another road then fills it, escaped
# in full.
_TERMINATORS = 2000
_TERMINATOR_RUN = "-->" * _TERMINATORS
_TERMINATED = f"REPORT: READY\n{_TERMINATOR_RUN}\nREPORT: END"
_SLACK = 20


def _published(commit: str) -> ReportPublication:
    """A publication of `commit` on the capture's branch, onto pull request 12."""
    return ReportPublication(
        pull_request=FakePR(number=support.VERIFIED_PR, head_branch=support.BRANCH, head=FakePRRef(sha=commit)),
        repo_slug=support.REPO, branch=support.BRANCH, commit=commit,
    )


def _handed_off(**record) -> support.CompletionWorld:
    """An issue pinned with `record`, its first capture handed off as its delivery, which nothing has bound yet."""
    world = support.seeded(**record)
    captured = world.completion()
    world.captures(captured)
    world.asks(_handoff.transfer, captured.invocation)
    return world


def _repaired() -> support.CompletionWorld:
    """A handed-off capture a hand edit damaged, as the tick read it, and a human repaired right behind that reading."""
    world = _handed_off()
    sound = world.record()[support.FIELD]
    damaged = dict(sound)
    damaged.pop(_SOURCE)
    commit_support.another_road(world.github, world.issue, **{support.FIELD: damaged})
    read = world.restarted()
    commit_support.another_road(world.github, world.issue, **{support.FIELD: sound})
    return read


class CapturedSourceBindingTest(unittest.TestCase, transaction_support.ReportTransactionCase):
    """A delivery handed off from a captured completion binds only to the branch and commit that capture reported on."""

    def setUp(self) -> None:
        transaction_support.ReportTransactionCase.setUp(self)

    def publishes(self, source_sha: str, *, damaged: bool = False) -> DeliveredReport:
        """Deliver a report a capture over `source_sha` handed off, then bind and publish it onto the case's PR.

        `damaged` has a hand edit drop the capture's source, so nobody can read it.
        """
        delivered = dataclasses.replace(delivery_support.DELIVERED, requirements_revision=self.requirements())
        _delivery_state.record_delivered_report(self.state, delivered)
        invocation = AgentInvocation(
            repo=self.gh.repo_slug, issue=transaction_support.ISSUE_NUMBER, comment=1, cycle=0, ordinal=1,
            nonce=_NONCE,
        )
        handed_off = _spelling.spelled(_records.ResolvedCapture(
            invocation, _STAGE.HANDED_OFF, receipt=delivered.receipt, report_revision=delivered.report_revision,
            branch=transaction_support.BRANCH, source_sha=source_sha,
        ))
        if damaged:
            handed_off.pop(_SOURCE)
        self.state.set(support.FIELD, handed_off)
        commit_support.pinned((self.gh, self.issue), self.state)
        binds_and_publishes(self.gh, self.issue, self.state, ReportPublication(
            pull_request=self.pull_request, repo_slug=self.gh.repo_slug,
            branch=transaction_support.BRANCH, commit=transaction_support.SOURCE_SHA,
        ))
        return delivered

    def test_its_own_source_binds(self) -> None:
        """The capture's branch and commit are the publication's, so its report is bound and published."""
        self.publishes(transaction_support.SOURCE_SHA)
        transaction_support.assert_one_report(self)

    def test_a_held_source_parks_intact(self) -> None:
        """Another commit than the capture's, or a capture nobody can read, parks once with the delivery as it stood."""
        for source_sha, damaged, notice in _HELD:
            self.setUp()
            delivered = self.publishes(source_sha, damaged=damaged)
            observed = (
                self.state.get(transaction_support.AWAITING_HUMAN),
                self.state.get(transaction_support.PARK_REASON),
                _delivery_state.read_delivered_report(self.state),
                transaction_support.report_comments(self),
            )
            with self.subTest(notice=notice):
                self.assertEqual(observed, (True, UNDELIVERABLE_REPORT, delivered, []))
                self.assertIn(notice, self.issue.comments[-1].body)


class OwedSourceTest(unittest.TestCase):
    """A handed-off capture is kept while it is the one record of the commit its unsettled report is about.

    Neither retirement takes it then. A later capture replaces it only while
    the report it became is a delivery still standing unbound -- one that
    capture's own transfer will supersede -- and only by carrying it, so the
    delivery is held to its source meanwhile, and still is once that capture
    is invalidated and retires carrying it.
    """

    def assert_retirements_kept(self, world: support.CompletionWorld) -> None:
        """Both retirements of the handoff are refused as unbound, writing nothing."""
        for reason in (_REASON.SETTLED, _REASON.INVALIDATED):
            before = world.snapshot()
            refusal = world.asks(_checkpoint.retire, world.invocation(), reason).refusal
            with self.subTest(retired=reason):
                self.assertEqual((refusal, world.snapshot()), (support.REFUSAL.UNBOUND, before))

    def assert_kept(self, world: support.CompletionWorld) -> None:
        """A later capture and both retirements of the handoff are refused as unbound, writing nothing."""
        self.assert_retirements_kept(world)
        before = world.snapshot()
        refusal = world.captures(world.completion(2)).refusal
        self.assertEqual((refusal, world.snapshot()), (support.REFUSAL.UNBOUND, before))

    def assert_carried(self, world: support.CompletionWorld, later, handoff) -> None:
        """`later` lands carrying `handoff`, and the delivery that handoff became is still held to its source."""
        delivered = _delivery_state.read_delivered_report(world.state)
        landed = world.captures(later).status
        carried = _spelling.read_record(world.record()[support.FIELD]).supersedes
        bound = binds_the_delivery(world.github, world.issue, world.state, _published(transaction_support.MOVED_SHA))
        kept = _delivery_state.read_delivered_report(world.state)
        self.assertEqual(
            (landed, carried, bound, kept),
            (_STATUS.LANDED, handoff, False, delivered),
        )

    def test_an_unbound_handoff_is_carried(self) -> None:
        """A later capture carries the handoff, its delivery still held to its source.

        A transaction an earlier report settled leaves its record `null`,
        which claims none, so it holds the later capture no more than an
        issue that never published one.
        """
        for settled in ({}, {PENDING_REPORT: None}):
            with self.subTest(settled=settled):
                world = _handed_off(**settled)
                self.assert_retirements_kept(world)
                handoff = _spelling.read_record(world.record()[support.FIELD])
                self.assert_carried(world, world.completion(2), handoff)

    def test_an_invalidated_carrier_keeps_the_handoff(self) -> None:
        """Invalidated, the carrier retires still carrying the handoff: its replay refused, a later one carrying it on.

        The retirement keeps which invocation it was, so a replay of that
        return answers the retirement standing rather than landing pending
        again; the handoff it carried keeps the delivery held to its source
        meanwhile, and the next capture carries it on.
        """
        world = _handed_off()
        handoff = _spelling.read_record(world.record()[support.FIELD])
        later = world.completion(2)
        world.captures(later)
        world.restarted().asks(_checkpoint.retire, later.invocation, _REASON.INVALIDATED)
        retired = _spelling.read_record(world.record()[support.FIELD])
        replayed = world.restarted().captures(later)
        self.assertEqual(
            (retired.stage, retired.invocation, retired.supersedes, replayed.status, replayed.stage),
            (_STAGE.RETIRED, later.invocation, handoff, _STATUS.STANDING, _STAGE.RETIRED),
        )
        self.assert_carried(world.restarted(), world.completion(3), handoff)

    def test_a_damaged_delivery_holds_it_too(self) -> None:
        """A delivery claim nobody can read may be the handoff's own, so the handoff is kept beside it."""
        world = _handed_off()
        commit_support.another_road(world.github, world.issue, **{DELIVERED_REPORT: list(_DAMAGED_DELIVERY)})
        self.assert_kept(world.restarted())

    def test_a_bound_handoff_is_kept_until_it_settles(self) -> None:
        """Bound to its own commit, the report is the transaction's, which the handoff stays owed to until it settles.

        A settlement dropping that transaction is what lets the handoff retire
        and a later capture land.
        """
        world = _handed_off()
        bound = binds_the_delivery(world.github, world.issue, world.state, _published(support.SOURCE))
        self.assertTrue(bound)
        self.assert_kept(world)
        commit_support.another_road(world.github, world.issue, **{PENDING_REPORT: None})
        settled = world.restarted()
        retired = settled.asks(_checkpoint.retire, settled.invocation(), _REASON.SETTLED)
        later = settled.captures(settled.completion(2))
        self.assertEqual((retired.status, retired.stage), (_STATUS.LANDED, _STAGE.RETIRED))
        self.assertIs(later.status, _STATUS.LANDED)



class RepairedCaptureTest(unittest.TestCase):
    """A park decided on the capture beside a delivery is held to that capture as the comment still carries it."""

    def test_a_repaired_capture_parks_nothing(self) -> None:
        """Damage a human repaired since the tick read it earns no notice and no park, and nothing is written."""
        world = _repaired()
        before = world.snapshot()
        notices = len(world.issue.comments)
        bound = binds_the_delivery(world.github, world.issue, world.state, _published(support.SOURCE))
        self.assertEqual((bound, len(world.issue.comments)), (False, notices))
        self.assertEqual(world.snapshot(), before)



class EscapedInFullTest(unittest.TestCase):
    """A captured report is bound and settled only where the comment carries it with every terminator escaped."""

    def filled(self, world: support.CompletionWorld, note: str) -> support.CompletionWorld:
        """`world` as a later tick reads it, once another road filled its comment escaped in full to the slack."""
        blank = {**world.record(), "operator_note": note}
        width = MAX_PINNED_BODY - _SLACK - len(pinned_state_body(blank, escaped_in_full=True))
        commit_support.another_road(world.github, world.issue, operator_note=note + "x" * width)
        return world.restarted()

    def test_a_binding_is_measured_escaped_in_full(self) -> None:
        """A binding that fits only unescaped is refused for room, the delivery kept and nothing parked."""
        world = support.seeded()
        completion = world.completion(message=_TERMINATED)
        world.captures(completion)
        world.asks(_handoff.transfer, completion.invocation)
        filled = self.filled(world, "")
        delivered = _delivery_state.read_delivered_report(filled.state)
        bound = binds_the_delivery(filled.github, filled.issue, filled.state, _published(support.SOURCE))
        self.assertFalse(bound)
        self.assertIsNone(filled.record().get("awaiting_human"))
        self.assertEqual(_delivery_state.read_delivered_report(filled.restarted().state), delivered)

    def test_a_settlement_is_measured_escaped_in_full(self) -> None:
        """A settlement whose comment fits only unescaped is refused before anything is posted."""
        world = _handed_off()
        binds_the_delivery(world.github, world.issue, world.state, _published(support.SOURCE))
        filled = self.filled(world, _TERMINATOR_RUN)
        pending = _record_state.read_pending_report(filled.state)
        commit = _report_commits.ReportCommit(filled.github, filled.issue, filled.state)
        self.assertIsNotNone(pending)
        self.assertFalse(_settling.prepares(commit, pending))


if __name__ == "__main__":
    unittest.main()
