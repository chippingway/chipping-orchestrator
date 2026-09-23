# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Which outcomes let a requirements edit be recorded as answered.

The prompt a drift resume is given is frozen with the record of what it
quoted, and that record is settled after the run. The difference matters for
exactly the outcomes where no developer read it: a shutdown kill has no
trustworthy result, a live pause stops before anything is persisted, and a
launch the run circuit turned away started no process at all, so each leaves
the edit as unanswered as it found it. Everything else records
it -- a push, an ACK, a timeout, a question park -- because the prompt
carrying those words reached an agent. Delivery is not resolution: the park a
question takes says what is wrong with the ANSWER, not with the input.

What each case compares is the WHOLE prompt, built from the issue and the
words on its thread. A fragment found inside one says nothing about the
conversation the excerpt bound cut short, the reply a second read would have
widened it by, or our own notice an agent needs to make sense of the answers.

The excerpt bound and a reply written mid-run are asked here as whole ticks
rather than of the helper, because what they are about is the road: the bound
decides the prompt, so it has to decide the mark, and nothing between the
freeze and the settlement may re-read the thread.

A pre-session edit takes the other road, and the rule is the same one asked a
step later. Clearing the park hands nobody anything, so what settles the edit
is the fresh spawn below it -- its prompt, and its outcome. A spawn the retry
budget refuses is that rule's sharpest case: no agent ran, so the edit is
still owed, and the continuation a human buys is what finally delivers it.
"""

from __future__ import annotations

import unittest
from types import MappingProxyType
from unittest.mock import MagicMock, patch

from orchestrator import config
from orchestrator.workflow.engine import (
    content_hash as _content_hash,
    drift as _engine_drift,
    prompt_context as _prompt_context,
    prompts as _prompts,
)
from tests.support.fakes import (
    DEFAULT_BOT_LOGIN,
    FakeComment,
    FakeGitHubClient,
    FakeUser,
    make_issue,
)
from tests.workflow.stages.implementing import drift_test_support as support

ACK_REPLY = support.ACK_REPLY
AWAITING_HUMAN = support.AWAITING_HUMAN
CONTINUE_COMMAND = support.CONTINUE_COMMAND
DEV_AGENT_SPEC = support.DEV_AGENT
DEV_SESSION = support.DEV_SESSION
FRESH_SESSION = support.FRESH_SESSION
GUIDANCE = support.GUIDANCE
IMPLEMENTER_PROMPT_FRAGMENT = support.IMPLEMENTER_PROMPT_FRAGMENT
LABEL_IMPLEMENTING = support.LABEL_IMPLEMENTING
LANDED_MID_RUN = support.LANDED_MID_RUN
LAST_ACTION_COMMENT_ID = support.LAST_ACTION_COMMENT_ID
OVERSIZED_REPLY = support.OVERSIZED_REPLY
OVERSIZED_TAIL = support.OVERSIZED_TAIL
PARK_REASON = support.PARK_REASON
PARK_RETRY_CAP = support.PARK_RETRY_CAP
QUESTION_REPLY = support.QUESTION_REPLY
RUN_AGENT = support.RUN_AGENT
SETTLEMENT_ISSUE = support.SETTLEMENT_ISSUE
STALE_CONTENT_HASH = support.STALE_CONTENT_HASH
TRUSTED_AUTHOR = support.TRUSTED_AUTHOR
UPDATED_REQUIREMENTS = support.UPDATED_REQUIREMENTS
USER_CONTENT_HASH = support.USER_CONTENT_HASH
_TEST_SPEC = support._TEST_SPEC
_agent = support._agent
_paused_mid_run = support._paused_mid_run
_iso_hours_ago = support._iso_hours_ago
_issue_branch = support._issue_branch
_reported = support._reported

GET_ISSUE = "get_issue"

# The live thread reader a fresh respawn's preamble would take a SECOND read
# through, and what it would carry if it ever ran on this road.
RECENT_COMMENTS = "_recent_comments_text"
A_SECOND_READ = "@alice: a comment this tick never froze"

# How far the issue had already read its thread when the edit arrived: below
# every reply these cases go on to write, which is what the fake client's own
# ascending ids guarantee.
PARKED_AT = 100

# Where the prompt sits in the intercepted agent call.
_PROMPT_ARGUMENT = 1

# A budget with nothing left in it, and the knob that decides so: the gate
# reads the cap when it runs, so a case spends the issue out against a bound
# it names rather than against whatever the host is configured for.
MAX_RETRIES = "MAX_RETRIES_PER_DAY"
_ONE_A_DAY = 1
_SPENT_BUDGET = MappingProxyType({
    "retry_count": _ONE_A_DAY,
    "retry_window_start": _iso_hours_ago(0),
})

# The two heads a tick reads around its run: one that moved because the agent
# committed, and one that did not.
_COMMITTED_HEADS = ("before-resume", "after-resume")
_UNMOVED_HEADS = ("same-sha", "same-sha")

# Where each outcome leaves the mark. `_REPLY` is the settlement itself: the
# id of the words the prompt carried. `_PAST_OUR_NOTICE` is that settlement
# plus the bounded walk an announced park takes from it, up through comments
# this orchestrator wrote and no further -- a walk that could not have reached
# the notice at all if the reply under it were still unread. `_UNTOUCHED` is a
# run nobody read the prompt through.
_REPLY = "the reply"
_PAST_OUR_NOTICE = "the park notice above it"
_UNTOUCHED = "nothing"

# What each outcome does to the record of the prompt it was given, and whether
# the resume left a commit behind.
_SETTLES = (
    ("a published commit", _agent(session_id=DEV_SESSION, last_message=_reported("addressed it")), True, _REPLY),
    ("an ACK", _agent(session_id=DEV_SESSION, last_message=ACK_REPLY), False, _REPLY),
    ("a question", _agent(session_id=DEV_SESSION, last_message=QUESTION_REPLY), False, _PAST_OUR_NOTICE),
    ("a timeout", _agent(session_id=DEV_SESSION, timed_out=True), False, _PAST_OUR_NOTICE),
    ("a shutdown kill", _agent(session_id=DEV_SESSION, interrupted=True), False, _UNTOUCHED),
    ("a refused launch", _agent(session_id=DEV_SESSION, invoked=False), False, _UNTOUCHED),
)


def _the_one_prompt(mocks) -> str:
    """The prompt of the tick's single agent run."""
    mocks[RUN_AGENT].assert_called_once()
    return mocks[RUN_AGENT].call_args[0][_PROMPT_ARGUMENT]


