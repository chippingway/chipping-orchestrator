# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""A squash committed and never pushed, published only under the approval it was begun under.

The collapse is made on a real checkout and its push is still owed, so what
publishes it is the push transport, stood in for and counted: the recovery in
the validating handler, and -- a road the dispatcher takes before that handler
is reached -- the reconciliation that pays the debt the squash's size gate
recorded before its push. Each is driven for real over the same checkout.

An approval standing behind the push lets either road publish the commit on
the checkout. One that does not -- its records gone, the evidence its claim
names no longer current, or a subject of another head than the collapse was
planned over -- publishes nothing on either, whatever label the issue wears,
whatever the pull request seems to stand on, and over a collapse record that
will not read: the squash stays on the checkout, the records stay, and a human
is told once. Only a landing this issue's own receipt proves is finished
without one, as the leased no-op it is, and work that has ended goes to its
terminal.
"""
from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from orchestrator import config
from orchestrator.git import branch_transport as _branch_transport, ref_transport as _ref_transport
from orchestrator.workflow.engine import (
    report_settlement_state as _report_settlement,
    review_subjects as _review_subjects,
    verification_records as _verification_records,
)
from orchestrator.workflow.late_split import collapses as _collapses
from orchestrator.workflow.stages.implementing import (
    late_approval_reading as _late_approval_reading,
    late_approval_state as _late_approval_state,
    late_publication_state as _late_publication_state,
    late_squash_proof as _late_squash_proof,
)
from orchestrator.workflow.stages.validating import approved_evidence as _approved_evidence
from tests.workflow.stages.validating.squash_recovery_git_support import HalfMadeCollapseWorld
from tests.workflow.stages.validating.squash_tick_git_support import ISSUE_NUMBER, PR_NUMBER, run_git

PARK_REASON = "park_reason"

PARK_SQUASH_FAILED = "squash_failed"

# What the park a recovery takes over an approval that does not stand says first.
NOT_RESUMED = "squash-on-approval was not resumed"

# A measurement ceiling the three one-line commits fit under, so the size gate
# a resumed publication is entered through admits it.
_ROOMY_CEILING = 100

_PUBLISHED_UNAPPROVED = "a recorded squash was published without an approval standing behind its push"

_DOCUMENTING = "workflow:documenting"

_DONE = "done"

# The body an issue edited after its approval carries: requirements nobody was handed.
_EDITED_BODY = "Another requirement, added after the approval."


class _UnpushedSquashWorld(HalfMadeCollapseWorld):
    """The collapse made on the checkout, and the push it owes not yet out."""

    def setUp(self) -> None:
        super().setUp()
        self._commits(self.repo.path, f"fix: collapsed change (#{PR_NUMBER})", ".")
        self.squashed = self.repo.head()

    def _parked(self) -> tuple:
        """The park reason and collapse record on the comment, the parks reported, and whether a notice said so."""
        pinned = self.github.pinned_data(ISSUE_NUMBER)
        bodies = [body for _, body in self.github.posted_comments]
        return (
            pinned.get(PARK_REASON),
            pinned.get(_collapses.LATE_COLLAPSE_HEAD),
            self._parks_reported(),
            any(NOT_RESUMED in body for body in bodies),
        )

    def _pushed(self, push: MagicMock) -> list[str]:
        """The revisions the stood-in push transport was handed, in order."""
        return [call.kwargs["revision"] for call in push.call_args_list]

    def _refused(self) -> tuple:
        """What a refused push leaves: the squash on the checkout, the record kept, and one park."""
        return (PARK_SQUASH_FAILED, self.repo.accepted, 1, True)

    def _edits(self, key: str, edit) -> None:
        """Apply `edit` to the pinned value under `key`, dropping the key where it answers None."""
        state = self.github.read_pinned_state(self.issue)
        edited = edit(state.get(key))
        if edited is None:
            state.data.pop(key)
        else:
            state.set(key, edited)
        self.github.write_pinned_state(self.issue, state)

    def _remote_on(self, head: str) -> None:
        """Stand the remote read on `head`, under a size gate that admits the squash."""
        stack = patch.multiple(config, DECOMPOSE=True, MAX_ADDED_LINES=_ROOMY_CEILING)
        stack.start()
        self.addCleanup(stack.stop)
        remote = _ref_transport._RefRead(sha=head)
        read = patch.object(_branch_transport, "_remote_branch_read", return_value=remote)
        read.start()
        self.addCleanup(read.stop)

    def _owes_a_debt(self) -> None:
        """Leave the debt the squash's size gate records before its push: the squash, leased on the approved head."""
        state = self.github.read_pinned_state(self.issue)
        _late_approval_state._approve(
            state, self.squashed, self.repo.accepted, _late_approval_reading.LateApprovalBasis.READING,
        )
        self.github.write_pinned_state(self.issue, state)



