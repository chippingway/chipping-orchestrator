# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What a verification re-reads, and which of its refusals stops the tick.

A `REPORT: VERIFIED` transaction posts nothing. What it owes is a fresh read of
the exact location the developer named, whose text still has to hash to the
revision it was verified at and whose author this deployment still has to
trust. The developer's assertion proves none of that: a report that is gone,
one that never hashed to the revision claimed, and one a human edited since are
all worlds the record cannot tell apart on its own.

Which refusal STOPS the tick is the split this module is about. A read nobody
could take holds, because nothing was learned. Every definite answer about a
location a human owns stands down, so the routes behind the guard run while the
transaction stays owed -- held instead, an issue whose report somebody edited
would sit in front of every one of them for good.

The AUTHOR is two reads deep, and both are covered here. `user` comes off the
object GitHub handed back and `login` comes off that, so on a worker that has
not completed it either is a request that can fail -- and a failure is not an
untrusted author but nobody saying, which holds. Left outside a boundary either
one leaves the guard by an exception rather than by a verdict, through the
dispatcher and out of the tick.
"""
from __future__ import annotations

import unittest
from unittest.mock import patch

from orchestrator import config
from orchestrator.github import comments as _trust
from orchestrator.github.developer_reports import content_digest
from orchestrator.github.pull_request_reports import ReportLocation
from orchestrator.workflow.engine import (
    report_records as _records,
    report_settlement_state as _settlement,
)
from orchestrator.workflow.state import WorkflowLabel
from tests.support.fakes import FakeComment, FakeUser, UnreadableUser
from tests.workflow.engine import report_transaction_test_support as support

_HUMAN_REPORT = "A report a maintainer wrote by hand."

_HUMAN_COMMENT_ID = 4242

_AUTHOR = "alice"

# What a read GitHub would not answer raises.
_REFUSED = "GitHub did not answer the read"

# The two reads standing between a verified report and its author, named by the
# member each one is.
_LOGIN = "login"

_AUTHOR_READS = (_LOGIN, "user")


def _refuses_the_author_read(case, read: str):
    """One of the two reads between a verified report and its author, failing.

    `login` is taken through the real trust reader, under an allowlist that
    makes it ask -- an empty one trusts everybody and never reads a login at
    all. `user` is the read one level up, which fails before that reader is
    entered, so it is refused at the reader's own name.
    """
    if read == _LOGIN:
        case.human.user = UnreadableUser()
        return patch.object(config, "ALLOWED_ISSUE_AUTHORS", (_AUTHOR,))
    return patch.object(
        _trust, "is_trusted_author", side_effect=RuntimeError(_REFUSED),
    )


def _verification(case) -> _records.PendingReport:
    """The transaction a developer's `REPORT: VERIFIED` would record."""
    return case.record(
        mode=_records.ReportMode.VERIFY,
        route=WorkflowLabel.IN_REVIEW,
        report="",
        location=ReportLocation(
            pr_number=support.PR_NUMBER, comment_id=_HUMAN_COMMENT_ID,
        ),
        content_revision=content_digest(_HUMAN_REPORT),
    )


class VerifiedTransactionTest(unittest.TestCase, support.ReportTransactionCase):
    """A verification re-reads the location and never posts a report."""

    def setUp(self) -> None:
        support.ReportTransactionCase.setUp(self)
        self.human = FakeComment(
            id=_HUMAN_COMMENT_ID, body=_HUMAN_REPORT, user=FakeUser(_AUTHOR),
        )
        self.pull_request.issue_comments.append(self.human)

    def test_a_trusted_match_settles_without_posting(self) -> None:
        _verification(self)

        self.assertFalse(self.reconcile())

        self.assertEqual(support.report_comments(self), [])
        self.assertEqual(
            _settlement.read_current_report(self.state).location,
            ReportLocation(
                pr_number=support.PR_NUMBER, comment_id=_HUMAN_COMMENT_ID,
            ),
        )
        self.assertIsNotNone(_settlement.read_handoff(self.state))

    def test_an_edited_report_stands_down(self) -> None:
        # A location a human owns, read and found to hold something else. That
        # is a definite answer rather than a missing read, so the tick carries
        # on to the routes behind the guard instead of stopping in front of
        # them for as long as the edit stands.
        _verification(self)
        self.human.body = f"{_HUMAN_REPORT} And a sentence added afterwards."

        self.assertFalse(self.reconcile())
        support.assert_still_owed(self)

    def test_a_report_that_is_gone_stands_down(self) -> None:
        _verification(self)
        self.pull_request.issue_comments.remove(self.human)

        self.assertFalse(self.reconcile())
        support.assert_still_owed(self)

    def test_an_untrusted_author_stands_down(self) -> None:
        # The location is somebody else's comment, and the marker on it proves
        # nothing: this workflow trusts thread content by author.
        _verification(self)
        self.human.user = FakeUser("mallory")

        with patch.object(config, "ALLOWED_ISSUE_AUTHORS", (_AUTHOR,)):
            self.assertFalse(self.reconcile())

        support.assert_still_owed(self)

    def test_an_unreadable_author_holds(self) -> None:
        # An author nobody could read is NOT an untrusted one. The refusal
        # above is a definite answer about a location a human owns and stands
        # down; this is a reading that did not happen, so it holds with the
        # content read beside it and the next tick asks again.
        for read in _AUTHOR_READS:
            with self.subTest(read=read):
                self.setUp()
                _verification(self)

                with _refuses_the_author_read(self, read):
                    self.assertTrue(self.reconcile())

                support.assert_still_owed(self)

    def test_an_unreadable_location_holds(self) -> None:
        # The one refusal on this road that stops the tick for a reason of its
        # own: nothing was learned, so the next tick asks again rather than
        # carrying on over a report nobody could read.
        _verification(self)
        self.gh.report_failures.unreadable.add(support.PR_NUMBER)

        self.assertTrue(self.reconcile())
        support.assert_still_owed(self)


if __name__ == "__main__":
    unittest.main()
