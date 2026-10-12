# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Tests for implementing rotation behavior."""

from __future__ import annotations

import copy
import unittest
from types import MappingProxyType

from orchestrator.agents.models import ToolLifecycle
from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.engine import (
    pinned_commit_models as _commit_models,
    prompts as _prompts,
)
from orchestrator.workflow.stages.implementing import (
    handoff as _handoff,
    session as _session,
    session_retirement as _session_retirement,
)
from tests.workflow import report_guidance as _report_guidance
from tests.workflow.stages.implementing import retry_test_support as support

BACKEND_CLAUDE = support.BACKEND_CLAUDE
DONE_MESSAGE = support.DONE_MESSAGE
EMPTY_SESSION_RESULT_ISSUE = support.EMPTY_SESSION_RESULT_ISSUE
FIX_PROMPT_FRAGMENT = support.FIX_PROMPT_FRAGMENT
FRESH_SESSION = support.FRESH_SESSION
FakeGitHubClient = support.FakeGitHubClient
HIGH_RESUME_COUNT = support.HIGH_RESUME_COUNT
IMPLEMENT_PROMPT_FRAGMENT = support.IMPLEMENT_PROMPT_FRAGMENT
KEY_DEV_RESUME_COUNT = support.KEY_DEV_RESUME_COUNT
KEY_DEV_SESSION_ID = support.KEY_DEV_SESSION_ID
LABEL_DOCUMENTING = support.LABEL_DOCUMENTING
LIVE_SESSION = support.LIVE_SESSION
MISSING_SESSION_ISSUE = support.MISSING_SESSION_ISSUE
MagicMock = support.MagicMock
OK_MESSAGE = support.OK_MESSAGE
POISONED_SESSION = support.POISONED_SESSION
PREAMBLE_ISSUE = support.PREAMBLE_ISSUE
PROMPT_TOO_LONG_MESSAGE = support.PROMPT_TOO_LONG_MESSAGE
RESUME_PROMPT_FRAGMENT = support.RESUME_PROMPT_FRAGMENT
RESUME_SESSION_ID = support.RESUME_SESSION_ID
_ProactiveSessionFixtureMixin = support._ProactiveSessionFixtureMixin
_TEST_SPEC = support._TEST_SPEC
_FAKE_WT = support._FAKE_WT
_agent = support._agent
make_issue = support.make_issue
KEY_AWAITING_HUMAN = support.KEY_AWAITING_HUMAN
KEY_CODEX_SESSION_ID = support.KEY_CODEX_SESSION_ID
KEY_DEV_AGENT = support.KEY_DEV_AGENT
KEY_LAST_ACTION_COMMENT_ID = support.KEY_LAST_ACTION_COMMENT_ID
KEY_SILENT_PARK_COUNT = support.KEY_SILENT_PARK_COUNT
LEGACY_SESSION = support.LEGACY_SESSION
PARKED_WATERMARK = support.PARKED_WATERMARK
LABEL_IMPLEMENTING = support.LABEL_IMPLEMENTING
RUN_AGENT = support.RUN_AGENT
FIRST_SPAWN_ISSUE = 966

KEY_RETIREMENT = "dev_session_retirement"
RECORD_IDS = "session_ids"
RECORD_REASON = "reason"
RECORD_PENDING = "recovery_pending"
OWED_PIN_REASON = "pinned while a fresh conversation was owed"
RETIRED_SESSION = "agy-quota-failed"
EARLIER_RETIRED_SESSION = "agy-earlier-failed"
STAGED_WATERMARK = PARKED_WATERMARK + 5
QUOTA_REASON = "agent_session_limit"
AGY_SPEC = "agy --model gemini-3.8-flash-high --effort high"
AGY_ARGS = ("--model", "gemini-3.8-flash-high", "--effort", "high")
EXTRA_ARGS = "extra_args"

# What a retirement may not touch: the issue's branch and pull request, its
# retry gates, its lifetime run ledger, and the park a human still owes.
CONTEXT_RECORDS = MappingProxyType({
    "branch": "orchestrator/issue-962",
    "pr_number": support.CONTINUE_PR_NUMBER,
    "retry_count": 2,
    "retry_window_start": "2026-10-11T08:00:00+00:00",
    "retry_cap_continued": 1,
    "agent_runs_used": 7,
    "agent_run_allowance": 40,
    "issue_agent_runs": 7,
    "awaiting_human": True,
    "park_reason": "agent_silent",
    KEY_LAST_ACTION_COMMENT_ID: PARKED_WATERMARK,
})


def _retirement(*session_ids: str, pending: bool = True, reason: str | None = QUOTA_REASON) -> dict:
    """The record as the pinned comment spells it."""
    return {
        RECORD_IDS: list(session_ids),
        RECORD_REASON: reason,
        RECORD_PENDING: pending,
    }


# The park a human still owes and the watermark it was taken over.
PARKED_RECORDS = MappingProxyType({
    key: CONTEXT_RECORDS[key] for key in ("awaiting_human", "park_reason", KEY_LAST_ACTION_COMMENT_ID)
})

