# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""GitHub comment reads, writes, and watermarks for pinned state.

Both writers use the pinned-state parser on the same thread traversal that
locates the target comment. The whole-state writer can create a pin. The
strict editor requires the authoritative comment to match the caller's
reading and reports whether GitHub confirmed the edit.
"""
from __future__ import annotations

import json
import logging

from github.Issue import Issue
from github.IssueComment import IssueComment

from orchestrator.github import edit_questions as _edit_questions, pinned_refusal as _pinned_refusal
from orchestrator.github.issue_polling import GitHubIssuePollingMixin
from orchestrator.github.pinned_state import (
    PINNED_STATE_MARKER,
    SCHEMA_VERSION_KEY,
    SUPPORTED_SCHEMA_VERSION,
    PinnedAdmission,
    PinnedEdit,
    PinnedState,
    pinned_state_body,
    pinned_state_from_comment,
)

log = logging.getLogger("orchestrator.github")


class GitHubStateMixin(GitHubIssuePollingMixin):
    """Durable pinned-state reads/writes and issue comment scans."""

    def read_pinned_state(self, issue: Issue) -> PinnedState:
        """Return the first authenticated, state-only pinned comment."""
        trusted_login = getattr(self, "_bot_login", None)
        repo = getattr(issue, "repository", None)
        repo_slug = getattr(repo, "full_name", None) or getattr(self, "_repo_slug", None)
        for issue_comment in issue.get_comments():
            reading = pinned_state_from_comment(
                issue_comment,
                trusted_login=trusted_login,
                issue_number=issue.number,
                repo_slug=repo_slug,
            )
            if reading is not None:
                return reading
        return PinnedState(issue_number=issue.number, repo_slug=repo_slug)

    def write_pinned_state(
        self,
        issue: Issue,
        state: PinnedState,
    ) -> PinnedState:
        """Create or replace the issue's authoritative state-only comment.

        A `withheld` state is not written at all, and is answered unchanged.
        So is every state written by a client that does not know whose token
        it holds: it can authenticate no comment, so it could not tell a
        refused record from none and would post a pin beside one. A state the
        walk below finds a record refused admission for -- the comment the
        caller's id names, or one ahead of it, or one anywhere where that id
        names no state comment -- is not written either, and that refusal
        RAISES (`pinned_refusal.RecordRefused`) rather than answering: neither
        writer may overwrite that comment, create a replacement beside it, or
        silently stamp it as current, and a caller answered quietly would go
        on to whatever the write was for over a record nobody can read -- one
        a human's edit since the caller's reading is enough to leave. A state
        carrying no version is stamped with the supported one, and a state the
        next reading would refuse -- another version, a value JSON cannot
        spell, nesting past the recursion limit -- is not written either.

        The named comment is rewritten only where that same walk admitted it;
        one that is gone or no longer state is replaced by a new comment, as
        an issue with nothing pinned is given its first.
        """
        if state.withheld:
            log.warning(
                "issue=#%s holds a state a guarded commit did not land over; "
                "writing nothing over the pinned comment", issue.number,
            )
            return state
        if getattr(self, "_bot_login", None) is None:
            log.warning(
                "issue=#%s has no trusted account to authenticate its pinned comment by; "
                "writing nothing", issue.number,
            )
            return state
        located = self._pinned_comment(issue, state.comment_id)
        if located is not None and not located[1].supported:
            refused = located[1]
            log.warning(
                "repo=%s issue=#%s holds %s pinned comment #%s (%s); writing nothing",
                refused.repo_slug, issue.number, refused.admission_status.value,
                refused.comment_id, refused.refusal_reason,
            )
            raise _pinned_refusal.RecordRefused(f"issue #{issue.number} holds a pinned comment admission refuses")
        state.state_data.setdefault(SCHEMA_VERSION_KEY, SUPPORTED_SCHEMA_VERSION)
        refusal = PinnedAdmission.payload_refusal(state.state_data)
        if refusal is not None:
            log.warning("issue=#%s state to pin is refused (%s); writing nothing", issue.number, refusal)
            return state
        body = pinned_state_body(state.state_data)
        if located is None:
            state.comment_id = issue.create_comment(body).id
        else:
            located[0].edit(body)
        state.synced = json.dumps(state.state_data, sort_keys=True)
        return state

    def edit_pinned_state(
        self,
        issue: Issue,
        state: PinnedState,
        *,
        over: dict,
    ) -> PinnedEdit:
        """Rewrite the pinned comment `state` names in place, and only over `over`.

        The strict counterpart of `write_pinned_state`, for a caller that
        derived `state` from a reading and has to land on that reading or
        nowhere. It never posts: a comment that is gone, that is no longer
        the authenticated state-only comment it was, or that a supported
        record ahead of it on the thread has displaced as the one every reader
        takes, is answered MISSING rather than recreated or edited where no
        reader would see it. The walk that finds the comment is also the
        last reading before the edit, so a comment another writer moved since
        `over` was read -- compared as the comment's JSON spells it, where
        `null` is not an absent field and `true` is not `1` -- is answered
        MOVED and left as it stands. Behind that walk, and immediately before
        the edit, a caller's question is asked (`edit_questions`): an answer
        that the edit no longer stands is HELD, with nothing sent.

        Nothing is sent over a record refused admission -- answered
        UNSUPPORTED, or MOVED where it will not parse at all -- nor for a state
        the next reading would refuse, another version, a value JSON cannot
        spell, or nesting past the recursion limit, answered UNSUPPORTED. A
        state carrying no version is stamped with the supported one. A client
        that does not know whose token it holds authenticates no comment, so
        its walk finds none and it answers MISSING.

        The two requests are the primitives below, so the in-memory double
        answers through this same policy over its own records.
        """
        state.state_data.setdefault(SCHEMA_VERSION_KEY, SUPPORTED_SCHEMA_VERSION)
        if PinnedAdmission.payload_refusal(state.state_data) is not None:
            log.warning(
                "issue=#%s rewrite is refused (%s); sending nothing",
                issue.number, PinnedAdmission.payload_refusal(state.state_data),
            )
            return PinnedEdit.UNSUPPORTED
        try:
            located = self._pinned_comment(issue, state.comment_id, authoritative=True)
        except Exception:
            log.exception(
                "issue=#%s could not read its pinned comment to rewrite it",
                issue.number,
            )
            return PinnedEdit.UNREAD
        unsent = PinnedEdit.unsent(located and located[1], over)
        if unsent is None and not _edit_questions.stands(over, state.state_data):
            unsent = PinnedEdit.HELD
        if unsent is not None:
            return unsent
        body = pinned_state_body(state.state_data)
        try:
            answered = self._send_pinned_edit(located[0], body)
        except Exception:
            log.exception(
                "issue=#%s its pinned comment rewrite went unanswered, so it "
                "may or may not have landed",
                issue.number,
            )
            answered = None
        return PinnedEdit.EDITED if answered == body else PinnedEdit.UNCONFIRMED

    def comments_after(
        self,
        issue: Issue,
        after_id: int | None,
        *,
        state_comment_id: int | None = None,
        comments=None,
    ) -> list[IssueComment]:
        """Return non-state issue comments newer than the watermark.

        Which comment is the state one is answered by IDENTITY where the
        caller can name it, and by the marker in the body otherwise. The two
        are not the same question. The body test also hides every comment that
        merely quotes the marker -- an adjudicator explaining itself, a human
        pasting a payload back -- which is right for a reader looking for
        conversation and wrong for one looking for a receipt this orchestrator
        posted: a sentence carrying somebody else's copy of the marker would
        be invisible to the only read that could tell it had been said.

        `comments` is a read the caller already holds, cut in place of the
        thread's own. A caller deriving several answers from one batch -- the
        prompt, the watermarks that batch settles, the requirements it
        fingerprints -- has to take them off ONE read: a second read is newer
        than the first, so a comment landing between them reaches some of
        those answers and not the others.
        """
        read = issue.get_comments() if comments is None else comments
        if state_comment_id is None:
            conversation = [
                issue_comment for issue_comment in read
                if PINNED_STATE_MARKER not in (issue_comment.body or "")
            ]
        else:
            conversation = [issue_comment for issue_comment in read if issue_comment.id != state_comment_id]
        return [
            issue_comment
            for issue_comment in conversation
            if after_id is None or issue_comment.id > after_id
        ]

    def latest_comment_id(self, issue: Issue) -> int | None:
        """Return the largest issue-comment id, when any comment exists."""
        latest_id: int | None = None
        for issue_comment in issue.get_comments():
            if latest_id is None or issue_comment.id > latest_id:
                latest_id = issue_comment.id
        return latest_id

    def _pinned_comment(
        self, issue: Issue, comment_id: int | None, *, authoritative: bool = False,
    ) -> tuple[IssueComment, PinnedState] | None:
        """The comment a write naming `comment_id` answers to, and what it reads as, or None.

        Every comment the walk passes is admitted through the one owner, so
        the reading a writer decides on is the read it lands from: nothing a
        writer sends rests on an earlier walk of the thread. The named comment
        is answered where it is still what `read_pinned_state` would take as a
        record -- authored by the trusted account, nothing but the marker --
        whatever it was admitted as. An authenticated comment refused admission
        is answered in its place where it comes ahead of it, and wherever it is
        on a thread on which no id is named or the named comment is not state:
        a caller holding a stale id never reaches past a refused record, nor
        posts a replacement beside one. None is a thread carrying neither: the
        named comment gone, edited into prose, or by an author the read does
        not trust, since a rewrite of that would be the record of nobody's
        reading.

        `authoritative` is the strict edit's walk, which stops at the first
        record the read would take: a supported one ahead of the named comment
        answers None as well, since that comment is no longer the record any
        reader takes, and an edit landing there would be confirmed over a
        record nobody reads. The whole-state writer walks on past it.
        """
        trusted_login = getattr(self, "_bot_login", None)
        repo_name = getattr(getattr(issue, "repository", None), "full_name", None)
        repo_slug = repo_name or getattr(self, "_repo_slug", None)
        for issue_comment in issue.get_comments():
            reading = pinned_state_from_comment(
                issue_comment,
                trusted_login=trusted_login,
                issue_number=issue.number,
                repo_slug=repo_slug,
            )
            if reading is None:
                continue
            if issue_comment.id == comment_id or not reading.supported:
                return issue_comment, reading
            if authoritative:
                return None
        return None

    def _send_pinned_edit(self, issue_comment: IssueComment, body: str) -> str:
        """Send one edit and hand back the body GitHub answered it with.

        PyGithub refreshes the comment from the response, so what it carries
        afterwards is what GitHub says it stored.
        """
        issue_comment.edit(body)
        return issue_comment.body
