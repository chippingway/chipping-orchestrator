# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The fresh cycle an operator authorizes by taking `rejected` back off."""
from __future__ import annotations

import unittest
from dataclasses import replace
from unittest.mock import Mock, patch

from orchestrator.config import settings as config
from orchestrator.workflow.late_split import state as _late_state
from orchestrator.workflow.late_split.models import (
    LateFailure,
    LateResourceState,
)
from orchestrator.workflow.stages.decomposition import (
    late_restart as _late_restart,
)
from orchestrator.workflow.state import WorkflowLabel
from tests.workflow.stages.decomposition import late_restart_support as _fix
from tests.workflow.stages.decomposition.late_seam_support import (
    local_teardown,
)
from tests.workflow.stages.decomposition.late_test_support import (
    CYCLE_ID,
    LATE_ISSUE_NUMBER,
)

_CONFIG_DECOMPOSE = "DECOMPOSE"
_CONFIG_ALLOWLIST = "ALLOWED_ISSUE_AUTHORS"

_SET_WORKFLOW_LABEL = "set_workflow_label"
_WRITE_PINNED_STATE = "write_pinned_state"
_ANNOUNCED_STEP = "_announced"
_RETIRED_STEP = "_retired"
_LAST_APPLIED = "last_workflow_label_applied"

_REFUSED = "github said no"

_RESTARTED = ((LATE_ISSUE_NUMBER, WorkflowLabel.DECOMPOSING),)

# The one entry every terminal this issue reaches leaves in the history.
_TERMINAL = (LATE_ISSUE_NUMBER, WorkflowLabel.REJECTED)

# The two states the current `DECOMPOSE` setting chooses between, and the only
# two a restart may apply.
_DECOMPOSE_ROUTES = (
    (True, WorkflowLabel.DECOMPOSING),
    (False, WorkflowLabel.IMPLEMENTING),
)

# The damaged identities, each with the ancestry standing beside it and the
# root the repair therefore lands on: a record that cannot name its own issue
# is one whose remaining lineage claims nothing vouches for, so the ancestry
# answers for both -- and an owner with no ancestry is its own root.
_DAMAGED_ROOTS = (
    (
        replace(_fix.CANCELLED, current_issue=_fix.FOREIGN_ISSUE),
        {_fix.KEY_ANCESTRY_ROOT: _fix.ANCESTRY_ROOT},
        _fix.ANCESTRY_ROOT,
    ),
    (replace(_fix.CANCELLED, root_issue=0), {}, LATE_ISSUE_NUMBER),
)

# Every state an obligation can be left in that is not `reconciled`, each of
# which is still owed to the remote.
_STILL_OWED = (
    LateResourceState.PENDING,
    LateResourceState.RETAINED,
    LateResourceState.FAILED,
)


