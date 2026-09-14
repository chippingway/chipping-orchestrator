# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The branch a split superseded, and the change that may come back for it.

The last irreversible act of a published split is the delete that takes its
branch away, and it happens on the umbrella's terminal -- ticks after the pass
that closed the pull request the branch belongs to. A human who reopens that
change has one pointing at a ref this delete would remove out from under them,
and nothing afterwards puts a branch back.

So the question is asked immediately in front of the delete, and not where the
pass assembles its work list. Between those two the snapshot rule may spend a
remote probe of its own, deciding whether an ordered ref the consumers no
longer clear is already gone -- and a probe is a request a human can reopen a
pull request inside. A retry with an owed branch and an ordered ref is exactly
the shape that has one, which is why these cases build one rather than seeding
a fresh umbrella.

And the terminal that closes the parent asks the same question twice more,
off the ledger rather than through it. A reclamation that FINISHED leaves
nothing owed, so an entry-driven guard sees a settled record and waves the
terminal through -- while a human who restored the branch and reopened the
change has left the one thing that still matters unfinished. What the terminal
writes is `done`, a close, and the drop of the publication group, after which
nothing would ever ask again.

Twice, because the settlement's own ask is not the boundary: the resolution
comment and the latches behind it are requests, and the reopen can land in
any of them. So it is asked once where refusing costs nothing -- before
anything is said -- and once immediately in front of the retirement write,
where refusing costs the sentence that has already gone out and the thread is
what stops that repeating.

That receipt belongs to this road and no other. It is scoped to the cycle and
generation, since an operator restarting a rejected one keeps the thread, and
it is stamped only where something behind the sentence could still refuse --
which is nothing on any umbrella but a published split's.
"""
from __future__ import annotations

import unittest
from dataclasses import replace

from orchestrator.git.snapshots import refs as _snapshot_refs
from orchestrator.workflow.stages.decomposition import umbrella as _umbrella, umbrella_terminal as _umbrella_terminal
from orchestrator.workflow.state import WorkflowLabel
from tests.support.fakes import FakeComment, FakeLabel, FakeUser
from tests.workflow.fixtures import _TEST_SPEC
from tests.workflow.stages.decomposition import late_race_support as _late_race, late_test_support as _late_support
from tests.workflow.stages.decomposition.late_published_split_support import (
    STATE_CLOSED,
    PublishedSplitCase,
)
from tests.workflow.stages.decomposition.late_seam_support import (
    RecordedDelete,
    SnapshotOutcome,
    local_teardown,
)
from tests.workflow.stages.decomposition.late_transaction_support import (
    ERROR,
    KEY_RESOURCES,
    LateSplitCase,
    SnapshotSeed,
    label_of,
)

LABEL_DONE = "done"

KEY_PUBLISHED_PR = "late_published_pr_number"

RESOURCE_BRANCH = "branch"

STATE_FAILED = "failed"

# The read-only ask the snapshot rule spends on an ordered ref the consumers
# no longer clear. It stands between the work list and the branch delete, so
# it is where a case puts the reopen.
SNAPSHOT_PROBE = "observed_snapshot_ref"

# The one request standing between the settlement's own ask and the retirement
# write: the sentence a resolved umbrella owes its thread.
RESOLUTION_SAID = "_resolution_said"

# What that sentence starts with, for a case counting how often it went out.
RESOLVED_NOTICE = "all children resolved"

# The cycle an operator restarted this issue out of. Its receipt is still on
# the thread, because a restart clears the label and not the conversation.
EARLIER_CYCLE = 2

# An id no comment this fixture writes takes, so a planted receipt cannot be
# mistaken for one the run itself posted.
PLANTED_COMMENT_ID = 9001

# The prefix every receipt of this kind starts with, for the umbrella that
# must carry none.
RECEIPT_PREFIX = "<!--orchestrator-umbrella-resolved"


class ReopenedDuringCleanupTest(PublishedSplitCase, unittest.TestCase):
    """A retry whose branch delete is licensed by a stale reading, or not.

    Built rather than seeded: the state that has a probe in it -- an owed
    branch beside a snapshot entry an earlier delete already ordered -- is
    what a real cleanup RETRY looks like, and only a run that actually failed
    once leaves it.
    """

    def test_a_reopen_in_the_probe_keeps_the_branch(self) -> None:
        # The work list said the branch could go, the probe went out, and the
        # change came back inside it. Licensed by the earlier answer, this
        # tick would delete the ref that change points at and record the
        # obligation settled.
        self._refused_once()
        self._reopen_one_child()
        deleted = list(self.github.deleted_remote_branches)

        with self.assertLogs(level=ERROR):
            probed = self._retried(moved=self.reopened)

        # The window this is about has to have been open: a retry that spent
        # no probe would pass here while proving nothing.
        self.assertTrue(probed.observed)
        self.assertEqual(self.github.deleted_remote_branches, deleted)
        self.assertEqual(self._branch_states(), [STATE_FAILED])
        self.assertEqual(
            label_of(self.github, _late_support.LATE_ISSUE_NUMBER), WorkflowLabel.UMBRELLA,
        )

    def test_the_same_retry_reclaims_it_untouched(self) -> None:
        # And the floor under that: with nobody moving the pull request, the
        # very same retry deletes the branch and settles the entry. Without
        # this the case above would pass on a cleanup that never works.
        self._refused_once()
        self._reopen_one_child()
        deleted = len(self.github.deleted_remote_branches)

        self._retried()

        self.assertEqual(
            len(self.github.deleted_remote_branches), deleted + 1,
        )
        self.assertEqual(self._branch_states(), ["reconciled"])

    def _refused_once(self) -> None:
        """A split whose branch and ref both survived their first attempt.

        The local teardown will not finish, so the branch stays owed however
        the remote answers; the ref delete is refused outright, which is what
        leaves an ORDERED entry for the retry to find.
        """
        self._transact(
            generation=self.generation,
            snapshot=SnapshotSeed(local_gone=False),
        )
        for child in self.github.created_child_issues:
            child.labels = [FakeLabel(LABEL_DONE)]
            child.closed = True
        refused = RecordedDelete(SnapshotOutcome.UNREADABLE)
        with refused.answering(), local_teardown(local_gone=False):
            _umbrella._handle_umbrella(self.github, _TEST_SPEC, self.issue)

    def _reopen_one_child(self) -> None:
        """One consumer live again, so the ref is asked about rather than cut.

        Which is what puts the probe on this road: a ref whose consumers are
        no longer unanimous qualifies only through the recorded decision, and
        that qualification is a read-only ask of the remote.
        """
        self.github.created_child_issues[0].closed = False

    def _retried(self, *, moved=None) -> RecordedDelete:
        """One more umbrella tick, with a human moving things or not."""
        remote = RecordedDelete(SnapshotOutcome.DELETED)
        with remote.answering(), local_teardown(), _late_race.interleaved_after(
            _snapshot_refs, SNAPSHOT_PROBE, moved or _nothing,
        ):
            _umbrella._handle_umbrella(
                self.github, _TEST_SPEC, self.issue,
            )
        return remote

    def _branch_states(self) -> list:
        """What this issue's branch obligations were left reading."""
        return [
            entry["state"] for entry in self._pinned().get(KEY_RESOURCES) or []
            if entry["kind"] == RESOURCE_BRANCH
        ]


