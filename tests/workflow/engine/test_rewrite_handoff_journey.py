# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""A pull request in review rebased twice, its report refreshed and reviewed between, each rebase's tail cut short.

The squash-rebase journey (`squash_rebase_journey_support`) walked into
review, then rebased onto `REBASED` over a base that changed what the branch
carries: the evidence the approval's squash carried is invalidated, nothing is
recorded for the rebased head -- no reviewer was handed it, so the fresh
reviewer owes its evidence -- and the developer is asked for the head's report,
the reviewer handed that report declares one result of the suite, and the docs
pass and the ping take the issue back into review. Then the base moves again
and the same happens at `ADVANCED`, its reviewer declaring a different result.
Each base refresh's tail is killed at one final handoff boundary
(`rewrite_handoff_test_support`) and finished by the next tick's recovery,
before any dispatch reads the issue.

Wherever both tails died, the journey ends as the uninterrupted one does: the
same runs spawned and charged -- a report refresh, a reviewer, and a docs pass
for each rebased head -- each rebase announced once and filed as `base_rebased`
once, the same stage entries, the second reviewer's run current with its own
transcript and tested head and the first's in history with its own, and every
reviewer handed the report of the head it reviews and no evidence, told to run
the verification itself.
"""
from __future__ import annotations

import unittest
from functools import partial
from types import MappingProxyType
from typing import NamedTuple

from orchestrator.workflow.engine import verification_settlement_state as _settlement
from tests.workflow.engine import rewrite_finish_readings as readings, rewrite_handoff_test_support as handoff
from tests.workflow.git_owners import seam_patch
from tests.workflow.stages.validating import (
    review_verdict_readings as _read,
    review_verdict_test_support as _world,
    squash_rebase_journey_support as _journey,
)

# The trees the rebased heads read as, each over a base that changed what the
# branch carries; every other commit reads as the tested one.
_TREES = MappingProxyType({
    _journey.REBASED: "d670460b4b4aece5915caf5c68d12f560a9fe3e4",
    _journey.ADVANCED: "e781571c5c5bfdf6026f27d6e73f6d23e5f4ab10",
})

# What each rebased head's reviewer saw the suite print.
_FIRST_OUTPUT = "12 passed in 1.80s"

_SECOND_OUTPUT = "13 passed, 1 skipped in 2.40s"

_RUN_IT_YOURSELF = "No current workflow verification evidence covers this subject, so run the verification yourself."

_HANDED_EVIDENCE = "Workflow verification evidence (revision"

_REBASED_EVENT = "base_rebased"

# What each rebased head's reviewer run is recorded as beside its revision,
# retirement, and head: the tree it tested, the witness, and what it printed.
_FIRST = (_TREES[_journey.REBASED], "reviewer-reported", _FIRST_OUTPUT)

_SECOND = (_TREES[_journey.ADVANCED], "reviewer-reported", _SECOND_OUTPUT)


def _tree_of(_worktree, revision: str) -> str:
    """The full tree `revision` reads as in the checkout."""
    return _TREES.get(revision, _world.TREE)


def _printed(artifact) -> tuple[str, str]:
    """The receipt `artifact` was posted under, and what it says its one command printed."""
    return artifact.receipt, artifact.commands[0].output


class _Record(NamedTuple):
    """One evidence record by what it is rather than by the receipt it was minted under.

    Its revision, why it retired ("current" for the current one), the head it
    tested and the tree, the witness, and what its artifact on the pull
    request says the suite printed.
    """

    revision: int
    retired: str
    tested: str
    tree: str
    witness: str
    printed: str | None

    @classmethod
    def of(cls, record, why: str, printed: dict) -> _Record:
        """`record` as it reads, retired for `why`, its output looked up in `printed` by receipt."""
        binding = record.binding
        return cls(
            revision=record.revision,
            retired=why,
            tested=binding.tested_sha,
            tree=binding.tested_tree,
            witness=binding.source.value,
            printed=printed.get(record.receipt),
        )


class _TwoAdvances(_journey._SquashRebaseJourney):
    """The journey into review and through two rebases, every tree read through `_tree_of` once in review."""

    def dispatched(self, *staged: tuple, **run_options) -> dict:
        """One whole dispatch, its trees read through the reading the case installed."""
        run_options.setdefault("checkout_tree", None)
        return super().dispatched(*staged, **run_options)

    def base_refresh(self, onto: str | None = None, **run_options) -> None:
        """One whole base refresh, its trees read through the reading the case installed."""
        run_options.setdefault("checkout_tree", None)
        super().base_refresh(onto, **run_options)

    def journeys(self, boundary: handoff.Boundary | None) -> dict:
        """Walk into review and through both rebases, each tail killed at `boundary`; what it all left (`_observed`)."""
        self.walks_into_review()
        self.enterContext(seam_patch("_tree_sha", _tree_of))
        for head, report, output in (
            (_journey.REBASED, _journey.REBASED_REPORT, _FIRST_OUTPUT),
            (_journey.ADVANCED, _journey.ADVANCED_REPORT, _SECOND_OUTPUT),
        ):
            handoff.dies_at(self.github, boundary, partial(self.base_refresh, head))
            self.base_refresh()
            self.dispatched(_journey.refresh(report))
            self.approved_into_review(head, output)
        self.dispatched()
        return self._observed()

    def _observed(self) -> dict:
        """What the journey left: runs and charges, what was said and entered, the evidence, the reviewers, the end."""
        pinned = self.pinned()
        pending = readings.records(pinned)[0]
        return {
            "runs": self.roles(),
            "charged": self.spent_since(self.charged),
            "said": self._said(),
            "stages": handoff.stage_entries(self.github, _world.ISSUE),
            "evidence": self._evidence(),
            "reviewers": self._reviewers(),
            "finished": (self.labels()[-1], pending, pinned[readings.KEY_PENDING_PUSH]),
        }

    def _said(self) -> tuple:
        """The heads `base_rebased` names, and how many announcements the pull request carries."""
        rebased = [event for event in self.github.recorded_events if event.get("event") == _REBASED_EVENT]
        filed = [event.get("sha") for event in rebased]
        posted = [body for _number, body in self.github.posted_pr_comments]
        return filed, sum(body.startswith(":mag:") for body in posted)

    def _evidence(self) -> list[_Record]:
        """Every evidence record, oldest first and the current one last."""
        state = self.github.read_pinned_state(self.issue)
        printed = dict(map(_printed, _read.artifacts(self)))
        history = _settlement.read_evidence_history(state) or ()
        described = [_Record.of(record, record.retired.value, printed) for record in history]
        return [*described, _Record.of(_settlement.read_current_evidence(state), "current", printed)]

    def _reviewers(self) -> list[tuple]:
        """Whether each reviewer was handed evidence or told to verify, and which rebased head's report it quotes."""
        reports = (_journey.REBASED_REPORT, _journey.ADVANCED_REPORT)
        return [
            (
                _HANDED_EVIDENCE in prompt,
                _RUN_IT_YOURSELF in prompt,
                [report for report in reports if f"> {report}" in prompt],
            )
            for prompt in self.spawned(_journey.REVIEWER)
        ]


