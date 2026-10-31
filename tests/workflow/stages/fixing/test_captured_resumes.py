# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The resume that finishes a reviewer's change request's parked round, captured as it returns and finished once.

The round a reviewer's request handed its developer parks, and on
`workflow:fixing` a human's reply -- or an operator's `/orchestrator continue`,
replaying the reviewer's feedback -- resumes that developer. Its report is
captured as it returns, and while an operator holds the issue nothing it was
handed is consumed: the park stands, and the reply or the command still reads
as unread. Once the control comes off, the dispatcher's recovery finishes the
round from the capture with no developer launched: the park comes down, the
reply or command is settled exactly once beside the report, the round is
spent once, and the issue is handed back for review.
"""
from __future__ import annotations

import unittest
from itertools import product
from types import MappingProxyType
from unittest.mock import patch

from orchestrator import config
from orchestrator.workflow.engine import completion_routes as _routes
from orchestrator.workflow.stages.fixing import resume_road as _resume_road
from orchestrator.workflow.state import WorkflowLabel
from tests.workflow import captured_fixes as _held, fix_reports as world, published_reports as _published_reports
from tests.workflow.fixtures import LABEL_VALIDATING, accounted

ISSUE = 2_430

PR = 24_300

_BOUNDARY = "last_action_comment_id"

# The two answers that resume the round, each beside the park it answers: a
# reply to the question the round asked, and a continue retrying a session
# that failed, which replays the reviewer's feedback.
_ANSWERS = (
    (None, "the helper should move"),
    ("agent_silent", "/orchestrator continue"),
)

# Every hold a resumed developer may return under, by the control and by
# whether it committed or answered in its report alone.
_HOLDS = tuple(product((_held.PAUSED, _held.BACKLOG), (True, False)))

# The report another road settles over the one the round was reviewed over.
_LATER_REPORT = "A newer report replaces the reviewed report."

# The evidence revision floor, and the case raising it past the one claimed.
_REVISION_FLOOR = "verification_evidence_revision"
_LATER_REVISION = "a later revision"

# Each move of the evidence frozen beside a held resume, by the stage it
# leaves the capture in: a later revision spent over the one claimed retires
# it; a floor nobody can read, or the handoff gone from beside the current
# evidence it was settled with, is damage and holds it.
_MOVED_EVIDENCE = (
    (_REVISION_FLOOR, _LATER_REVISION, _held.RETIRED),
    (_REVISION_FLOOR, "unreadable", _held.PENDING),
    ("verification_evidence_handoff", _held.OMITTED, _held.PENDING),
)

# What happens as the reviewed report is re-read: nothing, its re-read left
# unconfirmed; a control applied; or a push onto the pull request.
_READ_MOVES = ({}, {"control": _held.BACKLOG}, {"push": True})

# The code-publication receipt's three members, as the implementing stage spells them.
_RECEIPT = ("implementing_published_sha", "implementing_published_lease", "implementing_published_pr")

# The reply a round that committed and asked a question is resumed on.
_REPLY = "the helper should move"

# The issue's run ledger, capped at the runs the round and its resume spend:
# the reviewer's, the developer's, and the resume's.
_RUN_CAP = "MAX_AGENT_RUNS_PER_ISSUE"
_RUNS_SPENT = 3

# The park a spent run ledger stands on, as an operator records it while the
# recovery re-reads the reviewed report, and the reply that lifts it.
_RUN_LIMIT = "agent_run_limit"
_RUN_LIMIT_PARK = MappingProxyType({_held.AWAITING: True, "park_reason": _RUN_LIMIT})
_GRANT = "/orchestrator add-agent-runs 1"


class HeldResumeTest(unittest.TestCase, _held.CapturedFixTicks):
    """A held resume's report settles exactly what its run was handed, once the recovery finishes it."""

    def test_each_answer_is_settled_once(self) -> None:
        # The reply and the continue alike, under either control, committed
        # or not: held, the park and the reply boundary stand and nothing is
        # published or spent; unheld, the park comes down, the boundary moves
        # over the answer the run consumed, the report is published once, the
        # round is spent once, and the issue goes back for review -- one
        # accounted exit for the run, and no developer run again.
        for (reason, answer), (control, committed) in product(_ANSWERS, _HOLDS):
            with self.subTest(answer=answer, control=control, committed=committed):
                self.seeded(ISSUE, PR, LABEL_VALIDATING)
                self.requested_fix(world.QUESTION_REPLY, committed=False, issue_worktree=_held.CHECKOUT)
                world.parked(self, reason)
                world.replied(self, answer)
                self._answered(control, committed=committed)

    def test_a_disagreeing_pair_holds_until_repaired(self) -> None:
        # The settled report and its handoff the resume froze no longer agree
        # -- either one a revision past the other, or taken off from beside
        # it -- as the control comes off. One settlement writes the two
        # together, so the pair is damage, never a report settled since: over
        # a resume that committed and one that answered in its report alone,
        # the park, the reply, and the capture stand with nothing written.
        # Repaired, the next dispatch finishes the round once, with no
        # developer run.
        for (field, moved), committed in product(_held.DISAGREEING, (True, False)):
            with self.subTest(field=field, moved=moved, committed=committed):
                self.seeded(ISSUE, PR, LABEL_VALIDATING)
                self.requested_fix(world.QUESTION_REPLY, committed=False, issue_worktree=_held.CHECKOUT)
                world.parked(self)
                world.replied(self, _REPLY)
                self._answered(_held.PAUSED, committed=committed, unsettled=(field, moved))

    def _answered(self, control: str, *, committed: bool, unsettled: tuple = ()) -> None:
        """The answer the thread ends on, its resume held under `control`, then recovered.

        Where `unsettled` names a case of the settled report pair left
        disagreeing, the recovery holds first, until the pair is repaired.
        """
        answered = max(comment.id for comment in self.issue.comments)
        self.held_resume(world.reported(), control, committed=committed)
        held = self.pinned()
        self._held(held, answered)
        self.held_ticks()
        if unsettled:
            self._held_until_repaired(*unsettled, committed=committed)
        self.unheld(**_held.READING[committed])
        self._finished(held, answered, committed=committed)

    def _held_until_repaired(self, field: str, moved, *, committed: bool) -> None:
        """The pair left disagreeing as `field` and `moved` say holds the capture, nothing written; then repaired."""
        settled = self.unsettles(field, moved)
        before = (self.pinned(), self.github.write_state_calls)
        self.unheld(**_held.READING[committed])
        self.assertEqual((self.pinned(), self.github.write_state_calls), before)
        self.hand_edit(**{field: settled})

    def _held(self, held: dict, answered: int) -> None:
        """`held` captured the resume on the change request's road, with the park and the answer left standing."""
        handoff = _held.capture_of(held).handoff
        self.assertEqual(
            (
                held[_held.CAPTURED]["stage"], handoff.route, handoff.origin,
                tuple(field for field, _digest in handoff.frozen),
                dict(handoff.watermarks)[_BOUNDARY], dict(handoff.spends)[_held.ROUND],
            ),
            (
                _held.PENDING,
                _routes.CompletionRoute.REQUESTED_CHANGES,
                WorkflowLabel.FIXING,
                tuple(sorted(_resume_road.FROZEN)),
                answered,
                1,
            ),
        )
        self.assertLess(held.get(_BOUNDARY) or 0, answered)
        self.assertEqual(
            (
                held[_held.AWAITING],
                held[_held.ROUND],
                self.reports(),
                self.pull_request.head.sha,
            ),
            (True, 0, 0, world.PUBLISHED_HEAD),
        )

    def _finished(self, held: dict, answered: int, *, committed: bool) -> None:
        """The recovery took the park down, consumed the answer, and published the report once on one round."""
        recovered = self.pinned()
        head = world.FIXED_HEAD if committed else world.PUBLISHED_HEAD
        self.assertEqual(
            (
                recovered[_held.CAPTURED]["stage"], _held.capture_of(recovered).invocation,
                recovered[_held.AWAITING], recovered[_held.ROUND], recovered[_held.ANCHOR],
            ),
            (_held.HANDED_OFF, _held.capture_of(held).invocation, False, 1, None),
        )
        self.assertGreaterEqual(recovered[_BOUNDARY], answered)
        # The baseline the run was handed, which its report is stamped with.
        self.assertEqual(
            (recovered["user_content_hash"], self.records()["current"].subject.requirements_revision),
            (_held.capture_of(held).handoff.requirements_revision,) * 2,
        )
        self.assertEqual(
            (
                self.reports(), self.records()["current"].subject.source_sha,
                self.pull_request.head.sha, self.github.label_history[-1], accounted(recovered),
            ),
            (1, head, head, (ISSUE, LABEL_VALIDATING), accounted(held)),
        )



