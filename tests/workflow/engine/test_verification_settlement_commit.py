# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The commit making verification evidence current, over a comment other roads keep writing.

A settling tick reads the pinned comment four times: to prepare the settlement
ahead of the post, ahead of the proof, behind the proof -- the reading the
settlement is composed over -- and to commit it. Each case lets another road
write right behind one of those readings, as a whole-record write over the
comment as that road reads it, and reads back the record, the artifacts on the
pull request, and what the next tick does.

A field the settlement owns none of -- a usage total, a watermark, another
road's comment on the ledger, a reviewer's verdict, a field no binary here
knows -- is kept as that road left it. A bound record it moves, however the
comment's JSON spells the move, refuses the commit: the move is kept, nothing
is declared current, the transaction stays owed, and the artifact is still
recorded as ours. A comment replaced or no longer parsing holds the tick with
nothing written over it, whichever write meets it -- the settlement's commit or
the artifact's ledger entry committed alone. However the commit was refused, a
later tick settles the one artifact once wherever the proof still holds. And
the room proved before the post reserves the artifact's ledger entry against
the ledger as it stands, so a slot another road took since posts nothing.
"""
from __future__ import annotations

import itertools
import json
import unittest
from collections.abc import Callable
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any
from unittest.mock import patch

from orchestrator.github.pinned_state import MAX_PINNED_BODY, PinnedState, pinned_state_body
from orchestrator.workflow.engine import (
    comments as _comments,
    pinned_commit_models as _commit_models,
    report_records as _report_records,
    review_subjects as _review_subjects,
    verification_record_state as _record_state,
    verification_records as _records,
    verification_settlement_state as _settlement,
)
from tests.workflow.engine import verification_evidence_test_support as support

# The reading the settlement is composed over, and the one its commit takes.
_COMPOSED_OVER = 3
_COMMITTED_OVER = 4

# What another road writes that a settlement owns none of.
_INDEPENDENT = MappingProxyType({
    "issue_total_tokens": 4321,
    "issue_cost_sources": ["unknown-price"],
    "last_action_comment_id": 987654,
    "review_returned_verdict": {"round": 1, "verdict": "approved"},
    "a_field_no_binary_writes_yet": {"n": [1, None, True]},
})

# A comment another road posted and recorded as the orchestrator's.
_ANOTHER_ROADS_COMMENT = 555555

# A bound record another road removes, rather than writes.
_GONE = _commit_models.ABSENT

# A field of another road's that fills the pinned comment.
_FILLER = "filler"

# Where a comment is spoiled under a settlement, and whether a push during the
# post refused the binding first: behind the reading the settlement is composed
# over, behind the commit's own reading, and behind the reading a refused
# binding leaves the artifact's ledger entry over.
_SPOILING_WINDOWS = ((_COMPOSED_OVER, False), (_COMMITTED_OVER, False), (_COMPOSED_OVER, True))


def _writes_bookkeeping(case) -> None:
    """Another road's write of fields no settlement owns, and of a comment of its own onto the ledger."""
    elsewhere = case.gh.read_pinned_state(case.issue)
    elsewhere.data.update(_INDEPENDENT)
    _comments._track_orchestrator_comment(elsewhere, _ANOTHER_ROADS_COMMENT)
    case.gh.write_pinned_state(case.issue, elsewhere)


@dataclass(frozen=True)
class _Move:
    """Another road moving one bound record, and whether a later tick's proof still settles over the move."""

    name: str
    record: str
    # What the record is moved to, for one case; `_GONE` removes it.
    to: Callable[[Any], Any]
    settles: bool

    def lands(self, case) -> None:
        """The move, as a whole-record write over another road's own reading of the comment."""
        elsewhere = case.gh.read_pinned_state(case.issue)
        moved_to = self.to(case)
        if moved_to is _GONE:
            elsewhere.data.pop(self.record)
        else:
            elsewhere.set(self.record, moved_to)
        case.gh.write_pinned_state(case.issue, elsewhere)

    def spelled_on(self, case) -> tuple[str | None, str | None]:
        """How the comment spells the record now, and how the move spelled it; None for absent."""
        persisted = case.gh.pinned_data(support.ISSUE_NUMBER).get(self.record, _GONE)
        return _spelling(persisted), _spelling(self.to(case))


