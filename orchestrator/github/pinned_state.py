# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Authenticated pinned-state comment model, parser, and client mixin."""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any

from github.Issue import Issue
from github.IssueComment import IssueComment

from orchestrator.github.issue_polling import GitHubIssuePollingMixin

log = logging.getLogger("orchestrator.github")

PINNED_STATE_MARKER = "<!--orchestrator-state"
PINNED_STATE_RE = re.compile(
    r"<!--orchestrator-state\s+(\{.*?\})\s*-->",
    re.DOTALL,
)
# What a body has to be for the comment carrying it to be the pinned state:
# the marker and nothing else, anchored at both ends, so an ordinary
# bot-authored comment that merely embeds the marker is not mistaken for state.
#
# The payload alternates for a reason. The object form is matched first and
# spans anything, because a recorded field can legitimately contain `-->` --
# a preserved pull-request body does -- and that is a live payload this has
# always read back. Everything else is matched by a form that may not cross a
# `-->`, since without that guard a forged marker followed by the ordinary
# comment marker would backtrack onto the trailing `-->` and be adopted as the
# state comment. What the second form buys is that `[]`, `7`, or `null` from
# the bot is IDENTIFIED as a corrupted state comment rather than passed over
# as no state at all -- the parser then refuses it, and a caller that would
# have read the miss as "this issue recorded nothing" is told otherwise.
PINNED_STATE_BODY_RE = re.compile(
    r"\A\s*<!--orchestrator-state\s+(\{.*?\}|(?:(?!-->).)*?)\s*-->\s*\Z",
    re.DOTALL,
)
PINNED_STATE_TEMPLATE = "<!--orchestrator-state {payload}-->"

# What ends the comment the payload is wrapped in, and what it is written as
# inside that payload. The replacement is the JSON escape for `>`, so a reader
# decodes it back to the terminator it stands for without knowing anything
# about this: what is escaped is the SERIALIZED form, never the value. It can
# introduce no terminator of its own, since it carries no `>` at all.
_COMMENT_CLOSE = "-->"

_ESCAPED_COMMENT_CLOSE = r"--\u003e"

# How long a comment body GitHub accepts. A write past it is refused, so a
# caller about to add something large to the pinned state -- a preserved pull
# request body, a recorded child manifest -- asks `pinned_state_body` what the
# comment would become and measures it against this rather than finding out
# from a failed request after the work it was recording has been paid for.
MAX_PINNED_BODY = 65536

_MISSING_STATE = object()


@dataclass(init=False)
class PinnedState:
    """Pinned comment identity and mutable workflow state payload.

    ``state_data`` is the descriptive constructor keyword. The custom adapter
    retains the historical ``data=`` keyword and the ``.data`` instance
    attribute used throughout the workflow.

    ``parsed`` is whether the payload this carries came out of the comment or
    stood in for one that would not parse. It is a field of its own because
    the substitute is indistinguishable from the real thing: a corrupted
    pinned comment reads back as ``{}``, which is exactly what an issue the
    orchestrator has not recorded anything for reads back as. A caller
    rewriting the comment wants that -- an empty payload is what it is about
    to replace -- but a caller DECIDING on the absence of a recorded branch or
    pull request would be deciding on a record it never read.
    """

    comment_id: int | None = None
    state_data: dict = field(default_factory=dict)
    parsed: bool = True

    def __init__(
        self,
        comment_id: int | None = None,
        state_data: Any = _MISSING_STATE,
        *,
        parsed: bool = True,
        **legacy_fields: Any,
    ) -> None:
        legacy_state = legacy_fields.pop("data", _MISSING_STATE)
        if legacy_fields:
            unexpected_name = next(iter(legacy_fields))
            raise TypeError(
                "PinnedState() got an unexpected keyword argument "
                f"{unexpected_name!r}",
            )
        if state_data is not _MISSING_STATE and legacy_state is not _MISSING_STATE:
            raise TypeError("PinnedState() got multiple values for state data")
        selected_state = legacy_state if state_data is _MISSING_STATE else state_data
        if selected_state is _MISSING_STATE:
            selected_state = {}
        self.comment_id = comment_id
        self.state_data = selected_state
        self.parsed = parsed

    def __getattr__(self, attribute_name: str) -> Any:
        if attribute_name == "data":
            return self.state_data
        raise AttributeError(attribute_name)

    def __setattr__(self, attribute_name: str, attribute_value: Any) -> None:
        target_name = "state_data" if attribute_name == "data" else attribute_name
        object.__setattr__(self, target_name, attribute_value)

    def carries(self, key: str) -> bool:
        """Whether this comment has the field at all, whatever it holds.

        Presence rather than value, and the two are different questions. A
        reader deciding what a field MEANS reads it fail-closed, so a value
        nothing can act on comes back as an absence -- which is right there
        and wrong for a reader asking whether the record CLAIMS something. An
        issue that never wrote a field and one whose field a hand edit
        truncated are the same absence to the first reader and opposite
        answers to the second.

        The payload is JSON, so a field can be present and `null`: an older
        binary writing a value this one reads as nothing, or a hand edit.
        Asked as a value that would read as absent, which is why the key is
        what this looks for.
        """
        return key in self.state_data

    def get(self, key: str, default: Any = None) -> Any:
        """Return a workflow-state field or its default."""
        return self.state_data.get(key, default)

    def set(self, key: str, state_value: Any) -> None:
        """Set one workflow-state field."""
        self.state_data[key] = state_value