# Records spelled readably but for one field, each naming the retired
# conversation and claiming its recovery is done, beside the reason each
# carries once a cleared pin spells it readable again.
MISSPELLED_RECORDS = (
    ("lone id for the list", {**_retirement(pending=False), RECORD_IDS: RETIRED_SESSION}, QUOTA_REASON),
    ("id list holding a non-id", {**_retirement(pending=False), RECORD_IDS: [RETIRED_SESSION, 7]}, QUOTA_REASON),
    ("reason not a string", {**_retirement(RETIRED_SESSION, pending=False), RECORD_REASON: 7}, None),
    ("flag not a boolean", {**_retirement(RETIRED_SESSION, pending=False), RECORD_PENDING: 0}, QUOTA_REASON),
)

# Every record not spelled the way a retirement writes it, the same way.
MALFORMED_RECORDS = (
    ("present null", None, OWED_PIN_REASON),
    ("not an object", "garbage", OWED_PIN_REASON),
    *MISSPELLED_RECORDS,
)

# Each record beside the id pinned with it, and whether a resume may open it.
RESUMABILITY_CASES = (
    ("retired id pinned again", _retirement(RETIRED_SESSION, pending=False), RETIRED_SESSION, False),
    ("pin while a fresh one is owed", _retirement(pending=True), LIVE_SESSION, False),
    ("unreadable record", "garbage", LIVE_SESSION, False),
    ("distinct recovered conversation", _retirement(RETIRED_SESSION, pending=False), FRESH_SESSION, True),
    *((name, record, RETIRED_SESSION, False) for name, record, _ in MALFORMED_RECORDS),
)

# The launch a recovered conversation is opened with: no resume, the pinned
# command's backend and arguments, and the issue's own worktree.
FRESH_AGY_LAUNCH = (None, "agy", _FAKE_WT, AGY_ARGS)

# The id an unparked tick's comment pins over a recovery still owed and the id
# its first spawn hands back, beside the pin and the record that spawn leaves:
# the pin the recovery was owed over, handed back, is unpinned and named.
FIRST_SPAWN_CASES = (
    (None, RETIRED_SESSION, (None, _retirement(RETIRED_SESSION, pending=True))),
    (None, FRESH_SESSION, (FRESH_SESSION, _retirement(RETIRED_SESSION, pending=False))),
    (LIVE_SESSION, LIVE_SESSION, (None, _retirement(RETIRED_SESSION, LIVE_SESSION))),
)

# The command, both pins, and the record a first spawn over a legacy pin leaves.
LEGACY_PIN_RECORDS = (KEY_DEV_AGENT, KEY_DEV_SESSION_ID, KEY_CODEX_SESSION_ID, KEY_RETIREMENT)

# The id a first spawn over an owed recovery and a legacy pin hands back,
# beside the conversation left pinned: the legacy one is refused, a distinct
# one recovers.
LEGACY_FIRST_SPAWN_CASES = (
    (LEGACY_SESSION, None),
    (FRESH_SESSION, FRESH_SESSION),
)

# The record a resume leaves over the pin a record nobody can read was owed
# over: that conversation retired by name, with the recovery still owed.
OWED_PIN_RECORD = MappingProxyType(_retirement(LIVE_SESSION, reason=OWED_PIN_REASON))

# An AGY step a run left running, which earns one continuation of its conversation.
UNFINISHED_STEP = ToolLifecycle(step_index=1, tool_name="run_command", state="ACTIVE")

# The id an owed recovery's AGY run stops on with a step unfinished, beside the
# launches that follow and the conversation left pinned.
AGY_CONTINUATION_CASES = (
    (RETIRED_SESSION, [None], None),
    (FRESH_SESSION, [None, FRESH_SESSION], FRESH_SESSION),
)


