# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The squash of a commit a human adjudicated, against a real repository.

The one case the exemption cannot answer on its own. A `single` verdict
accepts an oversized candidate and names that exact commit; the reviewer then
approves the pull request and the squash collapses it into an object nobody
ruled on. Measured like any other candidate it is oversized again -- the same
lines, over the same base -- and the last push before the merge button would
route the work back into adjudication.

Every reading here is the real one: a real repository, a real squash, and the
canonical fingerprint taken over the actual objects on both sides of the
rewrite. Only the authenticated push is stood in for, and only the remote-side
base freeze, which these fixtures have no token to reach.

Both durable writes one transferring squash makes are read here, and they are
read at the moment each lands rather than once the tick is over: the grant
moves nothing and the receipt behind it is what carries the verdict over, so
a case that only looked at the end could not tell the two apart -- nor tell
either from a tick that lost one of them.
"""
from __future__ import annotations

import unittest

from orchestrator.workflow.late_split import (
    exemption as _exemption,
    exemption_reading as _exemption_reading,
    rewrite_fields as _rewrite_fields,
    rewrite_reading as _rewrite_reading,
    rewrite_values as _rewrite_values,
)
from tests.git.publication import squash_git_support as squash_support
from tests.git.publication.squash_exemption_support import (
    GRANT_WRITE,
    LABEL_DECOMPOSING,
    RECEIPT_WRITE,
    UNRECORDED_DIGEST,
    _AdjudicatedSquashMixin,
    _RecordsEachWrite,
    _RefusesOneWrite,
)
from tests.git.publication.squash_gate_support import (
    MOVED_HEAD,
    TRACKED_EDIT,
    TRACKED_FILE,
    PublicationSeed,
    _squash_gate,
)

KEY_CANDIDATE_SHA = "late_candidate_sha"
# The receipt a landed gated push leaves, which is what the settlement that
# carries the exemption over rides.
KEY_PUBLISHED_SHA = "implementing_published_sha"
# The debt the grant's own write carries beside the permission: the commit
# still owed a push, and the head that push is leased against.
KEY_APPROVED_SHA = "late_approved_sha"
KEY_APPROVED_LEASE = "late_approved_lease"


class SquashedExemptionRealGitTest(
    _AdjudicatedSquashMixin,
    squash_support.SquashGitFixtureMixin,
    unittest.TestCase,
):
    """The transfer an equivalent squash earns, and what one write puts down."""

    def test_an_equivalent_squash_publishes(self) -> None:
        # The squash has the same tree over the same base, so it contributes
        # the change a human already ruled on. Without the transfer this is
        # the oversized reading that routes an approved pull request back to
        # the adjudication.
        gate = self._adjudicated()

        squash_run = self._squashes(gate)

        self.assertTrue(squash_run.success)
        self.assertFalse(squash_run.held)
        self.assertEqual(
            squash_run.push_mock.call_args.kwargs["revision"],
            self._head_sha(),
        )
        self.assertNotIn(
            (gate.issue.number, LABEL_DECOMPOSING), gate.gh.label_history,
        )

    def test_the_permission_leaves_the_exemption_put(self) -> None:
        # The grant records what licenses the push and moves nothing, and the
        # only moment that is readable is its own write: the verdict stays on
        # the commit a human ruled on until a receipt for a landed push spends
        # the permission, so a push that never lands leaves no verdict on an
        # object only this host has.
        gate = self._adjudicated()
        accepted = self._head_sha()
        writes = _RecordsEachWrite(gate)

        with writes.held():
            self._squashes(gate)

        granted = writes.nth(GRANT_WRITE)
        self.assertEqual(granted[_exemption_reading.LATE_EXEMPT_SHA], accepted)
        self.assertEqual(
            granted[_rewrite_fields.LATE_REWRITE_PHASE],
            str(_rewrite_values.LateRewritePhase.AUTHORIZED),
        )

    def test_the_receipt_carries_the_exemption_over(self) -> None:
        # The push landed, so the commit the verdict is about to name is one
        # the pull request really carries -- which is the whole of what makes
        # the move safe, and why it rides this write and no earlier one.
        gate = self._adjudicated()

        self._squashes(gate)

        squashed = self._head_sha()
        self._assert_exempts(gate, squashed)
        durable = gate.gh.read_pinned_state(gate.issue)
        identity = _exemption_reading.read_semantic_identity(durable)
        self.assertEqual(identity.candidate_sha, squashed)
        authorized = _rewrite_reading.read_rewrite_authorization(durable)
        self.assertEqual(
            authorized.phase, _rewrite_values.LateRewritePhase.PUBLISHED,
        )
        self.assertEqual(
            self._pinned(gate)[KEY_PUBLISHED_SHA], squashed,
        )

    def test_a_refused_receipt_leaves_the_verdict_put(self) -> None:
        # The window the settlement closes, read from the side that can still
        # be wrong: the branch is on the remote and the write that would say
        # so was refused. Nothing may be durable there -- least of all a
        # verdict, which would name a commit no receipt accounts for. The
        # branch is left on the squash the remote now has, and the permission
        # stands for the reconciliation that republishes it as a leased no-op.
        gate = self._adjudicated()
        accepted = self._head_sha()
        refusing = _RefusesOneWrite(gate, ordinal=RECEIPT_WRITE)

        with refusing.held(gate), self.assertRaises(RuntimeError):
            self._squashes(gate)

        self.assertNotEqual(self._head_sha(), accepted)
        self._assert_exempts(gate, accepted)
        pinned = self._pinned(gate)
        self.assertEqual(
            pinned[_rewrite_fields.LATE_REWRITE_PHASE],
            str(_rewrite_values.LateRewritePhase.AUTHORIZED),
        )
        self.assertNotIn(KEY_PUBLISHED_SHA, pinned)

    def test_the_authorization_names_both_ends(self) -> None:
        gate = self._adjudicated()
        accepted = self._head_sha()

        self._squashes(gate)

        authorized = _rewrite_reading.read_rewrite_authorization(
            gate.gh.read_pinned_state(gate.issue),
        )
        self.assertEqual(authorized.rewrite.from_sha, accepted)
        self.assertEqual(authorized.rewrite.to_sha, self._head_sha())
        self.assertEqual(authorized.rewrite.lease, accepted)
        self.assertEqual(
            authorized.rewrite.kind, _rewrite_values.LateRewriteKind.SQUASH,
        )

    def test_the_grant_owes_the_push(self) -> None:
        # The crash boundary the grant opens, read at the write that settles
        # it: the permission that licenses the push and the debt that says one
        # is owed for the commit it names go down together, so no tick comes
        # back to a permission for a push nothing on the comment asks for.
        gate = self._adjudicated()
        accepted = self._head_sha()
        writes = _RecordsEachWrite(gate)

        with writes.held():
            self._squashes(gate)

        granted = writes.nth(GRANT_WRITE)
        self.assertEqual(granted[KEY_APPROVED_SHA], self._head_sha())
        self.assertEqual(granted[KEY_APPROVED_LEASE], accepted)
        self.assertEqual(
            granted[_rewrite_fields.LATE_REWRITE_PHASE],
            str(_rewrite_values.LateRewritePhase.AUTHORIZED),
        )

    def test_a_refused_push_drops_the_permission(self) -> None:
        # The rollback puts the branch back on the accepted commit, which is
        # the commit the exemption never left -- so what the reset owes is
        # dropping the permission granted for an object on no branch.
        gate = self._adjudicated()
        accepted = self._head_sha()

        squash_run = self._squashes(gate, push_result=False)

        self.assertFalse(squash_run.success)
        self.assertEqual(self._head_sha(), accepted)
        pinned = self._pinned(gate)
        self._assert_exempts(gate, accepted)
        self.assertNotIn(_rewrite_fields.LATE_REWRITE_PHASE, pinned)
        identity = _exemption_reading.read_semantic_identity(
            gate.gh.read_pinned_state(gate.issue),
        )
        self.assertEqual(identity.candidate_sha, accepted)


class UntransferredSquashRealGitTest(
    _AdjudicatedSquashMixin,
    squash_support.SquashGitFixtureMixin,
    unittest.TestCase,
):
    """The squashes that earn no transfer, and are measured as they always were."""

    def test_an_unrecorded_digest_is_adjudicated(self) -> None:
        # The recorded digest is what proves the identity belongs to the pair
        # the evidence claims. One that does not is a record nothing may
        # transfer under, so the squash is measured like any other candidate.
        gate = self._adjudicated(digest=UNRECORDED_DIGEST)

        squash_run = self._squashes(gate)

        self.assertTrue(squash_run.held)
        self.assertIn(
            (gate.issue.number, LABEL_DECOMPOSING), gate.gh.label_history,
        )
        self.assertEqual(
            self._pinned(gate)[KEY_CANDIDATE_SHA], self._head_sha(),
        )

    def test_a_hand_edited_base_is_adjudicated(self) -> None:
        # The record's own base is what the accepted contribution is read
        # over. Moved to another commit in this repository it still types, and
        # the digest beside it then describes a pair this issue never
        # adjudicated -- so the record fails to prove itself and the squash is
        # measured like any other candidate.
        gate = self._adjudicated(base=self._one_commit_back())

        self.assertTrue(self._squashes(gate).held)
        self.assertIn(
            (gate.issue.number, LABEL_DECOMPOSING), gate.gh.label_history,
        )

    def test_a_legacy_exemption_is_adjudicated(self) -> None:
        # An issue whose pinned comment predates the semantic record exempts
        # the exact commit and can prove nothing about what it contributes.
        gate = _squash_gate(self, PublicationSeed())
        accepted = self._head_sha()
        _exemption.record_exemption(gate.state, accepted)
        gate.gh.write_pinned_state(gate.issue, gate.state)

        self.assertTrue(self._squashes(gate).held)
        pinned = self._pinned(gate)
        self._assert_exempts(gate, accepted)
        self.assertEqual(pinned[KEY_CANDIDATE_SHA], self._head_sha())

    def test_work_after_the_verdict_is_measured(self) -> None:
        # An exemption names one commit, and a branch that went on committing
        # after its verdict has a different one at the tip. What the squash
        # collapses is that tip -- the accepted change plus everything on top
        # of it -- so the contribution a push would publish is not the one a
        # human ruled on, and it is measured like any other candidate.
        accepted = self._head_sha()
        self._commits_over(1)
        gate = self._adjudicated(accepted=accepted)

        self.assertTrue(self._squashes(gate).held)
        self.assertIn(
            (gate.issue.number, LABEL_DECOMPOSING), gate.gh.label_history,
        )
        self._assert_exempts(gate, accepted)
        self.assertNotIn(_rewrite_fields.LATE_REWRITE_PHASE, self._pinned(gate))

    def test_unadjudicated_work_is_still_measured(self) -> None:
        # The exemption names one commit and only it. An issue that never
        # earned one gets the reading it always did.
        gate = _squash_gate(self, PublicationSeed())

        self.assertTrue(self._squashes(gate).held)
        self.assertIn(
            (gate.issue.number, LABEL_DECOMPOSING), gate.gh.label_history,
        )


class InterruptedSquashRealGitTest(
    _AdjudicatedSquashMixin,
    squash_support.SquashGitFixtureMixin,
    unittest.TestCase,
):
    """A squash of an accepted commit that stops being publishable as it runs.

    The entry is asked before the reset so a doomed publication costs no
    rewrite, but the commit is made behind that answer and the gate's second
    reading is the only one that sees what arrived in between. Nothing is
    measured there and nothing is granted: the transfer sits behind that
    reading, so a permission would be a claim about a publication this tick
    could no longer take.
    """

    def test_a_publication_that_moved_grants_nothing(self) -> None:
        # Somebody pushed to the pull request while the rewrite ran, so the
        # head the force-push is leased against is not the head the remote is
        # on. A permit granted here would license a push onto a publication
        # nothing re-read, and its receipt would carry a human's verdict over
        # on the strength of it.
        gate = self._adjudicated()
        accepted = self._head_sha()

        squash_run = self._interrupted(gate, head=MOVED_HEAD)

        self._assert_nothing_moved(gate, accepted, squash_run)

    def test_a_tree_written_to_grants_nothing(self) -> None:
        # The gate's first refusal, and the one a transfer turns on twice
        # over: a tree carrying anything loose is one whose contribution is
        # not the contribution a push would send, so neither end of the
        # rewrite says what this checkout would publish.
        gate = self._adjudicated()
        accepted = self._head_sha()

        squash_run = self._interrupted(gate, writes=TRACKED_EDIT)

        self._assert_nothing_moved(gate, accepted, squash_run)
        # And the edit survives the restore as the uncommitted change it was,
        # which is the repair a `--hard` rollback would have thrown away.
        self.assertEqual((self.work / TRACKED_FILE).read_text(), TRACKED_EDIT)

    def _assert_nothing_moved(self, gate, accepted: str, squash_run) -> None:
        """The verdict, the branch, and the record after a refused rewrite."""
        self.assertTrue(squash_run.held)
        squash_run.push_mock.assert_not_called()
        self.assertEqual(self._head_sha(), accepted)
        self._assert_exempts(gate, accepted)
        self.assertNotIn(_rewrite_fields.LATE_REWRITE_PHASE, self._pinned(gate))
        identity = _exemption_reading.read_semantic_identity(
            gate.gh.read_pinned_state(gate.issue),
        )
        self.assertEqual(identity.candidate_sha, accepted)


class LostGrantRealGitTest(
    _AdjudicatedSquashMixin,
    squash_support.SquashGitFixtureMixin,
    unittest.TestCase,
):
    """What a refused GRANT leaves, with the branch already collapsed.

    A squash has replaced the branch's commits with one by the time that write
    is attempted, so what losing it may not do is end the tick in an
    exception: the caller would never reach the decision about the rewrite it
    is holding. The permit is refused where the write is lost instead, and the
    rewritten commit falls through to the ordinary cumulative gate.
    """

    def test_a_lost_grant_falls_through_to_the_gate(self) -> None:
        # The grant's own write is handled where it happens: the permit is
        # refused, the staged move is put back, and the tick carries on into
        # the ordinary cumulative reading rather than ending in an exception
        # the caller could not roll its rewrite back for.
        gate = self._adjudicated()
        accepted = self._head_sha()
        refusing = _RefusesOneWrite(gate, ordinal=GRANT_WRITE)

        with refusing.held(gate):
            squash_run = self._squashes(gate)

        self.assertTrue(squash_run.held)
        self.assertIsNone(squash_run.error)
        self.assertIn(
            (gate.issue.number, LABEL_DECOMPOSING), gate.gh.label_history,
        )
        pinned = self._pinned(gate)
        self.assertEqual(pinned[KEY_CANDIDATE_SHA], self._head_sha())
        # The move the refused write staged is put back, so what the comment
        # exempts is still the commit the adjudication accepted.
        self._assert_exempts(gate, accepted)
        self.assertNotIn(_rewrite_fields.LATE_REWRITE_PHASE, pinned)
