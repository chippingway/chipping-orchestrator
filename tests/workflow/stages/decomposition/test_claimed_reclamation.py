# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""A snapshot's delete and its receipts, decided under every recorded consumer's writer claim.

The ref a split preserved goes once every consumer it records has ended, and
that is a decision about each of them: another poller on this host may be
writing any one, and a consumer whose pinned record admission refuses is one
this build cannot say the ref no longer matters to. So the delete takes every
consumer's claim in front of its last reading, holds each record read behind
those claims to admission, and keeps the claims through the delete and the
receipts behind it. A consumer refused there keeps the ref -- one closed on
`done` and an original the manifest no longer tracks alike -- and is told
nothing, even where an earlier pass's delete already took the ref, while a
supported consumer, or one with no pinned record at all, is reclaimed over as
ever. Driven through the two polls that reach a held ref: the umbrella's own,
and the sweep of an owner a human closed mid-cycle.
"""
from __future__ import annotations

import unittest
from itertools import product
from types import MappingProxyType

from orchestrator.workflow.late_split.obligations import LateResourceState
from tests.support.writer_claims import claimable, held_elsewhere
from tests.workflow.fixtures import _PatchedWorkflowMixin
from tests.workflow.stages.decomposition import (
    child_claim_test_support as _claims,
    late_cleanup_support as _support,
)
from tests.workflow.stages.decomposition.late_cleanup_support import (
    OwnerSeed,
    RecordedDelete,
    SeededUmbrella,
    SnapshotOutcome,
)

# The one consumer every owner here records.
_CONSUMER = _support.CHILD_NUMBER

_WARNING = "WARNING"

_KEY_SCHEMA_VERSION = "schema_version"

# A version this build does not admit, as a human's edit could leave it.
_ANOTHER_VERSION = MappingProxyType({_KEY_SCHEMA_VERSION: 2})

# The roads a pass takes to a ref whose one recorded consumer has ended,
# closed on `done`, each by the label its owner stands on and keeps while the
# ref is owed: the umbrella's terminal over the child it tracks, the same
# terminal once an edit's re-decomposition left that child an original the
# manifest no longer tracks, and the sweep of an owner a human closed mid-cycle.
_TERMINAL = "terminal"

_ORPHANED = "orphaned original"

_CLOSED_OWNER = "closed owner"

_ROADS = MappingProxyType({
    _TERMINAL: _support.UMBRELLA,
    _ORPHANED: _support.UMBRELLA,
    _CLOSED_OWNER: _support.DECOMPOSING,
})

# The consumer records a reclamation acts over, by whether each is fresh: one
# the split seeded, and none at all.
_ADMITTED = MappingProxyType({"supported": False, "fresh": True})

# How the delete lands, by the entry the ref stands at and what the remote
# answers: taken now, or by an earlier pass whose record of it was lost, which
# leaves the decision on the ledger over a ref the remote no longer has.
_DELETES = MappingProxyType({
    "now": (LateResourceState.RETAINED, SnapshotOutcome.DELETED),
    "earlier": (LateResourceState.RECLAIMING, SnapshotOutcome.ABSENT),
})


class _ReclamationCase(_PatchedWorkflowMixin):
    """An owner holding a ref its one recorded consumer has ended, and the poll that reaches it."""

    def _ended(
        self, road: str, *, snapshot: LateResourceState = LateResourceState.RETAINED, fresh: bool = False,
    ) -> SeededUmbrella:
        """An owner on `road` owing its branch and holding the ref at `snapshot`.

        `fresh` leaves the consumer with no pinned record at all.
        """
        seeded = _support.split_umbrella(
            LateResourceState.PENDING,
            snapshot=snapshot,
            owner=OwnerSeed(label=_ROADS[road], closed=road == _CLOSED_OWNER, child_ancestry=not fresh),
        )
        if road == _ORPHANED:
            seeded.replaced()
        return seeded

    def _walked(self, seeded: SeededUmbrella, road: str, remote: RecordedDelete) -> RecordedDelete:
        """Run the poll `road` reaches the owner by, the remote answering as `remote` says."""
        if road == _CLOSED_OWNER:
            return seeded.swept_by(self, remote)
        with remote.answering():
            _support.walk_owner(self, seeded)
        return remote

    def _refuse(self, seeded: SeededUmbrella, version) -> None:
        """Leave the consumer's record one admission refuses, keeping everything else it records."""
        recorded = seeded.github.pinned_data(_CONSUMER)
        recorded.pop(_KEY_SCHEMA_VERSION, None)
        seeded.github.seed_state(_CONSUMER, raw=True, **recorded, **version)

    def _receipts(self, seeded: SeededUmbrella) -> list[str]:
        """The comments posted on the consumer."""
        return [body for number, body in seeded.github.posted_comments if number == _CONSUMER]


