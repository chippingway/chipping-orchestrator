# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""A captured run's recovery, while what it is proved against moves: the issue, and the base its replay sits on.

The recovery proves a captured run again over the issue and pinned comment
read afresh, and then takes the last word behind every request: the landing,
the head's standing on the base tip its replay was recorded as made onto, the
requirements, and the configuration, read once more. A base that moves while
the proof's requests are answered abandons the run and holds the route, and
once the base is back the next recovery routes the head with nothing run or
recorded; an issue edited, a checkout committed, or a configuration changed
meanwhile -- or while the last word reads the base again -- abandons the run
too, and a checkout that moved holds the route besides. A failure notice an earlier finish recorded, and a run a
recovery already abandoned, are held the same way to the base and the landing
behind the requests made for them. A base rewound under the head is told by
the tip the attempt recorded, not by counting what the head carries over it --
so a rebase that dropped commits the base had already taken is no cover for
it -- and an attempt that recorded no tip proves nothing. None of them runs the
captured command again, pushes the landed head again, or launches a developer.
"""
from __future__ import annotations

import unittest
from copy import copy
from functools import partial
from itertools import product
from unittest.mock import patch

from orchestrator.git import branch_transport
from orchestrator.git.base_sync import rewrite_facts
from tests.workflow.engine import (
    rewrite_finish_git_support as git_support,
    rewrite_finish_readings as readings,
    rewrite_verification_recovery_support as support,
)
from tests.workflow.interleaving import _RacesPastTheStep

_EDITED_BODY = "Also cover a base that moved twice."

_MAIN = "main"

_QUIET = "--quiet"

_REREAD = "reread_report_location"

_REMOTE_READ = "_remote_branch_read"

_STRAY_COMMIT = (
    "-c", "user.name=stray", "-c", "user.email=stray@example.invalid",
    "commit", _QUIET, "--allow-empty", "-m", "stray",
)

# What moves while the recovery re-reads the settled report a captured run is
# bound to, each read ahead of that request by the proof.
_MID_PROOF_MOVES = (
    ("the issue body was edited", lambda case: setattr(case.issue, "body", _EDITED_BODY), True),
    ("another command was configured", lambda case: case.configures("echo another"), True),
    ("the checkout committed past the head", lambda case: case._git(*_STRAY_COMMIT, cwd=case._wt), False),
)

# The requests a recovery's proof of a captured run, and the last word behind
# it, are answered over: the settled report re-read, and the base read again.
_PROOF_STEPS = (
    ("the settled report re-read", lambda case: case.gh, _REREAD),
    ("the base read again", lambda _case: rewrite_facts, "_standing_on_the_remote_base"),
)


def _captures(case: support.VerificationRecoveryCase) -> tuple:
    """Land a reviewed rebase whose finish records its run and dies at the relabel; the head, and that run."""
    head = case.lands_a_reviewed_rebase()
    case.dies_routing(partial(case.finishes, head))
    case.assertEqual(case.runs(), 1)
    return head, readings.pinned_records(case)[0]


def _once(owner, step: str, original, move) -> None:
    """Put `original` back as `owner`'s `step`, then make `move` -- so it races that step's first call only."""
    setattr(owner, step, original)
    move()


def _races(owner, step: str, move) -> None:
    """Have `move` happen once, just after `owner`'s `step` first answers."""
    original = getattr(owner, step)
    racer = _RacesPastTheStep(original, partial(_once, owner, step, original, move))
    setattr(owner, step, racer)


def _snapshot(case: support.VerificationRecoveryCase, _number: int):
    """`case`'s issue as a fetch hands it over: a copy that no later edit reaches."""
    return copy(case.issue)


def _commits(case: support.VerificationRecoveryCase, cwd, name: str, text: str) -> None:
    """Write `name` with `text` in `cwd` and commit it there."""
    (cwd / name).write_text(text)
    case._git("add", name, cwd=cwd)
    case._git("commit", _QUIET, "-m", f"add {name}", cwd=cwd, env_extra=case._author_env)


