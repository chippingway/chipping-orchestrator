# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What a publication that did not finish costs, which is a tick and no more.

A plan commit can outlive the round that made it -- a mid-run pause withholds
every disposition by contract, a crash takes them with it -- and it can outlive
the publication itself, when a tick dies between opening the PR and recording
it or when the push simply fails. Each of those leaves the same thing on disk:
a branch whose whole diff against base is the plan file. So each is answered
the same way, by publishing it, and the parts that make that safe to repeat are
what this module pins.

Repeating it is safe because the records bracket the PR: the marker names the
tip before anything can change the world, and the rest land after it, so the
window a crash falls into leaves a PR the next tick adopts (`test_publication_
reuse.py`) rather than a record naming one that was never opened. The
alternative to all of this is what the refusal parks would otherwise say to an
operator: reset the worktree, discarding a plan the humans agreed to and a PR
that may already be open against it.

What none of it extends to is a commit nobody here began: while a marker
stands, it answers for the branch, so a second plan-shaped commit appearing
over an unfinished publication parks rather than going out as the agreed
design.
"""

from __future__ import annotations

import tempfile
import unittest
from dataclasses import dataclass
from pathlib import Path

from tests.support.fakes import FakePR, FakePRRef
from tests.workflow.fixtures import (
    BASE_TIP_SHA,
    KEY_PARK_REASON,
    STATE_CLOSED,
    _agent,
)
from tests.workflow.stages.discussion import discussion_test_support as _support
from tests.workflow.stages.discussion.discussion_resume_test_support import (
    DISCUSSION_REPLY,
    UNASKED_ROUND,
    _mark_in_flight,
    _paused_resumed_round,
    _reply,
    _seed_parked_discussion,
)
from tests.workflow.stages.discussion.discussion_test_support import _DiscussionWorkflowMixin

_RECOVERED_ISSUE_NUMBER = 1240
_ORDERING_ISSUE_NUMBER = 1242
_UNATTRIBUTED_ISSUE_NUMBER = 1244
_INTERRUPTED_ISSUE_NUMBER = 1245
_PAUSED_RESUME_ISSUE_NUMBER = 1247
_STALE_ISSUE_NUMBER = 1250
_STALE_REPEAT_ISSUE_NUMBER = 1251
_UNATTRIBUTED_PLAN_ISSUE_NUMBER = 1253
_DIVERGED_ISSUE_NUMBER = 1254
_UNREADABLE_REMOTE_ISSUE_NUMBER = 1255
_LEASED_ISSUE_NUMBER = 1256
_RESET_BRANCH_ISSUE_NUMBER = 1257
_RECONCILED_ISSUE_NUMBER = 1258
_PUBLISHED_RESET_ISSUE_NUMBER = 1260
_UNLANDED_RESET_ISSUE_NUMBER = 1261
_CLOSED_PR_RESET_ISSUE_NUMBER = 1262
_FOREIGN_COMMIT_ISSUE_NUMBER = 1263
_INTERRUPTED_FOREIGN_ISSUE_NUMBER = 1264
_PUBLISHED_PR_NUMBER = 8330
_CLOSED_PR_NUMBER = 8331
# What the remote says about a branch that is not there any more.
_NO_SUCH_BRANCH = ""
_ON_THE_REMOTE = "on the remote branch"
_RESET_COMMAND = "reset --hard"

# What a reviewer's own push leaves on the plan's branch while a publication of
# it is unfinished: a commit this host has never seen and does not contain.
_FOREIGN_TIP = "the-commit-a-reviewer-pushed-onto-the-plan-branch"

# The two tips a plan commit can fail to contain: one somebody else pushed, and
# the inherited PR head a round reset the branch off before committing its plan.
_UNCONTAINED_TIPS = (
    (_DIVERGED_ISSUE_NUMBER, _FOREIGN_TIP),
    (_RESET_BRANCH_ISSUE_NUMBER, _support.HEAD_BEFORE_ROUND),
)

_INHERITING_ROUND = "a round that would inherit it"
_CONFIRMED_DESIGN = "confirmed -- writing it up"

# A tick that publishes without opening a round reads the tip twice: once
# against the anchor, and once as the tip a publication would push.
_RECOVERED_HEAD = (_support.HEAD_AFTER_COMMIT,) * 2


class _OrderedClient:
    """Record the order a publication's two irreversible steps land in.

    Both are intercepted on the client the stage really calls, so what comes
    back is the order the tick executed rather than one this fixture arranged.
    """

    def __init__(self, gh) -> None:
        self.order: list[str] = []
        self.marked_shas: list = []
        self._open_pr = gh.open_pr
        self._write_pinned_state = gh.write_pinned_state
        gh.open_pr = self.open_pr
        gh.write_pinned_state = self.write_pinned_state

    def open_pr(self, **pr_fields):
        self.order.append("pr")
        return self._open_pr(**pr_fields)

    def write_pinned_state(self, issue, state):
        self.order.append("state")
        self.marked_shas.append(state.get(_support.KEY_PUBLISHING_SHA))
        return self._write_pinned_state(issue, state)


class DiscussionRecoveredPlanTest(unittest.TestCase, _DiscussionWorkflowMixin):
    """A plan commit found by a tick that opened no round of its own."""

    def test_a_recovered_plan_publishes_itself(self) -> None:
        # The round that wrote it was withheld mid-run or cut short before it
        # could report, so this tick reports for it -- publishing exactly what
        # that round would have, rather than costing the humans the artifact.
        recovered = self._publish_recovered(_RECOVERED_ISSUE_NUMBER)

        recovered.mocks[_support.RUN_AGENT].assert_not_called()
        recovered.mocks[_support.PUSH_BRANCH].assert_called_once()
        self.assertEqual(len(recovered.gh.opened_prs), 1)
        self.assertEqual(
            recovered.pinned[KEY_PARK_REASON], _support.PARK_DISCUSSION_PLAN_PUBLISHED,
        )
        self.assertEqual(recovered.pinned[_support.KEY_ROUND_SHA], _support.HEAD_AFTER_COMMIT)

    def test_a_plan_with_no_session_is_refused(self) -> None:
        # The other half of the same crash: the round that made this commit
        # opened a NEW conversation, so it dropped the previous id before
        # spawning and never got to record the one it opened. Publishing would
        # mean naming either nothing or a conversation that never saw the plan.
        unattributed = self._publish_recovered(
            _UNATTRIBUTED_PLAN_ISSUE_NUMBER, attributed=False,
        )

        self.assert_nothing_published(unattributed.gh, unattributed.mocks)
        self.assertEqual(
            unattributed.pinned[KEY_PARK_REASON], _support.PARK_DISCUSSION_UNATTRIBUTED,
        )
        self.assertNotIn(_support.KEY_PLAN_PATH, unattributed.pinned)
        # The commit is left where it is: the plan is real, only its
        # provenance is missing, and the message asks for the reset that lets
        # a round write it again under a session.
        _, body = unattributed.gh.posted_comments[0]
        self.assertIn(_support.HEAD_BEFORE_ROUND, body)

    def test_the_pr_is_bracketed_by_the_two_writes(self) -> None:
        # The marker goes first, so a tick that dies past it leaves a tip the
        # next one recognizes as its own rather than a plan-shaped commit
        # nobody may publish. The records go last, so a PR with no record is
        # recovered by the reuse in `test_publication_reuse.py` while a record
        # naming a PR that was never opened cannot happen at all. That the push
        # comes before the PR is the push-failure park's to pin.
        gh, issue = self._seed_unfinished_round(_ORDERING_ISSUE_NUMBER)
        writes_before = gh.write_state_calls
        recorded = _OrderedClient(gh)

        with tempfile.TemporaryDirectory() as tree:
            self._run_recovery_tick(gh, issue, Path(tree))

        self.assertEqual(recorded.order, ["state", "pr", "state"])
        self.assertEqual(gh.write_state_calls - writes_before, 2)
        self.assertEqual(
            recorded.marked_shas, [_support.HEAD_AFTER_COMMIT, None],
        )

    def _publish_recovered(
        self, issue_number: int, *, attributed: bool = True,
    ) -> _ParkedTick:
        """Seed a crashed round's commit and run the tick that settles it."""
        gh, issue = self._seed_unfinished_round(
            issue_number, attributed=attributed,
        )
        with tempfile.TemporaryDirectory() as tree:
            mocks = self._run_recovery_tick(gh, issue, Path(tree))
        return _ParkedTick(
            gh=gh, mocks=mocks, pinned=dict(gh.pinned_data(issue_number)),
        )

    def _seed_unfinished_round(self, issue_number: int, *, attributed=True):
        """An issue whose last round left a commit and no disposition.

        `attributed` is the session pin that round ran under: a resume has one
        durable before it spawns, which is what the publication names, while a
        round opening a NEW conversation drops the pin and can be cut short
        before it records the id it opened.
        """
        seeded = _support._seed_discussion(issue_number)
        round_records = {
            _support.KEY_ROUND_BRANCH: _support._issue_branch(issue_number),
            _support.KEY_ROUND_SHA: _support.HEAD_BEFORE_ROUND,
            _support.KEY_ROUND_OPEN: True,
            _support.KEY_BASE_SHA: BASE_TIP_SHA,
        }
        if attributed:
            round_records[_support.KEY_DISCUSSION_SESSION_ID] = _support.DISCUSSION_SESSION
        seeded[0].seed_state(issue_number, **round_records)
        return seeded

    def _run_recovery_tick(self, gh, issue, tree: Path):
        """One tick on an issue whose branch carries the plan, nothing else."""
        return self._run_discussion_on_worktree(
            gh,
            issue,
            tree,
            run_agent=_agent(last_message=_INHERITING_ROUND),
            head_shas=_RECOVERED_HEAD,
            committed_paths=(self.plan_path(issue.number),),
        )


