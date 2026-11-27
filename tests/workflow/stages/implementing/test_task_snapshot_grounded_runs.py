# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""An implementing run's task snapshot: bound to what its prompt quoted, and recorded only where its grounding is kept.

A retry that opens a fresh conversation hands it the issue beside the
batch's read of the thread, rendered before the launch. A trusted human's
comment edited while that run is out is in neither that prompt nor the
requirements its snapshot is bound to: the fingerprint is taken over the
comments as the road froze them, never over the live objects they were read
as. A reply revised after its batch was read, as the resume prepares its
checkout, is quoted as read -- by the conversation resumed, and by a fresh
replacement's preamble and followup alike -- and the snapshot is bound to
that read. A human reply whose session is gone opens a fresh conversation
the same way: its snapshot, and the grounding kept for it, are bound to the issue as
the replacement prompt quoted it -- a body edit landed as the stale run
failed included -- under the reference the reply's report is stamped with.
That grounding is kept beside the baseline the reply settles, so the
operator's retry resuming the replacement once the reply settled is bound to
the edit too.

A human reply resuming the conversation hands it the requirements its
settlement records as the baseline, so whatever this host kept for that
conversation is taken away. Where the host will not take that change, the
snapshot is a lost observation -- one warning and nothing recorded, never a
snapshot a stale grounding could contradict -- and the run is accounted,
captured, and its report published as ever.
"""
from __future__ import annotations

import unittest
from pathlib import Path
from types import MappingProxyType
from unittest.mock import MagicMock, patch

from orchestrator import config
from orchestrator.scheduler import writer_claims
from orchestrator.workflow.engine import content_hash as _content_hash, task_snapshot_grounding as _grounding
from orchestrator.workflow.stages.implementing import worktree as _worktree
from tests.support.fakes import FakeComment, FakeUser
from tests.workflow.fixtures import _FAKE_WT, _agent, accounted
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

# The seams of a tick whose branch the run left where it was.
_UNMOVED = MappingProxyType({"has_new_commits": False, "head_shas": _held.UNMOVED})

_REPLACEMENT = "replacement-session"

# What the CLI answers a resume of a conversation it no longer has with.
_STALE = "No conversation found with session ID: asked-session"

# What a reply's launches resume: the stale conversation, a fresh one, then the retry's of that.
_LAUNCHES = (_ASKED["dev_session_id"], None, _REPLACEMENT)


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
    """A reply's runs: the conversation it resumes gone, the body edited as that run fails; then the replacement's.

    Keeps every prompt it was handed and the conversation each launch resumed, in order.
    """

    def __init__(self, issue) -> None:
        self._issue = issue
        self.prompts: list[str] = []
        self.resumed: list[str | None] = []

    def __call__(self, _backend, prompt, *_spawn, **options):
        """Edit the body and fail as a stale session the first time; return the snapshot alone after."""
        self.prompts.append(prompt)
        self.resumed.append(options["options"].resume_session_id)
        if len(self.prompts) > 1:
            return _agent(session_id=_REPLACEMENT, last_message=_support.SNAPSHOT)
        body = self._issue.body
        self._issue.body = f"{body}\n{_EDIT}"
        return _agent(last_message="", exit_code=1, stderr=_STALE)


class _EditedAtCheckout:
    """The checkout a reply's resume prepares once its batch is read, revising the reply as it does."""

    def __init__(self, comment: FakeComment) -> None:
        self._comment = comment

    def __call__(self, *_checkout):
        """Revise the reply, and hand back the issue's checkout."""
        self._comment.body = _REVISED
        return _FAKE_WT


def _grounding_of(github) -> Path:
    """Where this host keeps the grounding of `github`'s issue."""
    claim = writer_claims.claim_path(github.repo_id, _held.ISSUE)
    return claim.with_suffix(_grounding.GROUNDING_SUFFIX)


def _bound(case: GroundedRunTest) -> list[tuple]:
    """The requirements revision and task reference each snapshot on `case`'s sink is bound to, in order."""
    return [
        (snapshot[_support.REVISION], snapshot[_support.TASK_REF])
        for snapshot in case.events(_support.SNAPSHOT_EVENT)
    ]


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

    def test_an_edit_at_checkout_moves_nothing(self) -> None:
        # The conversation the reply resumes, then one gone and replaced by a
        # fresh one: every prompt quotes the reply as the batch read it, and
        # the snapshot is bound to that read.
        self.enterContext(patch.object(config, "ALLOWED_ISSUE_AUTHORS", (_ALICE,)))
        stale = _agent(last_message="", exit_code=1, stderr=_STALE)
        for launched in (
            (_agent(session_id=_ASKED["dev_session_id"], last_message=_support.SNAPSHOT),),
            (stale, _agent(session_id=_REPLACEMENT, last_message=_support.SNAPSHOT)),
        ):
            prompts, read = self._edited_at_checkout(launched)
            quoted = {(_GUIDANCE in prompt, _REVISED in prompt) for prompt in prompts}
            with self.subTest(launches=len(launched)):
                self.assertEqual(len(prompts), len(launched))
                self.assertEqual(quoted, {(True, False)})
                self.assertEqual(self.only(_support.SNAPSHOT_EVENT)[_support.REVISION], read)

    def test_a_fresh_reply_keeps_the_edit(self) -> None:
        # The reply's tick, then the operator's retry of the silence it
        # parked on, resuming the replacement past the reply's settlement:
        # both bound to the edit the replacement's prompt quoted, under the
        # reference the reply settled.
        self.enterContext(patch.object(config, "ALLOWED_ISSUE_AUTHORS", (_ALICE,)))
        github, issue = self.seeded(**_ASKED)
        issue.comments.append(_REPLY)
        runs = _StaleThenFresh(issue)
        self.dispatch(github, issue, runs, **self.sunk, **_UNMOVED)
        issue.comments.append(_RETRY)
        self.dispatch(github, issue, runs, **self.sunk, **_UNMOVED)
        settled = github.pinned_data(_held.ISSUE)["user_content_hash"]
        bound = (_content_hash._compute_user_content_hash(issue, set()), _support.reference(settled))
        self.assertEqual(runs.resumed, list(_LAUNCHES))
        self.assertIn(_EDIT, runs.prompts[1])
        self.assertNotEqual(bound[0], settled)
        self.assertEqual(_bound(self), [bound, bound])

    def test_a_refused_grounding_records_nothing(self) -> None:
        # The reply clears the conversation's grounding from a place a
        # directory takes, which the host neither writes over nor takes away.
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

    def _edited_at_checkout(self, launched: tuple) -> tuple[list[str], str]:
        """Dispatch a reply the resume's checkout revises, run as `launched`: their prompts, and the read before."""
        self.sink.unlink(missing_ok=True)
        github, issue = self.seeded(**_ASKED)
        reply = FakeComment(id=_REPLY.id, body=_GUIDANCE, user=FakeUser(_ALICE))
        issue.comments.append(reply)
        read = _content_hash._compute_user_content_hash(issue, set())
        runs = MagicMock(side_effect=launched)
        with patch.object(_worktree, "_ensure_resume_worktree", _EditedAtCheckout(reply)):
            self.dispatch(github, issue, runs, **self.sunk, **_UNMOVED)
        self.assertEqual(reply.body, _REVISED)
        return [called.args[1] for called in runs.call_args_list], read


if __name__ == "__main__":
    unittest.main()
