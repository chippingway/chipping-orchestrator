# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The record one auto-rebase attempt leaves, and the three answers it gives."""

from __future__ import annotations

import unittest
from types import MappingProxyType
from unittest.mock import MagicMock, patch

from orchestrator.git.base_sync import attempt_records as _attempt_records, attempts, startup
from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.state import WorkflowLabel
from tests.git.base_sync import base_sync_helpers as fixtures
from tests.git.base_sync.refresh_scenarios import (
    PUSH_PATCH,
    REBASE_PATCH,
    _scenario,
)
from tests.git.base_sync.refresh_test_support import (
    AFTER_SHA,
    BEFORE_SHA,
    ISSUE,
    LABEL_IN_REVIEW,
    PR_NUMBER,
    THREE_BEHIND_STDOUT,
    _git_result,
    _SyncWorktreeWithBaseFixture,
)

KEY_ANCHOR = "pending_auto_base_rebase_push_sha"

KEY_REWRITE_SHA = "pending_auto_base_rebase_rewrite_sha"

KEY_REWRITE_PR = "pending_auto_base_rebase_rewrite_pr"

KEY_REWRITE_STAGE = "pending_auto_base_rebase_rewrite_stage"

KEY_ANNOUNCED_SHA = "pending_auto_base_rebase_announced_sha"

# The publication one attempt is made for. `in_review` is a stage that pushes
# onto a pull request the remote already carries, which is the only kind this
# record may name.
ATTEMPT_PR = fixtures.PR_NUMBER

ATTEMPT_STAGE = WorkflowLabel.IN_REVIEW

# A commit id at the length every recorded head here is read at, and the two
# values that are not one: an abbreviation names a commit no comparison could
# make, and a word is not hex at all.
REPLAYED_SHA = "5ca1ab1e" * 5

ABBREVIATED_SHA = REPLAYED_SHA[:8]

NOT_A_SHA = "the-head-it-left"

# A stage no publication is entered from. The rebase it would describe is one
# this workflow never makes, so a record naming it is not an attempt.
UNPUBLISHED_STAGE = str(WorkflowLabel.IMPLEMENTING)

DIRTY_PATCH = "dirty"

# The client call the refresh's own finish makes between its announcement and
# its last write, read here for the comment standing at that moment.
SET_LABEL = "set_workflow_label"

RELABEL_SEAM = "relabel"

# What each patched git seam answers once it has read the comment: a rebase
# that left no conflicts, and a worktree with nothing uncommitted in it. The
# relabel is not here -- it is read through rather than replaced, so the route
# it makes and the event it files stay part of the flow under test.
_SEAM_ANSWERS = MappingProxyType({REBASE_PATCH: (True, []), DIRTY_PATCH: []})


# The whole record after each of the three writes that make it, spelled at
# every step rather than as a delta: what a writer may not do is disturb a
# member it is not the one answering for, and only the whole group says so.
_ANCHOR_AND_TERMS = MappingProxyType({
    KEY_ANCHOR: BEFORE_SHA,
    KEY_REWRITE_PR: PR_NUMBER,
    KEY_REWRITE_STAGE: LABEL_IN_REVIEW,
})

_WITH_THE_REPLAY = MappingProxyType({
    **_ANCHOR_AND_TERMS, KEY_REWRITE_SHA: REPLAYED_SHA,
})

_WITH_THE_MARK = MappingProxyType({
    **_WITH_THE_REPLAY, KEY_ANNOUNCED_SHA: REPLAYED_SHA,
})

# Those writes in the order the flow makes them, each beside the moment it is
# the first one able to answer for its member.
_WRITERS = (
    (
        "the anchor and the terms, before git runs",
        lambda context: startup._record_auto_rebase_attempt(
            context, BEFORE_SHA, None,
        ),
        _ANCHOR_AND_TERMS,
    ),
    (
        "the head the replay produced",
        lambda context: attempts._records_the_replay(context, REPLAYED_SHA),
        _WITH_THE_REPLAY,
    ),
    (
        "the mark a finish leaves before it routes",
        lambda context: attempts._announces(context, REPLAYED_SHA),
        _WITH_THE_MARK,
    ),
)


def _recorded(**overrides) -> PinnedState:
    """The comment a whole attempt leaves, with any member replaced.

    A member given as None is taken OUT of the payload rather than nulled, so
    a case about a group something edited is seeded with the edit it means
    rather than with the blank the clear writes.
    """
    written = {
        KEY_ANCHOR: BEFORE_SHA,
        KEY_REWRITE_SHA: REPLAYED_SHA,
        KEY_REWRITE_PR: ATTEMPT_PR,
        KEY_REWRITE_STAGE: str(ATTEMPT_STAGE),
        **overrides,
    }
    return PinnedState(data={
        key: recorded for key, recorded in written.items()
        if recorded is not None
    })


