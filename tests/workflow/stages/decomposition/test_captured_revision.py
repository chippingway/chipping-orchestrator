# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""A late revision's held report, finished by the dispatcher's recovery with no developer run.

Each case holds a revision's run under an operator's control as it finishes on
a report, takes the control off, and dispatches the issue whole, as a poll
does, reading back what the recovery left: the candidate re-measured, the
guidance consumed, and the report handed to the delivery once -- or, where the
world moved under the capture, nothing of it at all. What the next dispatch
does over the record left is read too, so a finished capture is never a second
revision or a second report.
"""
from __future__ import annotations

import itertools
from functools import partial
from types import MappingProxyType
from unittest.mock import MagicMock, patch

from orchestrator.git.measurement.models import AdditionMeasurement
from orchestrator.workflow.stages.decomposition.late_result_models import _LateDisposition
from tests.workflow.stages.decomposition import (
    captured_revision_moves as _moves,
    captured_revision_support as _captured,
    late_content_replies as _content_replies,
    late_content_support as _support,
    late_published_support as _published,
    late_revision_support as _stage_support,
)
from tests.workflow.stages.decomposition.late_run_support import WorktreeSeed
from tests.workflow.stages.decomposition.late_test_support import (
    ADDITIONS,
    CANDIDATE_SHA,
    GENERATION_NUMBER,
    KEYS,
    NEXT_GENERATION,
    PUBLISHED_BRANCH,
    PUBLISHED_HEAD_SHA,
    PUBLISHED_PR_NUMBER,
)

# What a finished revision settles, none of which a retired one may: its
# consumption of the guidance, and its report's delivery.
_UNSETTLED = (_support.KEY_COMMENT_WATERMARK, _captured.DELIVERED)

# The room somebody leaves on the pinned comment: too little for the
# capture's transfer and the reconciliation riding it.
_SPARE = 100

# The route bookkeeping a hold on the pair owes, as its writers spell it.
_SPENDS = "late_spends"

# Hand edits another road or an operator makes while the capture waits: the
# generation advanced, a reply made owed a whole quote the run was never
# handed, and a handoff the pair now owes.
_ADVANCED = MappingProxyType({_support.KEY_GENERATION: NEXT_GENERATION})
_NEWLY_OWED = MappingProxyType({_captured.OWED_REPLIES: [_content_replies.GUIDANCE_ID]})
_NEW_HANDOFF = MappingProxyType({_SPENDS: [["review_round", 2]]})

# A split child somebody records, and where the split's register of its
# children lives.
_CHILD = 99
_SPLIT_CHILDREN = "late_split_children"

# The obligations a split records taking on outside, as their writers spell
# them: a child it created, a branch it pushed, and an issue waiting on it.
_NEW_CHILD = MappingProxyType({_SPLIT_CHILDREN: [_CHILD]})
_NEW_RESOURCE = MappingProxyType({"late_resources": [{"kind": "branch", "target": "split/one", "state": "pending"}]})
_NEW_CONSUMER = MappingProxyType({"late_consumers": [_CHILD]})

# The obligations a retired capture leaves exactly as it found them.
_OBLIGATIONS = (_captured.OWED_REPLIES, _SPENDS, *_NEW_CHILD, *_NEW_RESOURCE, *_NEW_CONSUMER)

# A post-publication generation's revised candidate, which the pull request it
# was entered on does not stand on yet, measured oversized; and a head that
# pull request was pushed to by nothing of this issue's.
_PUBLISHED_REVISION = WorktreeSeed(head="cccccccccccccccccccccccccccccccccccccccc")
_PUBLISHED_MEASURED = AdditionMeasurement(
    candidate_sha=_PUBLISHED_REVISION.head, base_sha=_support.REVISED_BASE_SHA, additions=ADDITIONS,
)
_ELSEWHERE = "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"

# What GitHub answers a fetch it refuses with.
_UNANSWERED = "GitHub did not answer the issue read"

# A head a checkout moved to after a revision's report was captured.
_MOVED_HEAD = "ffffffffffffffffffffffffffffffffffffffff"

# The two checkouts a recovery reconciles: one it parks over, and one it
# re-measures and hands on.
_DIRTY = WorktreeSeed(head=_support.REVISED_SHA, dirty=_stage_support.DIRTY_TREE)
_CLEAN = WorktreeSeed(head=_support.REVISED_SHA)


class CapturedRevisionRecoveryTest(_captured.CapturedRevisionCase):
    """A held revision is finished once, by the dispatch that reads it after the control comes off."""

    def test_a_recovery_finishes_it_once(self) -> None:
        # Once the control comes off, the dispatch finishes the capture with
        # no developer run: the candidate re-frozen and re-measured, the
        # guidance consumed, the park answered, and the report handed to the
        # delivery for that candidate -- and the next dispatch, reading all
        # of it back, buys the adjudication that generation is owed rather
        # than a second revision. A candidate adjudicated before publication
        # whose pinned pull request is still the discussion's plan is
        # finished the same way: that pull request is none of the run's.
        for control, planned in zip(_captured.CONTROLS, (False, True), strict=True):
            with self.subTest(control=control, planned=planned):
                self._guided(planned=planned)
                self._held(control)
                self._released(control)

                self._dispatched().assert_not_called()

                generation = _captured.finished(self, _support.REVISED_SHA)[_support.KEY_GENERATION]
                remeasured = [body for body in self._bodies() if _stage_support.REMEASURED_NOTICE in body]
                self.assertEqual(len(remeasured), 1)
                self._dispatched().assert_called_once()
                self.assertEqual(self._pinned()[_support.KEY_GENERATION], generation)
                self.assertEqual(self._developer_runs(), 1)

    def test_a_lost_handoff_lands_once(self) -> None:
        # The process lost as the handoff went out leaves the capture to the
        # next dispatch's recovery; the handoff landed with its answer lost
        # leaves everything it carried on the comment, the owed reply it
        # repaid dropped in that very commit. Either way the guidance is
        # consumed, the reply repaid, the generation advanced, and the report
        # recorded exactly once -- and the dispatch behind it, reading that
        # back, buys the adjudication the advanced generation is owed: no
        # second revision, generation, or report.
        for lost, recovered in _captured.LOST_HANDOFFS:
            with self.subTest(lost=lost):
                self._seed_drifted()
                self._hand_edit(**{_captured.OWED_REPLIES: [self.guidance.id]})
                with self._lost_at_the_handoff(lost):
                    self._revise(_captured.DEV_REPORT, measurement=_stage_support.REMEASURED_OVERSIZED)
                if recovered:
                    self._dispatched().assert_not_called()

                delivered = _captured.finished(self, _support.REVISED_SHA)[_captured.DELIVERED]
                self._dispatched().assert_called_once()

                pinned = self._pinned()
                self.assertEqual(pinned[_support.KEY_GENERATION], NEXT_GENERATION)
                self.assertEqual(pinned[_captured.DELIVERED], delivered)
                self.assertEqual(self._developer_runs(), 1)

    def test_a_world_moved_under_it_retires_it(self) -> None:
        # Superseding guidance, a generation another road advanced, a reply
        # an operator made owed a whole quote the run was never handed, a
        # handoff the pair now owes, an obligation a split recorded taking on
        # since the launch, and a checkout moved off the commit reported on
        # each prove the held report no longer the answer: it is
        # retired, nothing it was handed is consumed or repaid, every
        # obligation the move left stands, and no developer runs over it.
        for name, moved in (
            ("superseding guidance", self._superseded),
            ("an advanced generation", partial(self._hand_edit, **_ADVANCED)),
            ("a newly owed reply", partial(self._hand_edit, **_NEWLY_OWED)),
            ("a changed pending handoff", partial(self._hand_edit, **_NEW_HANDOFF)),
            ("a split child recorded", partial(self._hand_edit, **_NEW_CHILD)),
            ("a split resource recorded", partial(self._hand_edit, **_NEW_RESOURCE)),
            ("a consumer recorded", partial(self._hand_edit, **_NEW_CONSUMER)),
            ("a moved checkout", self._moved_off),
        ):
            with self.subTest(name):
                self._seed_drifted()
                self._held()
                self._released()
                seed = moved()
                owed = {field: self._pinned().get(field) for field in _OBLIGATIONS}

                self._dispatched(seed=seed).assert_not_called()

                pinned = self._pinned()
                self.assertEqual(_captured.capture_of(pinned).stage, _captured.RETIRED)
                self.assertEqual([field for field in _UNSETTLED if field in pinned], [])
                self.assertEqual({field: pinned.get(field) for field in _OBLIGATIONS}, owed)
                self.assertEqual(self._developer_runs(), 1)

    def test_a_child_added_while_measuring_holds_it(self) -> None:
        # A split child recorded while the recovery measures the candidate
        # moves a record the handoff was frozen over: the commit handing the
        # report on is refused, the generation where it stood and the capture
        # pending. The next dispatch retires that capture, and the one after
        # it parks over the child, with no developer run.
        self._seed_drifted()
        self._held()
        self._released()
        measured = _moves.MeasuredWhile(self._hand_edit, **{_SPLIT_CHILDREN: [_CHILD]})

        self._dispatched(alongside=measured.patched()).assert_not_called()

        held = self._pinned()
        self.assertEqual(
            (held[_support.KEY_GENERATION], held[_SPLIT_CHILDREN], _captured.capture_of(held).stage),
            (GENERATION_NUMBER, [_CHILD], _captured.PENDING),
        )
        self._dispatched().assert_not_called()
        self._dispatched().assert_not_called()
        parked = self._pinned()
        self.assertEqual(
            (parked[KEYS.park_reason], _captured.capture_of(parked).stage, _captured.DELIVERED in parked),
            (_support.PARK_REVISION_UNANSWERED, _captured.RETIRED, False),
        )

    def _guided(self, *, planned: bool) -> None:
        """A drift park answered with guidance, over the discussion's plan pull request where `planned`."""
        if not planned:
            self._seed_drifted()
            return
        self._seed_with_plan_pr(**_support.DRIFT_PARKED, **_stage_support.DEV_PIN)
        self.issue.title = _support.EDITED_TITLE
        self.guidance = _content_replies.reply(self.issue)

    def _superseded(self) -> None:
        """A human writes more guidance while the capture waits."""
        _content_replies.reply(self.issue, _support.OTHER_GUIDANCE)

    def _moved_off(self) -> WorktreeSeed:
        """The checkout put back on the candidate the revision started from."""
        return WorktreeSeed(head=CANDIDATE_SHA)