class RecoveredSquashApprovalTest(_UnpushedSquashWorld, unittest.TestCase):
    """The validating handler's recovery resumes the push only under the approval standing behind it."""

    def setUp(self) -> None:
        super().setUp()
        self._remote_on(self.repo.accepted)

    def test_a_standing_approval_resumes_the_push(self) -> None:
        agent, push = self._runs_the_tick()

        agent.assert_not_called()
        self.assertEqual(self._pushed(push), [self.squashed])

    def test_no_approval_record_publishes_nothing(self) -> None:
        self._edits(_review_subjects.APPROVED_SUBJECT, _dropped)
        self._edits(_approved_evidence.APPROVED_EVIDENCE, _dropped)

        self._refuses_the_push()

    def test_evidence_gone_publishes_nothing(self) -> None:
        # The claim still reads whole, but the record it names is gone.
        self._edits(_verification_records.CURRENT_EVIDENCE, _dropped)

        self._refuses_the_push()

    def test_another_head_publishes_nothing(self) -> None:
        # Read whole, with its evidence standing, but of the base rather than
        # of the head the collapse was planned over.
        base = self.repo.base
        self._edits(_review_subjects.APPROVED_SUBJECT, lambda subject: {**subject, "sha": base})

        self._refuses_the_push()

    def _refuses_the_push(self) -> None:
        """Run the tick and assert nothing was pushed, the squash stayed, and the park was taken."""
        agent, push = self._runs_the_tick()

        ran = (agent.call_count, self._pushed(push), self.repo.head())
        self.assertEqual(ran, (0, [], self.squashed), _PUBLISHED_UNAPPROVED)
        self.assertEqual(self._parked(), self._refused())


