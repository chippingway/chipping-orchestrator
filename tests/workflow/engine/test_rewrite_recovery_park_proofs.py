# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""A captured run proved again before every recovery park that keeps its attempt, so no restoration revives it.

A finish recorded its run for the landed head and died posting its artifact, and the
next recovery parks rather than finish the landing, keeping the attempt -- and
the run with it -- for a human's reply: a fetch and an abort reset that both
fail, an issue relabelled out of the stages the refresh drives, whether the
refresh or the dispatcher's hold answers it, an issue that records another
pull request than the landing was made for, or an attempt whose record of its
replay no longer vouches for the landed head. Before each such park the run is
proved again over what can still be read, and abandoned where anything it is
bound to moved -- the configuration, the pull request -- so putting that back
and continuing routes the head with nothing the run carried, and the
reconciliation settles nothing. A run that still proves is kept, and routed
exactly as recorded once continued. Where no write could record the
abandonment, nothing is parked and the anchor still holds the run. Nothing
runs, pushes, or announces again, and no developer is launched.
"""
from __future__ import annotations

import contextlib
import subprocess
import unittest
from functools import partial
from unittest.mock import patch

from orchestrator.git import branch_transport, commands
from orchestrator.github.pinned_state import PinnedEdit
from orchestrator.workflow.engine import base_refresh, dispatch_guards, verification_durable
from tests.support.fakes import FakeLabel, FakePR, FakePRRef
from tests.workflow.engine import (
    rewrite_finish_git_support as git_support,
    rewrite_finish_readings as readings,
    rewrite_verification_recovery_support as support,
)

_GIT = "_git_hardened"

_FETCH = "_authed_fetch"

_RESOLVING = "workflow:resolving_conflict"

_MOVED_COMMAND = "echo another"

# What a recovery aborts behind, beside the step that fails and what it answers:
# the fetch of the pull request's branch, and the count of the checkout's lag
# against base, which the refresh answers with the same abort.
_ABORTS = (
    ("the fetch failed", branch_transport, _FETCH, subprocess.CompletedProcess([], 1, "", "refused")),
    ("the base lag was not counted", base_refresh, "_worktree_behind_base", None),
)

# Another pull request on the issue's branch, standing on the landed head, that
# the issue can be repointed to.
_REPOINTED_PR = 43

# What the issue or its attempt records differently from the landing, beside
# what it is moved to, the command configured meanwhile where one is, and
# whether the run captured for that landing still proves: the pull request the
# issue records is the one its binding names, while the stage the attempt was
# made from is not, and the replay it names is no part of the binding either,
# so a moved configuration is what refuses the run there.
_REPOINTED = (
    ("the issue's pull request", "pr_number", _REPOINTED_PR, None, False),
    ("the attempt's stage", readings.KEY_REWRITE_STAGE, "workflow:fixing", None, True),
    ("the attempt's replay, the configuration moved", readings.KEY_REWRITE_SHA, "5742a7c0" * 5, _MOVED_COMMAND, False),
)


def _refuses(original, refused, *called, **options):
    """Answer `original`, save a call `refused` names, which fails as git does."""
    if refused(called):
        return subprocess.CompletedProcess(called, 1, "", "refused")
    return original(*called, **options)


def _resets(called: tuple) -> bool:
    """Whether a git call resets the checkout."""
    return called[0] == "reset"


@contextlib.contextmanager
def _failing_abort(owner, step: str, answered):
    """Have `owner`'s `step` answer `answered`, failing into an abort, and that abort's reset fail, while entered."""
    reset = partial(_refuses, getattr(commands, _GIT), _resets)
    with (
        patch.object(owner, step, return_value=answered),
        patch.object(commands, _GIT, side_effect=reset),
    ):
        yield


@contextlib.contextmanager
def _unwritable(case: support.CapturedRunCase):
    """Have every write that records an abandonment on `case`'s comment fail, while this is entered."""
    unread = (None, verification_durable._UNREAD)
    with (
        patch.object(verification_durable, "durable_comment", return_value=unread),
        patch.object(case.gh, "edit_pinned_state", return_value=PinnedEdit.MOVED),
    ):
        yield


def _records(case: support.CapturedRunCase, key: str, recorded):
    """Record `recorded` as `key` on `case`'s pinned comment, as another road would; what `key` read before."""
    state = case.gh.read_pinned_state(case.issue)
    original = state.get(key)
    state.set(key, recorded)
    case.gh.write_pinned_state(case.issue, state)
    return original


def _held_by_the_dispatcher(case: support.CapturedRunCase) -> None:
    """Have the dispatcher's anchor hold answer `case`'s issue under the label it now wears."""
    label = case.gh.workflow_label(case.issue)
    state = case.gh.read_pinned_state(case.issue)
    dispatch_guards._anchor_holds_the_tick(case.gh, case._spec, case.issue, label, state)