class AuthorizedRestartTest(_fix.RestartCase, unittest.TestCase):
    """What the removal of `rejected` over a settled cancellation earns."""

    def test_the_gesture_starts_a_fresh_cycle(self) -> None:
        self._seed()

        dispatched = self._reported_route()

        dispatched.assert_not_called()
        self.assertEqual(self._notice_count(), 1)
        self.assertEqual(self._labels(), _RESTARTED)
        self.assertEqual(
            self._pinned()[_fix.KEY_CYCLE_ID], _fix.RESTART_CYCLE_ID,
        )
        self.assertNotIn(_fix.KEY_RESTART_PENDING, self._pinned())

    def test_each_decompose_route_is_applied(self) -> None:
        # The restart puts the issue back where a first pickup would have put
        # it, so the kill switch decides between the same two states here.
        for decompose, target in _DECOMPOSE_ROUTES:
            with self.subTest(decompose=decompose):
                self._seed()
                with patch.object(config, _CONFIG_DECOMPOSE, decompose):
                    self._reported_route()

                self.assertEqual(
                    self._labels(),
                    ((LATE_ISSUE_NUMBER, target),),
                )
                self.assertIn(target, self._notices()[0])

    def test_an_outsider_is_restarted_all_the_same(self) -> None:
        # `ALLOWED_ISSUE_AUTHORS` guards the path a stranger reaches on their
        # own -- filing an issue nobody has labelled. Nobody files their way to
        # here: it takes a pinned comment only this orchestrator writes and a
        # label removal only a repository's own people may make, so the gesture
        # is what authorizes the fresh attempt.
        self._seed(author=_fix.OUTSIDER)

        with patch.object(config, _CONFIG_ALLOWLIST, (_fix.HUMAN,)):
            self._reported_route()

        self.assertEqual(self._labels(), _RESTARTED)

    def test_a_control_label_defers_it(self) -> None:
        # Every step is a write, and the authorization is durable on the
        # issue's own surface -- so the fresh cycle waits rather than being
        # started where an operator said not to react.
        for control in ("paused", "backlog"):
            with self.subTest(control=control):
                self._seed(label=control)

                self._reported_route()

                self.assertEqual(self._notices(), [])
                self.assertEqual(self.github.label_history, [])
                self.assertNotIn(_fix.KEY_RESTART_PENDING, self._pinned())


class InertRecordTest(_fix.RestartCase, unittest.TestCase):
    """Every record the gesture does not authorize a restart over."""

    def test_a_rejection_with_no_cycle_is_inert(self) -> None:
        # A `rejected` issue somewhere else in the workflow reached its
        # terminal for its own reasons, and taking the label off leaves the
        # record that workflow ended on. Greeting it as new would mint a SECOND
        # pinned comment -- invisible from the moment it is written, since the
        # first authenticated one is the one every read answers with -- while
        # the pull request and branch the old one names go on being nobody's.
        self._seed(
            replace(_fix.CANCELLED, cycle_id=0), **_fix.CARRIED_OVER,
        )

        dispatched = self._route()

        dispatched.assert_not_called()
        self.assertEqual(self.github.posted_comments, [])
        self.assertEqual(self.github.label_history, [])
        self.assertEqual(self.github.write_state_calls, 0)
        self.assertEqual(self._pinned(), dict(_fix.CARRIED_OVER))

    def test_an_unsettled_ending_is_not_restarted(self) -> None:
        # The fresh cycle keeps no ledger, so restarting over an obligation
        # still owed would discharge it by forgetting it. That is the cleanup
        # path's to finish first.
        for owed in _STILL_OWED:
            with self.subTest(owed=owed):
                self._seed(_fix.owing_cycle(owed))

                dispatched = self._reported_route()

                dispatched.assert_not_called()
                self.assertEqual(self._notices(), [])
                self.assertNotIn(_fix.KEY_RESTART_PENDING, self._pinned())

    def test_an_unprovable_hold_is_not_restarted(self) -> None:
        # The obligation no ledger entry carries, and the one the cancellation
        # holds its own terminal for: a plan PR number with no preserved
        # description beside it. Projecting the fresh cycle over it would drop
        # the last thing on the issue naming a pull request this orchestrator
        # left marked and open, on an issue nothing revisits afterwards.
        self._seed(_fix.UNPROVABLE_HOLD)

        dispatched = self._reported_route()

        dispatched.assert_not_called()
        self.assertEqual(self._notices(), [])
        self.assertNotIn(_fix.KEY_RESTART_PENDING, self._pinned())
        self.assertEqual(
            self._pinned()[_fix.KEY_PLAN_PR_NUMBER], _fix.PLAN_PR_NUMBER,
        )

    def test_an_undischarged_child_receipt_holds_it(self) -> None:
        # The obligation the ending's own reading walks past -- it lists
        # branches, refs, and plan pull requests -- so only the domain's counts
        # it. Restarting here would reach the retirement and be refused there,
        # with the marker down and the label already applied; falling through
        # instead would hand a cancelled cycle to the pickup path.
        self._seed(_fix.owing_child())

        dispatched = self._reported_route()

        dispatched.assert_not_called()
        self.assertEqual(self._notices(), [])
        self.assertNotIn(_fix.KEY_RESTART_PENDING, self._pinned())

    def test_a_missing_terminal_is_written_first(self) -> None:
        # The gesture is removing `rejected`, and an issue whose workflow label
        # a human stripped while the cleanup was still running wears exactly
        # the same nothing -- so the record is what separates them. This cycle
        # never reached a state its terminal could be written from, so nobody
        # removed anything: the ending writes the terminal it still owes, and
        # the fresh cycle waits for an operator to take THAT off.
        self._seed(terminal=False)

        dispatched = self._reported_route()

        dispatched.assert_not_called()
        self.assertEqual(self._notices(), [])
        self.assertEqual(
            self._labels(),
            (_TERMINAL,),
        )
        self.assertEqual(
            self._pinned()[_fix.KEY_TERMINAL_CYCLE], CYCLE_ID,
        )

    def test_a_closed_issue_is_never_restarted(self) -> None:
        # The gesture is a reopen AND a label removal. A closed issue is the
        # cleanup sweep's, whatever its record says.
        self._seed()
        self.issue.closed = True

        self._route()

        self.assertEqual(self._notices(), [])
        self.assertEqual(self._labels(), ())