class DispatchedSquashDebtTest(_UnpushedSquashWorld, unittest.TestCase):
    """The debt the squash's size gate recorded is its push, held to the same approval ahead of the handler."""

    def setUp(self) -> None:
        super().setUp()
        self._remote_on(self.repo.accepted)
        self._owes_a_debt()

    def test_a_standing_approval_pays_the_debt(self) -> None:
        # The control: the dispatcher reaches the reconciliation, and what
        # goes out is the commit on the checkout and nothing else.
        pushed = self._pushed(self._dispatches())

        self.assertEqual(set(pushed), {self.squashed})

    def test_no_approval_record_pays_nothing(self) -> None:
        # Whatever else the dispatcher finds: a collapse record that will not
        # read whole, an issue relabelled onto another stage the
        # reconciliation publishes from, or a pull request read as already
        # carrying the squash -- which proves nothing about what the push it
        # leases from a reading of its own would publish. Nothing is pushed,
        # the debt and the collapse record are kept, and the park is taken.
        for name, beside in _BESIDE_NO_APPROVAL:
            with self.subTest(name):
                self.setUp()
                self._edits(_review_subjects.APPROVED_SUBJECT, _dropped)
                self._edits(_approved_evidence.APPROVED_EVIDENCE, _dropped)
                beside(self)

                pushed = self._pushed(self._dispatches())
                ran = (pushed, self.repo.head(), self._owed())

                self.assertEqual(ran, ([], self.squashed, self.squashed), _PUBLISHED_UNAPPROVED)
                self.assertEqual(self._parked(), self._refused())

    def test_a_stale_subject_pays_nothing(self) -> None:
        # The approval reads whole and its evidence stands, but the subject it
        # covers does not: the issue was edited since, or the report it was
        # given was edited in place. Nothing the squash owes is published,
        # and the park is taken.
        for name, moves in _STALE_SUBJECTS:
            with self.subTest(name):
                self.setUp()
                moves(self)

                ran = (self._pushed(self._dispatches()), self.repo.head())

                self.assertEqual(ran, ([], self.squashed), _PUBLISHED_UNAPPROVED)
                self.assertEqual(self._parked(), self._refused())

    def test_a_merged_pr_reaches_its_terminal(self) -> None:
        # The artifact the approval's evidence rests on cannot be read, which
        # holds a squash that approval backs -- but the pull request merged,
        # so the work is the terminal's: the issue is finalized, and nothing,
        # the debt included, is pushed onto it.
        self.github.get_pr(PR_NUMBER).merged = True

        with patch.object(self.github, "reread_verification_artifact", side_effect=RuntimeError("unreadable")):
            pushed = self._pushed(self._dispatches())

        label = self.github.workflow_label(self.issue)
        self.assertEqual((pushed, label), ([], _DONE))

    def _owed(self) -> str | None:
        """The commit the debt the squash's size gate recorded still names."""
        return _late_approval_reading._approved_commit(self.github.read_pinned_state(self.issue))

    def _edits_the_report(self) -> None:
        """Rewrite the words of the report recorded as current, in place on the pull request."""
        current = _report_settlement.read_current_report(self.github.read_pinned_state(self.issue))
        for comment in self.github.get_pr(PR_NUMBER).issue_comments:
            if comment.id == current.location.comment_id:
                comment.body = f"{comment.body}\nEdited after the approval."


class LandedSquashRecoveryTest(_UnpushedSquashWorld, unittest.TestCase):
    """A push this issue's own receipt proves landed is finished as the leased no-op it is, approval or not."""

    def setUp(self) -> None:
        super().setUp()
        self._remote_on(self.squashed)
        self.github.get_pr(PR_NUMBER).head.sha = self.squashed
        self._receipts(self.squashed, PR_NUMBER)

    def test_a_receipted_landing_needs_no_approval(self) -> None:
        # The approval no longer stands -- its evidence claim gone, or the
        # verification configuration moved since -- but finishing this landing
        # publishes nothing new: the one push is leased on the squash itself,
        # so a remote anywhere else refuses it. The record ends, nothing
        # parks, and the move past `validating` is held for a fresh review.
        for name, unbacks in _UNBACKED_LANDINGS:
            with self.subTest(name):
                self.setUp()
                unbacks(self)

                leases = self._leases(self._dispatches())

                pinned = self.github.pinned_data(ISSUE_NUMBER)
                left = (_collapses.LATE_COLLAPSE_HEAD in pinned, pinned.get(PARK_REASON), self.github.label_history)
                self.assertEqual(leases, [(self.squashed, self.squashed)])
                self.assertEqual(left, (False, None, []))

    def test_an_unproved_landing_parks(self) -> None:
        # A receipt of this commit onto another pull request, one of another
        # commit than the checkout stands on, or a debt still owed beside it
        # proves nothing about what finishing the squash would publish: with
        # no approval standing, nothing is pushed and the park is taken.
        for name, unproves in _UNPROVED_LANDINGS:
            with self.subTest(name):
                self.setUp()
                self._edits(_approved_evidence.APPROVED_EVIDENCE, _dropped)
                unproves(self)

                ran = (self._pushed(self._dispatches()), self.repo.head())

                self.assertEqual(ran, ([], self.squashed), _PUBLISHED_UNAPPROVED)
                self.assertEqual(self._parked(), self._refused())

    def test_a_moved_checkout_publishes_nothing(self) -> None:
        # The receipt proves the landing over the checkout as the handler read
        # it, and then the checkout moves onto another commit before the
        # squash reads it -- with the remote back on the approved head, where
        # that commit would land under the head the collapse replaced. The
        # recovery is bound to the commit the receipt proved: it refuses the
        # moved checkout, and nothing is pushed.
        self._edits(_approved_evidence.APPROVED_EVIDENCE, _dropped)
        self.github.get_pr(PR_NUMBER).head.sha = self.repo.accepted
        self._remote_on(self.repo.accepted)
        self._proves = _late_squash_proof._receipted_landing
        self._proofs = []

        with patch.object(_late_squash_proof, "_receipted_landing", side_effect=self._moves_behind_the_handler):
            leases = self._leases(self._dispatches())

        self.assertEqual(
            (self._proofs, leases, _collapses.LATE_COLLAPSE_HEAD in self.github.pinned_data(ISSUE_NUMBER)),
            ([self.squashed, self.squashed], [], True),
        )

    def _moves_behind_the_handler(self, gate, recorded) -> str:
        """Take the receipt's proof, and move the checkout onto another commit right behind the handler's.

        The dispatcher proves it first and the handler second.
        """
        landed = self._proves(gate, recorded)
        self._proofs.append(landed)
        if len(self._proofs) == 2:
            run_git(
                "-c", "user.name=Maintainer", "-c", "user.email=maintainer@example.com",
                "commit", "--amend", "-m", "fix: another squash", cwd=self.repo.path,
            )
        return landed

    def _receipts(self, published: str, pull_request: int) -> None:
        """Record this issue's receipt of `published`, pushed from the approved head onto `pull_request`."""
        state = self.github.read_pinned_state(self.issue)
        _late_publication_state._record_publication(state, published, self.repo.accepted, pull_request)
        self.github.write_pinned_state(self.issue, state)

    def _leases(self, push: MagicMock) -> list[tuple[str, str]]:
        """Each revision the stood-in push transport was handed, beside the head it was leased against."""
        return [(call.kwargs["revision"], call.kwargs["force_with_lease"]) for call in push.call_args_list]


