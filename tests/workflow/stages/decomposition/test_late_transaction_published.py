# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""A split whose candidate was measured on a pull request that already exists.

The transaction closes the pull request this cycle's work is on, hands the
issue to `umbrella`, activates the children, and reclaims the branch. Which
pull request that is depends on the side of publication the generation was
entered on -- the plan one before the first push, the implementation one past
it -- and the second is the sharper of the two: left unsuperseded it is an
open change carrying work nobody will finish, pointing at a branch the
reclamation has already deleted.

So it is proved before it is closed, and the proof is the settlement's own.
A pull request nothing could read, one a human settled while the adjudication
was open, and one somebody pushed to are each a refusal with a durable retry
rather than a supersession taken on evidence that has been overtaken. The
hold this cycle put on that same pull request comes off ahead of all of it,
because a change closed while it still wears a "do not merge" notice wears it
for good.

That the road is entered at all is the first case here and is driven from the
coordinator, since nothing below it would notice a post-publication verdict
that never arrived.
"""
from __future__ import annotations

import unittest

from orchestrator.workflow.stages.decomposition import (
    late_hold as _late_hold,
    late_park_state as _late_park_state,
    late_retirement as _late_retirement,
    late_transaction as _late_transaction,
    parents as _parents,
)
from orchestrator.workflow.stages.decomposition.late_models import (
    _LateDisposition,
)
from orchestrator.workflow.state import WorkflowLabel
from tests.workflow.stages.decomposition.late_crash_support import (
    killed_after,
    refusing,
)
from tests.workflow.stages.decomposition.late_published_split_support import (
    MOVED_PUBLISHED_HEAD,
    PUBLISHED_BODY,
    PUBLISHED_ISSUE_BRANCH,
    STATE_CLOSED,
    STATE_OPEN,
    PublishedSplitCase,
    seeded_published_split,
)
from tests.workflow.stages.decomposition.late_race_support import (
    RecordedLookups,
    interleaved_after,
)
from tests.workflow.stages.decomposition.late_run_support import (
    adjudicate,
    agent_reply,
)
from tests.workflow.stages.decomposition.late_test_support import (
    CANDIDATE_SHA,
    KEYS,
    LATE_ISSUE_NUMBER,
    PUBLISHED_PR_NUMBER,
    SPLIT_REPLY,
)
from tests.workflow.stages.decomposition.late_transaction_support import (
    CHILDREN,
    ERROR,
    KEY_PR_NUMBER,
    KEY_RESOURCES,
    SNAPSHOT_REF,
    SUPERSESSION_MARKER,
    first_child,
    label_of,
)

STATE_RECONCILED = "reconciled"
STATE_FAILED = "failed"
RESOURCE_PLAN_PR = "plan_pr"
RESOURCE_BRANCH = "branch"
STATE_PENDING = "pending"
GET_PR = "get_pr"
EDIT_PR_BODY = "edit_pr_body"
# The step a crash lands past on this road: the close is made and its
# obligation recorded, and the retirement behind it never runs.
SUPERSEDED = "_superseded"
# The step in front of it: the publication has been proved and the close it
# licenses has not been made, which is the interval a proof goes stale in.
PROVED = "_publication_is_still_the_one"
# The barrier every step of the tail takes, and the two seams past the
# retirement it stands in front of: the scan the release of the children is
# decided on, and the activation walk itself. Past the retirement there is no
# record to park, so what a refusal buys is the step declined.
HOLDS = "_publication_holds"
ACTIVATED = "_activated"
CHILD_SCAN = "_read_child_labels"

# How many times this road asks GitHub about the publication on a pass that
# settles: the proof the close is decided on, the confirming read the close is
# made against, and one apiece in front of the retirement, the release of the
# children, and the delete of the branch. Every one of them guards an effect
# nothing takes back, which is why none of them is shared with another.
PUBLICATION_READS = 5

# How many slices the reply a coordinator-driven case answers with declares.
SPLIT_SLICES = 2


class PublishedSplitWiringTest(unittest.TestCase):
    """A generation entered past the first push reaches the same transaction.

    Driven from the coordinator rather than from a guarded handoff, because
    what this is about is the road as a whole: the hold this cycle takes on
    the publication before an agent starts, the owner read behind the run, and
    the transaction the cleared split then hands to. Every step below it has
    cases of its own; none of them would notice if a post-publication verdict
    never arrived here at all.
    """

    def test_a_published_split_settles_end_to_end(self) -> None:
        github, issue, published = seeded_published_split()

        outcome, spawn = adjudicate(
            github, issue, agent_reply(SPLIT_REPLY), transact=True,
        )

        spawn.assert_called_once()
        self.assertEqual(outcome.disposition, _LateDisposition.SETTLED)
        self.assertEqual(len(github.created_child_issues), SPLIT_SLICES)
        self.assertEqual(published.state, STATE_CLOSED)
        self.assertEqual(
            label_of(github, LATE_ISSUE_NUMBER), WorkflowLabel.UMBRELLA,
        )
        # And the branch that publication was standing on is taken back, which
        # is safe only behind the ref the children were cut from.
        self.assertEqual(
            github.deleted_remote_branches, [PUBLISHED_ISSUE_BRANCH],
        )


class PublishedSupersessionTest(PublishedSplitCase, unittest.TestCase):
    """The publication is told where the work went, and closed."""

    def test_it_closes_the_publication(self) -> None:
        # Without this the transaction clears `pr_number`, lets the children
        # loose, and deletes the branch, leaving an open pull request carrying
        # superseded work with nothing on it saying so.
        self._transact(generation=self.generation)

        self.assertEqual(self.published_pr.state, STATE_CLOSED)
        self.assertIn(
            SUPERSESSION_MARKER, self.github.posted_pr_comments[-1][1],
        )

    def test_it_restores_the_description_it_held(self) -> None:
        # A change closed while it still wears this cycle's "do not merge"
        # notice wears it for good, and the description that notice displaced
        # is the only copy there was.
        self._transact(generation=self.held_publication())

        self.assertEqual(self.published_pr.body, PUBLISHED_BODY)
        self.assertEqual(self.published_pr.state, STATE_CLOSED)

    def test_the_notice_links_forward_to_everything(self) -> None:
        self._transact(generation=self.generation)

        notice = self.github.posted_pr_comments[-1][1]
        self.assertIn(f"#{LATE_ISSUE_NUMBER}", notice)
        self.assertIn(SNAPSHOT_REF, notice)
        self.assertIn(CANDIDATE_SHA, notice)

    def test_every_effect_is_asked_for_afresh(self) -> None:
        # Every reading on this road guards one effect and no other, and each
        # names the pull request the entry froze. A step sharing the reading
        # in front of it would be a step licensed by evidence a human had time
        # to overtake -- which is the whole shape this road is built in.
        looked_up = RecordedLookups()

        with looked_up.recording(self.github):
            self._transact(generation=self.generation)

        self.assertEqual(len(looked_up.numbers), PUBLICATION_READS)
        self.assertEqual(set(looked_up.numbers), {PUBLISHED_PR_NUMBER})

    def test_no_thread_scan_stands_before_the_close(self) -> None:
        # The helper would otherwise search the thread for its own receipt
        # before posting, and that search is a request standing between this
        # pass's confirmation and the close it authorizes -- long enough for a
        # human to settle the change, after which the notice lands on their
        # settlement and this pass reports success and hands the work on.
        # Nothing can move the answer in that window, since the marker counts
        # only on a comment of ours and this pass has posted none, so the
        # answer travels with the call and the write is all that is left.
        self._transact(generation=self.generation)

        self.assertEqual(self.github.marker_scans, [])
        self.assertEqual(self.published_pr.state, STATE_CLOSED)

    def test_it_records_the_obligation_settled(self) -> None:
        # The ledger is what holds the umbrella's terminal open until the
        # remote has let go, so a supersession that landed has to say so.
        self._transact(generation=self.generation)

        self.assertIn(
            [RESOURCE_PLAN_PR, str(PUBLISHED_PR_NUMBER), STATE_RECONCILED],
            [
                [entry["kind"], entry["target"], entry["state"]]
                for entry in self._pinned().get(KEY_RESOURCES) or []
            ],
        )

    def test_it_hands_the_issue_on_behind_the_close(self) -> None:
        # And the tail runs only once the pull request is settled: the label,
        # the cleared pointer, and the children.
        self._transact(generation=self.generation)

        self.assertEqual(
            label_of(self.github, LATE_ISSUE_NUMBER), WorkflowLabel.UMBRELLA,
        )
        self.assertIsNone(self._pinned().get(KEY_PR_NUMBER))


class PublishedSupersessionRefusalTest(
    PublishedSplitCase, unittest.TestCase,
):
    """Every reading that says this is not the publication that was judged."""

    def test_a_moved_publication_parks(self) -> None:
        # Somebody pushed to it while the adjudication was open, so the change
        # this verdict was about is not the change closing it would close.
        self.published_pr.head.sha = MOVED_PUBLISHED_HEAD

        with self.assertLogs(level=ERROR):
            outcome = self._transact(generation=self.generation)

        self._assert_left_alone(outcome)

    def test_a_settled_publication_parks(self) -> None:
        # A human merged or closed it themselves. Letting the children loose
        # beside a merge would hand the work to N issues after it landed.
        for merged in (True, False):
            with self.subTest(merged=merged):
                self.setUp()
                self.published_pr.merged = merged
                self.published_pr.state = STATE_CLOSED

                with self.assertLogs(level=ERROR):
                    outcome = self._transact(generation=self.generation)

                self.assertEqual(outcome.disposition, _LateDisposition.PARKED)
                self.assertEqual(self.published_pr.merged, merged)

    def test_an_unreadable_publication_parks(self) -> None:
        # A fetched pull request is lazy, so the request that fails is as
        # likely to be the read as the write behind it -- and by then the
        # children are already live.
        with refusing(self.github, GET_PR), self.assertLogs(level=ERROR):
            outcome = self._transact(generation=self.generation)

        self._assert_left_alone(outcome)

    def test_a_release_that_fails_leaves_it_open(self) -> None:
        # The preserved description is not back where it belongs, so the
        # close waits: settling the entry over a hold nothing could take off
        # is what the order between the two exists to prevent.
        held = self.held_publication()

        with refusing(self.github, EDIT_PR_BODY), self.assertLogs(level=ERROR):
            outcome = self._transact(generation=held)

        self._assert_left_alone(outcome)
        self.assertEqual(self.published_pr.body, _late_hold._hold_body(held))

    def test_a_refused_supersession_parks(self) -> None:
        # The proof passed and the close itself did not land.
        self.github.unsupersedable_prs.add(PUBLISHED_PR_NUMBER)

        outcome = self._transact(generation=self.generation)

        self._assert_left_alone(outcome)

    def test_the_retry_supersedes_it(self) -> None:
        # The children are durable by then, so the retry is a read and a
        # close: the same recorded verdict settles once the disagreement is
        # reconciled, and the thread carries one notice.
        self.github.unsupersedable_prs.add(PUBLISHED_PR_NUMBER)
        self._transact(generation=self.generation)
        self.github.unsupersedable_prs.clear()

        self._resume()

        self.assertEqual(self.published_pr.state, STATE_CLOSED)
        self.assertEqual(
            len([
                body for _, body in self.github.posted_pr_comments
                if SUPERSESSION_MARKER in body
            ]),
            1,
        )
        self.assertEqual(len(self.github.created_child_issues), len(CHILDREN))

    def _assert_left_alone(self, outcome) -> None:
        """Parked with the publication open and no child let loose."""
        self.assertEqual(outcome.disposition, _LateDisposition.PARKED)
        self.assertEqual(
            self._pinned().get(KEYS.park_reason),
            _late_park_state.PARK_SUPERSESSION_FAILED,
        )
        self.assertEqual(
            label_of(self.github, LATE_ISSUE_NUMBER),
            WorkflowLabel.DECOMPOSING,
        )
        self.assertEqual(
            first_child(self.github).labels[0].name, WorkflowLabel.BLOCKED,
        )
        self.assertEqual(self._pinned().get(KEY_PR_NUMBER), PUBLISHED_PR_NUMBER)


class PublishedSupersessionRetryTest(PublishedSplitCase, unittest.TestCase):
    """The window the retirement behind the supersession leaves open.

    The close is not the last step: the label, the cleared pointer, the
    children, and the branch all come after it. A tick that died in between
    comes back to a pull request it closed ITSELF, which reads exactly as a
    human's settlement does -- and the receipt on the thread is the only thing
    that tells the two apart.

    What the receipt buys is the STATE and nothing else. The branch is live
    for the whole of that window, so the head is proved on this path exactly
    as on the open one.
    """

    def test_a_death_past_the_close_resumes(self) -> None:
        # The window the supersession opens on this road: the pull request is
        # closed and its obligation reconciled, and the retirement behind them
        # never ran -- so the record is still live and the next tick reads a
        # publication it closed ITSELF. Told from a human's settlement only by
        # the receipt on the thread, and read as one it parks for good with
        # the children blocked behind a supersession already made.
        self._crash_past_the_close()
        self.assertEqual(self.published_pr.state, STATE_CLOSED)

        resumed = self._resume()

        self.assertEqual(resumed.disposition, _LateDisposition.SETTLED)
        self.assertEqual(
            label_of(self.github, LATE_ISSUE_NUMBER), WorkflowLabel.UMBRELLA,
        )
        self.assertNotEqual(
            first_child(self.github).labels[0].name, WorkflowLabel.BLOCKED,
        )
        # And it finishes as a READ: the notice is already on the thread and
        # the pull request is already closed, so it adds neither.
        self.assertEqual(
            len([
                body for _, body in self.github.posted_pr_comments
                if SUPERSESSION_MARKER in body
            ]),
            1,
        )

    def test_a_merged_publication_parks_past_it(self) -> None:
        # The receipt is not a licence. A human who reopened the pull request
        # and landed the work decided the opposite of what the supersession
        # claims, and handing it to children afterwards is the one outcome
        # nothing takes back.
        self._crash_past_the_close()
        self.published_pr.merged = True

        with self.assertLogs(level=ERROR):
            resumed = self._resume()

        self.assertEqual(resumed.disposition, _LateDisposition.PARKED)
        self.assertEqual(
            label_of(self.github, LATE_ISSUE_NUMBER),
            WorkflowLabel.DECOMPOSING,
        )

    def test_a_push_past_the_close_parks(self) -> None:
        # The receipt is not a licence one field over either. It says the
        # close was made and nothing about the branch behind it standing
        # still: a close does not freeze a ref, so somebody can push between
        # the crash and the retry. Waved through on the receipt alone, the
        # retry would settle the split, activate the children, and RECLAIM
        # that branch -- deleting a commit the snapshot, taken at the frozen
        # head, does not hold.
        self._crash_past_the_close()
        self.published_pr.head.sha = MOVED_PUBLISHED_HEAD

        with self.assertLogs(level=ERROR):
            resumed = self._resume()

        self.assertEqual(resumed.disposition, _LateDisposition.PARKED)
        self.assertEqual(
            label_of(self.github, LATE_ISSUE_NUMBER),
            WorkflowLabel.DECOMPOSING,
        )
        self.assertEqual(
            first_child(self.github).labels[0].name, WorkflowLabel.BLOCKED,
        )
        self.assertEqual(self.github.deleted_remote_branches, [])
        self.assertFalse(self.teardown.attempted)

    def test_the_park_names_the_push_not_a_write(self) -> None:
        # The supersession did not fail here -- this transaction made it --
        # so the notice that says "could not be superseded" would send the
        # human looking for a write that never went wrong. What they have to
        # reconcile is the head.
        self._crash_past_the_close()
        self.published_pr.head.sha = MOVED_PUBLISHED_HEAD

        with self.assertLogs(level=ERROR):
            self._resume()

        parked = self.github.posted_comments[-1][1]
        self.assertEqual(
            self._pinned().get(KEYS.park_reason),
            _late_park_state.PARK_SUPERSESSION_FAILED,
        )
        self.assertIn(MOVED_PUBLISHED_HEAD, parked)
        self.assertNotIn("could not be superseded", parked)

    def _crash_past_the_close(self) -> None:
        """The window itself: the close lands and the retirement never runs."""
        with self.assertRaises(KeyboardInterrupt):
            self._transact(
                generation=self.generation,
                killed=killed_after(_late_transaction, SUPERSEDED),
            )


class PublishedSupersessionRaceTest(PublishedSplitCase, unittest.TestCase):
    """A human moving the publication INSIDE the pass that is closing it.

    The third window and the only one no ordering closes. The refusals above
    are readings taken before a pass and the retries beside them are readings
    taken after a crash; here the process lives, every step reports back, and
    what goes stale is a proof taken one round-trip ago. A supersession is one
    of those round-trips and the retirement behind it is another, so a merge,
    a push, or a reopen lands between two steps that both succeed.

    What stops it is a reading taken again in front of every effect it
    licenses -- the close, the retirement, the release of the children, and
    the delete of the branch -- so no step is ever run on evidence a step
    before it took. What a refusal then costs depends on which side of the
    retirement it lands: before it the pass parks with the record still live,
    and past it there is no record left to park, so the step is declined and
    left to the retry that owns it.
    """

    def test_a_settlement_at_the_close_is_untouched(self) -> None:
        # The proof is taken, and before the close is made a human merges the
        # change, closes it, or somebody pushes to the branch behind it. The
        # confirming read is what catches all three, and catching them THERE
        # is what leaves the pull request untouched: marking and closing a
        # change nobody adjudicated and refusing to finish afterwards would
        # settle nothing and take a human's change away.
        moves = (
            ("merged", self.merged),
            ("closed", self.closed),
            ("pushed", self.pushed),
        )
        for described, moved in moves:
            with self.subTest(moved=described):
                self.setUp()

                self._assert_held_back(self._moved_inside_the_close(moved))

                self.assertEqual(self.github.posted_pr_comments, [])
                self.assertEqual(
                    self._pinned().get(KEY_PR_NUMBER), PUBLISHED_PR_NUMBER,
                )

    def test_a_pushed_publication_is_never_closed(self) -> None:
        # The sharpest of the three, because a merge and a close both leave a
        # settled change either way: here the pull request is still open and
        # this pass is the only thing that would have closed it.
        self._moved_inside_the_close(self.pushed)

        self.assertEqual(self.published_pr.state, STATE_OPEN)

    def test_a_reopen_before_the_retirement_parks(self) -> None:
        # The close landed and a human reopened it in the window the
        # retirement stands in. Waved through, this pass would clear the
        # pointer, let the children loose, and delete the branch behind a
        # pull request that is open and carrying the superseded work.
        with interleaved_after(_late_transaction, SUPERSEDED, self.reopened), self.assertLogs(level=ERROR):
            outcome = self._transact(generation=self.generation)

        self._assert_held_back(outcome)
        self.assertEqual(self.published_pr.state, STATE_OPEN)
        # And the obligation is owed again, so the next tick supersedes the
        # same pull request rather than reading the entry an earlier step
        # wrote and stepping over it.
        self.assertIn(
            [RESOURCE_PLAN_PR, str(PUBLISHED_PR_NUMBER), STATE_FAILED],
            [
                [entry["kind"], entry["target"], entry["state"]]
                for entry in self._pinned().get(KEY_RESOURCES) or []
            ],
        )

    def _moved_inside_the_close(self, moved):
        """One pass with the world moving between the proof and the close."""
        with interleaved_after(_late_transaction, PROVED, moved), self.assertLogs(level=ERROR):
            return self._transact(generation=self.generation)

    def _assert_held_back(self, outcome) -> None:
        """Parked with nothing past the supersession allowed to happen."""
        self.assertEqual(outcome.disposition, _LateDisposition.PARKED)
        self.assertEqual(
            self._pinned().get(KEYS.park_reason),
            _late_park_state.PARK_SUPERSESSION_FAILED,
        )
        self.assertEqual(
            label_of(self.github, LATE_ISSUE_NUMBER),
            WorkflowLabel.DECOMPOSING,
        )
        self.assertEqual(
            first_child(self.github).labels[0].name, WorkflowLabel.BLOCKED,
        )
        self.assertEqual(self.github.deleted_remote_branches, [])
        self.assertFalse(self.teardown.attempted)


class PublishedRetirementRaceTest(PublishedSplitCase, unittest.TestCase):
    """A reopen landing PAST the retirement, where no record is left to park.

    The write that hands the issue to `umbrella` drops the generation, so the
    barriers behind it have nothing to park and no label to hold. What they
    have instead is the step in front of them, and declining that is the whole
    of what they can do: the children are left for the umbrella's own walk and
    the branch for its terminal, both of which are retries that already exist
    and both of which take their own reading.

    Which makes the placement the point. The barrier before the retirement is
    the last thing to run before that write, so what is left to these two is
    the window the write itself opens -- and a reopen inside it costs a label
    that lands, not a child that runs or a branch that goes.
    """

    def test_a_reopen_past_the_barrier_holds_children(self) -> None:
        # The barrier in front of the retirement clears and the pull request
        # is reopened inside the write behind it -- the one window this road
        # cannot close. The label lands, because that write is what the window
        # IS. Nothing after it does: the children stay blocked for the
        # umbrella's own walk, and the branch stays on the ledger.
        with interleaved_after(_late_transaction, HOLDS, self.reopened), self.assertLogs(level=ERROR):
            outcome = self._transact(generation=self.generation)

        self.assertEqual(outcome.disposition, _LateDisposition.SETTLED)
        self.assertEqual(
            label_of(self.github, LATE_ISSUE_NUMBER), WorkflowLabel.UMBRELLA,
        )
        self.assertEqual(
            first_child(self.github).labels[0].name, WorkflowLabel.BLOCKED,
        )
        self._assert_branch_kept()

    def test_a_reopen_in_the_child_scan_holds_them(self) -> None:
        # The scan the release is decided on is a request per child, so a
        # barrier in front of it is one the walk behind it has already
        # outlived. What answers for each relabel is the reading taken
        # immediately before that relabel, which is the walk's own.
        with interleaved_after(_parents, CHILD_SCAN, self.reopened), self.assertLogs(level=ERROR):
            self._transact(generation=self.generation)

        self.assertEqual(
            first_child(self.github).labels[0].name, WorkflowLabel.BLOCKED,
        )
        self.assertEqual(self.published_pr.state, STATE_OPEN)
        self._assert_branch_kept()

    def test_a_reopen_past_activation_keeps_branch(self) -> None:
        # And the last barrier of all, which is the furthest from the proof
        # that licensed it: a pinned write, a label write, an owner read, a
        # child scan, and one relabel per child stand in between. Deleting the
        # ref behind a change somebody reopened is the one act here no later
        # pass could undo, so the branch stays even though the children ran.
        with interleaved_after(_late_retirement, ACTIVATED, self.reopened), self.assertLogs(level=ERROR):
            self._transact(generation=self.generation)

        self.assertNotEqual(
            first_child(self.github).labels[0].name, WorkflowLabel.BLOCKED,
        )
        self._assert_branch_kept()

    def _assert_branch_kept(self) -> None:
        """The branch untouched on every surface, and still owed on record.

        Owed rather than failed: no delete was attempted, so what comes back
        for it is the umbrella's terminal rather than a typed failure.
        """
        self.assertEqual(self.github.deleted_remote_branches, [])
        self.assertFalse(self.teardown.attempted)
        self.assertEqual(
            [
                entry["state"]
                for entry in self._pinned().get(KEY_RESOURCES) or []
                if entry["kind"] == RESOURCE_BRANCH
            ],
            [STATE_PENDING],
        )


if __name__ == "__main__":
    unittest.main()