def _is_state_comment(
    issue_comment: IssueComment, state_comment_id: int | None,
) -> bool:
    """Whether this comment is the pinned one, by identity or by marker.

    Identity where the caller can name it. The marker is the stand-in for a
    caller that cannot, and it answers a wider question than it looks: every
    comment that merely QUOTES the marker reads as the state comment too.
    """
    if state_comment_id is None:
        return PINNED_STATE_MARKER in (issue_comment.body or "")
    return issue_comment.id == state_comment_id


def pinned_state_body(state_data: dict) -> str:
    """Return the comment body one pinned state is written as.

    The one rendering of it, so a caller measuring what a write would produce
    measures the write rather than an approximation of it.

    The payload is wrapped in an HTML comment, so a value carrying that
    comment's terminator would close it early and leave everything after it --
    the rest of the record, whatever a stage happens to have written -- as
    visible issue text. Values are not this owner's to sanitize: an agent's
    explanation, a preserved pull-request body, a human's own words all reach
    here as somebody wrote them. So the terminator is escaped in the SERIALIZED
    form and nowhere else, as the JSON escape for its last character, which
    every reader decodes back to exactly what was stored. Nothing else about
    the payload changes, and a body written before this reads back the same.

    That escape is five characters an occurrence, and a record already on an
    issue never paid them. One accepted at the ceiling with terminators in it
    -- a preserved pull-request body is where they come by the thousand --
    escapes into a comment GitHub refuses, and the write that would carry it
    is the write a stage's park, its notice, or its recorded outcome rides out
    on. Losing those to a rendering is the worse trade of the two: the record
    is what a later tick reads, while the escape only decides how the comment
    LOOKS. So a payload the escape puts past the limit is written exactly as
    it was stored, which is the rendering the binary that accepted it gave it,
    and which every reader here still parses -- the object form spans the
    terminator on the way back.
    """
    payload = json.dumps(state_data, sort_keys=True)
    escaped = PINNED_STATE_TEMPLATE.format(
        payload=payload.replace(_COMMENT_CLOSE, _ESCAPED_COMMENT_CLOSE),
    )
    if len(escaped) <= MAX_PINNED_BODY:
        return escaped
    return PINNED_STATE_TEMPLATE.format(payload=payload)


def pinned_state_from_comment(
    issue_comment: IssueComment,
    *,
    trusted_login: str | None,
    issue_number: int,
) -> PinnedState | None:
    """Parse one authenticated, state-only pinned comment candidate.

    A payload that is not a workflow state -- one that will not parse, and one
    that parses into an array, a string, a number, or `null` -- still resolves
    to the comment carrying it, with an empty state and `parsed` withheld. The
    comment id is what lets the next write overwrite the corruption in place
    rather than leave a second pinned comment beside it; the flag is what
    keeps a reader from spending that empty payload as a record of an issue
    with nothing pinned.
    """
    body = issue_comment.body or ""
    if PINNED_STATE_MARKER not in body:
        return None
    author_login = getattr(
        getattr(issue_comment, "user", None),
        "login",
        None,
    )
    if trusted_login is not None and author_login != trusted_login:
        return None
    state_match = PINNED_STATE_BODY_RE.match(body)
    if state_match is None:
        return None
    payload = _state_payload(state_match.group(1), issue_number)
    if payload is None:
        return PinnedState(comment_id=issue_comment.id, parsed=False)
    return PinnedState(
        comment_id=issue_comment.id,
        state_data=payload,
    )


def _state_payload(payload: str, issue_number: int) -> dict | None:
    """The workflow state one pinned payload carries, or None if it carries none.

    Two ways to carry none, answered the same: JSON that does not parse, and
    JSON that parses into something no state can be read out of. An array, a
    string, a number, and `null` are all valid JSON the bot could have written
    -- a truncated write, a hand-edited comment -- and none of them has the
    `get` every reader of a state calls. Handing one back would move the
    failure from here, where it can be reported, to whichever reader touched
    it first.
    """
    try:
        parsed_state = json.loads(payload)
    except json.JSONDecodeError:
        log.warning("issue=#%s pinned state JSON unparseable", issue_number)
        return None
    if isinstance(parsed_state, dict):
        return parsed_state
    log.warning(
        "issue=#%s pinned state is a %s rather than an object",
        issue_number, type(parsed_state).__name__,
    )
    return None


class GitHubStateMixin(GitHubIssuePollingMixin):
    """Durable pinned-state reads/writes and issue comment scans."""

    def read_pinned_state(self, issue: Issue) -> PinnedState:
        """Return the first authenticated, state-only pinned comment."""
        trusted_login = getattr(self, "_bot_login", None)
        for issue_comment in issue.get_comments():
            pinned_state = pinned_state_from_comment(
                issue_comment,
                trusted_login=trusted_login,
                issue_number=issue.number,
            )
            if pinned_state is not None:
                return pinned_state
        return PinnedState()

    def write_pinned_state(
        self,
        issue: Issue,
        state: PinnedState,
    ) -> PinnedState:
        """Create or replace the issue's authoritative state-only comment."""
        body = pinned_state_body(state.data)
        if state.comment_id is None:
            created_comment = issue.create_comment(body)
            state.comment_id = created_comment.id
            return state
        for issue_comment in issue.get_comments():
            if issue_comment.id == state.comment_id:
                issue_comment.edit(body)
                return state
        created_comment = issue.create_comment(body)
        state.comment_id = created_comment.id
        return state

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
        return [
            issue_comment
            for issue_comment in read
            if not _is_state_comment(issue_comment, state_comment_id)
            and (after_id is None or issue_comment.id > after_id)
        ]

    def latest_comment_id(self, issue: Issue) -> int | None:
        """Return the largest issue-comment id, when any comment exists."""
        latest_id: int | None = None
        for issue_comment in issue.get_comments():
            if latest_id is None or issue_comment.id > latest_id:
                latest_id = issue_comment.id
        return latest_id
