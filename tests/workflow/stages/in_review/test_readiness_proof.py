# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The ready ping is taken only over current passing evidence, proved whole at the ping on either route.

A head qualified for the ping -- by the final-docs pass stamped on it, or by a
GitHub approval of it -- is announced only once the issue's current
verification evidence proves current there: the configured repository, the
pull request on its branch and standing on the head, the remote branch level
with it, the tested tree, the configured verification context, the applicable
review subject, the latest revision with its handoff describing it, and its
artifact still the one that settled. And it has to pass: every command
exiting 0, at least one of them, with the configured suite among them.

Anything of that moved -- before the tick, or while the gate asks GitHub about
the pull request -- pings nobody and writes nothing, and so does evidence that
is missing, failed, leaves the configured suite out, or records that nothing
ran, under any configuration. A reading the proof needs that stops answering
holds the ping the same way, and the ping follows once it answers. A ping an
earlier tick armed and never posted takes the same proof before it goes out.
And the proof is the last thing asked before any post: a push, a report edit,
or the artifact deleted behind the ping's arming or behind the reading its
settlement is prepared over -- on a first attempt or a recovered one -- still
pings nobody, with the arming left standing and nothing else written; so does
the pull request merged or closed while that last proof re-reads the artifact,
which leaves its head where it was and is seen by its state read last.
"""
from __future__ import annotations

import unittest
from functools import partial
from itertools import product
from types import MappingProxyType
from unittest.mock import MagicMock, patch

from orchestrator import config
from orchestrator.github.verification_evidence import VerifiedCommand
from orchestrator.workflow.state import WorkflowLabel
from tests.workflow.git_owners import seam_patch
from tests.workflow.stages.in_review import readiness_test_support as support, ready_ping_test_support as ping

# A repository other than the one the evidence was recorded against: the one the
# client is configured for, or the one a fork's head is built from.
ELSEWHERE = "octo/elsewhere"

# The client request the gate asks right before it decides the head is
# approved, which a late change lands behind.
_VETO = "pr_has_changes_requested"

# A command the configuration does not list.
_UNCONFIGURED = "uv run ruff check"

# Each thing the evidence is bound to, moved before the tick, beside the tick's
# own readings where those are what moved: the configured repository, a fork's
# head, another branch, a push, a remote branch standing past the head, another
# tree, the verification context, the review subject the evidence answers for,
# a later run recorded, a handoff that no longer describes the record, and the
# artifact edited or deleted.
_BINDINGS = (
    ("another repository", lambda case: setattr(case.github, "_repo_slug", ELSEWHERE), {}),
    ("a fork's head", lambda case: setattr(case.pull_request.head.repo, "full_name", ELSEWHERE), {}),
    ("another branch", lambda case: setattr(case.pull_request.head, "ref", "another-branch"), {}),
    ("a push", support.EvidenceMoves.pushes, {}),
    ("the branch past the head", None, {"fetched_branch_tip": support.PUSHED}),
    ("another tree", None, {"checkout_tree": support.OTHER_TREE}),
    ("a moved context", support.RecordEdits.moves_the_context, {}),
    ("no review subject", partial(support.RecordEdits.restates, review_returned_subject=None), {}),
    ("a later run recorded", support.RecordEdits.records_a_later_run, {}),
    ("no handoff", partial(support.RecordEdits.restates, verification_evidence_handoff=None), {}),
    ("an edited artifact", support.EvidenceMoves.edits_the_artifact, {}),
    ("a deleted artifact", support.EvidenceMoves.deletes_the_artifact, {}),
)

# Evidence nothing may be announced over, by what it carries: nothing recorded
# at all, a failed command, a passing run leaving the configured suite out, and
# a record that nothing ran.
_UNPASSING = (
    ("no evidence", None),
    ("a failed command", (VerifiedCommand(support.SUITE, 1, support.FAILED_OUTPUT),)),
    ("the suite left out", (VerifiedCommand(_UNCONFIGURED, 0, "ok"),)),
    ("nothing run", ()),
)

# Each of those on either route, with the approval's claim naming the evidence
# and with no claim recorded at all.
_UNPASSING_CASES = tuple(product(support.ROUTES, _UNPASSING, (True, False)))

# What lands while the gate asks GitHub about the pull request: a push, the
# issue edited, the report edited, the artifact edited or deleted, and the
# verification configuration changed.
_LATE = (
    ("a push", support.EvidenceMoves.pushes),
    ("an issue edit", support.EvidenceMoves.edits_the_issue),
    ("a report edit", support.EvidenceMoves.edits_the_report),
    ("an artifact edit", support.EvidenceMoves.edits_the_artifact),
    ("an artifact deletion", support.EvidenceMoves.deletes_the_artifact),
    ("a moved context", support.RecordEdits.moves_the_context),
)

# A reading that stops answering while the gate asks GitHub about the pull
# request, by the client request that then raises -- None for the pull
# request's thread, which a re-read of the artifact reports as unconfirmed --
# or by the tick's own git readings: a branch that would not compare, a tree
# read answering nothing, and git not started at all.
_UNREAD_REQUESTS = (None, "get_issue", "get_pr", "reread_verification_artifact")

_UNREAD_READINGS = (
    ("an uncompared branch", {"branch_divergence_readable": False}),
    ("an unread tree", {"checkout_tree": ""}),
    ("an unstarted git", {"checkout_tree": None}),
)

# What lands behind one of the ping's checkpoints, on either route: a push, a
# report edit, or the artifact deleted, behind the arming or behind the reading
# the settlement is prepared over -- the first patching the client's edit, the
# second its read of the pinned comment.
_CHECKPOINT_MOVES = (
    ("a push", support.EvidenceMoves.pushes),
    ("a report edit", support.EvidenceMoves.edits_the_report),
    ("an artifact deletion", support.EvidenceMoves.deletes_the_artifact),
)

_CHECKPOINTS = (
    ("arming", "edit_pinned_state", support.BehindTheArming),
    ("preparation", "read_pinned_state", support.BehindThePreparation),
)

# A merge or a close landing behind the last proof's first artifact re-read, on
# either route, on a first attempt -- seeded and armed on the tick -- or on a
# recovered one, armed by an earlier tick; and the terminal label each leaves.
_LATE_ENDS = tuple(product(
    support.ROUTES,
    (True, False),
    (("first", support._ReadinessFixture.seeded_on), ("recovered", support._ReadinessFixture.armed)),
))

_ENDED = MappingProxyType({True: WorkflowLabel.DONE, False: WorkflowLabel.REJECTED})

_ENDS = MappingProxyType({
    merged: partial(support.EvidenceMoves.ends_behind_the_next_artifact_read, merged=merged)
    for merged in (True, False)
})

# The window behind the reading the settlement is prepared over.
_PREPARATION = ("read_pinned_state", support.BehindThePreparation)

_BEHIND_THE_CHECKPOINTS = tuple(
    (route, f"{moved} behind the {checkpoint[0]}", checkpoint[1:], move)
    for route, checkpoint, (moved, move) in product(support.ROUTES, _CHECKPOINTS, _CHECKPOINT_MOVES)
)


class _DuringTheVeto:
    """The gate's veto request answered with no veto, `move` made on the case while GitHub answered it."""

    def __init__(self, case, move) -> None:
        self._case = case
        self._move = move

    def __call__(self, *_asked, **_options) -> bool:
        self._move(self._case)
        return False