class ResumeSubjectTest(unittest.TestCase, _held.CapturedFixTicks):
    """A held resume over unpushed work is published, and one over a subject that moved is retired or held."""

    def test_a_resume_over_stranded_work_publishes_it(self) -> None:
        # The round committed and asked rather than reported, so its commit
        # is still unpushed when the reply's resume reports over it: the
        # checkout stands a commit ahead of the pull request on both sides of
        # the run. Its own tick and the recovery of a held one alike hand the
        # report on and publish that commit beside it, one round spent and no
        # developer run again.
        for held in (False, True):
            with self.subTest(held=held):
                self._parked_over_stranded_work()
                if held:
                    self.held_resume(world.reported(), **_held.STRANDED)
                    self.unheld(**_held.STRANDED)
                else:
                    self.parked_resume(world.reported(), issue_worktree=_held.CHECKOUT, **_held.STRANDED)
                finished = self.pinned()
                self.assertEqual(
                    (
                        _held.stage_of(finished),
                        self.pull_request.head.sha,
                        finished[_held.ROUND],
                        self.reports(),
                    ),
                    (_held.HANDED_OFF, world.FIXED_HEAD, 1, 1),
                )

    def test_a_moved_subject_retires_or_holds_it(self) -> None:
        # The report the round was reviewed over is settled over by another
        # road while the resume is held: its answer is to a review nobody is
        # asking about any more, so the capture is retired, the newer report
        # stands, and no round is spent. A settled record nobody can read --
        # `null` included, which no writer leaves -- proves nothing, and holds
        # the capture with nothing written.
        self._parked_resume_held()
        _published_reports.republishes_the_report(self.github, self.issue, text=_LATER_REPORT)
        self.unheld(**_held.UNMOVED)
        retired = self.pinned()
        self.assertEqual(
            (
                _held.stage_of(retired),
                self.records()["current"].report_revision,
                self.reports(),
                retired[_held.ROUND],
            ),
            (_held.RETIRED, 2, 0, 0),
        )
        for damaged in ({"damaged": True}, None):
            with self.subTest(damaged=damaged):
                self._parked_resume_held()
                self.hand_edit(**{_held.CURRENT_REPORT: damaged})
                before = (self.pinned(), self.github.write_state_calls)
                self.unheld(**_held.UNMOVED)
                self.assertEqual((self.pinned(), self.github.write_state_calls), before)

    def test_an_unread_or_moved_read_holds_it(self) -> None:
        # The report the round was reviewed over will not read where it
        # settled, or an operator applies a control or somebody pushes onto
        # the pull request while it is re-read: the park stands, the reply
        # reads as unread, no round is spent, and the capture waits with
        # nothing written.
        for moves in _READ_MOVES:
            with self.subTest(moves=moves):
                self._parked_resume_held()
                before = self.pinned()
                reread = _held.ReadAt(self, self.opening_report.location, **moves)
                with patch.object(self.github, "reread_report_location", side_effect=reread):
                    self.unheld(**_held.UNMOVED)
                self.assertEqual(self.pinned(), before)

    def test_moved_evidence_retires_or_holds_it(self) -> None:
        # The round's reviewer declared a passing check, and the evidence it
        # published is frozen beside the resume. A later revision spent over
        # it while the resume is held retires the capture with nothing
        # published or spent; a revision floor nobody can read, or an
        # evidence handoff dropped from beside the current evidence, holds it
        # with nothing written.
        for field, moved, stage in _MOVED_EVIDENCE:
            with self.subTest(field=field, moved=moved):
                self.seeded(ISSUE, PR, LABEL_VALIDATING)
                self.verified_round(world.QUESTION_REPLY)
                world.replied(self)
                self.held_resume(world.reported(), committed=False)
                spelled = self.pinned()[_REVISION_FLOOR] + 1 if moved == _LATER_REVISION else moved
                self.hand_edit(**{field: spelled})
                self.unheld(**_held.UNMOVED)
                moved = self.pinned()
                self.assertEqual(
                    (_held.stage_of(moved), self.reports(), moved[_held.ROUND]),
                    (stage, 0, 0),
                )

    def test_a_damaged_receipt_holds_it(self) -> None:
        # The resume froze the code-publication receipt whole -- the commit
        # last published, the head that push replaced, and the pull request
        # it went onto -- since the push writes the three as one record. Any
        # of them spelled as nothing the receipt's reader takes is damage:
        # the park stands, nothing is published or spent, and the capture
        # waits with nothing written.
        for member in _RECEIPT:
            with self.subTest(member=member):
                self._parked_resume_held()
                self.hand_edit(**{member: "unreadable"})
                before = (self.pinned(), self.github.write_state_calls, 0)
                self.unheld(**_held.UNMOVED)
                after = (self.pinned(), self.github.write_state_calls, self.reports())
                self.assertEqual(after, before)

    def _parked_over_stranded_work(self) -> None:
        """The round committed, asked a question, and parked, its commit unpushed; a human replied."""
        self.seeded(ISSUE, PR, LABEL_VALIDATING)
        self.requested_fix(world.QUESTION_REPLY, committed=True, issue_worktree=_held.CHECKOUT)
        world.replied(self)

    def _parked_resume_held(self) -> None:
        """The round asked a question and parked, a reply resumed it, and an operator held its run."""
        self.seeded(ISSUE, PR, LABEL_VALIDATING)
        self.requested_fix(world.QUESTION_REPLY, committed=False, issue_worktree=_held.CHECKOUT)
        world.parked(self)
        world.replied(self, _REPLY)
        self.held_resume(world.reported(), committed=False)