class TerminalProofTest(_fix.RestartCase, unittest.TestCase):
    """What makes a removed `rejected` a gesture rather than an absence."""

    def test_a_refused_terminal_is_no_gesture(self) -> None:
        # Two ticks. The first settles the cycle and cannot get `rejected` onto
        # the issue, which leaves an owner unlabeled for the reason it always
        # was -- so the second must retry that write rather than read the
        # attempt as a removal and start a cycle nobody asked for.
        self._seed(terminal=False)
        with patch.object(
            self.github,
            _SET_WORKFLOW_LABEL,
            side_effect=RuntimeError(_REFUSED),
        ):
            self._reported_route()
        self.assertNotIn(_fix.KEY_TERMINAL_CONFIRMED, self._pinned())

        dispatched = self._reported_route()

        dispatched.assert_not_called()
        self.assertEqual(self._notices(), [])
        self.assertEqual(
            self._labels(),
            (_TERMINAL,),
        )
        self.assertTrue(self._pinned()[_fix.KEY_TERMINAL_CONFIRMED])

    def test_a_stale_label_cache_proves_it_too(self) -> None:
        # `stale_label_cache` reproduces PyGithub: `set_labels(REJECTED)`
        # writes the remote and leaves the cached `self.issue.labels` where it
        # was, so a pass that read the label back after writing it would see
        # the one the issue wore a moment ago and record nothing. The proof
        # available to the pass that made the write is the write RETURNING --
        # and it has to take it, because a CLOSED owner leaves the sweep on
        # that write and gets no second visit to see the label for itself.
        # What that costs when it is missed is the operator's gesture: one
        # reopen and one removal reapply the terminal instead of restarting.
        self._seed(terminal=False)
        self.github._stale_label_cache = True
        self.issue.closed = True
        self._reported_route()

        self.issue.closed = False
        dispatched = self._reported_route()

        dispatched.assert_not_called()
        self.assertEqual(self._notice_count(), 1)
        self.assertEqual(self._labels(), (
            _TERMINAL,
            (LATE_ISSUE_NUMBER, WorkflowLabel.DECOMPOSING),
        ))

    def test_a_death_before_the_receipt_recovers(self) -> None:
        # The one window neither half of the receipt covers: the label landed
        # and the process died before the proof. A terminal is on no sweep's
        # list, so nothing revisits the closed owner -- the operator's reopen
        # is the next thing that happens, and their removal leaves a record
        # that looks exactly like a terminal write GitHub refused. The remote's
        # own label history is what separates the two, and it is asked from
        # behind the reconciliation -- so the tick that recovers the proof is
        # the one before the tick that restarts.
        _fix.crashed_ending(self)
        self.issue.closed = False
        self.issue.labels = []

        self._reported_route()
        dispatched = self._reported_route()

        dispatched.assert_not_called()
        self.assertEqual(self._notice_count(), 1)
        self.assertEqual(self._labels(), (_TERMINAL, *_RESTARTED))

    def test_an_unreadable_history_writes_it_again(self) -> None:
        # A read that established nothing is not a `no`, and it is not a yes
        # either. Both fall the same way: the terminal is written again rather
        # than a fresh cycle started on a removal nobody could show was made.
        _fix.crashed_ending(self)
        self.issue.closed = False
        self.issue.labels = []

        with patch.object(self.github, _LAST_APPLIED, return_value=None):
            self._reported_route()

        self.assertEqual(self._notices(), [])
        self.assertEqual(self._labels(), (
            _TERMINAL,
            _TERMINAL,
        ))

    def test_an_older_terminal_is_proved_on_sight(self) -> None:
        # A cancellation that reached `rejected` before this record existed
        # carries nothing saying so. The proof a pass that made no write can
        # take is a READING, so the visit that finds such an issue still
        # wearing the label writes down what it can see -- and the operator's
        # FIRST removal is the one that authorizes the fresh cycle.
        self._seed(terminal=False, label=WorkflowLabel.REJECTED)
        self._reported_route()
        self.assertTrue(self._pinned()[_fix.KEY_TERMINAL_CONFIRMED])

        self.issue.labels = []
        self._reported_route()

        self.assertEqual(self._notice_count(), 1)
        self.assertEqual(
            self._pinned()[_fix.KEY_CYCLE_ID], _fix.RESTART_CYCLE_ID,
        )


    def test_a_legacy_terminal_is_recovered(self) -> None:
        # A cancellation that ended before the terminal record existed carries
        # neither half of it. Reopened and unlabelled inside one poll interval,
        # no pass ever saw the label -- so the remote's history is the only
        # thing that says the removal was made, and requiring a DECISION beside
        # it would leave every such issue needing a second one.
        self._seed(terminal=False)
        # The double's ordered history IS the timeline, so an entry appended
        # to it is a `labeled` event GitHub kept from before this record
        # existed -- which no pinned state of this binary's could have written.
        self.github.label_history.append(_TERMINAL)

        self._reported_route()
        dispatched = self._reported_route()

        dispatched.assert_not_called()
        self.assertEqual(self._notice_count(), 1)
        self.assertEqual(self._labels(), (_TERMINAL, *_RESTARTED))

    def test_a_branch_the_ending_finds_is_reclaimed(self) -> None:
        # The proof is adopted from BEHIND the reconciliation, because what
        # decides whether anything is owed is the record the ending has just
        # settled rather than the one it found. This cycle was cancelled
        # between the supersession and the write that records the branch it
        # superseded, so nothing on the ledger names that branch until the
        # ending discovers it -- and a restart in front of that would project
        # it away with the receipt it was derived from.
        self._seed(_fix.ANNOUNCED, terminal=False, **{
            _fix.KEY_BRANCH: _fix.SUPERSEDED_BRANCH,
        })
        self.github.label_history.append(_TERMINAL)

        # The local half of a reclamation is held: a real `git worktree
        # remove` here is a command against whatever directory the configured
        # root happens to name.
        with local_teardown():
            self._reported_route()

        self.assertEqual(
            self.github.deleted_remote_branches, [_fix.SUPERSEDED_BRANCH],
        )
        self.assertEqual(self._notices(), [])
        self.assertTrue(self._pinned()[_fix.KEY_TERMINAL_CONFIRMED])