class ProactiveSessionRotationTest(
    unittest.TestCase,
    _ProactiveSessionFixtureMixin,
):
    """`--resume` replays the whole transcript every time, so a session resumed
    past `DEV_SESSION_MAX_RESUMES` is retired proactively and rebuilt fresh from
    durable state -- capping context creep BEFORE it overflows the window. Each
    resume charges one against the per-session `dev_resume_count`; a fresh spawn
    resets it and is re-grounded with the issue requirements + branch pointer.
    """

    def test_below_threshold_bumps_and_keeps_session(self) -> None:
        gh, issue = self._seeded_issue(resume_count=3)
        run_agent = MagicMock(return_value=_agent(session_id=LIVE_SESSION, last_message=DONE_MESSAGE))

        state, _ = self._run_resume(
            gh,
            issue,
            fake_run=run_agent,
            threshold=10,
        )

        self.assertEqual(
            run_agent.call_args.kwargs.get(RESUME_SESSION_ID),
            LIVE_SESSION,
            "below budget must resume in place",
        )
        self.assertEqual(
            state.get(KEY_DEV_RESUME_COUNT),
            4,
            "each resume charges one against the per-session budget",
        )
        self.assertEqual(state.get(KEY_DEV_SESSION_ID), LIVE_SESSION)

    def test_threshold_rotates_to_fresh_spawn(self) -> None:
        gh, issue = self._seeded_issue(resume_count=10)
        run_agent = MagicMock(return_value=_agent(session_id=FRESH_SESSION, last_message=OK_MESSAGE))

        state, _ = self._run_resume(
            gh,
            issue,
            fake_run=run_agent,
            threshold=10,
        )

        self.assertEqual(
            [run_agent.call_args.kwargs.get(RESUME_SESSION_ID)],
            [None],
            "budget reached must fresh-spawn (no resume id), not resume",
        )
        self.assertEqual(state.get(KEY_DEV_SESSION_ID), FRESH_SESSION)
        self.assertEqual(
            state.get(KEY_DEV_RESUME_COUNT),
            0,
            "rotation resets the budget for the new session",
        )

    def test_zero_threshold_disables_rotation(self) -> None:
        gh, issue = self._seeded_issue(resume_count=HIGH_RESUME_COUNT)
        run_agent = MagicMock(return_value=_agent(session_id=LIVE_SESSION, last_message=DONE_MESSAGE))

        state, _ = self._run_resume(
            gh,
            issue,
            fake_run=run_agent,
            threshold=0,
        )

        self.assertEqual(
            [run_agent.call_args.kwargs.get(RESUME_SESSION_ID)],
            [LIVE_SESSION],
            "0 = unbounded: must keep resuming regardless of count",
        )
        self.assertEqual(state.get(KEY_DEV_RESUME_COUNT), 100)

    def test_rotation_prompt_is_regrounded(self) -> None:
        # The rotated fresh spawn has no transcript, so its prompt must carry
        # the re-grounding preamble (issue body + branch pointer) AND the
        # stage followup appended after it. The followup here teaches no
        # report, so the report scope and receipt restriction it carries are
        # the preamble's.
        gh, issue = self._seeded_issue(resume_count=5)
        run_agent = MagicMock(return_value=_agent(session_id=FRESH_SESSION, last_message=OK_MESSAGE))

        self._run_resume(gh, issue, fake_run=run_agent, threshold=5)

        prompt = run_agent.call_args.args[1]
        self.assertIn(RESUME_PROMPT_FRAGMENT, prompt)
        self.assertIn(IMPLEMENT_PROMPT_FRAGMENT, prompt, "issue body re-grounds")
        _report_guidance.assert_teaches_report_scope(self, prompt)
        _report_guidance.assert_teaches_receipt_restriction(self, prompt)
        self.assertTrue(
            prompt.rstrip().endswith(FIX_PROMPT_FRAGMENT),
            "stage followup must be appended after the preamble",
        )

    def test_resume_in_place_prompt_has_no_preamble(self) -> None:
        # A live resume already carries the issue context in its transcript, so
        # the bare followup is sent -- no re-grounding, no token duplication.
        gh, issue = self._seeded_issue(resume_count=1)
        run_agent = MagicMock(return_value=_agent(session_id=LIVE_SESSION, last_message=DONE_MESSAGE))

        self._run_resume(gh, issue, fake_run=run_agent, threshold=10)

        self.assertEqual(run_agent.call_args.args[1], FIX_PROMPT_FRAGMENT)


