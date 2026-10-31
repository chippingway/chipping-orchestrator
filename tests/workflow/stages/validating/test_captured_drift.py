# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""A requirements-drift resume on `validating` held under a control, captured, and finished with no developer run.

The body edit this stage resumes the developer on, and the reply it reads as
the rest of that drift resume, each launch on the drift road. Held under
`paused` or `backlog`, the run's report is captured as it returns and nothing
else it was handed is settled: the baseline, the round, the reply boundary,
the reports, and the session stay as the launch found them. Unheld, the
dispatcher's recovery publishes the captured report through the stage's own
drift disposition -- beside the commit, or onto the head the pull request
carries where none was made -- records the requirements the run was handed as
the baseline, and spends the round its own tick would have spent once, and
only then. An edit, a reply, a reset checkout, a push, or a checkout nobody
can read while it waits retires or holds the capture rather than publishing
the old output, and a process lost at the handoff is finished by the next
dispatch with nothing paid twice.
"""
from __future__ import annotations

import unittest
from itertools import product
from types import MappingProxyType
from unittest.mock import patch

from orchestrator import config
from orchestrator.git.worktrees.models import ProbeAnswer
from orchestrator.workflow.state import WorkflowLabel
from tests.support.fakes import FakeLabel
from tests.workflow import captured_drifts as _held, captured_fixes as _fixes, drift_reports as world
from tests.workflow.fixtures import LABEL_VALIDATING, _agent

ISSUE = 2_431
PR = 24_310

_REVIEW_REPLY = "Looked it over."

LABEL_BLOCKED = str(WorkflowLabel.BLOCKED)
_QUESTION_REPLY = "Should the new criterion replace the old one or sit beside it?"

_HOLDS = tuple(product((_fixes.PAUSED, _fixes.BACKLOG), (True, False)))

# What a recovery settles that a live drift's own tick settles too.
_BOUNDARY = "last_action_comment_id"
_AWAITING = "awaiting_human"
_SETTLED = ("user_content_hash", "review_round", _BOUNDARY, "dev_session_id", "dev_resume_count")

_DRIFT_OPEN = "requirements_drift_open"
_ROUND_RESET = "developer_report_owed_round_reset"

# The reply's tick reads the checkout once ahead of its launch, on the head
# the pull request carries, and the run leaves the commit it made.
_REPLY_READS = MappingProxyType({world.HEAD_SHAS: (world.PUBLISHED_HEAD, world.PUBLISHED_HEAD, world.FIXED_HEAD)})


class HeldDriftTest(unittest.TestCase, _held.HeldDriftTicks):
    """A held drift resume's report is captured, waited through, and finished once with no developer run."""

    def test_each_hold_is_finished_once(self) -> None:
        # Under either control, a resume that committed and one that
        # answered the edit in its report alone: held, nothing but the
        # capture and the run's accounting moves, and two held polls write
        # nothing; unheld, the report is published once -- beside the commit,
        # or onto the head the pull request carries -- the baseline records
        # the requirements the run was handed, the round is spent only by the
        # commit, and the next tick runs the reviewer rather than the edit's
        # developer again.
        for control, committed in _HOLDS:
            with self.subTest(control=control, committed=committed):
                self.seeded(ISSUE, PR, LABEL_VALIDATING)
                launched = _held.held(self.pinned())
                self.held_drift(world.reported(), control, committed=committed)
                self.assertEqual(_held.held(self.pinned()), launched)
                self.held_ticks()
                self.unheld(**_held.READING[committed])
                self._finished(committed=committed)
                self._reviewed_next()

    def test_a_recovery_settles_as_the_live_drift(self) -> None:
        # The same resume, its return held and recovered, settles the same
        # baseline, round, boundary, and session as one whose own tick
        # disposed of it -- a resumed conversation charged one resume.
        settled = []
        for held in (False, True):
            self.seeded(ISSUE, PR, LABEL_VALIDATING)
            if held:
                self.held_drift(world.reported())
                self.unheld(**_held.COMMITTED)
            else:
                self.dispatched(_agent(session_id=world.DEV_SESSION, last_message=world.reported()))
            pinned = self.pinned()
            settled.append(tuple(map(pinned.get, _SETTLED)))
            self.assertEqual(_fixes.stage_of(pinned), _fixes.HANDED_OFF)
        self.assertEqual(settled[0], settled[1])

    def _finished(self, *, committed: bool) -> None:
        """One report published, of the requirements the run was handed, and the round spent by the commit alone."""
        finished = self.pinned()
        current = self.records()["current"]
        self.assertEqual(
            (
                _fixes.stage_of(finished),
                len(self.published_reports()),
                finished[_held.BASELINE],
                current.subject.requirements_revision,
                finished[_held.ROUND],
                self.pull_request.head.sha,
            ),
            (
                _fixes.HANDED_OFF,
                1,
                world.handed_revision(self.issue),
                world.handed_revision(self.issue),
                1 if committed else 0,
                world.FIXED_HEAD if committed else world.PUBLISHED_HEAD,
            ),
        )

    def _reviewed_next(self) -> None:
        """The next dispatch runs the reviewer over the published head, never the developer again."""
        reviewer = _agent(last_message=_REVIEW_REPLY)
        reviewed = self.dispatched(reviewer, committed=False)[_fixes.RUN_AGENT]
        self.assertEqual(reviewed.call_args[0][0], config.REVIEW_AGENT)