class RepeatCycleTest(_fix.RestartCase, unittest.TestCase):
    """What an issue that has already reached this terminal once proves."""

    def test_a_previous_terminal_is_no_proof(self) -> None:
        # An issue reaches `rejected` once per cycle, so a repeat carries an
        # older one in its history -- and adopting that would authorize a
        # fresh cycle off a removal an operator made a cycle ago. What
        # separates them is that the restart between the two applied a label
        # of its own, so the newest application is the restart's target rather
        # than the terminal. This cycle's own write failed, so the ending
        # still owes it: written again, and no second notice.
        self._ended_and_restarted()

        self._ending_refused()

        self.assertEqual(self._notice_count(), 1)
        self.assertEqual(self._labels(), (
            _TERMINAL,
            (LATE_ISSUE_NUMBER, WorkflowLabel.DECOMPOSING),
            _TERMINAL,
        ))

    def test_a_hand_applied_target_is_reapplied(self) -> None:
        # What separates one cycle's terminal from the next's is the restart's
        # OWN application of its target, and a collaborator applying that same
        # name is not one: GitHub records no event for a label already there,
        # so a cycle minted over it would leave the predecessor's `rejected`
        # standing as the newest thing this orchestrator applied -- and the
        # next unlabeled cancellation would adopt that as proof of a terminal
        # it never reached. The name is taken off and put back for that
        # reason, so the ending owes its own `rejected` exactly as before.
        self._ended_and_restarted(by_hand=True)

        self._ending_refused()

        self.assertEqual(self._notice_count(), 1)
        self.assertEqual(self._labels(), (
            _TERMINAL,
            (LATE_ISSUE_NUMBER, None),
            (LATE_ISSUE_NUMBER, WorkflowLabel.DECOMPOSING),
            _TERMINAL,
        ))

    def _ended_and_restarted(self, *, by_hand: bool = False) -> None:
        """One whole cycle: its terminal, the gesture, and the fresh cycle.

        `by_hand` is the same cycle restarted onto a target somebody else
        applied. The window is the one the marker exists for: the pass that
        would have written the label is refused, and the label arrives from
        outside the workflow before the next pass resumes.
        """
        self._seed(terminal=False)
        self.issue.closed = True
        self._reported_route()
        self.issue.closed = False
        self.issue.labels = []
        if by_hand:
            self._refused_label()
            self.github.apply_foreign_label(
                self.issue, WorkflowLabel.DECOMPOSING,
            )
        self._reported_route()

    def _ending_refused(self) -> None:
        """The fresh cycle cancelled and settled, its terminal write refused."""
        self._recancel(_fix.RESTART_CYCLE_ID)
        self.issue.labels = []
        self._refused_label()
        self._reported_route()

    def _refused_label(self) -> None:
        """One pass whose workflow-label write GitHub declines."""
        with patch.object(
            self.github,
            _SET_WORKFLOW_LABEL,
            side_effect=RuntimeError(_REFUSED),
        ):
            self._reported_route()

    def _recancel(self, cycle_id: int) -> None:
        """End the cycle this issue is on now, settled and owing nothing.

        What a second late cycle looks like once its own owner was closed: the
        identities the restart projected, cancelled, with no ledger. The pinned
        comment is rewritten in place, so the thread and the label history the
        first cycle left are exactly as they were.
        """
        recorded = self.github.read_pinned_state(self.issue)
        _late_state.write_late_generation(recorded, replace(
            _fix.CANCELLED, cycle_id=cycle_id, restart_predecessor=CYCLE_ID,
        ))
        self.github.seed_state(LATE_ISSUE_NUMBER, **recorded.data)