class RefusedConsumerTest(_ReclamationCase, unittest.TestCase):
    """A ref whose one consumer holds a record admission refuses."""

    def test_a_refused_consumer_keeps_the_ref(self) -> None:
        # Otherwise reclaimable on every road, and refused under either
        # version admission does not take.
        for road, shape in product(_ROADS, _claims.UNADMITTED):
            with self.subTest(road=road, consumer=shape):
                self._kept_for(road, shape)

    def test_a_landed_delete_tells_it_nothing(self) -> None:
        # The delete landed and its record did not, so the entry reads
        # `reclaiming` over a ref the remote no longer has. Finishing that
        # needs no proof, but its receipt is an act on the consumer's issue:
        # the refused consumer is told nothing, and the entry stays owed
        # rather than reading as delivered, holding the umbrella open.
        for shape, version in _claims.UNADMITTED.items():
            with self.subTest(consumer=shape):
                seeded = self._ended(_TERMINAL, snapshot=LateResourceState.RECLAIMING)
                self._refuse(seeded, version)
                before = _claims.standing(seeded.github, _CONSUMER)

                with self.assertLogs(_support.WORKFLOW_LOG, level=_WARNING) as logged:
                    self._walked(seeded, _TERMINAL, RecordedDelete.absent())
                    self.assertTrue(_claims.said_refused(logged.output, _CONSUMER))

                self.assertEqual(
                    _support.resource_states(seeded.github)[_support.SNAPSHOT_REF], _support.STATE_RECLAIMING,
                )
                self.assertEqual(_claims.standing(seeded.github, _CONSUMER), before)
                self.assertFalse(seeded.parent.closed)

    def _kept_for(self, road: str, shape: str) -> None:
        """Walk an owner on `road` whose consumer `shape` refuses, and read back what it kept.

        The ref stays on the remote and the decision unfinished on the
        ledger, the consumer is written nothing and is said only locally, and
        the owner is not handed on -- while the branch, which owes no
        consumer anything, is reclaimed.
        """
        seeded = self._ended(road)
        self._refuse(seeded, _claims.UNADMITTED[shape])
        before = _claims.standing(seeded.github, _CONSUMER)

        with self.assertLogs(_support.WORKFLOW_LOG, level=_WARNING) as logged:
            deleted = self._walked(seeded, road, RecordedDelete(SnapshotOutcome.DELETED))
            self.assertTrue(_claims.said_refused(logged.output, _CONSUMER))

        self.assertEqual(deleted.refs, [], "the ref stays for whoever disposes of the record")
        self.assertEqual(_support.resource_states(seeded.github), {
            _support.SUPERSEDED_BRANCH: _support.STATE_RECONCILED,
            _support.SNAPSHOT_REF: _support.STATE_RECLAIMING,
        })
        self.assertEqual(_claims.standing(seeded.github, _CONSUMER), before)
        self.assertEqual(seeded.github.workflow_label(seeded.parent), _ROADS[road])


class AdmittedConsumerTest(_ReclamationCase, unittest.TestCase):
    """The controls: a consumer admission takes, on every road and however the delete lands."""

    def test_an_admitted_consumer_lets_it_go(self) -> None:
        for road, record, landing in product(_ROADS, _ADMITTED, _DELETES):
            with self.subTest(road=road, consumer=record, delete=landing):
                self._reclaimed_over(road, record, landing)

    def _reclaimed_over(self, road: str, record: str, landing: str) -> None:
        """Walk an owner on `road` over consumer `record`, the delete landing at `landing`.

        The entry reconciles, and a live cycle tells the consumer once -- a
        closed owner's cancelled one tells it nothing.
        """
        entry, answer = _DELETES[landing]
        seeded = self._ended(road, snapshot=entry, fresh=_ADMITTED[record])
        told = 0 if road == _CLOSED_OWNER else 1

        self._walked(seeded, road, RecordedDelete(answer, presence=answer))

        self.assertEqual(
            _support.resource_states(seeded.github)[_support.SNAPSHOT_REF], _support.STATE_RECONCILED,
        )
        self.assertEqual(len(self._receipts(seeded)), told)