class PendingRewriteReadTest(unittest.TestCase):
    """The three answers a comment carrying this record can give.

    A whole one that vouches for its own replay, one nobody ever wrote, and
    the window between the two writes that make it -- kept apart here because
    collapsing any two of them is what would let a state nobody can vouch for
    take a road reserved for one that can.
    """

    def test_a_whole_record_vouches_for_its_replay(self) -> None:
        pending = _attempt_records._pending_rewrite(_recorded())

        self.assertTrue(pending.is_declared)
        self.assertTrue(pending.is_recorded)
        self.assertTrue(pending.left_a_replay)
        self.assertFalse(pending.damaged)
        self.assertEqual(pending.sha, REPLAYED_SHA)
        self.assertTrue(pending.names(REPLAYED_SHA))
        self.assertTrue(pending.answers_for(ATTEMPT_PR, ATTEMPT_STAGE))

    def test_it_vouches_for_nothing_else(self) -> None:
        # Everything a record has to refuse for the roads above it to be safe:
        # a checkout standing somewhere else, a checkout that cannot name its
        # own head, a pull request the issue was repointed to, and the relabel
        # a crash left behind. Each would attribute an attempt's work to a
        # publication it was never made for.
        pending = _attempt_records._pending_rewrite(_recorded())

        self.assertFalse(pending.names(AFTER_SHA))
        self.assertFalse(pending.names(""))
        self.assertFalse(pending.answers_for(ATTEMPT_PR + 1, ATTEMPT_STAGE))
        self.assertFalse(
            pending.answers_for(ATTEMPT_PR, WorkflowLabel.VALIDATING),
        )
        self.assertFalse(pending.answers_for(ATTEMPT_PR, None))

    def test_a_comment_with_no_member_claims_nothing(self) -> None:
        pending = _attempt_records._pending_rewrite(PinnedState(data={}))

        self.assertFalse(pending.is_declared)
        self.assertFalse(pending.is_recorded)
        self.assertFalse(pending.left_a_replay)
        self.assertFalse(pending.damaged)

    def test_a_blanked_group_is_nobodys_record(self) -> None:
        # The write that ends an attempt blanks these fields rather than
        # removing them, so a group of nulls has to read exactly as a comment
        # that never carried one -- otherwise every issue the refresh has
        # finished once would claim a damaged attempt forever.
        state = _recorded()
        attempts._clears_the_attempt(state)

        pending = _attempt_records._pending_rewrite(state)

        self.assertFalse(pending.damaged)
        self.assertFalse(pending.left_a_replay)

    def test_the_terms_alone_date_the_attempt(self) -> None:
        # The terms go down before git runs and the head after it, so a
        # comment carrying one and not the other is not a group short of a
        # member: it is an attempt whose branch may be standing on a replay
        # nothing here can name.
        pending = _attempt_records._pending_rewrite(_recorded(**{
            KEY_REWRITE_SHA: None,
        }))

        self.assertTrue(pending.is_declared)
        self.assertFalse(pending.is_recorded)
        self.assertFalse(pending.left_a_replay)
        self.assertFalse(pending.damaged)
        self.assertEqual(pending.pr_number, ATTEMPT_PR)
        self.assertEqual(pending.stage, ATTEMPT_STAGE)


