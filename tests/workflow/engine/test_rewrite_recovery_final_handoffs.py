# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The tail of a landed base rewrite's finish, cut short behind its resolved evidence and finished by a later tick.

The real-git finish case (`rewrite_verification_recovery_support`): issue #7's
head rebased onto a moved base and pushed, and its finish killed at a final
handoff boundary (`rewrite_handoff_test_support`) once its evidence is
resolved -- a run of the configured command settled under the anchor, a failed
run's notice on the pull request, or nothing recorded where no reviewer was
handed the rebased head, the fresh reviewer owing the evidence. The next
tick's whole base refresh finishes it from the mark, the pull request, the
event stream, and the label the dead tick left: the head is announced once --
one notice and one `base_rebased` event, whichever boundary the tick died at --
relabelled once with one stage-entry event, its round reset, and the attempt
retired, with nothing run, posted, or settled again, nothing pushed, and no
developer launched; a later poll finds nothing left to do.
"""
from __future__ import annotations

import unittest
from functools import partial
from itertools import product
from typing import NamedTuple

from tests.workflow.engine import (
    rewrite_finish_git_support as git_support,
    rewrite_finish_readings as readings,
    rewrite_handoff_test_support as handoff,
    rewrite_verification_recovery_support as support,
    verification_evidence_test_support as _evidence_support,
)


def _hands_the_reviewer(case: support.CapturedRunCase) -> str:
    """Rebase and push the branch over the anchor with no reviewer handed the head; that head."""
    git_support.advances_the_base(case)
    return case.rebases_by_hand()


def _fails_its_run(case: support.CapturedRunCase) -> str:
    """Land a reviewed rebase on which the configured command fails; that head."""
    case.configures("echo 'test_rebased failed' && exit 3")
    return case.lands_a_reviewed_rebase()


class _Resolution(NamedTuple):
    """How a landed head's evidence is resolved before its tail: the landing, its runs, and whether its run failed."""

    name: str
    lands: object
    ran: int
    failed: bool


_RESOLUTIONS = (
    _Resolution("a run settled under the anchor", support.CapturedRunCase.lands_a_reviewed_rebase, 1, failed=False),
    _Resolution("a failed run's notice published", _fails_its_run, 1, failed=True),
    _Resolution("the evidence handed to the fresh reviewer", _hands_the_reviewer, 0, failed=False),
)

_VALIDATING = "validating"


class _HandoffCase(support.CapturedRunCase):
    """Issue #7's landed rebase finished up to a boundary, and read back as the next tick finds it."""

    def dies_finishing(self, head: str, boundary: handoff.Boundary | None) -> None:
        """Publish `head`'s finish, killed at `boundary` -- or run through, where there is none."""
        handoff.dies_at(self.gh, boundary, partial(self.finishes, head))

    def said(self) -> tuple:
        """What was said of the landings: the heads `base_rebased` names, how many announcements, and failed heads.

        The head each failure notice names is its first quoted span, short.
        """
        posted = readings.notices(self)
        failures = [notice for notice in posted if notice.startswith(":x:")]
        failed = [notice.split("`")[1] for notice in failures]
        return support.announced(self), len(posted) - len(failures), failed

    def assert_announced_once(self, head: str, *, failed: bool = False) -> None:
        """`head` announced, relabelled, and entered into `validating` once; a failure it `failed` noticed once."""
        failures = [head[:8]] if failed else []
        self.assertEqual(self.said(), ([head], 1, failures))
        routed = (readings.relabels(self), handoff.stage_entries(self.gh, git_support.ISSUE))
        self.assertEqual(routed, (readings.ROUTED, [_VALIDATING]))

    def assert_finished(self, ran: int) -> None:
        """The attempt retired with its round reset and no failure owed, `ran` runs, nothing pushed or launched."""
        pinned = readings.pinned(self)
        self.assertEqual(readings.attempt(pinned), readings.RETIRED)
        reset = (pinned[readings.KEY_REVIEW_ROUND], readings.failure(pinned))
        self.assertEqual(reset, (0, None))
        made = (self.runs(), self.pushes.call_count, self.developer.call_count)
        self.assertEqual(made, (ran, 0, 0))

    def resolved(self) -> tuple:
        """The pending, current, and retired evidence records the pinned comment carries, and the artifacts posted."""
        return readings.pinned_records(self), len(_evidence_support.posted_artifacts(self))


class FinalHandoffRecoveryTest(_HandoffCase, unittest.TestCase):
    """A tail cut short at any boundary is finished once by the next tick."""

    def test_each_boundary_finishes_once(self) -> None:
        # Whatever resolved the evidence and wherever the tail died, two later
        # polls leave one announcement, one relabel and stage entry, the
        # evidence exactly as resolved, and nothing run or published again.
        for resolution, boundary in product(_RESOLUTIONS, handoff.BOUNDARIES):
            with self.subTest(resolution=resolution.name, boundary=boundary.name):
                self.setUp()
                head = resolution.lands(self)
                self.dies_finishing(head, boundary)
                resolved = self.resolved()

                self.recovers()
                self.recovers()

                self.assert_announced_once(head, failed=resolution.failed)
                self.assertEqual(self.resolved(), resolved)
                self.assert_finished(resolution.ran)


if __name__ == "__main__":
    unittest.main()