class CapturedRevisionRoomTest(_captured.CapturedRevisionCase):
    """A held revision whose report the comment has no room to hand on is kept, never discarded."""

    def test_a_full_comment_keeps_it_for_room(self) -> None:
        # The transfer the recovery makes is refused for room, so nothing of
        # the reconciliation is written either: the capture stays pending,
        # the guidance unread, the generation and the park where they stood.
        # Every dispatch asks again, and the one after room is freed finishes
        # it once, with no developer run.
        self._held_over_a_full_comment()
        for held in ("first", "second"):
            with self.subTest(held=held):
                self._dispatched().assert_not_called()
                self._kept()
        self._filled(0)

        self._dispatched().assert_not_called()

        _captured.finished(self, _support.REVISED_SHA)
        self.assertEqual(self._developer_runs(), 1)

    def _held_over_a_full_comment(self) -> None:
        """A revision held to its capture, the control taken off, and the comment filled to `_SPARE` characters."""
        self._seed_drifted()
        self._held()
        self._released()
        self._filled(_SPARE)

    def _kept(self) -> None:
        """Assert the capture is still pending and nothing of the revision it holds was written."""
        pinned = self._pinned()
        self.assertEqual(_captured.capture_of(pinned).stage, _captured.PENDING)
        self.assertEqual(pinned[_support.KEY_GENERATION], GENERATION_NUMBER)
        self.assertEqual([field for field in _UNSETTLED if field in pinned], [])
        self.assertEqual(pinned[KEYS.park_reason], _support.PARK_CONTENT_DRIFT)