# Who answers an anchor under a label the refresh does not drive: the refresh,
# and the dispatcher's hold.
_INELIGIBLE_ROUTES = (
    ("the refresh", lambda case: case.recovers()),
    ("the dispatcher's hold", _held_by_the_dispatcher),
)


class ParkProofRecoveryTest(support.CapturedRunCase, unittest.TestCase):
    """A captured run is proved again before a recovery park keeps it, and abandoned where it moved."""

    def test_a_failed_abort_proves_the_run(self) -> None:
        # The configuration moves, and the recovery fails into its abort --
        # behind a fetch that failed, or a lag against base nobody could count
        # -- whose reset fails too: the park keeps the attempt, so the run is
        # proved again before it and abandoned over the moved configuration.
        for aborted, *failing in _ABORTS:
            with self.subTest(aborted=aborted):
                self.setUp()
                head, run = self.captures()
                self.configures(_MOVED_COMMAND)
                with _failing_abort(*failing):
                    self.recovers()

                self._assert_parked(run, None)
                self.configures(support.CONFIGURED)
                self._continues_to(head, None)

    def test_an_ineligible_label_proves_the_run(self) -> None:
        # The configuration moves and the issue is relabelled out of the stages
        # the refresh drives: whoever answers the anchor, the stranded park is
        # taken only once the run is proved again and abandoned.
        for route, answers in _INELIGIBLE_ROUTES:
            with self.subTest(route=route):
                self.setUp()
                head, run = self.captures()
                self.configures(_MOVED_COMMAND)
                self.issue.labels = [FakeLabel(_RESOLVING)]
                answers(self)

                self._assert_parked(run, None)
                self.issue.labels = [FakeLabel(git_support.REVIEWING)]
                self.configures(support.CONFIGURED)
                self._continues_to(head, None)

    def test_a_misrecorded_landing_proves_the_run(self) -> None:
        # The recovery parks rather than finish a landing made for another
        # publication than the issue records, or one the attempt's record no
        # longer vouches for, and the run is proved again before that park.
        # Put back and continued, the head is routed with the run the proof
        # kept, exactly as recorded, and settled by the reconciliation -- or
        # with nothing the abandoned run carried.
        for repointed in _REPOINTED:
            with self.subTest(moved=repointed[0]):
                head, run = self._parks_repointed(*repointed[1:4])
                kept = run if repointed[4] else None

                self._assert_parked(run, kept)
                self._continues_to(head, kept)

    def test_an_unrecorded_abandonment_parks_nothing(self) -> None:
        # The configuration moves behind a failed fetch or an uncounted lag and a failed reset, and no write lands:
        # the run cannot be abandoned, so nothing is parked and the anchor still holds the run for the next recovery.
        for aborted, *failing in _ABORTS:
            with self.subTest(aborted=aborted):
                self.setUp()
                run = self.captures()[1]
                self.configures(_MOVED_COMMAND)
                posted = len(self.gh.posted_comments)
                with _failing_abort(*failing), _unwritable(self):
                    self.recovers()

                pinned = readings.pinned(self)
                self.assertEqual(len(self.gh.posted_comments), posted)
                self.assertIsNone(pinned.get("awaiting_human"))
                self.assertEqual(pinned[readings.KEY_PENDING_PUSH], self.anchor)
                self.assertEqual(readings.records(pinned)[0], run)

    def _parks_repointed(self, key: str, recorded_as, command: str | None) -> tuple:
        """A fresh case's captured run, recovered with `key` recording `recorded_as` and `command` configured.

        Both put back once that recovery parked. The head and the run.
        """
        self.setUp()
        repointed = FakePRRef(sha=self.anchor)
        self.gh.add_pr(FakePR(number=_REPOINTED_PR, head_branch=git_support.BRANCH, head=repointed))
        landed = self.captures()
        repointed.sha = landed[0]
        self.configures(command or support.CONFIGURED)
        original = _records(self, key, recorded_as)
        self.recovers()
        _records(self, key, original)
        self.configures(support.CONFIGURED)
        return landed

    def _assert_parked(self, run, kept) -> None:
        """The issue parked with its anchor standing, the run `kept` pending -- or, kept None, abandoned unrun."""
        pinned = readings.pinned(self)
        self.assertTrue(pinned.get("awaiting_human"))
        recorded = readings.records(pinned)
        self.assertEqual(pinned[readings.KEY_PENDING_PUSH], self.anchor)
        self.assertEqual(recorded[0], kept)
        if kept is None:
            retired = recorded[2][-1]
            self.assertEqual(retired, (run.receipt, readings.ABANDONED))
        self.assertEqual(self.runs(), 1)

    def _continues_to(self, head: str, kept) -> None:
        """Continue the park and recover: `head` routed, the reconciliation settling `kept` and nothing else."""
        self.continues()
        self.recovers()
        self.assert_recovered(head)
        self.reconciles()
        current = readings.pinned_records(self)[1]
        self.assertEqual(current and current.receipt, kept and kept.receipt)


if __name__ == "__main__":
    unittest.main()