class ProactiveSessionRecoveryTest(
    unittest.TestCase,
    _ProactiveSessionFixtureMixin,
):
    def test_overflow_recovery_is_regrounded(self) -> None:
        # Ties the two features together: an overflowed ("Prompt is too long")
        # resume drops the session and the recovery fresh spawn -- like the
        # rotation spawn -- is re-grounded with the preamble.
        gh, issue = self._seeded_issue(resume_count=0, sid=POISONED_SESSION)
        run_agent = MagicMock(
            side_effect=[
                _agent(session_id="", last_message=PROMPT_TOO_LONG_MESSAGE),
                _agent(session_id=FRESH_SESSION, last_message=OK_MESSAGE),
            ]
        )

        self._run_resume(gh, issue, fake_run=run_agent, threshold=10)

        agent_calls = run_agent.call_args_list
        self.assertEqual(
            [call.kwargs.get(RESUME_SESSION_ID) for call in agent_calls],
            [POISONED_SESSION, None],
        )
        self.assertEqual(
            agent_calls[0].args[1],
            FIX_PROMPT_FRAGMENT,
            "the initial resume sends the bare followup",
        )
        self.assertIn(
            RESUME_PROMPT_FRAGMENT,
            agent_calls[1].args[1],
            "the overflow-recovery fresh spawn must be re-grounded",
        )

    def test_preamble_includes_requirements_branch(self) -> None:
        issue = make_issue(PREAMBLE_ISSUE, body="do the work", title="My Issue")
        text = _prompts._build_fresh_respawn_preamble(_TEST_SPEC, issue, "@alice: please add tests", [_TEST_SPEC])
        self.assertIn("do the work", text)
        self.assertIn("@alice: please add tests", text)
        self.assertIn("git diff", text, "must point the fresh agent at the branch")
        self.assertIn("do NOT restart", text)

    def test_no_session_entry_spawns_and_persists(self) -> None:
        # `dev_agent` is pinned but `dev_session_id` is absent -- e.g. an
        # earlier backend hiccup that committed work but surfaced no session
        # id. There is nothing to resume, so the spawn must open a NEW session
        # (no resume id), re-ground it, persist the returned id, and zero the
        # stale resume count -- otherwise later resumes find no live session
        # and fresh-spawn from scratch every tick.
        gh = FakeGitHubClient()
        issue = make_issue(
            MISSING_SESSION_ISSUE,
            label=LABEL_DOCUMENTING,
            body=IMPLEMENT_PROMPT_FRAGMENT,
        )
        gh.add_issue(issue)
        gh.seed_state(
            MISSING_SESSION_ISSUE,
            dev_agent=BACKEND_CLAUDE,
            silent_park_count=0,
            dev_resume_count=7,
        )
        run_agent = MagicMock(
            return_value=_agent(
                session_id="hiccup-recovered",
                last_message=OK_MESSAGE,
            )
        )

        state, _ = self._run_resume(
            gh,
            issue,
            fake_run=run_agent,
            threshold=10,
        )

        self.assertEqual(
            [run_agent.call_args.kwargs.get(RESUME_SESSION_ID)],
            [None],
            "no live session -> fresh spawn with no resume id",
        )
        self.assertIn(
            RESUME_PROMPT_FRAGMENT,
            run_agent.call_args.args[1],
            "the fresh spawn must be re-grounded",
        )
        self.assertEqual(
            state.get(KEY_DEV_SESSION_ID),
            "hiccup-recovered",
            "the returned session id must be persisted, not dropped",
        )
        self.assertEqual(
            state.get(KEY_DEV_RESUME_COUNT),
            0,
            "the new session starts its resume budget from zero",
        )

    def test_missing_session_empty_result_keeps_clear(self) -> None:
        # The recovery spawn ALSO returns no session id (another hiccup): the
        # session stays unpinned so the next tick fresh-spawns again rather
        # than resuming a phantom id, and the resume budget is not charged.
        gh = FakeGitHubClient()
        issue = make_issue(
            EMPTY_SESSION_RESULT_ISSUE,
            label=LABEL_DOCUMENTING,
            body=IMPLEMENT_PROMPT_FRAGMENT,
        )
        gh.add_issue(issue)
        gh.seed_state(
            EMPTY_SESSION_RESULT_ISSUE,
            dev_agent=BACKEND_CLAUDE,
            silent_park_count=0,
            dev_resume_count=2,
        )
        run_agent = MagicMock(return_value=_agent(session_id="", last_message=""))

        state, _ = self._run_resume(
            gh,
            issue,
            fake_run=run_agent,
            threshold=10,
        )

        self.assertIsNone(
            run_agent.call_args.kwargs.get(RESUME_SESSION_ID),
            "still a fresh spawn, no resume id",
        )
        self.assertIsNone(state.get(KEY_DEV_SESSION_ID))
        self.assertEqual(
            state.get(KEY_DEV_RESUME_COUNT),
            2,
            "a no-session fresh spawn must not charge the resume budget",
        )


class _RetiredRecoveryMixin(_ProactiveSessionFixtureMixin):
    """Seeds an owed recovery, resumes over it, and reads back each launch and what it left pinned."""

    def _owed_recovery(self, sid: str | None = None):
        """An issue whose comment owes a fresh conversation over the retired one, under the pinned command."""
        return self._seeded_issue(
            dev_agent=AGY_SPEC, sid=sid, dev_session_retirement=_retirement(RETIRED_SESSION),
        )

    def _resumed(self, gh, issue, fake_run) -> PinnedState:
        """The state one resume over the comment alone leaves, its resume budget nowhere near spent."""
        return self._run_resume(gh, issue, fake_run=fake_run, threshold=10)[0]

    def _resume_written(self, gh, issue, state, fake_run) -> None:
        """Write `state` back as its tick would, and resume once more from the comment alone."""
        gh.write_pinned_state(issue, state)
        self._resumed(gh, issue, fake_run)

    def _pinned_and_record(self, state) -> tuple:
        """The conversation `state` -- or the comment's data -- pins and the retirement record beside it."""
        return state.get(KEY_DEV_SESSION_ID), state.get(KEY_RETIREMENT)

    def _resumed_ids(self, run_agent) -> list:
        """The conversation each launch resumed, None for a fresh one."""
        return [launch.kwargs.get(RESUME_SESSION_ID) for launch in run_agent.call_args_list]

    def _launch(self, run_agent) -> tuple:
        """The resume id, backend, worktree, and arguments the last launch was made with."""
        launch = run_agent.call_args
        return (
            launch.kwargs.get(RESUME_SESSION_ID),
            launch.args[0],
            launch.args[2],
            launch.kwargs.get(EXTRA_ARGS),
        )