class _Unanswered:
    """The client request `request` raising once stopped, until the case `answers` it -- the PR's thread, for None."""

    def __init__(self, request: str | None) -> None:
        self._request = request
        self._refused = None

    def __call__(self, case) -> None:
        if self._request is None:
            case.github.report_failures.unreadable.add(ping.PR)
            return
        unanswered = MagicMock(side_effect=RuntimeError("no answer"))
        self._refused = patch.object(case.github, self._request, unanswered)
        self._refused.start()

    def answers(self, case) -> None:
        """Answer the request again, as GitHub does once it recovers."""
        case.github.report_failures.unreadable.discard(ping.PR)
        if self._refused is not None:
            self._refused.stop()


def _unpassing(commands: tuple | None, *, claimed: bool):
    """The move leaving the current evidence carrying `commands` -- or none at all, for None -- `claimed` or not."""
    if commands is None:
        return partial(support.RecordEdits.drops_the_evidence, claimed=claimed)
    return partial(support.RecordEdits.rewrites_the_evidence, commands=commands, claimed=claimed)


class ReadinessProofTest(support._ReadinessFixture, unittest.TestCase):
    """What the ping needs of the evidence on either route, and that it pings nobody where that is not there."""

    def test_passing_evidence_pings_on_either_route(self) -> None:
        # Current, passing, and covering the configured suite: the head is
        # pinged once, armed and recorded, and a quiet tick after says nothing.
        for route in support.ROUTES:
            with self.subTest(route):
                self.seeded_on(route)

                self.tick()

                self.assert_settled()
                self.doCleanups()
                self.setUp()

    def test_a_moved_binding_withholds(self) -> None:
        for route, (name, moves, readings) in product(support.ROUTES, _BINDINGS):
            with self.subTest(route=route, moved=name):
                self.withheld_over(route, moves, **readings)

    def test_unpassing_evidence_withholds(self) -> None:
        # The record and its artifact each describe the other, so the evidence
        # proves current, and what its commands say is what refuses it --
        # whether the approval's claim names it, or the approval was never
        # held to any evidence at all.
        for route, (name, commands), claimed in _UNPASSING_CASES:
            with self.subTest(route=route, evidence=name, claimed=claimed):
                self.withheld_over(route, _unpassing(commands, claimed=claimed))

    def test_nothing_run_never_passes_unconfigured(self) -> None:
        # With no `VERIFY_COMMANDS` configured, a record that nothing ran
        # still covers the configuration -- and is still no evidence that
        # anything passed.
        for route, claimed in product(support.ROUTES, (True, False)):
            with self.subTest(route=route, claimed=claimed):
                self.enterContext(patch.object(config, "VERIFY_COMMANDS", ()))
                self.withheld_over(route, _unpassing((), claimed=claimed))


