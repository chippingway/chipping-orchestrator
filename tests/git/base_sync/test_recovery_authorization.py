# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""A real interrupted rebase of a commit a human already ruled on.

The two crash windows either side of the grant, over an actual repository and
with the contributions really fingerprinted rather than answered by a double.
That is the whole point of doing it here: what licenses the reissued push is
the claim that the replay contributes what the adjudication accepted, and the
only way to hold this domain to it is to let a real `git rebase` produce the
replay and let the digest be taken over what git actually wrote.

Both windows have to end in the same place -- the push the dead tick never
made goes out, the verdict moves with it, and the tick is over -- and neither
may reach a second reading of the change, which would send it back into
adjudication with the pull request already open over the work.
"""
from __future__ import annotations

import unittest
from unittest.mock import MagicMock

from orchestrator.git.base_sync import eligibility
from orchestrator.git.base_sync.models import _AutoRebaseContext
from orchestrator.git.measurement import (
    additions as _measurement,
    commits as _measurement_commits,
    fingerprint as _fingerprint,
)
from orchestrator.git.measurement.models import FrozenCommit
from orchestrator.workflow.late_split import (
    exemption as _exemption,
    rewrites as _rewrites,
)
from orchestrator.workflow.stages.implementing import late_parks as _parks
from orchestrator.workflow.state import WorkflowLabel
from tests.git.base_sync import recovery_git_support as fixtures
from tests.git.base_sync.recovery_git_support import RecoveryGitFixtureMixin
from tests.git.base_sync.refresh_test_support import _patched
from tests.support.authorization import _authorize

# The events a second reading of this change would leave, and the label it
# would hand the issue to.
MEASUREMENT_EVENT = "late_measurement"
TRANSFER_EVENT = "late_transfer"
DECOMPOSING = "workflow:decomposing"

# What the refresh counts this branch behind base. Zero, because the replay
# the crash left is already ON the advanced base -- which is what lets the
# recovery route the reviewer rather than fall through to a second rebase.
BEHIND_BY = 0

# The park a road that may not measure takes when its permit refuses.
PARK_FAILED = "auto_base_rebase_failed"


class _AdjudicatedRecoveryCase(RecoveryGitFixtureMixin, unittest.TestCase):
    """An interrupted rebase of the very commit an adjudication accepted.

    The exemption names the head the pull request carries, the identity under
    it records what that commit contributes over the base it was measured on,
    and the operator authorization beside them is the other half of the
    bypass. What the rebase then produced is a different object carrying the
    same contribution over the advanced base -- which is the one thing a
    permit is granted on.
    """

    def setUp(self) -> None:
        super().setUp()
        # The permit holds the recorded base to the tip the REMOTE names, and
        # this fixture has no token to reach one with. It is the real advanced
        # base rather than a placeholder, because the reachability check
        # behind it is a genuine walk of this repository.
        _patched(
            self, _measurement_commits, "_freeze_base_commit",
            MagicMock(return_value=FrozenCommit(sha=self.replayed_base)),
        )
        self.accepted_digest = self._contributes(
            self.accepted_base, self.anchor,
        )
        self._adjudicate()

    def _contributes(self, base_sha: str, candidate_sha: str) -> str:
        """What one pair really contributes, read off the objects themselves."""
        return _fingerprint._fingerprint_contribution(
            self.work, base_sha, candidate_sha,
        ).digest

    def _adjudicate(self) -> None:
        """Record the verdict a settled `single` left on the anchor."""
        state = self._state()
        _exemption.record_exemption(state, self.anchor)
        _exemption.record_semantic_identity(
            state,
            base_sha=self.accepted_base,
            candidate_sha=self.anchor,
            fingerprint=self.accepted_digest,
        )
        _authorize(
            state, self.anchor, self.accepted_base, self.accepted_digest,
        )
        self.gh.write_pinned_state(self.gh._issues[fixtures.ISSUE], state)

    def _grants(self) -> None:
        """Both halves of the write the interrupted grant landed.

        The permission saying what a push may carry the verdict over, and the
        debt saying that push is owed and what it is pinned to. Together,
        because the grant makes them in one durable statement.
        """
        state = self._state()
        rewrite = _rewrites.LateRewrite(
            kind=_rewrites.LateRewriteKind.AUTO_CLEAN_REBASE,
            from_sha=self.anchor,
            from_base_sha=self.accepted_base,
            to_sha=self.recovered,
            to_base_sha=self.replayed_base,
            pr_number=fixtures.PR_NUMBER,
            source_stage=WorkflowLabel.IN_REVIEW,
            lease=self.anchor,
        )
        _rewrites.record_rewrite_authorization(
            state, rewrite, self.accepted_digest,
        )
        _parks._approve(
            state, self.recovered, self.anchor,
            _parks.LateApprovalBasis.UNMEASURED,
        )
        self.gh.write_pinned_state(self.gh._issues[fixtures.ISSUE], state)

    def _resumes(self) -> bool:
        """The tick after the crash, entered where the refresh enters it.

        Through the eligibility gate rather than through the recovery call
        directly, because what has to be proved is not only that the push goes
        out: the decision this gate hands back is what says the tick is OVER,
        so nothing behind it rebases the branch a second time or spawns
        anything over it.
        """
        issue = self.gh._issues[fixtures.ISSUE]
        decision = eligibility._auto_rebase_recovery_decision(
            _AutoRebaseContext(
                gh=self.gh,
                spec=self.spec,
                issue=issue,
                state=self.gh.read_pinned_state(issue),
                worktree=self.work,
                pr_number=fixtures.PR_NUMBER,
                behind=BEHIND_BY,
                label=fixtures.LABEL,
                pending_pre_rebase_sha=self.anchor,
            ),
            None,
        )
        return decision.should_continue

    def _state(self):
        return self.gh.read_pinned_state(self.gh._issues[fixtures.ISSUE])

    def _events_of(self, family: str) -> list[dict]:
        return [
            record for record in self.gh.recorded_events
            if record.get(fixtures.EVENT_FIELD) == family
        ]

    def _assert_the_verdict_moved(self) -> None:
        """The push landed and the exemption is on the commit it published."""
        self.assertEqual(self.push.leases, [self.anchor])
        self.assertEqual(
            fixtures.head_sha(self.remote, fixtures.BRANCH_REF),
            self.recovered,
        )
        durable = self._state()
        self.assertTrue(_exemption.is_exempt(durable, self.recovered))
        self.assertEqual(
            _rewrites.read_rewrite_authorization(durable).phase,
            _rewrites.LateRewritePhase.PUBLISHED,
        )
        self.assertEqual(
            _exemption.read_semantic_identity(durable).base_sha,
            self.replayed_base,
        )

    def _assert_nothing_was_read_again(self) -> None:
        """No count, no adjudication, and no rebase behind this tick."""
        _measurement._count_added_lines.assert_not_called()
        self.assertEqual(self._events_of(MEASUREMENT_EVENT), [])
        self.assertNotIn((fixtures.ISSUE, DECOMPOSING), self.gh.label_history)
        self.assertIn(
            (fixtures.ISSUE, fixtures.VALIDATING), self.gh.label_history,
        )
        # HEAD is the replay the dead tick left: the recovery published it
        # rather than replaying the branch a second time.
        self.assertEqual(fixtures.head_sha(self.work), self.recovered)


class CrashBeforeTheGrantTest(_AdjudicatedRecoveryCase):
    """The window between `git rebase` and the permission it was owed."""

    def setUp(self) -> None:
        super().setUp()
        self.resumed = self._resumes()

    def test_the_re_derived_evidence_earns_the_permit(self) -> None:
        # Nothing on the comment named a rewrite, so the evidence is rebuilt
        # from exactly the readings the dead tick would have taken -- and the
        # real replay of the accepted change proves out against it.
        self.assertFalse(self.resumed)
        self._assert_the_verdict_moved()
        self.assertEqual(len(self._events_of(TRANSFER_EVENT)), 1)

    def test_the_replay_is_never_read_again(self) -> None:
        self._assert_nothing_was_read_again()

    def test_the_attempt_record_is_ended(self) -> None:
        pinned = self.gh.pinned_data(fixtures.ISSUE)
        self.assertIsNone(pinned.get(fixtures.KEY_PENDING_PUSH_SHA))
        self.assertIsNone(pinned.get(fixtures.KEY_PENDING_REWRITE_SHA))


class CrashAfterTheGrantTest(_AdjudicatedRecoveryCase):
    """The window between the durable permission and the push it licensed."""

    def setUp(self) -> None:
        super().setUp()
        self._grants()
        self.resumed = self._resumes()

    def test_a_standing_permission_is_spent(self) -> None:
        # The record IS the evidence here, re-asked in full rather than
        # believed, and the receipt behind the reissued push is what finally
        # carries the verdict over.
        self.assertFalse(self.resumed)
        self._assert_the_verdict_moved()

    def test_the_debt_the_grant_left_is_paid(self) -> None:
        durable = self._state()
        self.assertEqual(_parks._approved_commit(durable), "")
        self.assertEqual(
            _parks._publication_from(
                durable, self.anchor, fixtures.PR_NUMBER,
            ),
            self.recovered,
        )

    def test_the_replay_is_never_read_again(self) -> None:
        self._assert_nothing_was_read_again()


class CrashAtTheGrantTest(_AdjudicatedRecoveryCase):
    """The window this route's own durable grant opens under itself.

    The road for a replay in flight persists the permission before it pushes,
    so a process lost between the two comes back to the shape neither half of
    the record accounts for on its own: terms with no head, and an
    authorization naming the head the checkout is standing on. Read as the
    plain in-flight window it would be refused for carrying a permission; read
    by the counts it would be refused as divergence, since a replayed branch
    is behind its own publication. Either way this route would park every
    crash its own write caused, and leave the authorization standing with
    nothing able to spend it.
    """

    def setUp(self) -> None:
        super().setUp()
        self.forget_the_replay_head()
        self._grants()
        self.counted = self.divergence_from_remote()
        self.resumed = self._resumes()

    def test_the_grant_this_route_left_vouches(self) -> None:
        # Cross-bound to the anchor it is leased against, the publication the
        # terms name, and the accepted pair the identity names -- and written
        # only once the permit had proved the contribution equal to it.
        self.assertFalse(self.resumed)
        self._assert_the_verdict_moved()

    def test_the_counts_never_decide_it(self) -> None:
        # The proof the classification is not reading the divergence: read
        # before the tick, a real replay is ahead of its publication by the
        # rebase and behind it by the object that rebase replaced.
        self.assertGreater(self.counted[0], 0)
        self.assertGreater(self.counted[1], 0)
        self.assertEqual(self.push.leases, [self.anchor])

    def test_the_replay_is_never_read_again(self) -> None:
        self._assert_nothing_was_read_again()


class UndoneRebaseTest(_AdjudicatedRecoveryCase):
    """A branch put back on the anchor with the grant still standing."""

    def setUp(self) -> None:
        super().setUp()
        self._grants()
        self.roll_back_to_the_anchor()
        self.resumed = self._resumes()

    def test_the_rollback_is_finished_not_restarted(self) -> None:
        # HEAD equalling the anchor is the shortcut only for an attempt that
        # never started. Taken here it would drop the anchor and hand the
        # branch to a fresh rebase, which force-pushes a commit no
        # adjudication has seen over the one the pull request carries.
        self.assertFalse(self.resumed)
        self.assertEqual(self.push.leases, [])
        self.assertEqual(fixtures.head_sha(self.work), self.anchor)
        self.assertEqual(
            fixtures.head_sha(self.remote, fixtures.BRANCH_REF), self.anchor,
        )
        self.assertEqual(self.gh.label_history, [])

    def test_the_abandoned_bookkeeping_goes_with_it(self) -> None:
        # The reset re-run onto the commit the branch is already on moves
        # nothing, and that is the point: it is the step the debt for a commit
        # no branch has, and the permission that will never be spent on it,
        # ride out on.
        durable = self._state()
        self.assertEqual(_parks._approved_commit(durable), "")
        self.assertFalse(_rewrites.carries_rewrite_authorization(durable))
        # The grant moved nothing, so the verdict is still where the
        # adjudication put it.
        self.assertTrue(_exemption.is_exempt(durable, self.anchor))

    def test_a_human_is_asked_what_undid_it(self) -> None:
        pinned = self.gh.pinned_data(fixtures.ISSUE)
        self.assertTrue(pinned.get(fixtures.KEY_AWAITING_HUMAN))
        self.assertEqual(pinned.get(fixtures.KEY_PARK_REASON), PARK_FAILED)
        self.assertIsNone(pinned.get(fixtures.KEY_PENDING_PUSH_SHA))


class RefusedPermitTest(_AdjudicatedRecoveryCase):
    """A replay the verdict does not account for is reset and parked."""

    def test_a_changed_contribution_is_not_published(self) -> None:
        # The identity records a contribution this replay does not carry, so
        # the permit refuses -- and measuring instead would either publish an
        # adjudicated change with the verdict left behind or route it into a
        # second adjudication.
        state = self._state()
        _exemption.record_semantic_identity(
            state,
            base_sha=self.accepted_base,
            candidate_sha=self.anchor,
            fingerprint="c" * len(self.accepted_digest),
        )
        self.gh.write_pinned_state(self.gh._issues[fixtures.ISSUE], state)

        self.assertFalse(self._resumes())

        self.assertEqual(self.push.leases, [])
        self.assertEqual(fixtures.head_sha(self.work), self.anchor)
        pinned = self.gh.pinned_data(fixtures.ISSUE)
        self.assertTrue(pinned.get(fixtures.KEY_AWAITING_HUMAN))
        self.assertEqual(
            pinned.get(fixtures.KEY_PARK_REASON), PARK_FAILED,
        )


if __name__ == "__main__":
    unittest.main()
