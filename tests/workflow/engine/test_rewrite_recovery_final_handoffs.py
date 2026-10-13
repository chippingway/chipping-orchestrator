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

Settled evidence is proved ready again before that route: an issue edited, a
later report settled and reviewed, or another command configured since the
settlement invalidates it into history whole, its revision and binding kept,
and the head goes on to the fresh reviewer, while a pull request nobody could
read holds the route for the next tick, which routes the evidence exactly as
it settled, and a checkout that moves off the head while the evidence is
proved invalidates it and holds the route. A base that advanced again while
the attempt stood continues the landed head to another rebase instead of
routing it, with no second announcement of it. And two base advances whose
runs come out differently each settle or publish their own result once,
whatever boundary either finish died at.
"""
from __future__ import annotations

import unittest
from functools import partial
from itertools import product
from typing import NamedTuple
from unittest.mock import patch

from orchestrator.workflow.engine import (
    report_evidence_models as _evidence_models,
    report_publication_evidence as _publication,
    verification_settlement_state as _settlement,
)
from orchestrator.workflow.state import WorkflowLabel
from tests.workflow.engine import (
    rewrite_finish_git_support as git_support,
    rewrite_finish_readings as readings,
    rewrite_handoff_test_support as handoff,
    rewrite_verification_recovery_support as support,
    verification_evidence_test_support as _evidence_support,
    verification_report_fixture as _report,
)
from tests.workflow.interleaving import _RacesPastTheCall

_EDITED_BODY = "Also cover a base that moved twice."

# A suite that passes until the base brings `later.txt` in, and then fails.
_SUITE = (
    "test -f feature.py && test ! -f later.txt && echo 'feature.py is in place' "
    "|| { echo 'test_later failed: later.txt breaks the widget'; exit 3; }"
)


def _settles_a_later_report(case: support.CapturedRunCase, head: str) -> None:
    """Settle report 3 of `head` and hand a reviewer it, over the comment as it stands."""
    case.state = case.gh.read_pinned_state(case.issue)
    _report.settles_report(case, 3, "Implemented the change and covered a base that moved twice.", head=head)
    case.gh.write_pinned_state(case.issue, case.state)


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

_REREAD = "reread_report_location"

# The pull request read answering as one nobody could take does.
_UNREAD_PULL_REQUEST = _evidence_models.ReportEvidence(
    _evidence_models.ReportEvidenceVerdict.HOLD, "the recorded pull request could not be read",
)

# What moves under evidence settled for the landed head before the next tick reads it.
_MOVES = (
    ("the issue was edited", lambda case, _head: setattr(case.issue, "body", _EDITED_BODY)),
    ("a later report was settled and reviewed", _settles_a_later_report),
    ("another command was configured", lambda case, _head: case.configures("echo another")),
)


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

    def assert_invalidated(self, settled) -> None:
        """`settled` invalidated into history behind the anchor's evidence, its revision and binding kept whole."""
        retired = (*git_support.invalidated(self), (settled.receipt, readings.INVALIDATED))
        self.assertEqual(self.records(), (None, None, retired))
        entry = _settlement.read_evidence_history(self.gh.read_pinned_state(self.issue))[-1]
        self.assertEqual((entry.revision, entry.binding), (settled.revision, settled.binding))
        self.assertEqual(self.artifacts(settled), 1)

    def artifacts(self, settled=None) -> int:
        """How many artifacts the pull request carries: all of them, or those under `settled`'s receipt."""
        receipts = [artifact.receipt for artifact in _evidence_support.posted_artifacts(self)]
        return len(receipts) if settled is None else receipts.count(settled.receipt)

    def records(self) -> tuple:
        """The pending, current, and retired evidence records the pinned comment carries now."""
        return readings.pinned_records(self)


