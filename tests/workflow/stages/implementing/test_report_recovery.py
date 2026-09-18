# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""A report that did not reach its pull request, and what the stage does then.

After the push, binding the report, re-reading the issue, and reading and
posting to the thread are separate requests GitHub can refuse. The stage keeps
the work unhanded-on and the debt recorded, so the next poll finishes it with no
developer run, no second pull request, and no second report -- unless no retry
can settle it, which parks. An edit to the requirements holds the report for the
drift resume. `test_report_undeliverable` covers reports never deliverable.
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
from tests.support.fakes import FakeComment, FakeUser
from tests.workflow.fixtures import LABEL_VALIDATING, _agent, _open_pr_for
from tests.workflow.stages.implementing import report_test_support as support

# The pull request the first tick opens: this client numbers the ones it opens
# from 1, and the failure a case is about has to be registered against a number
# before the request that meets it is made.
OPENED_PR = 1

RUN_AGENT = "run_agent"

PUBLISHED_SHA_KEY = "implementing_published_sha"

AWAITING_HUMAN = "awaiting_human"

PARK_REASON = "park_reason"

PUSH_BRANCH = "_push_branch"

# The edit a human makes to the issue while a run is working.
EDITED_BODY = "the requirements moved while the agent was running"

# The two requests a transaction's settlement waits on: the post a PUBLISH makes,
# and the re-read a VERIFY takes of the location it names.
POST_REPORT = "_post_report"

REREAD_REPORT = "reread_report_location"

# The pull request already open on the branch whose comment a developer
# verified, and that comment.
VERIFIED_PR = 55

VERIFIED_COMMENT = 9100

# What a human replaces the pull request's description with while its report
# is still owed.
EDITED_DESCRIPTION = "Rewritten by hand while the report was owed."


class ReportDebtTest(unittest.TestCase, support._ReportDeliveryMixin):
    def test_a_failure_after_the_push_is_retried(self) -> None:
        # A binding refused for room, an unreadable thread, a refused post, an
        # unread issue: each leaves the debt recorded, unhanded-on and unparked,
        # and the next poll finishes it on the same commit and pull request.
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
        # An edit while the developer worked leaves the report answering old
        # requirements, so it is left owed for the drift resume, unhanded-on.
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

    def test_an_edit_during_the_request_is_left_owed(self) -> None:
        # An edit landing while GitHub answers the post or the re-read is after
        # every earlier reading, so the settlement reads the issue once more.
        for request in (POST_REPORT, REREAD_REPORT):
            with self.subTest(request=request):
                github, issue = self.seeded()
                during = _EditsTheIssueDuring(issue, getattr(github, request))

                with patch.object(github, request, during):
                    self.deliver(
                        github, issue, self._reporting_for(github, request),
                    )

                recorded = github.pinned_data(support.REPORT_ISSUE)
                self.assertEqual(
                    (
                        during.calls > 0,
                        recorded[support.PENDING_RECORD] is not None,
                        support.CURRENT_RECORD in recorded,
                    ),
                    (True, True, False),
                )
                self.assertNotIn(
                    (support.REPORT_ISSUE, LABEL_VALIDATING),
                    github.label_history,
                )

    def test_a_report_that_cannot_settle_parks(self) -> None:
        # A report no retry can settle -- a lost response whose comment a human
        # then edited, a verified comment since deleted -- parks for the reply
        # that resumes the session to write it again, rather than being retried
        # unannounced for as long as the issue lives.
        for verified in (False, True):
            with self.subTest(verified=verified):
                github, issue = self.seeded()
                if verified:
                    message = self._reporting_for(github, REREAD_REPORT)
                    github.get_pr(VERIFIED_PR).issue_comments.clear()
                    self.deliver(github, issue, message)
                else:
                    github.report_failures.lost.add(OPENED_PR)
                    self.deliver(github, issue, support.ready_message())
                    github.report_failures.lost.clear()
                    github.get_pr(OPENED_PR).head.sha = support.PUBLISHED_SHA
                    comment = github.get_pr(OPENED_PR).issue_comments[-1]
                    comment.body = comment.body.replace(
                        support.REPORT_TEXT, "Edited by hand.",
                    )
                    self.republish(github, issue)

                self.assertEqual(
                    (
                        github.pinned_data(support.REPORT_ISSUE)[AWAITING_HUMAN],
                        github.pinned_data(support.REPORT_ISSUE)[PARK_REASON],
                    ),
                    (True, _report_delivery.UNDELIVERABLE_REPORT),
                )
                self.assertNotIn(
                    (support.REPORT_ISSUE, LABEL_VALIDATING), github.label_history,
                )

    def _reporting_for(self, github, request: str) -> str:
        """The report outcome whose settlement waits on `request`.

        A post needs only a report to publish. A re-read needs a location, so
        a pull request carrying a human's report is opened and that is what
        the developer verifies.
        """
        if request == POST_REPORT:
            return support.ready_message()
        reused = _open_pr_for(
            github, issue_number=support.REPORT_ISSUE, pr_number=VERIFIED_PR,
        )
        github.existing_open_pr[support.BRANCH] = reused
        reused.issue_comments.append(FakeComment(
            id=VERIFIED_COMMENT, body=support.REPORT_TEXT, user=FakeUser("alice"),
        ))
        return support.verified_message(
            VERIFIED_PR, support.REPORT_TEXT, comment_id=VERIFIED_COMMENT,
        )

    def _retry_settles(self, github, issue) -> None:
        """Run the next poll and prove it published what the first one owed.

        A human replaces the pull request's description in the window, which
        is as long as the report stays owed. What they wrote stays word for
        word: the closing reference and the attribution go above it.
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
                opened.body.startswith(f"Resolves #{support.REPORT_ISSUE}"),
                opened.body.endswith(f"\n{EDITED_DESCRIPTION}"),
            ),
            (1, 1, None, None, OPENED_PR, True, True),
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


class _EditsTheIssueDuring:
    """One report request a human edits the issue underneath.

    The edit lands inside the request, which is after the re-read the
    publication takes before it and before the settlement behind it.
    """

    def __init__(self, issue, request) -> None:
        self._issue = issue
        self._request = request
        self.calls = 0

    def __call__(self, *args, **kwargs):
        """Edit the issue, then answer the request as GitHub would."""
        self.calls += 1
        self._issue.body = EDITED_BODY
        return self._request(*args, **kwargs)


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
