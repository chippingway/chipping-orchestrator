# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""A returned reviewer's verdict, finished on a later tick from what it persisted.

The verdict is written before its evidence is published or the verdict acted
on, so a publication GitHub accepted and never confirmed holds the tick with
the verdict waiting. The next tick finds the artifact by its receipt rather
than posting it again, and finishes the verdict with no second reviewer, no
second fold of the reviewer's usage, no extra agent run charged, and no round
spent -- and hands a change request to exactly one developer. A verdict whose
subject moved in between is dropped, and that same tick hands a fresh
reviewer the subject as it stands.
"""
from __future__ import annotations

import unittest
from dataclasses import replace

from tests.workflow import published_reports as _published_reports
from tests.workflow.engine import usage_frames as _usage_frames
from tests.workflow.fixtures import (
    LABEL_DOCUMENTING,
    LABEL_FIXING,
    LABEL_VALIDATING,
    ROLE_DEVELOPER,
    ROLE_REVIEWER,
    _agent,
    _reported,
)
from tests.workflow.stages.validating import (
    review_evidence_readings as _read,
    review_evidence_test_support as _world,
)
from tests.workflow.stages.validating.validating_review_test_support import FIX_HEAD_SHAS

# What the issue has folded of its agents' usage, as their output reported it.
ISSUE_RUNS = "issue_agent_runs"

ISSUE_TOKENS = "issue_total_tokens"

# The members of the persisted verdict and of the evidence it claims.
EVIDENCE = "evidence"

RECEIPT = "receipt"

REQUESTED = "1. The suite fails on the empty configuration; handle it."

LATER_REPORT = "Covered the empty configuration as well; the suite passes."

# A reviewer asking for that change beside its declared run, which failed.
REQUESTING = _world.declared_run(exit_status=1, verdict="CHANGES_REQUESTED").replace(
    "Reviewed the diff and the report.", REQUESTED,
)

DOCUMENTING = (_world.ISSUE, LABEL_DOCUMENTING)


def _spent(case) -> tuple:
    """What the issue has spent so far: runs charged, usage folded, rounds."""
    pinned = case.pinned()
    return (
        pinned[_world.AGENT_RUNS_USED],
        pinned[ISSUE_RUNS],
        pinned[ISSUE_TOKENS],
        pinned[_world.REVIEW_ROUND],
    )


def _charged(case) -> tuple:
    """The runs charged and folded, and the rounds spent, so far."""
    runs, issue_runs, _, rounds = _spent(case)
    return (runs, issue_runs, rounds)


def _spawned(case) -> tuple:
    """How many reviewers and developers the issue has spawned."""
    return (_read.spawns(case, ROLE_REVIEWER), _read.spawns(case, ROLE_DEVELOPER))


class _HeldPublication(_world.ReviewEvidenceWorld):
    """Reviewer runs that report usage, over a pull request losing its responses."""

    def reviewer(self, message: str):
        """A reviewer run whose output also reports the usage it ran up."""
        return replace(super().reviewer(message), stdout=_usage_frames._codex_stdout_no_model())

    def held(self, message: str) -> dict:
        """The verdict `message` leaves waiting once its post lands and its response is lost."""
        self.github.report_failures.lost.add(_world.PR)
        self.dispatched(self.reviewer(message))
        self.github.report_failures.lost.discard(_world.PR)
        return self.pinned()[_world.RETURNED_VERDICT]


class HeldApprovalTest(_HeldPublication, unittest.TestCase):
    """An approval held on its publication is finished without a second reviewer."""

    def test_the_next_tick_finishes_the_approval(self) -> None:
        waiting = self.held(_world.declared_run())
        self.assertEqual(
            (
                waiting["verdict"],
                waiting[EVIDENCE]["use"],
                waiting[EVIDENCE]["passed"],
                self.pinned()[_world.PENDING_EVIDENCE] is not None,
                self.github.label_history,
            ),
            ("approved", "published", True, True, []),
        )
        spent = _spent(self)

        finished = self.dispatched()

        # The artifact that landed is found rather than posted again, and
        # settled; the approval goes on from the verdict the first tick wrote.
        self.assertEqual(
            (
                len(_read.artifacts(self)),
                _read.current_evidence(self).receipt,
                finished[_world.RUN_AGENT].call_count,
                _spawned(self),
                _spent(self),
            ),
            (1, waiting[EVIDENCE][RECEIPT], 0, (1, 0), spent),
        )
        self.assertEqual(
            (self.github.label_history[-1], self.pinned()[_world.RETURNED_VERDICT]),
            (DOCUMENTING, None),
        )


class HeldChangeRequestTest(_HeldPublication, unittest.TestCase):
    """A change request held on its publication reaches exactly one developer."""

    def test_one_developer_answers_it(self) -> None:
        waiting = self.held(REQUESTING)
        self.assertEqual(
            (REQUESTED in waiting["feedback"], _spawned(self), self.github.label_history),
            (True, (1, 0), []),
        )
        charged, folded, _ = _charged(self)

        fixed = self.dispatched(
            _agent(session_id=_world.DEV_SESSION, last_message=_reported("fixed")),
            dirty_files=(),
            push_branch=True,
            head_shas=FIX_HEAD_SHAS,
        )

        run = fixed[_world.RUN_AGENT].call_args
        self.assertEqual(
            (
                _spawned(self),
                run.kwargs.get("resume_session_id"),
                REQUESTED in run.args[1],
            ),
            ((1, 1), _world.DEV_SESSION, True),
        )
        self.assertEqual(
            self._published(), (1, True, 1),
            "the feedback is posted once, and the failing run published as what it was",
        )
        # One developer run charged and folded on top of the reviewer's, which
        # is folded once, and the round its pushed fix spends is the only one.
        self.assertEqual(
            _charged(self),
            (charged + 1, folded + 1, 1),
        )
        self.assertEqual(
            self.github.label_history,
            [(_world.ISSUE, LABEL_FIXING), (_world.ISSUE, LABEL_VALIDATING)],
        )

    def _published(self) -> tuple:
        """The feedback posts, whether they carry the request, and the exit the artifact reports."""
        feedback = _read.pr_comments(self, "requested changes")
        artifact = _read.artifacts(self)[0]
        return (
            len(feedback),
            REQUESTED in feedback[0],
            artifact.commands[0].exit_status,
        )


class MovedSubjectTest(_HeldPublication, unittest.TestCase):
    """A verdict whose subject moved before it was finished is dropped, not acted on."""

    def test_a_later_report_gets_a_fresh_reviewer(self) -> None:
        # The approval waits on its publication, and a later report settles
        # on the same head meanwhile: the waiting approval is of words the
        # pull request no longer carries. The next tick drops it and hands a
        # fresh reviewer the later report, whose own evidence abandons the
        # earlier transaction into history.
        first = self.held(_world.declared_run())[EVIDENCE][RECEIPT]
        _published_reports.republishes_the_report(self.github, self.issue, LATER_REPORT)

        ran = self.dispatched(self.reviewer(_world.declared_run()))

        pinned = self.pinned()
        self.assertEqual(
            (
                ran[_world.RUN_AGENT].call_count,
                f"> {LATER_REPORT}" in _read.prompt(ran),
                pinned[_world.APPROVED_SUBJECT]["report_revision"],
                [(entry[RECEIPT], entry["retired"]) for entry in pinned["verification_evidence_history"]],
            ),
            (1, True, 2, [(first, "abandoned")]),
        )
        self.assertEqual(
            (
                _read.current_evidence(self).receipt == first,
                len(_read.pr_comments(self, _world.APPROVAL_NOTICE)),
                self.github.label_history[-1],
            ),
            (False, 1, DOCUMENTING),
        )


if __name__ == "__main__":
    unittest.main()