@dataclass(frozen=True)
class _ParkedTick:
    """What one tick over a parked issue left for the assertions to read."""

    gh: object
    mocks: dict
    pinned: dict

    @property
    def park_reason(self) -> str:
        return self.pinned[KEY_PARK_REASON]


class DiscussionMarkedParkTest(unittest.TestCase, _DiscussionWorkflowMixin):
    """What a plan-shaped commit under a park earns, by who put it there."""

    def test_an_interrupted_publication_finishes(self) -> None:
        # The tick that began this one died after marking the tip and before
        # recording the PR, and its write took the consumed reply with it. So
        # nothing is unread on the thread, and waiting for one would mean
        # waiting for a human to answer the same round twice.
        published = self._tick_over_park(
            _INTERRUPTED_ISSUE_NUMBER, in_flight=_support.HEAD_AFTER_COMMIT,
        )

        self.assertEqual(len(published.gh.opened_prs), 1)
        self.assertEqual(published.park_reason, _support.PARK_DISCUSSION_PLAN_PUBLISHED)

    def test_an_unattributed_plan_commit_is_refused(self) -> None:
        # Nothing here began publishing anything: the round that earned this
        # park is over, so a commit that turned up on the branch afterwards
        # was made by something else -- an unrelated session, a hand at the
        # worktree -- and no reply, least of all one rejecting the design,
        # turns it into an agreed plan.
        refused = self._tick_over_park(
            _UNATTRIBUTED_ISSUE_NUMBER,
            replies=(_reply(DISCUSSION_REPLY),),
        )

        self.assert_nothing_published(refused.gh, refused.mocks)
        # Reported as the commit it is, and nothing recorded that would let a
        # later tick read the issue as having published a plan.
        self.assertEqual(refused.park_reason, _support.PARK_DISCUSSION_COMMITS)
        self.assertNotIn(_support.KEY_PLAN_PATH, refused.pinned)

    def test_a_moved_tip_parks_instead_of_publishing(self) -> None:
        # The commit the branch is on now is plan-shaped too, which is exactly
        # why this cannot fall through to the readings below: nothing checked
        # it, and publishing it would put a design out under a publication
        # begun for a different one.
        stale = self._tick_over_park(
            _STALE_ISSUE_NUMBER,
            in_flight=_support.HEAD_BEFORE_ROUND,
            # The round flag stands too, exactly as a crash mid-publication
            # leaves it: without the marker being authoritative, this commit
            # would be read as that round's own work and published.
            round_open=True,
            replies=(_reply(DISCUSSION_REPLY),),
        )

        self.assert_nothing_published(stale.gh, stale.mocks)
        self.assertEqual(
            stale.park_reason, _support.PARK_DISCUSSION_STALE_PUBLISH,
        )
        # Both SHAs are named: restoring the first is what lets the
        # publication finish on its own.
        _, body = stale.gh.posted_comments[0]
        self.assertIn(_support.HEAD_BEFORE_ROUND, body)
        self.assertIn(_support.HEAD_AFTER_COMMIT, body)
        # The marker stands, so a restored branch republishes rather than
        # costing the humans the artifact.
        self.assertEqual(stale.pinned[_support.KEY_PUBLISHING_SHA], _support.HEAD_BEFORE_ROUND)

    def _tick_over_park(
        self,
        issue_number: int,
        *,
        in_flight: str = "",
        round_open: bool = False,
        **park_options,
    ) -> _ParkedTick:
        """One tick on a parked issue whose branch carries the plan.

        What varies is only what the park has standing beside it: the tip a
        publication was pushing, and whether a round of this stage was still
        in flight. With neither, the commit on the branch is one this stage
        found rather than one it began.
        """
        gh, issue = _seed_parked_discussion(issue_number, **park_options)
        records = {}
        if in_flight:
            records[_support.KEY_PUBLISHING_SHA] = in_flight
        if round_open:
            records[_support.KEY_ROUND_OPEN] = True
        if records:
            _mark_in_flight(gh, issue.number, **records)

        with tempfile.TemporaryDirectory() as tree:
            mocks = self._run_discussion_on_worktree(
                gh,
                issue,
                Path(tree),
                run_agent=_agent(last_message=UNASKED_ROUND),
                head_shas=_RECOVERED_HEAD,
                committed_paths=(self.plan_path(issue.number),),
            )

        mocks[_support.RUN_AGENT].assert_not_called()
        return _ParkedTick(
            gh=gh, mocks=mocks, pinned=dict(gh.pinned_data(issue.number)),
        )