class LiveInputsRecoveryTest(support.VerificationRecoveryCase, unittest.TestCase):
    """A captured run is held, abandoned, or routed on what its issue and base read as once its proof is behind it."""

    def test_a_base_moved_mid_proof_abandons(self) -> None:
        # The base advances while the recovery re-reads the settled report
        # the captured run is bound to: the run proves, but the last word
        # reads the base elsewhere, so the run is abandoned unrun and nothing
        # is routed. The base is then put back on the tip the replay was made
        # onto: the next recovery finds the abandoned run, runs nothing again,
        # and routes the head with nothing recorded, pushed, or announced.
        head, captured = _captures(self)
        onto = self._git("rev-parse", f"refs/heads/{_MAIN}", cwd=self._remote).strip()
        _races(self.gh, _REREAD, partial(support.advances_the_base_again, self))

        self.recovers()

        self.assert_held(None)
        self._assert_abandoned(captured)
        self._git("update-ref", f"refs/heads/{_MAIN}", onto, cwd=self._remote)
        self.recovers()
        self._assert_abandoned(captured)
        self.assert_recovered(head)

    def test_a_move_around_the_proof_abandons(self) -> None:
        # The issue -- a snapshot, as a fetched issue is -- the configuration,
        # or the checkout moves while the proof re-reads the settled report,
        # or while the last word behind it reads the base again. Each is read
        # once more behind every request, so the run is abandoned unrun: the
        # head goes to the reviewer, unless the landing itself moved, which
        # holds it with nothing routed.
        for step, move in product(_PROOF_STEPS, _MID_PROOF_MOVES):
            with self.subTest(step=step[0], moved=move[0]):
                head, captured = self._moves_around_the_proof(step, move)

                self.recovers()

                self._assert_abandoned(captured)
                if move[2]:
                    self.assert_recovered(head)
                else:
                    self.assert_held(None)

    def test_a_rewind_past_dropped_commits_abandons(self) -> None:
        # Two topic commits were already in one upstream commit, so the
        # rebase dropped them and the head carries fewer commits over that
        # base than the anchor's own. The base is then rewound below that
        # upstream commit: the recorded tip says the head was replayed onto
        # a commit the base no longer is, so the captured run is abandoned.
        rewound = f"{self.anchor}^"
        self._carries_two_upstream_commits()
        head, captured = _captures(self)
        carried = self._git("rev-list", "--count", f"origin/{_MAIN}..{head}", cwd=self._wt)
        self.assertEqual(int(carried), 1)
        self._git("update-ref", f"refs/heads/{_MAIN}", rewound, cwd=self._remote)

        self.recovers()

        self._assert_abandoned(captured)
        self.assert_recovered(head)

    def test_an_unrecorded_base_tip_abandons(self) -> None:
        # An attempt recorded before the base tip was recorded with its
        # replay names none, which proves no base: the captured run is
        # abandoned unrun and the head goes to the reviewer.
        head, captured = _captures(self)
        self.state = self.gh.read_pinned_state(self.issue)
        self.state.set(readings.KEY_REWRITE_BASE, None)
        self.gh.write_pinned_state(self.issue, self.state)

        self.recovers()

        self._assert_abandoned(captured)
        self.assert_recovered(head)

    def _moves_around_the_proof(self, step: tuple, move: tuple) -> tuple:
        """A fresh case's captured run, `move` set to race the request `step` names; the head, and that run."""
        self.setUp()
        head, captured = _captures(self)
        owner, name = step[1](self), step[2]
        self.gh.get_issue = partial(_snapshot, self)
        self.enterContext(patch.object(owner, name, getattr(owner, name)))
        _races(owner, name, partial(move[1], self))
        return head, captured

    def _carries_two_upstream_commits(self) -> None:
        """Push two topic commits as the anchor, then a base commit carrying the feature and the first of them."""
        _commits(self, self._wt, "already.py", "already\n")
        _commits(self, self._wt, "survives.py", "survives\n")
        self.anchor = self._wt_head()
        self.pull_request.head.sha = self.anchor
        self._git("push", _QUIET, "origin", git_support.BRANCH, cwd=self._wt)
        self._git("checkout", _QUIET, _MAIN, cwd=self._work)
        (self._work / "feature.py").write_text("feature\n")
        self._git("add", "feature.py", cwd=self._work)
        _commits(self, self._work, "already.py", "already\n")
        self._git("push", _QUIET, "origin", _MAIN, cwd=self._work)

    def _assert_abandoned(self, captured) -> None:
        """Nothing pending or current, the settled evidence invalidated and `captured` abandoned, and no second run."""
        retired = (*git_support.invalidated(self), (captured.receipt, readings.ABANDONED))
        self.assertEqual(
            (readings.pinned_records(self), self.runs()),
            ((None, None, retired), 1),
        )