def _spelling(found: Any) -> str | None:
    """How the comment's JSON spells one value, or None for `_GONE`."""
    return None if found is _GONE else json.dumps(found, sort_keys=True)


_APPROVAL_RECORDED = _Move(
    "an approval recorded", _review_subjects.APPROVED_SUBJECT, lambda case: case.subject.recorded(), settles=True,
)

# Every bound record another road can move: a developer report recorded, the
# review subject removed, an approval recorded or written `null` where none
# was, and the pull request repointed or the same number spelled as a float.
# The approvals settle on a later tick; every other move is one the proof
# refuses there too -- a report owed, a subject gone, a pull request it does
# not pin.
_BOUND_MOVES = (
    _Move(
        "a later report recorded", _report_records.PENDING_REPORT,
        lambda _case: {"receipt": f"issue-{support.ISSUE_NUMBER}-report-2"}, settles=False,
    ),
    _Move("the review subject removed", _review_subjects.REVIEW_SUBJECT, lambda _case: _GONE, settles=False),
    _APPROVAL_RECORDED,
    _Move("an approval written null", _review_subjects.APPROVED_SUBJECT, lambda _case: None, settles=True),
    _Move("the pull request repointed", "pr_number", lambda _case: support.PR_NUMBER + 1, settles=False),
    _Move("the pull request as a float", "pr_number", lambda _case: float(support.PR_NUMBER), settles=False),
)


@dataclass
class _Behind:
    """One tick of `case` over the reading it took first, `road` landing right behind its `number`-th pinned reading."""

    case: Any
    number: int
    road: Callable[[Any], None]
    reads: Callable[[Any], PinnedState] = field(init=False)

    def __call__(self, issue) -> PinnedState:
        fresh = self.reads(issue)
        self.number -= 1
        if not self.number:
            self.road(self.case)
        return fresh

    def __post_init__(self) -> None:
        self.reads = self.case.gh.read_pinned_state

    def reconciles(self) -> bool:
        """What the tick answers."""
        tick = self.case.gh.read_pinned_state(self.case.issue)
        with patch.object(self.case.gh, "read_pinned_state", self):
            return self.case.reconcile(tick)


class IndependentUpdatesTest(unittest.TestCase, support.VerificationEvidenceCase):
    """What another road writes beside a settlement is kept, whenever it lands."""

    def setUp(self) -> None:
        support.VerificationEvidenceCase.setUp(self)

    def test_another_roads_fields_are_kept(self) -> None:
        # Behind the reading the settlement is composed over, its commit reads
        # the fields afresh and lands over them. Behind the commit's own
        # reading, the edit finds the comment moved and sends nothing: the
        # transaction stays owed with the artifact recorded as ours, and the
        # next tick settles it. Either way the fields are kept as written,
        # the ledger holds that road's comment and the artifact, and one
        # artifact is on the pull request.
        for number, settled in ((_COMPOSED_OVER, True), (_COMMITTED_OVER, False)):
            with self.subTest(number=number):
                self.setUp()
                pending = self.record()

                self.assertFalse(_Behind(self, number, _writes_bookkeeping).reconciles())
                self.assertEqual(self.state.data, self.gh.pinned_data(support.ISSUE_NUMBER))
                self.assertEqual(_record_state.carries_pending_evidence(self.state), not settled)
                if not settled:
                    self.assertFalse(self.reconcile())

                record = self.gh.pinned_data(support.ISSUE_NUMBER)
                current = _settlement.read_current_evidence(self.state)
                self.assertEqual(current.receipt, pending.receipt)
                self.assertEqual(self.artifacts(), [pending.artifact])
                self.assertEqual({**record, **_INDEPENDENT}, record)
                self.assertLessEqual({_ANOTHER_ROADS_COMMENT, current.comment_id}, set(record[support.LEDGER]))


    def test_the_artifacts_slot_is_reserved_afresh(self) -> None:
        # After this tick read the comment, another road records a comment at
        # the very id the tick's reading would reserve for the artifact, and
        # fills the comment to where the settlement and the invalidation behind
        # it fit only if that reservation costs nothing. Reserved against the
        # ledger as it stands, the artifact's entry still takes a slot of its
        # own, so nothing is posted or written and the transaction stays owed.
        pending = self.record()
        filled = PinnedState(comment_id=self.state.comment_id, state_data=dict(self.state.data))
        filled.set(_FILLER, "")
        invalidated = PinnedState(state_data=dict(_record_state.settled_payload(filled, pending)))
        self.assertTrue(_settlement.retire_current_evidence(invalidated))
        room = MAX_PINNED_BODY - len(pinned_state_body(invalidated.data))
        filled.set(_FILLER, "y" * room)
        filled.set(support.LEDGER, invalidated.get(support.LEDGER))
        self.gh.write_pinned_state(self.issue, filled)
        writes = self.gh.write_state_calls

        with self.assertLogs(support.WORKFLOW_LOG, "WARNING"):
            self.assertFalse(self.reconcile(self.state))

        self.assertEqual((self.artifacts(), self.gh.write_state_calls), ([], writes))
        self.assertEqual(_record_state.read_pending_evidence(self.gh.read_pinned_state(self.issue)), pending)


