# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""One issue that owes a developer report, and the world it is reconciled in.

The default world is the one a transaction is recorded in: a clean checkout
standing on the commit the report is about, an open pull request on the recorded
branch carrying that commit, a code-publication receipt naming both, and an issue
whose requirements are still the ones the run was handed. Each case then moves
exactly one of those, so what a refusal is about is the thing the case changed.

The requirements revision is computed from the issue rather than written down,
because that is what the evidence compares against: a fixture spelling a digest
of its own would pass or fail on the fixture rather than on the record.

Every git reading the evidence takes travels on one `checkout` record, owned by
`report_checkout_fixture` beside this, so a case that moves the head or the
remote does not have to know which owner answers it.
"""
from __future__ import annotations

import contextlib
import tempfile

from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.engine import (
    content_hash as _content_hash,
    report_record_state as _record_state,
    report_records as _records,
    report_settlement_state as _settlement,
    report_transaction as _transaction,
)
from orchestrator.workflow.state import WorkflowLabel
from tests.support.fakes import FakeGitHubClient, FakePR, FakePRRef, make_issue
from tests.workflow.engine.report_checkout_fixture import Fetched, fresh_checkout
from tests.workflow.fixtures import _TEST_SPEC, LABEL_VALIDATING, SHA_LENGTH
from tests.workflow.git_owners import seam_patch

ISSUE_NUMBER = 7

PR_NUMBER = 12

OTHER_PR_NUMBER = 13

BRANCH = "orchestrator/chippingway__orchestrator/issue-7"

SOURCE_SHA = "3f786850e387550fdab836ed7e6dc881de23001b"

MOVED_SHA = "ab" * (SHA_LENGTH // 2)

RECEIPT = "issue-7-report-1"

REPORT_TEXT = "Implemented the change.\n\nChecks: `uv run pytest tests` passed."

# The code-publication receipt group, spelled here as the pinned comment
# carries it, so a case seeding one seeds what production wrote.
PUBLISHED_SHA = "implementing_published_sha"

PUBLISHED_PR = "implementing_published_pr"

# The third member of the receipt group. `_record_publication` writes all three
# keys on every receipt, so a fixture that left this one off would be seeding a
# PARTIAL group -- which the receipt's own damage reader calls damage, and
# rightly. `None` is what an initial publication records for the head it froze
# none of.
PUBLISHED_LEASE = "implementing_published_lease"

PARK_REASON = "park_reason"

AWAITING_HUMAN = "awaiting_human"

REVIEW_ROUND = "review_round"

PR_WATERMARK = "pr_last_comment_id"

# What a record nobody can read is parked under, read off the owner that writes
# it rather than spelled again here.
PARK_DAMAGED = _transaction._DAMAGED_RECORD


class ReportTransactionCase:
    """An issue with one outstanding report transaction, and its world."""

    def setUp(self) -> None:
        worktrees = contextlib.ExitStack()
        self.addCleanup(worktrees.close)
        self.checkout = fresh_checkout(
            worktrees.enter_context(tempfile.TemporaryDirectory()), SOURCE_SHA,
        )
        self.issue = make_issue(ISSUE_NUMBER, label=LABEL_VALIDATING)
        # The label the dispatcher routed this tick on. A terminal one is what
        # says the issue is over even while it is still open.
        self.label = LABEL_VALIDATING
        # Standing ON the recorded commit, not merely carrying it: a head
        # that has moved past the report's commit is a pull request whose work
        # is no longer what the report describes.
        self.pull_request = FakePR(
            number=PR_NUMBER,
            head_branch=BRANCH,
            head=FakePRRef(sha=SOURCE_SHA),
            commit_shas=(SOURCE_SHA,),
        )
        self.gh = FakeGitHubClient([self.issue])
        self.gh.add_pr(self.pull_request)
        self.state = PinnedState(comment_id=1, state_data={
            PUBLISHED_SHA: SOURCE_SHA,
            PUBLISHED_PR: PR_NUMBER,
            PUBLISHED_LEASE: None,
        })

    def requirements(self) -> str:
        """The revision the issue's content currently hashes to."""
        return _content_hash._compute_user_content_hash(self.issue, set())

    def pending(self, **overrides) -> _records.PendingReport:
        """The transaction this issue owes, with any member replaced."""
        owed = {
            "receipt": RECEIPT,
            "subject": _records.ReportSubject(
                repo_slug=self.gh.repo_slug,
                pr_number=PR_NUMBER,
                branch=BRANCH,
                source_sha=SOURCE_SHA,
                requirements_revision=self.requirements(),
            ),
            "report_revision": 1,
            "mode": _records.ReportMode.PUBLISH,
            "route": WorkflowLabel.VALIDATING,
            "report": REPORT_TEXT,
        }
        return _records.PendingReport(**(owed | overrides))

    def record(self, **overrides) -> _records.PendingReport:
        """Stage one transaction onto the pinned state and return it."""
        pending = self.pending(**overrides)
        _record_state.record_pending_report(self.state, pending)
        return pending

    def reconcile(self) -> bool:
        """Run the dispatcher's report guard over this issue's world."""
        with self._seams():
            return _transaction._reconciles_pending_report(
                self.gh, _TEST_SPEC, self.issue, self.label, self.state,
            )

    @contextlib.contextmanager
    def _seams(self):
        """The three git readings the evidence takes, answered from the case."""
        with contextlib.ExitStack() as seams:
            seams.enter_context(
                seam_patch("_worktree_path", lambda *_args: self.checkout.path),
            )
            seams.enter_context(
                seam_patch("_worktree_status", lambda *_args: self.checkout.status),
            )
            seams.enter_context(
                seam_patch("_head_sha", lambda *_args: self.checkout.head),
            )
            seams.enter_context(seam_patch(
                "_authed_fetch",
                lambda *_args, **_kw: Fetched(self.checkout.fetched),
            ))
            seams.enter_context(
                seam_patch("_branch_divergence", lambda *_args: self.checkout.remote),
            )
            yield


def report_comments(case: ReportTransactionCase) -> list:
    """Every comment the reconciliation posted onto the pull request."""
    return [
        posted for pr_number, posted in case.gh.posted_pr_comments
        if pr_number == PR_NUMBER
    ]


def assert_nothing_published(case: ReportTransactionCase) -> None:
    """No report reached the pull request and the record still claims one.

    What `assert_still_owed` asserts minus the handoff, for a case that seeded
    a handoff of its own to disagree with.
    """
    case.assertEqual(report_comments(case), [])
    case.assertIsNotNone(_record_state.read_pending_report(case.state))


def assert_still_owed(case: ReportTransactionCase) -> None:
    """The transaction is outstanding, unpublished, and unrecorded.

    The three together, because a refusal that wrote any one of them would be
    claiming an unpublished report reached the pull request. `case` is the test
    itself -- the fixture is mixed into one -- so the assertions it makes are
    reported against the case that failed.
    """
    case.assertEqual(report_comments(case), [])
    case.assertIsNotNone(_record_state.read_pending_report(case.state))
    case.assertIsNone(_settlement.read_handoff(case.state))