class RetiredConversationTest(unittest.TestCase, _RetiredRecoveryMixin):
    """A conversation retired as failed is recorded apart from the pin and the
    counters, so nothing that clears or zeroes those brings it back: the
    retirement moves only the pins, the counters, and the record, and the
    planned resume and the post-run persistence both answer to the record --
    read fail-closed wherever it is not spelled the way a retirement writes it.
    """

    def test_retirement_keeps_command_and_context(self) -> None:
        seeds = (
            ({KEY_DEV_AGENT: AGY_SPEC, KEY_DEV_SESSION_ID: RETIRED_SESSION}, AGY_SPEC),
            ({KEY_CODEX_SESSION_ID: RETIRED_SESSION}, support.BACKEND_CODEX),
            # Already recorded, and pinned again where the command hides it
            # from the session read.
            (
                {
                    KEY_DEV_AGENT: AGY_SPEC,
                    KEY_CODEX_SESSION_ID: RETIRED_SESSION,
                    KEY_RETIREMENT: _retirement(RETIRED_SESSION),
                },
                AGY_SPEC,
            ),
        )
        for seeded, command in seeds:
            with self.subTest(seeded=sorted(seeded)):
                state = PinnedState(comment_id=1, state_data={
                    KEY_SILENT_PARK_COUNT: 1, KEY_DEV_RESUME_COUNT: 4, **CONTEXT_RECORDS, **seeded,
                })

                _session_retirement._retire_dev_session(state, RETIRED_SESSION, QUOTA_REASON)
                once = copy.deepcopy(state.data)
                _session_retirement._retire_dev_session(state, RETIRED_SESSION, QUOTA_REASON)

                self.assertEqual(state.data, once, "retiring the same conversation twice is retiring it once")
                self.assertEqual(
                    once,
                    {
                        **CONTEXT_RECORDS,
                        KEY_DEV_AGENT: command,
                        KEY_DEV_SESSION_ID: None,
                        KEY_CODEX_SESSION_ID: None,
                        KEY_SILENT_PARK_COUNT: 0,
                        KEY_DEV_RESUME_COUNT: 0,
                        KEY_RETIREMENT: _retirement(RETIRED_SESSION),
                    },
                    "only the pins, the per-session counters, and the record move; the command is kept",
                )

    def test_record_outlives_the_counters(self) -> None:
        for name, record, pinned, resumable in RESUMABILITY_CASES:
            with self.subTest(name):
                reason = self._planned_after_publication(record, pinned)

                self.assertEqual(reason is None, resumable, reason)

    def test_late_resume_charges_no_conversation(self) -> None:
        # The resumed conversation is retired while it runs, and a recovery
        # may pin a distinct one before the resume's own result is persisted.
        for recovered in (None, FRESH_SESSION):
            with self.subTest(recovered=recovered):
                state = PinnedState(state_data={
                    KEY_DEV_AGENT: AGY_SPEC, KEY_DEV_SESSION_ID: LIVE_SESSION, KEY_DEV_RESUME_COUNT: 3,
                })
                _session_retirement._retire_dev_session(state, LIVE_SESSION, QUOTA_REASON)
                _session._persist_dev_session_after_run(state, _agent(session_id=recovered), fresh_spawn=True)

                _session._persist_dev_session_after_run(
                    state,
                    _agent(session_id=LIVE_SESSION),
                    fresh_spawn=False,
                    resume_count=3,
                    resumed_session_id=LIVE_SESSION,
                )

                self.assertEqual(
                    (*self._pinned_and_record(state), state.get(KEY_DEV_RESUME_COUNT)),
                    (recovered, _retirement(LIVE_SESSION, pending=recovered is None), 0),
                    "neither the retired conversation nor the one replacing it is charged for the late resume",
                )

    def test_malformed_record_fails_closed(self) -> None:
        for name, record, reason in MALFORMED_RECORDS:
            with self.subTest(name):
                plan = _session._resolve_dev_session_for_resume(
                    make_issue(FIRST_SPAWN_ISSUE), self._seeded(record, RETIRED_SESSION),
                )
                state = self._seeded(record, RETIRED_SESSION)
                _session._persist_dev_session_after_run(state, _agent(session_id=RETIRED_SESSION), fresh_spawn=True)

                self.assertEqual(
                    (plan.fresh_spawn, plan.session.session_id, plan.session.spec),
                    (True, None, AGY_SPEC),
                    "a resolved resume opens a fresh conversation under the pinned command",
                )
                self.assertEqual(
                    self._pinned_and_record(state),
                    (None, _retirement(RETIRED_SESSION, reason=reason)),
                    "handed back, it is unpinned and named by a record spelled readable, with the recovery owed",
                )

                _session._persist_dev_session_after_run(state, _agent(session_id=FRESH_SESSION), fresh_spawn=True)

                self.assertEqual(
                    self._pinned_and_record(state),
                    (FRESH_SESSION, _retirement(RETIRED_SESSION, pending=False, reason=reason)),
                    "only a distinct conversation ends the recovery",
                )

    def test_misspelled_record_keeps_its_ids(self) -> None:
        # Nothing pins the retired conversation, so only the record can name
        # it when a fresh run hands its id back.
        for name, record, _ in MISSPELLED_RECORDS:
            with self.subTest(name):
                state = self._seeded(record, None)

                _session._persist_dev_session_after_run(state, _agent(session_id=RETIRED_SESSION), fresh_spawn=True)

                self.assertEqual(
                    self._pinned_and_record(state),
                    (None, record),
                    "an id a misspelled record still names is refused, with the recovery left owed",
                )

    def _planned_after_publication(self, record, pinned: str) -> str | None:
        """Why a resume would retire `pinned` under `record` once a publication reset the counters."""
        state = self._seeded(record, pinned)
        _handoff._reset_implementing_counters(state)
        session, reason = _session._planned_dev_session(state)
        self.assertEqual(session.session_id, pinned)
        self.assertEqual(state.get(KEY_RETIREMENT), record, "a publication reset keeps the record")
        return reason

    def _seeded(self, record, pinned: str | None) -> PinnedState:
        """A state pinning `pinned` under the AGY command beside `record`, with a silent park short of rotation."""
        return PinnedState(state_data={
            KEY_DEV_AGENT: AGY_SPEC,
            KEY_DEV_SESSION_ID: pinned,
            KEY_SILENT_PARK_COUNT: 1,
            KEY_DEV_RESUME_COUNT: 0,
            KEY_RETIREMENT: copy.deepcopy(record),
        })