def _dropped(_recorded) -> None:
    """The edit that takes a pinned record off the comment."""


def _relabels(case) -> None:
    """A human moving the issue onto `documenting`, another stage the reconciliation publishes from."""
    case.github.set_workflow_label(case.issue, _DOCUMENTING, guarded=False)


def _reads_as_landed(case) -> None:
    """The pull request answering every read as standing on the squash already."""
    case.github.get_pr(PR_NUMBER).head.sha = case.squashed


# What leaves a receipted landing with no approval standing behind it.
_UNBACKED_LANDINGS = (
    ("a missing evidence claim", lambda case: case._edits(_approved_evidence.APPROVED_EVIDENCE, _dropped)),
    (
        "a moved verification configuration",
        lambda case: case.enterContext(patch.object(config, "VERIFY_COMMANDS", ("printf changed-verification",))),
    ),
)

# What leaves a landing the receipt does not prove.
_UNPROVED_LANDINGS = (
    ("a receipt onto another pull request", lambda case: case._receipts(case.squashed, PR_NUMBER + 1)),
    ("a receipt of another commit", lambda case: case._receipts(case.repo.base, PR_NUMBER)),
    ("a debt still owed beside it", lambda case: case._owes_a_debt()),
)

# What leaves the subject an approval covers no longer the one standing.
_STALE_SUBJECTS = (
    ("an edited issue", lambda case: setattr(case.issue, "body", _EDITED_BODY)),
    ("an edited report", lambda case: case._edits_the_report()),
)

# What the dispatcher may find beside an approval nobody recorded.
_BESIDE_NO_APPROVAL = (
    ("nothing else", lambda _case: None),
    ("a collapse record that will not read", lambda case: case._edits(_collapses.LATE_COLLAPSE_COUNT, _dropped)),
    ("a relabel onto documenting", _relabels),
    ("a pull request read as carrying the squash", _reads_as_landed),
)


if __name__ == "__main__":
    unittest.main()