class RestartTransactionTest(_fix.RestartCase, unittest.TestCase):
    """Each boundary a crash can leave the transaction standing at."""

    def test_a_pass_that_wrote_nothing_re_mints(self) -> None:
        # The marker is the first durable thing, so a pinned write that never
        # landed leaves the record exactly as it was -- and the cycle a restart
        # may name is one more than the cycle in hand, so the next pass names
        # the same one rather than skipping a number.
        self._seed()
        with patch.object(
            self.github,
            _WRITE_PINNED_STATE,
            side_effect=RuntimeError(_REFUSED),
        ), self.assertRaises(RuntimeError):
            self._reported_route()
        self.assertNotIn(_fix.KEY_RESTART_PENDING, self._pinned())

        self._reported_route()

        self.assertEqual(
            self._pinned()[_fix.KEY_CYCLE_ID], _fix.RESTART_CYCLE_ID,
        )

    def test_a_marker_is_resumed_not_re_minted(self) -> None:
        # The whole reason the marker goes down first: a second pass finishes
        # the cycle the first one named rather than minting another and
        # announcing it again.
        self._seed()
        with patch.object(
            _late_restart, _ANNOUNCED_STEP, side_effect=RuntimeError(_REFUSED),
        ):
            self._reported_route()
        held = self._pinned()

        self._reported_route()

        self.assertEqual(held[_fix.KEY_RESTART_CYCLE_ID], _fix.RESTART_CYCLE_ID)
        self.assertEqual(held[_fix.KEY_RESTART_PREDECESSOR], CYCLE_ID)
        self.assertEqual(
            held[_fix.KEY_RESTART_TARGET], WorkflowLabel.DECOMPOSING,
        )
        self.assertEqual(self._notice_count(), 1)
        self.assertEqual(
            self._pinned()[_fix.KEY_CYCLE_ID], _fix.RESTART_CYCLE_ID,
        )

    def test_a_notice_is_not_said_twice(self) -> None:
        # The comment and the record of it cannot be made one operation, so the
        # thread is what proves it: a pass that posted and then could not
        # relabel resumes at the label alone. The id that notice took was
        # tracked in memory by the pass that lost it, so the resuming pass has
        # to adopt it off the thread -- the projection keeps exactly the
        # bounded id ledger, and a fresh cycle that could not recognize the
        # comment announcing it would read that comment as a human's.
        self._seed()
        self._refused_label()

        self._reported_route()

        self.assertEqual(self._notice_count(), 1)
        self.assertEqual(self._labels(), _RESTARTED)
        self.assertEqual(self._pinned(), _fix.fresh_state(**{
            _fix.KEY_ORCHESTRATOR_IDS: [_fix.notice_id(self)],
        }))

    def test_a_refused_effect_holds_the_marker(self) -> None:
        self._seed()

        self._refused_label()

        self.assertTrue(self._pinned()[_fix.KEY_RESTART_PENDING])
        self.assertEqual(
            [
                record["failure"]
                for record in _fix.records_named(self, _fix.EVENT_LATE_FAILURE)
            ],
            [LateFailure.RESTART_FAILED],
        )

    def test_an_applied_label_is_not_undone(self) -> None:
        # The boundary that would otherwise be fatal: the issue wears its
        # target over a record that still says cancelled, and the refusal
        # beside this guard would answer that by handing it `rejected` again.
        self._seed()
        with patch.object(_late_restart, _RETIRED_STEP, Mock()):
            self._reported_route()

        dispatched = self._reported_route()

        dispatched.assert_not_called()
        self.assertEqual(self._labels(), _RESTARTED)
        self.assertEqual(self._notice_count(), 1)
        self.assertNotIn(_fix.KEY_RESTART_PENDING, self._pinned())

    def test_a_retired_restart_is_not_re_entered(self) -> None:
        # What the retirement buys: the fresh cycle is an ordinary one, so the
        # next tick dispatches the issue to the stage its label names.
        self._seed()
        self._reported_route()

        dispatched = self._route()

        dispatched.assert_called_once()
        self.assertEqual(self._notice_count(), 1)
        self.assertEqual(self._labels(), _RESTARTED)

    def _refused_label(self) -> None:
        """One pass whose relabel GitHub declines."""
        with patch.object(
            self.github,
            _SET_WORKFLOW_LABEL,
            side_effect=RuntimeError(_REFUSED),
        ):
            self._reported_route()