class DiscussionDivergedBranchTest(unittest.TestCase, _DiscussionWorkflowMixin):
    """What a publication does with a remote branch somebody else moved.

    The recovery this stage is built on republishes a commit it already
    validated, and a push whose lease value is whatever its own read finds
    adopts that tip as the one it may overwrite. So a publication that crashed
    before its records, on a branch a reviewer has pushed to since, would send
    the older commit straight over that push and leave no trace it existed.
    """

    def test_an_uncontained_tip_is_refused(self) -> None:
        # Two shapes, one rule. A human amended the branch on its PR while the
        # publication was unfinished, and a round that reset an inherited PR
        # branch to base before committing the plan: in both the commit this
        # tick would push does not descend from what the remote is on, and no
        # record it names makes that safe -- the lease would only prove the ref
        # had not moved, not that the PR's history survives being replaced.
        for issue_number, remote_tip in _UNCONTAINED_TIPS:
            with self.subTest(remote_tip=remote_tip):
                refused = self._publish_over_remote(
                    issue_number, remote_tip, contains=False,
                )

                self.assert_nothing_published(refused.gh, refused.mocks)
                self.assertEqual(
                    refused.park_reason, _support.PARK_DISCUSSION_PUSH_FAILED,
                )
                # The tip that is there is named, so an operator can see what
                # would have been discarded.
                _, body = refused.gh.posted_comments[0]
                self.assertIn(remote_tip, body)
                # And the marker stands, so the retry is still there to be made
                # once the branch and the remote agree again.
                self.assertEqual(
                    refused.pinned[_support.KEY_PUBLISHING_SHA], _support.HEAD_AFTER_COMMIT,
                )

    def test_an_unreadable_remote_is_not_overwritten(self) -> None:
        # A read that failed established nothing, which is not the same as a
        # branch that has not moved -- and pushing on the difference is pushing
        # on a guess.
        unreadable = self._publish_over_remote(
            _UNREADABLE_REMOTE_ISSUE_NUMBER, None,
        )

        self.assert_nothing_published(unreadable.gh, unreadable.mocks)
        self.assertEqual(unreadable.park_reason, _support.PARK_DISCUSSION_PUSH_FAILED)
        self.assertEqual(
            unreadable.pinned[_support.KEY_PUBLISHING_SHA], _support.HEAD_AFTER_COMMIT,
        )

    def test_the_lease_pins_the_tip_that_was_read(self) -> None:
        # The publication that does go out: the branch is at the very commit
        # this publication pushed before it died. The lease is pinned to that
        # reading rather than left to the push's own, so anything that lands in
        # the window between the two commands refuses the push instead of
        # becoming the tip it is allowed to clobber.
        published = self._publish_over_remote(
            _LEASED_ISSUE_NUMBER, _support.HEAD_AFTER_COMMIT,
        )

        self.assertEqual(len(published.gh.opened_prs), 1)
        push = published.mocks[_support.PUSH_BRANCH].call_args
        self.assertEqual(push.kwargs["force_with_lease"], _support.HEAD_AFTER_COMMIT)
        self.assertEqual(push.kwargs["revision"], _support.HEAD_AFTER_COMMIT)

    def test_a_refusal_leaves_its_own_retry(self) -> None:
        # The FIRST attempt is the one that has to leave something behind. It
        # reads a tip this plan does not contain and parks -- and the retry that
        # park asks for is only reachable through the in-flight marker: with no
        # marker there is no publication to finish and no round open, the park's
        # own reason suppresses the repair request, and the thread goes quiet
        # with neither a push nor an agent ever running again.
        gh, issue = _support._seed_discussion(_RECONCILED_ISSUE_NUMBER)

        refused = self._publish_first_round(gh, issue)

        self.assertEqual(refused.park_reason, _support.PARK_DISCUSSION_PUSH_FAILED)
        self.assertEqual(refused.gh.opened_prs, [])
        self.assertEqual(
            refused.pinned[_support.KEY_PUBLISHING_SHA], _support.HEAD_AFTER_COMMIT,
        )

        # The operator reconciles the branch and says so on the thread.
        issue.comments.append(_reply(DISCUSSION_REPLY))
        published = self._retry_on_reply(gh, issue)

        self.assertEqual(len(published.gh.opened_prs), 1)
        self.assertEqual(published.park_reason, _support.PARK_DISCUSSION_PLAN_PUBLISHED)
        self.assertIsNone(published.pinned[_support.KEY_PUBLISHING_SHA])

    def _publish_first_round(self, gh, issue) -> _ParkedTick:
        """A round that commits the plan onto a branch the remote has moved."""
        mocks = self._run_discussion(
            gh,
            issue,
            run_agent=_agent(
                session_id=_support.DISCUSSION_SESSION, last_message=_CONFIRMED_DESIGN,
            ),
            head_shas=_support.MOVED_HEAD,
            committed_paths=(self.plan_path(issue.number),),
            remote_branch_tip=_FOREIGN_TIP,
            commit_contains=False,
        )
        return _ParkedTick(
            gh=gh, mocks=mocks, pinned=dict(gh.pinned_data(issue.number)),
        )

    def _retry_on_reply(self, gh, issue) -> _ParkedTick:
        """The reply that retries it, over a remote nobody has moved since."""
        mocks = self._run_discussion_in_temp_checkout(
            gh,
            issue,
            run_agent=_agent(last_message=UNASKED_ROUND),
            head_shas=_RECOVERED_HEAD,
            committed_paths=(self.plan_path(issue.number),),
            remote_branch_tip=_support.HEAD_AFTER_COMMIT,
        )

        mocks[_support.RUN_AGENT].assert_not_called()
        return _ParkedTick(
            gh=gh, mocks=mocks, pinned=dict(gh.pinned_data(issue.number)),
        )

    def _publish_over_remote(
        self, issue_number: int, remote_tip, *, contains: bool = True,
    ) -> _ParkedTick:
        """One tick recovering a marked publication over a given remote tip."""
        gh, issue = _seed_parked_discussion(issue_number)
        _mark_in_flight(
            gh, issue.number, **{_support.KEY_PUBLISHING_SHA: _support.HEAD_AFTER_COMMIT},
        )

        mocks = self._run_discussion_in_temp_checkout(
            gh,
            issue,
            run_agent=_agent(last_message=UNASKED_ROUND),
            head_shas=_RECOVERED_HEAD,
            committed_paths=(self.plan_path(issue.number),),
            remote_branch_tip=remote_tip,
            commit_contains=contains,
        )

        mocks[_support.RUN_AGENT].assert_not_called()
        return _ParkedTick(
            gh=gh, mocks=mocks, pinned=dict(gh.pinned_data(issue.number)),
        )


