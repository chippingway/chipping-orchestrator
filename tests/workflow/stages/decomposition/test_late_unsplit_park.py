# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What an oversized candidate no adjudicator could split waits on.

A `single` verdict is the adjudicator saying this change stays one change, and
that is the one answer it may not act on: the ceiling exists so unreviewed
bulk does not reach a pull request, so publishing past it is a human's call.
The workflow says so and stops.

What these cases pin is the shape of that stop. Nothing is published and
nothing is taken back, so the wait costs the issue one comment and no agent:
the commit, the generation, whichever pull request this cycle held or was
measured against, the session, and the recorded verdict are all exactly where
the adjudication left them, and every later tick reads that verdict rather
than paying for a second one. What the sentence it owes may name, and what a
record an older binary left still gets said, are the module beside this one.
"""
from __future__ import annotations

import unittest
from types import MappingProxyType

from orchestrator.workflow.stages.decomposition.late_models import (
    UNRECORDED_SPLIT_BLOCKER,
    _LateDisposition,
)
from tests.workflow.fixtures import LABEL_DECOMPOSING
from tests.workflow.stages.decomposition import late_test_support as _support
from tests.workflow.stages.decomposition.late_content_support import (
    RefusedComment,
)
from tests.workflow.stages.decomposition.late_published_support import (
    published_generation,
    seed_published_pr,
)
from tests.workflow.stages.decomposition.late_run_support import (
    WorktreeSeed,
    agent_reply,
)
from tests.workflow.stages.decomposition.late_settlement_support import (
    OWNER_GUARD,
    PARK_SINGLE_DECISION,
    SAID_ONCE,
    SINGLE_RUN,
    GuardedLateCase,
    HeldPlanPrCase,
    killed_at,
)

# Every category an adjudicator may land a `single` under, `unsafe_split`
# included: the workflow's answer is the same park for all of them, since what
# decides it is the verdict rather than the reason offered for it.
_CATEGORIES = (
    "generated_artifacts",
    "scope_ambiguous",
    "unsafe_split",
    "unknown_to_this_build",
)

# A verdict an older binary recorded with no explanation beside it, which live
# issues carry: the identities that make it this candidate's answer, and
# nothing under the key this domain later kept. A tick reading it back takes
# the park without an agent, and the notice answers with the stand-in rather
# than paying for a second run to recover the prose.
_UNEXPLAINED_RECORD = MappingProxyType({
    **_support.generation_state(_support.late_generation()),
    _support.KEYS.run_cycle_id: _support.CYCLE_ID,
    _support.KEYS.run_generation: _support.GENERATION_NUMBER,
    _support.KEYS.source_sha: _support.CANDIDATE_SHA,
    _support.KEYS.verdict: "single",
})

# A checkout whose push would be refused. What it turns into an assertion is
# that the road a settlement takes was never entered: a tick that reached the
# push would park as an unreconciled pull request rather than on the decision.
_REFUSED_PUSH = WorktreeSeed(push=False)

# What the generation carries that a decision about this candidate is taken
# against, and therefore what may not be cleared while one is owed.
_KEPT_GENERATION_KEYS = (
    _support.KEYS.candidate_sha,
    _support.KEYS.base_sha,
    _support.KEYS.additions,
    _support.KEYS.threshold,
)

# The publication a verdict taken past the first push was measured against:
# the pull request the work is on, the head it was standing on, and the stage
# the gate took the issue out of. None can be re-derived, and a decision about
# this candidate is taken against all three.
_PUBLICATION_CONTEXT = MappingProxyType({
    _support.KEYS.post_publication: True,
    _support.KEYS.published_pr_number: _support.PUBLISHED_PR_NUMBER,
    _support.KEYS.published_sha: _support.PUBLISHED_HEAD_SHA,
    _support.KEYS.source_stage: _support.PUBLISHED_SOURCE_STAGE,
})

# What the stage that routed this candidate into the gate left behind so its
# own resumed tick can finish what it was in the middle of. The park hands the
# issue to nobody, so nothing of it is spent.
_CALLER_RECOVERY = MappingProxyType({
    "docs_settled_sha": _support.OTHER_SHA,
    "conflict_settled_outcome": "resolved",
    "conflict_settled_sha": _support.OTHER_SHA,
})

# The pinned writes a tick that reuses a recorded answer owes whatever it
# decides: the claim the owner read is entered past, and the drop of that claim
# once the read comes back open. A park already standing adds none.
_READS_OWED_A_WRITE = 2


def _single_run(category: str):
    """One finished run whose `single` lands under the named category."""
    return agent_reply(_support.late_block(
        '{"decision": "single", "rationale": "one coherent change",'
        f' "split_blocker": "{_support.SPLIT_BLOCKER}", "category": "{category}"}}'
    ))


class UnsplittableParkTest(GuardedLateCase, unittest.TestCase):
    """A fresh `single` hands the issue to a human and publishes nothing."""

    def test_it_publishes_nothing_and_parks(self) -> None:
        outcome = self._decide(SINGLE_RUN)

        self.assertEqual(outcome.disposition, _LateDisposition.PARKED)
        pinned = self._pinned()
        self.assertEqual(pinned.get(_support.KEYS.park_reason), PARK_SINGLE_DECISION)
        self.assertTrue(pinned.get(_support.KEYS.awaiting))
        # The four writes a settlement would have made, none of which a
        # verdict alone licenses: the commit is not exempt, no publication is
        # approved, and the issue is not handed to a stage that would push it.
        self.assertNotIn(_support.KEYS.exempt_sha, pinned)
        self.assertNotIn(_support.KEYS.approved_sha, pinned)
        self.assertEqual(self.github.label_history, [])
        self.assertEqual(
            self.github.workflow_label(self.issue), LABEL_DECOMPOSING,
        )

    def test_the_notice_names_what_was_measured(self) -> None:
        # A human deciding whether this may publish unsplit needs the commit
        # they are deciding about, the reading that stopped it, and what the
        # adjudicator said stood in the way -- and the last of those is gone
        # with the run that said it.
        self._decide(SINGLE_RUN)

        said = self.github.posted_comments[-1][1]
        self.assertIn(_support.CANDIDATE_SHA, said)
        self.assertIn(str(_support.ADDITIONS), said)
        self.assertIn(str(_support.THRESHOLD), said)
        self.assertIn(_support.SPLIT_BLOCKER, said)

    def test_an_unexplained_record_says_so(self) -> None:
        # An outcome recorded before this domain kept an explanation is still
        # this candidate's answer, so it is announced with the stand-in
        # rather than re-run to recover prose an agent may not decide the
        # same way twice. What a fresh reply owes is the reply contract's,
        # and no record is held to it.
        self.github.seed_state(self.issue.number, **_UNEXPLAINED_RECORD)

        outcome, spawn = self._adjudicate()

        spawn.assert_not_called()
        self.assertEqual(outcome.disposition, _LateDisposition.PARKED)
        said = self.github.posted_comments[-1][1]
        self.assertIn(UNRECORDED_SPLIT_BLOCKER, said)

    def test_every_category_takes_the_same_road(self) -> None:
        for category in _CATEGORIES:
            with self.subTest(category=category):
                self.setUp()

                outcome = self._decide(_single_run(category))

                self.assertEqual(
                    outcome.disposition, _LateDisposition.PARKED,
                )
                self.assertEqual(
                    self._pinned().get(_support.KEYS.park_reason),
                    PARK_SINGLE_DECISION,
                )

    def test_what_a_decision_is_taken_against_is_kept(self) -> None:
        # The park is a wait, not an ending: everything a human is deciding
        # about has to still be on the record when they answer, and the
        # recorded run is what stops the next tick buying a second verdict.
        self._decide(agent_reply(
            SINGLE_RUN.last_message, session_id=_support.LATE_SESSION_ID,
        ))

        pinned = self._pinned()
        for kept in _KEPT_GENERATION_KEYS:
            with self.subTest(key=kept):
                self.assertIn(kept, pinned)
        self.assertEqual(pinned.get(_support.KEYS.session_id), _support.LATE_SESSION_ID)
        self.assertEqual(pinned.get(_support.KEYS.verdict), "single")
        self.assertEqual(pinned.get(_support.KEYS.split_blocker), _support.SPLIT_BLOCKER)


class StandingParkTest(GuardedLateCase, unittest.TestCase):
    """What every tick after the one that decided owes, and what it costs.

    The park is not one a fresh attempt supersedes, so nothing below is a
    retry of a step that failed: the verdict is already recorded, and each of
    these ticks reads it back, reaches the same park, and either finds it
    already said or says the sentence a dead process never did.
    """

    def test_a_recovered_verdict_pays_nothing(self) -> None:
        # A retry cannot decide differently without an agent, and no agent
        # runs against a candidate this issue has already adjudicated -- so
        # the later ticks reuse the record, find the park they would take
        # already standing, and say nothing.
        self._decide(SINGLE_RUN)

        first, second = self._adjudicate(), self._adjudicate()

        for outcome, spawn in (first, second):
            spawn.assert_not_called()
            self.assertEqual(outcome.disposition, _LateDisposition.PARKED)
        self.assertEqual(
            self._pinned().get(_support.KEYS.park_reason), PARK_SINGLE_DECISION,
        )
        self.assertEqual(len(self.github.posted_comments), SAID_ONCE)

    def test_a_standing_park_is_not_rewritten(self) -> None:
        # An issue waiting on a human waits for as long as the human takes,
        # so re-writing the same claim would spend a pinned write per poll on
        # a record nothing has changed.
        self._decide(SINGLE_RUN)
        settled = self.github.write_state_calls

        self._adjudicate()

        self.assertEqual(
            self.github.write_state_calls - settled, _READS_OWED_A_WRITE,
        )

    def test_a_refused_notice_is_said_later(self) -> None:
        # The durable half goes first, so a comment GitHub refuses leaves a
        # park standing over a thread that was told nothing -- and no later
        # attempt re-takes this one to say it. The obligation it recorded is
        # what brings the sentence back, once.
        with RefusedComment(self.github), self.assertRaises(RuntimeError):
            self._decide(SINGLE_RUN)
        self.assertEqual(self.github.posted_comments, [])

        self._adjudicate()
        self._adjudicate()

        said = [body for _number, body in self.github.posted_comments]
        self.assertEqual(len(said), SAID_ONCE)
        self.assertIn(_support.SPLIT_BLOCKER, said[0])

    def test_a_dead_tick_leaves_the_park(self) -> None:
        # The verdict is durable before the owner read, so a process that dies
        # in between costs the park and not the run: the next one reads the
        # answer back, takes the park, and says it once.
        with killed_at(OWNER_GUARD), self.assertRaises(KeyboardInterrupt):
            self._decide(SINGLE_RUN)

        outcome, spawn = self._adjudicate()

        spawn.assert_not_called()
        self.assertEqual(outcome.disposition, _LateDisposition.PARKED)
        self.assertEqual(
            self._pinned().get(_support.KEYS.park_reason), PARK_SINGLE_DECISION,
        )
        self.assertEqual(len(self.github.posted_comments), SAID_ONCE)


class PublishedCandidateParkTest(GuardedLateCase, unittest.TestCase):
    """A verdict taken over a pull request the remote already carries.

    The road a settlement would push on, and so the one where a park has the
    most to leave alone: the record names the pull request the work is on and
    the head the reading was taken over, the stage the gate took the issue out
    of is the one a settlement would hand it back to, and the caller that
    routed it here left its own resumption on the record beside them. A
    decision is taken against every one of those, so none is this park's to
    spend.
    """

    def setUp(self) -> None:
        super().setUp()
        seed_published_pr(self.github)
        self.github.seed_state(
            self.issue.number,
            **_support.generation_state(published_generation()),
            **_CALLER_RECOVERY,
        )

    def test_a_fresh_verdict_publishes_nothing(self) -> None:
        outcome = self._decide(SINGLE_RUN, worktree=_REFUSED_PUSH)

        self._assert_left_alone(outcome)

    def test_a_recovered_verdict_publishes_nothing(self) -> None:
        self._decide(SINGLE_RUN, worktree=_REFUSED_PUSH)

        outcome, spawn = self._adjudicate(worktree=_REFUSED_PUSH)

        spawn.assert_not_called()
        self._assert_left_alone(outcome)

    def _assert_left_alone(self, outcome) -> None:
        """Parked on the decision, with nothing published and nothing spent."""
        self.assertEqual(outcome.disposition, _LateDisposition.PARKED)
        self._assert_published_nothing()
        self._assert_kept_the_record()

    def _assert_published_nothing(self) -> None:
        """No exemption, no approval, no push, and no stage handed the issue.

        The refused push is what makes "nothing was pushed" an assertion
        rather than an absence: a tick that reached the push would meet that
        refusal and park as an unreconciled pull request instead.
        """
        pinned = self._pinned()
        self.assertEqual(pinned.get(_support.KEYS.park_reason), PARK_SINGLE_DECISION)
        self.assertNotIn(_support.KEYS.exempt_sha, pinned)
        self.assertNotIn(_support.KEYS.approved_sha, pinned)
        self.assertNotIn(_support.KEYS.approved_lease, pinned)
        self.assertEqual(self.github.label_history, [])
        self.assertEqual(
            self.github.get_pr(_support.PUBLISHED_PR_NUMBER).head.sha,
            _support.PUBLISHED_HEAD_SHA,
        )

    def _assert_kept_the_record(self) -> None:
        """Everything a decision about this candidate would be taken against."""
        pinned = self._pinned()
        self.assertEqual(
            self.github.workflow_label(self.issue), LABEL_DECOMPOSING,
        )
        for kept, standing in {
            **_PUBLICATION_CONTEXT, **_CALLER_RECOVERY,
        }.items():
            with self.subTest(key=kept):
                self.assertEqual(pinned.get(kept), standing)


class HeldPullRequestParkTest(HeldPlanPrCase, unittest.TestCase):
    """The pull request the candidate stands on keeps what the hold put on it.

    A hold is what stops a human merging an oversized change while the question
    of whether it should exist as one is open, and the park is exactly that
    question still being open. Releasing it here would leave the change
    mergeable with nothing on it saying anybody is deciding.
    """

    def test_the_hold_is_not_released(self) -> None:
        self._decide(SINGLE_RUN)

        self.assertIn(_support.HOLD_MARKER_PREFIX, self.plan_pr.body)
        self.assertEqual(self.github.edited_pr_bodies, [])
        self.assertEqual(
            self._pinned().get(_support.KEYS.plan_pr_number), self.plan_pr.number,
        )


if __name__ == "__main__":
    unittest.main()