class CapturedRevisionHoldTest(_captured.CapturedRevisionCase):
    """A hold an operator applies while the recovery works writes nothing of the revision it was finishing."""

    def test_a_hold_mid_recovery_writes_nothing(self) -> None:
        # Applied as the recovery reads the checkout -- behind every reading
        # of the thread it took and ahead of every write -- either control
        # stops the park the reconciliation would write over a dirty tree,
        # and the guidance it would consume with it, as surely as the handoff
        # it would make over a clean one: the record stays exactly as the
        # dispatch found it, the capture pending. Once the control comes off,
        # the next dispatch finishes the capture, with no developer run.
        for control, seed in itertools.product(_captured.CONTROLS, (_DIRTY, _CLEAN)):
            with self.subTest(control=control, dirty=bool(seed.dirty)):
                before = self._held_and_released()

                self._dispatched(seed=seed, applied=control).assert_not_called()

                self.assertEqual(self._pinned(), before)
                self._released(control)
                self._dispatched(seed=seed).assert_not_called()
                self._finished_over(seed)

    def test_a_hold_in_the_park_walk_writes_nothing(self) -> None:
        # Applied as the park's own write walks to the comment -- behind the
        # fresh reading its guarded commit took, and behind every reading of
        # the recovery -- either control stops that park, and the guidance it
        # would consume with it: the strict edit asks the recovery's question
        # behind that walk. The record stays exactly as the dispatch found
        # it, the capture pending, for the next dispatch to finish.
        for control in _captured.CONTROLS:
            with self.subTest(control=control):
                before = self._held_and_released()

                with _moves.AppliedInTheWalk(self, control).patched():
                    self._dispatched(seed=_DIRTY).assert_not_called()

                self.assertEqual(self._pinned(), before)
                self._released(control)
                self._dispatched(seed=_DIRTY).assert_not_called()
                self._finished_over(_DIRTY)

    def test_a_hold_behind_the_handoff_says_nothing(self) -> None:
        # Applied as the recovery reads the owner again behind the commit that
        # handed the report on, either control keeps everything that read
        # would write and say off the issue: the owed read stays claimed and
        # the re-measured candidate's notice unsaid. Once the control comes
        # off, the next dispatch takes that read, with no developer run.
        for control in _captured.CONTROLS:
            with self.subTest(control=control):
                self._held_and_released()
                applied = _moves.BehindTheHandoff(self, _moves.applying(self, control))

                with applied.fetched():
                    self._dispatched().assert_not_called()

                self.assertEqual(self._pinned(), applied.record)
                self.assertEqual(self._bodies()[applied.said:], [])
                self.assertTrue(applied.record[KEYS.owner_check_pending])
                self._released(control)
                self._dispatched()
                self.assertFalse(self._pinned().get(KEYS.owner_check_pending))
                self._finished_over(_CLEAN)

    def test_a_hold_after_the_handoff_writes_nothing(self) -> None:
        # Applied right behind the commit that hands the report on, ahead of
        # the owner read's claim, either control stops every write behind
        # that commit: each is a guarded commit whose strict edit asks the
        # issue's controls again, so the record stays as the handoff left it.
        # Applied right behind the owner read's settlement instead, it keeps
        # the re-measured candidate's notice unsaid, the issue fetched once
        # more ahead of it, and the write behind that notice unmade.
        for control, settled in itertools.product(_captured.CONTROLS, (False, True)):
            with self.subTest(control=control, settled=settled):
                self._held_and_released()
                applied = _moves.BehindTheHandoff(self, _moves.applying(self, control))

                with applied.landed(settled=settled):
                    self._dispatched().assert_not_called()

                self.assertEqual(self._pinned(), applied.record)
                self.assertEqual(self._bodies()[applied.said:], [])
                self._released(control)

    def test_a_hold_in_the_last_read_writes_nothing(self) -> None:
        # Applied as the recovery's question reads the comment once more --
        # the last of its readings of the comment, behind the admission's own
        # requests -- either control is read behind it when the question asks
        # the admission again, and holds the handoff: the record stays as the
        # dispatch found it, the capture pending.
        for control in _captured.CONTROLS:
            with self.subTest(control=control):
                before = self._held_and_released()
                applied = _moves.InTheLastRead(self, _moves.applying(self, control))

                with applied.patched():
                    self._dispatched().assert_not_called()

                self.assertTrue(applied.done)
                self.assertEqual(self._pinned(), before)
                self._released(control)

    def _held_and_released(self) -> dict:
        """A revision held to its capture with the control taken off again; the record it left."""
        self._seed_drifted()
        self._held()
        self._released()
        return self._pinned()

    def _finished_over(self, seed: WorktreeSeed) -> None:
        """Assert the capture was decided once over `seed`: its guidance consumed and itself no longer pending."""
        pinned = self._pinned()
        self.assertNotEqual(_captured.capture_of(pinned).stage, _captured.PENDING)
        self.assertEqual(pinned[_support.KEY_COMMENT_WATERMARK], self.guidance.id)
        parked = _support.PARK_REVISION_DIRTY if seed.dirty else None
        self.assertEqual(pinned.get(KEYS.park_reason), parked)
        self.assertEqual(self._developer_runs(), 1)