class LateReadinessTest(support._ReadinessFixture, unittest.TestCase):
    """What lands, or stops answering, while the gate decides, and a ping an earlier tick armed."""

    def test_a_late_change_withholds(self) -> None:
        # Each lands while GitHub answers the veto request, behind the head
        # the gate read and the drift and hand-back checks before it.
        for route, (name, move) in product(support.ROUTES, _LATE):
            with self.subTest(route=route, moved=name):
                self.seeded_on(route)
                before = self.standing()
                with patch.object(self.github, _VETO, _DuringTheVeto(self, move)):
                    self.tick()
                self.assert_withheld(before)
                self.doCleanups()
                self.setUp()

    def test_an_unread_request_holds(self) -> None:
        # Nothing is pinged or written while the request does not answer, and
        # the ping follows once it does.
        for route, request in product(support.ROUTES, _UNREAD_REQUESTS):
            with self.subTest(route=route, unread=request or "the thread"):
                unanswered = _Unanswered(request)
                self._held_over(route, _DuringTheVeto(self, unanswered))
                unanswered.answers(self)
                self._pinged_once_answered()

    def test_an_unread_git_reading_holds(self) -> None:
        # A branch that would not compare, a tree read answering nothing, or
        # git not started at all: held, and pinged once git answers.
        unstarted = MagicMock(side_effect=OSError("git was not started"))
        for route, (name, readings) in product(support.ROUTES, _UNREAD_READINGS):
            with self.subTest(route=route, unread=name), seam_patch("_tree_sha", unstarted):
                self._held_over(route, MagicMock(return_value=False), **readings)
            self._pinged_once_answered()

    def _held_over(self, route: str, veto, **readings) -> None:
        """Seed `route` and tick with `veto` answering the veto request, over `readings`: nothing pinged or written."""
        self.seeded_on(route)
        before = self.standing()
        with patch.object(self.github, _VETO, veto):
            self.tick(**readings)
        self.assert_withheld(before)

    def _pinged_once_answered(self) -> None:
        """With every reading answering again, the next tick pings once; the case is then set up afresh."""
        self.tick()
        self.assert_settled()
        self.doCleanups()
        self.setUp()


