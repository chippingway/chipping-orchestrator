# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Issue, pinned-state, and event services for the fake GitHub client."""
from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from orchestrator.config import settings as config
from orchestrator.github import events as _events
from orchestrator.github.comments import carries_own_marker
from orchestrator.github.pinned_state import PINNED_STATE_MARKER, PinnedState
from orchestrator.observability.analytics.recording import events as _recording_events
from orchestrator.workflow import (
    label_reading as _label_reading,
    state as _workflow_state,
    transition_guard as _transition_guard,
)
from tests.support.github.model_helpers import _has_closed_sweep_label
from tests.support.github.models import (
    FakeComment,
    FakeIssue,
    FakeLabel,
    FakeUser,
)
from tests.support.github.state import _CommentHistory, _LabelHistory

_STATE_CLOSED = "closed"


def _workflow_label(
    owner_or_issue,
    issue: FakeIssue | None = None,
) -> _workflow_state.WorkflowLabel | None:
    target_issue = issue or owner_or_issue
    return _label_reading.issue_workflow_label(label.name for label in target_issue.labels)


def _set_workflow_label(
    client,
    issue: FakeIssue,
    new_label: str | None,
    *,
    guarded: bool = True,
) -> None:
    resolved_label = _label_reading.coerce_workflow_label(new_label) if new_label else None
    if resolved_label is not None and guarded:
        _transition_guard.guard_transition(
            client.workflow_label(issue),
            resolved_label,
            config.WORKFLOW_TRANSITION_GUARD,
        )
    replaced = _label_reading.replaced_label_names(label.name for label in issue.labels)
    retained = [
        label for label in issue.labels if label.name not in replaced
    ]
    if resolved_label:
        retained.append(FakeLabel(resolved_label))
    if not client._stale_label_cache:
        issue.labels = retained
    client.label_history.append((issue.number, resolved_label))
    if resolved_label:
        client.emit_event(
            "stage_enter",
            issue_number=issue.number,
            stage=_workflow_state.stage_name(resolved_label),
        )
        _recording_events.record_stage_enter(
            repo=client._repo_slug,
            issue=issue.number,
            stage=_workflow_state.stage_name(resolved_label),
        )


class _IssueHistoryView:
    @property
    def posted_comments(self) -> _CommentHistory:
        return self._issue_history._posted_comments

    @property
    def label_history(self) -> _LabelHistory:
        return self._issue_history._label_history

    @property
    def created_child_issues(self) -> list[FakeIssue]:
        return self._issue_history._created_child_issues

    @property
    def write_state_calls(self) -> int:
        return self._issue_history._write_state_calls


class _EventHistoryView:
    @property
    def recorded_events(self) -> list[dict]:
        return self._event_history._recorded_events


class _IssueService:
    def add_issue(self, issue: FakeIssue) -> None:
        self._issues[issue.number] = issue

    def list_pollable_issues(self) -> Iterable[FakeIssue]:
        pollable: list[FakeIssue] = []
        seen: set[int] = set()
        self._pollable_calls += 1
        for issue in self._issues.values():
            if issue.closed:
                continue
            seen.add(issue.number)
            pollable.append(issue)
        every = config.CLOSED_ISSUE_SWEEP_EVERY_N_TICKS
        if every > 1 and (self._pollable_calls - 1) % every != 0:
            return pollable
        for issue in self._issues.values():
            if (
                issue.closed
                and issue.number not in seen
                and _has_closed_sweep_label(issue)
            ):
                seen.add(issue.number)
                pollable.append(issue)
        return pollable

    def get_issue(self, number: int) -> FakeIssue:
        return self._issues[int(number)]

    def create_child_issue(
        self,
        *,
        title: str,
        body: str,
        parent_number: int,
        labels: list[str],
    ) -> FakeIssue:
        validated = [_label_reading.coerce_workflow_label(label) for label in labels]
        trimmed_body = (body or "").rstrip()
        full_body = f"{trimmed_body}\n\nParent: #{parent_number}"
        child = FakeIssue(
            number=next(self._next_issue_number),
            title=title,
            body=full_body,
            labels=[FakeLabel(label) for label in validated],
            user=FakeUser(self._bot_login),
        )
        self._issues[child.number] = child
        self.created_child_issues.append(child)
        return child

    def find_issue_carrying(self, marker: str) -> FakeIssue | None:
        """The issue this client created carrying `marker`, in any state.

        Unscoped like the real one: the window this lookup exists for is a
        child nobody has attributed yet, and a human is free to close it or
        move its label in that window.
        """
        for candidate in self._issues.values():
            if carries_own_marker(
                [candidate], marker, bot_login=self._bot_login,
            ):
                return candidate
        return None