class CapturedRevisionMovedTest(_captured.CapturedRevisionCase):
    """A record the revision's handoff was frozen over, moved while the recovery works, writes none of it."""

    def test_a_moved_generation_parks_nothing(self) -> None:
        # Advanced as the recovery reads a dirty checkout -- behind the
        # admission and ahead of the park -- the generation is a record the
        # handoff was frozen over, so the park that would consume the guidance
        # under the old one is refused: the generation stays advanced, the
        # guidance unread, and the capture pending. The next dispatch retires
        # that capture as past its candidate, with no developer run.
        self._seed_drifted()
        self._held()
        self._released()
        moved = _moves.TreeReadWhile(self._hand_edit, **{_support.KEY_GENERATION: NEXT_GENERATION})

        self._dispatched(seed=_DIRTY, alongside=moved.patched()).assert_not_called()

        held = self._pinned()
        self.assertEqual(
            (held[_support.KEY_GENERATION], held[KEYS.park_reason], _captured.capture_of(held).stage),
            (NEXT_GENERATION, _support.PARK_CONTENT_DRIFT, _captured.PENDING),
        )
        self.assertEqual([field for field in _UNSETTLED if field in held], [])
        self._dispatched(seed=_DIRTY).assert_not_called()
        retired = self._pinned()
        self.assertEqual(
            (retired[_support.KEY_GENERATION], _captured.capture_of(retired).stage, self._developer_runs()),
            (NEXT_GENERATION, _captured.RETIRED, 1),
        )
        self.assertEqual([field for field in _UNSETTLED if field in retired], [])

    def test_a_child_added_behind_the_handoff_stands(self) -> None:
        # A split child recorded as the owner read behind the handoff begins
        # moves a record the capture's handoff was frozen over, so the guarded
        # commit the read's write lands through is refused: the child stands,
        # the read stays owed for a later tick, and nothing is said.
        self._seed_drifted()
        self._held()
        self._released()
        recorded = _moves.BehindTheHandoff(self, self._hand_edit, **_NEW_CHILD)

        with recorded.fetched():
            self._dispatched().assert_not_called()

        pinned = self._pinned()
        self.assertEqual(pinned[_SPLIT_CHILDREN], [_CHILD])
        self.assertTrue(pinned[KEYS.owner_check_pending])
        self.assertEqual(self._bodies()[recorded.said:], [])

    def test_a_head_moved_off_the_report_holds_it(self) -> None:
        # A checkout whose head moved after the revision's report was
        # captured is not the commit the report is about: its own tick
        # reconciles nothing -- the generation, the candidate, and the guidance
        # where they stood -- and the next dispatch retires the capture over
        # the moved checkout, with no developer run.
        self._seed_drifted()

        held = self._revise(_moves.MovedAfterTheReturn(_MOVED_HEAD))[0]

        pinned = self._pinned()
        self.assertEqual(
            (held.disposition, pinned[_support.KEY_GENERATION], pinned[KEYS.candidate_sha]),
            (_LateDisposition.DEFERRED, GENERATION_NUMBER, CANDIDATE_SHA),
        )
        self.assertEqual(_captured.capture_of(pinned).stage, _captured.PENDING)
        self._dispatched(seed=WorktreeSeed(head=_MOVED_HEAD)).assert_not_called()
        retired = self._pinned()
        self.assertEqual(_captured.capture_of(retired).stage, _captured.RETIRED)
        self.assertEqual([field for field in _UNSETTLED if field in retired], [])
        self.assertEqual(self._developer_runs(), 1)