class RecordedDecisionBaseTest(support.VerificationRecoveryCase, unittest.TestCase):
    """A failure notice or an abandoned run an earlier finish recorded is held to the base, and never run again."""

    def test_a_failure_notice_waits_on_the_base(self) -> None:
        # The run failed: its notice is recorded and on the pull request, and
        # the tick died at the relabel. The base advances while the recovery
        # reads the conversation for that notice: nothing is posted, run, or
        # routed again, and the next recovery continues the head to a rebase.
        self.configures("echo 'test_rebased failed' && exit 3")
        head = self.lands_a_reviewed_rebase()
        self.dies_routing(partial(self.finishes, head))
        failed = readings.failure(readings.pinned(self))
        _races(self.gh, "pr_conversation_thread", partial(support.advances_the_base_again, self))

        self.recovers()

        self.assert_held(None)
        recorded = readings.failure(readings.pinned(self))
        self.assertEqual(
            (recorded, self.runs(), len(readings.notices(self))),
            (failed, 1, 2),
        )
        self._assert_continued(head)

    def test_an_abandoned_run_waits_on_the_base(self) -> None:
        # A recovery abandoned the captured run for a moved configuration and
        # died at its relabel. The base advances once the next recovery has
        # counted the head and is reading where the remote has the branch:
        # nothing is run or routed, and the recovery after that continues
        # the head to a rebase.
        head, captured = _captures(self)
        self.configures("echo another")
        self.dies_routing(self.recovers)
        self.enterContext(patch.object(branch_transport, _REMOTE_READ, branch_transport._remote_branch_read))
        _races(branch_transport, _REMOTE_READ, partial(support.advances_the_base_again, self))

        self.recovers()

        self.assert_held(None)
        retired = readings.pinned_records(self)[2]
        self.assertEqual(retired[-1], (captured.receipt, readings.ABANDONED))
        self._assert_continued(head)

    def test_a_failure_notice_waits_on_the_landing(self) -> None:
        # The checkout commits past the head while the recovery reads the
        # conversation for the recorded failure's notice: the landing it would
        # route no longer stands, so nothing is retired or relabelled, and
        # nothing is run or posted again.
        self.configures("echo 'test_rebased failed' && exit 3")
        head = self.lands_a_reviewed_rebase()
        self.dies_routing(partial(self.finishes, head))
        failed = readings.failure(readings.pinned(self))
        commits = partial(self._git, *_STRAY_COMMIT, cwd=self._wt)
        _races(self.gh, "pr_conversation_thread", commits)

        self.recovers()

        self.assert_held(None)
        recorded = readings.failure(readings.pinned(self))
        noticed = len(readings.notices(self))
        self.assertEqual(
            (recorded, self.runs(), noticed, support.announced(self)),
            (failed, 1, 2, [head]),
        )
        self.assertEqual((self.pushes.call_count, self.developer.call_count), (0, 0))

    def _assert_continued(self, head: str) -> None:
        """The next recovery rebases `head` once more and routes what it publishes, with nothing run again."""
        self.recovers()
        rebased = git_support.remote_head(self)
        attempt = readings.attempt(readings.pinned(self))
        self.assertEqual(
            (self.runs(), readings.relabels(self), attempt),
            (1, readings.ROUTED, readings.RETIRED),
        )
        self.assertEqual(
            (support.announced(self), self.pushes.call_count, self.developer.call_count),
            ([head, rebased], 1, 0),
        )


if __name__ == "__main__":
    unittest.main()
