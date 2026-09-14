# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What a child born of a split proves before it starts work.

The owner that reclaimed the ref cannot make this safe from its side: it would
be writing another live issue's pinned comment from a worker of its own, and a
handler of the child's own that read that comment first and wrote it after
would undo whatever the owner recorded. So the decision is the child's, taken
on the child's own dispatch -- where there is nobody to race.

Driven through `_process_issue` rather than any one handler, because the issue
this is about is one no handler would touch: a consumer that ended wears `done`
or `rejected`, reopening leaves the label exactly where it was, and both are
terminal no-ops. What these cases pin down is that the park happens before any
of that is decided.
"""
from __future__ import annotations

import unittest
from unittest.mock import Mock

from orchestrator.git.snapshots.refs import SnapshotOutcome
from orchestrator.workflow.engine import issue_processing as _issue_processing
from orchestrator.workflow.late_split import ancestry as _ancestry
from orchestrator.workflow.late_split.models import LateResourceState
from orchestrator.workflow.stages.decomposition import (
    late_reuse as _late_reuse,
)
from tests.support.fakes import FakeComment, FakeUser, make_issue
from tests.workflow.fixtures import _TEST_SPEC, _agent, _PatchedWorkflowMixin
from tests.workflow.stages.decomposition.late_cleanup_support import (
    CHILD_NUMBER,
    LABEL_DONE,
    LABEL_REJECTED,
    PARENT_NUMBER,
    SNAPSHOT_REF,
    OwnerSeed,
    RecordedDelete,
    split_umbrella,
)
from tests.workflow.stages.decomposition.late_test_support import (
    CANDIDATE_SHA,
    CYCLE_ID,
    GENERATION_NUMBER,
)

_READY = "workflow:ready"

LABEL_IMPLEMENTING = "workflow:implementing"

LABEL_DECOMPOSING = "workflow:decomposing"

# The spawn the hermetic patch set holds, under the name it holds it by:
# what a guard stepped aside for would have let a stage handler reach.
_SPAWN = "run_agent"

_ANCESTRY_REF = "late_ancestry_snapshot_ref"

_ANCESTRY_SHA = "late_ancestry_snapshot_sha"

_PARKED = "awaiting_human"

# The audit record a park leaves, and what the two verdicts file one under.
_PARK_EVENT = "park_awaiting_human"

_REASON_REPOINTED = _late_reuse.PARK_SNAPSHOT_REPOINTED

# The sentence that tells a re-pointed ref apart from a reclaimed one: the
# name survived and what it stood for did not.
_REPOINTED_NOTICE = "no longer carries the commit it was preserved at"

_WORKFLOW_LOG = "orchestrator.workflow"

_WARNING = "WARNING"

# An issue of this repository that no split ever created.
_STRANGER_NUMBER = 7

# One comment id nothing else in this module hands out.
_FORGED_COMMENT_ID = 8801

# A commit this split never adjudicated: what a copy of the snapshot points at
# once anything with the shared clone has written the ref.
_ANOTHER_COMMIT = "d15ea5ed15ea5ed15ea5ed15ea5ed15ea5ed15ea"

# An issue number this repository does not have, for a body marker naming an
# owner nothing can be read from.
_MISSING_OWNER = 4242

# The two pinned fields an owner's record is unusable without, in the states
# that make it so: a consumer list this binary cannot type, and no candidate
# for a ref to be held to.
_OWNER_CONSUMERS = "late_consumers"

_OWNER_CANDIDATE = "late_candidate_sha"

_OPAQUE_CONSUMERS = '["?"]'


def _resumable(
    *,
    child_label: str = _READY,
    child_closed: bool = False,
    child_ancestry: bool = True,
    child_mirror_first: bool = True,
):
    """A child of a settled split, back in front of the workflow."""
    return split_umbrella(
        LateResourceState.RECONCILED,
        snapshot=LateResourceState.RECONCILED,
        child_label=child_label,
        owner=OwnerSeed(
            closed=True,
            child_closed=child_closed,
            child_ancestry=child_ancestry,
            child_mirror_first=child_mirror_first,
        ),
    )


def _present() -> RecordedDelete:
    """A ref this host still mirrors, which is the ordinary steady state."""
    return RecordedDelete(
        SnapshotOutcome.DELETED,
        presence=SnapshotOutcome.PRESENT,
        mirror_sha=CANDIDATE_SHA,
    )


class _ReuseCase(_PatchedWorkflowMixin):
    """The child every case here asks about, and how it is asked."""

    def child(self, seeded):
        """The one consumer, as GitHub currently holds it."""
        return seeded.github.get_issue(CHILD_NUMBER)

    def receipted(self, seeded, *, cycle: int = CYCLE_ID) -> None:
        """Leave one reclamation's receipt on the child, as its owner would."""
        seeded.github.comment(
            self.child(seeded),
            _ancestry.release_marker(
                owner=PARENT_NUMBER, cycle=cycle, generation=GENERATION_NUMBER,
            ),
        )

    def refused(self, seeded, answers: RecordedDelete, issue=None) -> bool:
        """Ask the guard about one issue, with the remote answering."""
        subject = issue or self.child(seeded)
        with answers.answering():
            return _late_reuse._refuses_reuse(
                seeded.github,
                _TEST_SPEC,
                subject,
                seeded.github.read_pinned_state(subject),
            )

    def resume(self, seeded, answers: RecordedDelete):
        """Dispatch the child as a tick would, with the remote answering.

        The whole route, not one handler: the hard-skip filter, the label
        read, and everything `_route_issue_to_handler` decides from it. What
        comes back is the held SPAWN, because the park is only half of what a
        refusal is worth -- the other half is that nothing was started against
        a ref that is gone.
        """
        child = self.child(seeded)
        with answers.answering():
            return self._run(
                lambda: _issue_processing._process_issue(
                    seeded.github, _TEST_SPEC, child,
                ),
                run_agent=_agent(),
            )[_SPAWN]

    def told(self, seeded) -> str:
        """Everything this child has been told, as one string."""
        return "\n".join(
            body for number, body in seeded.github.posted_comments
            if number == CHILD_NUMBER
        )

    def park_reasons(self, seeded) -> list:
        """What every park on this child was filed under."""
        return [
            record.get("reason")
            for record in seeded.github.recorded_events
            if record.get("event") == _PARK_EVENT
            and record.get("issue") == CHILD_NUMBER
        ]

    def assert_parked(self, seeded, *, owner: int = 0) -> None:
        """The child is stopped, names no snapshot, and was never relabelled."""
        child_state = seeded.github.pinned_data(CHILD_NUMBER)
        self.assertTrue(child_state[_PARKED])
        self.assertNotIn(_ANCESTRY_REF, child_state)
        self.assertNotIn(_ANCESTRY_SHA, child_state)
        self.assertEqual(seeded.github.label_history, [])
        if owner:
            self.assertEqual(child_state["late_ancestry_parent"], owner)


