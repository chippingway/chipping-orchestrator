# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""A captured run's recovery, while what it is proved against moves: the issue, and the base its replay sits on.

The recovery proves a captured run again over the issue and pinned comment
read afresh, the requirements read once more behind the proof's own requests,
and only then the head's standing on the base tip its replay was recorded as
made onto. A base that moves while the proof's requests are answered holds the
route, and the next recovery continues the head to another rebase; an issue
edited meanwhile abandons the run. A base rewound under the head is told by
the tip the attempt recorded, not by counting what the head carries over it --
so a rebase that dropped commits the base had already taken is no cover for
it -- and an attempt that recorded no tip proves nothing. None of them runs the
captured command again, pushes the landed head again, or launches a developer.
"""
from __future__ import annotations

import unittest
from copy import copy
from functools import partial

from tests.workflow.engine import (
    rewrite_finish_git_support as git_support,
    rewrite_finish_readings as readings,
    rewrite_verification_recovery_support as support,
)
from tests.workflow.interleaving import _RacesPastTheStep

_EDITED_BODY = "Also cover a base that moved twice."

_MAIN = "main"

_QUIET = "--quiet"


def _captures(case: support.VerificationRecoveryCase) -> tuple:
    """Land a reviewed rebase whose finish records its run and dies at the relabel; the head, and that run."""
    head = case.lands_a_reviewed_rebase()
    case.dies_routing(partial(case.finishes, head))
    case.assertEqual(case.runs(), 1)
    return head, readings.pinned_records(case)[0]


def _once_read(case: support.VerificationRecoveryCase, reread, move) -> None:
    """Put `reread` back on `case`'s client, then make `move` -- after the first settled report re-read only."""
    case.gh.reread_report_location = reread
    move()


def _commits(case: support.VerificationRecoveryCase, cwd, name: str, text: str) -> None:
    """Write `name` with `text` in `cwd` and commit it there."""
    (cwd / name).write_text(text)
    case._git("add", name, cwd=cwd)
    case._git("commit", _QUIET, "-m", f"add {name}", cwd=cwd, env_extra=case._author_env)


class LiveInputsRecoveryTest(support.VerificationRecoveryCase, unittest.TestCase):
    """A captured run is held, abandoned, or routed on what its issue and base read as once its proof is behind it."""

    def test_a_base_moved_mid_proof_holds(self) -> None:
        # The base advances while the recovery re-reads the settled report
        # the captured run is bound to: the run proves, but the head no
        # longer stands where it was counted, so nothing is routed. The next
        # recovery counts it behind the base, abandons the run unrun, and
        # the tick's rebase publishes and routes the next head.
        head, captured = _captures(self)
        self._races_the_proof(partial(support.advances_the_base_again, self))

        self.recovers()

        self.assert_held(captured)
        self.recovers()
        rebased = git_support.remote_head(self)
        self._assert_abandoned(captured)
        self.assertEqual(readings.relabels(self), readings.ROUTED)
        self.assertEqual(
            (support.announced(self), self.pushes.call_count, self.developer.call_count),
            ([head, rebased], 1, 0),
        )

    def test_an_issue_edited_mid_proof_abandons(self) -> None:
        # The issue's body is edited while the recovery re-reads the settled
        # report, and the issue read ahead of the proof is a snapshot that
        # cannot show it: the requirements read again behind the proof do,
        # so the run is abandoned unrun and the head goes to the reviewer.
        head, captured = _captures(self)
        self.gh.get_issue = lambda _number: copy(self.issue)
        self._races_the_proof(partial(setattr, self.issue, "body", _EDITED_BODY))

        self.recovers()

        self._assert_abandoned(captured)
        self.assert_recovered(head)

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

    def _races_the_proof(self, move) -> None:
        """Have `move` happen once, just after the recovery first re-reads a settled report."""
        reread = self.gh.reread_report_location
        self.gh.reread_report_location = _RacesPastTheStep(reread, partial(_once_read, self, reread, move))

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


if __name__ == "__main__":
    unittest.main()
