# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""One finish of a landed base rewrite, whichever road reached it, said once and routed by its base lag.

Every road is driven through the finalizer itself and read back off the client:
the publication of a rebase this tick made, a recovery that pushed the replay
again or found it already standing, and a finish whose announcement an earlier
tick already made -- each announcing at most once, retiring the whole attempt,
and routing to `workflow:validating` only where the base has not advanced past
the landed head. A landing the record does not account for, a finish already
made, and a caller's writer claim held across it are the edges around them.
"""
from __future__ import annotations

import unittest
from dataclasses import replace
from functools import partial
from types import MappingProxyType

from orchestrator.git.base_sync.rewrite_handoffs import _PushOutcome, _RewriteRefusal
from orchestrator.scheduler import writer_claims
from orchestrator.workflow.engine.rewrite_finish_models import FinishOutcome
from tests.workflow.engine import rewrite_finish_effects_support as effects, rewrite_finish_test_support as support
from tests.workflow.interleaving import _RacesTheStep

_PUBLISHED = (
    ":mag: PR was 2 commit(s) behind `origin/main`; orchestrator auto-rebased the branch and "
    "re-pushed it. Routing `workflow:fixing` -> `workflow:validating` so the reviewer re-runs "
    "against the new head (`b2b2b2b2`)."
)

_PUSHED = ":mag: Recovered an interrupted auto-rebase for PR #42; pushed the recovered head `b2b2b2b2`."

_FOUND = (
    ":mag: Recovered an interrupted auto-rebase for PR #42; the new head `b2b2b2b2` was already "
    "published before the orchestrator restart."
)

_ADVANCED = (
    " Base advanced again by 2 commit(s) since the interrupted rebase; rebasing once more before "
    "routing to `workflow:validating`."
)

_TO_REVIEW = " Routing `workflow:fixing` -> `workflow:validating`"

_FOUND_TO_REVIEW = f"{_FOUND}{_TO_REVIEW} so the reviewer re-runs against the rewritten branch."

_ROUTED = (support.LABEL_VALIDATING,)

# The method a landing this tick sent nothing for is filed under.
_FOUND_METHOD = "crash_recovery_relabel_only"

# A recovered push whose answer was lost, and the remote then read on the replay.
_PUSHED_UNANSWERED = replace(support.PUSHED_AGAIN, outcome=_PushOutcome.UNCERTAIN)

# A recovered push whose answer was lost, and the remote then not read at all.
_PUSH_UNRESOLVED = replace(_PUSHED_UNANSWERED, remote=None)

# A recovery whose publication was refused because the remote already stood on
# the replay: nothing was sent, so it is a push an earlier tick made.
_ALREADY_STANDING = replace(
    support.PUSHED_AGAIN, outcome=_PushOutcome.REFUSED, refusal=_RewriteRefusal.PUBLISHED,
)

# The publication of this tick's own rebase, refused the same way.
_PUBLISHED_STANDING = replace(_ALREADY_STANDING, road=support.PUBLISHED.road)

# Whether each landing counts as this tick's own push: only one the remote was
# shown standing on does.
_SENT = (
    (support.PUSHED_AGAIN, True),
    (_PUSHED_UNANSWERED, True),
    (_PUSH_UNRESOLVED, False),
    (support.FOUND, False),
    (_ALREADY_STANDING, False),
    (_PUBLISHED_STANDING, False),
)

# Each recovery a later tick finishes: the road it took, the notice that says
# what it found, the method its event files, what it came to, and the labels
# it wrote.
_RECOVERIES = (
    (support.PUSHED_AGAIN, f"{_PUSHED}{_TO_REVIEW}.", "crash_recovery_pushed", FinishOutcome.ROUTED, _ROUTED),
    (_PUSHED_UNANSWERED, f"{_PUSHED}{_TO_REVIEW}.", "crash_recovery_pushed", FinishOutcome.ROUTED, _ROUTED),
    (
        replace(support.PUSHED_AGAIN, behind=2), f"{_PUSHED}{_ADVANCED}",
        "crash_recovery_pushed", FinishOutcome.CONTINUED, (),
    ),
    (support.FOUND, _FOUND_TO_REVIEW, _FOUND_METHOD, FinishOutcome.ROUTED, _ROUTED),
    (_ALREADY_STANDING, _FOUND_TO_REVIEW, _FOUND_METHOD, FinishOutcome.ROUTED, _ROUTED),
    (
        replace(support.FOUND, behind=2), f"{_FOUND}{_ADVANCED}",
        _FOUND_METHOD, FinishOutcome.CONTINUED, (),
    ),
)

# The attempt as a finish leaves it: every member blanked rather than removed.
_RETIRED = MappingProxyType(dict.fromkeys(support.ATTEMPT_KEYS))

# A publication whose push the remote was not shown standing on.
_UNSHOWN = replace(support.PUBLISHED, remote=support.ANCHOR)

# A rebase that replayed nothing, which the transport refuses with the remote
# still on the anchor -- and the same unmoved head as a recovery observes it.
_UNMOVED = replace(
    _UNSHOWN, outcome=_PushOutcome.REFUSED, head=support.ANCHOR, refusal=_RewriteRefusal.UNMOVED,
)
_UNMOVED_OBSERVED = replace(support.FOUND, remote=support.ANCHOR, head=support.ANCHOR)

# A publication a guard refused over a dirty tree while the remote, from an
# earlier push, already stood on the replay.
_REFUSED_DIRTY = replace(support.PUBLISHED, outcome=_PushOutcome.REFUSED, refusal=_RewriteRefusal.DIRTY_TREE)

# An attempt record from before the attempt's terms and replay were recorded.
_UNRECORDED = MappingProxyType({
    support.KEY_REWRITE_PR: None, support.KEY_REWRITE_STAGE: None, support.KEY_REWRITE_SHA: None,
})

# Each landing the pinned record does not account for: what it pins, and the road that reached it.
_UNACCOUNTED = (
    ("the remote is not on the replay", {}, _UNSHOWN),
    ("a lost answer the remote could not be read after", {}, _PUSH_UNRESOLVED),
    ("the rewrite moved nothing", {}, _UNMOVED),
    ("a recovery observes a head that moved nothing", {}, _UNMOVED_OBSERVED),
    ("a guard refused its publication", {}, _REFUSED_DIRTY),
    ("the attempt recorded another replay", {support.KEY_REWRITE_SHA: support.OTHER}, support.FOUND),
    ("the attempt's replay record is damaged", {support.KEY_REWRITE_SHA: "not-a-commit"}, support.FOUND),
    ("the attempt was made for another pull request", {support.KEY_REWRITE_PR: 43}, support.FOUND),
    ("the attempt was made from another stage", {support.KEY_REWRITE_STAGE: "workflow:in_review"}, support.FOUND),
    ("the attempt recorded no replay", _UNRECORDED, support.FOUND),
    ("its lag against the base was not counted", {}, replace(support.FOUND, behind=None)),
    ("no anchor is pinned", {support.KEY_PENDING_PUSH: None}, support.PUBLISHED),
    ("the anchor is another head", {support.KEY_PENDING_PUSH: support.OTHER}, support.PUBLISHED),
    ("the issue pins another pull request", {support.KEY_PR: 43}, support.PUBLISHED),
    ("a mark names another head", {support.KEY_ANNOUNCED: support.OTHER}, support.FOUND),
)


def _contends(github, contended: list[bool]) -> None:
    """Another writer of issue #7 asking for its claim; whether it got it, appended to `contended`."""
    with writer_claims.issue_writer(github.repo_id, support.ISSUE) as held:
        contended.append(held)