def _said(author: str, body: str) -> str:
    """One comment as the thread reader renders it into a prompt."""
    return f"@{author}: {body}"


# The one reply these cases put on the thread, rendered as a prompt quotes it.
_QUOTED_GUIDANCE = _said(TRUSTED_AUTHOR, GUIDANCE)


def _expected_prompt(
    issue, *spoken: str, fresh: bool = False, respawned: bool = False,
) -> str:
    """The whole prompt a tick quoting exactly `spoken` and nothing else gives.

    Built from the issue and the rendered comments themselves, through the
    same builders the stage calls, so a case compares what an agent was really
    handed rather than looking for a fragment inside it. `fresh` picks the
    spawn's implement prompt over the resume's, and `respawned` puts the
    re-grounding preamble a retired session's replacement is given in front of
    it -- over the same conversation, since there is one read to quote.
    """
    convo = "\n\n".join(spoken)
    if fresh:
        return _prompts._build_implement_prompt(
            _TEST_SPEC, issue, convo, config.default_repo_specs(),
        )
    followup = _engine_drift._build_user_content_change_prompt(issue, convo)
    if not respawned:
        return followup
    preamble = _prompts._build_fresh_respawn_preamble(
        _TEST_SPEC, issue, convo, config.default_repo_specs(),
    )
    return f"{preamble}\n\n{followup}"


class _RunsWhileOneLands:
    """The seeded run, and a reply written in the minutes it is out for.

    A class rather than a closure because it stands in for a named value --
    the agent runner this repository patches -- and the reply has to land
    between the prompt being frozen and the settlement being taken, which is
    the only window a case can put it in.
    """

    def __init__(self, case, resumed, lands: str = "") -> None:
        self._case = case
        self._resumed = resumed
        self._lands = lands
        self.landed = 0

    def __call__(self, *called, **options):
        if self._lands:
            self.landed = self._case._they_say(self._lands)
        return self._resumed