class DamagedAttemptTest(unittest.TestCase):
    """A comment that claims the record and cannot show it is not read."""

    def test_every_unreadable_member_is_damage(self) -> None:
        # Read as absent, a strictly-ahead checkout would be measured and
        # force-pushed on the strength of a claim nothing could check; read
        # as in flight, the same. So each of these is its own answer.
        damaged = {
            "a head that is not a whole object id": {
                KEY_REWRITE_SHA: ABBREVIATED_SHA,
            },
            "a head that is not hex at all": {KEY_REWRITE_SHA: NOT_A_SHA},
            "terms missing under a head that is there": {
                KEY_REWRITE_PR: None, KEY_REWRITE_STAGE: None,
            },
            "a pull request that is not an identity": {
                KEY_REWRITE_PR: str(ATTEMPT_PR),
            },
            "a pull request no issue is numbered": {KEY_REWRITE_PR: 0},
            "a stage no publication is entered from": {
                KEY_REWRITE_STAGE: UNPUBLISHED_STAGE,
            },
            "a stage this build does not know": {
                KEY_REWRITE_STAGE: "workflow:renamed",
            },
        }
        for described, damage in damaged.items():
            with self.subTest(record=described):
                pending = _attempt_records._pending_rewrite(_recorded(**damage))

                self.assertTrue(pending.damaged)
                self.assertTrue(pending.left_a_replay)
                self.assertFalse(pending.is_declared)
                self.assertFalse(pending.is_recorded)
                self.assertFalse(pending.names(REPLAYED_SHA))

    def test_a_null_beside_a_value_is_a_claim(self) -> None:
        # A pinned comment is JSON, so a field can be PRESENT and null. Read
        # for a value rather than for the key, the minimal damaged group would
        # answer "no record at all" and let a road reserved for one nobody
        # wrote be taken over one something took apart.
        state = _recorded()
        state.set(KEY_REWRITE_PR, None)

        self.assertTrue(_attempt_records._pending_rewrite(state).damaged)


class AnnouncementMarkTest(unittest.TestCase):
    """The checkpoint a finish leaves between its notice and its relabel."""

    def test_this_heads_mark_says_it_was_announced(self) -> None:
        state = _recorded(**{KEY_ANNOUNCED_SHA: REPLAYED_SHA})

        self.assertTrue(attempts._already_announced(state, REPLAYED_SHA))
        self.assertFalse(attempts._foreign_mark(state, REPLAYED_SHA))

    def test_a_comment_with_no_mark_announces_nothing(self) -> None:
        state = _recorded()

        self.assertFalse(attempts._already_announced(state, REPLAYED_SHA))
        self.assertFalse(attempts._foreign_mark(state, REPLAYED_SHA))

    def test_a_foreign_mark_is_not_silence(self) -> None:
        # Read as "nothing was announced", such a mark costs the pull request
        # a second notice and the stream a second `base_rebased` for one
        # publication that happened once.
        foreign = {
            "a mark for some other commit": AFTER_SHA,
            "a mark that names no commit": NOT_A_SHA,
        }
        for described, recorded in foreign.items():
            with self.subTest(mark=described):
                state = _recorded(**{KEY_ANNOUNCED_SHA: recorded})

                self.assertFalse(
                    attempts._already_announced(state, REPLAYED_SHA),
                )
                self.assertTrue(attempts._foreign_mark(state, REPLAYED_SHA))

    def test_an_unreadable_head_announces_nothing(
        self,
    ) -> None:
        state = _recorded(**{KEY_ANNOUNCED_SHA: REPLAYED_SHA})

        self.assertFalse(attempts._already_announced(state, ""))
        self.assertTrue(attempts._foreign_mark(state, ""))


class ClearedAttemptTest(unittest.TestCase):
    """Ending an attempt takes the whole record and nothing beside it."""

    def test_the_clear_takes_every_member_at_once(self) -> None:
        state = _recorded(**{KEY_ANNOUNCED_SHA: REPLAYED_SHA})
        state.set("review_round", 3)

        attempts._clears_the_attempt(state)

        for key in attempts._ATTEMPT_KEYS:
            with self.subTest(key=key):
                self.assertIn(key, state.data)
                self.assertIsNone(state.get(key))
        self.assertEqual(state.get("review_round"), 3)

    def test_the_clear_is_staged_rather_than_written(self) -> None:
        # What makes the drop durable is the caller's own write, which is what
        # lets it land with the route, the park, or the receipt it belongs to
        # -- or not at all.
        context = fixtures._recovery_context(
            pending_auto_base_rebase_push_sha=fixtures.PRE_REBASE_SHA,
        )

        attempts._clears_the_attempt(context.state)

        self.assertEqual(
            context.gh.pinned_data(fixtures.ISSUE).get(KEY_ANCHOR),
            fixtures.PRE_REBASE_SHA,
        )