class ReuseGuardTest(_ReuseCase, unittest.TestCase):
    """A ref the remote has provably let go of stops the child that names it."""

    def test_a_reclaimed_ref_parks_before_any_work(self) -> None:
        # Dispatched as `ready`, which is where an implementation would start.
        # The park is taken before the route reaches that handler, so nothing
        # is seeded, relabelled, or spawned against a ref that is gone.
        seeded = _resumable()

        with self.assertLogs(_WORKFLOW_LOG, level=_WARNING):
            self.resume(seeded, RecordedDelete.absent())

        self.assert_parked(seeded)

    def test_a_receipt_outranks_a_ref_still_there(self) -> None:
        # The two ways the world can look untouched after a reclamation: a
        # mirror this host never got round to dropping, and a ref somebody
        # pushed again at the same commit. Neither brings back what the child
        # was promised -- that the candidate provably came from one
        # adjudication -- and the receipt is what says the reclamation
        # happened at all.
        seeded = _resumable()
        self.receipted(seeded)

        with self.assertLogs(_WORKFLOW_LOG, level=_WARNING):
            self.resume(seeded, _present())

        self.assert_parked(seeded)

    def test_a_repointed_ref_parks_the_child(self) -> None:
        # The other way the promise breaks: the ref is still there and carries
        # a commit nobody preserved, so the candidate this child was cut from
        # cannot be obtained from it. Waving that through would spawn an agent
        # against reuse instructions naming work that is not there, and the
        # reclamation refuses a re-pointed ref for a human in the same breath.
        seeded = _resumable()
        repointed = RecordedDelete(
            SnapshotOutcome.DELETED, presence=SnapshotOutcome.MISMATCH,
        )

        with self.assertLogs(_WORKFLOW_LOG, level=_WARNING):
            spawned = self.resume(seeded, repointed)

        spawned.assert_not_called()
        self.assert_parked(seeded)
        self.assertIn(
            _REPOINTED_NOTICE, self.told(seeded),
        )
        self.assertEqual(self.park_reasons(seeded), [_REASON_REPOINTED])

    def test_a_repointed_mirror_masks_nothing(self) -> None:
        # This host's copy is a ref in the object store every agent's worktree
        # shares, so a name that resolves is not a candidate. Read as one it
        # would do both halves of the damage at once: start the child on work
        # nobody adjudicated, and skip the ask that says the ref it was
        # actually promised is gone.
        seeded = _resumable()
        planted = RecordedDelete(
            SnapshotOutcome.DELETED,
            presence=SnapshotOutcome.ABSENT,
            mirror_sha=_ANOTHER_COMMIT,
        )

        with self.assertLogs(_WORKFLOW_LOG, level=_WARNING):
            spawned = self.resume(seeded, planted)

        self.assertEqual(planted.observed, [SNAPSHOT_REF])
        spawned.assert_not_called()
        self.assert_parked(seeded)

    def test_a_child_whose_seed_failed_is_parked(self) -> None:
        # The crash window the split leaves by design: a child is recorded on
        # the parent's ledger BEFORE its ancestry is seeded, so a seed that
        # failed leaves an issue the reclamation still counts as a consumer --
        # and still leaves its receipt on -- while its own pinned comment says
        # nothing at all. The body marker is what says whose child it is, and
        # the receipt is the only thing that can answer for it.
        seeded = _resumable(child_ancestry=False, child_closed=True)
        self.receipted(seeded)
        self.child(seeded).closed = False

        with self.assertLogs(_WORKFLOW_LOG, level=_WARNING):
            self.resume(seeded, _present())

        self.assert_parked(seeded, owner=PARENT_NUMBER)

    def test_an_unread_thread_holds_the_dispatch(self) -> None:
        # The receipt outranks every reading of the ref, so a thread this tick
        # could not read is not a thread with no receipt on it: what it may be
        # hiding is exactly what would overrule the readings behind it. Both
        # shapes stop there -- neither the copy this host holds nor the remote
        # is asked, because a world that looks untouched is what a recreated
        # mirror or a ref pushed again at the same commit looks like too.
        for recorded in (True, False):
            with self.subTest(recorded=recorded):
                seeded = _resumable(
                    child_ancestry=recorded, child_closed=True,
                )
                child = self.child(seeded)
                child.closed = False
                child.get_comments = Mock(side_effect=RuntimeError("503"))
                untouched = _present()

                with self.assertLogs(_WORKFLOW_LOG, level=_WARNING):
                    spawned = self.resume(seeded, untouched)

                spawned.assert_not_called()
                self.assertEqual(untouched.observed, [])
                self.assertEqual(seeded.github.write_state_calls, 0)

    def test_a_stale_write_cannot_undo_the_guard(self) -> None:
        # The interleaving the owner could not survive: a handler of the
        # child's own read its pinned comment before the reclamation and wrote
        # it after, putting the ancestry back and taking the park off. The
        # guard is evaluated by the child's own handler afterwards, so what a
        # stale write restored is read again and refused again.
        seeded = _resumable()
        github = seeded.github
        stale = dict(github.pinned_data(CHILD_NUMBER))
        with self.assertLogs(_WORKFLOW_LOG, level=_WARNING):
            self.resume(seeded, RecordedDelete.absent())
        github.seed_state(CHILD_NUMBER, **stale)
        self.assertIn(_ANCESTRY_REF, github.pinned_data(CHILD_NUMBER))

        with self.assertLogs(_WORKFLOW_LOG, level=_WARNING):
            self.resume(seeded, RecordedDelete.absent())

        self.assert_parked(seeded)