class FinalHandoffRecoveryTest(_HandoffCase, unittest.TestCase):
    """A tail cut short at any boundary is finished once by the next tick, over evidence proved ready again."""

    def test_each_boundary_finishes_once(self) -> None:
        # Whatever resolved the evidence and wherever the tail died, two later
        # polls leave one announcement, one relabel and stage entry, the
        # evidence exactly as resolved, and nothing run or published again.
        for resolution, boundary in product(_RESOLUTIONS, handoff.BOUNDARIES):
            with self.subTest(resolution=resolution.name, boundary=boundary.name):
                self.setUp()
                head = resolution.lands(self)
                self.dies_finishing(head, boundary)
                resolved = (self.records(), self.artifacts())

                self.recovers()
                self.recovers()

                self.assert_announced_once(head, failed=resolution.failed)
                self.assertEqual((self.records(), self.artifacts()), resolved)
                self.assert_finished(resolution.ran)

    def test_movement_invalidates_settled_evidence(self) -> None:
        # The run settled before the tail died, and something it is bound to
        # moved before the next tick: the recovery invalidates it whole rather
        # than routing it as current, and routes the head to the fresh
        # reviewer with nothing run or posted again and no second notice.
        for (name, moves), boundary in product(_MOVES, handoff.BOUNDARIES):
            with self.subTest(move=name, boundary=boundary.name):
                self.setUp()
                head = self.lands_a_reviewed_rebase()
                self.dies_finishing(head, boundary)
                settled = self.records()[1]
                moves(self, head)

                self.recovers()

                self.assert_invalidated(settled)
                self.assert_announced_once(head)
                self.assert_finished(1)

    def test_an_unread_proof_holds_the_route(self) -> None:
        # The pull request will not read while the recovery proves the settled
        # run ready again: the route is held with the run current and the
        # attempt standing, nothing said or relabelled beyond what the dead
        # tick did, and the next recovery routes the run exactly as it settled.
        for boundary in handoff.BOUNDARIES:
            with self.subTest(boundary=boundary.name):
                self.setUp()
                head = self.lands_a_reviewed_rebase()
                self.dies_finishing(head, boundary)
                resolved = self._standing()
                with patch.object(_publication, "subject_verdict", return_value=_UNREAD_PULL_REQUEST):
                    self.recovers()

                self.assertEqual(self._standing(), resolved)
                self.recovers()
                self.assert_announced_once(head)
                self.assertEqual(self.records(), resolved[0])
                self.assert_finished(1)

    def test_a_landing_moved_mid_proof_holds(self) -> None:
        # The checkout commits past the landed head while the recovery re-reads
        # the report the settled run is bound to: that is movement under the
        # run, which is invalidated whole, and the landing it would route no
        # longer stands, so the route is held with the attempt standing and
        # nothing said or relabelled beyond what the dead tick did.
        for boundary in handoff.BOUNDARIES:
            with self.subTest(boundary=boundary.name):
                self.setUp()
                head = self.lands_a_reviewed_rebase()
                self.dies_finishing(head, boundary)
                settled = self.records()[1]
                held = (self.anchor, self.said(), readings.relabels(self))
                commits = partial(self._git, *support.STRAY_COMMIT, cwd=self._wt)
                with patch.object(self.gh, _REREAD, _RacesPastTheCall(self.gh.reread_report_location, 1, commits)):
                    self.recovers()

                self.assert_invalidated(settled)
                self.assertEqual(self._standing()[1:], held)

    def test_a_base_advance_continues_the_head(self) -> None:
        # The base advances again while the attempt stands: the next tick
        # retires it unrouted -- announcing the landed head only where the
        # dead tick had not -- rebases once more, and routes what that push
        # landed, invalidating the run settled for the head it replaced.
        for boundary in handoff.BOUNDARIES:
            with self.subTest(boundary=boundary.name):
                self.setUp()
                head = self.lands_a_reviewed_rebase()
                self.dies_finishing(head, boundary)
                settled = self.records()[1]
                support.advances_the_base_again(self)

                self.recovers()
                self.recovers()

                self._assert_continued(head, settled, relabelled=boundary is handoff.BEFORE_THE_RETIREMENT)

    def _standing(self) -> tuple:
        """The evidence records, the anchor the attempt stands on, what was said, and every relabel, read now."""
        anchored = readings.pinned(self)[readings.KEY_PENDING_PUSH]
        return self.records(), anchored, self.said(), readings.relabels(self)

    def _assert_continued(self, head: str, settled, *, relabelled: bool) -> None:
        """`head` and the head its continuation pushed each announced once, the run `settled` for `head` invalidated.

        The pushed head is routed, behind the relabel the dead tick already
        made where it `relabelled` `head`; the command ran once, the push
        went out once, and no developer was launched.
        """
        rebased = [head, git_support.remote_head(self)]
        self.assertEqual(self.said(), (rebased, 2, []))
        self.assertEqual(readings.relabels(self), readings.ROUTED * (1 + relabelled))
        self.assert_invalidated(settled)
        made = (self.runs(), self.pushes.call_count, self.developer.call_count)
        self.assertEqual(made, (1, 1, 0))


class DifferingRunsJourneyTest(_HandoffCase, unittest.TestCase):
    """Two base advances whose runs pass and then fail each resolve their own result once."""

    def test_each_advance_resolves_its_own_run(self) -> None:
        # The first rebased head's run passes and settles; the second's, over
        # a base that brought in what breaks the suite, fails and its notice
        # is published. Wherever both tails died, the passing run ends in
        # history with its own tested head, nothing is current, each head is
        # announced once and run once, and nothing is pushed or launched.
        for boundary in (None, *handoff.BOUNDARIES):
            named = "uninterrupted" if boundary is None else boundary.name
            with self.subTest(boundary=named):
                self.setUp()
                self.configures(_SUITE)
                first, settled = self._lands_the_first(boundary)
                second = self._lands_the_second(boundary)

                self._assert_each_resolved_once(first, settled, second)

    def _assert_each_resolved_once(self, first: str, settled, second: str) -> None:
        """`first`'s run `settled`, then invalidated with its own head; `second`'s failure noticed; each said once."""
        failed = [second[:8]]
        self.assertEqual(self.said(), ([first, second], 2, failed))
        self.assertEqual(settled.binding.tested_sha, first)
        self.assert_invalidated(settled)
        relabelled = (WorkflowLabel.VALIDATING, git_support.REVIEWING, WorkflowLabel.VALIDATING)
        self.assertEqual(readings.relabels(self), relabelled)
        self.assert_finished(2)

    def _lands_the_first(self, boundary: handoff.Boundary | None) -> tuple:
        """Land and review the first rebase, finish it -- killed at `boundary` -- and recover; it, and its run."""
        first = self.lands_a_reviewed_rebase()
        self.dies_finishing(first, boundary)
        self.recovers()
        settled = self.records()[1]
        self.assertEqual(settled.binding.target.target_head, first)
        return first, settled

    def _lands_the_second(self, boundary: handoff.Boundary | None) -> str:
        """Put the issue back in review, advance the base again, and land and review that rebase too; its head.

        The label is written straight back, standing in for the review, the
        docs pass, and the ping that would take the issue there. Finished --
        killed at `boundary` -- and recovered the way the first was.
        """
        self.gh.set_workflow_label(self.issue, git_support.REVIEWING, guarded=False)
        self.anchor = git_support.remote_head(self)
        support.advances_the_base_again(self)
        second = self.rebases_by_hand()
        _settles_a_later_report(self, second)
        self.dies_finishing(second, boundary)
        self.recovers()
        return second


if __name__ == "__main__":
    unittest.main()