class CheckpointReadinessTest(support._ReadinessFixture, unittest.TestCase):
    """The proof taken once more behind the ping's checkpoints, the last thing asked before the post."""

    def test_a_move_behind_a_checkpoint_withholds(self) -> None:
        # A first attempt: the arming lands -- the one write the tick makes,
        # with no relabel -- and the move behind it, or behind the
        # settlement's reading, is seen by the proof taken right before the
        # post. Nothing is posted or recorded as pinged, and the tick after,
        # reading the thread without the ping, answers the move rather than
        # pinging: a report edit goes back for review, and a push or a
        # deleted artifact is announced over by nobody.
        for route, name, window, move in _BEHIND_THE_CHECKPOINTS:
            with self.subTest(route=route, moved=name):
                self.seeded_on(route)
                armed = self._armed_behind(window, move)
                self.tick()

                self.assertEqual(armed, (0, None, support.HEAD, 1, ()))
                self.assertEqual(self.standing()[:2], (0, None))
                self.doCleanups()
                self.setUp()

    def test_a_recovered_preparation_withholds(self) -> None:
        # A recovered attempt: the arming an earlier tick landed stands, the
        # thread reads without the ping, and the move lands behind the reading
        # the settlement is prepared over. Nothing is posted or written.
        for route, (name, move) in product(support.ROUTES, _CHECKPOINT_MOVES):
            with self.subTest(route=route, moved=name):
                self.armed(route)
                armed = self.standing()

                self._ticks_behind(_PREPARATION, move)

                self.assertEqual(self.standing(), armed)
                self.doCleanups()
                self.setUp()

    def test_an_unread_last_proof_holds(self) -> None:
        # The pull request's thread stops answering behind the arming: the
        # last proof cannot re-read the artifact, so nothing is posted, and
        # once it answers the next tick posts the ping under the receipt that
        # arming recorded.
        for route in support.ROUTES:
            with self.subTest(route):
                self.seeded_on(route)
                unanswered = _Unanswered(None)
                self._ticks_behind(("edit_pinned_state", support.BehindTheArming), unanswered)
                receipt = self.pinned()[ping.PENDING]["receipt"]
                self.assertEqual(self.pings(), [])
                unanswered.answers(self)

                self.tick()

                self.assert_settled(receipt)
                self.doCleanups()
                self.setUp()

    def test_a_late_end_holds_the_ping(self) -> None:
        # The pull request is merged or closed behind an artifact re-read of
        # the last proof, after that proof read it open: its head stays where
        # it was, so only the pull request's state read last sees the end.
        # Nothing is posted or recorded as pinged, and the next tick's
        # terminals finish the issue, pinging nobody.
        for route, merged, (attempt, seeds) in _LATE_ENDS:
            with self.subTest(route=route, merged=merged, attempt=attempt):
                seeds(self, route)
                held = self._armed_behind(_PREPARATION, _ENDS[merged])[:3]
                self.tick()

                self.assertEqual(held, (0, None, support.HEAD))
                self.assertEqual(self.pings(), [])
                self.assertEqual(self.github.label_history, [(ping.ISSUE, _ENDED[merged])])
                self.doCleanups()
                self.setUp()

    def _ticks_behind(self, window: tuple, move) -> None:
        """One tick with `move` made behind the checkpoint `window` names: the client request, and its double."""
        request, behind = window
        with patch.object(self.github, request, behind(self, move)):
            self.tick()

    def _armed_behind(self, window: tuple, move) -> tuple:
        """Tick with `move` behind `window`: pings, head pinged, head armed, writes made, and relabels.

        The pending record is told by the head it names, and the writes by how
        many this tick made.
        """
        writes = self.github.write_state_calls
        self._ticks_behind(window, move)
        standing = list(self.standing())
        standing[2] = standing[2]["sha"]
        standing[3] -= writes
        return tuple(standing)


class RecoveredReadinessTest(support._ReadinessFixture, unittest.TestCase):
    """A ping an earlier tick armed and never posted takes the whole proof before it goes out."""

    def test_a_recovered_ping_refuses_moved_evidence(self) -> None:
        # The ping is armed and its answer lost, so nothing is posted. Behind
        # it the artifact is deleted: the next tick reads the thread without
        # the ping, and the post it then owes is refused with the arming left
        # standing.
        for route in support.ROUTES:
            with self.subTest(route):
                self.armed(route)
                armed = self.standing()
                self.deletes_the_artifact()

                self.tick()

                self.assertEqual(self.standing(), armed)
                self.doCleanups()
                self.setUp()

    def test_an_unread_thread_holds_a_recovered_ping(self) -> None:
        # The same ping, and a pull-request thread nobody could read for the
        # artifact behind it: nothing is posted or written, and once it
        # answers the ping is posted under the receipt it was armed with.
        for route in support.ROUTES:
            with self.subTest(route):
                receipt = self.armed(route)
                armed = self.standing()
                unanswered = _Unanswered(None)
                unanswered(self)
                self.tick()
                self.assertEqual(self.standing(), armed)
                unanswered.answers(self)

                self.tick()

                self.assert_settled(receipt)
                self.doCleanups()
                self.setUp()


if __name__ == "__main__":
    unittest.main()