class NoWayRoundTest(_ReuseCase, unittest.TestCase):
    """Every way a child comes back, and none of them a way past this.

    The guard is asked where a label becomes a handler call, which is what
    makes the answer the same whatever brought the issue back: a label that
    never moved, one a human moved in the same gesture as the reopen, and
    one whose own handler the dispatcher normally steps aside for.
    """

    def test_a_reopened_terminal_child_is_parked(self) -> None:
        # The one the reclamation itself cannot reach: a consumer that ENDED,
        # reopened by a human afterwards. Its label is still `done`, which is
        # a dispatch no-op, so without this guard the tick would look at it and
        # do nothing at all -- leaving an open issue whose body tells whoever
        # picks it up to reuse a ref that is gone.
        for label in (LABEL_DONE, LABEL_REJECTED):
            with self.subTest(label=label):
                seeded = _resumable(child_label=label, child_closed=True)
                self.child(seeded).closed = False

                with self.assertLogs(_WORKFLOW_LOG, level=_WARNING):
                    self.resume(seeded, RecordedDelete.absent())

                self.assert_parked(seeded)

    def test_a_relabel_to_another_stage_is_no_escape(self) -> None:
        # A human who reopens and relabels in one move: the guard is asked
        # where the label becomes a handler call, so the stage it was moved to
        # is never reached.
        seeded = _resumable(child_label=LABEL_IMPLEMENTING, child_closed=False)

        with self.assertLogs(_WORKFLOW_LOG, level=_WARNING):
            self.resume(seeded, RecordedDelete.absent())

        self.assert_parked(seeded)
        self.assertEqual(seeded.github.opened_prs, [])

    def test_a_child_decomposed_when_closed_parks(self) -> None:
        # The one label the guards step aside for, and the state that wears it
        # without being in it. A consumer closed while it was being decomposed
        # comes back with `decomposing` exactly where it was and no generation
        # of its own -- so nothing on it is under adjudication, and stepping
        # aside on the label alone would spawn the decomposer against the
        # reuse instructions in its body, naming a ref that is gone.
        seeded = _resumable(child_label=LABEL_DECOMPOSING, child_closed=True)
        self.child(seeded).closed = False

        with self.assertLogs(_WORKFLOW_LOG, level=_WARNING):
            spawned = self.resume(seeded, RecordedDelete.absent())

        spawned.assert_not_called()
        self.assert_parked(seeded)

    def test_a_closed_pre_pr_child_parks_on_reopen(self) -> None:
        # The path no sweep reaches: `ready` and `blocked` are deliberately
        # never swept closed, so a consumer a human closed on one never
        # becomes terminal and never earns a pass of its own. Reopening it is
        # what brings it back, and this is where that lands.
        seeded = _resumable(child_closed=True)
        self.child(seeded).closed = False

        with self.assertLogs(_WORKFLOW_LOG, level=_WARNING):
            self.resume(seeded, RecordedDelete.absent())

        self.assert_parked(seeded)

