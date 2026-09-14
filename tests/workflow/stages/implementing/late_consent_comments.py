# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Human replies, visible pinned records, and notice counts on a consent thread."""
from __future__ import annotations

from orchestrator.github.pinned_state import (
    PinnedState,
    pinned_state_body,
)
from tests.support.fakes import FakeComment, FakeUser
from tests.workflow.stages.implementing import (
    late_consent_payloads as _consent_payloads,
)


class _ConsentComments:
    """Human replies, visible pinned records, and notice counts on a consent thread."""

    def _reply(self, body: str, author: str = _consent_payloads.TRUSTED_AUTHOR) -> int:
        """Add one comment past the consumed watermark, and say which it is."""
        identified = self.github.next_reply_id(self.issue)
        self.issue.comments.append(FakeComment(
            identified, body, user=FakeUser(author),
        ))
        return identified

    def _pin_the_record(self) -> int:
        """Put the pinned comment itself on the thread, rendered as it is written.

        The double keeps the record in a dict and puts no comment on the
        thread for it, so nothing that READS a thread can see the one comment
        every issue really carries. What a case here turns on is that body's
        contents, so it is produced by the production renderer rather than
        spelled out: a record whose escaped form would not fit is written as
        its own payload, and every receipt in it lands on the thread as the
        literal string it is.
        """
        state = self._state()
        self.issue.comments.append(FakeComment(
            state.comment_id,
            pinned_state_body(state.data),
            user=FakeUser(self.github._bot_login),
        ))
        return state.comment_id

    def _said(self) -> int:
        """How many sentences of ours this thread carries."""
        return len(self.github.posted_comments)

    def _state(self) -> PinnedState:
        return self.github.read_pinned_state(self.issue)
