# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""An authorized `single` over an auto-rebase replay the generation took over.

The replay is a head this orchestrator made, so the settlement that publishes
it -- onto the pull request the generation froze, leased to the head it froze
-- owes the pull request the report debt the rewrite finish records for every
rebase it publishes, before the label hands the head back to its stage. A
pull request somebody moved refuses the publication and records nothing, and
a retry past a push that landed records the same debt without pushing again.
The settlement of a candidate nobody took over is in
`test_late_settlement_published.py`.
"""
from __future__ import annotations

import unittest
from types import MappingProxyType
from unittest.mock import patch

from orchestrator.github.pinned_state import MAX_PINNED_BODY, pinned_state_body
from orchestrator.workflow.engine import rewrite_takeover as _takeover
from orchestrator.workflow.stages.decomposition import (
    late_replay_debt as _late_replay_debt,
    late_result_models as _late_result_models,
)
from orchestrator.workflow.stages.implementing import late_push as _late_push
from tests.workflow.stages.decomposition import late_test_support as _late_support
from tests.workflow.stages.decomposition.late_published_support import published_generation, seed_published_pr
from tests.workflow.stages.decomposition.late_run_support import WorktreeSeed
from tests.workflow.stages.decomposition.late_settlement_support import (
    PARK_PR_UNRECONCILED,
    PARK_SINGLE_DECISION,
    SINGLE_RUN,
    GuardedLateCase,
)

_LateDisposition = _late_result_models._LateDisposition

KEY_REWRITE_DEBT = "developer_report_rewrite_debt"
LABEL_DECOMPOSING = "workflow:decomposing"
KEY_REPLAY = "late_auto_rebase_replay_sha"

# The attempt the auto rebase pinned before the size gate took its replay to
# an adjudication: the anchor PR #78 stands on, its terms, and the replay.
_ATTEMPT = MappingProxyType({
    "pending_auto_base_rebase_push_sha": _late_support.PUBLISHED_HEAD_SHA,
    "pending_auto_base_rebase_rewrite_pr": _late_support.PUBLISHED_PR_NUMBER,
    "pending_auto_base_rebase_rewrite_stage": _late_support.PUBLISHED_SOURCE_STAGE,
    "pending_auto_base_rebase_rewrite_sha": _late_support.CANDIDATE_SHA,
})

# A pinned key nothing reads, standing in for whatever else fills the comment.
_FILLER = "room_filler"

# How far short of the room the replay's debt needs the comment is filled.
_SHORT_OF_THE_DEBT = 10

# The room a comment filled to the last character but one leaves: short of the
# debt and of the park that would ask for room alike.
_NO_ROOM = 1

# The two writes a settlement can die at past its push: the receipt the push
# writes, and the label behind the debt.
_RECEIPT_WRITE = "_publication_paid"
_LABEL_WRITE = "set_workflow_label"


def _owed(previous: str = _late_support.PUBLISHED_HEAD_SHA) -> dict:
    """The debt PR #78 is owed once it stands on the replay of `previous`."""
    return {
        "pr": _late_support.PUBLISHED_PR_NUMBER,
        "branch": _late_support.PUBLISHED_BRANCH,
        "previous_head": previous,
        "rewritten_head": _late_support.CANDIDATE_SHA,
    }


def _debt_room() -> int:
    """The characters the replay's debt adds to a pinned comment that already carries a field."""
    standing = {_FILLER: ""}
    grown = {**standing, KEY_REWRITE_DEBT: _owed()}
    return len(pinned_state_body(grown)) - len(pinned_state_body(standing))


def _crashes(*_called, **_options):
    """The step a settlement dies on, past its own push."""
    raise RuntimeError("the process ended here")


class _RefusesOversizedEdits:
    """GitHub refusing a pinned comment longer than it holds, as the real edit does; anything else written as asked."""

    def __init__(self, wrapped) -> None:
        self._wrapped = wrapped

    def __call__(self, issue, state):
        length = len(pinned_state_body(state.data))
        if length > MAX_PINNED_BODY and not state.withheld:
            raise ValueError(f"a pinned comment of {length} characters is past what GitHub holds")
        return self._wrapped(issue, state)