class ReuseCostTest(_ReuseCase, unittest.TestCase):
    """What the guard does not spend, and what it does not refuse.

    It is asked of every dispatched issue, so what it costs in the ordinary
    case is what decides whether it may live there at all -- and what it
    refuses has to be the one answer that means the work is really gone.
    """

    def test_another_reclamations_receipt_is_not_ours(self) -> None:
        # Scoped by owner, cycle, and generation together: an issue splits
        # more than once, and a receipt from a later cycle says nothing about
        # the ref this child was cut from.
        seeded = _resumable()
        self.receipted(seeded, cycle=CYCLE_ID + 1)

        self.assertFalse(self.refused(seeded, _present()))
        self.assertFalse(
            seeded.github.pinned_data(CHILD_NUMBER).get(_PARKED),
        )

    def test_a_forged_receipt_speaks_for_nobody(self) -> None:
        # A hidden comment is invisible in the rendered thread and trivially
        # copied, so the author is checked with the marker -- otherwise anyone
        # could park any child of any split by pasting one.
        seeded = _resumable()
        self.child(seeded).comments.append(
            FakeComment(
                id=_FORGED_COMMENT_ID,
                body=_ancestry.release_marker(
                    owner=PARENT_NUMBER,
                    cycle=CYCLE_ID,
                    generation=GENERATION_NUMBER,
                ),
                user=FakeUser("a-passer-by"),
            ),
        )

        self.assertFalse(self.refused(seeded, _present()))

    def test_a_repaired_lineage_is_not_asked_again(self) -> None:
        # The park writes back the lineage the receipt confirmed, so the tick
        # after it reads a child that names a split and no snapshot -- which
        # is the same answer as a child this guard has already released, and
        # costs neither a thread walk nor a request.
        seeded = _resumable(child_ancestry=False, child_closed=True)
        self.receipted(seeded)
        self.child(seeded).closed = False
        with self.assertLogs(_WORKFLOW_LOG, level=_WARNING):
            self.resume(seeded, _present())
        written = seeded.github.write_state_calls

        self.assertFalse(self.refused(seeded, RecordedDelete.absent()))
        self.assertEqual(seeded.github.write_state_calls, written)

    def test_an_issue_of_no_lineage_asks_nothing(self) -> None:
        # Every issue that never came out of a split, which is most of them.
        # It stops at what the dispatcher already holds: no recorded ancestry
        # and no marker in the body, so neither the thread nor the ref is
        # asked about and no request is spent.
        seeded = _resumable()
        stranger = make_issue(_STRANGER_NUMBER, label=_READY)
        seeded.github.add_issue(stranger)
        asked = RecordedDelete.absent()

        self.assertFalse(self.refused(seeded, asked, issue=stranger))
        self.assertEqual(asked.observed, [])
        self.assertEqual(seeded.github.posted_comments, [])

    def test_a_mirrored_ref_costs_nothing(self) -> None:
        # The steady state, and why a per-dispatch guard is affordable: a
        # reclamation takes this host's copy down BEFORE the remote ref and
        # refuses to touch the remote while it survives, so a copy still here
        # answers the whole question locally. What makes that sound rather
        # than hopeful is the transport's own ordering, and the commit the
        # copy is asked for: the read is named against the candidate this
        # child was promised, since the ref it reads lives in the store the
        # agents write and a name alone proves nothing about what is under it
        # (`tests/git/snapshots/test_local_snapshots.py`).
        seeded = _resumable()
        asked = _present()

        self.assertFalse(self.refused(seeded, asked))
        self.assertEqual(asked.observed, [])
        self.assertEqual(seeded.github.write_state_calls, 0)

    def test_an_unreadable_remote_holds_the_dispatch(self) -> None:
        # An outage is evidence of nothing, so it is neither a park nor a
        # permission: the whole route stops without writing anything, and the
        # same question is asked again next tick. Parking here would strand a
        # live child on a rate-limit window; continuing would start an agent
        # against a ref nobody could vouch for.
        seeded = _resumable()
        unreadable = RecordedDelete(
            SnapshotOutcome.DELETED, presence=SnapshotOutcome.UNREADABLE,
        )

        with self.assertLogs(_WORKFLOW_LOG, level=_WARNING):
            spawned = self.resume(seeded, unreadable)

        spawned.assert_not_called()
        self.assertFalse(
            seeded.github.pinned_data(CHILD_NUMBER).get(_PARKED),
        )
        self.assertEqual(seeded.github.write_state_calls, 0)
        self.assertEqual(seeded.github.posted_comments, [])
        self.assertEqual(seeded.github.label_history, [])

    def test_a_child_whose_ref_is_there_is_left_alone(self) -> None:
        # A child of a split still running: the ref it was cut from is exactly
        # where it was, and nothing about it is parked or dropped.
        seeded = _resumable(child_label=LABEL_DONE, child_closed=True)
        asked = RecordedDelete(
            SnapshotOutcome.DELETED, presence=SnapshotOutcome.PRESENT,
        )

        self.assertFalse(self.refused(seeded, asked))
        self.assertEqual(asked.observed, [SNAPSHOT_REF])
        self.assertEqual(
            seeded.github.pinned_data(CHILD_NUMBER)[_ANCESTRY_REF],
            SNAPSHOT_REF,
        )


