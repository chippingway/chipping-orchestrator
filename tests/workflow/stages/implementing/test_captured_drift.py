# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""A mid-implementation edit's session resume, held under a control, and finished with no developer run.

A body edit on an issue whose developer session is recorded resumes that
session on the drift road. Held under `paused` or `backlog`, its report is
captured as it returns and the edit stays unanswered: the baseline, the reply
boundary, the session, and the branch are as the launch found them, and no
pull request is opened. Unheld, the dispatcher's recovery publishes the
commit through the stage's own publication -- the pull request opened and the
issue handed to review -- under the captured report, records the
requirements the run was handed as the baseline, and charges the resumed
conversation once. A report with no commit to carry it parks as the question
it reads as there, its capture withdrawn first, and an edit while it waits
retires the capture so the next dispatch answers the edit afresh.
"""
from __future__ import annotations

import unittest
from types import MappingProxyType
from unittest.mock import MagicMock

from orchestrator.workflow.engine import content_hash as _content_hash
from tests.support.fakes import FakeLabel
from tests.workflow.fixtures import AGENT_RUN_WRITES, Launched, _agent, _reported, accounted
from tests.workflow.stages.implementing import held_capture_test_support as _held

_SESSION = "dev-sess"
_BASELINE = "user_content_hash"
_RESUMES = "dev_resume_count"

_EDITED_BODY = "updated requirements"
_LATER_BODY = "the requirements moved again while the agent worked"

# The issue's developer session, pinned under its command.
_SESSION_PIN = MappingProxyType({"dev_agent": "claude", _held.SESSION_PIN: _SESSION})

# A capture's stage, as its record spells it.
_STAGE = "stage"

# A held return's writes: its charge and accounting, and its capture.
_HELD_WRITES = AGENT_RUN_WRITES + 1

_CAPTURED_ALONE = (_held.CAPTURED,)

# A run that committed nothing, and one that left its commit.
_COMMITTED_NOTHING = MappingProxyType({"has_new_commits": False, "head_shas": _held.UNMOVED})

_LEFT_A_COMMIT = MappingProxyType({"has_new_commits": True, "head_shas": _held.LEFT})

# What a dispatch publishes: pull requests opened, relabels, and comments.
_PUBLISHED = ("opened_prs", "label_history", "posted_comments")


def _published(github) -> tuple:
    """How many pull requests, relabels, and comments the issue's client has taken so far."""
    return tuple(len(getattr(github, taken)) for taken in _PUBLISHED)


def _behind_the_notice(github) -> tuple:
    """What a held drift leaves published, from what `github` has taken so far: the one notice its road posts."""
    opened, relabelled, posted = _published(github)
    return (opened, relabelled, posted + 1)


def _finished():
    """What the resumed session comes back as: its report, on the conversation it resumed."""
    return _agent(session_id=_SESSION, last_message=_reported())


class HeldImplementingDriftTest(unittest.TestCase, _held.HeldCaptureTicks):
    """A held drift resume's report is captured, waited through, and published once by the recovery."""

    def test_each_hold_is_finished_once(self) -> None:
        # Under either control: held, the baseline still names the
        # requirements the edit moved off and the conversation is charged
        # nothing; unheld, the commit is published under the captured report
        # and handed to review, the baseline records what the run was
        # handed, and the conversation is charged one resume -- one exit
        # accounted, and no second run.
        for control in (_held.PAUSED, _held.BACKLOG):
            with self.subTest(control=control):
                github, issue = self._edited()
                handed = _content_hash._compute_user_content_hash(issue, set())
                held = self._held_drift(github, issue, control)
                self.assertNotEqual(held[_BASELINE], handed)
                self.assertNotIn(_RESUMES, held)
                self.held_ticks(github, issue)
                self.unpaused(github, issue)
                self._settled(self.published(github), handed)

    def test_a_report_with_no_commit_is_withdrawn(self) -> None:
        # The held resume reported and committed nothing, and the issue owes
        # no report: the recovery's disposition parks the question its own
        # tick would have parked, withdrawing the capture first, and nothing
        # is published.
        github, issue = self._edited()
        self._held_drift(github, issue, **_COMMITTED_NOTHING)
        self.unpaused(github, issue, **_COMMITTED_NOTHING)
        parked = github.pinned_data(_held.ISSUE)
        self.assertEqual((parked["awaiting_human"], github.opened_prs), (True, []))
        self.assertEqual(parked[_held.CAPTURED][_STAGE], _held.RETIRED)

    def test_an_edit_while_held_retires_it(self) -> None:
        # The requirements move again while the issue is held: the capture
        # answers requirements the issue no longer has, so it is retired with
        # nothing published, and the next dispatch resumes the session over
        # what the issue now asks, the edit still unanswered until then.
        github, issue = self._edited()
        launched = github.pinned_data(_held.ISSUE)[_BASELINE]
        self._held_drift(github, issue)
        issue.body = _LATER_BODY
        self.unpaused(github, issue)
        retired = github.pinned_data(_held.ISSUE)
        self.assertEqual(
            (retired[_held.CAPTURED][_STAGE], retired[_BASELINE], github.opened_prs),
            (_held.RETIRED, launched, []),
        )
        resumed = self.dispatch(github, issue, _finished(), **_LEFT_A_COMMIT)[_held.RUN_AGENT]
        resumed.assert_called_once()
        self.assertIn(_LATER_BODY, resumed.call_args.args[1])

    def _held_drift(self, github, issue, control: str = _held.PAUSED, **seams) -> dict:
        """Dispatch the drift resume over `seams`, held under `control` as it runs; the record it left.

        The run is launched once behind the notice its road always posts, and
        its return held: nothing moved but the charge, its one accounted exit,
        and the capture -- no pull request, label, park, input, or session.
        """
        launched = Launched.over(github, _held.ISSUE)
        noticed = _behind_the_notice(github)
        self._finished_mid_run = (issue, _finished(), FakeLabel(control))
        self.dispatch(github, issue, MagicMock(side_effect=self._pauses_mid_run), **seams)
        held = launched.held(self, github, _held.ISSUE, writes=_HELD_WRITES, beside=_CAPTURED_ALONE)
        self.assertEqual(held[_held.CAPTURED][_STAGE], _held.PENDING)
        self.assertEqual(_published(github), noticed)
        return held

    def _settled(self, record: dict, handed: str) -> None:
        """The baseline `handed`, the session charged one resume, one exit accounted, and the capture handed off."""
        self.assertEqual(
            (
                record[_BASELINE],
                record[_held.SESSION_PIN],
                record[_RESUMES],
                accounted(record),
                record[_held.CAPTURED][_STAGE],
            ),
            (handed, _SESSION, 1, (1, 1), _held.HANDED_OFF),
        )

    def _edited(self):
        """The issue on `workflow:implementing` with a recorded session, its body edited off the baseline."""
        github, issue = self.seeded(**_SESSION_PIN)
        issue.body = _EDITED_BODY
        return github, issue


if __name__ == "__main__":
    unittest.main()