class RestartProjectionTest(_fix.RestartCase, unittest.TestCase):
    """What a fresh cycle inherits, which is what is true about the issue."""

    def test_the_comment_is_the_fresh_cycle(self) -> None:
        self._seed(**_fix.CARRIED_OVER, **_fix.KEPT)

        self._reported_route()

        self.assertEqual(self._pinned(), _fix.fresh_state(**{
            **_fix.KEPT,
            _fix.KEY_ORCHESTRATOR_IDS: [
                *_fix.SEEDED_COMMENT_IDS, _fix.notice_id(self),
            ],
        }))

    def test_a_damaged_identity_is_rebuilt(self) -> None:
        # The projection carries the identity forward, so a record that could
        # not name its own issue -- or named no root a record can be joined by
        # -- would hand the fresh cycle one nothing can correlate. The current
        # issue is the issue the pinned comment was read off; the root falls
        # back to the ancestry, and to this issue where there is none.
        for damaged, ancestry, root in _DAMAGED_ROOTS:
            with self.subTest(current_issue=damaged.current_issue):
                self._seed(damaged, **ancestry)

                self._reported_route()

                self.assertEqual(
                    self._pinned()[_fix.KEY_CURRENT_ISSUE], LATE_ISSUE_NUMBER,
                )
                self.assertEqual(self._pinned()[_fix.KEY_ROOT_ISSUE], root)

    def test_the_comment_keeps_its_identity(self) -> None:
        # The projection rewrites the payload of the comment it was read from.
        # A second pinned comment is one `read_pinned_state` would never
        # return, since it answers with the first authenticated one it finds.
        self._seed()
        seeded = self.github.read_pinned_state(self.issue).comment_id

        self._reported_route()

        self.assertEqual(
            self.github.read_pinned_state(self.issue).comment_id, seeded,
        )