class StaleSettlementTest(unittest.TestCase, support.VerificationEvidenceCase):
    """A settlement whose bound records moved is refused, and the move is kept."""

    def setUp(self) -> None:
        support.VerificationEvidenceCase.setUp(self)
        self.pending = self.record()
        self.newer: list[_records.PendingEvidence] = []

    def test_a_bound_record_moved_refuses_the_commit(self) -> None:
        # Behind the reading the settlement is composed over, another road
        # moves one bound record. The commit refuses: nothing is current, the
        # transaction is owed, the record is spelled as that road left it,
        # and the artifact is on the ledger. A later tick settles the one
        # artifact where the proof still holds, and leaves it owed where not.
        for move in _BOUND_MOVES:
            with self.subTest(move.name):
                self.setUp()
                with self.assertLogs(support.WORKFLOW_LOG, "ERROR") as logged:
                    self.assertFalse(_Behind(self, _COMPOSED_OVER, move.lands).reconciles())
                    self.assertIn(f"{move.record} moved since this tick read it", support.logged_refusal(logged))

                persisted = self.gh.read_pinned_state(self.issue)
                posted = self.pull_request.issue_comments[-1].id
                self.assertEqual(*move.spelled_on(self))
                self.assertEqual(
                    (_settlement.read_current_evidence(persisted), _record_state.read_pending_evidence(persisted)),
                    (None, self.pending),
                )
                self.assertIn(posted, persisted.get(support.LEDGER))

                self.reconcile()

                self.assertEqual(
                    getattr(_settlement.read_current_evidence(self.state), "receipt", None),
                    self.pending.receipt if move.settles else None,
                )
                self.assertEqual(self.artifacts(), [self.pending.artifact])

    def test_newer_evidence_recorded_meanwhile(self) -> None:
        # Another road records a newer transaction behind the reading the
        # settlement is composed over, abandoning this one into history. The
        # commit refuses rather than put this one back over it or lower the
        # floor under it, and the next tick publishes and settles the newer
        # one -- each artifact once, the earlier indexed once.
        self.assertFalse(_Behind(self, _COMPOSED_OVER, self.records_newer).reconciles())
        persisted = self.gh.read_pinned_state(self.issue)
        newer = self.newer[0]
        self.assertEqual(
            (
                _record_state.read_pending_evidence(persisted),
                persisted.get(_records.REVISION_FLOOR),
                _settlement.read_current_evidence(persisted),
            ),
            (newer, newer.revision, None),
        )

        self.assertFalse(self.reconcile())

        self.assertEqual(self.artifacts(), [self.pending.artifact, newer.artifact])
        self.assertEqual(_settlement.read_current_evidence(self.state).receipt, newer.receipt)
        self.assertEqual(
            [(entry.receipt, entry.retired) for entry in _settlement.read_evidence_history(self.state)],
            [(self.pending.receipt, _records.Retirement.ABANDONED)],
        )

    def test_a_bound_record_moved_before_the_post(self) -> None:
        # The approval is recorded after this tick read the comment and
        # before anything is posted: the settlement prepared over the comment
        # as it stands is refused, so nothing is posted or written, and the
        # next tick posts and settles over the approval as written.
        tick = self.gh.read_pinned_state(self.issue)
        _APPROVAL_RECORDED.lands(self)
        writes = self.gh.write_state_calls

        with self.assertLogs(support.WORKFLOW_LOG, "WARNING"):
            self.assertFalse(self.reconcile(tick))
        self.assertEqual((self.artifacts(), self.gh.write_state_calls), ([], writes))

        self.assertFalse(self.reconcile())

        self.assertEqual(self.artifacts(), [self.pending.artifact])
        self.assertEqual(_settlement.read_current_evidence(self.state).receipt, self.pending.receipt)
        self.assertEqual(self.state.get(_review_subjects.APPROVED_SUBJECT), self.subject.recorded())

    def records_newer(self, _case) -> None:
        """Another road's transaction, recorded on its own reading of the comment."""
        elsewhere = self.gh.read_pinned_state(self.issue)
        self.newer.append(self.record(onto=elsewhere))


