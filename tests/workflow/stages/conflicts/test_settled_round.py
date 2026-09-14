# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The round a resolution earns when the size gate holds it off the PR.

A content update the gate sends to the adjudication is a round this stage
finished and could not publish: the commit is on the branch, a settled
`single` verdict publishes it from there, and the label comes back here with
the hand to `validating` still owed. What the resumed tick cannot work out for
itself is which of the four it was -- the branch it comes back to already
carries its base, which is the no-op flip's own reading and the one exit that
resolves nothing.

One pair holds one round, which is why nothing may start a fresh resume over a
receipt that is still standing: the second would write its outcome into the
slot the first is waiting in, and the round a settlement already published
would never be counted.
"""
from __future__ import annotations

import unittest
from unittest.mock import patch

from orchestrator.config import settings as config
from orchestrator.git.measurement.models import (
    FrozenCommit,
    MeasurementFailure,
)
from tests.workflow.patch_models import _agent
from tests.workflow.stages.conflicts.conflicts_test_support import (
    RESOLVED_HEAD_SHA,
    _ResolvingConflictMixin,
)

CONFLICT_ISSUE = 200
CONFLICT_FILE = "a.py"
BEFORE_HEAD = "be40e5ba" * 5
MERGED_HEAD = RESOLVED_HEAD_SHA

CEILING = 5
PAST_THE_CEILING = 6
MAX_ADDED_LINES = "MAX_ADDED_LINES"

# The flag a park sets, which every road out of one has to clear.
AWAITING_HUMAN = "awaiting_human"

RUN_AGENT = "run_agent"
PUSH_BRANCH = "_push_branch"

LABEL_DECOMPOSING = "workflow:decomposing"
LABEL_VALIDATING = "workflow:validating"

CONFLICT_ROUND = "conflict_round"
REVIEW_ROUND = "review_round"
RESOLVED_AT = "last_conflict_resolved_at"
SETTLED_OUTCOME = "conflict_settled_outcome"
SETTLED_SHA = "conflict_settled_sha"

AGENT_RESOLVED = "agent_resolved"
BASE_REBASED_CLEAN = "base_rebased_clean"
RECOVERED_PUSH = "recovered_push"
DRIFT_RESOLVED = "drift_resolved"

OUTCOME = "outcome"
SHA = "sha"

# The head an interrupted tick left on the branch and never pushed.
RECOVERED_HEAD = "1ec04e5e" * 5

# What `git rev-list --count HEAD..origin/<base>` answers for a branch that
# already carries its base, and for one that does not.
# A head somebody else's push left the pull request on, which a replacement
# host rebuilds its checkout from.
MOVED_HEAD = "0d0d0d0d" * 5

# The two spellings of a receipt no checkout can be compared to: a value
# nothing will type, and a round whose commit nobody could read.
NOT_A_COMMIT = "nope"
UNNAMED_HEAD = ""

# The head a body-edit resume commits, which is a round of its own and not the
# one a standing receipt is still owed for.
EDITED_HEAD = "ed17ed17" * 5

CANDIDATE_ABSENT = MeasurementFailure.CANDIDATE_ABSENT

ON_BASE = "0\n"
BEHIND_BASE = "2\n"
BASE_UP_TO_DATE = "base_up_to_date"


def _rounds_of(github) -> list[dict]:
    """Every `conflict_round` increment this run recorded."""
    return [
        event for event in github.recorded_events
        if event["event"] == CONFLICT_ROUND
    ]


def _outcomes_of(github) -> list[str]:
    """What each recorded round says put the branch where it is."""
    return [round_[OUTCOME] for round_ in _rounds_of(github)]


def _receipt_of(github) -> tuple:
    """The round a hold left for a later tick, as the pair it is written as."""
    pinned = github.pinned_data(CONFLICT_ISSUE)
    return (pinned.get(SETTLED_OUTCOME), pinned.get(SETTLED_SHA))


def _settlements_of(github) -> list[tuple]:
    """The same, with the head each round was recorded against."""
    return [(round_[OUTCOME], round_[SHA]) for round_ in _rounds_of(github)]


class ResolvingConflictHeldRoundTest(
    unittest.TestCase, _ResolvingConflictMixin,
):
    """What a resolution the size gate holds leaves on the pinned comment."""

    def test_a_held_resolution_names_its_round(self) -> None:
        # The hold ends the tick: the resolution is committed and the issue is
        # the adjudication's. The round is still resolved, so the pair that
        # names it goes down inside the gate's own write, ahead of the
        # relabel -- applied afterwards it would be lost to any crash in that
        # window, with nothing going back for it.
        github, mocks = self._held_agent_resolution()

        mocks[PUSH_BRANCH].assert_not_called()
        self.assertIn((CONFLICT_ISSUE, LABEL_DECOMPOSING), github.label_history)
        self.assertEqual(_receipt_of(github), (AGENT_RESOLVED, MERGED_HEAD))
        pinned = self._pinned(github)
        # Nothing is counted yet: the tail that counts is the one the resumed
        # tick runs, and counting here as well would spend the round twice.
        self.assertEqual(pinned.get(CONFLICT_ROUND), 0)
        self.assertNotIn(RESOLVED_AT, pinned)
        # And nothing is emitted either: a tail of the sink that saw a round
        # here would attribute one to a push that never went out.
        self.assertEqual(_rounds_of(github), [])

    def test_a_held_recovered_push_names_its_round(self) -> None:
        # The recovered push completes a round of its own when the branch it
        # publishes already carries base -- so a hold there owes the same
        # receipt an agent resolution does. Without it the resumed tick reads
        # a branch standing on its base and calls the round a no-op flip,
        # which resolves nothing and stamps no `last_conflict_resolved_at`.
        github, mocks = self._held_recovered_push()

        mocks[PUSH_BRANCH].assert_not_called()
        self.assertIn((CONFLICT_ISSUE, LABEL_DECOMPOSING), github.label_history)
        self.assertEqual(
            _receipt_of(github), (RECOVERED_PUSH, RECOVERED_HEAD),
        )

    def test_a_held_preamble_push_names_no_round(self) -> None:
        # A recovered push that leaves the branch still behind base is a
        # preamble rather than a round: the rebase behind it owns the
        # bookkeeping and leaves its own receipt. Recording one here too would
        # have the resumed tick close a round the rebase has not run yet.
        github = self._held_recovered_push(behind=BEHIND_BASE)[0]

        pinned = self._pinned(github)
        self.assertIsNone(pinned.get(SETTLED_OUTCOME))

    def _held_recovered_push(self, *, behind: str = ON_BASE):
        """One recovered push the gate measures past the ceiling."""
        return self._held(
            branch_ahead_behind=(1, 0),
            behind_base=behind,
            head_shas=[RECOVERED_HEAD, RECOVERED_HEAD],
            # The head this stage reads is the commit the gate proves the
            # checkout to: one read of one worktree, and the gate refuses a
            # checkout standing anywhere but on what its caller named.
            candidate_commit=FrozenCommit(sha=RECOVERED_HEAD),
            push_branch=True,
        )

    def _held_agent_resolution(self):
        """One agent resolution the gate measures past the ceiling."""
        return self._held(
            merge_succeeded=False,
            conflicted_files=[CONFLICT_FILE, "b.py"],
            head_shas=[BEFORE_HEAD, MERGED_HEAD],
            push_branch=True,
        )

    def _held(self, **run_options):
        """Seed one conflict issue and run a tick the gate holds."""
        github, issue = self._seed()[:2]
        with patch.object(config, MAX_ADDED_LINES, CEILING):
            return github, self._run_with_merge(
                github, issue,
                added_lines=PAST_THE_CEILING,
                **run_options,
            )[0]


class ResolvingConflictSettledRoundTest(
    unittest.TestCase, _ResolvingConflictMixin,
):
    """What the tick the settlement hands the label back to finishes."""

    def test_a_settled_round_is_finished_as_it_was(self) -> None:
        # The settlement publishes the accepted commit and hands the label
        # back. Re-derived instead of read, this round is the no-op flip: the
        # branch already carries its base, so the tick would emit
        # `base_up_to_date`, stamp no `last_conflict_resolved_at`, and tell a
        # tail of the sink that nothing was resolved.
        github = self._resumed(AGENT_RESOLVED)

        self.assertEqual(
            _settlements_of(github), [(AGENT_RESOLVED, MERGED_HEAD)],
        )
        self.assertIn(RESOLVED_AT, self._pinned(github))

    def test_a_settled_round_runs_no_agent(self) -> None:
        # Nothing is left to resolve or to push: what came back is a label
        # with the tail of a finished round still owed on it.
        github, mocks = self._resumed(AGENT_RESOLVED, reported=True)

        mocks[RUN_AGENT].assert_not_called()
        mocks[PUSH_BRANCH].assert_not_called()
        self.assertIn((CONFLICT_ISSUE, LABEL_VALIDATING), github.label_history)
        pinned = self._pinned(github)
        self.assertEqual(pinned.get(CONFLICT_ROUND), 1)
        self.assertEqual(pinned.get(REVIEW_ROUND), 0)
        # The receipt is paid, so a later tick finds nothing to finish twice.
        self.assertEqual(_receipt_of(github), (None, None))

    def test_a_settled_recovery_keeps_its_outcome(self) -> None:
        # End to end for the third seam: the recovered push is held, the
        # adjudication publishes the commit, and the label comes back here
        # over a branch already standing on its base. Re-derived, that reads
        # as the no-op flip -- `base_up_to_date`, no
        # `last_conflict_resolved_at`, and a tail of the sink told nothing was
        # resolved. Read off the receipt, the round the push earned is the
        # round that gets counted.
        github = self._resumed(RECOVERED_PUSH)

        self.assertEqual(
            _settlements_of(github), [(RECOVERED_PUSH, MERGED_HEAD)],
        )
        self.assertIn(RESOLVED_AT, self._pinned(github))

    def test_a_settled_rebase_keeps_its_outcome(self) -> None:
        # The other resolution the gate can hold, and the one the no-op flip
        # is easiest to mistake it for: both leave a branch carrying its base,
        # and only the record says which of them put it there.
        github = self._resumed(BASE_REBASED_CLEAN)

        self.assertEqual(_outcomes_of(github), [BASE_REBASED_CLEAN])

    def test_an_unpublished_round_waits(self) -> None:
        # The receipt alone cannot say the commit reached the remote: a
        # verdict that parked, or a human who moved the label by hand, leaves
        # the same pair over a commit still on disk. Ahead of the remote it
        # stands, and the recovered-commit push carries it through the gate,
        # which is the one road that measures it again.
        github, issue = self._settled(AGENT_RESOLVED)

        self._run_with_merge(
            github, issue,
            branch_ahead_behind=(2, 0),
            head_shas=[MERGED_HEAD, MERGED_HEAD],
            push_branch=True,
        )

        self.assertEqual(_outcomes_of(github), [RECOVERED_PUSH])
        self.assertIsNone(
            self._pinned(github).get(SETTLED_OUTCOME),
        )

    def _resumed(self, outcome: str, *, reported: bool = False):
        """Settle one held round, then run the tick it is handed back on."""
        github, issue = self._settled(outcome)
        mocks = self._run_with_merge(
            github, issue, head_shas=[MERGED_HEAD, MERGED_HEAD],
        )[0]
        return (github, mocks) if reported else github

    def _settled(self, outcome: str):
        """The pinned comment a held round and its adjudication left behind."""
        return self._seed(extra_state={
            SETTLED_OUTCOME: outcome,
            SETTLED_SHA: MERGED_HEAD,
        })[:2]


class ResolvingConflictSettledProofTest(
    unittest.TestCase, _ResolvingConflictMixin,
):
    """What a settled receipt is proved against before it is consumed.

    In sync with its remote is not the same claim as CARRYING the resolution
    the receipt names: a replacement host rebuilds the checkout from a pull
    request that has moved on, and what it gets is a branch level with its
    remote and standing on somebody else's head.
    """

    def test_a_moved_head_leaves_the_receipt(self) -> None:
        # In sync is not the same claim as carrying it. A replacement host
        # rebuilds the checkout from a pull request that has moved on, and
        # what it gets is a branch level with its remote and standing on
        # somebody else's head -- so the round would be reported over a
        # resolution this branch does not have.
        github, issue = self._settled(AGENT_RESOLVED)

        self._run_with_merge(
            github, issue,
            head_shas=[MOVED_HEAD, MOVED_HEAD],
            candidate_commit=FrozenCommit(sha=MOVED_HEAD),
        )

        self._assert_unclaimed(github)

    def test_an_unreadable_head_leaves_the_receipt(self) -> None:
        # A revision this host cannot peel is not a head anything may be
        # compared against, which is what a checkout the resolution never
        # reached answers with.
        github, issue = self._settled(AGENT_RESOLVED)

        self._run_with_merge(
            github, issue,
            head_shas=[MOVED_HEAD, MOVED_HEAD],
            candidate_commit=FrozenCommit(failure=CANDIDATE_ABSENT),
        )

        self._assert_unclaimed(github)

    def test_a_receipt_that_is_no_id_is_refused(self) -> None:
        # Read fail-closed like every other commit field: a head no checkout
        # can be compared to is no receipt, and comparing to it would compare
        # to nothing. The tick does its ordinary work instead -- what it may
        # not do is report a round under a claim nothing could prove.
        #
        # Which is why the seams that WRITE one must name a commit. A push
        # that recorded `("recovered_push", "")` and then crashed before its
        # tail would come back to exactly this: unpayable, so the round that
        # really landed is reported as the no-op flip below instead.
        for settled in (NOT_A_COMMIT, UNNAMED_HEAD):
            with self.subTest(settled=settled):
                github, issue = self._seed(extra_state={
                    SETTLED_OUTCOME: AGENT_RESOLVED, SETTLED_SHA: settled,
                })[:2]

                self._run_with_merge(
                    github, issue, head_shas=[MERGED_HEAD, MERGED_HEAD],
                )

                self.assertNotIn(AGENT_RESOLVED, _outcomes_of(github))
                self.assertIn(BASE_UP_TO_DATE, _outcomes_of(github))

    _settled = ResolvingConflictSettledRoundTest._settled

    def _assert_unclaimed(self, github) -> None:
        """No round is reported under a claim this checkout cannot prove.

        The tick carries on with its ordinary work behind the refusal -- the
        rebase, its own outcome, its own round. What it may not do is hand
        `validating` a round it says a settled resolution earned when the
        branch is not standing on that resolution.
        """
        self.assertNotIn(AGENT_RESOLVED, _outcomes_of(github))


class ResolvingConflictBodyEditRoundTest(
    unittest.TestCase, _ResolvingConflictMixin,
):
    """The fourth content update, and the receipt it shares with the others.

    A body edit resolved into a commit joins the pull request exactly as the
    rebase and the two resolutions do, so it is held the same way and owes the
    same receipt. It is also the one that can arrive while a receipt is
    already standing, because the handler asks for it ahead of the road that
    finishes an owed round.
    """

    def test_a_held_body_edit_names_its_round(self) -> None:
        # Without the receipt the settlement's tick reads a branch already
        # standing on its base and records this round as `base_up_to_date` --
        # the one exit that resolves nothing and stamps no
        # `last_conflict_resolved_at`.
        github, mocks = self._held_body_edit()

        mocks[PUSH_BRANCH].assert_not_called()
        self.assertIn((CONFLICT_ISSUE, LABEL_DECOMPOSING), github.label_history)
        self.assertEqual(_receipt_of(github), (DRIFT_RESOLVED, MERGED_HEAD))
        self.assertEqual(self._pinned(github).get(CONFLICT_ROUND), 0)

    def test_a_settled_body_edit_keeps_its_outcome(self) -> None:
        # End to end: the adjudication publishes the commit and hands the
        # label back, and the round is counted under the outcome the resume
        # actually had rather than the one a branch standing on its base
        # would be re-derived as.
        github = self._held_body_edit()[0]

        self._run_with_merge(
            github, github.get_issue(CONFLICT_ISSUE),
            head_shas=[MERGED_HEAD, MERGED_HEAD],
        )

        self.assertEqual(
            _settlements_of(github), [(DRIFT_RESOLVED, MERGED_HEAD)],
        )
        self.assertIn(RESOLVED_AT, self._pinned(github))

    def test_a_pending_round_defers_a_body_edit(self) -> None:
        # The edit arrives on a tick that already owes a round, and the head
        # seeded here is one a resume would commit. Let that resume run and it
        # takes the tick: its own outcome goes into the one receipt slot, the
        # round the settlement already published is never counted, and two
        # publications come to one increment under the wrong name. Deferred,
        # this tick pays what it owes under the outcome that earned it and
        # runs no agent -- there is no resolution in flight to reconsider,
        # since the receipt says the last one is already on the pull request.
        github = self._settled_and_edited()

        mocks = self._run_with_merge(
            github, github.get_issue(CONFLICT_ISSUE),
            head_shas=[MERGED_HEAD, EDITED_HEAD],
        )[0]

        self.assertEqual(
            _settlements_of(github), [(AGENT_RESOLVED, MERGED_HEAD)],
        )
        mocks[RUN_AGENT].assert_not_called()
        self.assertIn((CONFLICT_ISSUE, LABEL_VALIDATING), github.label_history)
        # Paid rather than replaced: the slot is empty because the round in it
        # was counted, not because a later resume overwrote it.
        self.assertIsNone(
            self._pinned(github).get(SETTLED_OUTCOME),
        )

    def test_a_deferred_body_edit_is_not_consumed(self) -> None:
        # The edit has to survive the tick that stepped over it, or the stage
        # it is handed to has nothing left to detect: the hash is the whole of
        # what says the body moved, and the notice is what tells a human the
        # dev was asked about it.
        github = self._settled_and_edited()
        baseline = self._pinned(github)["user_content_hash"]

        self._run_with_merge(
            github, github.get_issue(CONFLICT_ISSUE),
            head_shas=[MERGED_HEAD, MERGED_HEAD],
        )

        self.assertEqual(
            self._pinned(github)["user_content_hash"], baseline,
        )
        self.assertEqual(github.posted_pr_comments, [])

    def _held_body_edit(self):
        """One body-edit resolution the gate measures past the ceiling."""
        github = self._edited()
        with patch.object(config, MAX_ADDED_LINES, CEILING):
            return github, self._run_with_merge(
                github, github.get_issue(CONFLICT_ISSUE),
                head_shas=[BEFORE_HEAD, MERGED_HEAD],
                push_branch=True,
                added_lines=PAST_THE_CEILING,
                run_agent_result=_agent(
                    session_id="dev-sess", last_message="resolved the edit",
                ),
            )[0]

    def _settled_and_edited(self):
        """A round the settlement published, and a body edit on top of it."""
        return self._edited(**{
            SETTLED_OUTCOME: AGENT_RESOLVED, SETTLED_SHA: MERGED_HEAD,
        })

    def _edited(self, **extra_state):
        """One conflict issue whose body has moved since it was baselined."""
        github, issue = self._seed(extra_state=extra_state or None)[:2]
        self._seed_with_baseline_hash(github, issue)
        issue.body = "the requirement moved while the rebase was in flight"
        return github