class RestartRecordsTest(_fix.RestartCase, unittest.TestCase):
    """Both halves of the transaction, on both sinks, once each."""

    def test_a_stale_cache_keeps_the_stage(self) -> None:
        # `stale_label_cache` reproduces PyGithub: the label the restart just
        # applied is not on the cached issue, so reading it back would file
        # the reconciled record under the state the issue was in BEFORE the
        # restart -- which for the ordinary entry is no state at all. The
        # marker named the target before either effect ran.
        self._seed()
        self.github._stale_label_cache = True

        self._reported_route()

        self.assertEqual(
            [
                record.get("stage")
                for record in _fix.records_named(self, _fix.EVENT_LATE_RESTART)
            ],
            [None, _fix.DECOMPOSING_STAGE],
        )

    def test_each_half_is_recorded_once(self) -> None:
        self._seed()

        self._reported_route()
        self._route()

        recorded = _fix.records_named(self, _fix.EVENT_LATE_RESTART)
        self.assertEqual(
            [record["restart_step"] for record in recorded],
            ["pending", "reconciled"],
        )
        self.assertEqual(
            [record["cycle_id"] for record in recorded],
            [CYCLE_ID, _fix.RESTART_CYCLE_ID],
        )
        self.assertEqual(
            [record["predecessor_cycle_id"] for record in recorded],
            [CYCLE_ID, CYCLE_ID],
        )
        self.assertEqual(
            recorded[0]["restart_target"], WorkflowLabel.DECOMPOSING,
        )

    def test_a_damaged_identity_still_records(self) -> None:
        # Both sinks key a record on the generation's own identity: a foreign
        # `current_issue` files this restart under an issue it is not about,
        # and a root the contract cannot join produces no record at all -- a
        # restart that ran to completion saying nothing about itself.
        for damaged in _fix.DAMAGED_IDENTITIES:
            with self.subTest(root_issue=damaged.root_issue):
                self._seed(damaged)

                self._reported_route()

                self.assertEqual(
                    [
                        record["issue"]
                        for record in _fix.records_named(self, _fix.EVENT_LATE_RESTART)
                    ],
                    [LATE_ISSUE_NUMBER, LATE_ISSUE_NUMBER],
                )


if __name__ == "__main__":
    unittest.main()