class PublishedFinishTest(unittest.TestCase):
    """The tick that published its own rebase announces it, makes its debt durable, and routes it to review."""

    def test_a_publication_is_announced_and_routed(self) -> None:
        world = support.FinishWorld.seeded()
        relabel = effects.DurableAtTheRelabel(world)

        self.assertEqual(world.finalizes(), FinishOutcome.ROUTED)

        self.assertEqual(
            world.said(), ([effects.posted(_PUBLISHED)], [effects.rebased("auto_clean_rebase")]),
        )
        self.assertEqual(world.relabels(), _ROUTED)
        # The debt and the mark are durable beside the anchor when the issue is
        # routed, so a process lost in the relabel comes back to a finish that
        # says it announced itself and owes only its route.
        self.assertEqual(
            [support.checkpoint(seen) for seen in relabel.seen],
            [(support.owed(), support.LANDED, support.ANCHOR, 0)],
        )
        durable = world.pinned()
        self.assertEqual(
            (
                support.attempt(durable), durable[support.KEY_REVIEW_ROUND],
                durable[support.KEY_REWRITE_DEBT], len(durable[support.KEY_LEDGER]),
            ),
            (_RETIRED, 0, support.owed(), 1),
        )
        # The announcement and the retirement, and no other write.
        self.assertEqual(world.github.write_state_calls, 2)


    def test_a_publication_found_standing_says_so(self) -> None:
        # Refused because the remote already stood on the replay, this tick
        # pushed nothing: the landing is announced as one already published.
        world = support.FinishWorld.seeded()

        self.assertEqual(world.finalizes(_PUBLISHED_STANDING), FinishOutcome.ROUTED)

        self.assertEqual(
            world.said(),
            ([effects.posted(_FOUND_TO_REVIEW)], [effects.rebased(_FOUND_METHOD)]),
        )
        self.assertEqual(world.relabels(), _ROUTED)


