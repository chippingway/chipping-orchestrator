# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Authenticated pinned-state comment model, parser, and client mixin.

The mixin writes the record two ways. `write_pinned_state` lands a state
wherever it can -- in place, or as a new comment where none is named or the
named one is gone -- which every caller writing the whole record relies on.
`edit_pinned_state` is the strict one a guarded commit lands through: in
place or not at all, over the reading it was derived from, with an answer
that says whether GitHub confirmed it.

A state read from the comment, or written over it, also remembers what the
comment carried at that moment (`PinnedState.synced`), so what a tick staged on
it since can be told from what it read.
"""
from __future__ import annotations

import enum
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


class PinnedEdit(enum.Enum):
    """What a strict rewrite of the pinned comment came to.

    Only EDITED says the comment now carries the body sent, and only
    UNCONFIRMED says a request went out that may or may not have landed:
    GitHub's comment edit is a whole-body PATCH with no condition on what it
    replaces, so a response that never came back, or came back carrying
    another body, leaves the record reading either way. The other three were
    answered before anything was sent, so the comment is exactly as it was.
    """

    EDITED = "edited"
    # The thread could not be walked to the comment.
    UNREAD = "unread"
    # No comment carries the id, or the one that does is no longer an
    # authenticated, state-only comment.
    MISSING = "missing"
    # The comment no longer reads as the payload the rewrite was derived over,
    # or no longer parses at all.
    MOVED = "moved"
    UNCONFIRMED = "unconfirmed"


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

    ``synced`` is what the comment carried the last time this state was read
    from it or written over it, spelled as its JSON spells it so nothing
    staged on ``state_data`` moves it, and None for a state built in memory. It is not a field of the record and
    takes no part in comparing two states: it is what a guarded commit is
    captured over, so the changes a tick staged between two writes ride the
    next one while every field another writer moved meanwhile is kept as that
    writer left it.

    ``withheld`` is set on a state a guarded commit taken through
    `workflow/engine/report_commits.py` did not land over -- the developer
    report's, a validating reviewer round's, a change request's handoff and
    its recovery's, or an approval tail's -- one refused over a comment that
    moved, or one sent and never confirmed -- on one whose report post or
    re-read left its transaction owed over a comment another road wrote
    meanwhile, and on an approval tail's whose records the comment moved: the
    comment is not, or may not be, what the state
    was decided on, so the whole-state writer writes nothing for it rather
    than put back everything another road wrote since. Any such commit that
    lands clears it.
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
        self.synced = None
        self.withheld = False

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

    def reads_as(self, state_data: dict) -> bool:
        """Whether this reading parsed into exactly `state_data`, as the comment's JSON spells both.

        Spelled rather than compared as Python values, which call `true`
        equal to `1` and `1.0` equal to `1` at any depth: each of those is a
        different record to the reader that decides on it.
        """
        spelled = json.dumps(self.state_data, sort_keys=True)
        return self.parsed and spelled == json.dumps(state_data, sort_keys=True)

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
    reading = PinnedState(
        comment_id=issue_comment.id,
        state_data=payload,
    )
    reading.synced = json.dumps(payload, sort_keys=True)
    return reading


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
        """Create or replace the issue's authoritative state-only comment.

        A `withheld` state is not written at all, and is answered unchanged.
        """
        if state.withheld:
            log.warning(
                "issue=#%s holds a state a guarded commit did not land over; "
                "writing nothing over the pinned comment", issue.number,
            )
            return state
        body = pinned_state_body(state.data)
        if state.comment_id is None:
            created_comment = issue.create_comment(body)
            state.comment_id = created_comment.id
            state.synced = json.dumps(state.data, sort_keys=True)
            return state
        for issue_comment in issue.get_comments():
            if issue_comment.id == state.comment_id:
                issue_comment.edit(body)
                state.synced = json.dumps(state.data, sort_keys=True)
                return state
        created_comment = issue.create_comment(body)
        state.comment_id = created_comment.id
        state.synced = json.dumps(state.data, sort_keys=True)
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
        nowhere. It never posts: a comment that is gone, or that is no longer
        the authenticated state-only comment it was, is answered MISSING
        rather than recreated -- a record recreated from a derivation is one
        nobody read, pinned beside whatever replaced the comment it was
        derived from. The walk that finds the comment is also the last reading before
        the edit, so a comment another writer moved since `over` was read --
        compared as the comment's JSON spells it, where `null` is not an
        absent field and `true` is not `1` -- is answered MOVED and left as it
        stands.

        The two requests are the primitives below, so the in-memory double
        answers through this same policy over its own records.
        """
        try:
            located = self._pinned_comment(issue, state.comment_id)
        except Exception:
            log.exception(
                "issue=#%s could not read its pinned comment to rewrite it",
                issue.number,
            )
            return PinnedEdit.UNREAD
        if located is None:
            return PinnedEdit.MISSING
        target, reading = located
        if not reading.reads_as(over):
            return PinnedEdit.MOVED
        body = pinned_state_body(state.data)
        try:
            answered = self._send_pinned_edit(target, body)
        except Exception:
            log.exception(
                "issue=#%s its pinned comment rewrite went unanswered, so it "
                "may or may not have landed",
                issue.number,
            )
            answered = None
        if answered == body:
            return PinnedEdit.EDITED
        return PinnedEdit.UNCONFIRMED

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

    def _pinned_comment(
        self, issue: Issue, comment_id: int | None,
    ) -> tuple[IssueComment, PinnedState] | None:
        """The comment carrying `comment_id` and what it reads as, or None.

        None as well where that comment is no longer what `read_pinned_state`
        would take as the record -- a body edited into prose, or an author the
        read does not trust -- since a rewrite of it would be the record of
        nobody's reading.
        """
        trusted_login = getattr(self, "_bot_login", None)
        for issue_comment in issue.get_comments():
            if issue_comment.id != comment_id:
                continue
            reading = pinned_state_from_comment(
                issue_comment,
                trusted_login=trusted_login,
                issue_number=issue.number,
            )
            return None if reading is None else (issue_comment, reading)
        return None

    def _send_pinned_edit(self, issue_comment: IssueComment, body: str) -> str:
        """Send one edit and hand back the body GitHub answered it with.

        PyGithub refreshes the comment from the response, so what it carries
        afterwards is what GitHub says it stored.
        """
        issue_comment.edit(body)
        return issue_comment.body