class _ResolvedUmbrellaCase(PublishedSplitCase):
    """A published split whose cleanup finished and whose children are done.

    Which is the shape the terminal decides on, and the one no ledger has
    anything left to say about: every entry is `reconciled`, so what stands
    between this parent and `done` is the pull request alone.
    """

    def _settled_and_resolved(self) -> None:
        """A split whose cleanup finished and whose children are all done."""
        self._transact(generation=self.generation)
        for child in self.github.created_child_issues:
            child.labels = [FakeLabel(LABEL_DONE)]
            child.closed = True

    def _terminal_tick(self, *, moved=None) -> None:
        """One umbrella poll over a parent whose children have all resolved.

        `moved` is a human reaching the pull request inside the one request
        that stands between the settlement's ask and the retirement write.
        """
        remote = RecordedDelete(SnapshotOutcome.DELETED)
        with remote.answering(), local_teardown(), _late_race.interleaved_after(
            _umbrella_terminal, RESOLUTION_SAID, moved or _nothing,
        ):
            _umbrella._handle_umbrella(
                self.github, _TEST_SPEC, self.issue,
            )

    def _parent_comments(self) -> list:
        """What this tick said on the PARENT, receipts to children aside."""
        return [
            body for number, body in self.github.posted_comments
            if number == _late_support.LATE_ISSUE_NUMBER
        ]

    def _notices(self) -> int:
        """How many times this umbrella said its children all resolved."""
        return len([
            body for body in self._parent_comments()
            if RESOLVED_NOTICE in body
        ])


class RestoredAfterCleanupTest(_ResolvedUmbrellaCase, unittest.TestCase):
    """A change reopened once every obligation was already settled.

    The window a ledger cannot describe: the branch really was reclaimed and
    the ref really was let go, so nothing is owed and the terminal is free --
    and the pull request the split closed is open again with the superseded
    work on it. Closing over that would hand a human a `done` parent, a live
    change nobody will finish, and no record left saying the two were related.
    """

    def test_the_terminal_waits_on_a_reopen(self) -> None:
        self._settled_and_resolved()
        self.reopened()

        self._terminal_tick()

        self.assertEqual(
            label_of(self.github, _late_support.LATE_ISSUE_NUMBER), WorkflowLabel.UMBRELLA,
        )
        self.assertFalse(self.issue.closed)
        # And the record still names the pull request, which is the only
        # reason the tick after this one can ask the same question.
        self.assertEqual(
            self._pinned().get(KEY_PUBLISHED_PR), self.published_pr.number,
        )

    def test_it_says_nothing_until_it_may_close(self) -> None:
        # The resolution comment is gated on a stamp only the retirement write
        # puts down, so a refusal taken past it would repeat that comment on
        # every tick that holds.
        self._settled_and_resolved()
        self.reopened()

        said = self._parent_comments()
        self._terminal_tick()
        self._terminal_tick()

        self.assertEqual(self._parent_comments(), said)

    def test_a_settled_change_still_closes_it(self) -> None:
        # The floor under both: with nobody touching the pull request the very
        # same terminal resolves the umbrella and closes it.
        self._settled_and_resolved()

        self._terminal_tick()

        self.assertEqual(
            label_of(self.github, _late_support.LATE_ISSUE_NUMBER), WorkflowLabel.DONE,
        )
        self.assertTrue(self.issue.closed)

