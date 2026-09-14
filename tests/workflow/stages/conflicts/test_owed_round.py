# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""When a round this stage owes is settled, and what may not run before it.

The receipt is one slot and the round in it is already published, so what
decides whether it is ever counted is ORDER. Two things it outranks would each
lose it. The `MAX_CONFLICT_ROUNDS` cap refuses another attempt, and a round
already finished and published is not one -- so a receipt recorded at the
ceiling, which the body-edit road can reach, would be refused with the
attempts and strand there. A dev resume -- a body edit or a human reply --
writes the same slot with its own commit, so one answered first records its
outcome over the round the adjudication already published.

One thing outranks the receipt in turn. A branch behind its remote is refused,
because what the tail hands `workflow:validating` is the CHECKOUT and the
reviewer spawned behind it reuses a worktree rather than fast-forwarding it --
so the round waits for a human to reconcile the branch rather than buying a
verdict taken over a commit the pull request has moved past.

The receipt itself, and the four content updates that write it, are in
`test_settled_round.py` beside this.
"""
from __future__ import annotations

import unittest
from unittest.mock import patch

from orchestrator import config
from orchestrator.git.measurement.models import FrozenCommit
from tests.support.fakes import FakeComment, FakeUser
from tests.workflow.patch_models import _agent
from tests.workflow.stages.conflicts.round_record_support import _receipt_of, _rounds_of, _settlements_of
from tests.workflow.stages.conflicts.test_settled_round import (
    ResolvingConflictBodyEditRoundTest,
    ResolvingConflictSettledRoundTest,
    _ResolvingConflictMixin,
)

CONFLICT_ISSUE = 200
BEFORE_HEAD = "be40e5ba" * 5
MERGED_HEAD = "cccccccc" * 5

CEILING = 5
PAST_THE_CEILING = 6
MAX_ADDED_LINES = "MAX_ADDED_LINES"

RUN_AGENT = "run_agent"
PUSH_BRANCH = "_push_branch"

LABEL_VALIDATING = "workflow:validating"

AWAITING_HUMAN = "awaiting_human"
CONFLICT_ROUND = "conflict_round"
SETTLED_OUTCOME = "conflict_settled_outcome"
SETTLED_SHA = "conflict_settled_sha"

AGENT_RESOLVED = "agent_resolved"
DRIFT_RESOLVED = "drift_resolved"
RECOVERED_PUSH = "recovered_push"

# The cap on how many rounds this stage may spend, and a counter that has
# spent every one of them.
MAX_CONFLICT_ROUNDS = "MAX_CONFLICT_ROUNDS"
AT_THE_CAP = 3
CONFLICT_CAP = "conflict_cap"
PARK_EVENT = "park_awaiting_human"
REASON = "reason"
EVENT = "event"

# The reply an operator leaves on a parked rebase, and the watermark it has to
# clear before anything reads it as new.
HUMAN_REPLY_ID = 2000
CONSUMED_UP_TO = 1000
HUMAN_LOGIN = "alice"
LAST_ACTION_COMMENT_ID = "last_action_comment_id"

# A head the checkout is not standing on, so the receipt naming it is one this
# tick cannot prove.
UNPROVABLE_HEAD = "0d0d0d0d" * 5

# What the ahead/behind comparison answers for a branch a descendant landed on
# top of: the settled commit is still in the remote's history, and the checkout
# is no longer the head that pull request carries.
OVERTAKEN = (0, 2)

# What the divergence park says, which is the one thing that makes the handoff
# safe again.
DIVERGED_NOTICE = "stale or diverged"

# The label a settled round hands the checkout to, and what the reviewer
# spawned there answers with.
REVIEW_APPROVED = "VERDICT: APPROVED"
LABEL_DOCUMENTING = "workflow:documenting"

DEV_SESSION = "dev-sess"

# What the ahead/behind comparison answers for a checkout carrying a commit an
# earlier tick made and never pushed, and what that commit is.
AHEAD = (1, 0)
STRANDED_HEAD = "5717a9ed" * 5
ON_BASE = "0\n"

PUSH_BRANCH = "_push_branch"
USER_CONTENT_HASH = "user_content_hash"
REVISION = "revision"
PARK_REASON = "park_reason"

# A park that needs a real answer, left over a commit the timed-out agent had
# already made.
AGENT_TIMEOUT = "agent_timeout"

# What the human says on the park, which moves the drift hash exactly as a
# body edit does -- every reply does, since the hash covers the thread.
HUMAN_REPLY = "drop the half-finished helper and take the upstream one"

# The head the resumed dev leaves once it has been told what to do, and the
# outcomes the two roads out of an ahead checkout record.
RESOLVED_HEAD = "re501ved" * 5
OUTCOME = "outcome"


class ResolvingConflictCappedRoundTest(
    unittest.TestCase, _ResolvingConflictMixin,
):
    """What `MAX_CONFLICT_ROUNDS` stops at the ceiling, and what it may not.

    The cap ends a loop that cannot converge on its own, so what it refuses is
    another ATTEMPT -- a rebase, a recovered push, a dev run over conflicted
    files. A round this stage already finished and an adjudication has since
    published is none of those: the commit is on the pull request and only the
    counter and the label are still owed.
    """

    def test_a_capped_round_is_still_settled(self) -> None:
        # Refused with the attempts, the receipt is stranded for good: nothing
        # clears it, no round is ever counted for a push that really landed,
        # and the issue parks on a `validating` handoff no later tick makes.
        github = self._settled(AGENT_RESOLVED)[0]

        with patch.object(config, MAX_CONFLICT_ROUNDS, AT_THE_CAP):
            self._at_the_cap(github)

        self.assertEqual(
            _settlements_of(github), [(AGENT_RESOLVED, MERGED_HEAD)],
        )
        pinned = self._pinned(github)
        self.assertEqual(pinned.get(CONFLICT_ROUND), AT_THE_CAP + 1)
        self.assertIsNone(pinned.get(SETTLED_OUTCOME))
        self.assertIn((CONFLICT_ISSUE, LABEL_VALIDATING), github.label_history)
        self.assertFalse(pinned.get(AWAITING_HUMAN))

    def test_a_capped_tick_owing_nothing_still_parks(self) -> None:
        # What settling ahead of the cap may not cost. An issue with no round
        # outstanding still stops at the ceiling rather than rebasing again,
        # and it stops under the reason the cap gives rather than some later
        # refusal standing in for it.
        github = self._seed()[0]

        with patch.object(config, MAX_CONFLICT_ROUNDS, AT_THE_CAP):
            merge = self._at_the_cap(github)[1]

        merge.assert_not_called()
        pinned = self._pinned(github)
        self.assertTrue(pinned.get(AWAITING_HUMAN))
        self.assertEqual(pinned.get(CONFLICT_ROUND), AT_THE_CAP)
        self.assertEqual(
            [
                event[REASON] for event in github.recorded_events
                if event["event"] == PARK_EVENT
            ],
            [CONFLICT_CAP],
        )

    def test_a_capped_body_edit_is_resumed(self) -> None:
        # How a receipt reaches the ceiling in the first place: the body-edit
        # resume is asked ahead of the rebase road the cap guards, so an edit
        # arriving on a spent counter is still resolved -- and a resolution
        # the gate holds there leaves the same receipt any other would.
        github = self._edited()

        with patch.object(config, MAX_CONFLICT_ROUNDS, AT_THE_CAP), patch.object(config, MAX_ADDED_LINES, CEILING):
            mocks = self._at_the_cap(
                github,
                head_shas=[BEFORE_HEAD, MERGED_HEAD],
                push_branch=True,
                added_lines=PAST_THE_CEILING,
                run_agent_result=_agent(
                    session_id="dev-sess", last_message="resolved it",
                ),
            )[0]

        mocks[PUSH_BRANCH].assert_not_called()
        pinned = self._pinned(github)
        self.assertEqual(pinned.get(SETTLED_OUTCOME), DRIFT_RESOLVED)
        self.assertEqual(pinned.get(CONFLICT_ROUND), AT_THE_CAP)

    def test_a_capped_ahead_round_still_recovers(self) -> None:
        # The cap refuses another ATTEMPT, and publishing a commit an earlier
        # tick already made is not one -- it is the only road that pays the
        # receipt standing over it. Refused with the attempts, every tick
        # re-parks: nothing pushed, no round counted, and the receipt never
        # cleared.
        github = self._settled(AGENT_RESOLVED)[0]

        with patch.object(config, MAX_CONFLICT_ROUNDS, AT_THE_CAP):
            mocks = self._at_the_cap(
                github,
                head_shas=[STRANDED_HEAD, STRANDED_HEAD],
                candidate_commit=FrozenCommit(sha=STRANDED_HEAD),
                branch_ahead_behind=AHEAD,
                behind_base=ON_BASE,
                push_branch=True,
            )[0]

        mocks[PUSH_BRANCH].assert_called_once()
        # Reached its own tail, so the round is counted under the outcome that
        # push earned and the stale receipt goes with it -- nothing is left
        # for a later tick to finish a second time.
        self.assertEqual(
            _settlements_of(github), [(RECOVERED_PUSH, STRANDED_HEAD)],
        )
        self.assertEqual(_receipt_of(github), (None, None))

    def _at_the_cap(self, github, **run_options):
        """Run one tick over a counter that has spent every round it may."""
        pinned = self._pinned(github)
        pinned[CONFLICT_ROUND] = AT_THE_CAP
        github.seed_state(CONFLICT_ISSUE, **pinned)
        run_options.setdefault("head_shas", [MERGED_HEAD, MERGED_HEAD])
        return self._run_with_merge(
            github, github.get_issue(CONFLICT_ISSUE), **run_options,
        )

    _settled = ResolvingConflictSettledRoundTest._settled

    _edited = ResolvingConflictBodyEditRoundTest._edited


class ResolvingConflictParkedRoundTest(
    unittest.TestCase, _ResolvingConflictMixin,
):
    """A round owed on an issue that is also waiting on a person.

    The tick that comes back from a settlement can park before it settles --
    a branch fetch that failed, a divergence nothing could read -- and the
    receipt stands through it. What arrives next is a human reply, and the
    resume it would start writes the one receipt slot itself: pushed, the owed
    round is cleared without ever being counted; held, the gate writes over
    it. So the settlement goes first and the reply waits one tick.
    """

    def test_a_parked_round_settles_before_the_reply(self) -> None:
        # The round the adjudication published is counted under the outcome
        # that earned it, and no agent runs: a reply cannot answer a question
        # this stage is not asking, and resuming on it would spend the slot
        # the owed round is waiting in.
        github, mocks = self._replied_to()

        self.assertEqual(
            _settlements_of(github), [(AGENT_RESOLVED, MERGED_HEAD)],
        )
        mocks[RUN_AGENT].assert_not_called()
        self.assertIn((CONFLICT_ISSUE, LABEL_VALIDATING), github.label_history)

    def test_a_settled_round_clears_its_park(self) -> None:
        # The reading this tick took is the one the park was for, and it
        # worked. Left set, `validating` is handed an issue that reads as
        # waiting on somebody -- and the reply stays unconsumed, so the stage
        # the label lands on still sees it as new.
        github = self._replied_to()[0]

        pinned = self._pinned(github)
        self.assertFalse(pinned.get(AWAITING_HUMAN))
        self.assertIsNone(pinned.get(SETTLED_OUTCOME))
        self.assertEqual(pinned.get(LAST_ACTION_COMMENT_ID), CONSUMED_UP_TO)

    def test_an_unprovable_round_still_resumes(self) -> None:
        # The deferral is one tick's, not a deadlock. A receipt this host
        # cannot prove -- a checkout standing somewhere else -- is one no tick
        # can pay, so the reply is answered rather than held behind it
        # forever.
        github, mocks = self._replied_to(
            candidate_commit=FrozenCommit(sha=UNPROVABLE_HEAD),
        )

        mocks[RUN_AGENT].assert_called_once()
        self.assertEqual(_settlements_of(github), [])

    def _replied_to(self, **run_options):
        """One parked issue owing a round, with a fresh reply waiting on it."""
        github = self._seed(extra_state={
            AWAITING_HUMAN: True,
            LAST_ACTION_COMMENT_ID: CONSUMED_UP_TO,
            SETTLED_OUTCOME: AGENT_RESOLVED,
            SETTLED_SHA: MERGED_HEAD,
        })[0]
        issue = github.get_issue(CONFLICT_ISSUE)
        issue.comments.append(FakeComment(
            id=HUMAN_REPLY_ID,
            body="the conflict in foo.py is structural",
            user=FakeUser(HUMAN_LOGIN),
        ))
        return github, self._run_with_merge(
            github, issue,
            head_shas=[MERGED_HEAD, MERGED_HEAD],
            push_branch=True,
            run_agent_result=_agent(
                session_id="dev-sess", last_message="resolved",
            ),
            **run_options,
        )[0]


class ResolvingConflictOvertakenRoundTest(
    unittest.TestCase, _ResolvingConflictMixin,
):
    """A settled round whose remote has moved past the commit it names.

    The round really did land -- a remote standing on a DESCENDANT of the
    settled commit carries it -- so the counter is not what is at risk here.
    The handoff is: the tail hands `validating` this checkout, and the
    reviewer spawned behind it reuses the worktree as it finds it rather than
    fast-forwarding to the tip.
    """

    def test_an_overtaken_round_is_not_handed_on(self) -> None:
        # Waved through, the round is counted correctly and a human is then
        # shown a verdict taken over the commit the pull request has already
        # moved past.
        github, mocks = self._overtaken()

        self.assertEqual(_settlements_of(github), [])
        self.assertNotIn(
            (CONFLICT_ISSUE, LABEL_VALIDATING), github.label_history,
        )
        # And the checkout is left exactly as it stands: nothing here rebases
        # it forward or pushes it, so a human reconciling the branch is the
        # only thing that moves it.
        mocks[RUN_AGENT].assert_not_called()
        mocks[PUSH_BRANCH].assert_not_called()

    def test_an_overtaken_round_asks_for_the_branch(self) -> None:
        # The receipt keeps standing and the divergence guard behind the
        # settlement asks a human to reconcile the branch, which is the one
        # thing that makes the handoff safe again. The same reading settles
        # the round on the tick after that.
        github = self._overtaken()[0]

        self.assertEqual(_receipt_of(github), (AGENT_RESOLVED, MERGED_HEAD))
        pinned = self._pinned(github)
        self.assertTrue(pinned.get(AWAITING_HUMAN))
        self.assertIn(DIVERGED_NOTICE, github.posted_comments[-1][1])

    def test_a_reconciled_branch_settles_the_round(self) -> None:
        # What says the refusal above is about the checkout rather than about
        # the round: the same receipt, over a branch level with its remote,
        # is counted and handed on.
        github = self._settled(AGENT_RESOLVED)[0]

        self._tick(github)

        self.assertEqual(
            _settlements_of(github), [(AGENT_RESOLVED, MERGED_HEAD)],
        )
        self.assertIn((CONFLICT_ISSUE, LABEL_VALIDATING), github.label_history)

    def test_the_handoff_starts_a_reviewer_at_once(self) -> None:
        # Why the refusal above is about the checkout. The round hands the
        # issue to `validating`, and the very next tick there spawns the
        # reviewer over the worktree this stage left -- `_ensure_worktree`
        # reuses a checkout rather than fast-forwarding it to the remote tip,
        # so whatever head the handoff leaves behind is the head a human is
        # shown a verdict on.
        github = self._settled(AGENT_RESOLVED)[0]
        self._tick(github)

        mocks = self._run_validating(
            github, github.get_issue(CONFLICT_ISSUE),
            run_agent=_agent(last_message=REVIEW_APPROVED),
        )

        self.assertEqual(mocks[RUN_AGENT].call_count, 1)
        self.assertIn(
            (CONFLICT_ISSUE, LABEL_DOCUMENTING), github.label_history,
        )

    def _overtaken(self):
        """One owed round over a branch the remote has moved past."""
        github = self._settled(AGENT_RESOLVED)[0]
        return github, self._tick(github, branch_ahead_behind=OVERTAKEN)

    def _tick(self, github, **run_options):
        """One tick over the issue as this fixture last left it."""
        run_options.setdefault("head_shas", [MERGED_HEAD, MERGED_HEAD])
        return self._run_with_merge(
            github, github.get_issue(CONFLICT_ISSUE), **run_options,
        )[0]

    _settled = ResolvingConflictSettledRoundTest._settled


class ConflictAheadCheckoutTest(unittest.TestCase, _ResolvingConflictMixin):
    """A body edit on a checkout that is ahead of its own publication.

    Every publication behind a resume is leased against the head the round
    began at, and on an ahead checkout that head is a local commit the remote
    has never seen. Handed to the size gate as the publication's head it
    disagrees with the pull request, so the resume's own commit is refused as
    somebody else's movement -- and by then the edit that prompted it has been
    consumed, so nothing brings it back and the issue parks for good.

    So the unpublished commit is published first, and the edit waits a tick
    for a branch in sync to be answered against.
    """

    def test_an_ahead_checkout_publishes_first(self) -> None:
        _github, mocks = self._edited_while_ahead()

        mocks[RUN_AGENT].assert_not_called()
        self.assertEqual(
            mocks[PUSH_BRANCH].call_args.kwargs[REVISION], STRANDED_HEAD,
        )

    def test_a_deferred_edit_survives_the_publication(self) -> None:
        # The hash is the whole of what says the body moved, so an edit
        # consumed by a resume that then refuses is an edit nothing detects
        # again.
        reported = self._edited_while_ahead(reporting_baseline=True)
        github, baseline = reported[0], reported[2]

        self.assertEqual(self._pinned(github)[USER_CONTENT_HASH], baseline)

    def _edited_while_ahead(self, *, reporting_baseline: bool = False):
        """One body edit arriving on a checkout with an unpushed commit."""
        github, issue = self._seed()[:2]
        self._seed_with_baseline_hash(github, issue)
        baseline = self._pinned(github)[USER_CONTENT_HASH]
        issue.body = "the requirement moved while the rebase was in flight"
        mocks = self._run_with_merge(
            github, issue,
            head_shas=[STRANDED_HEAD, STRANDED_HEAD],
            candidate_commit=FrozenCommit(sha=STRANDED_HEAD),
            branch_ahead_behind=AHEAD,
            behind_base=ON_BASE,
            push_branch=True,
        )[0]
        return (github, mocks, baseline) if reporting_baseline else (
            github, mocks,
        )


if __name__ == "__main__":
    unittest.main()


class ConflictAheadReplyTest(unittest.TestCase, _ResolvingConflictMixin):
    """A human reply on a park whose checkout is ahead of its publication.

    An agent a timeout parked can leave a clean commit behind, and the whole
    point of the reply is to say what to do about it. Published as recovered
    work instead, that pre-reply commit reaches the reviewer as finished, the
    round is counted, the park is cleared -- and the reply is never fed to the
    developer at all.

    It is safe to resume where the body edit is not, and the difference is the
    head each leases its publication against: this one freezes the pull
    request's OWN head, read before the agent runs, so an unpublished commit
    under it changes nothing -- the resolution goes out carrying it.
    """

    def test_a_reply_outranks_an_unpublished_commit(self) -> None:
        github, mocks = self._replied_while_ahead()

        mocks[RUN_AGENT].assert_called_once()
        self.assertEqual(
            [round_[OUTCOME] for round_ in _rounds_of(github)],
            [AGENT_RESOLVED],
        )

    def test_the_reply_is_what_the_dev_is_resumed_on(self) -> None:
        # An agent running is not the same as the reply reaching it. Dropped
        # into the recovered push instead, the reply is neither fed to
        # anybody nor consumed, and the pre-reply commit ships as finished
        # work.
        mocks = self._replied_while_ahead()[1]

        self.assertIn(HUMAN_REPLY, mocks[RUN_AGENT].call_args.args[1])

    def test_the_resolution_carries_it_out(self) -> None:
        # What the resume publishes is the head it left, which has the
        # unpublished commit under it -- so nothing is stranded by resuming
        # rather than recovering first.
        github, mocks = self._replied_while_ahead()

        self.assertEqual(
            mocks[PUSH_BRANCH].call_args.kwargs[REVISION], RESOLVED_HEAD,
        )
        self.assertFalse(self._pinned(github)[AWAITING_HUMAN])

    def _replied_while_ahead(self):
        """One parked issue with an unpushed commit and a fresh reply.

        Baselined BEFORE the reply lands, which is the only shape production
        ever has: the hash covers the thread as well as the body, so every
        reply moves it and reaches the routing looking like a body edit. A
        fixture that re-baselined afterwards would hand this case to the reply
        road for free and prove nothing about the road it really takes.
        """
        github, issue = self._seed(extra_state={
            AWAITING_HUMAN: True,
            PARK_REASON: AGENT_TIMEOUT,
            LAST_ACTION_COMMENT_ID: CONSUMED_UP_TO,
        })[:2]
        self._seed_with_baseline_hash(github, issue)
        issue.comments.append(FakeComment(
            id=HUMAN_REPLY_ID,
            body=HUMAN_REPLY,
            user=FakeUser(HUMAN_LOGIN),
        ))
        return github, self._run_with_merge(
            github, issue,
            head_shas=[STRANDED_HEAD, RESOLVED_HEAD],
            candidate_commit=FrozenCommit(sha=RESOLVED_HEAD),
            branch_ahead_behind=AHEAD,
            behind_base=ON_BASE,
            push_branch=True,
            run_agent_result=_agent(
                session_id=DEV_SESSION, last_message="resolved",
            ),
        )[0]


if __name__ == "__main__":
    unittest.main()
