# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The report a run wrote and the pinned write never carried.

The window the recording exists to close, seen from the far side of it. A
finished run's report is written down before the size gate and before the push,
because that record is the only copy there is once the session ends -- and the
one request that write is can still fail, or the process can die inside it.
What that leaves is a branch carrying committed work and an issue with nothing
on it saying what the run did.

The tick after it recovers those commits and spawns nothing, since they are a
previous run's. Published there, a reviewer would be handed an implementation
nobody described, with no session left to ask; held, it is the same park every
other undeliverable report takes and the same reply answers it -- the developer
is resumed, writes the report again, and the commits already on the branch go
out under it.
"""

from __future__ import annotations

import unittest
from unittest.mock import patch

from orchestrator.github import developer_reports as _reports
from orchestrator.github.pinned_state import PinnedState
from orchestrator.github.pull_request_reports import ReportLocation
from orchestrator.workflow.engine import (
    report_delivery as _report_delivery,
    report_records as _records,
    report_settlement_state as _settlement,
)
from orchestrator.workflow.stages.implementing import state as _state
from tests.workflow.fixtures import (
    _TEST_SPEC,
    LABEL_VALIDATING,
    MEASURED_CANDIDATE_SHA,
    SHA_LENGTH,
)
from tests.workflow.stages.implementing import (
    late_gate_test_support as gate_support,
    report_test_support as support,
)

# The pull request the recovery finally opens: this client numbers the ones it
# opens from 1.
OPENED_PR = 1

PUSH_BRANCH = "_push_branch"

RUN_AGENT = "run_agent"

AWAITING_HUMAN = "awaiting_human"

PARK_REASON = "park_reason"

WRITE_PINNED_STATE = "write_pinned_state"

DEV_BACKEND = "claude"

# The report the resumed session writes in place of the one nothing recorded.
REPLACEMENT_REPORT = "Adds the thing, reported inline this time."

# What an earlier publication settled its report about: a commit the branch
# has since moved past, and the pull request that carried it.
OLDER_SHA = "d" * SHA_LENGTH

SETTLED_PR = 7

# The pull request the last push went onto, where that is not the one the
# settled report is on.
RECEIPT_PR = 8

# The comment the settled report is recorded at.
SETTLED_COMMENT = 8800

# The commit an approval says is owed a push.
APPROVED_SHA = "late_approved_sha"


class LostReportRecordTest(unittest.TestCase, support._ReportDeliveryMixin):
    def test_a_lost_record_holds_the_recovery(self) -> None:
        # The window the recording exists to close, seen from the far side of
        # it. The run finished and committed, and the write that would have
        # put its report on the pinned comment never landed. The next tick
        # finds the commits, spawns nothing -- they are a previous run's --
        # and has nothing on the issue saying what that run did.
        github, issue = self._lost_the_report_write()

        mocks = self.republish(github, issue)

        mocks[RUN_AGENT].assert_not_called()
        self._assert_held(github, mocks)

    def test_a_lost_record_is_redelivered(self) -> None:
        # And what that park buys, which is the same thing every other one
        # here buys: the reply resumes the session, the report it writes is
        # recorded, and the commits already on the branch go out under it --
        # one pull request, no second developer run over work the first one
        # already finished.
        github, issue = self._lost_the_report_write()
        self.republish(github, issue)
        support.replies(github, issue, "please report it again")

        self.redeliver(
            github, issue, support.ready_message(REPLACEMENT_REPORT),
        )

        posted = support.published_reports(github, OPENED_PR)
        self.assertEqual(len(posted), 1)
        self.assertIn(REPLACEMENT_REPORT, posted[0].body)
        recorded = github.pinned_data(support.REPORT_ISSUE)
        self.assertEqual(
            (
                len(github.opened_prs),
                recorded[support.DELIVERY_RECORD],
                recorded[support.PENDING_RECORD],
                recorded.get(AWAITING_HUMAN),
            ),
            (1, None, None, False),
        )
        self.assertIn(
            (support.REPORT_ISSUE, LABEL_VALIDATING), github.label_history,
        )
    def test_a_stale_settlement_holds_the_recovery(self) -> None:
        # A settlement is never cleared, so the pair an earlier publication
        # left reads as well as this commit's would. Only one about THIS head,
        # on the pull request the receipt says it was pushed onto, says its
        # report already went out; any other sends the commit to review with
        # no report on it describing the work.
        for described, settled in (
            ("an older commit", _settled_state(OLDER_SHA, SETTLED_PR)),
            (
                "another pull request",
                _settled_state(support.PUBLISHED_SHA, RECEIPT_PR),
            ),
        ):
            with self.subTest(settlement=described):
                github, issue = self.seeded()
                github.seed_state(
                    support.REPORT_ISSUE,
                    dev_agent=DEV_BACKEND,
                    dev_session_id=support.DEV_SESSION,
                    **settled,
                )

                self._assert_held(github, self.republish(
                    github, issue,
                    head_shas=(support.PUBLISHED_SHA, support.PUBLISHED_SHA),
                ))

    def _assert_held(self, github, mocks) -> None:
        """Prove the recovery published nothing and parked for a report."""
        mocks[PUSH_BRANCH].assert_not_called()
        recorded = github.pinned_data(support.REPORT_ISSUE)
        self.assertEqual(
            (
                github.opened_prs,
                recorded.get(AWAITING_HUMAN),
                recorded.get(PARK_REASON),
            ),
            ([], True, _report_delivery.UNDELIVERABLE_REPORT),
        )
        self.assertNotIn(
            (support.REPORT_ISSUE, LABEL_VALIDATING), github.label_history,
        )

    def _lost_the_report_write(self):
        """One tick whose run reported, and whose pinned write never landed.

        The session is on the comment before any of it, because it is durable
        from the run that FIRST recorded it and this window is about one write
        rather than about a session: with one, the reply that answers the park
        resumes the developer that can write the report again.
        """
        github, issue = self.seeded()
        github.seed_state(
            support.REPORT_ISSUE,
            dev_agent=DEV_BACKEND,
            dev_session_id=support.DEV_SESSION,
        )
        losing = patch.object(
            github, WRITE_PINNED_STATE, _LosesTheReportWrite(github),
        )
        with losing, self.assertRaises(RuntimeError):
            self.deliver(github, issue, support.ready_message())
        self.assertNotIn(
            support.DELIVERY_RECORD, github.pinned_data(support.REPORT_ISSUE),
        )
        return github, issue

class UnreportedCandidateTest(gate_support._GateCase, unittest.TestCase):
    """A candidate a gate record names, with no report of the run behind it."""

    def test_an_unreported_candidate_is_held(self) -> None:
        # Every road that republishes a candidate a gate record named is a
        # recovery: no developer runs, so what describes the commit is on the
        # comment or nowhere. With nothing there -- no delivery, no
        # transaction, no settled pair about it -- publishing it would hand
        # review an implementation nobody described.
        for record, seeded in (
            ("an approved commit", {APPROVED_SHA: MEASURED_CANDIDATE_SHA}),
            ("a frozen candidate", gate_support.recorded_generation()),
        ):
            with self.subTest(record=record):
                self.setUp()
                self._seed(**{support.DELIVERY_RECORD: None, **seeded})

                mocks = self._run_gate()

                self._assert_no_agent(mocks)
                self._assert_held(mocks)
                pinned = self._pinned()
                self.assertEqual(
                    (
                        pinned[AWAITING_HUMAN],
                        pinned[PARK_REASON],
                        self.github.label_history,
                    ),
                    (True, _report_delivery.UNDELIVERABLE_REPORT, []),
                )


def _settled_state(source_sha: str, pushed_to: int) -> dict:
    """What a publication that settled its report on `SETTLED_PR` leaves behind.

    The pair names the commit its report is about; the receipt beside it names
    the pull request the last push of `source_sha` went onto. A recovery reads
    the three together, so a case moves one of them.
    """
    state = PinnedState()
    _settlement.record_current_report(state, _records.CurrentReport(
        subject=_records.ReportSubject(
            repo_slug=_TEST_SPEC.slug,
            pr_number=SETTLED_PR,
            branch=support.BRANCH,
            source_sha=source_sha,
            requirements_revision=support.REQUIREMENTS_REVISION,
        ),
        report_revision=1,
        content_revision=_reports.content_digest(support.REPORT_TEXT),
        location=ReportLocation(pr_number=SETTLED_PR, comment_id=SETTLED_COMMENT),
    ))
    _settlement.record_handoff(state, _records.ReportHandoff(
        receipt=f"issue-{support.REPORT_ISSUE}-report-1",
        pr_number=SETTLED_PR,
        report_revision=1,
        source_sha=source_sha,
    ))
    return {
        **state.state_data,
        _state._PUBLISHED_SHA: source_sha,
        _state._PUBLISHED_PR: pushed_to,
        _state._PUBLISHED_LEASE: None,
    }


class _LosesTheReportWrite:
    """A pinned write that fails exactly where the report record goes down.

    Every other write of the tick lands, which is what makes this the window
    rather than an issue nothing could write to at all: the run was charged,
    the session recorded, the commit made -- and the one request carrying the
    report is the one that did not come back. A process killed in that call
    leaves the same thing behind.
    """

    def __init__(self, github) -> None:
        self._wrote = github.write_pinned_state

    def __call__(self, issue, state):
        """Write, unless this is the write that carries the report."""
        if state.get(support.DELIVERY_RECORD) is not None:
            raise RuntimeError("the pinned write never landed")
        return self._wrote(issue, state)


if __name__ == "__main__":
    unittest.main()