class CapturedPublishedRevisionTest(_captured.CapturedRevisionCase):
    """A held revision of a generation entered on a published pull request, finished over that pull request."""

    def test_the_published_head_admits_it(self) -> None:
        # Until a later publication pushes the revised candidate, the pull
        # request a post-publication generation was entered on still stands on
        # the head that publication pushed, so the run's report is owed exactly
        # that push: the recovery hands it on, with no developer run. One
        # standing on any other head is past the run, and retires it.
        for name, head, stage in (
            ("the published head", PUBLISHED_HEAD_SHA, _captured.HANDED_OFF),
            ("another head", _ELSEWHERE, _captured.RETIRED),
        ):
            with self.subTest(name):
                self._held_over_the_published_head()
                self.github.get_pr(PUBLISHED_PR_NUMBER).head.sha = head

                self._dispatched(seed=_PUBLISHED_REVISION, measurement=_PUBLISHED_MEASURED).assert_not_called()

                self.assertEqual(_captured.capture_of(self._pinned()).stage, stage)
                self.assertEqual(self._developer_runs(), 1)

    def _held_over_the_published_head(self) -> None:
        """Guidance on a post-publication generation, its revision held to its capture under `paused` and released."""
        self._seed(
            generation=_published.published_generation(), pr_number=PUBLISHED_PR_NUMBER, branch=PUBLISHED_BRANCH,
            **_support.DRIFT_PARKED, **_stage_support.DEV_PIN,
        )
        _published.seed_published_pr(self.github)
        self.issue.title = _support.EDITED_TITLE
        self.guidance = _content_replies.reply(self.issue)
        self._held(seed=_PUBLISHED_REVISION, measurement=_PUBLISHED_MEASURED)
        self._released()