class RecoveredFinishTest(unittest.TestCase):
    """A later tick finishes a landing an interrupted one left, spending the reply that brought it back."""

    def test_a_recovery_says_what_it_found(self) -> None:
        for road, notice, method, finished, relabelled in _RECOVERIES:
            with self.subTest(outcome=road.outcome.value, refusal=road.refusal, behind=road.behind):
                self.assertEqual(
                    self._recovers(road),
                    (
                        finished,
                        ([effects.posted(notice)], [effects.rebased(method)]),
                        relabelled,
                        _RETIRED,
                        (support.owed(), 0, True, False, None),
                    ),
                )

    def test_only_a_push_seen_landed_counts(self) -> None:
        world = support.FinishWorld.seeded()
        for road, sent in _SENT:
            with self.subTest(road=road):
                self.assertEqual(world.finish(road).pushed, sent)

    def _recovers(self, road: support.Road) -> tuple:
        """Finish `road` over an attempt a debt park held and a reply brought back; what it left."""
        world = support.FinishWorld.seeded(**{
            support.KEY_AWAITING_HUMAN: True,
            support.KEY_PARK_REASON: support.PARK_UNRECORDED_DEBT,
        })
        reply = effects.replies(world)
        outcome = world.finalizes(replace(road, retry=reply))
        durable = world.pinned()
        spent = (
            durable[support.KEY_REWRITE_DEBT],
            durable[support.KEY_REVIEW_ROUND],
            durable[support.KEY_WATERMARK] == reply,
            durable[support.KEY_AWAITING_HUMAN],
            durable[support.KEY_PARK_REASON],
        )
        return outcome, world.said(), world.relabels(), support.attempt(durable), spent