class ReplacedCommentTest(unittest.TestCase, support.VerificationEvidenceCase):
    """A comment replaced or unparsed under a settlement holds the tick with nothing written over it."""

    def setUp(self) -> None:
        support.VerificationEvidenceCase.setUp(self)
        self.pending = self.record()
        self.posts = self.gh._post_verification_artifact

    def test_nothing_is_written_over_another_comment(self) -> None:
        # The pinned comment is replaced by another carrying the same record,
        # or edited into something that does not parse: behind the reading the
        # settlement is composed over, behind the commit's own reading -- where
        # the edit finds the comment moved and the artifact's ledger entry is
        # committed alone -- or behind the reading a binding refused by a push
        # during the post leaves that entry over. Whichever write meets it
        # holds the tick and writes nothing. Over a replacement the next tick
        # settles the one artifact unless the push refuses it; over a comment
        # that does not parse it finds nothing it may act on and writes nothing.
        for (name, replaced), window in itertools.product(
            (("replaced", True), ("unparsed", False)), _SPOILING_WINDOWS,
        ):
            with self.subTest(name, window=window):
                self.setUp()
                writes = self.gh.write_state_calls

                with self.assertLogs(support.WORKFLOW_LOG, "WARNING"):
                    self.assertTrue(self.holds_behind(window, self.repins if replaced else self.unparses))
                self.assertEqual(self.gh.write_state_calls, writes)

                self.assertFalse(self.reconcile())

                settles = replaced and not window[1]
                self.assertEqual(
                    (
                        self.gh.write_state_calls - writes,
                        getattr(_settlement.read_current_evidence(self.state), "receipt", None),
                        self.artifacts(),
                    ),
                    (int(settles), self.pending.receipt if settles else None, [self.pending.artifact]),
                )

    def holds_behind(self, window: tuple[int, bool], road) -> bool:
        """The tick with `road` behind the reading `window` names, after a push during the post where it says."""
        number, pushed = window
        with patch.object(self.gh, "_post_verification_artifact", self.posts_then_pushes if pushed else self.posts):
            return _Behind(self, number, road).reconciles()

    def posts_then_pushes(self, pull_request, body: str):
        """Land the artifact, then push the pull request past the head it was proved on."""
        landed = self.posts(pull_request, body)
        self.moves_the_head(support.REBASED_SHA)
        return landed

    def repins(self, _case) -> None:
        """The pinned comment replaced by another carrying the same record."""
        self.gh.seed_state(self.issue, **self.gh.pinned_data(support.ISSUE_NUMBER))

    def unparses(self, _case) -> None:
        """The pinned comment edited in place into something that does not parse."""
        self.gh._pinned[support.ISSUE_NUMBER] = PinnedState(
            comment_id=self.gh.read_pinned_state(self.issue).comment_id, parsed=False,
        )


if __name__ == "__main__":
    unittest.main()
