# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Shared fixtures for the quota-retirement tests: one AGY issue, its implementing ticks, and what they read back.

The stops are synthetic Antigravity quota failures, normalized the way a stage
receives them. Every tick runs with rotation off, so only the retirement record
can retire a conversation.
"""
from __future__ import annotations

import os
import unittest
from dataclasses import replace
from functools import partial
from types import MappingProxyType
from unittest.mock import MagicMock, patch

from orchestrator import config
from orchestrator.workflow.engine import content_hash as _content_hash
from tests.support import agy_stream as stream
from tests.workflow.agent_failure_values import agy_quota_stop
from tests.workflow.stages.implementing import retry_test_support as support

ISSUE = 2214
RUN_AGENT = support.RUN_AGENT
AGENT_SILENT = "agent_silent"
QUOTA_REASON = "agent_session_limit"
VALIDATING = (ISSUE, support.LABEL_VALIDATING)
_RETRIES_PER_DAY = 3
_REPLY_GAP = 100
_EXTRA_ARGS = "extra_args"
# A directory that takes no new entry, and the mode it is given back; a file
# that takes no write.
FROZEN = 0o555
WRITABLE = 0o755
READ_ONLY = 0o444
# Those modes refuse nothing to root, so a test leaning on them is skipped there.
honors_modes = unittest.skipIf(os.geteuid() == 0, "root writes past a mode that refuses the write")

# The pinned fields read back.
COMMAND = "dev_agent"
PIN = "dev_session_id"
RECORD = "dev_session_retirement"
RESUMES = "dev_resume_count"
STREAK = "silent_park_count"
AWAITING = "awaiting_human"
PARKED_AS = "park_reason"
WATERMARK = "last_action_comment_id"
RUNS = "agent_runs_used"
RETRIES = "retry_count"
# A field another writer lands on the comment while a retirement is committed.
MOVED = "written_meanwhile"

# A quota stop with a tool step still running beside it, which would earn an
# ordinary unfinished command one immediate continuation.
QUOTA = agy_quota_stop(unfinished=True)
# The same stop naming no conversation of its own.
UNNAMED_QUOTA = replace(QUOTA, session_id=None)
PINNED_SESSION = stream.SESSION_ID
FRESH_SESSION = support.FRESH_SESSION
REPORTED = support._agent(session_id=FRESH_SESSION, last_message=support.DONE_MESSAGE)
# The same report from a run that handed the retired conversation's id back.
HANDED_BACK = replace(REPORTED, session_id=PINNED_SESSION)
# A fresh conversation under the pinned AGY command, in the issue's checkout.
FRESH_LAUNCH = (None, stream.BACKEND, support._FAKE_WT, stream.ARGS)
# A run that committed and left the tree clean, which publishes -- on a branch
# that carried nothing before the run, for a spawn the commits would otherwise
# read as an earlier run's to recover.
PUBLISHES = MappingProxyType({"has_new_commits": True, "dirty_files": (), "push_branch": True})
SPAWN_PUBLISHES = MappingProxyType({**PUBLISHES, "has_new_commits": (False, True)})
# An issue parked as a retryable session failure on the pinned conversation,
# with a resume budget, a silent streak, and a retry budget part spent.
PARK = MappingProxyType({AWAITING: True, PARKED_AS: AGENT_SILENT, WATERMARK: support.PARKED_WATERMARK})
PARKED = MappingProxyType({**PARK, PIN: PINNED_SESSION, STREAK: 1, RESUMES: 2, RETRIES: 1})


def retired(*, pending: bool = True) -> dict:
    """The record the quota stop leaves of the pinned conversation, the fresh one still owed or not."""
    return {"session_ids": [PINNED_SESSION], "reason": QUOTA_REASON, "recovery_pending": pending}


def launch(run_agent: MagicMock) -> tuple:
    """The resume id, backend, worktree, and arguments the last launch was made with."""
    backend, _, worktree = run_agent.call_args.args
    options = run_agent.call_args.kwargs
    return options.get(support.RESUME_SESSION_ID), backend, worktree, options.get(_EXTRA_ARGS)


def reply(github, issue, body: str) -> int:
    """One trusted reply above everything the thread and the park's watermark already hold; its id."""
    watermark = github.pinned_data(ISSUE).get(WATERMARK) or 0
    newest = max([watermark, *(comment.id for comment in issue.comments)])
    reply_id = newest + _REPLY_GAP
    author = support.FakeUser(support.TRUSTED_AUTHOR)
    issue.comments.append(support.FakeComment(id=reply_id, body=body, user=author))
    return reply_id


def stops_after(change, *change_args, stop=QUOTA) -> MagicMock:
    """A run that ends in `stop`, a quota stop unless named, during which `change`, handed `change_args`, is made."""
    return MagicMock(side_effect=partial(_ran_after, partial(change, *change_args), stop))


def _ran_after(change, stop, *_launch_args, **_launch_options):
    change()
    return stop


def edit_after_a_move(github, issue, state, *, over: dict):
    """The strict pinned-comment edit, with another writer landing on the comment just ahead of it.

    The writer lands the same field every time, so only the first edit finds
    the comment moved; one after it is ordinary.
    """
    moved = github.read_pinned_state(issue)
    moved.set(MOVED, True)
    github.write_pinned_state(issue, moved)
    return type(github).edit_pinned_state(github, issue, state, over=over)


class QuotaTicks(support._ProactiveSessionFixtureMixin):
    """Implementing ticks on one AGY issue, read back off its pinned comment."""

    def _issue(self, **seeded):
        """An implementing issue pinned to the AGY command, with `seeded` on its comment."""
        github = support.FakeGitHubClient()
        issue = support.make_issue(ISSUE, label=support.LABEL_IMPLEMENTING, body=support.IMPLEMENT_PROMPT_FRAGMENT)
        github.add_issue(issue)
        github.seed_state(
            ISSUE,
            dev_agent=stream.SPEC,
            user_content_hash=_content_hash._compute_user_content_hash(issue, set()),
            **seeded,
        )
        return github, issue

    def _tick(self, github, issue, run_agent, **run_options):
        """One implementing tick with rotation off, so only the retirement can retire a conversation."""
        with (
            patch.object(config, "MAX_RETRIES_PER_DAY", _RETRIES_PER_DAY),
            patch.object(config, "DEV_SESSION_MAX_RESUMES", 0),
        ):
            return self._run_implementing(github, issue, run_agent=run_agent, **run_options)

    def _replied(self, github, issue, run_agent=REPORTED):
        """The launch mock of one tick whose run, if one is made, reports and leaves a commit that publishes."""
        return self._tick(github, issue, run_agent, **PUBLISHES)[RUN_AGENT]

    def _spawned(self, github, issue, run_agent=HANDED_BACK):
        """The launch mock of one unparked tick whose spawn, if one is made, runs `run_agent` and publishes."""
        return self._tick(github, issue, run_agent, **SPAWN_PUBLISHES)[RUN_AGENT]

    def _paused(self, github):
        """An operator's pause the fresh issue read after a run finds."""
        view = support.make_issue(ISSUE, label=support.LABEL_IMPLEMENTING)
        view.labels.append(support.FakeLabel(support.PAUSED_LABEL))
        return patch.object(github, "get_issue", return_value=view)

    def _pinned(self, github, *keys: str) -> dict:
        """The named fields of the pinned comment."""
        pinned = github.pinned_data(ISSUE)
        return {key: pinned.get(key) for key in keys}
