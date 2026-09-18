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
from types import MappingProxyType
from unittest.mock import MagicMock, patch

from orchestrator.git.measurement.models import MeasurementFailure
from orchestrator.git.worktrees import paths as _worktree_paths
from orchestrator.workflow.engine import (
    issue_processing as _issue_processing,
    poll_models as _poll_models,
    run_ledger_values as _run_ledger_values,
)
from orchestrator.workflow.stages.implementing import (
    disposition as _disposition,
    late_command as _late_command,
    late_measurement_state as _late_measurement_state,
    state as _state,
)
from tests.workflow.fixtures import (
    _TEST_SPEC,
    LABEL_IMPLEMENTING,
    _agent,
    _stand_opened_prs_on_the_push,
)
from tests.workflow.stages.implementing import (
    late_consent_case as _consent_case,
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

# Where a whole tick's agent run is intercepted, and where its prompt sits in
# the call: the two cases that ask what an agent was really handed run the
# dispatched handler rather than the resume helper.
_RUN_AGENT = "run_agent"
_PROMPT_ARGUMENT = 1

# The opening line of the prompt an explicit retry issues. It carries no
# comment of anybody's, which is the whole difference from a generic resume.
_RETRIED = "Resuming after a session/usage limit"

# What the retried session answers with: words and no commit, the end that
# parks again without publishing anything.
_ASKS = "which of the two did you mean?"

# A lifetime ledger spent to its last run, so the circuit refuses the resume
# before any process starts -- and the command that buys it more.
_SPENT = 3
_SPENT_LEDGER = MappingProxyType({
    _run_ledger_values.AGENT_RUN_ALLOWANCE: _SPENT,
    _run_ledger_values.AGENT_RUNS_USED: _SPENT,
})
_ADD_RUNS = "/orchestrator add-agent-runs 3"

# What the refusal a bare continue earns on a park needing real words says.
_NEEDS_GUIDANCE = "needs your actual guidance"

# The two parks a reopened resume can end on, what the run behind each came
# back with, and what a bare `/orchestrator continue` then earns: the explicit
# retry on a session failure, the refusal on a question.
_CONTINUED_PARKS = (
    ("a timeout", _agent(timed_out=True), _RETRIED),
    ("a question", _agent(last_message=_ASKS), _NEEDS_GUIDANCE),
)

# How a resume's followup opens: the reply it delivers, quoted by its author.
# A resume continues a pinned session, so this is the whole head of the
# prompt -- and a fresh spawn's opens with the issue it re-grounds instead.
_QUOTED = f"@{_support.TRUSTED_AUTHOR}: {{said}}"

# Which agent a run was, as the spawn event every launch records names it.
_EVENT = "event"
_SPAWNED = "agent_spawn"
_ROLE = "agent_role"
_DEVELOPER = "developer"

# The quiet publication a timeout park with no reply on it is tried with.
_QUIET_RECOVERY = "_try_recover_implementing_timeout_park"

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
        #
        # Asked twice, the second with a run-limit grant's command written
        # under it to lift that hold. The park's own road reads past an
        # answered grant, so this one has to: taking the grant as the last
        # word, it would deliver the command as prose to a developer.
        for described, after in (
            ("alone", ()),
            ("over an answered grant", (_consent_payloads.ANSWERED_GRANT,)),
        ):
            with self.subTest(command=described):
                self.setUp()
                self._seed(**{
                    _state._PARK_REASON: _late_command.PARK_UNAUTHORIZED_EXEMPTION,
                })
                for said in (_consent_payloads.AUTHORIZE, *after):
                    self._they_say(said)

                resumed = self._resumes()

                resumed.call.assert_not_called()
                self.assertEqual(self._watermark(), _support.PARKED_AT)

    def test_guidance_over_it_is_an_ordinary_resume(self) -> None:
        # Somebody who asked to publish and then asked for a change has
        # replaced the command, so the developer answers the change and the
        # batch is consumed whole.
        #
        # Asked twice, the second over a reply quoting the pinned record's
        # marker. The park's own reading names that record by id and counts
        # the reply as the last word; a freeze reading it by marker would drop
        # the reply, find the command last, reserve the tick for that park's
        # road, and the two would hand it back and forth for good.
        for said in (_support.GUIDANCE, _support.QUOTES_THE_RECORD):
            with self.subTest(said=said):
                self.setUp()
                self._seed(**{
                    _state._PARK_REASON: (
                        _late_command.PARK_UNAUTHORIZED_EXEMPTION
                    ),
                })
                self._they_say(_consent_payloads.AUTHORIZE)
                spoke = self._they_say(said)

                resumed = self._resumes()

                resumed.call.assert_called_once()
                self.assertIn(said, resumed.followup)
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

    Which batch each of them classifies is the other half of it. Both the
    preflight and this reservation read the replies a prompt would be built
    from, so a comment neither would deliver cannot make one of them call the
    batch mixed while the other hands the command over as prose.
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

    def test_our_notice_over_a_command_still_retries(self) -> None:
        # The whole two-tick shape: the operator writes the command while the
        # developer is out, the timeout park posts its notice above it, and
        # the bound leaves both unread. Counted as somebody's words, that
        # notice makes the thread look mixed to the classifier, the command
        # falls through as prose, and a developer is paid to read
        # `/orchestrator continue` as requirements.
        self._times_out_while_one_commands()

        prompt = self._prompt_of_the_next_tick()

        self.assertIn(_RETRIED, prompt)
        self.assertNotIn(_consent_payloads.CONTINUE, prompt)

    def test_a_forged_marker_over_it_still_retries(self) -> None:
        # The same mismatch one step over, and the reason the marker alone
        # settles nothing: a body anybody may paste reaches no prompt, so it
        # may not decide who owns the batch either.
        self._seed(**{
            _state._PARK_REASON: _state._AGENT_TIMEOUT,
            _state._DEV_AGENT: _BACKEND,
            _state._DEV_SESSION_ID: _SESSION,
        })
        self._they_say(_consent_payloads.CONTINUE)
        self._they_say(_support.FORGED)

        prompt = self._prompt_of_the_next_tick()

        self.assertIn(_RETRIED, prompt)
        self.assertNotIn(_consent_payloads.CONTINUE, prompt)
        self.assertNotIn(_support.FORGED, prompt)

    def _times_out_while_one_commands(self) -> None:
        """One whole tick: guidance resumes a developer, it times out, and the
        operator writes the retry while it is still out.

        The park this leaves is the premise of the tick after it -- the
        command unread under a notice of ours that the mark stops below.
        """
        self._seed(**{
            _state._DEV_AGENT: _BACKEND,
            _state._DEV_SESSION_ID: _SESSION,
        })
        guided = self._they_say(_support.GUIDANCE)
        landing = _RunsWhileOneLands(
            self, _consent_payloads.CONTINUE, _agent(timed_out=True),
        )
        self._run_implementing(
            self.github,
            self.issue,
            run_agent=MagicMock(side_effect=landing),
            has_new_commits=False,
        )
        pinned = self.github.pinned_data(_support.ISSUE_NUMBER)
        self.assertEqual(pinned[_state._PARK_REASON], _state._AGENT_TIMEOUT)
        self.assertEqual(pinned[_state._LAST_ACTION_COMMENT_ID], guided)

    def _prompt_of_the_next_tick(self) -> str:
        """The one prompt the poll after that park hands an agent."""
        mocks = self._run_implementing(
            self.github,
            self.issue,
            run_agent=_agent(last_message=_ASKS),
            has_new_commits=False,
        )
        mocks[_RUN_AGENT].assert_called_once()
        return mocks[_RUN_AGENT].call_args.args[_PROMPT_ARGUMENT]


class RunLimitCycleTest(_support._ParkedThread, unittest.TestCase):
    """The run a spent ledger refuses, and the reply it was handed.

    The refusal comes from the circuit, below the resume: no process starts,
    so the resume records nothing. But the park that refusal takes posts a
    notice above the reply, the tick after it repairs that notice's lost write,
    and the grant that lifts the park consumes what it read -- and each of
    those is a watermark write. Any of them crossing the reply marks answered
    a batch no agent ever read. And the grant is where the run the human paid
    for happens, so what it puts back decides which run that is: the resume
    that was refused, on the reply it was refused on. So the whole cycle is
    driven here through the dispatcher's hold and the real circuit, rather
    than with a refused result seeded under the resume.
    """

    def test_the_grant_runs_the_resume_it_refused(self) -> None:
        # Cleared rather than put back, the park the refusal stood in front
        # of is gone and the grant's tick takes the stage's ordinary road: a
        # fresh spawn quoting the reply -- and the grant command -- with no
        # record that either was delivered, so the poll after it hands the
        # developer the same reply again.
        self._seed(**{
            _state._DEV_AGENT: _BACKEND,
            _state._DEV_SESSION_ID: _SESSION,
            **_SPENT_LEDGER,
        })
        guided = self._they_say(_support.GUIDANCE)

        granted = self._refused_then_granted()
        after = self._tick()

        followup = granted[_RUN_AGENT].call_args.args[_PROMPT_ARGUMENT]
        self.assertTrue(followup.startswith(_QUOTED.format(said=_support.GUIDANCE)))
        self.assertNotIn(_ADD_RUNS, followup)
        self.assertEqual(
            [
                recorded[_ROLE] for recorded in self.github.recorded_events
                if recorded[_EVENT] == _SPAWNED
            ],
            [_DEVELOPER],
        )
        self.assertGreaterEqual(self._pinned_watermark(), guided)
        after[_RUN_AGENT].assert_not_called()

    def test_a_continue_after_it_is_classified_once(self) -> None:
        # The grant could not consume its own command without the reply below
        # it, so the command is still unread when the resumed run parks again
        # -- on a timeout or on a question -- and the operator answers that
        # park with a bare `/orchestrator continue`. The preflight and the
        # frozen batch have to read the same batch then: one seeing the grant
        # command beside the continue passes the tick through, the other
        # seeing the continue alone reserves it, and the park stands forever
        # with nothing retried, refused, or said.
        for described, park, answered in _CONTINUED_PARKS:
            with self.subTest(park=described):
                self.setUp()
                self._parked_again(park)
                commanded = self._they_say(_consent_payloads.CONTINUE)

                earned = _answer_to_the_continue(self._tick(), self.github)
                self.assertIn(answered, earned)
                self.assertNotIn(_ADD_RUNS, earned)
                self.assertGreaterEqual(self._pinned_watermark(), commanded)

    def test_an_unanswered_timeout_still_recovers(self) -> None:
        # The same leftover with nothing written after it. The timeout park is
        # the one a tick may lift without a human -- a commit that landed
        # after the timeout is published quietly -- and only a reply holds
        # that recovery off, since a reply is what the resume behind it owns.
        # The grant's command is no reply: the resume would hand nobody that
        # batch, so counted here it holds the recovery off for a resume that
        # does nothing, and the stranded commit waits on a human for good.
        self._parked_again(_agent(timed_out=True))

        with patch.object(
            _disposition, _QUIET_RECOVERY, return_value=_state._REASON_STUCK,
        ) as recovered:
            polled = self._tick()
            recovered.assert_called_once()

        polled[_RUN_AGENT].assert_not_called()

    def _parked_again(self, park) -> None:
        """The cycle, its grant's resume parking again on `park`."""
        self._seed(**{
            _state._DEV_AGENT: _BACKEND,
            _state._DEV_SESSION_ID: _SESSION,
            **_SPENT_LEDGER,
        })
        self._they_say(_support.GUIDANCE)
        self._refused_then_granted(park)

    def _refused_then_granted(self, answers=None):
        """The whole park: refused, its notice repaired, then bought past.

        Three polls, and each ends in a watermark write: the park's notice,
        the next tick's repair of that notice's lost write, and the grant. No
        agent reads the reply on the first two, so neither may record it as
        read. The third runs the one agent the grant paid for -- the resume
        the first refused, answering with `answers` -- and it is returned.
        """
        refused = self._tick()
        self._they_say(_ADD_RUNS)
        replayed = self._tick()
        granted = self._tick(answers)

        refused[_RUN_AGENT].assert_not_called()
        replayed[_RUN_AGENT].assert_not_called()
        granted[_RUN_AGENT].assert_called_once()
        return granted

    def _tick(self, answers=None):
        """One whole poll of this issue: the run-limit hold, then the stage.

        The agent that runs, where one does, answers with `answers` and no
        commit -- words by default, the end that parks on a question, so the
        next poll is an awaiting-human resume again.
        """
        return self._run(
            lambda: _issue_processing._route_issue_to_handler(
                self.github, _TEST_SPEC, self.issue, LABEL_IMPLEMENTING,
                reading=_poll_models._POLLED_OPEN,
            ),
            run_agent=MagicMock(
                return_value=_agent(last_message=_ASKS) if answers is None else answers,
            ),
            has_new_commits=False,
        )

    def _pinned_watermark(self):
        return self.github.pinned_data(_support.ISSUE_NUMBER).get(
            _state._LAST_ACTION_COMMENT_ID,
        )


class RunLimitAuthorizationTest(_consent_case._ParkedCase, unittest.TestCase):
    """The run-limit cycle on an issue whose candidate waits on an operator.

    The grant cannot consume its own command without the reply its park
    interrupted, so the command outlives the cycle -- and a later park that
    asks for the LAST word on the thread is the one that can mistake it for
    one. Both halves of that question, the park's own reading and the frozen
    resume batch, take it out the same way: counted by either alone, the tick
    goes to a road that cannot act on what it was handed.
    """

    def test_the_grant_alone_is_no_reply_to_the_park(self) -> None:
        # The grant's own tick runs the resume it lifted the refusal of,
        # which delivers the preserved reply, and the candidate that run
        # commits is held for an operator; the park's mark stops below the
        # grant command. Read as somebody speaking, that command hands every
        # later poll to a resume that drops it and has nothing to deliver --
        # so the park's own road holds instead, and the authorization the
        # operator then writes publishes.
        self._cycle(_consent_payloads.measured_pair(
            candidate_sha=_consent_payloads.STRANGER_SHA,
        ))
        granted = self._reply(_consent_payloads.ANSWERED_GRANT)
        self._tick()

        resumed = self._tick()

        resumed[_consent_payloads.RUN_AGENT].assert_called_once()
        self.assertIn(
            _consent_payloads.GUIDANCE,
            resumed[_consent_payloads.RUN_AGENT].call_args.args[_PROMPT_ARGUMENT],
        )
        self._assert_still_parked()
        self.assertLess(self._pinned()[_state._LAST_ACTION_COMMENT_ID], granted)
        read = _late_command._reads_the_thread(self.github, self.issue, self._state())
        self.assertFalse(read.spoke)
        self._reply(_consent_payloads.AUTHORIZE)
        self._assert_published(self._tick())

    def test_a_command_under_the_grant_publishes(self) -> None:
        # An operator who meant to publish as-is writes the authorization
        # while the run-limit hold stands, and then the grant that lifts it.
        # The grant puts the authorization park back, so its own tick reads
        # the command -- unless the grant is read as the last word, which
        # hides the command from the park's road and leaves the resume behind
        # it to drop the grant and pay a developer to read it as prose.
        self._cycle(_consent_payloads.measured_pair())
        self._reply(_consent_payloads.AUTHORIZE)
        self._reply(_consent_payloads.ANSWERED_GRANT)
        repaired = self._tick()

        published = self._tick()

        self._assert_no_agent(repaired)
        repaired[_consent_payloads.PUSH_BRANCH].assert_not_called()
        self._assert_published(published)

    def _cycle(self, pair: dict) -> None:
        """The park, the reply a spent ledger refuses to resume on, the hold."""
        self._seed(**pair, **{
            _state._DEV_AGENT: _BACKEND,
            _state._DEV_SESSION_ID: _SESSION,
            **_SPENT_LEDGER,
        })
        self._reply(_consent_payloads.GUIDANCE)
        refused = self._tick()
        refused[_consent_payloads.RUN_AGENT].assert_not_called()

    def _tick(self):
        """One whole poll through the dispatcher's run-limit hold.

        The developer that runs, where one does, commits the candidate the
        park is about -- over the ceiling, so it is held for an operator.
        """
        opened_before = len(self.github.opened_prs)
        with patch.object(
            _worktree_paths,
            _consent_payloads.WORKTREE_PATH,
            return_value=_consent_payloads.TEMP_WORKTREE_ROOT,
        ):
            polled = self._run(
                lambda: _issue_processing._route_issue_to_handler(
                    self.github, _TEST_SPEC, self.issue, LABEL_IMPLEMENTING,
                    reading=_poll_models._POLLED_OPEN,
                ),
                run_agent=MagicMock(return_value=_agent(last_message=_COMMITTED)),
                has_new_commits=True,
                added_lines=_consent_payloads.OVERSIZED_ADDITIONS,
            )
        _stand_opened_prs_on_the_push(self.github, polled, opened_before)
        return polled


def _answer_to_the_continue(polled, github) -> str:
    """What one poll answered a bare continue with, in the words it used.

    The prompt of the one run it started where it started one -- the retry's
    own, or the continue handed over as prose -- and otherwise the last thing
    it said. Each answer a case expects is a sentence only one of those holds,
    so a continue spent as guidance, refused where it was owed a retry, or
    answered with nothing at all fails the same one assertion.
    """
    ran = polled[_RUN_AGENT]
    if not ran.called:
        return github.posted_comments[-1][1] if github.posted_comments else ""
    ran.assert_called_once()
    return ran.call_args.args[_PROMPT_ARGUMENT]


class _RunsWhileOneLands:
    """A developer run with one reply written inside the minutes it takes.

    A class rather than a closure because the runner this repository patches
    is a value with a name, and what these cases need is a comment written
    while the run is out -- the only window a park's own notice can land
    above, and so the only one that can put our sentence between a command and
    the road that owns it.
    """

    def __init__(self, case, said: str = _LANDED_MID_RUN, answers=None) -> None:
        self._case = case
        self._said = said
        self._answers = (
            _agent(last_message=_COMMITTED) if answers is None else answers
        )
        self.landed = 0

    def __call__(self, *called, **options):
        self.landed = self._case._they_say(self._said)
        return self._answers


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
        landing = _RunsWhileOneLands(self)
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
