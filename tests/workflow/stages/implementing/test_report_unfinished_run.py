# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""A run that did not finish, over a report an earlier run recorded.

That report describes the branch as the run that wrote it left it, so a commit
a later run added and never reported is held before anything is pushed: the
report stays recorded and is never bound to that commit, and the report the
reply brings back is the one published over the branch as it stands. With no
report at all, the requirements the run was handed are still read again before
the handoff, and an edit made while it ran holds the work for the drift resume.
The waiver an unfinished run earns, and its retirement by a report, are durable
before the size gate, so a process dying there leaves a recovery that reads them
right.
"""

from __future__ import annotations

import unittest
from types import MappingProxyType
from unittest.mock import patch

from orchestrator.git.measurement.models import FrozenCommit
from orchestrator.workflow.engine import (
    report_delivery as _report_delivery,
    report_delivery_state as _delivery_state,
    report_records as _records,
)
from orchestrator.workflow.stages.implementing import late_gate as _late_gate
from tests.workflow.fixtures import (
    _TEST_SPEC,
    LABEL_VALIDATING,
    SHA_LENGTH,
    _agent,
    _named_description,
    _open_pr_for,
)
from tests.workflow.stages.implementing import report_test_support as support

REUSED_PR = 71

# The pull request a fresh publication opens: this client numbers them from 1.
OPENED_PR = 1

RUN_AGENT = "run_agent"

# What a human changes the issue to while a run works, and the resumed
# session's answer to that edit, which changes nothing on the branch.
EDITED_BODY = "the requirements moved while the run worked"

ACKED = "ACK: nothing in the edit changes the branch"

PUSH_BRANCH = "_push_branch"

AWAITING_HUMAN = "awaiting_human"

PARK_REASON = "park_reason"

# The waiver an unfinished run's commit earns, and the size gate a process dies
# in with it just decided.
INCOMPLETE_RUN = "implementing_incomplete_run_sha"

HOLDS_COMMITTED_WORK = "_holds_committed_work"

# An issue an unfinished run's commit left owing a report: the waiver naming
# that commit, and the park a reply to which resumes the session.
UNFINISHED_AND_OWED = MappingProxyType({
    INCOMPLETE_RUN: support.PUBLISHED_SHA,
    _report_delivery.OWED_REPORT: True,
    PARK_REASON: _report_delivery.UNDELIVERABLE_REPORT,
    AWAITING_HUMAN: True,
    support.WATERMARK: 100,
    "dev_agent": "claude",
    "dev_session_id": support.DEV_SESSION,
})

# Where the first run started, and the commit it reported on. The resumed
# session's commit lands on the one the ordinary world publishes.
STARTING_SHA = "b" * SHA_LENGTH

REPORTED_SHA = "d" * SHA_LENGTH

# A description an operator wrote, naming nothing this implementation needs,
# and the same description once a human has put the two lines above it.
UNNAMED = "### Notes\n\nOpened by hand."

NAMED = "\n\n".join((
    _named_description(support.REPORT_ISSUE, support.DEV_SESSION), UNNAMED,
))

REPLACEMENT_REPORT = "Adds the thing, including what the resumed session committed."


class UnfinishedRunTest(unittest.TestCase, support._ReportDeliveryMixin):
    def test_a_timed_out_resume_is_held_unbound(self) -> None:
        # The reused description named nothing, so the report stayed unbound;
        # a human named it and replied, and the resumed session committed and
        # timed out. Bound to that commit, the report would answer
        # requirements the reply moved and be retried with no park.
        github, issue, reused = self._parked_on_an_unnamed_description()
        reused.body = NAMED
        support.replies(github, issue, "named the description")

        self._times_out(github, issue)[PUSH_BRANCH].assert_not_called()
        self._assert_held_unbound(github)
        support.replies(github, issue, "please report what the branch carries")

        self.redeliver(github, issue, support.ready_message(REPLACEMENT_REPORT))

        posted = support.published_reports(github, REUSED_PR, 2)
        pinned = github.pinned_data(support.REPORT_ISSUE)
        self.assertEqual(
            (
                len(posted),
                REPLACEMENT_REPORT in posted[0].body,
                pinned[support.CURRENT_RECORD]["sha"],
                reused.body,
            ),
            (1, True, support.PUBLISHED_SHA, NAMED),
        )
        self.assertIn(
            (support.REPORT_ISSUE, LABEL_VALIDATING), github.label_history,
        )

    def test_an_earlier_record_holds_the_commit(self) -> None:
        # Unbound, or bound as a transaction about the commit before it: both
        # describe that commit, so neither goes out over the new one.
        for recorded in (support.owing_state(), _bound_to_the_reported_commit()):
            with self.subTest(records=sorted(recorded.state_data)):
                github, issue = self.seeded()
                github.seed_state(
                    support.REPORT_ISSUE,
                    dev_session_id=support.DEV_SESSION,
                    **recorded.state_data,
                )

                mocks = self._times_out(
                    github, issue, has_new_commits=[False, True],
                )

                mocks[PUSH_BRANCH].assert_not_called()
                pinned = github.pinned_data(support.REPORT_ISSUE)
                self.assertEqual(
                    {key: pinned.get(key) for key in recorded.state_data},
                    recorded.state_data,
                )
                self.assertEqual(
                    (pinned[AWAITING_HUMAN], pinned[PARK_REASON]),
                    (True, _report_delivery.UNDELIVERABLE_REPORT),
                )

    def test_a_moved_issue_holds_an_unfinished_commit(self) -> None:
        # A run that did not finish records no report, so no settled report
        # holds the requirements to anything -- and a human edited the issue
        # while it ran. Read again last, that edit holds the handoff unparked;
        # the same run over an issue nobody edited is handed on.
        for edited in (False, True):
            with self.subTest(edited=edited):
                github, issue = self.seeded()
                run = _EditsTheIssue(issue) if edited else _agent(
                    session_id=support.DEV_SESSION, timed_out=True,
                )

                self._times_out(
                    github, issue, run_agent=run, has_new_commits=[False, True],
                )

                pinned = github.pinned_data(support.REPORT_ISSUE)
                self.assertEqual(
                    (
                        len(github.opened_prs),
                        bool(pinned.get(AWAITING_HUMAN)),
                        (support.REPORT_ISSUE, LABEL_VALIDATING)
                        in github.label_history,
                    ),
                    (1, False, not edited),
                )

    def test_the_drift_resume_answers_that_hold(self) -> None:
        # Held, the handoff is owed rather than parked, so the drift check the
        # next tick opens with resumes the session against the edit rather
        # than republishing into the same hold; once it answers, the tick after
        # republishes onto the same pull request and hands it on.
        github, issue = self.seeded()
        self._times_out(
            github, issue,
            run_agent=_EditsTheIssue(issue), has_new_commits=[False, True],
        )
        github.get_pr(OPENED_PR).head.sha = support.PUBLISHED_SHA
        settled = (support.PUBLISHED_SHA, support.PUBLISHED_SHA)

        self._times_out(
            github, issue, head_shas=settled,
            run_agent=_agent(session_id=support.DEV_SESSION, last_message=ACKED),
        )[RUN_AGENT].assert_called_once()
        self.assertEqual(github.label_history, [])
        self.republish(github, issue, head_shas=settled)

        self.assertEqual(
            (len(github.opened_prs), github.label_history),
            (1, [(support.REPORT_ISSUE, LABEL_VALIDATING)]),
        )

    def _parked_on_an_unnamed_description(self):
        """Publish the first commit onto a pull request that names nothing."""
        github, issue = self.seeded()
        reused = _open_pr_for(
            github, issue_number=support.REPORT_ISSUE, pr_number=REUSED_PR,
        )
        reused.body = UNNAMED
        github.existing_open_pr[support.BRANCH] = reused
        self.deliver(
            github, issue, support.ready_message(),
            head_shas=(STARTING_SHA, REPORTED_SHA),
            candidate_commit=FrozenCommit(sha=REPORTED_SHA),
        )
        self._assert_held_unbound(github)
        reused.head.sha = REPORTED_SHA
        return github, issue, reused

    def _times_out(self, github, issue, **run_options):
        """A developer run that commits onto the reported one and is killed."""
        return self._run_implementing(
            github, issue,
            **{
                "run_agent": _agent(
                    session_id=support.DEV_SESSION, timed_out=True,
                ),
                "has_new_commits": True,
                "head_shas": (REPORTED_SHA, support.PUBLISHED_SHA),
                "dirty_files": (),
                "push_branch": True,
                **run_options,
            },
        )

    def _assert_held_unbound(self, github) -> None:
        """The first report recorded and unbound, and the work parked for it."""
        pinned = github.pinned_data(support.REPORT_ISSUE)
        self.assertEqual(
            (
                pinned[support.DELIVERY_RECORD]["revision"],
                pinned.get(support.PENDING_RECORD),
                pinned[AWAITING_HUMAN],
                pinned[PARK_REASON],
            ),
            (1, None, True, _report_delivery.UNDELIVERABLE_REPORT),
        )
        self.assertNotIn(
            (support.REPORT_ISSUE, LABEL_VALIDATING), github.label_history,
        )


class InterruptedGateTest(unittest.TestCase, support._ReportDeliveryMixin):
    """A process that dies in the size gate, around the incomplete-run waiver."""

    def test_a_waiver_survives_a_crash(self) -> None:
        # A run that did not finish committed clean work, and the process died
        # in the size gate. The waiver naming that commit is already on the
        # pinned comment, so the recovery after the restart publishes it
        # rather than holding it as work whose report was lost.
        github, issue = self.seeded()

        self._dies_in_the_gate(
            github, issue,
            run_agent=_agent(session_id=support.DEV_SESSION, timed_out=True),
            has_new_commits=[False, True],
            head_shas=(REPORTED_SHA, support.PUBLISHED_SHA),
        )

        self.assertEqual(
            github.pinned_data(support.REPORT_ISSUE)[INCOMPLETE_RUN],
            support.PUBLISHED_SHA,
        )
        self._restarts_into_review(github, issue)

    def test_a_retired_waiver_stays_retired(self) -> None:
        # A report-only reply over the waiver an unfinished run left: the
        # report it records retires the waiver in the same write, so a process
        # dying in the gate cannot leave the new report beside a waiver that
        # would read it as an older run's.
        github, issue = self.seeded()
        github.seed_state(support.REPORT_ISSUE, **UNFINISHED_AND_OWED)
        support.replies(github, issue)

        self._dies_in_the_gate(
            github, issue,
            run_agent=_agent(
                session_id=support.DEV_SESSION,
                last_message=support.ready_message(),
            ),
            head_shas=(support.PUBLISHED_SHA, support.PUBLISHED_SHA),
        )

        pinned = github.pinned_data(support.REPORT_ISSUE)
        self.assertEqual(
            (pinned[INCOMPLETE_RUN], pinned[support.DELIVERY_RECORD]["revision"]),
            (None, 1),
        )
        self._restarts_into_review(github, issue)

    def _dies_in_the_gate(self, github, issue, **run_options) -> None:
        """Run one tick whose process exits as the size gate is entered."""
        dies = patch.object(
            _late_gate, HOLDS_COMMITTED_WORK, side_effect=SystemExit,
        )
        with dies, self.assertRaises(SystemExit):
            self._run_implementing(github, issue, **{
                "has_new_commits": True,
                "dirty_files": (),
                "push_branch": True,
                **run_options,
            })

    def _restarts_into_review(self, github, issue) -> None:
        """The tick after the restart publishes with no run, and hands on."""
        settled = (support.PUBLISHED_SHA, support.PUBLISHED_SHA)

        self.republish(github, issue, head_shas=settled)[RUN_AGENT].assert_not_called()

        self.assertEqual(
            (
                bool(github.pinned_data(support.REPORT_ISSUE).get(AWAITING_HUMAN)),
                github.label_history,
            ),
            (False, [(support.REPORT_ISSUE, LABEL_VALIDATING)]),
        )


class _EditsTheIssue:
    """A developer run a human edits the issue under before it is killed."""

    def __init__(self, issue) -> None:
        self._issue = issue

    def __call__(self, *_args, **_kwargs):
        """Edit the issue's body, then answer as the run the timeout killed."""
        self._issue.body = EDITED_BODY
        return _agent(session_id=support.DEV_SESSION, timed_out=True)


def _bound_to_the_reported_commit():
    """The delivered report, bound as a transaction about the reported commit."""
    bound = support.owing_state()
    _delivery_state.binds_delivered_report(
        bound,
        _delivery_state.read_delivered_report(bound),
        _records.ReportSubject(
            repo_slug=_TEST_SPEC.slug,
            pr_number=REUSED_PR,
            branch=support.BRANCH,
            source_sha=REPORTED_SHA,
            requirements_revision=support.REQUIREMENTS_REVISION,
        ),
    )
    return bound


if __name__ == "__main__":
    unittest.main()