class ClaimedConsumerTest(_ReclamationCase, unittest.TestCase):
    """The consumer claims a delete is decided and carried out under, at the umbrella's terminal."""

    def setUp(self) -> None:
        self.seeded = self._ended(_TERMINAL)

    def test_a_refusal_at_its_claim_keeps_the_ref(self) -> None:
        # The consumer carries the supported record its split seeded when the
        # pass begins -- the one the scan that qualified the ref stood over --
        # and a human's edit landing as its claim is granted leaves it
        # refused. The delete decides on the reading behind the claims: the
        # ref stays on the remote with the decision unfinished, the consumer
        # keeps the record the edit left, its thread, labels, and close, and
        # the umbrella stays open.
        self.assertTrue(self._supported(), "the pass begins over a supported record")
        before = _claims.standing(self.seeded.github, _CONSUMER)
        edited = {**before[0], **_ANOTHER_VERSION}

        with (
            _claims.EditedOnClaim(self._refused_on_claim).installed(),
            self.assertLogs(_support.WORKFLOW_LOG, level=_WARNING) as logged,
        ):
            deleted = self._walked(self.seeded, _TERMINAL, RecordedDelete(SnapshotOutcome.DELETED))
            self.assertTrue(_claims.said_refused(logged.output, _CONSUMER))

        after = _claims.standing(self.seeded.github, _CONSUMER)
        self.assertEqual(deleted.refs, [], "the ref stays for whoever disposes of the record")
        self.assertEqual(
            _support.resource_states(self.seeded.github)[_support.SNAPSHOT_REF], _support.STATE_RECLAIMING,
        )
        self.assertEqual(after, (edited, *before[1:]), "the consumer keeps what the edit left it")
        self.assertFalse(self.seeded.parent.closed)

    def test_an_admission_at_its_claim_lets_it_go(self) -> None:
        # The other way round: the record is refused when the pass begins,
        # and the edit landing as the claim is granted puts the supported one
        # back, so the ref goes and the consumer is told on that reading.
        self._refused_on_claim(_CONSUMER)
        self.assertFalse(self._supported(), "the pass begins over a refused record")

        with _claims.EditedOnClaim(self._admitted_on_claim).installed():
            deleted = self._walked(self.seeded, _TERMINAL, RecordedDelete(SnapshotOutcome.DELETED))

        self.assertEqual(deleted.refs, [_support.SNAPSHOT_REF])
        self.assertEqual(len(self._receipts(self.seeded)), 1)

    def test_the_claims_span_the_delete(self) -> None:
        # Another poller holding the consumer keeps the ref this pass, the
        # consumer told nothing. Once it lets go, the claim is taken in front
        # of the reading, kept from every other poller while the remote is
        # asked, and given back once the pass is over.
        with held_elsewhere(self.seeded.github.repo_id, _CONSUMER), self.assertLogs(_support.WORKFLOW_LOG):
            held = self._walked(self.seeded, _TERMINAL, RecordedDelete(SnapshotOutcome.DELETED))

        self.assertEqual(held.refs, [])
        self.assertEqual(self._receipts(self.seeded), [])

        noting = _ClaimNotingDelete(self.seeded.github.repo_id)
        self._walked(self.seeded, _TERMINAL, noting)

        self.assertEqual(noting.refs, [_support.SNAPSHOT_REF])
        self.assertEqual(noting.claimable_during, [False])
        self.assertEqual(len(self._receipts(self.seeded)), 1)
        self.assertTrue(claimable(self.seeded.github.repo_id, _CONSUMER, elsewhere=True))

    def _refused_on_claim(self, number: int) -> None:
        """Leave the consumer's record one admission refuses, as a human's edit would; any other is left."""
        if number == _CONSUMER:
            self._refuse(self.seeded, _ANOTHER_VERSION)

    def _admitted_on_claim(self, number: int) -> None:
        """Leave the consumer's record a supported one, everything else it records kept; any other is left."""
        if number == _CONSUMER:
            recorded = self.seeded.github.pinned_data(_CONSUMER)
            recorded.pop(_KEY_SCHEMA_VERSION, None)
            self.seeded.github.seed_state(_CONSUMER, **recorded)

    def _supported(self) -> bool:
        """Whether the consumer's record reads as one admission takes right now."""
        github = self.seeded.github
        return github.read_pinned_state(github.get_issue(_CONSUMER)).supported


class _ClaimNotingDelete(RecordedDelete):
    """A delete that notes, as the remote is asked, whether another poller could take the consumer's claim."""

    def __init__(self, repo_id: int) -> None:
        super().__init__(SnapshotOutcome.DELETED)
        self._repo_id = repo_id
        self.claimable_during: list[bool] = []

    def __call__(self, spec, cwd, *, ref: str, sha: str):
        """Note the consumer's claim, then answer as the remote would."""
        self.claimable_during.append(claimable(self._repo_id, _CONSUMER, elsewhere=True))
        return super().__call__(spec, cwd, ref=ref, sha=sha)


if __name__ == "__main__":
    unittest.main()