class _EditedThread(support._PatchedWorkflowMixin):
    """An implementing issue whose requirements a human moved under the dev.

    Unparked and carrying a locked session, which is the shape that takes the
    drift resume; the pre-session cases re-seed it without one.
    """

    def setUp(self) -> None:
        self.github = FakeGitHubClient()
        self.issue = make_issue(
            SETTLEMENT_ISSUE,
            label=LABEL_IMPLEMENTING,
            body=UPDATED_REQUIREMENTS,
        )
        self.github.add_issue(self.issue)
        self._seed()

    def _seed(self, **pinned) -> None:
        self.github.seed_state(self.issue, **{
            USER_CONTENT_HASH: STALE_CONTENT_HASH,
            "dev_agent": DEV_AGENT_SPEC,
            "dev_session_id": DEV_SESSION,
            LAST_ACTION_COMMENT_ID: PARKED_AT,
            "branch": _issue_branch(SETTLEMENT_ISSUE),
            **pinned,
        })

    def _they_say(self, body: str) -> int:
        """Add one reply from a trusted author, above the recorded watermark."""
        identified = self.github.next_reply_id(self.issue)
        self.issue.comments.append(
            FakeComment(identified, body, user=FakeUser(TRUSTED_AUTHOR)),
        )
        return identified

    def _we_said(self, which: int = 0) -> str:
        """One notice of our own, as a prompt quotes it back to an agent."""
        return _said(DEFAULT_BOT_LOGIN, self.github.posted_comments[which][1])

    def _drifts(self, run, *, committed=False, paused=False, lands="", commit_probes=None):
        """Run one whole tick over this thread with the agent's answer seeded.

        `self.landed` is left holding the id of the reply written while the
        run was out, for the case that asks what may not have crossed it.
        """
        runner = _RunsWhileOneLands(self, run, lands)
        with _paused_mid_run(self.github, paused):
            mocks = self._run_implementing(
                self.github,
                self.issue,
                run_agent=MagicMock(side_effect=runner),
                has_new_commits=committed if commit_probes is None else commit_probes,
                dirty_files=(),
                push_branch=True,
                head_shas=list(_COMMITTED_HEADS if committed else _UNMOVED_HEADS),
            )
        self.landed = runner.landed
        return mocks

    def _pinned(self):
        return self.github.pinned_data(SETTLEMENT_ISSUE)

    def _assert_recorded(self, spoke: int, mark: str = _REPLY) -> None:
        """What the issue says it has read, and the revision it says it is at.

        `spoke` is the reply the prompt delivered and `mark` says where the
        tick is allowed to have left the watermark: on that reply, past the
        notice an announced park walks to above it, or exactly where the tick
        started for a run that read nothing.
        """
        pinned = self._pinned()
        recorded = {
            _REPLY: spoke,
            _PAST_OUR_NOTICE: self.issue.comments[-1].id,
            _UNTOUCHED: PARKED_AT,
        }[mark]
        self.assertEqual(pinned.get(LAST_ACTION_COMMENT_ID), recorded)
        self.assertEqual(
            pinned.get(USER_CONTENT_HASH),
            STALE_CONTENT_HASH if mark == _UNTOUCHED
            else _content_hash._compute_user_content_hash(self.issue, set()),
        )


