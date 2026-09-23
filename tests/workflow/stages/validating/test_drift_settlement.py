# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What a body-edit resume on `validating` records as having been delivered.

The prompt this route gives the developer is frozen with the record of what
it quoted, and that record is settled once the run is back. So the question
each case asks is which outcomes may cross the words on the thread: a pushed
fix, an ACK, and a question park all reached an agent and do; a shutdown kill,
a live pause, and a launch the run circuit refused reach the caller before any
pinned write and do not.

The reply written while the agent is out is the same window the resume road
has, one stage over: nothing between the freeze and the settlement re-reads
the thread, so that reply is quoted to nobody, crossed by nothing, and still
an edit on the poll that follows. What the excerpt bound cut short is the
other half of the same rule, and it is asked here as a whole tick too.

Each case compares the WHOLE prompt rather than looking for a fragment in it,
since a fragment says nothing about what else the conversation carried -- or
stopped carrying.

The revision a run's report is stamped with is the same record's, and the
window that proves it is the one between the two reads this route takes: the
drift check decides there is an edit off the live thread, and the prompt is
built from a read taken a moment later. A reply written in between is in the
prompt and in the baseline the settlement records, so a report stamped with
the earlier revision would be held against requirements its own prompt already
contained, and never published.
"""

from __future__ import annotations

import contextlib
import unittest
from unittest.mock import MagicMock, patch

from orchestrator import config
from orchestrator.github.labels import PAUSED_LABEL
from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.engine import (
    content_hash as _content_hash,
    drift as _engine_drift,
    prompt_context as _prompt_context,
    prompts as _prompts,
    report_record_state as _record_state,
)
from tests.support.fakes import (
    DEFAULT_BOT_LOGIN,
    DEFAULT_PR_HEAD_SHA,
    FakeComment,
    FakeGitHubClient,
    FakeLabel,
    FakePR,
    FakeUser,
    make_issue,
)
from tests.workflow.fixtures import (
    _TEST_SPEC,
    LABEL_VALIDATING,
    MEASURED_CANDIDATE_SHA,
    _agent,
    _PatchedWorkflowMixin,
    _reported,
)

SETTLEMENT_ISSUE = 71
SETTLEMENT_PR = 710
BRANCH = f"orchestrator/chippingway__orchestrator/issue-{SETTLEMENT_ISSUE}"

BACKEND = "claude"
DEV_SESSION = "dev-sess"
STALE_HASH = "stale-hash"
UPDATED_BODY = "updated criteria"
TRUSTED_AUTHOR = "alice"

GUIDANCE = "and add a test for the retry"
LATE_GUIDANCE = "and the cache key needs the locale in it"
# A run that answered the edit with code ends on its report, which is what
# this road holds a committing run to before it publishes anything.
FIXED_REPLY = _reported("addressed the edited criteria")
ACK_REPLY = "ACK: the pushed commits already cover it"
QUESTION_REPLY = "which of the two did you mean?"
LANDED_MID_RUN = "actually, hold on"

# A comment far past the excerpt bound, ending in words a prompt can be
# searched for: what the bound keeps is the tail, so everything above it is
# dropped from the prompt and left unread by the mark.
_PAST_THE_BOUND = 5000
_BEYOND_THE_BOUND = "b" * _PAST_THE_BOUND
OVERSIZED_TAIL = "and the tail survives"
OVERSIZED_REPLY = f"{_BEYOND_THE_BOUND} {OVERSIZED_TAIL}"

GET_ISSUE = "get_issue"
COMMENT = "comment"
# The live thread reader a fresh respawn's preamble would take a SECOND read
# through, and what it would carry if it ever ran on this road.
RECENT_COMMENTS = "_recent_comments_text"
A_SECOND_READ = "@alice: a comment this tick never froze"
RUN_AGENT = "run_agent"
LAST_ACTION_COMMENT_ID = "last_action_comment_id"
USER_CONTENT_HASH = "user_content_hash"
REVIEW_ROUND = "review_round"

# How far this issue had read its thread when the edit arrived: below every
# reply these cases write, which the fake client's ascending ids guarantee.
PARKED_AT = 100

# Where the prompt sits in the intercepted agent call.
_PROMPT_ARGUMENT = 1

# The heads a round reads around its run: the pull request's own, and the
# commit a fix leaves the checkout on.
_PUSHED_HEADS = (DEFAULT_PR_HEAD_SHA, MEASURED_CANDIDATE_SHA)
_UNMOVED_HEADS = (DEFAULT_PR_HEAD_SHA, DEFAULT_PR_HEAD_SHA)

# Where each outcome leaves the mark: on the reply the prompt carried, past
# the notice an announced park walks to above it -- a walk that could not have
# reached the notice with the reply under it still unread -- or exactly where
# the tick started, for a run nobody read the prompt through.
_REPLY = "the reply"
_PAST_OUR_NOTICE = "the park notice above it"
_UNTOUCHED = "nothing"

_SETTLES = (
    ("a pushed fix", _agent(session_id=DEV_SESSION, last_message=FIXED_REPLY), True, _REPLY),
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


def _expected_prompt(issue, *spoken: str, respawned: bool = False) -> str:
    """The whole resume prompt a tick quoting exactly `spoken` gives.

    Built from the issue and the rendered comments themselves, through the
    builder the route calls, so a case compares what the developer was really
    handed rather than looking for a fragment inside it. `respawned` puts the
    re-grounding preamble a retired session's replacement is given in front of
    it -- over the same conversation, since there is one read to quote.
    """
    convo = "\n\n".join(spoken)
    followup = _engine_drift._build_user_content_change_prompt(issue, convo)
    if not respawned:
        return followup
    preamble = _prompts._build_fresh_respawn_preamble(
        _TEST_SPEC, issue, convo, config.default_repo_specs(),
    )
    return f"{preamble}\n\n{followup}"


class _SpeaksAsWeAnnounce:
    """A human writing while the route's own notice goes out.

    The one window a case can put a reply in between the two reads this route
    takes: it lands after the drift check has decided there is an edit and
    before the prompt is built, so it is in the second read and not the first.
    """

    def __init__(self, case, body: str) -> None:
        self._case = case
        self._body = body
        self._posting = case.github.comment
        self.spoke = 0

    def __call__(self, issue, body: str):
        if not self.spoke:
            self.spoke = self._case._they_say(self._body)
        return self._posting(issue, body)


class _RunsWhileOneLands:
    """The seeded run, and a reply written in the minutes it is out for."""

    def __init__(self, case, resumed, lands: str = "") -> None:
        self._case = case
        self._resumed = resumed
        self._lands = lands
        self.landed = 0

    def __call__(self, *called, **options):
        if self._lands:
            self.landed = self._case._they_say(self._lands)
        return self._resumed


class _EditedUnderReview(_PatchedWorkflowMixin):
    """A `validating` issue whose body a human moved while the reviewer ran."""

    def setUp(self) -> None:
        self.github = FakeGitHubClient()
        self.issue = make_issue(
            SETTLEMENT_ISSUE, label=LABEL_VALIDATING, body=UPDATED_BODY,
        )
        self.github.add_issue(self.issue)
        self.github.add_pr(FakePR(number=SETTLEMENT_PR, head_branch=BRANCH))
        self.github.seed_state(
            self.issue,
            user_content_hash=STALE_HASH,
            dev_agent=BACKEND,
            dev_session_id=DEV_SESSION,
            pr_number=SETTLEMENT_PR,
            last_action_comment_id=PARKED_AT,
            review_round=1,
            branch=BRANCH,
        )

    def _they_say(self, body: str) -> int:
        """Add one reply from a trusted author, above the recorded watermark."""
        identified = self.github.next_reply_id(self.issue)
        self.issue.comments.append(
            FakeComment(identified, body, user=FakeUser(TRUSTED_AUTHOR)),
        )
        return identified

    def _paused_mid_run(self, paused: bool):
        """The freshly fetched view a guard reads after the run comes back."""
        if not paused:
            return contextlib.nullcontext()
        view = make_issue(SETTLEMENT_ISSUE, label=LABEL_VALIDATING)
        view.labels.append(FakeLabel(PAUSED_LABEL))
        return patch.object(
            self.github, GET_ISSUE, MagicMock(return_value=view),
        )

    def _drifts(self, run, *, pushed=False, paused=False, lands=""):
        """Run one whole tick over this thread with the agent's answer seeded.

        `self.landed` is left holding the id of the reply written while the
        run was out, for the case that asks what may not have crossed it.
        """
        runner = _RunsWhileOneLands(self, run, lands)
        with self._paused_mid_run(paused):
            mocks = self._run_validating(
                self.github,
                self.issue,
                run_agent=MagicMock(side_effect=runner),
                has_new_commits=pushed,
                dirty_files=(),
                push_branch=True,
                head_shas=list(_PUSHED_HEADS if pushed else _UNMOVED_HEADS),
            )
        self.landed = runner.landed
        return mocks

    def _we_said(self, which: int = 0) -> str:
        """One notice of our own, as a prompt quotes it back to an agent."""
        return _said(DEFAULT_BOT_LOGIN, self.github.posted_comments[which][1])

    def _pinned(self):
        return self.github.pinned_data(SETTLEMENT_ISSUE)

    def _assert_recorded(self, spoke: int, mark: str = _REPLY) -> None:
        """What the issue says it has read, and the revision it says it is at."""
        pinned = self._pinned()
        recorded = {
            _REPLY: spoke,
            _PAST_OUR_NOTICE: self.issue.comments[-1].id,
            _UNTOUCHED: PARKED_AT,
        }[mark]
        self.assertEqual(pinned.get(LAST_ACTION_COMMENT_ID), recorded)
        self.assertEqual(
            pinned.get(USER_CONTENT_HASH),
            STALE_HASH if mark == _UNTOUCHED
            else _content_hash._compute_user_content_hash(self.issue, set()),
        )


class ValidatingDriftSettlementTest(_EditedUnderReview, unittest.TestCase):
    """What a finished drift resume on `validating` records about its prompt."""

    def test_only_a_run_that_read_it_consumes_it(self) -> None:
        # Each case starts on its own edited issue: a reply left behind by the
        # case before would be a second one for the next prompt to quote.
        for described, run, pushed, mark in _SETTLES:
            with self.subTest(outcome=described):
                self.setUp()
                spoke = self._they_say(GUIDANCE)

                self.assertEqual(
                    _the_one_prompt(self._drifts(run, pushed=pushed)),
                    _expected_prompt(
                        self.issue,
                        _said(TRUSTED_AUTHOR, GUIDANCE),
                        self._we_said(),
                    ),
                )
                self._assert_recorded(spoke, mark)

    def test_a_live_pause_consumes_nothing(self) -> None:
        # The operator pauses while the dev is out. The route returns before
        # its result handler and before any pinned write, so the edit is still
        # unanswered and the round is unspent.
        spoke = self._they_say(GUIDANCE)

        quoted = _the_one_prompt(self._drifts(
            _agent(session_id=DEV_SESSION, last_message=FIXED_REPLY),
            pushed=True,
            paused=True,
        ))

        self.assertEqual(
            quoted,
            _expected_prompt(
                self.issue, _said(TRUSTED_AUTHOR, GUIDANCE), self._we_said(),
            ),
        )
        self.assertEqual(self._pinned().get(REVIEW_ROUND), 1)
        self._assert_recorded(spoke, _UNTOUCHED)

    def test_a_reply_written_mid_run_stays_unread(self) -> None:
        # Nothing between the freeze and the settlement re-reads the thread,
        # so the reply written while the agent was out is neither quoted nor
        # crossed -- and the revision recorded leaves it an edit next poll.
        spoke = self._they_say(GUIDANCE)

        quoted = _the_one_prompt(self._drifts(
            _agent(session_id=DEV_SESSION, last_message=QUESTION_REPLY),
            lands=LANDED_MID_RUN,
        ))

        self.assertEqual(
            quoted,
            _expected_prompt(
                self.issue, _said(TRUSTED_AUTHOR, GUIDANCE), self._we_said(),
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
        # The session this route resumes can be gone -- rotated, retired, or
        # a transcript the backend lost -- and what runs then is a fresh spawn
        # re-grounded with a conversation of its own. Read live that would be
        # a SECOND reading, newer than the record this tick settles, so the
        # frozen words are handed over and the live reader is never called.
        self.github.seed_state(
            self.issue, **{**self._pinned(), "dev_session_id": None},
        )
        spoke = self._they_say(GUIDANCE)

        with patch.object(
            _prompt_context, RECENT_COMMENTS, MagicMock(return_value=A_SECOND_READ),
        ):
            quoted = _the_one_prompt(self._drifts(
                _agent(session_id="fresh-sess", last_message=QUESTION_REPLY),
            ))

        self.assertEqual(
            quoted,
            _expected_prompt(
                self.issue,
                _said(TRUSTED_AUTHOR, GUIDANCE),
                self._we_said(),
                respawned=True,
            ),
        )
        self._assert_recorded(spoke, _PAST_OUR_NOTICE)

    def test_the_excerpt_bound_decides_the_mark(self) -> None:
        # A thread whose tail alone fills the excerpt. What reaches the
        # developer is the last characters of the conversation and nothing
        # above them, so the older comment is recorded as read by nobody and
        # is left above the watermark for the scan that delivers it.
        self._they_say(GUIDANCE)
        self._they_say(OVERSIZED_REPLY)

        quoted = _the_one_prompt(self._drifts(
            _agent(session_id=DEV_SESSION, last_message=QUESTION_REPLY),
        ))

        whole = "\n\n".join((
            _said(TRUSTED_AUTHOR, GUIDANCE),
            _said(TRUSTED_AUTHOR, OVERSIZED_REPLY),
            self._we_said(),
        ))
        self.assertEqual(
            quoted,
            _expected_prompt(self.issue, whole[-_prompt_context._EXCERPT_CHARS:]),
        )
        self.assertNotIn(GUIDANCE, quoted)
        self.assertIn(OVERSIZED_TAIL, quoted)
        self.assertEqual(self._pinned().get(LAST_ACTION_COMMENT_ID), PARKED_AT)

    def test_the_report_names_that_revision(self) -> None:
        # The reply that lands while the notice goes out is in the prompt and
        # in the baseline the settlement records, so the report the run wrote
        # has to name the same revision. Stamped with the drift check's older
        # one it would be a report about requirements the issue has already
        # moved past, which the reviewer hold refuses to publish.
        self._they_say(GUIDANCE)
        before = _content_hash._compute_user_content_hash(self.issue, set())
        speaking = _SpeaksAsWeAnnounce(self, LATE_GUIDANCE)

        with patch.object(self.github, COMMENT, side_effect=speaking):
            quoted = _the_one_prompt(self._drifts(
                _agent(session_id=DEV_SESSION, last_message=FIXED_REPLY),
                pushed=True,
            ))

        self.assertEqual(
            quoted,
            _expected_prompt(
                self.issue,
                _said(TRUSTED_AUTHOR, GUIDANCE),
                _said(TRUSTED_AUTHOR, LATE_GUIDANCE),
                self._we_said(),
            ),
        )
        self._assert_stamped(before, speaking.spoke)

    def _assert_stamped(self, before: str, spoke: int) -> None:
        """The revision the report names, the baseline, and the mark agree."""
        pinned = self._pinned()
        written = _record_state.read_pending_report(PinnedState(state_data=pinned))
        self.assertEqual(
            written.subject.requirements_revision,
            pinned.get(USER_CONTENT_HASH),
        )
        self.assertNotEqual(written.subject.requirements_revision, before)
        self.assertEqual(pinned.get(LAST_ACTION_COMMENT_ID), spoke)