class _ReplayCase(GuardedLateCase):
    """Issue #41 adjudicating the replay of PR #78's head that it took over from an auto rebase."""

    def _seed_replay(self, *, replay_sha: str = _late_support.CANDIDATE_SHA, **pinned) -> None:
        """Re-seed the issue with the generation owning `replay_sha`, PR #78 open on its frozen head."""
        seed_published_pr(self.github)
        self.github.seed_state(
            self.issue.number,
            branch=_late_support.PUBLISHED_BRANCH,
            **_late_support.generation_state(published_generation(replay_sha=replay_sha)),
            **pinned,
        )

    def _landed(self) -> None:
        """Put PR #78 on the replay, as the settlement's push left it."""
        self.github.get_pr(_late_support.PUBLISHED_PR_NUMBER).head.sha = _late_support.CANDIDATE_SHA

    def _settled(self, outcome) -> tuple:
        """The disposition, the label, and the debt the record carries."""
        label = self.github.workflow_label(self.issue)
        return (outcome.disposition, label, self._pinned().get(KEY_REWRITE_DEBT))

    def _pinned_comment(self) -> dict:
        """The record issue #41's pinned comment holds, to be edited where it stands."""
        return self.github._pinned[_late_support.LATE_ISSUE_NUMBER].data


class ReplayPublicationTest(_ReplayCase, unittest.TestCase):
    """The replay is pushed where the generation froze it and leaves its report owed."""

    def test_the_replay_publishes_and_owes_its_report(self) -> None:
        # The attempt hands its replay to the generation first, and owning it
        # is what the settlement's push owes the report for.
        self._seed_replay(replay_sha="", **_ATTEMPT)
        state = self.github.read_pinned_state(self.issue)
        handed = _takeover.takes_over(self.github, self.issue, state)
        self.assertEqual(handed, _takeover.TakeoverOutcome.TAKEN_OVER)

        outcome = self._settle()

        self.assertEqual(
            self._settled(outcome),
            (_LateDisposition.SETTLED, _late_support.PUBLISHED_SOURCE_STAGE, _owed()),
        )
        pinned = self._pinned()
        # Pushed as exactly the replay over the frozen head, its publication
        # debt paid, and the ownership retired with the generation after the
        # attempt it was handed from.
        self.assertEqual(
            (
                pinned[_late_support.KEYS.receipt_sha],
                pinned[_late_support.KEYS.receipt_lease],
                pinned[_late_support.KEYS.receipt_pr],
                pinned.get(_late_support.KEYS.approved_sha),
                KEY_REPLAY in pinned,
                {key: pinned[key] for key in _ATTEMPT},
            ),
            (
                _late_support.CANDIDATE_SHA, _late_support.PUBLISHED_HEAD_SHA,
                _late_support.PUBLISHED_PR_NUMBER, None, False, dict.fromkeys(_ATTEMPT),
            ),
        )

    def test_a_standing_claim_moves_onto_the_replay(self) -> None:
        # An earlier rebase left PR #78 owing a report of the head it stands on,
        # and none has settled: the replay retargets that claim, keeping the
        # head the settled report is about.
        earlier = {**_owed(_late_support.OTHER_SHA), "rewritten_head": _late_support.PUBLISHED_HEAD_SHA}
        self._seed_replay(**{KEY_REWRITE_DEBT: earlier})

        outcome = self._settle()

        self.assertEqual(
            self._settled(outcome),
            (_LateDisposition.SETTLED, _late_support.PUBLISHED_SOURCE_STAGE, _owed(_late_support.OTHER_SHA)),
        )

    def test_an_unowned_candidate_owes_no_report(self) -> None:
        # A candidate a developer committed, and an ownership naming another
        # commit than the one being published: neither is this orchestrator's
        # rewrite, so the settlement records no debt for it.
        for replay_sha in ("", _late_support.OTHER_SHA):
            with self.subTest(replay_sha=replay_sha):
                self.setUp()
                self._seed_replay(replay_sha=replay_sha)

                outcome = self._settle()

                self.assertEqual(
                    self._settled(outcome),
                    (_LateDisposition.SETTLED, _late_support.PUBLISHED_SOURCE_STAGE, None),
                )

    def test_ownership_alone_publishes_nothing(self) -> None:
        # The adjudicator answers `single` and no operator has authorized the
        # replay: owning it is no licence, so the issue parks for the human with
        # nothing pushed, receipted, or owed.
        self._seed_replay()

        outcome = self._decide(SINGLE_RUN)

        pinned = self._pinned()
        self.assertEqual(self._settled(outcome), (_LateDisposition.PARKED, LABEL_DECOMPOSING, None))
        self.assertEqual(
            (pinned[_late_support.KEYS.park_reason], _late_support.KEYS.receipt_sha in pinned, pinned[KEY_REPLAY]),
            (PARK_SINGLE_DECISION, False, _late_support.CANDIDATE_SHA),
        )

    def test_a_foreign_head_refuses_the_publication(self) -> None:
        # Somebody pushed to PR #78 while the replay was adjudicated -- seen
        # where the settlement reads the pull request, or by the lease refusing
        # the push itself. Nothing is published or owed, and the generation
        # keeps the replay for the retry.
        for described, seeded, worktree in (
            ("moved before the reading", _late_support.OTHER_SHA, WorktreeSeed()),
            ("moved under the lease", _late_support.PUBLISHED_HEAD_SHA, WorktreeSeed(push=False)),
        ):
            with self.subTest(described):
                self.setUp()
                self._seed_replay()
                self.github.get_pr(_late_support.PUBLISHED_PR_NUMBER).head.sha = seeded

                outcome = self._settle(worktree=worktree)

                pinned = self._pinned()
                self.assertEqual(self._settled(outcome), (_LateDisposition.PARKED, LABEL_DECOMPOSING, None))
                self.assertEqual(
                    (pinned[_late_support.KEYS.park_reason], pinned[KEY_REPLAY]),
                    (PARK_PR_UNRECONCILED, _late_support.CANDIDATE_SHA),
                )


