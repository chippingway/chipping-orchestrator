# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Every move of an approval past its squash is held to the evidence the approval was proved over.

The approval records the claim it was proved over beside the subject it
covers, and the collapse record its squash puts down carries both. Past the
squash no proof of the evidence can be taken again, since the pull request
stands on a commit the evidence was never bound to, so each later move -- the
squash tail's relabel, the recovery that finishes a collapse an earlier tick
recorded, the merge gate's ready ping -- holds the approval to every part of
that proof the rewrite left standing (`approved_evidence.stands`): the claim
still naming the current record, with no revision past it spent, minted under
the verification context configured now, and its artifact, re-read on the pull
request it was published on, still the one that settled and passing.

A later revision settled -- failing, here -- or recorded and still owed is
evidence the approval was never given, and so is evidence minted under a
verification configuration that has since moved, or whose artifact is gone:
the move is not taken, and evidence a moved configuration left behind is
invalidated with the handoff over it. An artifact nobody could read holds the
move too.
"""
from __future__ import annotations

import unittest
from unittest.mock import patch

from orchestrator import config
from orchestrator.git.publication.models import _SquashOutcome
from orchestrator.workflow.late_split import collapses as _collapses, handoffs as _late_handoffs
from orchestrator.workflow.stages.documenting import handler as _documenting
from orchestrator.workflow.stages.implementing import late_collapse_state as _late_collapse_state
from tests.workflow.fixtures import _agent
from tests.workflow.repo_values import _TEST_SPEC
from tests.workflow.stages.validating import (
    approval_proof_test_support as _proof,
    review_verdict_readings as _read,
    review_verdict_test_support as _world,
)

# What the squash says it is about to collapse: the head it replaces, the
# base under it, and how many commits it counts.
COLLAPSED_HEAD = "aa11bb22" * 5

COLLAPSED_BASE = "cc33dd44" * 5

COLLAPSED = 3

IN_REVIEW = "in_review"

HANDED_BACK = (_world.ISSUE, "workflow:validating")

DONE = "done"

# The read of the evidence's artifact on the pull request, behind which another
# road records a later verification revision.
ARTIFACT_REREAD = "reread_verification_artifact"

# The highest verification revision this issue has spent, which a later
# transaction raises the moment it is recorded.
REVISION_FLOOR = "verification_evidence_revision"

READY_PING = "ready for review/merge"

# The squash that finishes the recorded collapse on the recovery tick,
# standing the pull request where it already stands.
_FINISHED = _SquashOutcome(success=True, sha=_world.HEAD, count=0)


def _records_a_revision_still_owed(case) -> None:
    """Another road recording a later run whose publication GitHub took without answering, so it is still owed."""
    case.github.report_failures.lost.add(_world.PR)
    _read.settles_evidence(case)
    case.github.report_failures.lost.discard(_world.PR)


def _records_behind_the_artifact(case) -> _world.AnotherRoadBehind:
    """The artifact's re-read, behind whose first answer another road records a later revision still owed."""
    return _world.AnotherRoadBehind(case, ARTIFACT_REREAD, bool, _records_a_revision_still_owed)


def _moves_the_configuration(case) -> None:
    """An operator adding a command to `VERIFY_COMMANDS` for the rest of the case."""
    case.enterContext(patch.object(config, "VERIFY_COMMANDS", (_world.SUITE, "uv run ruff check")))


class _RecordsItsCollapseThen:
    """A squash that records its collapse, behind which another road does `road`'s work, and then publishes."""

    def __init__(self, case, road) -> None:
        self._case = case
        self._road = road

    def __call__(self, gate, _branch, _pr_number) -> _SquashOutcome:
        _late_collapse_state._records_the_collapse(
            gate, head=COLLAPSED_HEAD, base_sha=COLLAPSED_BASE, count=COLLAPSED,
        )
        self._road(self._case)
        return _SquashOutcome(success=True, sha=_world.HEAD, count=COLLAPSED)


# The later verification revisions another road can land behind a recorded
# collapse: one settled that failed, and one recorded and still owed.
_LATER_REVISIONS = (
    ("a later failing revision", lambda case: _read.settles_evidence(case, exit_status=1)),
    ("a later revision still owed", _records_a_revision_still_owed),
)

# What leaves the pinned records standing and the evidence all the same no
# longer proved: a verification configuration moved, or the artifact deleted
# or unreadable on the pull request it was published on, which no rewrite of
# the branch touches.
_BESIDE_THE_RECORDS = (
    ("a moved verification configuration", _moves_the_configuration),
    ("a deleted artifact", _proof.deletes_the_artifact),
    ("an unread artifact", _proof.stops_reading_the_artifact),
)

# What another road does before the merge gate is asked, and whether the ready
# ping is taken over it.
_BEFORE_THE_PING = (
    ("nothing", lambda _case: None, True),
    ("a later revision still owed", _records_a_revision_still_owed, False),
    *((name, road, False) for name, road in _BESIDE_THE_RECORDS),
)


