# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Which outcomes let a resume record the reply it was given as answered.

The batch is frozen before the run and settled after it, and the difference
between the two matters for exactly the outcomes where no developer read it. A
launch the run circuit turned away invoked no process; a shutdown kill left no
trustworthy result; a live pause stops before anything is persisted and the
caller returns on the same flag. Marked answered by any of those, a human's
reply is one nobody will ever hand to an agent again.

Every other outcome does record it, whatever the agent came back with -- a
timeout, an empty message, a question -- because the prompt carrying those
replies reached an agent and the park that follows mentions a human about what
the agent said rather than about the input it was given.

Three batches are never settled at all, and not because of an outcome: while
the authorization park, the measurement park, or the parked-continue
classifier has a claim on the reply, it belongs to the road that acts on it
and the whole tick is handed back unconsumed.

A run that COMMITTED and then failed to publish reaches a park further from
the resume than any of those -- the push that refused, the diff nobody could
count -- and each of them still has the whole agent run between the batch it
was resumed on and the notice it posts. So each owes the same bound, and the
last cases here are the committed failure paths that prove it.
"""

from __future__ import annotations

import unittest
from dataclasses import replace
from unittest.mock import MagicMock

from orchestrator.git.measurement.models import MeasurementFailure
from orchestrator.workflow.stages.implementing import (
    late_command as _late_command,
    late_measurement_state as _late_measurement_state,
    state as _state,
)
from tests.workflow.fixtures import _agent
from tests.workflow.stages.implementing import (
    late_consent_payloads as _consent_payloads,
    resume_batch_test_support as _support,
)

# A reply written while the agent was out -- the minutes nothing reads the
# thread in, and the comment a settlement taken off the tip would swallow.
_LANDED_MID_RUN = "actually, hold on"

# What a run that produced work comes back saying, and the two heads that say
# it really did: a park past the publication seam is only reached by a commit.
_COMMITTED = "implemented"
_BEFORE_RUN = "before-run"
_AFTER_RUN = "after-run"

# The locked session a resume needs to be one.
_BACKEND = "claude"
_SESSION = "dev-sess"

# The two ways publishing a committed candidate fails: a count the ceiling
# lets through whose push refuses, and a diff this host could not read.
_UNDER_THE_CEILING = 12
_DIFF_FAILED = MeasurementFailure.DIFF_FAILED

# How the seeded agent result is named to the resume helper, spelled once
# because the table below hands it over for most of its cases.
_RUN = "run"

# The two parks a bare `/orchestrator continue` is an answer on, and so the
# two the classifier that answers it owns a batch of: one it retries, and one
# it refuses because the park needs words a command does not carry.
_CONTINUE_PARKS = (
    ("a retryable failure", _state._AGENT_TIMEOUT),
    ("a real question", None),
)

# What each outcome does to the record, asked of the one reply the developer
# was handed.
_SETTLES = (
    ("a clean answer", {}, True),
    ("a timeout", {_RUN: _agent(timed_out=True)}, True),
    ("an empty message", {_RUN: _agent(last_message="")}, True),
    ("a shutdown kill", {_RUN: _agent(interrupted=True)}, False),
    ("a refused launch", {_RUN: replace(_agent(), invoked=False)}, False),
    ("a live pause", {"paused": True}, False),
)


class ResumeSettlementTest(_support._ParkedThread, unittest.TestCase):
    """What a finished resume records about the batch it was resumed on."""

    def test_only_a_run_that_read_it_consumes_it(self) -> None:
        # A refused launch is spelled on its own rather than beside the kill
        # the run circuit pairs it with, because it is the half of the rule
        # that says why: no process was invoked, so there is nothing that
        # could have been read.
        #
        # Each case starts on its own parked issue, since what it asks about
        # is one reply and one mark: replies left on the thread by the case
        # before would put a second one past the park's watermark.
        for described, outcome, consumed in _SETTLES:
            with self.subTest(outcome=described):
                self.setUp()
                spoke = self._they_say(_support.GUIDANCE)

                resumed = self._resumes(**outcome)

                resumed.call.assert_called_once()
                self.assertEqual(
                    self._watermark(),
                    spoke if consumed else _support.PARKED_AT,
                )

    def test_a_reply_landing_mid_run_stays_unread(self) -> None:
        # The window the run opens. What is settled is the batch the prompt
        # was built from, so a comment written while the agent was out is
        # still there for the next poll instead of being crossed by a mark
        # taken off whatever the thread ended on.
        spoke = self._they_say(_support.GUIDANCE)

        resumed = self._resumes(lands=_LANDED_MID_RUN)

        self.assertNotIn(_LANDED_MID_RUN, resumed.followup)
        self.assertEqual(self._watermark(), spoke)
        self.assertLess(spoke, resumed.landed)

    def test_an_authorization_command_is_reserved(self) -> None:
        # The last fresh reply is the command that ends a standing
        # authorization park, so this road resumes nothing and consumes
        # nothing: its own run's park would stamp the thread read to a notice
        # above the command and take it for good.
        self._seed(**{
            _state._PARK_REASON: _late_command.PARK_UNAUTHORIZED_EXEMPTION,
        })
        self._they_say(_consent_payloads.AUTHORIZE)

        resumed = self._resumes()

        resumed.call.assert_not_called()
        self.assertEqual(self._watermark(), _support.PARKED_AT)

    def test_guidance_over_it_is_an_ordinary_resume(self) -> None:
        # Somebody who asked to publish and then asked for a change has
        # replaced the command, so the developer answers the change and the
        # batch is consumed whole.
        self._seed(**{
            _state._PARK_REASON: _late_command.PARK_UNAUTHORIZED_EXEMPTION,
        })
        self._they_say(_consent_payloads.AUTHORIZE)
        spoke = self._they_say(_support.GUIDANCE)

        resumed = self._resumes()

        resumed.call.assert_called_once()
        self.assertEqual(self._watermark(), spoke)

    def test_a_marker_over_it_is_read_as_guidance(self) -> None:
        # Both roads have to agree which reply is LAST or each hands the tick
        # to the other forever. The park's own reading names our comments by
        # the id ledger alone, so the reservation is read off that same batch:
        # a marker somebody pasted over the command demotes it, this is an
        # ordinary resume, and the command reaches a developer as prose -- the
        # answer that at least moves.
        self._seed(**{
            _state._PARK_REASON: _late_command.PARK_UNAUTHORIZED_EXEMPTION,
        })
        spoke = self._they_say(_consent_payloads.AUTHORIZE)
        self._they_say(_support.FORGED)

        resumed = self._resumes()

        resumed.call.assert_called_once()
        self.assertNotIn(_support.FORGED, resumed.followup)
        self.assertEqual(self._watermark(), spoke)

    def test_a_measurement_retry_is_reserved(self) -> None:
        # The measurement park's own retry asks for a reading rather than for
        # a developer, and the whole batch is deferred rather than its last
        # reply spared -- reserved off a narrower batch, this tick would defer
        # what that road then refuses.
        self._seed(**{
            _state._PARK_REASON: (
                _late_measurement_state.PARK_MEASUREMENT_FAILED
            ),
        })
        self._they_say(_consent_payloads.CONTINUE)

        resumed = self._resumes()

        resumed.call.assert_not_called()
        self.assertEqual(self._watermark(), _support.PARKED_AT)

    def test_words_beside_that_retry_are_guidance(self) -> None:
        # A batch carrying real words is what a developer is owed, so it is an
        # ordinary resume rather than a reading nobody asked for.
        self._seed(**{
            _state._PARK_REASON: (
                _late_measurement_state.PARK_MEASUREMENT_FAILED
            ),
        })
        self._they_say(_consent_payloads.CONTINUE)
        spoke = self._they_say(_support.GUIDANCE)

        resumed = self._resumes()

        resumed.call.assert_called_once()
        self.assertEqual(self._watermark(), spoke)


class ContinueReservationTest(_support._ParkedThread, unittest.TestCase):
    """The explicit retry a resume may not spend as guidance.

    The parked-continue classifier runs in this stage's preflight and hands
    the tick back, and the minutes after that are time an operator can write
    in. A bare command landing there is in the resume's batch and in nobody
    else's: fed to a developer as prose, the retry the operator bought -- or
    the refusal a park needing real guidance owes them -- is gone, and the
    watermark moves past the words that asked for it.
    """

    def test_a_late_bare_continue_is_reserved(self) -> None:
        # Both classifications, because both are answers only that road may
        # give: a retryable park earns the retry, and one needing real
        # guidance earns the refusal. Either way this resume spends nothing.
        for described, park_reason in _CONTINUE_PARKS:
            with self.subTest(park=described):
                self.setUp()
                self._seed(**{_state._PARK_REASON: park_reason})
                self._they_say(_consent_payloads.CONTINUE)

                resumed = self._resumes(continue_claimed=True)

                resumed.call.assert_not_called()
                self.assertEqual(self._watermark(), _support.PARKED_AT)

    def test_guidance_beside_it_is_an_ordinary_resume(self) -> None:
        # `passthrough` there and an ordinary resume here, which is the same
        # answer read off the same words: a command with real words beside it
        # is guidance the developer is owed.
        self._seed(**{_state._PARK_REASON: _state._AGENT_TIMEOUT})
        self._they_say(_consent_payloads.CONTINUE)
        spoke = self._they_say(_support.GUIDANCE)

        resumed = self._resumes(continue_claimed=True)

        resumed.call.assert_called_once()
        self.assertEqual(self._watermark(), spoke)

    def test_a_road_yet_to_look_reserves_nothing(self) -> None:
        # `validating`'s shape. Its awaiting-human road classifies the command
        # itself rather than ahead of itself, so a batch deferred here would
        # be deferred to nobody and the operator's retry would never be taken.
        self._seed(**{_state._PARK_REASON: _state._AGENT_TIMEOUT})
        self._they_say(_consent_payloads.CONTINUE)

        resumed = self._resumes()

        resumed.call.assert_called_once()


class _CommitsWhileOneLands:
    """A run that commits, with one reply written while it is out.

    A class rather than a closure because the runner this repository patches
    is a value with a name, and what these cases need is a comment written
    inside the minutes the run takes.
    """

    def __init__(self, case) -> None:
        self._case = case
        self.landed = 0

    def __call__(self, *called, **options):
        self.landed = self._case._they_say(_LANDED_MID_RUN)
        return _agent(last_message=_COMMITTED)


class CommittedRunParkTest(_support._ParkedThread, unittest.TestCase):
    """What a park past the publication seam records the thread as read to.

    These roads are the furthest a resumed run gets from its own batch: the
    work is committed and the failure is a push or a reading rather than
    anything the agent said. The park is still the thing that writes down how
    far the thread was read, and the run it ends is still minutes long.
    """

    def test_a_failed_push_keeps_what_landed(self) -> None:
        # Small enough to publish and the push refuses, so the tick parks
        # holding committed work. The reply written during the run sits below
        # that notice and is nobody's to cross.
        landed = self._commits_over_guidance(
            added_lines=_UNDER_THE_CEILING, push_branch=False,
        )

        self._assert_kept(landed)

    def test_a_lost_count_keeps_what_landed(self) -> None:
        # The diff this host could not read, which parks under the typed
        # measurement reason rather than publishing a candidate nobody sized.
        landed = self._commits_over_guidance(added_lines=_DIFF_FAILED)

        self._assert_kept(landed)

    def _assert_kept(self, landed: tuple) -> None:
        """The tick read the guidance it ran on, and stopped below the rest."""
        spoke, landing = landed
        pinned = self.github.pinned_data(_support.ISSUE_NUMBER)
        self.assertEqual(pinned[_state._LAST_ACTION_COMMENT_ID], spoke)
        self.assertTrue(pinned[_state._AWAITING_HUMAN])
        self.assertLess(spoke, landing.landed)

    def _commits_over_guidance(self, **run_options) -> tuple:
        """One whole tick: guidance resumes a developer, and it commits."""
        self._seed(**{
            _state._DEV_AGENT: _BACKEND,
            _state._DEV_SESSION_ID: _SESSION,
        })
        spoke = self._they_say(_support.GUIDANCE)
        landing = _CommitsWhileOneLands(self)
        self._run_implementing(
            self.github,
            self.issue,
            run_agent=MagicMock(side_effect=landing),
            has_new_commits=True,
            dirty_files=(),
            head_shas=[_BEFORE_RUN, _AFTER_RUN],
            **run_options,
        )
        return spoke, landing


if __name__ == "__main__":
    unittest.main()