class ParkedDuringTheReadTest(unittest.TestCase, _held.CapturedFixTicks):
    """A park recorded while a held resume's subject is read stands, and the grant that lifts it finishes the round."""

    def test_a_run_limit_park_holds_it(self) -> None:
        # The resume spent the issue's last run, and an operator records the
        # spent ledger's park while the recovery re-reads the report the
        # round was reviewed over. The resume's report is recorded decided on
        # the park's flags as the recovery read them, so nothing takes the
        # park down: the capture pending, nothing published, pushed, or
        # spent, and only the operator's write on the comment, whether the
        # run committed or answered in its report alone. The grant that lifts
        # the park lets the next dispatch finish the round once, with no
        # developer run.
        for committed in (False, True):
            with self.subTest(committed=committed), patch.object(config, _RUN_CAP, _RUNS_SPENT):
                self._resume_held(committed=committed)
                writes = self.github.write_state_calls
                during = _held.ReadAt(self, self.opening_report.location, damage=_RUN_LIMIT_PARK)
                with patch.object(self.github, "reread_report_location", side_effect=during):
                    self.unheld(**_held.READING[committed])[_held.PUSH_BRANCH].assert_not_called()
                self.assertEqual(
                    (self._standing(), self.github.write_state_calls),
                    ((_held.PENDING, True, _RUN_LIMIT, 0, 0), writes + 1),
                )
                world.replied(self, _GRANT)
                self.dispatched(**_held.READING[committed])[_held.RUN_AGENT].assert_not_called()
                self.assertEqual(self._standing(), (_held.HANDED_OFF, False, None, 1, 1))

    def _resume_held(self, *, committed: bool) -> None:
        """The round asked and parked, a reply resumed it, and an operator held its run, the last the ledger allows."""
        self.seeded(ISSUE, PR, LABEL_VALIDATING)
        self.requested_fix(world.QUESTION_REPLY, committed=False, issue_worktree=_held.CHECKOUT)
        world.parked(self)
        world.replied(self, _REPLY)
        self.held_resume(world.reported(), committed=committed)
        self.assertEqual(self.ledger()[0], _RUNS_SPENT)

    def _standing(self) -> tuple:
        """The capture's stage, the park's flags, the round, and how many reports the pull request carries."""
        pinned = self.pinned()
        return (
            _held.stage_of(pinned),
            pinned[_held.AWAITING],
            pinned.get("park_reason"),
            pinned[_held.ROUND],
            self.reports(),
        )


if __name__ == "__main__":
    unittest.main()