class RetiredConversationRecoveryTest(unittest.TestCase, _RetiredRecoveryMixin):
    """What the next permitted developer run does over a recorded retirement:
    a fresh conversation in the same worktree under the pinned command, and
    the recovery left owed until it returns an id of its own.
    """

    def test_seeded_retirement_recovers_fresh(self) -> None:
        # The retired id is pinned again and both counters read healthy, with
        # rotation disabled: only the record can retire it.
        seeded = self._owed_recovery(sid=RETIRED_SESSION)
        run_agent = MagicMock(return_value=_agent(session_id=FRESH_SESSION, last_message=OK_MESSAGE))

        state, _ = self._run_resume(*seeded, fake_run=run_agent, threshold=0)

        self.assertEqual(
            self._launch(run_agent),
            FRESH_AGY_LAUNCH,
            "a retired conversation is never resumed; the fresh one runs the pinned command in the same worktree",
        )
        prompt = run_agent.call_args.args[1]
        self.assertIn(RESUME_PROMPT_FRAGMENT, prompt)
        self.assertIn(IMPLEMENT_PROMPT_FRAGMENT, prompt, "the issue context re-grounds it")
        self.assertEqual(
            {key: state.get(key) for key in (KEY_DEV_AGENT, KEY_DEV_SESSION_ID, KEY_DEV_RESUME_COUNT)},
            {KEY_DEV_AGENT: AGY_SPEC, KEY_DEV_SESSION_ID: FRESH_SESSION, KEY_DEV_RESUME_COUNT: 0},
        )
        self.assertEqual(
            state.get(KEY_RETIREMENT),
            _retirement(RETIRED_SESSION, pending=False),
            "a distinct id ends the recovery and the retired one stays recorded",
        )

        resumed = MagicMock(return_value=_agent(session_id=FRESH_SESSION, last_message=DONE_MESSAGE))
        self._resume_written(*seeded, state, resumed)

        self.assertEqual(
            self._launch(resumed)[0],
            FRESH_SESSION,
            "the recovered conversation is resumed like any other",
        )

    def test_recovery_stays_pending_without_a_new_id(self) -> None:
        for returned in ("", RETIRED_SESSION):
            with self.subTest(returned=returned):
                seeded = self._owed_recovery()
                run_agent = MagicMock(return_value=_agent(session_id=returned, last_message=OK_MESSAGE))

                state = self._resumed(*seeded, run_agent)
                self._resume_written(*seeded, state, run_agent)

                self.assertEqual(
                    self._resumed_ids(run_agent),
                    [None, None],
                    "no conversation was pinned, so the next run is fresh again",
                )
                self.assertEqual(
                    self._pinned_and_record(state),
                    (None, _retirement(RETIRED_SESSION)),
                    "a missing or retired id is never pinned",
                )

    def test_unreadable_record_retires_its_pin(self) -> None:
        # A record nobody can read names no conversation, so the one pinned
        # over it is named as the resume clears that pin -- and refused when
        # the fresh run hands the same id back.
        for record in ("garbage", None):
            with self.subTest(record=record):
                seeded = self._seeded_issue(dev_agent=AGY_SPEC, sid=LIVE_SESSION, dev_session_retirement=record)
                run_agent = MagicMock(return_value=_agent(session_id=LIVE_SESSION, last_message=OK_MESSAGE))

                state = self._resumed(*seeded, run_agent)
                self._resume_written(*seeded, state, run_agent)

                self.assertEqual(
                    self._resumed_ids(run_agent),
                    [None, None],
                    "the conversation the record was owed over is never resumed",
                )
                self.assertEqual(
                    self._pinned_and_record(state),
                    (None, OWED_PIN_RECORD),
                    "its id is refused and the recovery stays owed",
                )

    def test_agy_continuation_skips_retired_ids(self) -> None:
        # An AGY run left a command running, which earns one continuation of the
        # conversation it returned -- never of a retired one, before the
        # persistence that refuses to pin it even reads it.
        for returned, launches, pinned in AGY_CONTINUATION_CASES:
            with self.subTest(returned=returned):
                run_agent = MagicMock(side_effect=[
                    _agent(session_id=returned, exit_code=1, unfinished_steps=(UNFINISHED_STEP,)),
                    _agent(session_id=returned, last_message=OK_MESSAGE),
                ])

                state = self._resumed(*self._owed_recovery(), run_agent)

                self.assertEqual(
                    self._resumed_ids(run_agent),
                    launches,
                    "a distinct conversation is continued; the retired one is not resumed",
                )
                self.assertEqual(
                    self._pinned_and_record(state),
                    (pinned, _retirement(RETIRED_SESSION, pending=pinned is None)),
                )

    def test_first_spawn_pins_distinct_ids_only(self) -> None:
        # An unparked tick spawns rather than resumes, and the id its run
        # hands back answers to the same record a resume's does.
        for pinned, returned, left in FIRST_SPAWN_CASES:
            with self.subTest(pinned=pinned, returned=returned):
                launch, gh = self._first_spawn(returned, dev_session_id=pinned)

                self.assertEqual(launch, FRESH_AGY_LAUNCH)
                self.assertEqual(
                    self._pinned_and_record(gh.pinned_data(FIRST_SPAWN_ISSUE)),
                    left,
                    "a retired id is refused with recovery owed; a distinct one is pinned and ends it",
                )

    def test_first_spawn_retires_a_hidden_legacy_pin(self) -> None:
        # The spawn pins `dev_agent` before its run, after which the session
        # read no longer sees the legacy pin the recovery was owed over.
        for returned, pinned in LEGACY_FIRST_SPAWN_CASES:
            with self.subTest(returned=returned):
                launch, gh = self._first_spawn(returned, dev_agent=None, codex_session_id=LEGACY_SESSION)

                self.assertEqual(launch, (None, support.BACKEND_CODEX, _FAKE_WT, ()))
                self.assertEqual(
                    {key: gh.pinned_data(FIRST_SPAWN_ISSUE).get(key) for key in LEGACY_PIN_RECORDS},
                    {
                        KEY_DEV_AGENT: support.BACKEND_CODEX,
                        KEY_DEV_SESSION_ID: pinned,
                        KEY_CODEX_SESSION_ID: None,
                        KEY_RETIREMENT: _retirement(RETIRED_SESSION, LEGACY_SESSION, pending=pinned is None),
                    },
                    "the legacy pin is unpinned and named either way; only a distinct id ends the recovery",
                )

                run_agent = MagicMock(return_value=_agent(session_id=returned, last_message=OK_MESSAGE))
                self._resumed(gh, gh.get_issue(FIRST_SPAWN_ISSUE), run_agent)

                self.assertEqual(
                    self._resumed_ids(run_agent),
                    [pinned],
                    "the legacy conversation is never resumed; the distinct one is",
                )

    def _first_spawn(self, returned: str, **pins) -> tuple:
        """One unparked tick over an owed recovery whose spawn hands `returned` back.

        `pins` overrides the AGY command the comment pins and the conversation
        it pins under it. Answers the spawn's launch and the client.
        """
        gh = FakeGitHubClient()
        issue = make_issue(FIRST_SPAWN_ISSUE, label=LABEL_IMPLEMENTING)
        gh.add_issue(issue)
        gh.seed_state(
            FIRST_SPAWN_ISSUE,
            **{KEY_DEV_AGENT: AGY_SPEC, **pins},
            dev_session_retirement=_retirement(RETIRED_SESSION),
        )
        mocks = self._run_implementing(
            gh,
            issue,
            run_agent=_agent(session_id=returned, last_message=DONE_MESSAGE),
            has_new_commits=[False, True],
            dirty_files=(),
            push_branch=True,
        )
        return self._launch(mocks[RUN_AGENT]), gh


