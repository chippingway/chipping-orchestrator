# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The docs commit the size gate measures, and the pass a hold leaves owed.

A docs pass is the last push before a human is asked to merge, so it is
measured like every other candidate for a pull request the remote already
carries. A hold ends the tick with the pass itself finished, which is what the
receipt here is about: the adjudication publishes the commit and hands the
label back, and the tick that gets it has to finish the handoff rather than
read a branch in sync with its remote as an issue no docs pass has run for.
That handoff is the one every published docs commit earns -- back to
`validating`, owed a report of the commit the code-publication receipt names
-- and a receipt that names no such publication hands it back owed nothing.
"""
from __future__ import annotations

import unittest
from types import MappingProxyType
from unittest.mock import MagicMock, patch

from orchestrator import config
from orchestrator.git.measurement.models import (
    FrozenCommit,
    MeasurementFailure,
)
from tests.workflow.fixtures import MEASURED_CANDIDATE_SHA, _agent
from tests.workflow.mid_run_effects import _MovesThePullRequest
from tests.workflow.stages.documenting import (
    documenting_test_support as documenting_support,
)
from tests.workflow.stages.documenting.documenting_test_support import (
    _FreshDocumentingFixture,
)

DEV_SESSION = "dev-sess"

# The head a docs pass leaves the checkout on. Each IS the commit the size
# gate proves that checkout to, because in production they are one read of one
# worktree: the stage names the commit it means to publish and the gate
# refuses a checkout standing anywhere else, so a fixture that spelled them
# differently would be modelling the race rather than the tick.
SHA_AFTER = MEASURED_CANDIDATE_SHA
SHA_BEFORE = documenting_support.SHA_BEFORE

# A pull request somebody else pushed to while the docs agent was out.
MOVED_PR_HEAD = "cafef00d" * 5

# The ahead/behind reading a branch level with its remote answers.
IN_SYNC = (0, 0)

DOCS_VERDICT = "docs_verdict"
DOCS_CHECKED_SHA = "docs_checked_sha"
SETTLED_DOCS_SHA = "docs_settled_sha"
REWRITE_DEBT = "developer_report_rewrite_debt"
VERDICT_UPDATED = "updated"

DECOMPOSING = "workflow:decomposing"
IN_REVIEW = "in_review"
VALIDATING = "workflow:validating"

# Every label a finished pass hands the issue on to.
HANDED_ON = frozenset((IN_REVIEW, VALIDATING))

# The lease the gate records beside the docs receipt: the head the docs push
# replaces, which the completion records as the head the pass was entered on.
SETTLED_DOCS_LEASE = "docs_settled_lease"

DOCS_LEASE = MappingProxyType({SETTLED_DOCS_LEASE: SHA_BEFORE})

# The code-publication receipt an authorized settlement writes as it publishes
# the held commit -- that commit, onto the pull request the issue pins, over the
# head the adjudication froze -- beside the docs receipt's lease the gate's hold
# wrote.
PUBLICATION_RECEIPT = MappingProxyType({
    "implementing_published_sha": SHA_AFTER,
    "implementing_published_pr": _FreshDocumentingFixture.pr_number,
    "implementing_published_lease": SHA_BEFORE,
})

SETTLEMENT_RECEIPT = MappingProxyType({**PUBLICATION_RECEIPT, **DOCS_LEASE})

# A docs receipt's lease as no gate writes it: missing, written null, and no
# commit id at all. Each is a record something edited, which the completion
# holds over rather than reading an entry head off anything else or erasing it.
DAMAGED_LEASES = MappingProxyType({
    "a missing lease": PUBLICATION_RECEIPT,
    "a null lease": MappingProxyType({**PUBLICATION_RECEIPT, SETTLED_DOCS_LEASE: None}),
    "a lease that is no commit": MappingProxyType({**PUBLICATION_RECEIPT, SETTLED_DOCS_LEASE: "not-a-commit"}),
})

# Each receipt a settled commit's tick may find beside it: the settlement's,
# which proves the publication, and none, which leaves the checkout standing on
# the commit to prove it. Either way the completion leaves, as `_completed`
# reads it, the commit stamped `updated`, the docs receipt consumed, and no
# report debt.
SETTLED_RECEIPTS = (
    ("the settlement's receipt", SETTLEMENT_RECEIPT),
    ("no receipt of the publication", DOCS_LEASE),
)

COMPLETED = (VERDICT_UPDATED, SHA_AFTER, None, None)

CEILING = 5
PAST_THE_CEILING = 6
MAX_ADDED_LINES = "MAX_ADDED_LINES"

RUN_AGENT = "run_agent"
PUSH_BRANCH = "_push_branch"
REVISION = "revision"

DOCS_REPLY = "docs: README tweak"

# A commit something else put on the checkout between the pass reading its own
# head and the gate proving that checkout for itself.
STRAY_COMMIT = "9a9a9a9a" * 5

# The head a settled verdict published, and the one a replacement host
# rebuilt from a moved pull request finds instead.
SETTLED_SHA = "5e771ed0" * 5
MOVED_HEAD = "0d0d0d0d" * 5

# A receipt no checkout can be compared to.
NOT_A_COMMIT = "nope"

CANDIDATE_ABSENT = MeasurementFailure.CANDIDATE_ABSENT


# A published pass's tick that ends elsewhere, as the record seeded beside the
# receipts, whether the pull request is merged, and the relabels it makes: a
# merged pull request finalizes `done`, and a park with no reply waits on it.
TERMINAL_AND_PARKED = MappingProxyType({
    "a merged pull request": (MappingProxyType({}), True, [(_FreshDocumentingFixture.issue_number, "done")]),
    "a standing park": (
        MappingProxyType({"awaiting_human": True, "park_reason": "late_candidate_moved"}), False, [],
    ),
})


class DocumentingSizeGateTest(
    unittest.TestCase,
    _FreshDocumentingFixture,
):
    """A docs commit is measured before it joins the pull request it is for."""

    def test_an_oversized_docs_commit_is_held(self) -> None:
        # The docs push is the last one before a human is asked to merge,
        # which is what makes it matter rather than what makes it an
        # exception: a pass that took the diff past the ceiling would put an
        # unadjudicated pull request in front of the person who merges it.
        oversized = self._seeded()

        with patch.object(config, MAX_ADDED_LINES, CEILING):
            mocks = self._run_documenting(
                *oversized,
                run_agent=_agent(
                    session_id=DEV_SESSION,
                    last_message="docs: README tweak",
                ),
                push_branch=True,
                head_shas=[SHA_BEFORE, SHA_AFTER],
                branch_ahead_behind=IN_SYNC,
                added_lines=PAST_THE_CEILING,
            )

        mocks[PUSH_BRANCH].assert_not_called()
        routed = [label for _, label in oversized[0].label_history]
        self.assertEqual(routed, [DECOMPOSING])
        # The pass is over -- an agent ran and committed -- so the head it
        # produced is left as the receipt the handoff is still owed.
        self.assertEqual(
            oversized[0].pinned_data(self.issue_number).get(SETTLED_DOCS_SHA),
            SHA_AFTER,
        )

    def test_a_settled_commit_completes(self) -> None:
        # A settled `single` verdict publishes the held commit from the
        # adjudication and hands the label back here. The branch is in sync
        # with its remote by then, which is the reading an issue no docs pass
        # has run for gives -- so without the receipt this tick would spawn a
        # second docs agent over work the first one already published, commit
        # again, and hand the gate a candidate to adjudicate a second time.
        # The pass is over, so it completes into `in_review` stamped as a docs
        # commit, owed no report -- whether the settlement's receipt proves
        # the publication or the checkout standing on it does.
        for name, receipt in SETTLED_RECEIPTS:
            with self.subTest(name):
                gh, issue = self._seeded(docs_settled_sha=SHA_AFTER, **receipt)

                self._runs_and_pushes_nothing(gh, issue)

                self.assertEqual(gh.label_history, [(self.issue_number, IN_REVIEW)])
                self.assertEqual(self._completed(gh), COMPLETED)

    def test_an_unpublished_receipt_is_measured(self) -> None:
        # The receipt alone cannot say the commit reached the remote: a
        # verdict that parked, or a human who moved the label by hand, leaves
        # the same receipt over a commit still on disk. Ahead of the remote it
        # stands, and the recovered-commit path carries it through the gate,
        # which is the one road that measures it again.
        gh, issue = self._settled_docs_commit()

        mocks = self._run_documenting(
            gh, issue,
            run_agent=MagicMock(),
            head_shas=[SHA_AFTER],
            branch_ahead_behind=(1, 0),
            push_branch=True,
            added_lines=1,
        )

        mocks[RUN_AGENT].assert_not_called()
        mocks[PUSH_BRANCH].assert_called_once()
        self.assertEqual([label for _, label in gh.label_history], [IN_REVIEW])
        self.assertIsNone(
            gh.pinned_data(self.issue_number).get(SETTLED_DOCS_SHA),
        )

    def _runs_and_pushes_nothing(self, gh, issue) -> None:
        """One documenting tick over a branch in sync, standing on the settled commit, that runs and pushes nothing."""
        mocks = self._run_documenting(
            gh, issue,
            run_agent=MagicMock(),
            head_shas=[SHA_AFTER],
            branch_ahead_behind=IN_SYNC,
        )
        mocks[RUN_AGENT].assert_not_called()
        mocks[PUSH_BRANCH].assert_not_called()

    def _completed(self, gh) -> tuple:
        """The verdict, checked head, docs receipt, and report debt on the pinned comment."""
        state = gh.pinned_data(self.issue_number)
        return (
            state.get(DOCS_VERDICT),
            state.get(DOCS_CHECKED_SHA),
            state.get(SETTLED_DOCS_SHA),
            state.get(REWRITE_DEBT),
        )

    def _settled_docs_commit(self):
        """A docs pass the gate held and an adjudication has since settled."""
        return self._seeded(docs_settled_sha=SHA_AFTER)


class PublishedReceiptOrderTest(
    unittest.TestCase,
    _FreshDocumentingFixture,
):
    """A published pass's completion is asked ahead of its approval, and behind the terminals and any park."""

    def test_the_terminals_and_a_park_come_first(self) -> None:
        # The receipts proving the pass published are no licence to step over
        # a merged pull request, which finalizes `done`, or over a park that
        # stands for a human's reply: neither is completed, and the docs
        # receipt is left as it was for the road that does answer it.
        for name, (seeded, merged, ended_on) in TERMINAL_AND_PARKED.items():
            with self.subTest(name):
                published = self._published_tick({**SETTLEMENT_RECEIPT, **seeded}, merged)
                self.assertEqual(published[:2], (ended_on, None))

    def test_a_damaged_lease_holds_the_completion(self) -> None:
        # The head the docs push replaced is the head the pass was entered
        # on, which the completion records, and a receipt that carries no
        # readable one is not current state to act on: nothing is relabelled,
        # announced, or recorded, and the receipt and its lease are left
        # exactly as they stand for a human to repair -- never read off the
        # code-publication receipt instead.
        for name, receipt in DAMAGED_LEASES.items():
            with self.subTest(name):
                published = self._published_tick(receipt, merged=False)

                held = (SHA_AFTER, receipt.get(SETTLED_DOCS_LEASE))
                self.assertEqual(published, ([], None, [], held))

    def _published_tick(self, receipt, merged: bool) -> tuple:
        """One tick over a published pass's docs receipt beside `receipt`, its pull request merged where `merged`.

        Read back as the relabels made, the docs verdict stamped, the notices
        posted on the pull request, and the docs receipt and its lease.
        """
        github, issue = self._seeded(docs_settled_sha=SHA_AFTER, **receipt)
        github.get_pr(self.pr_number).merged = merged
        self._run_documenting(github, issue, run_agent=MagicMock())
        state = github.pinned_data(self.issue_number)
        return (
            github.label_history, state.get(DOCS_VERDICT), github.posted_pr_comments,
            (state.get(SETTLED_DOCS_SHA), state.get(SETTLED_DOCS_LEASE)),
        )