class ImplementingDriftSettlementTest(_EditedThread, unittest.TestCase):
    """What a finished drift resume records about the prompt it was given."""

    def test_only_a_run_that_read_it_consumes_it(self) -> None:
        # Each case starts on its own edited issue: a reply left behind by the
        # case before would be a second one for the next prompt to quote.
        for described, run, committed, mark in _SETTLES:
            with self.subTest(outcome=described):
                self.setUp()
                spoke = self._they_say(GUIDANCE)

                self.assertEqual(
                    _the_one_prompt(self._drifts(run, committed=committed)),
                    _expected_prompt(
                        self.issue,
                        _QUOTED_GUIDANCE,
                        self._we_said(),
                    ),
                )
                self._assert_recorded(spoke, mark)

    def test_a_live_pause_consumes_nothing(self) -> None:
        # The operator pauses while the agent is out. The handler stops before
        # its disposition and writes no pinned state, so the edit is still
        # unanswered and the reply still undelivered.
        spoke = self._they_say(GUIDANCE)

        quoted = _the_one_prompt(self._drifts(
            _agent(session_id=DEV_SESSION, last_message=_reported("addressed it")),
            committed=True,
            paused=True,
        ))

        self.assertEqual(
            quoted,
            _expected_prompt(
                self.issue, _QUOTED_GUIDANCE, self._we_said(),
            ),
        )
        self.assertEqual(self.github.opened_prs, [])
        self._assert_recorded(spoke, _UNTOUCHED)

    def test_a_reply_written_mid_run_stays_unread(self) -> None:
        # The window the run opens. What is settled is the frozen prompt, so a
        # comment written while the agent was out is neither quoted to it nor
        # crossed -- not by the settlement, and not by the walk the park above
        # it takes, which stops at the first reply nobody has delivered. The
        # revision recorded leaves it an edit for the poll that follows.
        spoke = self._they_say(GUIDANCE)

        quoted = _the_one_prompt(self._drifts(
            _agent(session_id=DEV_SESSION, last_message=QUESTION_REPLY),
            lands=LANDED_MID_RUN,
        ))

        self.assertEqual(
            quoted,
            _expected_prompt(
                self.issue, _QUOTED_GUIDANCE, self._we_said(),
            ),
        )
        recorded = self._pinned()
        self.assertGreaterEqual(recorded.get(LAST_ACTION_COMMENT_ID), spoke)
        self.assertLess(recorded.get(LAST_ACTION_COMMENT_ID), self.landed)
        self.assertNotEqual(
            recorded.get(USER_CONTENT_HASH),
            _content_hash._compute_user_content_hash(self.issue, set()),
        )

    def test_a_respawn_is_grounded_on_the_same_read(self) -> None:
        # A rotated, retired or poisoned session turns this resume into a
        # fresh spawn, and that spawn is re-grounded with a conversation of
        # its own. Read live it would be a SECOND reading of the thread,
        # newer than the record this tick settles: a comment written in
        # between would reach the agent and be handed to it again on the next
        # poll. So the frozen words are handed over, and the live reader --
        # seeded here with words nothing froze -- is not called at all.
        self._seed(dev_session_id=None)
        spoke = self._they_say(GUIDANCE)

        with patch.object(
            _prompt_context, RECENT_COMMENTS, MagicMock(return_value=A_SECOND_READ),
        ):
            quoted = _the_one_prompt(self._drifts(
                _agent(session_id=FRESH_SESSION, last_message=QUESTION_REPLY),
            ))

        self.assertEqual(
            quoted,
            _expected_prompt(
                self.issue,
                _QUOTED_GUIDANCE,
                self._we_said(),
                respawned=True,
            ),
        )
        self._assert_recorded(spoke, _PAST_OUR_NOTICE)

    def test_the_excerpt_bound_decides_the_mark(self) -> None:
        # A thread whose tail alone fills the excerpt. What reaches the agent
        # is the last characters of the whole conversation and nothing above
        # them, so the older comment is recorded as read by nobody: it is left
        # above the watermark for the scan that delivers it.
        self._they_say(GUIDANCE)
        self._they_say(OVERSIZED_REPLY)

        quoted = _the_one_prompt(
            self._drifts(_agent(session_id=DEV_SESSION, last_message=QUESTION_REPLY)),
        )

        whole = "\n\n".join((
            _QUOTED_GUIDANCE,
            _said(TRUSTED_AUTHOR, OVERSIZED_REPLY),
            self._we_said(),
        ))
        self.assertEqual(
            quoted,
            _expected_prompt(
                self.issue, whole[-_prompt_context._EXCERPT_CHARS:],
            ),
        )
        self.assertNotIn(GUIDANCE, quoted)
        self.assertIn(OVERSIZED_TAIL, quoted)
        self.assertEqual(self._pinned().get(LAST_ACTION_COMMENT_ID), PARKED_AT)