class MovedWhileHeldTest(unittest.TestCase, _held.HeldDriftTicks):
    """A held capture the issue moved past is retired, or held where nothing can be read, and never published."""

    def test_new_requirements_retire_it(self) -> None:
        # An edit of the body, or a reply on the thread, while the issue is
        # held: the report answers requirements the issue no longer has, so
        # the capture is retired with nothing published or settled, and the
        # next dispatch resumes the developer over what the issue now asks --
        # its report stamped with that, never the old output relabelled.
        for change in ("edit", "comment"):
            with self.subTest(change=change):
                self.seeded(ISSUE, PR, LABEL_VALIDATING)
                launched = _held.held(self.pinned())
                self.held_drift(world.reported())
                self._changes(change)
                self.unheld(**_held.COMMITTED)
                self._retired(launched)
                answered = self.dispatched(_agent(
                    session_id=world.DEV_SESSION, last_message=world.reported(world.LATER_REPORT_TEXT),
                ))
                answered[_fixes.RUN_AGENT].assert_called_once()
                self.assertEqual(
                    (
                        len(self.published_reports(world.LATER_REPORT_TEXT)),
                        self.published_reports(),
                        self.records()["current"].subject.requirements_revision,
                    ),
                    (1, [], world.handed_revision(self.issue)),
                )

    def test_moved_heads_retire_it(self) -> None:
        # The checkout reset off the commit the report is about, or the pull
        # request pushed to a head neither the run began on nor reported:
        # the report describes no commit that would be published, so it is
        # retired with nothing published, pushed, or settled.
        for moved in ("checkout", "pull request"):
            with self.subTest(moved=moved):
                self.seeded(ISSUE, PR, LABEL_VALIDATING)
                launched = _held.held(self.pinned())
                self.held_drift(world.reported())
                reading = dict(_held.COMMITTED)
                if moved == "checkout":
                    reading[world.HEAD_SHAS] = (_held.MOVED_HEAD,)
                else:
                    self.pull_request.head.sha = world.CONCURRENT_HEAD
                pushed = self.unheld(**reading)
                pushed[_fixes.PUSH_BRANCH].assert_not_called()
                self._retired(launched)

    def test_an_unreadable_checkout_holds_it(self) -> None:
        # A checkout nobody can prove the issue's own, or whose head will not
        # read: nothing proves the capture stale, so it is kept with nothing
        # written, and the dispatch whose readings return publishes it once.
        for unread in ({"checkout_identity": ProbeAnswer.UNREADABLE}, {world.HEAD_SHAS: ("",)}):
            with self.subTest(unread=unread):
                self.seeded(ISSUE, PR, LABEL_VALIDATING)
                self.held_drift(world.reported())
                before = (self.pinned(), self.github.write_state_calls)
                self.unheld(**{**_held.COMMITTED, **unread})
                self.assertEqual((self.pinned(), self.github.write_state_calls), before)
                self.dispatched(**_held.COMMITTED)[_fixes.RUN_AGENT].assert_not_called()
                self.assertEqual(len(self.published_reports()), 1)
                self.assertEqual(self.pinned()[_held.ROUND], 1)

    def test_a_dependency_hold_keeps_it_waiting(self) -> None:
        # A human moves the held issue onto a dependency hold: the capture
        # waits through it, and the hold's own tick reads no edit, so the
        # baseline it defers, the round, and the reports stay as the launch
        # found them, with nothing published and no developer run.
        self.seeded(ISSUE, PR, LABEL_VALIDATING)
        launched = _held.held(self.pinned())
        self.held_drift(world.reported())
        self._relabelled(LABEL_BLOCKED)
        self.unheld(**_held.COMMITTED)
        waiting = self.pinned()
        self.assertEqual(
            (_fixes.stage_of(waiting), _held.held(waiting), self.published_reports()),
            (_fixes.PENDING, launched, []),
        )

    def _relabelled(self, label: str) -> None:
        """Swap the issue's workflow label for `label`, as a human editing its labels does."""
        self.issue.labels = [held for held in self.issue.labels if held.name != LABEL_VALIDATING]
        self.issue.labels.append(FakeLabel(label))

    def _changes(self, change: str) -> None:
        """Move the issue's requirements while it is held: its body edited, or a human reply on the thread."""
        if change == "edit":
            world.edits(self, world.LATER_BODY)
        else:
            world.human_reply(self, world.LATER_COMMENT)

    def _retired(self, launched: tuple) -> None:
        """The capture retired with its invocation kept, nothing published, and nothing it was handed settled."""
        retired = self.pinned()
        self.assertEqual(
            (_fixes.stage_of(retired), self.published_reports(), _held.held(retired)),
            (_fixes.RETIRED, [], launched),
        )