class RewriteHandoffJourneyTest(_TwoAdvances, unittest.TestCase):
    """Both rebases' tails, cut short at any boundary, end the journey exactly as an uninterrupted one."""

    def test_every_boundary_ends_as_uninterrupted(self) -> None:
        # The uninterrupted journey is what every interrupted one is held to,
        # and it is checked whole first: two refreshes, two reviewers, two
        # docs passes, each charged once; each rebase announced once; the
        # second reviewer's run current and the first's invalidated with its
        # own head, tree, and output; and neither reviewer handed evidence.
        uninterrupted = self.journeys(None)
        self._assert_the_journey(uninterrupted)
        for boundary in handoff.BOUNDARIES:
            with self.subTest(boundary=boundary.name):
                self.setUp()
                self.assertEqual(self.journeys(boundary), uninterrupted)

    def _assert_the_journey(self, observed: dict) -> None:
        """`observed` is the uninterrupted journey: what ran and was charged, said, and left as evidence."""
        runs = observed["runs"]
        self.assertEqual(runs, (_journey.REFRESHER, _journey.REVIEWER, _journey.DOCUMENTER) * 2)
        self.assertEqual(observed["charged"][0], len(runs))
        self.assertEqual(observed["said"], ([_journey.REBASED, _journey.ADVANCED], 2))
        self.assertEqual(observed["stages"].count("validating"), 2)
        self._assert_reviewed(observed)

    def _assert_reviewed(self, observed: dict) -> None:
        """Each reviewer handed its own head's report and no evidence; each one's run recorded as its own."""
        first, second = observed["evidence"][-2:]
        self.assertEqual(first, _Record(3, "invalidated", _journey.REBASED, *_FIRST))
        self.assertEqual(second, _Record(4, "current", _journey.ADVANCED, *_SECOND))
        reports = [[_journey.REBASED_REPORT], [_journey.ADVANCED_REPORT]]
        self.assertEqual(observed["reviewers"], [(False, True, report) for report in reports])
        self.assertEqual(observed["finished"], ("in_review", None, None))


if __name__ == "__main__":
    unittest.main()