class AskedOfTheRemoteTest(_ReuseCase, unittest.TestCase):
    """The two shapes this host's own copy cannot answer for.

    The free local read is bought by the reclamation's ordering and by the
    pointer being a whole one, and two shapes have neither.

    One is a pointer written before that ordering existed. An orchestrator
    that deleted the remote ref first and dropped this host's copy afterwards
    -- best-effort, and past the point of no return -- could leave a mirror
    standing beside a ref that is gone; every child of a split a repository
    ran before the upgrade carries such a pointer, no pass ever revisits its
    owner again, and the receipt that would settle it was never written
    either. So the stamp the split writes is what the shortcut is conditioned
    on.

    The other is a child whose ancestry seed failed, which records no pointer
    at all -- only the marker in its body. A body is a field the world can
    write, so what that marker buys is the right to ask rather than an answer:
    the OWNER's own record is read fresh, has to name the same cycle and
    generation, and has to carry this issue among the consumers it cut from
    that ref. Vouched, it hands over the whole pointer the failed seed never
    wrote -- the ref the identity mints and the commit the owner recorded
    preserving -- and the wire is asked about exactly that. Unvouched, the
    guard has nothing to say and steps aside; unanswerable, it holds.
    """

    def test_an_unseeded_child_parks_on_a_gone_ref(self) -> None:
        # The window a receipt cannot cover: the reclamation deletes the ref
        # BEFORE it posts to anybody, so a thread read to the end with nothing
        # on it is also what that window looks like. It is not permission.
        # What answers instead is the ref the owner's ledger vouches for --
        # the one the body marker's identity names -- and its absence is what
        # stops the child.
        seeded = _resumable(child_ancestry=False, child_closed=True)
        self.child(seeded).closed = False
        reclaimed = RecordedDelete.absent()

        with self.assertLogs(_WORKFLOW_LOG, level=_WARNING):
            spawned = self.resume(seeded, reclaimed)

        self.assertEqual(reclaimed.observed, [SNAPSHOT_REF])
        spawned.assert_not_called()
        self.assert_parked(seeded, owner=PARENT_NUMBER)

    def test_an_unseeded_child_of_a_live_ref_runs(self) -> None:
        # The other side of that ask, and why it is an ask rather than a stop:
        # a split still in flight has left its ref exactly where it created
        # it, and the orphan its crash left behind is ordinary work that has
        # to keep moving. Nothing is refused, nothing is written, and what it
        # cost was the one request -- named against the candidate the owner
        # recorded, which is the half this child never wrote down.
        seeded = _resumable(child_ancestry=False, child_closed=True)
        self.child(seeded).closed = False
        live = RecordedDelete(
            SnapshotOutcome.DELETED, presence=SnapshotOutcome.PRESENT,
        )

        self.assertFalse(self.refused(seeded, live))
        self.assertEqual(live.observed, [SNAPSHOT_REF])
        self.assertEqual(seeded.github.write_state_calls, 0)

    def test_a_repointed_ref_parks_an_unseeded_child(self) -> None:
        # What the owner's recorded candidate buys: the ref is still there and
        # carries a commit nobody preserved, which an occupancy check would
        # have waved through as work to start on. It is the recorded shape's
        # verdict and the recorded shape's sentence, because the ledger is
        # what named the ref this issue never recorded.
        seeded = _resumable(child_ancestry=False, child_closed=True)
        self.child(seeded).closed = False
        repointed = RecordedDelete(
            SnapshotOutcome.DELETED, presence=SnapshotOutcome.MISMATCH,
        )

        with self.assertLogs(_WORKFLOW_LOG, level=_WARNING):
            spawned = self.resume(seeded, repointed)

        spawned.assert_not_called()
        self.assert_parked(seeded, owner=PARENT_NUMBER)
        self.assertIn(_REPOINTED_NOTICE, self.told(seeded))
        self.assertEqual(self.park_reasons(seeded), [_REASON_REPOINTED])

    def test_a_forged_marker_speaks_for_nobody(self) -> None:
        # A body is a field the world can write, and the marker in one is the
        # only lineage claim here that is not authenticated. Corroborated
        # against the split's own consumer ledger, an issue that split never
        # cut anything for is an issue this guard has nothing to say about --
        # so nothing is asked of the remote and nothing is said to a human,
        # which is the park-by-paste this check exists to refuse.
        seeded = _resumable()
        forged = make_issue(
            _STRANGER_NUMBER, label=_READY, body=_ancestry.child_marker(
                issue=PARENT_NUMBER,
                cycle=CYCLE_ID,
                generation=GENERATION_NUMBER,
                index=0,
            ),
        )
        seeded.github.add_issue(forged)
        asked = RecordedDelete.absent()

        self.assertFalse(self.refused(seeded, asked, issue=forged))
        self.assertEqual(asked.observed, [])
        self.assertEqual(seeded.github.posted_comments, [])

    def test_a_claim_nothing_can_vouch_for_is_held(self) -> None:
        # Refused and unanswerable are not the same absence. An owner nothing
        # can be read from, a consumer list this binary cannot type, and a
        # record naming no candidate to hold a ref to all leave the claim
        # standing -- it may be perfectly true and this tick cannot tell -- so
        # the dispatch is held rather than released. What that costs is an
        # issue whose own body claims a split it cannot corroborate; what
        # releasing it would cost is the child this shape exists for.
        for owner, damaged in (
            (_MISSING_OWNER, {}),
            (PARENT_NUMBER, {_OWNER_CONSUMERS: _OPAQUE_CONSUMERS}),
            (PARENT_NUMBER, {_OWNER_CANDIDATE: None}),
        ):
            with self.subTest(owner=owner, damaged=tuple(damaged)):
                seeded = _resumable()
                seeded.github.seed_state(PARENT_NUMBER, **{
                    **seeded.github.pinned_data(PARENT_NUMBER), **damaged,
                })
                claiming = make_issue(
                    _STRANGER_NUMBER, label=_READY,
                    body=_ancestry.child_marker(
                        issue=owner,
                        cycle=CYCLE_ID,
                        generation=GENERATION_NUMBER,
                        index=0,
                    ),
                )
                seeded.github.add_issue(claiming)
                asked = RecordedDelete.absent()

                with self.assertLogs(_WORKFLOW_LOG, level=_WARNING):
                    self.assertTrue(
                        self.refused(seeded, asked, issue=claiming),
                    )

                self.assertEqual(asked.observed, [])
                self.assertEqual(seeded.github.write_state_calls, 0)

    def test_an_unstamped_pointer_asks_the_remote(self) -> None:
        seeded = _resumable(child_mirror_first=False)
        # The state the shortcut alone would misread: this host's copy is
        # still here, and the ref it mirrors has been reclaimed.
        reclaimed = RecordedDelete(
            SnapshotOutcome.DELETED,
            presence=SnapshotOutcome.ABSENT,
            mirror_sha=CANDIDATE_SHA,
        )

        with self.assertLogs(_WORKFLOW_LOG, level=_WARNING):
            spawned = self.resume(seeded, reclaimed)

        self.assertEqual(reclaimed.observed, [SNAPSHOT_REF])
        spawned.assert_not_called()
        self.assert_parked(seeded)

    def test_a_stamped_pointer_trusts_the_mirror(self) -> None:
        # The same world, one field apart: a pointer this binary wrote is a
        # claim about the ordering that can take the ref, so the copy still
        # here settles it and nothing goes on the wire.
        seeded = _resumable()

        self.assertFalse(self.refused(seeded, _present()))


if __name__ == "__main__":
    unittest.main()