class CapturedRevisionOwnerReadTest(_captured.CapturedRevisionCase):
    """The issue the recovery reads behind its readings: a close any of them reads ends the cycle, held or reopened."""

    def test_a_close_beside_a_hold_ends_the_cycle(self) -> None:
        # Closed and held at once as the owner is read behind the handoff,
        # the issue's close outranks the hold: the cycle is cancelled in that
        # very dispatch -- over the comment read again, past the write the
        # hold kept out of the recovery's own -- so reopening the issue and
        # taking the hold off launches nothing for that cycle.
        for control in _captured.CONTROLS:
            with self.subTest(control=control):
                self._held_and_released()
                closed = _moves.BehindTheHandoff(self, self._closed_and_held, control)

                with closed.fetched():
                    self._dispatched().assert_not_called()

                self.assertTrue(self._pinned()[KEYS.cancelled])
                self.issue.closed = False
                self._released(control)
                self._dispatched().assert_not_called()

    def test_a_close_at_the_notice_says_nothing(self) -> None:
        # Closed as the owner read's settlement lands, the issue is read once
        # more ahead of the re-measured candidate's notice: the close it
        # shows ends the cycle, and the notice is never said.
        self._held_and_released()
        closed = _moves.BehindTheHandoff(self, setattr, self.issue, "closed", True)

        with closed.landed(settled=True):
            self._dispatched().assert_not_called()

        self.assertEqual(self._bodies()[closed.said:], [])
        self.assertTrue(self._pinned()[KEYS.cancelled])

    def test_a_close_while_measuring_ends_the_cycle(self) -> None:
        # Closed as the recovery re-measures the candidate, with no poll to
        # latch it, the issue is read closed by the admission the handoff's
        # strict edit asks again: that holds the handoff, and the close it
        # read ends the cycle in that very dispatch, the guidance unread and
        # the generation where it stood. Reopening the issue then finishes
        # nothing of the capture and launches nothing for that cycle.
        self._held_and_released()
        closing = _moves.MeasuredWhile(setattr, self.issue, "closed", True)

        self._dispatched(alongside=closing.patched()).assert_not_called()

        ended = self._pinned()
        self.assertEqual(
            (ended[KEYS.cancelled], _captured.capture_of(ended).stage, ended[_support.KEY_GENERATION]),
            (True, _captured.PENDING, GENERATION_NUMBER),
        )
        self.assertEqual([field for field in _UNSETTLED if field in ended], [])
        self.issue.closed = False
        self._dispatched().assert_not_called()
        reopened = self._pinned()
        self.assertTrue(reopened[KEYS.cancelled])
        self.assertEqual(reopened[_support.KEY_GENERATION], GENERATION_NUMBER)
        self.assertNotEqual(_captured.capture_of(reopened).stage, _captured.HANDED_OFF)
        self.assertEqual([field for field in _UNSETTLED if field in reopened], [])

    def _held_and_released(self) -> None:
        """A revision held to its capture under `paused` and released."""
        self._seed_drifted()
        self._held()
        self._released()

    def _closed_and_held(self, control: str) -> None:
        """A human closing the issue and an operator applying `control` to it."""
        self.issue.closed = True
        _moves.applying(self, control)()


