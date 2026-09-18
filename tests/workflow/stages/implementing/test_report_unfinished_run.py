# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""A run that did not finish, over a report an earlier run recorded.

That report describes the branch as the run that wrote it left it, so a commit
a later run added and never reported is held before anything is pushed: the
report stays recorded and is never bound to that commit, and the report the
reply brings back is the one published over the branch as it stands.
"""

from __future__ import annotations

import unittest

from orchestrator.git.measurement.models import FrozenCommit
from orchestrator.github.pinned_state import MAX_PINNED_BODY
from orchestrator.workflow.engine import (
    report_delivery as _report_delivery,
    report_delivery_state as _delivery_state,
    report_records as _records,
)
from tests.workflow.fixtures import (
    _TEST_SPEC,
    LABEL_VALIDATING,
    SHA_LENGTH,
    _agent,
    _open_pr_for,
)
from tests.workflow.stages.implementing import report_test_support as support

REUSED_PR = 71

PUSH_BRANCH = "_push_branch"

AWAITING_HUMAN = "awaiting_human"

PARK_REASON = "park_reason"

# Where the first run started, and the commit it reported on. The resumed
# session's commit lands on the one the ordinary world publishes.
STARTING_SHA = "b" * SHA_LENGTH

REPORTED_SHA = "d" * SHA_LENGTH

# A description the two lines this implementation needs would take past
# GitHub's ceiling, and the same description once a human has shortened it.
NEAR_THE_CEILING = "x" * (MAX_PINNED_BODY - 10)

SHORTENED = "### Notes\n\nShortened by hand."

REPLACEMENT_REPORT = "Adds the thing, including what the resumed session committed."


class UnfinishedRunTest(unittest.TestCase, support._ReportDeliveryMixin):
    def test_a_timed_out_resume_is_held_unbound(self) -> None:
        # The reused description was too long to name, so the report stayed
        # unbound; a human shortened it and replied, and the resumed session
        # committed and timed out. Bound to that commit, the report would
        # answer requirements the reply moved and be retried with no park.
        github, issue, reused = self._parked_on_a_long_description()
        reused.body = SHORTENED
        support.replies(github, issue, "shortened the description")

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
                reused.body.startswith(f"Resolves #{support.REPORT_ISSUE}"),
            ),
            (1, True, support.PUBLISHED_SHA, True),
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

    def _parked_on_a_long_description(self):
        """Publish the first commit onto a pull request too long to name."""
        github, issue = self.seeded()
        reused = _open_pr_for(
            github, issue_number=support.REPORT_ISSUE, pr_number=REUSED_PR,
        )
        reused.body = NEAR_THE_CEILING
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
            run_agent=_agent(session_id=support.DEV_SESSION, timed_out=True),
            **{
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