class SquashRecoveryTest(_proof.ApprovedVerdictWorld, unittest.TestCase):
    """The squash tail and the recovery behind it move the label only under evidence still standing."""

    def test_a_later_revision_holds_the_recovery(self) -> None:
        # The approval's tick records its collapse beside the approval and
        # its evidence, then stops once the later revision lands -- settled,
        # or recorded and still owed. The recovery finishes the collapse but
        # leaves the label where it is, with the handoff standing for the
        # next tick to drop.
        for name, road in _LATER_REVISIONS:
            with self.subTest(name):
                self.setUp()
                self.waits_on_settled_evidence()
                self.approves(squash_result=_RecordsItsCollapseThen(self, road))
                recorded = _collapses.LATE_COLLAPSE_HEAD in self.pinned()

                self._run_validating(self.github, self.issue, run_agent=[], squash_result=_FINISHED)

                self.assertTrue(recorded)
                self.assertEqual(self._handed(), ([], _world.HEAD))

    def test_unproved_evidence_holds_the_tail(self) -> None:
        # Nothing on the pinned comment moves, so the tail finishes the
        # squash -- but the evidence was minted under a verification context
        # no longer configured, or its artifact is gone from the pull request
        # or cannot be read there. The relabel is held either way. A moved
        # context proves the evidence answers for nothing: it is invalidated
        # and the handoff dropped in the tail's own write, for a fresh
        # reviewer. An artifact gone or unread leaves the handoff for the next
        # tick to drop or to ask again.
        for name, road in _BESIDE_THE_RECORDS:
            with self.subTest(name):
                self.setUp()
                self.waits_on_settled_evidence()

                self.approves(squash_result=_RecordsItsCollapseThen(self, road))

                invalidated = road is _moves_the_configuration
                self.assertEqual(self._handed(), ([], None if invalidated else _world.HEAD))
                self.assertEqual(_read.current_evidence_revision(self) is None, invalidated)

    def _handed(self) -> tuple:
        """Every relabel, and the squash handoff the pinned comment carries."""
        return (self.github.label_history, self.pinned().get(_late_handoffs.LATE_COLLAPSE_HANDOFF))


class MergeGateEvidenceTest(_proof.ApprovedVerdictWorld, unittest.TestCase):
    """The ready ping is taken only under an approval whose evidence still stands."""

    def test_the_ping_holds_to_the_evidence(self) -> None:
        for name, road, pinged in _BEFORE_THE_PING:
            with self.subTest(name):
                self.setUp()
                self.waits_on_settled_evidence()
                self.approves()
                self._documents()
                road(self)

                self._run_in_review(self.github, self.issue, run_agent=_agent())

                self.assertEqual(self._pinged(), (pinged, _world.HEAD if pinged else None))

    def test_a_revision_mid_check_holds_the_ping(self) -> None:
        # Another road records a later revision while the ping re-reads the
        # evidence's artifact. The pinned comment read last, ahead of the
        # ping's write, no longer carries the evidence records the check was
        # taken over: nobody is pinged, and the later revision's floor is not
        # written back over.
        self.waits_on_settled_evidence()
        self.approves()
        self._documents()

        with patch.object(self.github, ARTIFACT_REREAD, _records_behind_the_artifact(self)):
            self._run_in_review(self.github, self.issue, run_agent=_agent())

        floor = self.pinned()[REVISION_FLOOR]
        self.assertEqual((self._pinged(), floor), ((False, None), 2))

    def _documents(self) -> None:
        """What the documenting stage leaves when its pass needed no change, and the issue handed to `in_review`."""
        state = self.github.read_pinned_state(self.issue)
        state.set("docs_checked_sha", self.pull_request.head.sha)
        state.set("docs_verdict", "no_change")
        self.github.write_pinned_state(self.issue, state)
        self.github.apply_foreign_label(self.issue, IN_REVIEW)

    def _pinged(self) -> tuple:
        """Whether a ready ping went out, and the head the pinned comment records it for."""
        pings = [said for _, said in self.github.posted_comments if READY_PING in said]
        return (bool(pings), self.pinned().get("ready_ping_sha"))


class DocumentingEvidenceTest(_proof.ApprovedVerdictWorld, unittest.TestCase):
    """The docs pass runs only under an approval whose evidence still stands, and never ahead of a terminal."""

    def test_a_revision_mid_check_goes_back(self) -> None:
        # Another road records a later revision while the documenting stage's
        # opening re-reads the evidence's artifact. The comment read behind
        # it no longer carries the records the check was taken over, so the
        # issue goes back to `validating` before any docs pass, and the floor
        # stands.
        self.waits_on_settled_evidence()
        self.approves()

        with patch.object(self.github, ARTIFACT_REREAD, _records_behind_the_artifact(self)):
            ran = self._documents_a_tick()

        self.assertFalse(ran[_world.RUN_AGENT].called)
        self.assertEqual(self.github.label_history[-1], HANDED_BACK)
        self.assertEqual(self.pinned()[REVISION_FLOOR], 2)

    def test_merged_pr_finalizes_over_unread_evidence(self) -> None:
        # The terminals come ahead of the approval's reading: a pull request
        # merged while the issue sat on `documenting` finalizes to `done`
        # even where the evidence's artifact could not be read, which would
        # otherwise hold the tick forever on a pull request already landed.
        self.waits_on_settled_evidence()
        self.approves()
        self.pull_request.merged = True
        _proof.stops_reading_the_artifact(self)

        ran = self._documents_a_tick()

        self.assertFalse(ran[_world.RUN_AGENT].called)
        self.assertEqual(self.github.label_history[-1], (_world.ISSUE, DONE))

    def _documents_a_tick(self) -> dict:
        """One documenting tick over the issue as the comment carries it."""
        return self._run(
            lambda: _documenting._handle_documenting(self.github, _TEST_SPEC, self.issue), run_agent=_agent(),
        )


if __name__ == "__main__":
    unittest.main()
