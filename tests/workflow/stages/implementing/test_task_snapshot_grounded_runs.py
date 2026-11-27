# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""An implementing run's task snapshot: bound to what its prompt quoted, and recorded only where its grounding is kept.

A retry that opens a fresh conversation hands it the issue beside the
batch's read of the thread, rendered before the launch. A trusted human's
comment edited while that run is out is in neither that prompt nor the
requirements its snapshot is bound to: the fingerprint is taken over the
comments as the road froze them, never over the live objects they were read
as. A human reply whose session is gone opens a fresh conversation the same
way: its snapshot, and the grounding kept for it, are bound to the issue as
the replacement prompt quoted it -- a body edit landed as the stale run
failed included -- under the reference the reply's report is stamped with.

A human reply resuming the conversation hands it requirements its
settlement has yet to record as the baseline, which this host keeps as the
conversation's grounding. Where the host will not keep it, the snapshot is a
lost observation -- one warning and nothing recorded, never a snapshot a
later one's grounding could contradict -- and the run is accounted,
captured, and its report published as ever.
"""
from __future__ import annotations

import json
import unittest
from pathlib import Path
from types import MappingProxyType
from unittest.mock import patch

from orchestrator import config
from orchestrator.scheduler import writer_claims
from orchestrator.workflow.engine import content_hash as _content_hash, task_snapshot_grounding as _grounding
from tests.support.fakes import FakeComment, FakeUser
from tests.workflow.fixtures import _agent, accounted
from tests.workflow.stages.implementing import (
    held_capture_test_support as _held,
    task_snapshot_test_support as _support,
)

_GUIDANCE = "Use the green variant."

_REVISED = "Use the blue variant."

_EDIT = "Also display the release date."

# A session failure an operator retries, no conversation left to resume.
_SILENT = MappingProxyType({
    "awaiting_human": True, "park_reason": "agent_silent", "last_action_comment_id": 900, "dev_agent": "claude",
})

# The developer's question, its conversation left to resume.
_ASKED = MappingProxyType({
    "awaiting_human": True, "last_action_comment_id": 900, "dev_session_id": "asked-session", "dev_agent": "claude",
})

# The trusted human, and their retry of the session failure.
_ALICE = "alice"
_RETRY_ID = 1100
_RETRY = FakeComment(id=_RETRY_ID, body="/orchestrator continue", user=FakeUser(_ALICE))

# Their answer to the developer's question.
_REPLY = FakeComment(id=1000, body=_GUIDANCE, user=FakeUser(_ALICE))


class _EditedMidRun:
    """A fresh retry's run, which revises a comment the thread already held once it has its prompt."""

    def __init__(self, comment: FakeComment) -> None:
        self._comment = comment
        self.prompt = ""

    def __call__(self, _backend, prompt, *_spawn, **_options):
        """Keep the prompt, revise the comment, and return the snapshot alone."""
        self.prompt = prompt
        self._comment.body = _REVISED
        return _agent(session_id="fresh-session", last_message=_support.SNAPSHOT)


class _StaleThenFresh:
    """A reply's runs: the conversation it resumes gone, the body edited as that run fails; then the replacement's."""

    def __init__(self, issue) -> None:
        self._issue = issue
        self.prompts: list[str] = []

    def __call__(self, _backend, prompt, *_spawn, **_options):
        """Edit the body and fail as a stale session the first time; ask a question with the snapshot after."""
        self.prompts.append(prompt)
        if len(self.prompts) > 1:
            return _agent(session_id="replacement-session", last_message=f"{_support.SNAPSHOT}\nWhich label?")
        body = self._issue.body
        self._issue.body = f"{body}\n{_EDIT}"
        return _agent(last_message="", exit_code=1, stderr="No conversation found with session ID: asked-session")


def _grounding_of(github) -> Path:
    """Where this host keeps the grounding of `github`'s issue."""
    claim = writer_claims.claim_path(github.repo_id, _held.ISSUE)
    return claim.with_suffix(_grounding.GROUNDING_SUFFIX)


def _kept(github) -> dict:
    """The grounding this host keeps for `github`'s issue."""
    return json.loads(_grounding_of(github).read_text(encoding="utf-8"))


def _bound(case: GroundedRunTest) -> tuple:
    """The requirements revision and task reference the one snapshot on `case`'s sink is bound to."""
    snapshot = case.only(_support.SNAPSHOT_EVENT)
    return (snapshot[_support.REVISION], snapshot[_support.TASK_REF])


class GroundedRunTest(_support.SinkOfItsOwn, _held.HeldCaptureTicks):
    """Implementing runs resuming a park, dispatched as a poll does."""

    def test_a_comment_edited_mid_run_moves_nothing(self) -> None:
        github, issue = self.seeded(**_SILENT)
        guidance = FakeComment(id=100, body=_GUIDANCE, user=FakeUser(_ALICE))
        issue.comments.extend((guidance, _RETRY))
        run = _EditedMidRun(guidance)
        with patch.object(config, "ALLOWED_ISSUE_AUTHORS", (_ALICE,)):
            handed = _content_hash._compute_user_content_hash(issue, set())
            self.dispatch(github, issue, run, **self.sunk, has_new_commits=False)
            self.assertNotEqual(_content_hash._compute_user_content_hash(issue, set()), handed)
        self.assertIn(_GUIDANCE, run.prompt)
        self.assertNotIn(_REVISED, run.prompt)
        self.assertEqual(self.only(_support.SNAPSHOT_EVENT)[_support.REVISION], handed)

    def test_a_fresh_reply_takes_the_edit(self) -> None:
        github, issue = self.seeded(**_ASKED)
        issue.comments.append(_REPLY)
        runs = _StaleThenFresh(issue)
        with patch.object(config, "ALLOWED_ISSUE_AUTHORS", (_ALICE,)):
            delivered = _content_hash._compute_user_content_hash(issue, set())
            self.dispatch(github, issue, runs, **self.sunk, has_new_commits=False)
            edited = _content_hash._compute_user_content_hash(issue, set())
        self.assertIn(_EDIT, runs.prompts[-1])
        self.assertNotEqual(edited, delivered)
        self.assertEqual(_bound(self), (edited, _support.reference(delivered)))
        self.assertEqual(_kept(github)["requirements"], edited)

    def test_a_refused_grounding_records_nothing(self) -> None:
        # The reply's grounding is owed a place a directory takes, which the
        # host neither writes over nor takes away.
        github, issue = self.seeded(**_ASKED)
        issue.comments.append(_REPLY)
        _grounding_of(github).mkdir(parents=True)
        with self.assertLogs("orchestrator.workflow", level="WARNING") as logged:
            self.dispatch(github, issue, _support.returning(), **self.sunk, has_new_commits=True)
            warned = [line for line in logged.output if "task snapshot" in line]
        record = self.published(github)
        self.assertEqual(accounted(record), (1, 1))
        self.assertEqual(record[_held.CAPTURED]["stage"], _held.HANDED_OFF)
        self.assertEqual(self.observations(), [])
        self.assertEqual(len(warned), 1, warned)


if __name__ == "__main__":
    unittest.main()