class DiscussionResetOverPublicationTest(
    unittest.TestCase, _DiscussionWorkflowMixin,
):
    """A branch back at the round's anchor, over a publication that landed.

    That reading is the one that spends the marker, and it is a claim about the
    remote that no local probe can make. The push sends the SHA it validated
    rather than `HEAD`, so a plan committed on a detached head goes out while
    the local ref never moves -- and a checkout restored later comes back on
    that ref rather than on the head just fetched. Every local reading then
    agrees the branch was reset back to where the round opened it, while the
    plan sits on a pull request nobody recorded.
    """

    def test_a_landed_publication_is_not_reset_away(self) -> None:
        # Spent on that reading, the marker goes, no records replace it, and
        # the tick opens another round over a design the humans already have on
        # a PR. So the remote is asked before the reset is believed.
        gh, plan_issue = self._seed_published_elsewhere(
            _PUBLISHED_RESET_ISSUE_NUMBER,
        )

        mocks = self._run_discussion_in_temp_checkout(
            gh,
            plan_issue,
            run_agent=_agent(last_message=_INHERITING_ROUND),
            # Enough for the round this must not open, so a regression fails
            # on the agent having run rather than on a probe running dry.
            head_shas=(_support.HEAD_BEFORE_ROUND,) * 5,
            committed_paths=(self.plan_path(plan_issue.number),),
            remote_branch_tip=_support.HEAD_AFTER_COMMIT,
        )

        mocks[_support.RUN_AGENT].assert_not_called()
        self.assert_nothing_published(gh, mocks)
        pinned_data = gh.pinned_data(plan_issue.number)
        # The record that knows a publication is out there survives.
        self.assertEqual(pinned_data[_support.KEY_PUBLISHING_SHA], _support.HEAD_AFTER_COMMIT)
        self.assertEqual(
            pinned_data[KEY_PARK_REASON], _support.PARK_DISCUSSION_STALE_PUBLISH,
        )
        _, body = gh.posted_comments[0]
        # Told where the plan really is, and not told to reset it away: a local
        # reset cannot drop a commit the remote has, and offering one would ask
        # an operator to lose track of a pull request that stays open anyway.
        self.assertIn(_ON_THE_REMOTE, body)
        self.assertNotIn(_RESET_COMMAND, body)

    def test_a_reset_with_nothing_published_is_final(self) -> None:
        # The other half of the same question, and the flow that must not be
        # caught by it: the branch is on the remote -- an issue relabeled here
        # carrying its dev's PR has one -- but what is on it does not descend
        # from the commit the marker names, so nothing of this stage's is out
        # there to outlive the reset. The operator took the remedy, the marker
        # is spent, and the conversation continues from where it was left.
        gh, plan_issue = self._seed_published_elsewhere(
            _UNLANDED_RESET_ISSUE_NUMBER,
        )

        mocks = self._run_discussion_in_temp_checkout(
            gh,
            plan_issue,
            run_agent=_agent(
                session_id=_support.DISCUSSION_SESSION, last_message=_INHERITING_ROUND,
            ),
            head_shas=(_support.HEAD_BEFORE_ROUND,) * 5,
            remote_branch_tip=_FOREIGN_TIP,
            commit_contains=False,
        )

        mocks[_support.RUN_AGENT].assert_called_once()
        self.assert_nothing_published(gh, mocks)
        self.assertIsNone(
            gh.pinned_data(plan_issue.number)[_support.KEY_PUBLISHING_SHA],
        )

    def test_a_closed_pr_does_not_keep_the_marker(self) -> None:
        # The branch is gone from the remote, and the pull request carrying the
        # commit is closed rather than merged: nothing landed, nothing is
        # reviewable, and there is nothing left for a later push to overwrite.
        # Read as "still published", the marker is kept over a plan that no
        # longer exists anywhere and the conversation never gets to continue.
        gh, plan_issue = self._seed_published_elsewhere(
            _CLOSED_PR_RESET_ISSUE_NUMBER,
        )
        gh.add_pr(FakePR(
            number=_CLOSED_PR_NUMBER,
            head_branch=_support._issue_branch(_CLOSED_PR_RESET_ISSUE_NUMBER),
            head=FakePRRef(sha=_support.HEAD_AFTER_COMMIT),
            state=STATE_CLOSED,
        ))

        mocks = self._run_discussion_in_temp_checkout(
            gh,
            plan_issue,
            run_agent=_agent(
                session_id=_support.DISCUSSION_SESSION, last_message=_INHERITING_ROUND,
            ),
            head_shas=(_support.HEAD_BEFORE_ROUND,) * 5,
            remote_branch_tip=_NO_SUCH_BRANCH,
        )

        mocks[_support.RUN_AGENT].assert_called_once()
        self.assert_nothing_published(gh, mocks)
        self.assertIsNone(
            gh.pinned_data(plan_issue.number)[_support.KEY_PUBLISHING_SHA],
        )

    def _seed_published_elsewhere(self, issue_number: int):
        """An issue whose plan is on the remote and whose branch is not.

        The marker names the commit that went out, the anchor names the tip the
        local ref never moved off, and the pull request the crash opened is up
        on that branch with nothing pinned pointing at it.
        """
        gh, plan_issue = _support._seed_discussion(issue_number)
        branch = _support._issue_branch(issue_number)
        gh.seed_state(
            issue_number,
            **{
                _support.KEY_PUBLISHING_SHA: _support.HEAD_AFTER_COMMIT,
                _support.KEY_ROUND_BRANCH: branch,
                _support.KEY_ROUND_SHA: _support.HEAD_BEFORE_ROUND,
                _support.KEY_BASE_SHA: BASE_TIP_SHA,
                _support.KEY_DISCUSSION_SESSION_ID: _support.DISCUSSION_SESSION,
            },
        )
        gh.existing_open_pr[branch] = FakePR(
            number=_PUBLISHED_PR_NUMBER, head_branch=branch,
        )
        return gh, plan_issue