class RetirementCommitTest(unittest.TestCase, _RetiredRecoveryMixin):
    """The retirement landed alone on the pinned comment: durable where the
    tick that recorded it never writes, and kept whole where it does.
    """

    def test_lands_without_the_tick(self) -> None:
        # The comment pins no command yet: the tick staged it before its run,
        # beside the moves its discarded disposition would have published.
        gh, issue, state = self._read_by_tick(dev_agent=None, sid=None, **PARKED_RECORDS)
        state.set(KEY_DEV_AGENT, AGY_SPEC)
        state.set(KEY_AWAITING_HUMAN, False)
        state.set(KEY_LAST_ACTION_COMMENT_ID, STAGED_WATERMARK)

        outcome = _session_retirement._commit_dev_session_retirement(
            gh, issue, state, RETIRED_SESSION, QUOTA_REASON,
        )

        self.assertIs(outcome.status, _commit_models.CommitStatus.COMMITTED)
        self.assertEqual(
            gh.pinned_data(issue.number),
            {
                **PARKED_RECORDS,
                KEY_DEV_AGENT: AGY_SPEC,
                KEY_DEV_SESSION_ID: None,
                KEY_CODEX_SESSION_ID: None,
                KEY_SILENT_PARK_COUNT: 0,
                KEY_DEV_RESUME_COUNT: 0,
                KEY_RETIREMENT: _retirement(RETIRED_SESSION),
            },
            "the retirement and the command land; the park and the watermark stay as pinned",
        )
        self.assertEqual(state.get(KEY_RETIREMENT), _retirement(RETIRED_SESSION), "the tick carries it too")

        run_agent = MagicMock(return_value=_agent(session_id=RETIRED_SESSION, last_message=OK_MESSAGE))
        self._resumed(gh, issue, run_agent)

        self.assertEqual(
            self._launch(run_agent),
            FRESH_AGY_LAUNCH,
            "the next run reads the comment alone and opens a fresh conversation under the pinned command",
        )

    def test_keeps_the_comments_record(self) -> None:
        # Another road retired an earlier conversation on the comment after
        # this tick read it, and the tick's own whole write follows the commit.
        gh, issue, state = self._read_by_tick(dev_agent=AGY_SPEC, sid=None)
        state.set(KEY_LAST_ACTION_COMMENT_ID, STAGED_WATERMARK)
        self._retired_meanwhile(gh, issue)

        _session_retirement._commit_dev_session_retirement(gh, issue, state, RETIRED_SESSION, QUOTA_REASON)
        gh.write_pinned_state(issue, state)

        self.assertEqual(
            {key: gh.pinned_data(issue.number)[key] for key in (KEY_RETIREMENT, KEY_LAST_ACTION_COMMENT_ID)},
            {
                KEY_RETIREMENT: _retirement(EARLIER_RETIRED_SESSION, RETIRED_SESSION),
                KEY_LAST_ACTION_COMMENT_ID: STAGED_WATERMARK,
            },
            "the tick's write keeps every conversation the comment had retired, beside its own staging",
        )

        self._assert_earlier_stays_retired(gh, issue)

    def test_keeps_the_ticks_own_record(self) -> None:
        # The tick retired an earlier conversation on its state alone, and its
        # own whole write never follows the commit.
        gh, issue, state = self._read_by_tick(dev_agent=AGY_SPEC, sid=None)
        _session_retirement._retire_dev_session(state, EARLIER_RETIRED_SESSION, QUOTA_REASON)

        _session_retirement._commit_dev_session_retirement(gh, issue, state, RETIRED_SESSION, QUOTA_REASON)

        self.assertEqual(
            (gh.pinned_data(issue.number)[KEY_RETIREMENT], state.get(KEY_RETIREMENT)),
            (_retirement(EARLIER_RETIRED_SESSION, RETIRED_SESSION),) * 2,
            "the comment and the tick both keep the conversation the tick retired and never wrote",
        )
        self.assertFalse(
            _session_retirement._pin_dev_session(state, EARLIER_RETIRED_SESSION),
            "the tick refuses to pin the earlier retired conversation",
        )
        self._assert_earlier_stays_retired(gh, issue)

    def test_unnamed_retirement_names_every_pin(self) -> None:
        # A retirement handed no conversation names every pinned one in its
        # place: the one the tick read, and the one another writer pinned on
        # the comment since. Neither is cleared unnamed, so neither can be
        # pinned again as the recovery.
        gh, issue, state = self._read_by_tick(dev_agent=AGY_SPEC, sid=LIVE_SESSION)
        moved = gh.read_pinned_state(issue)
        moved.set(KEY_DEV_SESSION_ID, FRESH_SESSION)
        gh.write_pinned_state(issue, moved)

        _session_retirement._commit_dev_session_retirement(gh, issue, state, None, QUOTA_REASON)

        self.assertEqual(
            (gh.pinned_data(issue.number)[KEY_RETIREMENT], state.get(KEY_RETIREMENT)),
            (_retirement(FRESH_SESSION, LIVE_SESSION),) * 2,
            "the comment's pin and the tick's are both named retired",
        )
        self.assertEqual(
            [_session_retirement._pin_dev_session(state, pinned) for pinned in (FRESH_SESSION, LIVE_SESSION)],
            [False, False],
            "neither is pinned again",
        )

    def _assert_earlier_stays_retired(self, gh, issue) -> None:
        """A run from the comment alone that hands the earlier retired conversation back leaves it unpinned."""
        run_agent = MagicMock(return_value=_agent(session_id=EARLIER_RETIRED_SESSION, last_message=OK_MESSAGE))
        resumed = self._resumed(gh, issue, run_agent)

        self.assertEqual(
            self._pinned_and_record(resumed),
            (None, _retirement(EARLIER_RETIRED_SESSION, RETIRED_SESSION)),
            "the earlier retired conversation is not pinned again",
        )

    def _read_by_tick(self, **records) -> tuple:
        """A seeded issue and the state a tick read it as."""
        gh, issue = self._seeded_issue(**records)
        return gh, issue, gh.read_pinned_state(issue)

    def _retired_meanwhile(self, gh, issue) -> None:
        """Another road retires an earlier conversation on the comment, behind the reading a tick holds."""
        other = gh.read_pinned_state(issue)
        _session_retirement._retire_dev_session(other, EARLIER_RETIRED_SESSION, QUOTA_REASON)
        gh.write_pinned_state(issue, other)
