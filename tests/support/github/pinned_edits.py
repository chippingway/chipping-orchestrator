# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The strict pinned-state edit for the in-memory GitHub client.

The policy is the real client's, borrowed rather than copied: which comment a
rewrite may land on, that a vanished one is never recreated, that it lands only
over the reading it was derived from, and what an unanswered request is reported
as. What this supplies is the two requests that policy makes, answered from the
records the client pins -- and the ways GitHub leaves them unanswered, named per
issue on `pinned_failures`.
"""
from __future__ import annotations

import copy

from orchestrator.github.pinned_state import GitHubStateMixin, PinnedState, pinned_state_from_comment
from tests.support.github.models import FakeComment, FakeIssue, FakeUser
from tests.support.github.state import _FakePinnedFailures

# What an unanswered request raises. The real policy catches whatever a request
# raises, so the double need not spell PyGithub's exceptions to be answered alike.
_READ_REFUSED = "GitHub did not answer the pinned-comment read"
_EDIT_REFUSED = "GitHub refused the pinned-comment edit"
_RESPONSE_LOST = "the pinned-comment edit landed and its response was lost"


class _PinnedEditService:
    """Answer the strict edit's requests from the records this client pins."""

    edit_pinned_state = GitHubStateMixin.edit_pinned_state

    @property
    def pinned_failures(self) -> _FakePinnedFailures:
        """The issues whose pinned-comment requests go unanswered, by how."""
        return self._pinned_failures

    def _pinned_comment(
        self, issue: FakeIssue, comment_id: int | None,
    ) -> tuple[FakeIssue, PinnedState] | None:
        if issue.number in self.pinned_failures.unreadable:
            raise RuntimeError(_READ_REFUSED)
        pinned = self._pinned.get(issue.number)
        if pinned is None or pinned.comment_id != comment_id:
            return None
        return issue, PinnedState(
            comment_id=pinned.comment_id,
            data=copy.deepcopy(pinned.data),
            parsed=pinned.parsed,
        )

    def _send_pinned_edit(self, issue: FakeIssue, body: str) -> str:
        """Pin what `body` reads back as, counted as one more pinned-state write.

        Read back through the real parser, so the record holds what the next
        reading of the rendered comment would. A lost response lands the
        record and raises afterwards, which is the accepted write a caller
        has to settle from its own receipts rather than take as refused.
        """
        self._issue_history._write_state_calls += 1
        if issue.number in self.pinned_failures.refused:
            raise RuntimeError(_EDIT_REFUSED)
        self._pinned[issue.number] = pinned_state_from_comment(
            FakeComment(
                id=self._pinned[issue.number].comment_id,
                body=body,
                user=FakeUser(self._bot_login),
            ),
            trusted_login=self._bot_login,
            issue_number=issue.number,
        )
        if issue.number in self.pinned_failures.lost:
            raise RuntimeError(_RESPONSE_LOST)
        return body