class DiscussionOpenRoundOwnershipTest(
    unittest.TestCase, _DiscussionWorkflowMixin,
):
    """What the open-round record decides about a commit found under a park.

    A park means some stage handed the issue back, so a commit that appeared
    after one is not this stage's on its face. `discussion_round_open` is the
    record that says otherwise, and it is read whichever stage wrote the park:
    pinned state outlives a relabel, and an issue moved out to `question` and
    back arrives under that stage's park still carrying this stage's anchor
    and session id.
    """

    def test_a_paused_resumed_round_still_publishes(self) -> None:
        # A resumed round runs with the park it is answering still durable, so
        # the anchor alone cannot say a round of this stage made the commit
        # that appeared under it. The flag written beside the anchor can, and
        # without it the plan the humans just agreed to would come back to
        # them as a violation to reset away.
        gh, issue = _seed_parked_discussion(
            _PAUSED_RESUME_ISSUE_NUMBER, replies=(_reply(DISCUSSION_REPLY),),
        )

        with tempfile.TemporaryDirectory() as tree:
            _paused_resumed_round(self, gh, issue, Path(tree))

            # The pause withheld every disposition, so the round said nothing
            # and its reply is still unread -- but it committed.
            self.assertEqual(gh.posted_comments, [])

            recovery_mocks = self._run_discussion_on_worktree(
                gh,
                issue,
                Path(tree),
                run_agent=_agent(last_message=UNASKED_ROUND),
                head_shas=_RECOVERED_HEAD,
                committed_paths=(self.plan_path(issue.number),),
            )

        recovery_mocks[_support.RUN_AGENT].assert_not_called()
        self.assertEqual(len(gh.opened_prs), 1)
        self.assertEqual(
            gh.pinned_data(issue.number)[KEY_PARK_REASON],
            _support.PARK_DISCUSSION_PLAN_PUBLISHED,
        )

    def test_a_foreign_stage_commit_is_not_published(self) -> None:
        # The route in is a relabel: a discussion that finished leaves its
        # anchor and its session id behind, an operator moves the issue to
        # `question`, that agent commits the one path this stage publishes and
        # parks for it, and the issue comes back. The park is not this stage's,
        # so the tick reads the branch itself -- and the anchor alone says only
        # that the tip moved, never by whom. The open-round record is what says
        # it, and no round of this stage was running.
        gh, relabeled = _seed_parked_discussion(
            _FOREIGN_COMMIT_ISSUE_NUMBER, park_reason=_support.PARK_FOREIGN_QUESTION,
        )

        mocks = self._foreign_park_tick(gh, relabeled)

        # A plan-shaped commit is exactly the dangerous case: every other check
        # passes it, and only the ownership record refuses it.
        mocks[_support.RUN_AGENT].assert_not_called()
        self.assert_nothing_published(gh, mocks)
        self.assert_worktree_preserved(mocks)
        pinned_data = gh.pinned_data(relabeled.number)
        self.assertEqual(
            (pinned_data[KEY_PARK_REASON], pinned_data.get(_support.KEY_PLAN_PATH)),
            (_support.PARK_DISCUSSION_COMMITS, None),
        )
        # The park names the anchor to reset back to, so the operator is not
        # told to throw away commits the branch arrived carrying.
        self.assertIn(
            f"{_RESET_COMMAND} {_support.HEAD_BEFORE_ROUND}",
            gh.posted_comments[-1][1],
        )

    def test_an_open_round_publishes_under_it(self) -> None:
        # The same foreign park with the flag set: an operator relabeled away
        # and back while a round of THIS stage was still running, so the commit
        # under it is the plan that round wrote and publishing it is right.
        gh, interrupted = _seed_parked_discussion(
            _INTERRUPTED_FOREIGN_ISSUE_NUMBER,
            park_reason=_support.PARK_FOREIGN_QUESTION,
        )
        _mark_in_flight(gh, interrupted.number, **{_support.KEY_ROUND_OPEN: True})

        self._foreign_park_tick(gh, interrupted)

        self.assertEqual(len(gh.opened_prs), 1)
        self.assertEqual(
            gh.pinned_data(interrupted.number)[KEY_PARK_REASON],
            _support.PARK_DISCUSSION_PLAN_PUBLISHED,
        )

    def _foreign_park_tick(self, gh, issue):
        """One tick over a checkout another stage committed into."""
        return self._run_discussion_in_temp_checkout(
            gh,
            issue,
            run_agent=_agent(last_message=_INHERITING_ROUND),
            head_shas=_RECOVERED_HEAD,
            committed_paths=(self.plan_path(issue.number),),
        )


if __name__ == "__main__":
    unittest.main()