class DriftParkReplyTest(unittest.TestCase, _held.HeldDriftTicks):
    """A reply answering a drift park is the rest of that drift resume, captured and finished on its own round."""

    def test_a_held_reply_spends_what_its_park_owes(self) -> None:
        # The drift resume asked a question, so its park stands over an edit
        # nothing answered. The reply that answers it is held as it reports:
        # nothing of the reply is consumed while held, and the recovery
        # publishes the report and the commit together on the round that
        # park owes -- the next round, or none where an `in_review` hand-back
        # already reset the budget for exactly this publication.
        for reset in (False, True):
            with self.subTest(reset=reset):
                parked = self._parked_on_a_question(reset=reset)
                world.human_reply(self, "replace the old criterion")
                self.held_drift(world.reported(), **_REPLY_READS)
                still_parked = self.pinned()
                self.assertEqual(
                    (still_parked[_AWAITING], still_parked.get(_BOUNDARY)),
                    (True, parked.get(_BOUNDARY)),
                )
                self.unheld(**_held.COMMITTED)
                self.assertEqual(self._answered(), {
                    "reports": 1,
                    "parked": False,
                    "drift": None,
                    "round": int(not reset),
                    "baseline": world.handed_revision(self.issue),
                    "boundary": self.issue.comments[-1].id,
                })

    def _parked_on_a_question(self, *, reset: bool) -> dict:
        """The drift resume parked on a question, its edit unanswered -- its budget reset where `reset`; the record."""
        self.seeded(ISSUE, PR, LABEL_VALIDATING)
        asked = _agent(session_id=world.DEV_SESSION, last_message=_QUESTION_REPLY)
        self.dispatched(asked, committed=False)
        if reset:
            self.hand_edit(**{_ROUND_RESET: True})
        parked = self.pinned()
        self.assertTrue(parked[_AWAITING])
        self.assertTrue(parked.get(_DRIFT_OPEN))
        return parked

    def _answered(self) -> dict:
        """The reports published, the park, the drift claim, the round, the baseline, and the reply boundary."""
        finished = self.pinned()
        return {
            "reports": len(self.published_reports()),
            "parked": finished[_AWAITING],
            "drift": finished.get(_DRIFT_OPEN),
            "round": finished[_held.ROUND],
            "baseline": finished[_held.BASELINE],
            "boundary": finished[_BOUNDARY],
        }


class LostHandoffTest(unittest.TestCase, _held.HeldDriftTicks):
    """A process or an answer lost at the recovery's handoff is finished by a later dispatch, nothing paid twice."""

    def test_a_held_drift_lost_at_its_handoff(self) -> None:
        # The recovery's process is lost as the report's handoff goes out:
        # the capture still holds the report, and the next dispatch publishes
        # it once, on one round, with no developer run. Lost once the handoff
        # landed, or the handoff landing with its answer lost, the delivery
        # owns the report and the baseline went down with it, and the commit
        # is still unpushed: the next dispatch holds that report for a human,
        # as the drift road holds one a process died before pushing, with no
        # developer run, no report posted, and no round spent.
        for lost in (_fixes.SENT, _fixes.LANDED, _fixes.ANSWER):
            with self.subTest(lost=lost):
                self.seeded(ISSUE, PR, LABEL_VALIDATING)
                self.held_drift(world.reported())
                self._lost_at_the_handoff(lost)
                handed = lost != _fixes.SENT
                published = int(not handed)
                self.dispatched(**(_fixes.STRANDED if handed else _held.COMMITTED))[
                    _fixes.RUN_AGENT
                ].assert_not_called()
                finished = self.pinned()
                self.assertEqual(
                    (
                        _fixes.stage_of(finished),
                        len(self.published_reports()),
                        finished[_held.ROUND],
                        finished[_held.BASELINE],
                        bool(finished.get(_AWAITING)),
                    ),
                    (_fixes.HANDED_OFF, published, published, world.handed_revision(self.issue), handed),
                )

    def _lost_at_the_handoff(self, lost: str) -> None:
        """Take the control off and dispatch the recovery, losing its process or its answer at the handoff."""
        for label in tuple(self.issue.labels):
            if label.name == self.control:
                self.issue.labels.remove(label)
        with patch.object(self.github, "edit_pinned_state", _fixes.LostAtTheHandoff(self.github, lost)):
            try:
                self.dispatched(**_held.COMMITTED)
            except SystemExit:
                self.assertNotEqual(lost, _fixes.ANSWER)


if __name__ == "__main__":
    unittest.main()
