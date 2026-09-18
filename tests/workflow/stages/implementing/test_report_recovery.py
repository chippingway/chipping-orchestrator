# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""A report that did not reach its pull request, and what the stage does then.

The ordinary window is the one every publication has: the branch is on the
remote, a pull request carries it, and what is left -- binding the report to
that publication, re-reading the issue it answers, reading the thread and
posting to it -- is a run of separate requests any of which GitHub can refuse,
or accept without saying so. What the stage owes there is to keep the work
exactly where it is -- unhanded-on, unparked, and recorded as still owing a
report -- so the next poll finishes it with no developer run, no second pull
request, and no second report. That retry
runs over the world the first tick left, which is the world the size gate calls
DELIVERED: the receipt names the commit, and the pull request is standing on
it, so the push moves nothing and the bookkeeping is all that is left.

The other road here is the requirements moving while the run that reported on
them worked. Nothing is published then either: the report answers an issue that
has changed, and what supersedes it is the resume the edit earns.

A report this workflow cannot deliver AT ALL is the neighbouring module's,
`test_report_undeliverable`: those roads publish no code either, and what
answers them is a reply rather than a poll.
"""

from __future__ import annotations

import unittest
from contextlib import contextmanager
from unittest.mock import patch

from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.engine import (
    report_delivery as _report_delivery,
    report_delivery_state as _delivery_state,
)
from tests.workflow.fixtures import LABEL_VALIDATING, _agent
from tests.workflow.stages.implementing import report_test_support as support

# The pull request the first tick opens: this client numbers the ones it opens
# from 1, and the failure a case is about has to be registered against a number
# before the request that meets it is made.
OPENED_PR = 1

RUN_AGENT = "run_agent"

PUBLISHED_SHA_KEY = "implementing_published_sha"

AWAITING_HUMAN = "awaiting_human"

PUSH_BRANCH = "_push_branch"

# The edit a human makes to the issue while a run is working.
EDITED_BODY = "the requirements moved while the agent was running"

# What a human replaces the pull request's description with while its report
# is still owed.
EDITED_DESCRIPTION = "Rewritten by hand while the report was owed."


class ReportDebtTest(unittest.TestCase, support._ReportDeliveryMixin):
    def test_a_failure_after_the_push_is_retried(self) -> None:
        # Every way the report can fail to settle once the code is out: the
        # binding refused for room, the thread unreadable, the post refused,
        # and the issue that could not be re-read for its requirements. Each
        # leaves the code published and the debt recorded -- unhanded-on and
        # unparked, since nothing here needs a human -- and the next poll
        # finishes it on the same commit and the same pull request.
        for described, failing in _FAILURES_AFTER_THE_PUSH:
            with self.subTest(failure=described):
                github, issue = self.seeded()
                with failing(github):
                    self.deliver(github, issue, support.ready_message())

                recorded = github.pinned_data(support.REPORT_ISSUE)
                self.assertEqual(
                    (
                        len(github.opened_prs),
                        recorded[PUBLISHED_SHA_KEY],
                        support.published_reports(github, OPENED_PR),
                        bool(recorded.get(AWAITING_HUMAN)),
                    ),
                    (1, support.PUBLISHED_SHA, [], False),
                )
                self.assertTrue(_report_delivery.owes_a_report(
                    PinnedState(state_data=recorded),
                ))
                self.assertNotIn(
                    (support.REPORT_ISSUE, LABEL_VALIDATING),
                    github.label_history,
                )
                self._retry_settles(github, issue)

    def test_a_lost_response_is_not_reposted(self) -> None:
        # GitHub accepted the comment and the answer never came back, so the
        # first tick cannot say the report is there. The retry reads the thread
        # by this transaction's receipt and finds what landed.
        github, issue = self.seeded()
        github.report_failures.lost.add(OPENED_PR)

        self.deliver(github, issue, support.ready_message())
        landed = support.published_reports(github, OPENED_PR)
        self.assertEqual(len(landed), 1)
        github.get_pr(OPENED_PR).head.sha = support.PUBLISHED_SHA

        self.republish(github, issue)

        self.assertEqual(len(support.published_reports(github, OPENED_PR)), 1)
        recorded = github.pinned_data(support.REPORT_ISSUE)
        self.assertIsNone(recorded[support.PENDING_RECORD])
        # The comment this orchestrator posted is recorded as the report's own
        # location and in its own comment ledger, so no later scan reads the
        # report back as somebody's fresh feedback.
        self.assertEqual(
            (
                recorded[support.CURRENT_RECORD]["location_comment"],
                landed[0].id in recorded["orchestrator_comment_ids"],
            ),
            (landed[0].id, True),
        )
        self.assertIn(
            (support.REPORT_ISSUE, LABEL_VALIDATING), github.label_history,
        )

    def test_edited_requirements_hold_the_report(self) -> None:
        # A human edited the issue while the developer worked, so the report
        # answers requirements the issue no longer has. Publishing it would
        # stamp it with the revision its run was handed and hand it to a
        # reviewer as current, so it is left owed for the drift resume -- and
        # the work is not handed on either.
        github, issue = self.seeded()

        self._run_implementing(
            github,
            issue,
            run_agent=_EditsTheIssue(issue, support.ready_message()),
            has_new_commits=[False, True],
            dirty_files=(),
            push_branch=True,
        )

        self.assertEqual(len(github.opened_prs), 1)
        self.assertEqual(support.published_reports(github, OPENED_PR), [])
        recorded = github.pinned_data(support.REPORT_ISSUE)
        self.assertIsNotNone(recorded[support.PENDING_RECORD])
        self.assertNotIn(support.CURRENT_RECORD, recorded)
        self.assertNotIn(
            (support.REPORT_ISSUE, LABEL_VALIDATING), github.label_history,
        )

    def _retry_settles(self, github, issue) -> None:
        """Run the next poll and prove it published what the first one owed.

        A human replaces the pull request's description in the window, which
        is as long as the report stays owed. The retry is finishing a
        publication rather than making one, so what they wrote stays.
        """
        # What the push left on the remote, which is what makes this the
        # gate's delivered road: the pull request is standing on the commit
        # the receipt names, so the retry publishes nothing new.
        opened = github.get_pr(OPENED_PR)
        opened.head.sha = support.PUBLISHED_SHA
        opened.body = EDITED_DESCRIPTION

        mocks = self.republish(github, issue)

        mocks[RUN_AGENT].assert_not_called()
        # Leased against the commit itself, which only the delivered road
        # does: the gate admitted the candidate because that pull request is
        # already standing on it, so the push sends nothing and a tip somebody
        # moved in the window is refused rather than force-overwritten.
        self.assertEqual(
            mocks[PUSH_BRANCH].call_args.kwargs["force_with_lease"],
            support.PUBLISHED_SHA,
        )
        recorded = github.pinned_data(support.REPORT_ISSUE)
        self.assertEqual(
            (
                len(github.opened_prs),
                len(support.published_reports(github, OPENED_PR)),
                recorded[support.DELIVERY_RECORD],
                recorded[support.PENDING_RECORD],
                recorded[support.CURRENT_RECORD]["pr"],
                opened.body,
            ),
            (1, 1, None, None, OPENED_PR, EDITED_DESCRIPTION),
        )
        self.assertIn(
            (support.REPORT_ISSUE, LABEL_VALIDATING), github.label_history,
        )


@contextmanager
def _unanswered(failures: set[int]):
    """Leave one kind of report request on the opened pull request unanswered."""
    failures.add(OPENED_PR)
    try:
        yield
    finally:
        failures.discard(OPENED_PR)


def _crowded_binding(_github):
    """Refuse the binding for room, as a comment grown past its reservation is."""
    return patch.object(
        _delivery_state,
        "binds_delivered_report",
        return_value=_delivery_state.CROWDED_COMMENT,
    )


def _unread_issue(github):
    """Fail every read of the issue made once its pull request is open."""
    return patch.object(github, "get_issue", _UnreadOnceOpened(github))


class _UnreadOnceOpened:
    """An issue read GitHub leaves unanswered once the pull request exists.

    Only then, because the re-read this is about is the one taken after the
    push: the reads that open the tick are what the report is stamped against.
    """

    def __init__(self, github) -> None:
        self._github = github
        self._reads = github.get_issue

    def __call__(self, number):
        """Read the issue, unless the publication has already opened its PR."""
        if self._github.opened_prs:
            raise RuntimeError("GitHub did not answer the issue read")
        return self._reads(number)


_FAILURES_AFTER_THE_PUSH = (
    ("a refused binding", _crowded_binding),
    (
        "an unreadable thread",
        lambda github: _unanswered(github.report_failures.unreadable),
    ),
    (
        "a refused post",
        lambda github: _unanswered(github.report_failures.refused),
    ),
    ("an unread issue", _unread_issue),
)


class _EditsTheIssue:
    """A developer run a human edits the issue's body underneath.

    The edit lands where the window this is about is: after the drift check
    that opened the tick and before anything the publication reads, which is
    exactly a human typing while an agent works.
    """

    def __init__(self, issue, message: str) -> None:
        self._issue = issue
        self._message = message

    def __call__(self, *_args, **_kwargs):
        """Edit the issue, then answer as the run that reported on it."""
        self._issue.body = EDITED_BODY
        return _agent(
            session_id=support.DEV_SESSION, last_message=self._message,
        )


if __name__ == "__main__":
    unittest.main()