class AnnouncedFinishTest(unittest.TestCase):
    """A finish whose mark already names the landed head says nothing again and owes only its route."""

    def test_an_announced_finish_says_nothing_again(self) -> None:
        # A label the issue already wears is not written again.
        for label, relabelled in ((support.LABEL_FIXING, _ROUTED), (support.LABEL_VALIDATING, ())):
            with self.subTest(label=label):
                world = support.FinishWorld.seeded(label=label, **{
                    support.KEY_ANNOUNCED: support.LANDED,
                    support.KEY_REWRITE_DEBT: support.owed(),
                })

                self.assertEqual(world.finalizes(support.FOUND), FinishOutcome.ROUTED)

                self.assertEqual(
                    (world.said(), world.relabels(), support.attempt(world.pinned())),
                    (([], []), relabelled, _RETIRED),
                )
                self.assertEqual(world.github.write_state_calls, 1)

    def test_an_earlier_marks_debt_precedes_its_route(self) -> None:
        # A mark an earlier build wrote with no debt beside it: the claim is
        # new, so it is made durable while the anchor stands, ahead of the
        # relabel, and nothing is said again.
        world = support.FinishWorld.seeded(**{support.KEY_ANNOUNCED: support.LANDED})
        relabel = effects.DurableAtTheRelabel(world)

        self.assertEqual(world.finalizes(support.FOUND), FinishOutcome.ROUTED)

        self.assertEqual(world.said(), ([], []))
        self.assertEqual(
            [support.checkpoint(seen) for seen in relabel.seen],
            [(support.owed(), support.LANDED, support.ANCHOR, support.SPENT_ROUND)],
        )
        self.assertEqual(world.pinned()[support.KEY_REWRITE_DEBT], support.owed())


class UnaccountedLandingTest(unittest.TestCase):
    """A landing the pinned record does not account for, or one already finished, is finished by nobody."""

    def test_an_unaccounted_landing_makes_nothing(self) -> None:
        for case, pinned, road in _UNACCOUNTED:
            with self.subTest(case):
                world = support.FinishWorld.seeded(**pinned)

                self.assertEqual(world.finalizes(road), FinishOutcome.UNFINISHABLE)

                untouched = (support.attempt_record(**pinned), ([], []), (), 0)
                self.assertEqual(self._left(world), untouched)

    def test_an_in_flight_record_is_finished(self) -> None:
        # Terms recorded and no head yet is the window between the rebase
        # returning and its record of what it produced: no contradiction, and
        # vouching for that landing is the caller's before it hands it over.
        world = support.FinishWorld.seeded(**{support.KEY_REWRITE_SHA: None})

        self.assertEqual(world.finalizes(support.FOUND), FinishOutcome.ROUTED)

        self.assertEqual(support.attempt(world.pinned()), _RETIRED)

    def test_a_finished_landing_is_not_finished_again(self) -> None:
        world = support.FinishWorld.seeded()
        self.assertEqual(world.finalizes(), FinishOutcome.ROUTED)
        finished = self._left(world)

        for road in (support.PUBLISHED, support.FOUND):
            with self.subTest(road=road.road.value):
                self.assertEqual(world.finalizes(road), FinishOutcome.UNFINISHABLE)
                self.assertEqual(self._left(world), finished)

    def _left(self, world: support.FinishWorld) -> tuple:
        """What issue #7 was left with: its record, what was said, its labels, and how many pinned writes."""
        return world.pinned(), world.said(), world.relabels(), world.github.write_state_calls


class CallersClaimTest(unittest.TestCase):
    """The finish runs under the writer claim its caller holds, and asks for none of its own."""

    def test_the_callers_claim_covers_the_finish(self) -> None:
        world = support.FinishWorld.seeded()
        contended: list[bool] = []
        world.github.set_workflow_label = _RacesTheStep(
            world.github.set_workflow_label, partial(_contends, world.github, contended),
        )

        with writer_claims.issue_writer(world.github.repo_id, support.ISSUE) as held:
            self.assertTrue(held)
            outcome = world.finalizes()

        # Held across the whole finish: another writer asking as the route is
        # relabelled is refused, and the finish needed no claim of its own.
        self.assertEqual((outcome, contended), (FinishOutcome.ROUTED, [False]))
        self.assertEqual(world.relabels(), _ROUTED)


if __name__ == "__main__":
    unittest.main()
