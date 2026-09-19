# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The report a completed run leaves behind, and the transaction it becomes.

Two halves, in the order they happen. A run's outcome is recorded before its
code is published, holding everything the session settled and nothing a pull
request decides -- and what the transaction it becomes will cost is reserved
there too, since the binding happens after the push and a report refused then
is one the code went out without. Then the publication arrives and the record
is bound to it: one write that drops the delivery and records the transaction,
or no write at all and a refusal that says which of the two it was.

Beside them, what the comment has to have room for before either happens, and
what a run that moved no head IS while a report is still owed -- the one
reading that keeps the reply a park earns from being read as a question.
"""

from __future__ import annotations

import unittest
from dataclasses import replace

from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.engine import (
    report_delivery as _delivery,
    report_delivery_state as _delivery_state,
    report_record_state as _record_state,
    report_records as _records,
    report_settlement_state as _settlement,
)
from orchestrator.workflow.state import WorkflowLabel
from tests.workflow.engine import (
    report_delivery_test_support as delivery_support,
    report_record_test_support as support,
)
from tests.workflow.fixtures import (
    _FAKE_WT,
    _TEST_SPEC,
    PROVIDER_OVERLOAD_MESSAGE,
    _agent,
)
from tests.workflow.git_owners import seam_patch

# A notice offered to a park that is still standing, which nobody may be sent.
_SECOND_NOTICE = "The report this issue owes still cannot be delivered."


class DeliveredReportRecordTest(unittest.TestCase):
    def test_both_modes_round_trip(self) -> None:
        for delivered_report in (delivery_support.DELIVERED, delivery_support.ASSERTED):
            with self.subTest(mode=delivered_report.mode):
                state = PinnedState()

                self.assertTrue(_delivery_state.record_delivered_report(
                    state, delivered_report,
                ))

                self.assertTrue(
                    _delivery_state.carries_delivered_report(state),
                )
                self.assertEqual(
                    _delivery_state.read_delivered_report(state),
                    delivered_report,
                )

    def test_a_claim_is_not_an_absence(self) -> None:
        # A record cleared holds `null` and owes nothing; one a hand edit left
        # as something else owes a report nobody can describe, and the two may
        # never read the same.
        cleared = PinnedState()
        _delivery_state.clear_delivered_report(cleared)
        claimed = PinnedState(state_data={_records.DELIVERED_REPORT: []})

        self.assertFalse(_delivery_state.carries_delivered_report(cleared))
        self.assertTrue(_delivery_state.carries_delivered_report(claimed))
        for state in (cleared, claimed):
            with self.subTest(recorded=state.get(_records.DELIVERED_REPORT)):
                self.assertIsNone(
                    _delivery_state.read_delivered_report(state),
                )

    def test_an_unpublishable_report_is_refused(self) -> None:
        # Every refusal is the same answer -- a record describing a
        # publication this build could never make -- and none of them writes
        # anything, so the caller hears it while the run is still there.
        for described, text in delivery_support.UNPUBLISHABLE_REPORTS:
            with self.subTest(report=described):
                state = PinnedState()

                self.assertFalse(_delivery_state.record_delivered_report(
                    state, _records.DeliveredReport(
                        receipt=delivery_support.RECEIPT,
                        report_revision=1,
                        mode=_records.ReportMode.PUBLISH,
                        route=WorkflowLabel.IMPLEMENTING,
                        requirements_revision=support.REQUIREMENTS,
                        report=text,
                    ),
                ))

                self.assertEqual(state.data, {})

    def test_a_locationless_verify_is_refused(self) -> None:
        # A location is what a verification is: with none there is nothing to
        # re-read, so the record is refused rather than written as a
        # publication with no text.
        state = PinnedState()

        self.assertFalse(_delivery_state.record_delivered_report(
            state, _records.DeliveredReport(
                receipt=delivery_support.RECEIPT,
                report_revision=1,
                mode=_records.ReportMode.VERIFY,
                route=WorkflowLabel.IMPLEMENTING,
                requirements_revision=support.REQUIREMENTS,
                content_revision=support.CONTENT_DIGEST,
            ),
        ))

        self.assertEqual(state.data, {})


class DeliveredReportCapacityTest(unittest.TestCase):
    """What the comment has to have room for before a record is accepted.

    Three writes, and the record's own is only the first: the transaction
    it is bound into after the push, and the code-publication receipt the
    push itself leaves, both land on this same comment. A record accepted
    without room for either is one refused when nothing can be asked of
    the run that wrote the report.
    """

    def test_a_record_past_the_comment_is_refused(self) -> None:
        # The record shares the comment with everything else this issue has
        # recorded, so what is measured is the write it would make.
        crowded = delivery_support.crowded_comment(0)

        self.assertFalse(
            _delivery_state.record_delivered_report(crowded, delivery_support.DELIVERED),
        )

        self.assertFalse(
            _delivery_state.carries_delivered_report(crowded),
        )

    def test_a_transaction_past_the_comment(self) -> None:
        # The delivered record fits and the transaction it will be bound into
        # does not, which is the whole reason the second write is measured
        # where the first one is: the binding happens after the push, so a
        # report accepted here and refused there is one the code went out
        # without.
        crowded = delivery_support.crowded_comment(delivery_support.CROWDED_FOR_RESERVATION)

        self.assertTrue(_record_state.fits_the_comment({
            **crowded.data, _records.DELIVERED_REPORT: delivery_support.delivered_object(),
        }))
        self.assertFalse(
            _delivery_state.record_delivered_report(crowded, delivery_support.DELIVERED),
        )
        self.assertFalse(_delivery_state.carries_delivered_report(crowded))

    def test_the_reservation_is_the_write_it_makes(self) -> None:
        # What is reserved is the comment the BINDING leaves, which is the
        # delivery dropped and the transaction in its place. A first delivery
        # has to carry the `null` that drop writes; a redelivery gets back the
        # room the record it replaces is holding. Measured over the comment as
        # it stands, the first is accepted and then refused with the code
        # already pushed, and the second is refused with room to spare.
        tombstoned = delivery_support.crowded_comment(delivery_support.CROWDED_FOR_TOMBSTONE)
        replaced = delivery_support.crowded_comment(
            delivery_support.CROWDED_FOR_REDELIVERY,
            {_records.DELIVERED_REPORT: delivery_support.delivered_object()},
        )

        self.assertFalse(
            _delivery_state.record_delivered_report(tombstoned, delivery_support.DELIVERED),
        )
        self.assertTrue(
            _delivery_state.record_delivered_report(replaced, delivery_support.DELIVERED),
        )

        self.assertEqual(
            _delivery_state.binds_delivered_report(
                PinnedState(state_data={
                    **tombstoned.data,
                    _records.DELIVERED_REPORT: delivery_support.delivered_object(),
                }),
                delivery_support.DELIVERED,
                delivery_support.WIDEST_SUBJECT,
            ),
            _delivery_state.CROWDED_COMMENT,
        )
        self.assertEqual(
            _delivery_state.binds_delivered_report(
                replaced, delivery_support.DELIVERED, delivery_support.WIDEST_SUBJECT,
            ),
            "",
        )

    def test_the_push_s_own_write_is_reserved(self) -> None:
        # Between this record and the transaction it becomes stands the push,
        # and the gate that pushes writes the code-publication receipt onto
        # this same comment. So the comment this write leaves has to still
        # have room for that one -- over everything the issue already carries,
        # a transaction an earlier publication left outstanding included,
        # which is a world the exchanged reservation never measures.
        crowded = delivery_support.crowded_comment(
            delivery_support.OUTSTANDING_REPORT
            + delivery_support.CROWDED_FOR_RECEIPT,
            delivery_support.outstanding_comment(),
        )
        staged = {
            **crowded.data,
            _records.DELIVERED_REPORT: delivery_support.delivered_object(),
        }

        self.assertTrue(_record_state.fits_the_comment(staged))
        self.assertFalse(_record_state.fits_the_comment({
            **_record_state.with_publication_receipt(crowded).data,
            _records.DELIVERED_REPORT: delivery_support.delivered_object(),
        }))
        self.assertFalse(_delivery_state.record_delivered_report(
            crowded, delivery_support.DELIVERED,
        ))
    def test_the_widest_branch_is_reserved(self) -> None:
        # What the comment charges for a branch is not what the reader counts:
        # the field is bounded in codepoints and the comment in the characters
        # JSON renders them as, so one codepoint outside the BMP costs twelve
        # -- and a ref of 256 of them is one git makes without complaint.
        # Reserved at the ASCII width, this report is accepted and then
        # refused with the code already pushed; reserved at the width the
        # rendering charges, it is refused here instead, while the comment
        # that does have room for it binds that branch.
        wide = replace(delivery_support.WIDEST_SUBJECT, branch=delivery_support.WIDEST_BRANCH)
        crowded = delivery_support.crowded_comment(delivery_support.CROWDED_FOR_ASCII_BRANCH)
        roomy = delivery_support.crowded_comment(delivery_support.CROWDED_FOR_RESERVED_SUBJECT)

        self.assertFalse(
            _delivery_state.record_delivered_report(crowded, delivery_support.DELIVERED),
        )
        self.assertTrue(
            _delivery_state.record_delivered_report(roomy, delivery_support.DELIVERED),
        )
        self.assertEqual(
            _delivery_state.binds_delivered_report(roomy, delivery_support.DELIVERED, wide), "",
        )


class ReportedRunTest(unittest.TestCase):
    """What a run EARNS, and what recording it leaves on the comment.

    A run that completed owes a report, because every developer prompt asks
    for one; a run that never reached its own end owes nothing, because there
    was nobody to hold to the contract. What a run that DID report leaves is
    a durable record, minted past every revision this issue has already used.
    """

    def test_a_run_that_reported_nothing_holds(self) -> None:
        # Every way a run that COMPLETED can hand over no report: no marker at
        # all, a question, a block nothing closed, and a verification naming
        # another repository -- which is a location this workflow would
        # re-read on somebody else's thread. Each holds the tick and parks,
        # and the park is what remembers the debt, since there is no report to
        # record.
        seeded = delivery_support.seeded_issue()
        messages = (
            ("no marker at all", "implemented"),
            ("a question", "which database should this use?"),
            ("a report block nothing closed", "REPORT: READY\nthe report"),
            ("another repository", (
                "REPORT: VERIFIED https://github.com/someone/else/pull/3"
                f" sha256:{support.CONTENT_DIGEST}"
            )),
        )
        for described, message in messages:
            with self.subTest(message=described):
                state = PinnedState(state_data={delivery_support.BASELINE: support.REQUIREMENTS})

                self.assertTrue(_delivery.recording_stops_the_tick(
                    *seeded, state, _agent(last_message=message),
                    WorkflowLabel.IMPLEMENTING,
                ))

                self.assertFalse(
                    _delivery_state.carries_delivered_report(state),
                )
                self.assertEqual(
                    (state.get(delivery_support.PARK_REASON), _delivery.owes_a_report(state)),
                    (_delivery.UNDELIVERABLE_REPORT, True),
                )

    def test_the_debt_outlives_its_park(self) -> None:
        # The flags are single, so a later park -- a resumed run that timed out
        # -- replaces the reason. The debt is kept beside it, so the issue
        # still owes its report, until a run that reports retires both.
        seeded = delivery_support.seeded_issue()
        state = PinnedState(state_data={delivery_support.BASELINE: support.REQUIREMENTS})
        _delivery.recording_stops_the_tick(
            *seeded, state, _agent(last_message="implemented"),
            WorkflowLabel.IMPLEMENTING,
        )
        state.set(delivery_support.PARK_REASON, "agent_timeout")
        self.assertEqual(
            (state.get(_delivery.OWED_REPORT), _delivery.owes_a_report(state)),
            (True, True),
        )

        self.assertFalse(_delivery.recording_stops_the_tick(
            *seeded, state,
            _agent(last_message=delivery_support.ready("The report.")),
            WorkflowLabel.IMPLEMENTING,
        ))

        self.assertIsNone(state.get(_delivery.OWED_REPORT))
        self.assertTrue(_delivery_state.carries_delivered_report(state))

    def test_a_standing_legacy_park_takes_the_debt(self) -> None:
        # A park taken before the debt had a field of its own carries the
        # reason alone. Met again while it stands, it is told nothing new, and
        # the debt is written down, so the park that replaces the reason next
        # leaves the report still owed.
        github, issue = delivery_support.seeded_issue()
        state = PinnedState(state_data=dict(delivery_support.OWED) | {
            delivery_support.AWAITING_HUMAN: True,
        })

        _delivery.parks_an_undeliverable_report(
            github, issue, state, _SECOND_NOTICE,
        )
        state.set(delivery_support.PARK_REASON, "agent_timeout")

        self.assertEqual(
            (
                [posted.body for posted in issue.comments].count(_SECOND_NOTICE),
                github.pinned_data(issue.number)[_delivery.OWED_REPORT],
                _delivery.owes_a_report(state),
            ),
            (0, True, True),
        )

    def test_a_run_no_process_finished_holds_nothing(self) -> None:
        # Every way a run falls short of its own end: one no process produced
        # at all -- the sentence a caller synthesizes to publish committed
        # work an earlier run left -- and the four a shutdown kill, the
        # orchestrator's own timeout, a provider refusal -- the marker the
        # provider sends beside a nonzero exit -- and an exit of its own. The
        # rest carry a well-formed report, so the judgement is visibly about
        # the RUN rather than about its message: none of these is a developer
        # declining to report, so nothing is recorded and nothing is held.
        seeded = delivery_support.seeded_issue()
        runs = (
            ("nothing invoked", {"invoked": False}),
            ("a shutdown kill", {"interrupted": True}),
            ("the orchestrator's timeout", {"timed_out": True}),
            (
                "a provider refusal",
                {"last_message": PROVIDER_OVERLOAD_MESSAGE, "exit_code": 1},
            ),
            ("a nonzero exit", {"exit_code": 3}),
        )
        for described, run in runs:
            with self.subTest(run=described):
                state = PinnedState(state_data={delivery_support.BASELINE: support.REQUIREMENTS})

                self.assertFalse(_delivery.recording_stops_the_tick(
                    *seeded, state,
                    _agent(**{"last_message": delivery_support.ready(delivery_support.DELIVERED.report), **run}),
                    WorkflowLabel.IMPLEMENTING,
                ))

                self.assertFalse(_delivery.owes_a_report(state))

    def test_a_verified_report_is_recorded(self) -> None:
        # A run that says the report is already on this repository's thread
        # records the exact place and the digest it read there. Nothing of it
        # is believed here: what settles is a fresh read of that location.
        github, issue = delivery_support.seeded_issue()
        state = PinnedState(state_data={delivery_support.BASELINE: support.REQUIREMENTS})

        self.assertFalse(_delivery.recording_stops_the_tick(
            github, issue, state, _agent(last_message=(
                f"done\n\nREPORT: VERIFIED https://github.com/{support.SLUG}"
                f"/pull/{support.PR_NUMBER}#issuecomment-{support.COMMENT_ID}"
                f" sha256:{support.CONTENT_DIGEST}"
            )),
            WorkflowLabel.IMPLEMENTING,
        ))

        self.assertEqual(
            _delivery_state.read_delivered_report(state), delivery_support.ASSERTED,
        )

    def test_a_repository_nobody_could_read(self) -> None:
        # The one reading on this road that leaves the process: whether the
        # location a verification names is on this repository. Raised, it
        # would take the tick down with the only copy of what the developer
        # said and leave the commit in a worktree nothing had said anything
        # about -- so it is held for a human exactly as a location on somebody
        # else's repository is.
        github, issue = delivery_support.seeded_issue()
        delivery_support.unreachable_repository(github)
        state = PinnedState(
            state_data={delivery_support.BASELINE: support.REQUIREMENTS},
        )

        self.assertTrue(_delivery.recording_stops_the_tick(
            github, issue, state, _agent(last_message=(
                f"done\n\nREPORT: VERIFIED https://github.com/{support.SLUG}"
                f"/pull/{support.PR_NUMBER} sha256:{support.CONTENT_DIGEST}"
            )),
            WorkflowLabel.IMPLEMENTING,
        ))

        self.assertFalse(_delivery_state.carries_delivered_report(state))
        self.assertEqual(
            (
                state.get(delivery_support.AWAITING_HUMAN),
                state.get(delivery_support.PARK_REASON),
            ),
            (True, _delivery.UNDELIVERABLE_REPORT),
        )

    def test_no_baseline_parks_the_tick(self) -> None:
        # The requirements revision is the one member of a subject the run
        # settles, and a record without it is a transaction nothing could
        # prove again -- so the report cannot be recorded, and a report this
        # build cannot record holds the tick rather than letting the code go
        # out without one.
        github, issue = delivery_support.seeded_issue()
        state = PinnedState()

        self.assertTrue(_delivery.recording_stops_the_tick(
            github, issue, state, _agent(last_message=delivery_support.ready(delivery_support.DELIVERED.report)),
            WorkflowLabel.IMPLEMENTING,
        ))

        self.assertFalse(_delivery_state.carries_delivered_report(state))
        self.assertEqual(
            (state.get(delivery_support.AWAITING_HUMAN), state.get(delivery_support.PARK_REASON)),
            (True, _delivery.UNDELIVERABLE_REPORT),
        )


class DeliveredRevisionTest(unittest.TestCase):
    """What the record a finished run leaves SAYS, once the run is gone.

    Every report this issue has already recorded pins a revision it has used,
    and the receipt is spelled from that revision -- so the record has to move
    past all of them, and it has to be on GitHub before the code it is about
    goes anywhere.
    """

    def test_the_revision_moves_forward(self) -> None:
        # A settled report and an outstanding transaction each pin a revision
        # this issue has used: one because a settlement replaces the current
        # report, the other because a transaction's receipt is spelled from
        # its revision and may not be minted twice.
        state = PinnedState(state_data={delivery_support.BASELINE: support.REQUIREMENTS})
        _settlement.record_current_report(state, support.CURRENT)
        _record_state.record_pending_report(state, support.PUBLISHED)
        github, issue = delivery_support.seeded_issue()

        _delivery.recording_stops_the_tick(
            github, issue, state, _agent(last_message=delivery_support.ready(delivery_support.DELIVERED.report)),
            WorkflowLabel.IMPLEMENTING,
        )

        recorded = _delivery_state.read_delivered_report(state)
        self.assertEqual(recorded.report_revision, support.REVISION + 1)
        self.assertEqual(recorded.receipt, f"issue-{delivery_support.ISSUE_NUMBER}-report-3")

    def test_a_redelivery_moves_past_the_delivery(self) -> None:
        # The reply an undeliverable-report park earns writes over the
        # delivery standing on the comment, so that record pins a revision
        # this issue has used exactly as the other two do: minted at its
        # revision, the replacement would carry the receipt the record it
        # replaces already carries -- which is what a retry finds its own
        # comment by.
        github, issue = delivery_support.seeded_issue()
        state = PinnedState(state_data={delivery_support.BASELINE: support.REQUIREMENTS})
        _delivery_state.record_delivered_report(state, delivery_support.DELIVERED)

        _delivery.recording_stops_the_tick(
            github, issue, state,
            _agent(last_message=delivery_support.ready("the report the park asked for")),
            WorkflowLabel.IMPLEMENTING,
        )

        recorded = _delivery_state.read_delivered_report(state)
        self.assertEqual(
            (recorded.report_revision, recorded.receipt),
            (2, f"issue-{delivery_support.ISSUE_NUMBER}-report-2"),
        )

    def test_a_handed_revision_outranks_the_baseline(self) -> None:
        # A caller that snapshotted what it handed the run is believed over
        # the baseline on the comment, which may have moved on since the
        # spawn; the route travels with the snapshot unchanged.
        state = PinnedState()
        state.set(delivery_support.BASELINE, support.REQUIREMENTS)
        handed = "b" * len(support.REQUIREMENTS)

        _delivery.recording_stops_the_tick(
            *delivery_support.seeded_issue(), state,
            _agent(last_message=delivery_support.ready("the resume's report")),
            _records.HandedRun(WorkflowLabel.VALIDATING, handed),
        )

        recorded = state.get(_records.DELIVERED_REPORT)
        self.assertEqual(
            (recorded["requirements"], recorded["route"]),
            (handed, WorkflowLabel.VALIDATING),
        )

    def test_the_delivery_is_durable(self) -> None:
        # The write is the owner's own, because what makes the report
        # recoverable is that it is on GitHub before the size gate reads the
        # candidate and before the push sends it.
        github, issue = delivery_support.seeded_issue()
        state = github.read_pinned_state(issue)
        state.set(delivery_support.BASELINE, support.REQUIREMENTS)

        _delivery.recording_stops_the_tick(
            github, issue, state, _agent(last_message=delivery_support.ready(delivery_support.DELIVERED.report)),
            WorkflowLabel.IMPLEMENTING,
        )

        self.assertEqual(
            github.pinned_data(delivery_support.ISSUE_NUMBER)[_records.DELIVERED_REPORT],
            state.get(_records.DELIVERED_REPORT),
        )
        self.assertTrue(_delivery.owes_a_report(state))


class DeliveredReportBindingTest(unittest.TestCase):
    def test_binding_exchanges_the_records(self) -> None:
        state = PinnedState()
        _delivery_state.record_delivered_report(state, delivery_support.DELIVERED)

        self.assertEqual(
            _delivery_state.binds_delivered_report(
                state, delivery_support.DELIVERED, support.SUBJECT,
            ),
            "",
        )

        self.assertFalse(_delivery_state.carries_delivered_report(state))
        self.assertEqual(
            _record_state.read_pending_report(state),
            _records.PendingReport(
                receipt=delivery_support.DELIVERED.receipt,
                subject=support.SUBJECT,
                report_revision=delivery_support.DELIVERED.report_revision,
                mode=delivery_support.DELIVERED.mode,
                route=delivery_support.DELIVERED.route,
                report=delivery_support.DELIVERED.report,
            ),
        )

    def test_a_refused_binding_writes_nothing(self) -> None:
        # A subject the transaction's own writer will not store, and a
        # verification asserting a report on another pull request. Neither may
        # half-apply: a delivery dropped with no transaction beside it is a
        # finished run's report lost. Both answer UNBINDABLE, since no room
        # the comment could get back would make either of them acceptable.
        refused = (
            (
                "a subject naming no pull request",
                delivery_support.DELIVERED,
                _records.ReportSubject(
                    repo_slug=support.SLUG,
                    pr_number=0,
                    branch=support.BRANCH,
                    source_sha=support.SOURCE_SHA,
                    requirements_revision=support.REQUIREMENTS,
                ),
            ),
            ("a location on another pull request", delivery_support.ASSERTED, _records.ReportSubject(
                repo_slug=support.SLUG,
                pr_number=support.PR_NUMBER + 1,
                branch=support.BRANCH,
                source_sha=support.SOURCE_SHA,
                requirements_revision=support.REQUIREMENTS,
            )),
        )
        for described, delivered_report, subject in refused:
            with self.subTest(binding=described):
                state = PinnedState()
                _delivery_state.record_delivered_report(state, delivered_report)

                self.assertEqual(
                    _delivery_state.binds_delivered_report(
                        state, delivered_report, subject,
                    ),
                    _delivery_state.UNBINDABLE_RECORD,
                )

                self.assertEqual(
                    _delivery_state.read_delivered_report(state),
                    delivered_report,
                )
                self.assertFalse(_record_state.carries_pending_report(state))

    def test_a_crowded_comment_is_its_own_refusal(self) -> None:
        # A sound record the comment cannot carry the transaction for is told
        # apart from one nothing could ever bind, because the two are cleared
        # by different things: room comes back as the routes behind a report
        # still owed write to the comment, and the record is left standing for
        # the tick that finds it.
        crowded = delivery_support.crowded_comment(
            delivery_support.CROWDED_FOR_BINDING,
            {_records.DELIVERED_REPORT: delivery_support.delivered_object()},
        )

        self.assertEqual(
            _delivery_state.binds_delivered_report(
                crowded, delivery_support.DELIVERED, support.SUBJECT,
            ),
            _delivery_state.CROWDED_COMMENT,
        )

        self.assertEqual(
            _delivery_state.read_delivered_report(crowded), delivery_support.DELIVERED,
        )
        self.assertFalse(_record_state.carries_pending_report(crowded))

    def test_a_foreign_requirements_revision(self) -> None:
        # The requirements revision belongs to the run and was frozen with the
        # report, so a subject restating it differently is refused before
        # anything is staged: bound, the transaction would claim the report
        # answers content the run never saw and prove it against that content
        # on the tick it settles.
        state = PinnedState()
        _delivery_state.record_delivered_report(state, delivery_support.DELIVERED)

        self.assertEqual(
            _delivery_state.binds_delivered_report(
                state, delivery_support.DELIVERED, replace(
                    support.SUBJECT,
                    requirements_revision=support.CONTENT_DIGEST,
                ),
            ),
            _delivery_state.UNBINDABLE_RECORD,
        )

        self.assertEqual(
            _delivery_state.read_delivered_report(state), delivery_support.DELIVERED,
        )
        self.assertFalse(_record_state.carries_pending_report(state))

    def test_a_delivery_the_comment_does_not_carry(self) -> None:
        # What is bound is the report the COMMENT holds. The argument reaches
        # here across a push and a pull request, so it can name a report this
        # issue never recorded, one nothing can read, or one a later report
        # has already replaced -- and the write drops whatever the record
        # holds, so binding on any of them would replace a finished run's
        # report with a value the comment never carried, or with none at all.
        carried = (
            ("nothing delivered at all", PinnedState()),
            (
                "a claim nothing can read",
                PinnedState(state_data={_records.DELIVERED_REPORT: []}),
            ),
            (
                "a record the issue has moved past",
                PinnedState(state_data={
                    _records.DELIVERED_REPORT: delivery_support.delivered_object(delivery_support.REDELIVERED),
                }),
            ),
        )
        for described, state in carried:
            with self.subTest(delivery=described):
                before = dict(state.data)

                self.assertEqual(
                    _delivery_state.binds_delivered_report(
                        state, delivery_support.DELIVERED, support.SUBJECT,
                    ),
                    _delivery_state.UNBINDABLE_RECORD,
                )

                self.assertEqual(state.data, before)
                self.assertFalse(_record_state.carries_pending_report(state))

class OwedReportRedeliveryTest(unittest.TestCase):
    """A run that committed nothing, on an issue that is owed a report.

    Every ordinary reply that moves no head is a question. An issue holding a
    report nothing could deliver is the exception: it was waiting for a report
    rather than for code, and the commits are already on the branch.
    """

    def test_a_report_republishes_the_branch(self) -> None:
        state = PinnedState()
        _delivery_state.record_delivered_report(state, delivery_support.DELIVERED)

        with seam_patch("_has_new_commits", lambda *_args: True):
            self.assertTrue(_delivery.redelivers_an_owed_report(
                _TEST_SPEC,
                state,
                _agent(last_message=delivery_support.ready(delivery_support.DELIVERED.report)),
                _FAKE_WT,
            ))

    def test_each_reading_answers_on_its_own(self) -> None:
        # The debt, the outcome and the branch are required together: an issue
        # owing nothing is the ordinary no-commit reply, a run that asked
        # rather than reported is still a question, and a branch with nothing
        # ahead of base would publish a pull request with no diff in it.
        answered = (
            ("no report is owed", PinnedState(), delivery_support.ready(delivery_support.DELIVERED.report)),
            (
                "the run asked a question",
                PinnedState(state_data=dict(delivery_support.OWED)),
                "which database?",
            ),
        )
        with seam_patch("_has_new_commits", lambda *_args: True):
            for described, state, message in answered:
                with self.subTest(refusal=described):
                    self.assertFalse(_delivery.redelivers_an_owed_report(
                        _TEST_SPEC, state, _agent(last_message=message),
                        _FAKE_WT,
                    ))

        with seam_patch("_has_new_commits", lambda *_args: False):
            self.assertFalse(_delivery.redelivers_an_owed_report(
                _TEST_SPEC,
                PinnedState(state_data=dict(delivery_support.OWED)),
                _agent(last_message=delivery_support.ready(delivery_support.DELIVERED.report)),
                _FAKE_WT,
            ))


if __name__ == "__main__":
    unittest.main()