class CapturedRevisionUnreadOwnerTest(_captured.CapturedRevisionCase):
    """An owner GitHub would not return behind the recovery's writes: the park's notice is never said past a hold."""

    def test_a_hold_past_an_unread_owner_says_nothing(self) -> None:
        # Held right behind the withdrawal that follows a dirty tree's park,
        # an owner GitHub then would not return leaves the park's notice owed:
        # the issue is read once more before it, and either control keeps it
        # unsaid.
        for control in _captured.CONTROLS:
            with self.subTest(control=control):
                self._held_and_released()
                applied = _moves.BehindTheHandoff(self, self._held_unread, control)

                with applied.landed(stage=_captured.RETIRED):
                    self._dispatched(seed=_DIRTY)

                self.assertIsNotNone(applied.record)
                self.assertEqual(self._bodies()[applied.said:], [])

    def test_a_hold_on_the_unread_park_says_nothing(self) -> None:
        # Applied right behind the write that parks the issue for an owner
        # GitHub would not return behind the handoff, either control keeps
        # that park's notice unsaid: the issue is read once more behind the
        # park's own write, and the notice stays owed on the record.
        for control in _captured.CONTROLS:
            with self.subTest(control=control):
                self._held_and_released()
                parked = _captured.BehindTheUnreadPark(self, _moves.applying(self, control))

                with parked.patched():
                    self._dispatched().assert_not_called()

                self.assertTrue(parked.refused)
                self.assertIsNotNone(parked.said)
                self.assertEqual(self._bodies()[parked.said:], [])
                self.assertTrue(self._pinned()[KEYS.park_notice])
                self._released(control)

    def _held_and_released(self) -> None:
        """A revision held to its capture under `paused` and released."""
        self._seed_drifted()
        self._held()
        self._released()

    def _held_unread(self, control: str) -> None:
        """An operator applying `control`, and GitHub refusing the next fetch of the issue."""
        _moves.applying(self, control)()
        answers = itertools.chain([RuntimeError(_UNANSWERED)], itertools.repeat(self.issue))
        self.enterContext(patch.object(self.github, "get_issue", MagicMock(side_effect=answers)))