class AttemptWriteOrderTest(_SyncWorktreeWithBaseFixture, unittest.TestCase):
    """Each half of the record goes down in the moment it can first be known.

    The terms before `git rebase` is allowed to touch the branch, because read
    off the issue after a crash they would compare today with today. The head
    before the first step that can leave the replay standing, because the
    anchor alone cannot say that a divergent checkout is this attempt's work.
    Asked of one whole rebase, and again of each writer on its own, since the
    order is a fact about the flow and what each write CARRIES is a fact about
    the owner that makes it.
    """

    def test_the_terms_are_durable_before_git_runs(self) -> None:
        observed = self._run_rebase()

        self.assertEqual(observed[REBASE_PATCH].get(KEY_ANCHOR), BEFORE_SHA)
        self.assertEqual(observed[REBASE_PATCH].get(KEY_REWRITE_PR), PR_NUMBER)
        self.assertEqual(
            observed[REBASE_PATCH].get(KEY_REWRITE_STAGE), LABEL_IN_REVIEW,
        )
        self.assertIsNone(observed[REBASE_PATCH].get(KEY_REWRITE_SHA))

    def test_the_replay_is_durable_by_the_dirty_check(
        self,
    ) -> None:
        observed = self._run_rebase()

        self.assertEqual(observed[DIRTY_PATCH].get(KEY_REWRITE_SHA), AFTER_SHA)

    def test_a_finished_route_leaves_no_member(self) -> None:
        self._run_rebase()

        published = self.gh.pinned_data(ISSUE)
        for key in attempts._ATTEMPT_KEYS:
            with self.subTest(key=key):
                self.assertIsNone(published.get(key))

    def test_the_mark_is_durable_before_the_relabel(self) -> None:
        # The window this refresh's own finish leaves, and the only one that
        # is not a recovery's: the notice and the audit event are out, the
        # relabel has not happened, and a tick lost there has to come back to
        # a comment that says the announcement was made. Read as unfinished,
        # it would put a second `base_rebased` on the stream and a second
        # notice on the pull request for one publication that happened once.
        # The anchor and the replay stand beside it, since they are what
        # bring that tick back at all.
        observed = self._run_rebase()

        self.assertEqual(observed[RELABEL_SEAM].get(KEY_ANNOUNCED_SHA), AFTER_SHA)
        self.assertEqual(observed[RELABEL_SEAM].get(KEY_ANCHOR), BEFORE_SHA)
        self.assertEqual(observed[RELABEL_SEAM].get(KEY_REWRITE_SHA), AFTER_SHA)

    def test_each_write_carries_only_its_own_member(self) -> None:
        # Three writers, one record: each adds the member it can first answer
        # for and leaves every other field exactly where it stands, so a crash
        # under any of them loses only what had not happened yet.
        context = fixtures._sync_context()
        for described, write, standing in _WRITERS:
            with self.subTest(write=described):
                write(context)

                published = context.gh.pinned_data(fixtures.ISSUE)
                self.assertEqual(
                    {key: published.get(key) for key in attempts._ATTEMPT_KEYS},
                    {key: standing.get(key) for key in attempts._ATTEMPT_KEYS},
                )

    def _run_rebase(self) -> dict:
        """Run one clean rebase, reading the comment at three points in it."""
        self._seed_pr_issue()
        self._add_pr()
        observed: dict = {}
        self.enterContext(patch.object(
            self.gh,
            SET_LABEL,
            _SeamReader(
                self.gh, observed, RELABEL_SEAM,
                original=getattr(self.gh, SET_LABEL),
            ),
        ))
        _scenario(
            dirty=MagicMock(side_effect=self._observes(observed, DIRTY_PATCH)),
            **{
                REBASE_PATCH: MagicMock(
                    side_effect=self._observes(observed, REBASE_PATCH),
                ),
                PUSH_PATCH: MagicMock(return_value=True),
            },
            head_sha=MagicMock(side_effect=[BEFORE_SHA, AFTER_SHA]),
            git=MagicMock(return_value=_git_result(stdout=THREE_BEHIND_STDOUT)),
            hardened=MagicMock(return_value=_git_result()),
        ).run(self)
        return observed

    def _observes(self, observed: dict, seam: str) -> _SeamReader:
        """Record the pinned comment as the flow reaches one git seam."""
        return _SeamReader(self.gh, observed, seam)


class _SeamReader:
    """Read the pinned comment as one seam of the flow is reached.

    `original` is what a seam that is only being WATCHED runs afterwards, so
    the relabel this refresh makes still happens and the event it files still
    lands; a seam with none is a git call the scenario replaced outright and
    answers from the table above.
    """

    def __init__(self, gh, observed: dict, seam: str, original=None) -> None:
        self._gh = gh
        self._observed = observed
        self._seam = seam
        self._original = original

    def __call__(self, *args, **kwargs):
        self._observed[self._seam] = dict(self._gh.pinned_data(ISSUE))
        if self._original is None:
            return _SEAM_ANSWERS[self._seam]
        return self._original(*args, **kwargs)


if __name__ == "__main__":
    unittest.main()
