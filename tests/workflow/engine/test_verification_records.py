# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The evidence records' round trip: safe absences, refusals, settlement, and history.

An issue that predates these records carries none of their keys, and has to
read back as owing nothing, holding nothing, and having retired nothing. A
record is accepted only where it reads back identically through the pinned
comment, its artifact renders, and the comment has room for the write that
settles it; a later one abandons the earlier into history rather than
forgetting a receipt that may already be on the thread. A settlement is one
composed write, a retirement keeps the record whole, and the history index
stays bounded without a later revision ever reusing one it evicted.

Every case drives the owners directly, since nothing in production records or
settles evidence yet.
"""
from __future__ import annotations

import copy
import unittest
import uuid
from dataclasses import replace
from types import MappingProxyType

from orchestrator.github.pinned_state import (
    MAX_PINNED_BODY,
    PINNED_STATE_MARKER,
    PinnedState,
    pinned_state_body,
)
from orchestrator.github.verification_evidence import EvidenceSource
from orchestrator.workflow.engine import (
    comments as _comments,
    report_record_values as _record_values,
    verification_record_state as _record_state,
    verification_records as _records,
    verification_settlement_state as _settlement,
)
from orchestrator.workflow.state import WorkflowLabel
from tests.support.fakes import FakeGitHubClient, make_issue
from tests.workflow.engine import verification_record_test_support as support

# The handoff member naming the label a settlement landed under.
_UNDER = "under"

# A transcript the artifact carries in half a comment, and the pinned record,
# whose JSON escapes each of these characters six characters wide, in none.
_ESCAPED_TRANSCRIPT = "é" * (MAX_PINNED_BODY // 2)

# Text a JSON escape can spell and UTF-8 cannot carry.
_LONE_SURROGATE = "12 passed \ud800"

# The filler a crowding case fills the rest of the comment with.
_FILLER = "filler"

# More settlements than the history index keeps, and how many it keeps.
_SETTLEMENTS = 7

_HISTORY_KEPT = 5

_BEYOND_RECORDED = _record_values.MAX_RECORDED_NUMBER + 1

# The revision floor an issue with damaged records has already raised.
_SPENT = 3

# The widest settlement: the label with the longest spelling, and a comment id
# at the widest this domain records.
_WIDEST_LABEL = max(WorkflowLabel, key=lambda label: len(str(label)))

_WIDEST_COMMENT = _record_values.MAX_RECORDED_NUMBER

# The recorded review subject about another pull request, and under other
# requirements.
_FOREIGN_SUBJECT = support.SUBJECT.recorded() | {"pr": support.PR_NUMBER + 1}

_OTHER_REQUIREMENTS = "0" * len(support.REQUIREMENTS)

_UNREQUIRED_SUBJECT = support.SUBJECT.recorded() | {"requirements": _OTHER_REQUIREMENTS}

# A review subject naming no developer report, which binds evidence to none.
_UNREPORTED_SUBJECT = support.SUBJECT.recorded() | {"report_revision": None, "report_content": None}

# A tree one character short of a whole object id.
_ABBREVIATED_TREE = support.TESTED_TREE[:-1]

# Each settled record with one member rewritten into something its writer
# never spells, and the reader that has to refuse it.
# The member naming the transaction a record came from.
_RECEIPT = "receipt"

# A receipt spelled as one minted under a revision no settled record here has.
_FOREIGN_RECEIPT = _records.RECEIPT.format(
    issue=support.ISSUE_NUMBER, revision=_SPENT, nonce=uuid.UUID(int=0).hex,
)

_DAMAGE = (
    (_records.CURRENT_EVIDENCE, _RECEIPT, _FOREIGN_RECEIPT),
    (_records.CURRENT_EVIDENCE, "tree", _ABBREVIATED_TREE),
    (_records.CURRENT_EVIDENCE, "passed", "yes"),
    (_records.CURRENT_EVIDENCE, "comment", None),
    (_records.EVIDENCE_HANDOFF, _RECEIPT, _FOREIGN_RECEIPT),
    (_records.EVIDENCE_HANDOFF, "head", _ABBREVIATED_TREE),
    (_records.EVIDENCE_HISTORY, _RECEIPT, _FOREIGN_RECEIPT),
    (_records.EVIDENCE_HISTORY, "retired", "forgotten"),
    # A comment exactly for evidence that was current: never beside an
    # abandonment, never missing beside a supersession, and an identity.
    (_records.EVIDENCE_HISTORY, "retired", str(_records.Retirement.ABANDONED)),
    (_records.EVIDENCE_HISTORY, "comment", None),
    (_records.EVIDENCE_HISTORY, "comment", str(support.ARTIFACT_COMMENT)),
)

_READERS = MappingProxyType({
    _records.CURRENT_EVIDENCE: _settlement.read_current_evidence,
    _records.EVIDENCE_HANDOFF: _settlement.read_evidence_handoff,
    _records.EVIDENCE_HISTORY: _settlement.read_evidence_history,
})

# Each witness, over a passing run, a run with a failure, and a run of nothing,
# with whether the record says it passed.
_SHAPES = (
    (EvidenceSource.ORCHESTRATOR_EXECUTED, (support.ran(),), True),
    (
        EvidenceSource.REVIEWER_REPORTED,
        (support.ran(), support.ran("1 failed", exit_status=1)),
        False,
    ),
    (EvidenceSource.REVIEWER_REPORTED, (), False),
)


def _issue() -> PinnedState:
    """The pinned comment of an issue with a pull request and no evidence yet."""
    return PinnedState(comment_id=1, state_data={"pr_number": support.PR_NUMBER})


def _filling_the_record() -> str:
    """A transcript filling exactly the room `_issue` has for a record carrying it.

    The artifact wraps a transcript in more than the record does -- a preamble
    naming its whole identity -- so this one is past what the artifact's own
    comment holds while the record, and the settlement that drops it, fit.
    """
    state = _issue()
    _record_state.record_pending_evidence(
        state, support.minted(state, commands=(support.ran(""),)),
    )
    return "x" * (MAX_PINNED_BODY - len(pinned_state_body(state.data)))


class AbsentRecordsTest(unittest.TestCase):
    """An issue that recorded no evidence owes nothing, and nor does one nobody can read."""

    def test_an_issue_without_the_keys_owes_nothing(self) -> None:
        state = _issue()
        before = dict(state.data)

        self.assertFalse(_record_state.carries_pending_evidence(state))
        self.assertEqual(
            (
                _record_state.read_pending_evidence(state),
                _settlement.read_current_evidence(state),
                _settlement.read_evidence_history(state),
                _settlement.read_evidence_handoff(state),
            ),
            (None, None, (), None),
        )
        self.assertEqual(support.minted(state).revision, 1)
        self.assertFalse(_settlement.retire_current_evidence(state))
        self.assertEqual(state.data, before)

    def test_damage_reads_as_nothing_to_rely_on(self) -> None:
        damaged = {_RECEIPT: "issue-7-verification-1"}
        state = PinnedState(comment_id=1, state_data={
            _records.PENDING_EVIDENCE: damaged,
            _records.CURRENT_EVIDENCE: damaged,
            _records.EVIDENCE_HISTORY: {"not": "a list"},
            _records.EVIDENCE_HANDOFF: damaged,
            _records.REVISION_FLOOR: _SPENT,
        })

        # Claimed, but nobody can read what it claims.
        self.assertTrue(_record_state.carries_pending_evidence(state))
        self.assertEqual(
            (
                _record_state.read_pending_evidence(state),
                _settlement.read_current_evidence(state),
                _settlement.read_evidence_history(state),
                _settlement.read_evidence_handoff(state),
            ),
            (None, None, None, None),
        )
        # Recording and settling over the damage drops it without indexing any
        # of it, past the revisions it spent; the unreadable history is
        # replaced once something is retired.
        first, _ = [support.settles(state) for _ in range(2)]

        self.assertEqual(first.revision, _SPENT + 1)
        self.assertEqual(
            _settlement.read_evidence_history(state),
            (_records.HistoricalEvidence.of(
                support.current(first), _records.Retirement.SUPERSEDED,
            ),),
        )


    def test_an_unprovable_floor_refuses_every_record(self) -> None:
        # Nobody can say which revisions were spent, so any could be one an
        # artifact on the pull request already carries.
        for case, (state, later) in self._unprovable().items():
            with self.subTest(case=case):
                before = copy.deepcopy(state.data)

                self.assertIsNone(support.minted(state))
                self.assertFalse(_record_state.record_pending_evidence(state, later))
                self.assertEqual(state.data, before)

    def test_an_unwritten_history_is_damage(self) -> None:
        # Only what its writer leaves reads: never a `null`, at most the
        # entries kept, each revision once, strictly rising.
        for case, unwritten in self._unwritten_histories().items():
            with self.subTest(case=case):
                damaged = PinnedState(state_data={_records.EVIDENCE_HISTORY: unwritten})

                self.assertIsNone(_settlement.read_evidence_history(damaged))

    def _unwritten_histories(self) -> dict[str, object]:
        """Each history no retirement writes, built from entries that read."""
        indexed = _issue()
        for _ in range(_SETTLEMENTS):
            support.settles(indexed)
        kept = indexed.get(_records.EVIDENCE_HISTORY)
        _settlement.retire_current_evidence(indexed)
        later = indexed.get(_records.EVIDENCE_HISTORY)
        return {
            "null": None,
            "past the entries kept": [kept[0], *later],
            "a revision twice": [*kept[:-1], kept[-2]],
            "revisions out of order": [kept[1], kept[0], *kept[2:]],
        }

    def _unprovable(self) -> dict[str, tuple[PinnedState, _records.PendingEvidence]]:
        """Each comment that cannot say which revisions it spent, and a transaction next otherwise."""
        settled = _issue()
        support.settles(settled)
        later = support.minted(settled)
        floorless = dict(settled.data)
        floorless.pop(_records.REVISION_FLOOR)
        first = support.minted(PinnedState())
        return {
            "unreadable floor": (PinnedState(state_data=settled.data | {_records.REVISION_FLOOR: "1"}), later),
            "floor missing beside a record": (PinnedState(state_data=floorless), later),
            "floor missing beside a null record": (
                PinnedState(state_data={_records.PENDING_EVIDENCE: None}), first,
            ),
            "null floor": (PinnedState(state_data={_records.REVISION_FLOOR: None}), first),
            # Its empty stand-in reads exactly as an issue that recorded nothing.
            "comment that did not parse": (PinnedState(comment_id=1, parsed=False), first),
        }


class RoundTripTest(unittest.TestCase):
    """Each record reads back through the pinned comment exactly as written."""

    def test_every_record_round_trips(self) -> None:
        for source, commands, passed in _SHAPES:
            with self.subTest(source=source, commands=len(commands)):
                pending = support.minted(
                    PinnedState(), support.binding(source=source), commands,
                )

                self.assertIs(pending.passed, passed)
                self._round_trips(pending)

    def test_a_retargeted_run_names_what_it_tested(self) -> None:
        state = _issue()
        pending = support.minted(state, support.binding().retargeted(support.REBASED_SHA))

        self.assertTrue(_record_state.record_pending_evidence(state, pending))
        artifact = _record_state.read_pending_evidence(support.reread(state)).artifact
        self.assertEqual(
            (artifact.tested_sha, artifact.tested_tree, artifact.target_head, artifact.review_subject),
            (support.TESTED_SHA, support.TESTED_TREE, support.REBASED_SHA, support.TESTED_SHA),
        )

    def test_the_settling_label_is_optional(self) -> None:
        # Optional, but never unreadable: a label nobody names is damage.
        state = _issue()
        pending = support.recorded(state)
        state.data = _settlement.settled_state(state, pending, support.ARTIFACT_COMMENT, None).data
        recorded = state.get(_records.EVIDENCE_HANDOFF)

        self.assertNotIn(_UNDER, recorded)
        self.assertIsNone(_settlement.read_evidence_handoff(state).settled_under)

        state.set(_records.EVIDENCE_HANDOFF, recorded | {_UNDER: "workflow:elsewhere"})

        self.assertIsNone(_settlement.read_evidence_handoff(state))

    def test_an_unwritten_member_is_damage(self) -> None:
        for key, member, damaged in _DAMAGE:
            with self.subTest(record=key, member=member):
                state = self._superseded()
                state.set(key, self._rewritten(state.get(key), member, damaged))

                self.assertIsNone(_READERS[key](state))

    def _superseded(self) -> PinnedState:
        """An issue whose second settlement superseded its first: every settled record held."""
        state = _issue()
        for _ in range(2):
            support.settles(state)
        return state

    def _rewritten(self, recorded: dict | list, member: str, damaged: object) -> dict | list:
        """`recorded` -- or the first entry of a history -- with one member replaced."""
        if isinstance(recorded, list):
            first = self._rewritten(recorded[0], member, damaged)
            return [first, *recorded[1:]]
        return recorded | {member: damaged}

    def _round_trips(self, pending: _records.PendingEvidence) -> None:
        """Record, settle, and retire `pending`, reading each record back off the comment."""
        state = _issue()

        self.assertTrue(_record_state.record_pending_evidence(state, pending))
        self.assertEqual(_record_state.read_pending_evidence(support.reread(state)), pending)

        support.settles(state, pending)
        settled = support.reread(state)

        self.assertFalse(_record_state.carries_pending_evidence(settled))
        self.assertEqual(_settlement.read_current_evidence(settled), support.current(pending))
        self.assertEqual(
            _settlement.read_evidence_handoff(settled),
            _records.EvidenceHandoff(
                receipt=pending.receipt,
                pr_number=support.PR_NUMBER,
                revision=pending.revision,
                target_head=support.TESTED_SHA,
                settled_under=support.SETTLED_UNDER,
            ),
        )

        _settlement.retire_current_evidence(state)

        self.assertEqual(
            _settlement.read_evidence_history(support.reread(state)),
            (_records.HistoricalEvidence.of(
                support.current(pending), _records.Retirement.INVALIDATED,
            ),),
        )


class RecordingTest(unittest.TestCase):
    """A record is accepted only where it reads back, publishes, and can settle."""

    def test_an_unpublishable_record_is_refused(self) -> None:
        for case, pending in self._refused().items():
            with self.subTest(case=case):
                state = _issue()
                before = dict(state.data)

                self.assertFalse(_record_state.record_pending_evidence(state, pending))
                self.assertEqual(state.data, before)

    def test_no_room_to_settle_refuses_the_record(self) -> None:
        # The settling write lands after the artifact is posted, and the
        # evidence it installs may later have to be invalidated, so a record
        # accepted into a comment either write overflows would leave a
        # transaction, or stale evidence, claiming the thread for good.
        pending = support.minted(PinnedState())
        room, growth = self._measured(pending)
        crowded = PinnedState(state_data={_FILLER: "y" * room})
        fitted = PinnedState(state_data={_FILLER: "y" * (room - growth)})

        self.assertGreater(growth, 0)
        self.assertFalse(_record_state.record_pending_evidence(crowded, pending))
        self.assertFalse(_record_state.carries_pending_evidence(crowded))
        self.assertFalse(_record_state.record_pending_evidence(
            PinnedState(state_data={_FILLER: "y" * (room - growth + 1)}), pending,
        ))
        # Measured over everything that follows rather than by a margin: room
        # for exactly that is enough, and the widest settlement that can land
        # -- its ledger entry included -- and the invalidation after it end at
        # exactly the ceiling.
        self.assertTrue(_record_state.record_pending_evidence(fitted, pending))
        self.assertEqual(self._landed(fitted, pending), MAX_PINNED_BODY)

    def test_a_spent_revision_or_receipt_is_refused(self) -> None:
        # A transaction minted before another settled shares that one's
        # revision, and recorded would publish a second artifact under it.
        state = _issue()
        stale = support.minted(state)
        settled = support.settles(state)
        before = copy.deepcopy(state.data)

        self.assertEqual(stale.revision, settled.revision)
        self.assertFalse(_record_state.record_pending_evidence(state, stale))
        # Nor may a later revision reuse a receipt a kept record carries.
        self.assertFalse(_record_state.record_pending_evidence(
            state, replace(settled, revision=settled.revision + 1),
        ))
        self.assertEqual(state.data, before)

    def test_a_retry_must_be_identical(self) -> None:
        # Its artifact may already be on the thread under that receipt, and a
        # record carrying anything else would no longer describe that post.
        state = _issue()
        first = support.recorded(state)
        changed = {
            "other commands": replace(first, commands=(support.ran("13 passed"),)),
            "another head": replace(first, binding=first.binding.retargeted(support.REBASED_SHA)),
        }

        self.assertTrue(_record_state.record_pending_evidence(state, first))
        for case, retry in changed.items():
            with self.subTest(case=case):
                self.assertFalse(_record_state.record_pending_evidence(state, retry))
        self.assertEqual(_record_state.read_pending_evidence(state), first)
        self.assertEqual(_settlement.read_evidence_history(state), ())

        # Not even identical once nobody can say which revisions were spent.
        state.set(_records.REVISION_FLOOR, None)

        self.assertFalse(_record_state.record_pending_evidence(state, first))

    def _refused(self) -> dict[str, _records.PendingEvidence]:
        """Each transaction a record refuses, by why."""
        headless = support.SUBJECT.recorded()
        headless.pop("sha")
        bindings = {
            "subject about another pull request": replace(support.TARGET, subject=_FOREIGN_SUBJECT),
            "subject under other requirements": replace(support.TARGET, subject=_UNREQUIRED_SUBJECT),
            "subject short of its head": replace(support.TARGET, subject=headless),
            "subject naming no report": replace(support.TARGET, subject=_UNREPORTED_SUBJECT),
        }
        refused = {
            case: support.minted(PinnedState(), support.binding(target=target))
            for case, target in bindings.items()
        }
        return refused | {
            "abbreviated tree": support.minted(
                PinnedState(), support.binding(tested_tree=_ABBREVIATED_TREE),
            ),
            "context that is no digest": support.minted(
                PinnedState(), support.binding(context_revision="v1"),
            ),
            "transcript UTF-8 cannot carry": support.minted(
                PinnedState(), commands=(support.ran(_LONE_SURROGATE),),
            ),
            "record past one comment": support.minted(
                PinnedState(), commands=(support.ran(_ESCAPED_TRANSCRIPT),),
            ),
            "artifact past one comment": support.minted(
                PinnedState(), commands=(support.ran(_filling_the_record()),),
            ),
            "revision past what is recorded": replace(
                support.minted(PinnedState()), revision=_BEYOND_RECORDED,
            ),
        }

    def _landed(self, state: PinnedState, pending: _records.PendingEvidence) -> int:
        """How long the pinned comment is once `pending` settles at its widest and is invalidated.

        The artifact's comment enters the ledger as the publication records
        it, and the settlement lands under the longest label there is.
        """
        landed = PinnedState(state_data=dict(state.data))
        _comments._track_orchestrator_comment(landed, _WIDEST_COMMENT)
        landed.data = _settlement.settled_state(
            landed, pending, _WIDEST_COMMENT, _WIDEST_LABEL,
        ).data
        self.assertLessEqual(len(pinned_state_body(landed.data)), MAX_PINNED_BODY)
        self.assertTrue(_settlement.retire_current_evidence(landed))
        return len(pinned_state_body(landed.data))

    def _measured(self, pending: _records.PendingEvidence) -> tuple[int, int]:
        """The room a bare filler leaves `pending`'s record, and the most what follows adds.

        What follows is its settlement and then the invalidation of the
        evidence that installs. The record itself fills that room exactly, so
        a refusal there is about what follows alone.
        """
        probe = PinnedState(state_data={_FILLER: ""})
        self.assertTrue(_record_state.record_pending_evidence(probe, pending))
        written = len(pinned_state_body(probe.data))
        lasting = PinnedState(state_data=_record_state.settled_payload(probe, pending))
        settling = len(pinned_state_body(lasting.data))
        self.assertTrue(_settlement.retire_current_evidence(lasting))
        invalidating = len(pinned_state_body(lasting.data))
        return MAX_PINNED_BODY - written, max(settling, invalidating) - written


class SettlementTest(unittest.TestCase):
    """A settlement is ONE write, composed on a copy, and refused whole."""

    def test_a_settlement_is_one_composed_write(self) -> None:
        state = _issue()
        first = support.settles(state)
        second = support.recorded(state)
        before = copy.deepcopy(state.data)

        settled = support.reread(_settlement.settled_state(
            state, second, support.ARTIFACT_COMMENT + 1, support.SETTLED_UNDER,
        ))

        self.assertEqual(state.data, before)
        self.assertEqual(
            (
                _record_state.read_pending_evidence(settled),
                _settlement.read_current_evidence(settled),
                _settlement.read_evidence_handoff(settled).receipt,
                _settlement.read_evidence_history(settled),
                settled.get("pr_number"),
            ),
            (
                None,
                support.current(second, support.ARTIFACT_COMMENT + 1),
                second.receipt,
                (_records.HistoricalEvidence.of(
                    support.current(first), _records.Retirement.SUPERSEDED,
                ),),
                support.PR_NUMBER,
            ),
        )

    def test_a_settlement_rewrites_its_own_comment(self) -> None:
        # Written through the pinned-state writer, the settled state has to
        # land on the comment the transaction was recorded on: a second state
        # comment would leave the pending record standing beside it.
        issue = make_issue(support.ISSUE_NUMBER)
        gh = FakeGitHubClient([issue])
        recording = PinnedState(state_data={"pr_number": support.PR_NUMBER})
        pending = support.recorded(recording)
        gh.write_pinned_state(issue, recording)

        gh.write_pinned_state(issue, _settlement.settled_state(
            gh.read_pinned_state(issue), pending, support.ARTIFACT_COMMENT, support.SETTLED_UNDER,
        ))

        settled = gh.read_pinned_state(issue)
        self.assertEqual(
            [comment.id for comment in issue.comments if PINNED_STATE_MARKER in comment.body],
            [recording.comment_id],
        )
        self.assertEqual(settled.comment_id, recording.comment_id)
        self.assertFalse(_record_state.carries_pending_evidence(settled))
        self.assertEqual(_settlement.read_current_evidence(settled), support.current(pending))

    def test_an_unrecordable_comment_settles_nothing(self) -> None:
        state = _issue()
        pending = support.recorded(state)

        for comment_id in (0, _BEYOND_RECORDED):
            with self.subTest(comment_id=comment_id):
                self.assertIsNone(_settlement.settled_state(
                    state, pending, comment_id, support.SETTLED_UNDER,
                ))
        self.assertEqual(_record_state.read_pending_evidence(state), pending)

    def test_only_the_recorded_transaction_settles(self) -> None:
        # One minted and never recorded raised no floor, and settling it would
        # drop the transaction that IS recorded; nor does a transaction settle
        # onto a comment recording none.
        owed = _issue()
        recorded = support.recorded(owed)
        cases = ((owed, support.minted(owed)), (_issue(), recorded))

        for state, pending in cases:
            with self.subTest(revision=pending.revision):
                self.assertIsNone(_settlement.settled_state(
                    state, pending, support.ARTIFACT_COMMENT, support.SETTLED_UNDER,
                ))


class HistoryTest(unittest.TestCase):
    """Current evidence retires into a bounded history; revisions never repeat."""

    def test_an_invalidation_keeps_it_whole(self) -> None:
        state = _issue()
        settled = support.settles(state)

        self.assertTrue(_settlement.retire_current_evidence(state))

        # Kept whole: the binding carries the report revision and digest and
        # the complete review subject, though the artifact names only the
        # subject's head.
        self.assertIsNone(_settlement.read_current_evidence(state))
        self.assertEqual(
            _settlement.read_evidence_history(support.reread(state)),
            (_records.HistoricalEvidence(
                receipt=settled.receipt,
                revision=settled.revision,
                binding=settled.binding,
                content_revision=settled.artifact.content_revision,
                passed=True,
                retired=_records.Retirement.INVALIDATED,
                comment_id=support.ARTIFACT_COMMENT,
            ),),
        )
        self.assertFalse(_settlement.retire_current_evidence(state))
        self.assertEqual(self._next_revision(state), settled.revision + 1)

    def test_a_later_record_abandons_the_earlier(self) -> None:
        state = _issue()
        first = support.recorded(state)
        second, sibling = [support.minted(state) for _ in range(2)]

        self.assertTrue(_record_state.record_pending_evidence(state, second))

        # Two mints over one state share a revision, never a receipt, and the
        # one recorded second is stale.
        self.assertEqual((second.revision, sibling.revision), (2, 2))
        self.assertNotEqual(second.receipt, sibling.receipt)
        self.assertFalse(_record_state.record_pending_evidence(state, sibling))
        self.assertEqual(_record_state.read_pending_evidence(state), second)
        # Abandoned whole, with no comment: none was confirmed for it.
        self.assertEqual(
            _settlement.read_evidence_history(support.reread(state)),
            (_records.HistoricalEvidence(
                receipt=first.receipt,
                revision=first.revision,
                binding=first.binding,
                content_revision=first.artifact.content_revision,
                passed=True,
                retired=_records.Retirement.ABANDONED,
            ),),
        )

    def test_an_abandoned_revision_is_never_reused(self) -> None:
        # Its artifact may already be on the thread under that revision.
        state = _issue()
        abandoned = support.recorded(state)

        self.assertTrue(_settlement.retire_pending_evidence(state, abandoned))

        self.assertFalse(_record_state.carries_pending_evidence(state))
        self.assertEqual(
            _settlement.read_evidence_history(state),
            (_records.HistoricalEvidence.of(abandoned, _records.Retirement.ABANDONED),),
        )
        self.assertEqual(self._next_revision(state), abandoned.revision + 1)

    def test_a_damaged_record_keeps_its_revision(self) -> None:
        # Its artifact may already be on the thread under that revision, and
        # the floor its own write raised says so once the record cannot.
        state = _issue()
        damaged = support.recorded(state)
        state.set(
            _records.PENDING_EVIDENCE,
            state.get(_records.PENDING_EVIDENCE) | {"tree": _ABBREVIATED_TREE},
        )
        later = support.minted(state)

        self.assertIsNone(_record_state.read_pending_evidence(state))
        self.assertEqual(later.revision, damaged.revision + 1)
        self.assertTrue(_record_state.record_pending_evidence(state, later))
        self.assertEqual(state.get(_records.REVISION_FLOOR), later.revision)

    def test_history_is_bounded_and_revisions_move_on(self) -> None:
        state = _issue()
        settled = [support.settles(state) for _ in range(_SETTLEMENTS)]

        self.assertEqual(
            [entry.revision for entry in _settlement.read_evidence_history(state)],
            list(range(_SETTLEMENTS - _HISTORY_KEPT, _SETTLEMENTS)),
        )
        self.assertEqual(_settlement.read_current_evidence(state).revision, _SETTLEMENTS)
        self.assertEqual(self._next_revision(state), _SETTLEMENTS + 1)
        # Its receipt evicted with it, the first transaction cannot come back
        # under a later revision: the receipt spells the one it was minted at.
        self.assertFalse(_record_state.record_pending_evidence(
            state, replace(settled[0], revision=_SETTLEMENTS + 1),
        ))


    def test_history_is_kept_in_revision_order(self) -> None:
        # A transaction abandoned before the evidence it would have superseded
        # retires ahead of it; the index still reads by revision.
        retiring = _issue()
        for _ in range(2):
            support.settles(retiring)
        abandoned = support.minted(retiring)
        self.assertTrue(_record_state.record_pending_evidence(retiring, abandoned))
        superseding = support.minted(retiring)
        self.assertTrue(_record_state.record_pending_evidence(retiring, superseding))

        support.settles(retiring, superseding)

        self.assertEqual(
            [
                (entry.revision, entry.retired)
                for entry in _settlement.read_evidence_history(support.reread(retiring))
            ],
            [
                (1, _records.Retirement.SUPERSEDED),
                (2, _records.Retirement.SUPERSEDED),
                (abandoned.revision, _records.Retirement.ABANDONED),
            ],
        )

    def _next_revision(self, state: PinnedState) -> int:
        """The revision the next transaction minted over `state` would carry."""
        return support.minted(state).revision


if __name__ == "__main__":
    unittest.main()