class PreSessionEditSettlementTest(_EditedThread, unittest.TestCase):
    """The edit a cleared park hands to the spawn below it."""

    def test_the_spawn_settles_the_edit(self) -> None:
        # No session to resume, so the park is cleared and a fresh spawn runs
        # this tick. Clearing delivered nothing; the implement prompt did, so
        # that is what the issue records as read.
        self._parked_without_a_session()
        spoke = self._they_say(GUIDANCE)

        quoted = _the_one_prompt(self._drifts(
            _agent(session_id=FRESH_SESSION, last_message=_reported()),
            committed=True,
            commit_probes=[False, False, True],
        ))

        self.assertIn(IMPLEMENTER_PROMPT_FRAGMENT, quoted)
        self.assertEqual(
            quoted,
            _expected_prompt(
                self.issue,
                _QUOTED_GUIDANCE,
                self._we_said(),
                fresh=True,
            ),
        )
        self.assertEqual(len(self.github.opened_prs), 1)
        self._assert_recorded(spoke)

    def test_an_interrupted_spawn_settles_nothing(self) -> None:
        # The shutdown sweep kills the fresh spawn. Nothing about the edit is
        # persisted -- not the cleared park, not the reply, not the revision
        # -- so the next process runs the same spawn on the same words.
        self._parked_without_a_session()
        spoke = self._they_say(GUIDANCE)

        quoted = _the_one_prompt(self._drifts(
            _agent(session_id=FRESH_SESSION, interrupted=True),
            commit_probes=[False, False, False],
        ))

        self.assertEqual(
            quoted,
            _expected_prompt(
                self.issue,
                _QUOTED_GUIDANCE,
                self._we_said(),
                fresh=True,
            ),
        )
        self.assertEqual(self.github.opened_prs, [])
        self.assertTrue(self._pinned().get(AWAITING_HUMAN))
        self._assert_recorded(spoke, _UNTOUCHED)

    def test_a_refused_spawn_leaves_the_edit_owed(self) -> None:
        # The budget is spent, so the gate re-parks the issue and no process
        # starts. Nothing may record the edit as answered here: a baseline
        # written for a spawn that never ran would leave the continuation a
        # human buys running against requirements nothing still calls new, and
        # the reply under it delivered to nobody.
        self._parked_without_a_session(**_SPENT_BUDGET)
        spoke = self._they_say(GUIDANCE)

        with patch.object(config, MAX_RETRIES, _ONE_A_DAY):
            mocks = self._drifts(
                _agent(session_id=FRESH_SESSION, last_message=_reported()),
                commit_probes=[False, False, False],
            )

        mocks[RUN_AGENT].assert_not_called()
        pinned = self._pinned()
        self.assertEqual(pinned.get(PARK_REASON), PARK_RETRY_CAP)
        # The baseline is the whole of what may not move: the watermark below
        # it is the refusal park's own, anchored on the notice it just posted.
        self.assertEqual(pinned.get(USER_CONTENT_HASH), STALE_CONTENT_HASH)
        self.assertLess(pinned.get(LAST_ACTION_COMMENT_ID), spoke + len(GUIDANCE))

    def test_the_continuation_delivers_it(self) -> None:
        # The tick after it. The operator's `/orchestrator continue` buys the
        # spawn the budget refused, and the edit is still there to be
        # answered: the prompt that spawn is given is the whole conversation
        # -- the reply, both notices the refusal left, and the command that
        # paid for it -- and settling that is what finally records the words
        # under it as delivered.
        self._parked_without_a_session(**_SPENT_BUDGET)
        self._they_say(GUIDANCE)
        with patch.object(config, MAX_RETRIES, _ONE_A_DAY):
            self._drifts(_agent(), commit_probes=[False, False, False])
        commanded = self._they_say(CONTINUE_COMMAND)

        quoted = _the_one_prompt(self._drifts(
            _agent(session_id=FRESH_SESSION, last_message=_reported()),
            committed=True,
            commit_probes=[False, False, True],
        ))

        self.assertEqual(
            quoted,
            _expected_prompt(
                self.issue,
                _QUOTED_GUIDANCE,
                self._we_said(),
                self._we_said(1),
                _said(TRUSTED_AUTHOR, CONTINUE_COMMAND),
                fresh=True,
            ),
        )
        self._assert_recorded(commanded)

    def _parked_without_a_session(self, **pinned) -> None:
        """The shape that has no session to resume: parked, and never spawned."""
        self._seed(**{
            "dev_agent": None,
            "dev_session_id": None,
            AWAITING_HUMAN: True,
            **pinned,
        })
