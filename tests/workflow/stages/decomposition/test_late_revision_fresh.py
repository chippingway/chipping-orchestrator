# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""A late revision's developer spawned fresh, quoted the conversation its reading was cut from.

A revision resumes the locked developer session, whose transcript already
holds the thread; one with no session pinned, or one whose session a
poisoned transcript forces it to replace, is spawned fresh instead and
re-grounded with the conversation. That conversation is the one the guidance
was read off, never a second read of the thread at the spawn: a reply
landing in between would reach the developer while the capture its report is
held on stays frozen over requirements that do not count it. Here a reply
lands as the revision's notice goes out, or as a poisoned resume fails, and
each case reads what the fresh spawn was handed and what became of the
reply.
"""
from __future__ import annotations

from unittest.mock import patch

from tests.workflow.stages.decomposition import (
    captured_revision_support as _captured,
    late_content_replies as _replies,
    late_content_support as _support,
    late_revision_support as _stage_support,
)
from tests.workflow.stages.decomposition.late_requirements_support import requirements
from tests.workflow.stages.decomposition.late_run_support import agent_reply
from tests.workflow.stages.decomposition.late_test_support import GENERATION_NUMBER

# A reply a human writes once the revision has read the guidance it quotes.
_ARRIVED = "Use a brand new storage engine for the importer."

# What a resume of a session the CLI's backend lost fails with, and what
# every fresh spawn's preamble opens with.
_STALE = "Error: No conversation found with session ID: dev-sess\n"
_FRESH = "resuming work on GitHub issue"

# The notice a revision posts right before the developer is started.
_REVISING = "resuming the developer against your guidance"


class FreshRevisionTest(_captured.CapturedRevisionCase):
    """A fresh or replacement spawn is re-grounded with the reading its guidance came off, and nothing newer."""

    def test_a_fresh_spawn_quotes_only_its_reading(self) -> None:
        # No session is pinned, so the revision is spawned fresh, and a reply
        # lands as its notice goes out: the spawn is handed the guidance and
        # the conversation it was read off, never that reply, and the capture
        # is frozen over exactly those requirements. Released with the reply
        # still standing, the recovery retires the capture as answering
        # requirements that moved, leaving the reply unread for a revision of
        # its own.
        self._seed_drifted()
        self._hand_edit(**{_stage_support.DEV_SESSION_ID: None})
        handed = requirements(self.issue)
        noticed = _RepliedAsNoticed(self)

        with patch.object(self.github, "comment", noticed):
            _, spawn = self._held()

        self._handed_only_the_reading(spawn.call_args.args[1])
        self.assertEqual(_captured.capture_of(self._pinned()).handoff.requirements_revision, handed)
        self._released()
        self._dispatched().assert_not_called()
        retired = self._pinned()
        self.assertEqual(
            (_captured.capture_of(retired).stage, retired[_support.KEY_GENERATION], self._developer_runs()),
            (_captured.RETIRED, GENERATION_NUMBER, 1),
        )
        self.assertLess(retired.get(_support.KEY_COMMENT_WATERMARK) or 0, noticed.arrived.id)

    def test_a_replacement_quotes_only_its_reading(self) -> None:
        # The pinned session's resume fails as one the CLI's backend lost,
        # and a reply lands as it fails: the session is replaced by a fresh
        # spawn, handed the guidance and the conversation it was read off,
        # never that reply, which the reconciled revision leaves unread.
        self._seed_drifted()
        poisoned = _PoisonedAsReplied(self)

        _, spawn = self._revise(reply=poisoned)

        self.assertEqual(spawn.call_count, 2)
        self._handed_only_the_reading(spawn.call_args.args[1])
        handed = self._pinned()
        self.assertEqual(handed[_support.KEY_COMMENT_WATERMARK], self.guidance.id)
        self.assertLess(handed[_support.KEY_COMMENT_WATERMARK], poisoned.arrived.id)

    def _handed_only_the_reading(self, prompt: str) -> None:
        """Assert `prompt` is a fresh spawn's, quoting the guidance it was read with and not the reply landed since."""
        self.assertIn(_FRESH, prompt)
        self.assertIn(self.guidance.body, prompt)
        self.assertNotIn(_ARRIVED, prompt)


class _RepliedAsNoticed:
    """The thread's comment post, a human replying right behind the revision's notice."""

    def __init__(self, case: _captured.CapturedRevisionCase) -> None:
        self._case = case
        self._posts = case.github.comment
        self.arrived = None

    def __call__(self, issue, body: str):
        """Post `body`, then land the reply behind it if it is the revision's notice."""
        sent = self._posts(issue, body)
        if _REVISING in body:
            self.arrived = _replies.reply(self._case.issue, _ARRIVED)
        return sent


class _PoisonedAsReplied:
    """A resume failing as a session the backend lost, a human replying as it fails; the replacement's report."""

    def __init__(self, case: _captured.CapturedRevisionCase) -> None:
        self._case = case
        self.arrived = None

    def __call__(self, *_asked, **_answering):
        """Fail the first attempt with a reply landed behind it; answer the replacement on its report."""
        if self.arrived is None:
            self.arrived = _replies.reply(self._case.issue, _ARRIVED)
            return agent_reply("", exit_code=1, stderr=_STALE)
        return agent_reply(_captured.DEV_REPORT)