class _WorkflowStateService:
    workflow_label = _workflow_label
    set_workflow_label = _set_workflow_label

    def last_workflow_label_applied(
        self, issue: FakeIssue,
    ) -> _workflow_state.WorkflowLabel | None:
        """The workflow label most recently applied to this issue.

        The double's ORDERED history is the timeline the real client walks:
        each entry is a `labeled` event GitHub recorded, oldest first, so the
        newest match wins. A write that CLEARS the label is skipped, since an
        issue put in no state was not put in one. An issue seeded wearing a
        label was given it before the history begins, which is what answers
        for a thread nothing has written to yet.

        A case that needs the read to establish nothing patches the method:
        the caller cannot tell a walk that failed from one that found no
        application, and treats both the same way.
        """
        for number, written in reversed(self.label_history):
            if number == issue.number and written is not None:
                return written
        return _workflow_label(self, issue)

    def apply_foreign_label(self, issue: FakeIssue, new_label: str) -> None:
        """Put a workflow label on an issue as somebody OTHER than the bot.

        The one distinction the history above is built to draw, so the double
        has to be able to express it: a collaborator is free to apply and
        remove the same names by hand, and GitHub attributes those events to
        them. The label lands on the issue and no application of THIS
        orchestrator's is recorded, which is exactly what the real client's
        actor filter walks past.
        """
        resolved_label = _label_reading.coerce_workflow_label(new_label)
        replaced = _label_reading.replaced_label_names(label.name for label in issue.labels)
        issue.labels = [
            label for label in issue.labels if label.name not in replaced
        ]
        issue.labels.append(FakeLabel(resolved_label))

    def seed_state(
        self, issue: FakeIssue | int, **state_data: Any,
    ) -> None:
        """Put a pinned record on this issue, numbered above its own thread.

        The thread is named rather than only its number, because the record's
        id has to clear whatever that thread already carries. A case may
        hand-number comments on an issue it never registered here, and a
        record sharing an id with one of them is a comment `comments_after`
        hides as the pinned record -- so the reply a case seeded is a reply no
        reading ever returns.

        A number still works and resolves through the register, which is what
        every issue this client was given is in.
        """
        thread = issue if isinstance(issue, FakeIssue) else self._issues.get(issue)
        number = issue.number if isinstance(issue, FakeIssue) else issue
        self._pinned[number] = PinnedState(
            comment_id=self._next_comment_id(thread),
            data=dict(state_data),
        )

    def emit_event(
        self,
        event: str,
        *,
        issue_number: int,
        stage: str | None = None,
        **extras: Any,
    ) -> None:
        record = _events.build_event_record(
            repo=self._repo_slug,
            issue_number=issue_number,
            event=event,
            stage=stage,
            **extras,
        )
        self.recorded_events.append(record)
        _events.write_event_record(record)

    def read_pinned_state(self, issue: FakeIssue) -> PinnedState:
        existing = self._pinned.get(issue.number)
        if existing is None:
            return PinnedState()
        return PinnedState(
            comment_id=existing.comment_id,
            data=dict(existing.data),
        )

    def write_pinned_state(
        self,
        issue: FakeIssue,
        state: PinnedState,
    ) -> PinnedState:
        self._issue_history._write_state_calls += 1
        if state.comment_id is None:
            state.comment_id = self._next_comment_id(issue)
            issue.comments.append(FakeComment(
                id=state.comment_id,
                body=f"{PINNED_STATE_MARKER} ... -->",
            ))
        self._pinned[issue.number] = PinnedState(
            comment_id=state.comment_id,
            data=dict(state.data),
        )
        return state

    def pinned_data(self, issue_number: int) -> dict[str, Any]:
        pinned_state = self._pinned.get(issue_number)
        if pinned_state is None:
            return {}
        return dict(pinned_state.data)


class _IssueCommentService:
    def comment(self, issue: FakeIssue, body: str) -> FakeComment:
        # Authored as the client's own login, like the real one: a receipt the
        # orchestrator reads back off a thread is recognized by its author as
        # well as by its marker.
        new_comment = FakeComment(
            id=self._next_comment_id(issue),
            body=body,
            user=FakeUser(self._bot_login),
        )
        issue.comments.append(new_comment)
        self.posted_comments.append((issue.number, body))
        return new_comment

    def next_reply_id(self, issue: FakeIssue) -> int:
        """Mint the id a comment appended to this thread now would carry.

        For a case that seeds a human reply AFTER a tick has already posted
        something. Ids ascend across the thread, so a hand-picked one can
        collide with a comment the orchestrator has since written -- and a
        reply sharing an id with the watermark is one no reader ever sees.

        Through the one allocator every comment on this client comes out of,
        because a seeded reply is a comment on a shared ascending id space
        like any other. Numbered off its own thread instead it repeats an id
        another thread was already given, and leaves the client's counter
        behind it -- so the next id MINTED anywhere, a pinned record's
        included, is handed out below a reply that is already on a thread.

        The thread is handed over because a case may seed a reply onto an
        issue this client was never given.
        """
        return self._next_comment_id(issue)

    def comments_after(
        self,
        issue: FakeIssue,
        after_id: int | None,
        *,
        state_comment_id: int | None = None,
    ) -> list[FakeComment]:
        return [
            comment
            for comment in issue.comments
            if not self._is_state_comment(comment, state_comment_id)
            and (after_id is None or comment.id > after_id)
        ]

    def latest_comment_id(self, issue: FakeIssue) -> int | None:
        return max(
            (comment.id for comment in issue.comments),
            default=None,
        )

    def _is_state_comment(
        self, comment: FakeComment, state_comment_id: int | None,
    ) -> bool:
        """Whether this is the pinned comment, by identity or by marker."""
        if state_comment_id is None:
            return PINNED_STATE_MARKER in (comment.body or "")
        return comment.id == state_comment_id