class InterruptedReplaySettlementTest(_ReplayCase, unittest.TestCase):
    """A settlement interrupted past its push keeps the debt it owes, and pushes nothing again.

    Every pinned write is held to what GitHub accepts, so a room refusal is
    measured on a comment that could really have been written.
    """

    def setUp(self) -> None:
        super().setUp()
        sized = _RefusesOversizedEdits(self.github.write_pinned_state)
        refusing = patch.object(self.github, "write_pinned_state", sized)
        refusing.start()
        self.addCleanup(refusing.stop)

    def test_a_landed_push_keeps_the_obligation(self) -> None:
        # The process ends after the push landed: before the receipt it wrote,
        # or at the label behind the debt. The retry finds PR #78 on the replay
        # and settles with a push that would refuse, so nothing is sent again.
        for seam in (_RECEIPT_WRITE, _LABEL_WRITE):
            with self.subTest(seam):
                self.setUp()
                self._seed_replay()
                owner = self.github if seam == _LABEL_WRITE else _late_push
                with patch.object(owner, seam, _crashes), self.assertRaises(RuntimeError):
                    self._settle()
                self._landed()

                outcome = self._settle(worktree=WorktreeSeed(push=False))

                self.assertEqual(
                    self._settled(outcome),
                    (_LateDisposition.SETTLED, _late_support.PUBLISHED_SOURCE_STAGE, _owed()),
                )

    def test_a_debt_without_room_parks_for_it(self) -> None:
        # The comment has room for the park asking for room and none for the
        # debt: the push is kept, the issue stays under adjudication with the
        # park said once, and the replay's ownership stands for the retry.
        self._published_then_filled(_debt_room() - _SHORT_OF_THE_DEBT)
        said = len(self.github.posted_comments)

        parked = self._settle(worktree=WorktreeSeed(push=False))

        pinned = self._pinned()
        self.assertEqual(self._settled(parked), (_LateDisposition.PARKED, LABEL_DECOMPOSING, None))
        self.assertEqual(
            (pinned[_late_support.KEYS.park_reason], pinned[_late_support.KEYS.receipt_sha], pinned[KEY_REPLAY]),
            (PARK_PR_UNRECONCILED, _late_support.CANDIDATE_SHA, _late_support.CANDIDATE_SHA),
        )
        self.assertEqual(len(self.github.posted_comments), said + 1)
        self._recovers()

    def test_no_room_for_its_park_writes_nothing(self) -> None:
        # Not even the park asking for room fits: nothing is posted or written,
        # and the comment as it stands -- the receipt and the generation owning
        # the replay -- is what the retry records the debt from.
        self._published_then_filled(_NO_ROOM)
        standing = (self._pinned(), len(self.github.posted_comments))

        held = self._settle(worktree=WorktreeSeed(push=False))

        self.assertEqual(self._settled(held), (_LateDisposition.PARKED, LABEL_DECOMPOSING, None))
        self.assertEqual((self._pinned(), len(self.github.posted_comments)), standing)
        self._recovers()

    def _published_then_filled(self, room: int) -> None:
        """Publish the replay, end the process before its debt, and leave `room` characters on the comment."""
        self._seed_replay()
        with patch.object(_late_replay_debt, "_records_the_replay_debt", _crashes), self.assertRaises(RuntimeError):
            self._settle()
        self._landed()
        pinned = self._pinned_comment()
        pinned[_FILLER] = ""
        free = MAX_PINNED_BODY - len(pinned_state_body(pinned))
        pinned[_FILLER] = "x" * (free - room)

    def _recovers(self) -> None:
        """Make room, and settle with a push that would refuse: the debt is recorded and nothing is sent again."""
        self._pinned_comment().pop(_FILLER)

        outcome = self._settle(worktree=WorktreeSeed(push=False))

        self.assertEqual(
            self._settled(outcome),
            (_LateDisposition.SETTLED, _late_support.PUBLISHED_SOURCE_STAGE, _owed()),
        )
