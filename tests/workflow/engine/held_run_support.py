# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Issue #7's settled run, its finish killed at a final handoff, and the moves a hold, park, or continuation proves.

The real-git settled route case (`settled_route_support`) the hold-proof
modules share: a reviewed rebase whose run settles under the anchor and whose
finish dies at a handoff boundary (`HoldCase.settles_then_dies`), a record or
the issue written beside it, a base advanced without changing a tree, and
report 3 of the head settled while a notice is posted
(`HoldCase.settles_under_the_notice`) -- a direct finish, or a whole recovery
-- with what it moved put back after. A case reads back the run invalidated
whole (`HoldCase.assert_invalidated`) or the head continued once.
"""
from __future__ import annotations

from functools import partial
from unittest.mock import patch

from orchestrator.workflow.engine import rewrite_finish_writes as _writes
from orchestrator.workflow.engine.rewrite_finish_models import FinishOutcome, FinishRoad
from tests.workflow.engine import (
    rewrite_finish_readings as readings,
    rewrite_handoff_test_support as handoff,
    rewrite_verification_recovery_support as support,
    settled_route_support as route,
    verification_report_fixture as _report,
)
from tests.workflow.interleaving import _RacesPastTheCall, _RacesPastTheStep

EDITED_BODY = "Also cover a base that moved twice."

# The report and review records report 3's settlement moves, as the pinned comment spells them.
MOVED_RECORDS = (
    "developer_report_current",
    "developer_report_handoff",
    "review_subject",
    "review_returned_subject",
)

# Room on the pinned comment for the run's history entry and the park behind
# it, and short of the landing's report debt and the announcement it rides.
SHORT_OF_THE_DEBT = 250

QUIET = "--quiet"


def settles_a_later_report(case: route.SettledRouteCase, head: str, replaced: list) -> None:
    """Settle and review report 3 of `head` as another road would, keeping in `replaced` the records it moves."""
    pinned = readings.pinned(case)
    replaced.append({key: pinned.get(key) for key in MOVED_RECORDS})
    case.state = case.gh.read_pinned_state(case.issue)
    _report.settles_report(case, 3, "Implemented the change and covered a base that moved twice.", head=head)
    case.gh.write_pinned_state(case.issue, case.state)


def loses_the_answer(moves) -> None:
    """Make `moves`, then lose the answer of the request it was made behind."""
    moves()
    raise RuntimeError("the answer was lost")


class HoldCase(route.SettledRouteCase):
    """Issue #7's settled run, its direct finish killed, and what the attempt and the run read back as."""

    def settles_then_dies(self, boundary: handoff.Boundary = handoff.BEFORE_THE_ANNOUNCEMENT) -> str:
        """Land a reviewed rebase and settle its run, its finish killed at `boundary`; the head, the run kept."""
        head = self.lands_a_reviewed_rebase()
        handoff.dies_at(self.gh, boundary, partial(self.finalizes, head, FinishRoad.PUBLICATION))
        self.settled = readings.pinned_records(self)[1]
        return head

    def writes_beside(self, key: str, record, body: str) -> tuple:
        """Write `record` as `key` and `body` as the issue's; the record and body they replaced."""
        state = self.gh.read_pinned_state(self.issue)
        replaced = (key, state.get(key), self.issue.body)
        state.set(key, record)
        self.gh.write_pinned_state(self.issue, state)
        self.issue.body = body
        return replaced

    def advances_without_change(self) -> None:
        """Move the base past the head by a file added and removed, a rebase onto it changing no tree; fetched."""
        work = self._work
        self._git("checkout", QUIET, "main", cwd=work)
        (work / "transient.txt").write_text("a file the base keeps for a moment\n")
        self._git("add", "transient.txt", cwd=work)
        self._git("commit", QUIET, "-m", "base adds a transient file", cwd=work, env_extra=self._author_env)
        self._git("rm", QUIET, "transient.txt", cwd=work)
        self._git("commit", QUIET, "-m", "base removes a transient file", cwd=work, env_extra=self._author_env)
        self._git("push", QUIET, "origin", "main", cwd=work)
        self._git("fetch", QUIET, "origin", cwd=self._wt)

    def assert_invalidated(self, *, standing: str | None) -> None:
        """The settled run invalidated whole, the attempt on `standing`, the run made once and nothing pushed."""
        self.assert_retired_whole(self.settled)
        self.assertEqual(readings.pinned(self)[readings.KEY_PENDING_PUSH], standing)
        self.assert_made()

    def settles_under_the_notice(
        self, head: str, *, raises: bool, restores: bool = False, recovered: bool = False,
    ) -> dict:
        """Finish `head` with report 3 settled as a notice posts, lost where `raises`, put back where `restores`.

        A whole recovery where `recovered`, which logs whatever its road raised.
        """
        replaced: list = []
        moves = partial(settles_a_later_report, self, head, replaced)
        if raises:
            moves = partial(loses_the_answer, moves)
        restored = _RacesPastTheStep(_writes.lands, partial(_puts_back_once, self, replaced, restores))
        with (
            patch.object(self.gh, "comment", _RacesPastTheCall(self.gh.comment, 1, moves)),
            patch.object(_writes, "lands", restored),
        ):
            if recovered:
                self.recovers()
            elif raises:
                self.assertRaises(RuntimeError, self.finalizes, head)
            else:
                self.assertEqual(self.finalizes(head), FinishOutcome.REFUSED)
        return replaced[0]

    def puts_back_records(self, recorded: dict) -> None:
        """Write the report and review records back as `recorded` kept them, before report 3 moved them."""
        state = self.gh.read_pinned_state(self.issue)
        for key, kept in recorded.items():
            state.set(key, kept)
        self.gh.write_pinned_state(self.issue, state)

    def assert_continued(self, head: str) -> None:
        """`head` announced once and continued, its attempt retired and nothing relabelled."""
        said = (support.announced(self), len(readings.notices(self)))
        self.assertEqual(said, ([head], 1))
        self.assertEqual(readings.relabels(self), ())
        self.assertEqual(readings.attempt(readings.pinned(self)), readings.RETIRED)


def _puts_back_once(case: HoldCase, replaced: list, restores: bool) -> None:
    """Write back what report 3 moved, once it moved, where `restores`."""
    if restores and replaced and replaced[-1] is not None:
        case.puts_back_records(replaced[-1])
        replaced.append(None)