class DocumentingCandidateBindingTest(
    unittest.TestCase,
    _FreshDocumentingFixture,
):
    """The commit this pass publishes is the commit this pass made."""

    def test_a_checkout_that_moved_publishes_nothing(self) -> None:
        # The stage reads the head its docs commit left, and the gate proves
        # the checkout again for itself. Between the two the worktree is
        # writable -- so a commit landing there would be measured and pushed
        # while the stamp below recorded the id the pass read as documented.
        gh, issue = self._seeded()

        mocks = self._run_documenting(
            gh, issue,
            run_agent=_agent(session_id=DEV_SESSION, last_message=DOCS_REPLY),
            push_branch=True,
            head_shas=[SHA_BEFORE, SHA_AFTER],
            branch_ahead_behind=IN_SYNC,
            added_lines=1,
            candidate_commit=FrozenCommit(sha=STRAY_COMMIT),
        )

        mocks[PUSH_BRANCH].assert_not_called()
        state = gh.pinned_data(self.issue_number)
        # The pre-spawn watermark stands; what must not be recorded is the
        # head this pass made, which nothing published.
        self.assertNotEqual(state[DOCS_CHECKED_SHA], SHA_AFTER)
        self.assertNotIn(DOCS_VERDICT, state)
        self.assertFalse(HANDED_ON & {label for _, label in gh.label_history})

    def test_a_publication_that_moved_mid_run_refuses(self) -> None:
        # The race the pass's own head closes, on the last push before a human
        # is asked to merge. The pull request was standing on A when the
        # reviewer approved it and this pass began there; somebody pushed B
        # while the agent was out, and the agent committed C on top of A. Read
        # afterwards, B becomes the lease and this force-push drops it -- and
        # what it drops is what that human would then not see.
        moved, moved_issue = self._seeded()

        mocks = self._run_documenting(
            moved, moved_issue,
            run_agent=_MovesThePullRequest(
                moved.get_pr(self.pr_number),
                MOVED_PR_HEAD,
                _agent(session_id=DEV_SESSION, last_message=DOCS_REPLY),
            ),
            push_branch=True,
            head_shas=[SHA_BEFORE, SHA_AFTER],
            branch_ahead_behind=IN_SYNC,
            added_lines=1,
        )

        mocks[PUSH_BRANCH].assert_not_called()
        self.assertFalse(HANDED_ON & {label for _, label in moved.label_history})
        # And the pull request is left exactly where the other push put it.
        self.assertEqual(moved.get_pr(self.pr_number).head.sha, MOVED_PR_HEAD)

    def test_an_agreeing_checkout_publishes(self) -> None:
        # What says the refusal above is about the disagreement rather than
        # about the binding refusing every pass it stands in front of.
        gh, issue = self._seeded()

        mocks = self._run_documenting(
            gh, issue,
            run_agent=_agent(session_id=DEV_SESSION, last_message=DOCS_REPLY),
            push_branch=True,
            head_shas=[SHA_BEFORE, SHA_AFTER],
            branch_ahead_behind=IN_SYNC,
            added_lines=1,
        )

        self.assertEqual(
            mocks[PUSH_BRANCH].call_args.kwargs[REVISION], SHA_AFTER,
        )
        self.assertEqual([label for _, label in gh.label_history], [IN_REVIEW])