class ReopenedInsideTheNoticeTest(_ResolvedUmbrellaCase, unittest.TestCase):
    """A change reopened inside the sentence the terminal owes its thread.

    The window the settlement's own ask cannot cover: it refuses before
    anything is said, and the saying is a request. Waved through, this pass
    goes on to drop the publication group, hand the parent `done`, and close
    it -- over a pull request that is open with the superseded work on it and
    with nothing left on the issue that could ever say so.
    """

    def test_a_reopen_in_the_notice_holds_it(self) -> None:
        self._settled_and_resolved()

        with self.assertLogs(level=ERROR):
            self._terminal_tick(moved=self.reopened)

        self.assertEqual(
            label_of(self.github, _late_support.LATE_ISSUE_NUMBER), WorkflowLabel.UMBRELLA,
        )
        self.assertFalse(self.issue.closed)
        # Nothing was written, so the next tick refuses where it costs
        # nothing: the group is exactly as this pass found it.
        self.assertEqual(
            self._pinned().get(KEY_PUBLISHED_PR), self.published_pr.number,
        )

    def test_an_earlier_cycle_receipt_is_not_this_one(self) -> None:
        # A rejected cycle's terminal can have said this before an operator
        # restarted the issue, and the restart keeps the thread. A receipt
        # scoped to the issue alone would silence the sentence the cycle after
        # it owes the humans reading that thread.
        self._settled_and_resolved()
        # Planted through the production builder, so what is on the thread is
        # exactly what THAT cycle's terminal would have left there.
        earlier = _umbrella_terminal._resolved_marker(
            self.issue, replace(self.generation, cycle_id=EARLIER_CYCLE),
        )
        self.issue.comments.append(FakeComment(
            id=PLANTED_COMMENT_ID,
            body=f"an earlier cycle resolved\n\n{earlier}",
            user=FakeUser(self.github._bot_login),
        ))

        self._terminal_tick()

        self.assertEqual(self._notices(), 1)
        self.assertEqual(
            label_of(self.github, _late_support.LATE_ISSUE_NUMBER), WorkflowLabel.DONE,
        )

    def test_the_notice_said_is_not_repeated(self) -> None:
        # The sentence went out and the write that records it did not, which
        # is a state only the thread can describe. Every tick that holds would
        # otherwise say it again, and so would the one that finally closes.
        self._settled_and_resolved()
        with self.assertLogs(level=ERROR):
            self._terminal_tick(moved=self.reopened)
        # A tick that refuses earlier, where the settlement holds it: it never
        # reaches the sentence at all.
        self._terminal_tick()
        self.published_pr.state = STATE_CLOSED

        self._terminal_tick()

        self.assertEqual(self._notices(), 1)
        self.assertEqual(
            label_of(self.github, _late_support.LATE_ISSUE_NUMBER), WorkflowLabel.DONE,
        )


class UnpublishedTerminalTest(LateSplitCase, unittest.TestCase):
    """An umbrella no publication stands behind, left exactly as it was.

    Every other umbrella -- the initial decomposer's, and a split entered
    before the first push -- has nothing that can refuse its terminal past the
    sentence it says, so the stamp is the whole of what stops a repeat. Giving
    them the thread gate too would spend a comment listing per completion and
    put a receipt on a thread nothing would ever read.
    """

    def test_its_notice_carries_no_receipt(self) -> None:
        self._transact()
        for child in self.github.created_child_issues:
            child.labels = [FakeLabel(LABEL_DONE)]
            child.closed = True
        remote = RecordedDelete(SnapshotOutcome.DELETED)

        with remote.answering(), local_teardown():
            _umbrella._handle_umbrella(self.github, _TEST_SPEC, self.issue)

        said = [
            body for number, body in self.github.posted_comments
            if number == _late_support.LATE_ISSUE_NUMBER and RESOLVED_NOTICE in body
        ]
        self.assertEqual(len(said), 1)
        self.assertNotIn(RECEIPT_PREFIX, said[0])
        self.assertEqual(
            label_of(self.github, _late_support.LATE_ISSUE_NUMBER), WorkflowLabel.DONE,
        )


def _nothing() -> None:
    """A world nobody touched, for the case that is about the floor."""


if __name__ == "__main__":
    unittest.main()
