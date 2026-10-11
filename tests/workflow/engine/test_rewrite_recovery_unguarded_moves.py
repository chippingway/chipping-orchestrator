# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""A captured run whose issue, configuration, or artifact moves behind its proof's requests is refused before use.

A finish recorded its run for the landed head and died posting its artifact,
so the recovery proves that run again, publishes it, and settles it with the
attempt still standing. The issue's requirements and the configured command
are held by no guarded commit, so they are read again behind every other
request: the publication's right before the post, behind the proof's re-read
of the settled report, and the settlement's right before its commit, behind
the anchor's last reading of the base. An issue edited or a command
configured otherwise in either window refuses it -- nothing stale is posted,
nothing settled -- and the run is abandoned into history, the head routed once
to the fresh reviewer. So does the artifact edited as the settlement's proof
re-reads the settled report: the settlement re-reads the artifact once more
behind its whole proof, so nothing edited is made current. Put back, the move
revives nothing, however often the recovery polls, nor in the dispatcher's
reconciliation. Nothing runs, pushes, or announces again, and no developer is
launched.
"""
from __future__ import annotations

import unittest
from copy import copy
from functools import partial
from itertools import product
from unittest.mock import patch

from orchestrator.workflow.engine import rewrite_evidence_proof
from orchestrator.workflow.stages.validating import review_report
from tests.workflow.engine import rewrite_verification_recovery_support as support
from tests.workflow.interleaving import _RacesPastTheCall

_EDITED_BODY = "Also cover a moved base."


def _races_past(case: support.CapturedRunCase, owner, step: str, nth: int, raced) -> None:
    """Have `raced()` made once, just after call number `nth` of `owner`'s `step` answers, for the rest of `case`."""
    races = _RacesPastTheCall(getattr(owner, step), nth, raced)
    case.enterContext(patch.object(owner, step, races))


def _behind_the_report_reread(case: support.CapturedRunCase, moves, nth: int = 2) -> None:
    """Have `moves` made as a proof re-reads the settled report: by default the publication's, the recovery's second.

    The first is the captured run's own proof behind the evidence step, and
    the third the settlement's.
    """
    _races_past(case, review_report, "_settled_report", nth, moves)


def _behind_the_last_base_read(case: support.CapturedRunCase, moves) -> None:
    """Have `moves` made as the settlement reads the base last of all, behind its first re-read of the artifact.

    That is the second base read behind that re-read; the first is the
    anchor's proof within the settlement's whole proof.
    """
    armed = partial(_races_past, case, rewrite_evidence_proof, "standing_refusal", 2, moves)
    _races_past(case, case.gh, "reread_verification_artifact", 1, armed)


def _edits_the_artifact(case: support.CapturedRunCase, kept: list) -> None:
    """Edit the artifact the recovery posted by hand, keeping what it said in `kept`."""
    posted = case.pull_request.issue_comments[-1]
    kept.append(posted.body)
    posted.body = f"{posted.body}\nEdited by hand."


# Where the move lands, beside how many artifacts the run's receipt is then
# posted under: none ahead of the post, the one landed ahead of the settlement.
_WINDOWS = (
    ("as the publication's proof re-reads the report", _behind_the_report_reread, 0),
    ("as the settlement reads the base last of all", _behind_the_last_base_read, 1),
)

# What moves, beside what puts it back given the issue body read before.
_MOVES = (
    (
        "the requirements",
        lambda case: setattr(case.issue, "body", _EDITED_BODY),
        lambda case, body: setattr(case.issue, "body", body),
    ),
    (
        "the configured command",
        lambda case: case.configures("echo another"),
        lambda case, _body: case.configures(support.CONFIGURED),
    ),
)


class UnguardedMoveRecoveryTest(support.CapturedRunCase, unittest.TestCase):
    """A run whose requirements, configuration, or artifact moved behind its proof's requests is abandoned for good."""

    def test_a_late_move_abandons(self) -> None:
        # The move lands behind the last request ahead of the post or the
        # settlement, and is read before either goes out; put back, a later
        # poll and the reconciliation find nothing to settle.
        for window, move in product(_WINDOWS, _MOVES):
            with self.subTest(moved=move[0], window=window[0]):
                head, captured, body = self._recovers_moved(window[1], move[1])

                self._assert_routed_abandoned(head, captured, window[2])
                move[2](self, body)
                self.recovers()
                self.recovers()
                self.reconciles()
                self._assert_routed_abandoned(head, captured, window[2])

    def test_an_artifact_edited_late_abandons(self) -> None:
        # The artifact is edited as the settlement's proof re-reads the
        # settled report, behind the settlement's first re-read of it: the
        # second, behind the whole proof, refuses it, so nothing edited is
        # made current and the run is abandoned. Put back, nothing revives
        # it, poll after poll.
        kept: list[str] = []
        arms = partial(_behind_the_report_reread, nth=3)
        edits = partial(_edits_the_artifact, kept=kept)
        head, captured = self._recovers_moved(arms, edits)[:2]

        self.assert_abandoned(captured)
        self.assert_recovered(head)
        self.pull_request.issue_comments[-1].body = kept[0]
        self.recovers()
        self.recovers()
        self.reconciles()
        self._assert_routed_abandoned(head, captured, 1)

    def _recovers_moved(self, arms, moves) -> tuple:
        """A fresh case's captured run, recovered with `moves` made where `arms` hangs it; head, run, and prior body.

        Every read of the issue through the client is a snapshot of it as it
        then stands, as GitHub hands one back, so an edit made after a reading
        is seen only by a reading taken after it.
        """
        self.setUp()
        head, captured = self.captures()
        body = self.issue.body
        self.enterContext(patch.object(self.gh, "get_issue", self._snapshot))
        arms(self, partial(moves, self))
        self.recovers()
        return head, captured, body

    def _snapshot(self, _number: int):
        """The issue as it stands now, apart from any later edit."""
        return copy(self.issue)

    def _assert_routed_abandoned(self, head: str, captured, posted: int) -> None:
        """`captured` abandoned with `posted` artifacts under its receipt, and `head` routed once to the reviewer."""
        self.assert_abandoned(captured)
        self.assert_recovered(head)
        self.assertEqual(len(self.posted(captured)), posted)


if __name__ == "__main__":
    unittest.main()