class SettledDocsProofTest(
    unittest.TestCase,
    _FreshDocumentingFixture,
):
    """What a settled receipt is proved against before it is consumed."""

    def test_a_moved_head_leaves_the_receipt(self) -> None:
        # In sync is not the same claim as carrying it. A replacement host
        # rebuilds the checkout from a pull request that has moved on, and
        # what it gets is a branch level with its remote and standing on
        # somebody else's head -- so the docs pass would be reported over a
        # commit this branch does not have.
        gh, issue = self._seeded(docs_settled_sha=SETTLED_SHA)

        mocks = self._run_documenting(
            gh, issue,
            run_agent=MagicMock(),
            head_shas=[MOVED_HEAD],
            branch_ahead_behind=IN_SYNC,
            candidate_commit=FrozenCommit(sha=MOVED_HEAD),
        )

        self._assert_unclaimed(gh, mocks)

    def test_an_unreadable_head_leaves_the_receipt(self) -> None:
        # A revision this host cannot peel is not a head anything may be
        # compared against, which is what a checkout the commit never reached
        # answers with.
        gh, issue = self._seeded(docs_settled_sha=SETTLED_SHA)

        mocks = self._run_documenting(
            gh, issue,
            run_agent=MagicMock(),
            head_shas=[MOVED_HEAD],
            branch_ahead_behind=IN_SYNC,
            candidate_commit=FrozenCommit(failure=CANDIDATE_ABSENT),
        )

        self._assert_unclaimed(gh, mocks)

    def test_a_receipt_that_is_no_id_is_refused(self) -> None:
        # Read fail-closed like every other commit field: a hand-edited value
        # is no receipt, and comparing a checkout to it would compare it to
        # nothing.
        gh, issue = self._seeded(docs_settled_sha=NOT_A_COMMIT)

        mocks = self._run_documenting(
            gh, issue,
            run_agent=MagicMock(),
            head_shas=[SETTLED_SHA],
            branch_ahead_behind=IN_SYNC,
        )

        self._assert_unclaimed(gh, mocks)

    def _assert_unclaimed(self, gh, mocks) -> None:
        """The receipt stands and nothing is handed on behind it."""
        state = gh.pinned_data(self.issue_number)
        self.assertNotIn(DOCS_CHECKED_SHA, state)
        self.assertFalse(HANDED_ON & {label for _, label in gh.label_history})
        mocks[PUSH_BRANCH].assert_not_called()
