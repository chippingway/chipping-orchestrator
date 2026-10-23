# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Authenticated pinned-state comment model, schema admission parser, and client mixin.

Only version-1 records (JSON objects with integer `schema_version == 1`)
authored by the account backing the orchestrator token are admitted as
supported state. Authenticated comments with missing, non-integer, or
unsupported versions, malformed JSON, or non-object payloads are refused and
preserved unchanged on GitHub: neither writer may overwrite them, create
replacements beside them, or silently stamp them as current. Genuinely new pins
are stamped with schema_version: 1 on first write, and neither writer sends a
state the next reading would refuse. A client that does not know whose token
it holds authenticates no comment and writes none.

The mixin writes the record two ways. `write_pinned_state` lands a state
wherever it can -- in place, or as a new comment where none is named or the
named one is gone or no longer state -- which every caller writing the whole
record relies on. Both decide on one walk of the thread that admits every
comment it passes and is the read they land from (`_pinned_comment`).
`edit_pinned_state` is the strict one a guarded commit lands through: in
place or not at all, over the reading it was derived from, with an answer
that says whether GitHub confirmed it. Strict edits remain non-creating.

A state read from the comment, or written over it, also remembers what the
comment carried at that moment (`PinnedState.synced`), so what a tick staged on
it since can be told from what it read.
"""
from __future__ import annotations

import enum
import json
import logging
import re
import sys
from dataclasses import dataclass, field
from typing import Any

from github.Issue import Issue
from github.IssueComment import IssueComment

from orchestrator.github import comments as _comments
from orchestrator.github.issue_polling import GitHubIssuePollingMixin

log = logging.getLogger("orchestrator.github")

SUPPORTED_SCHEMA_VERSION = 1
SCHEMA_VERSION_KEY = "schema_version"

PINNED_STATE_MARKER = "<!--orchestrator-state"
PINNED_STATE_RE = re.compile(
    r"<!--orchestrator-state\s+(\{.*?\})\s*-->",
    re.DOTALL,
)
# What a body has to be for the comment carrying it to be the pinned state:
# the marker and nothing else, anchored at both ends, so an ordinary
# bot-authored comment that merely embeds the marker is not mistaken for state.
#
# Where the payload runs is decided by the ordinary comment marker: every other
# comment this orchestrator posts carries it, appended at its end, or wherever
# its text already put it, in which case it is not appended again. A state
# comment carries it only inside a JSON string -- a key or value the comment
# had no room to escape.
#
# So whatever the payload is -- an object, closed by its brace or cut short of
# it, an array, a string, `7`, `null` -- it is read as JSON strings and the
# text between them. A string spans anything, raw `-->` and the ordinary marker
# included, since a preserved pull-request body can carry both, and a string a
# truncated write cut open runs to the terminator -- an escape it was cut in
# the middle of included, whose backslash is never taken to escape the
# terminator's first character. The text between strings spans a raw `-->` but
# never the marker, which only an ordinary comment's prose puts there, and the
# body may not end on it, which is where an ordinary comment appends it
# whatever string its text left open. A record a truncated write or a hand edit
# damaged -- `[]`, `["-->"]`, `7`, a raw object cut short -- is therefore
# IDENTIFIED as a corrupted state comment whatever its strings quote, while
# ordinary prose opening on a forged marker is no record.
#
# An identified comment is refused by the parser, so neither writer posts a
# record beside it, and a caller that would have read the miss as "this issue
# recorded nothing" is told otherwise.
#
# Every bot comment carrying the marker is matched against this on every read,
# so no quantifier gives back text another has to scan again: the whitespace
# after the marker and the payload's strings and text are taken possessively,
# and the payload ends directly on the terminator. A long run then costs one
# pass rather than one for every position before it.
_ORDINARY_COMMENT = re.escape(_comments.ORCHESTRATOR_COMMENT_MARKER)
_CLOSING_TERMINATOR = r"-->\s*\Z"
_JSON_STRING = r'"(?:[^"\\]|\\.)*+"'
PINNED_STATE_BODY_RE = re.compile(
    rf"""
    \A\s*<!--orchestrator-state\s++(?!.*{_ORDINARY_COMMENT}\s*\Z)(
        (?:{_JSON_STRING}|(?!{_ORDINARY_COMMENT}|{_CLOSING_TERMINATOR})[^"])*+
        (?:"(?:(?!{_CLOSING_TERMINATOR})(?:[^"\\]|\\(?!{_CLOSING_TERMINATOR}).))*+\\?)?
    ){_CLOSING_TERMINATOR}
    """,
    re.DOTALL | re.VERBOSE,
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


class AdmissionStatus(enum.Enum):
    """The outcome of admitting an issue comment candidate as pinned state.

    NO_COMMENT: No comment carrying authentic state markers authored by the
    trusted account was found.
    SUPPORTED: An authenticated comment carrying a valid object with integer
    schema_version equal to 1.
    UNSUPPORTED: An authenticated comment carrying an object, but with missing,
    non-integer, or unsupported schema_version.
    MALFORMED: An authenticated comment whose payload will not parse as JSON or
    parses into a non-object (array, scalar, null).
    """

    NO_COMMENT = "no_comment"
    SUPPORTED = "supported"
    UNSUPPORTED = "unsupported"
    MALFORMED = "malformed"

    @classmethod
    def of(cls, *, parsed: bool, supported: bool) -> AdmissionStatus:
        """What a reading was admitted as by its two flags, where whoever built it does not say.

        A state built in memory is a supported one, and a stand-in for a
        comment that would not parse is a malformed one.
        """
        if supported:
            return cls.SUPPORTED
        return cls.UNSUPPORTED if parsed else cls.MALFORMED


@dataclass(frozen=True)
class PinnedAdmission:
    """The admission result and identity of an authenticated pinned comment."""

    status: AdmissionStatus
    comment_id: int | None = None
    state: PinnedState | None = None
    found_version: Any = None
    supported_version: int = SUPPORTED_SCHEMA_VERSION
    refusal_reason: str | None = None
    issue_number: int | None = None
    repo_slug: str | None = None

    @classmethod
    def admit(
        cls,
        issue_comment: IssueComment,
        *,
        trusted_login: str | None,
        issue_number: int | None = None,
        repo_slug: str | None = None,
    ) -> PinnedAdmission:
        """Authenticate author and marker, then admit schema version.

        Without a trusted account nothing authenticates: with `trusted_login`
        None every comment answers NO_COMMENT, so a reader that could not
        learn whose token it holds never takes anybody's record as the state.
        """
        raw_payload = cls._authenticate(issue_comment, trusted_login)
        if raw_payload is None:
            return cls(
                status=AdmissionStatus.NO_COMMENT,
                issue_number=issue_number,
                repo_slug=repo_slug,
            )
        return cls._evaluate_payload(raw_payload, issue_comment.id, issue_number, repo_slug)

    @property
    def is_supported(self) -> bool:
        return self.status is AdmissionStatus.SUPPORTED

    @property
    def is_refused(self) -> bool:
        return self.status in (AdmissionStatus.UNSUPPORTED, AdmissionStatus.MALFORMED)

    @classmethod
    def payload_refusal(cls, payload: dict) -> str | None:
        """Why the next reading would refuse `payload` as a record, or None where it admits it.

        The one statement of the payload rule, for every reader or writer
        holding a payload rather than a comment: JSON's `true` and `1.0` are
        not the integer 1 to this reader, whatever Python's `==` says, a NaN or
        an infinity is a value JSON has no spelling for, and nesting past the
        recursion limit is past this reader's own bound, so a record carrying
        either is a comment no reader here parses.
        """
        if SCHEMA_VERSION_KEY not in payload:
            return "missing schema_version"
        version = payload[SCHEMA_VERSION_KEY]
        if isinstance(version, bool) or not isinstance(version, int):
            kind = "boolean" if isinstance(version, bool) else type(version).__name__
            return f"schema_version is {kind} rather than integer"
        if version != SUPPORTED_SCHEMA_VERSION:
            return f"unsupported schema_version {version} (supported: {SUPPORTED_SCHEMA_VERSION})"
        try:
            json.dumps(cls.spellable(payload), allow_nan=False)
        except (ValueError, RecursionError) as error:
            return f"a value JSON cannot spell ({error})"
        return None

    @classmethod
    def spellable(cls, payload: Any) -> Any:
        """`payload` itself, raising ValueError or RecursionError where it carries what no reading here takes.

        The value half of the payload rule, for a caller that spells a payload
        a value at a time before it holds a whole record: run first, it is what
        keeps any encoder from meeting nesting it could overflow on.

        Python's decoder takes `NaN`, `Infinity`, and `-Infinity`, and turns a
        literal past the float range, such as `1e309`, into an infinity: none
        is a number JSON has a spelling for. And how deep the decoder nests
        before it refuses depends on the interpreter and the stack it runs on:
        some stop far past the recursion limit, and some build nesting their
        own encoder then overflows on. So the recursion limit is this reader's
        own bound, the same everywhere, and nothing past it reaches an
        encoder. Walked a level at a time, with each level's numbers handed to
        the encoder flat, so neither the walk nor the encoder recurses.
        """
        nested = [payload]
        for _ in range(sys.getrecursionlimit()):
            dicts = [container.values() for container in nested if isinstance(container, dict)]
            sequences = [container for container in nested if isinstance(container, (list, tuple))]
            members = [member for container in (*dicts, *sequences) for member in container]
            json.dumps([number for number in members if isinstance(number, float)], allow_nan=False)
            nested = [member for member in members if isinstance(member, (dict, list, tuple))]
            if not nested:
                return payload
        raise RecursionError(f"nesting past the recursion limit of {sys.getrecursionlimit()}")

    @classmethod
    def _authenticate(
        cls,
        issue_comment: IssueComment,
        trusted_login: str | None,
    ) -> str | None:
        body = issue_comment.body or ""
        if PINNED_STATE_MARKER not in body:
            return None
        author_login = getattr(getattr(issue_comment, "user", None), "login", None)
        if trusted_login is None or author_login != trusted_login:
            return None
        match = PINNED_STATE_BODY_RE.match(body)
        return None if match is None else match.group(1)

    @classmethod
    def _evaluate_payload(
        cls,
        raw_payload: str,
        comment_id: int,
        issue_number: int | None,
        repo_slug: str | None,
    ) -> PinnedAdmission:
        try:
            payload = cls.spellable(json.loads(raw_payload))
        # Past the syntax error, the decoder refuses what it will not build: an
        # integer longer than the interpreter's digit limit is a ValueError, and
        # nesting deeper than it recurses a RecursionError. What it does build
        # is refused alike where a number in it is not finite or it nests past
        # the recursion limit. Each is a record no reader can take, so it is
        # refused like any other.
        except (ValueError, RecursionError) as error:
            log.warning(
                "repo=%s issue=#%s pinned state JSON unparseable in comment #%s: %s",
                repo_slug, issue_number, comment_id, error,
            )
            return cls(
                status=AdmissionStatus.MALFORMED,
                comment_id=comment_id,
                refusal_reason=f"malformed JSON ({error})",
                issue_number=issue_number,
                repo_slug=repo_slug,
            )
        if not isinstance(payload, dict):
            log.warning(
                "repo=%s issue=#%s pinned state is %s rather than an object in comment #%s",
                repo_slug, issue_number, type(payload).__name__, comment_id,
            )
            return cls(
                status=AdmissionStatus.MALFORMED,
                comment_id=comment_id,
                refusal_reason=f"payload is {type(payload).__name__} rather than an object",
                issue_number=issue_number,
                repo_slug=repo_slug,
            )
        found_ver = payload.get(SCHEMA_VERSION_KEY)
        reason = cls.payload_refusal(payload)
        if reason is not None:
            log.warning(
                "repo=%s issue=#%s pinned state schema_version %r invalid in comment #%s: %s",
                repo_slug, issue_number, found_ver, comment_id, reason,
            )
            return cls(
                status=AdmissionStatus.UNSUPPORTED,
                comment_id=comment_id,
                found_version=found_ver,
                refusal_reason=reason,
                issue_number=issue_number,
                repo_slug=repo_slug,
            )
        state = PinnedState(
            comment_id=comment_id,
            state_data=payload,
            parsed=True,
            supported=True,
            admission_status=AdmissionStatus.SUPPORTED,
            found_version=found_ver,
            issue_number=issue_number,
            repo_slug=repo_slug,
        )
        state.synced = json.dumps(payload, sort_keys=True)
        return cls(
            status=AdmissionStatus.SUPPORTED,
            comment_id=comment_id,
            state=state,
            found_version=found_ver,
            issue_number=issue_number,
            repo_slug=repo_slug,
        )


admit_pinned_comment = PinnedAdmission.admit


class PinnedEdit(enum.Enum):
    """What a strict rewrite of the pinned comment came to.

    Only EDITED says the comment now carries the body sent, and only
    UNCONFIRMED says a request went out that may or may not have landed:
    GitHub's comment edit is a whole-body PATCH with no condition on what it
    replaces, so a response that never came back, or came back carrying
    another body, leaves the record reading either way. The others were
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
    # The issue's record parses and is refused admission -- the comment named,
    # or an authenticated one ahead of it that every reader takes instead; one
    # that will not parse is MOVED -- or the state the rewrite would write is
    # one the next reading would refuse.
    UNSUPPORTED = "unsupported"
    UNCONFIRMED = "unconfirmed"


@dataclass(init=False)
class PinnedState:
    """Pinned comment identity and mutable workflow state payload.

    ``state_data`` is the descriptive constructor keyword. The custom adapter
    retains the historical ``data=`` keyword and the ``.data`` instance
    attribute used throughout the workflow.

    ``parsed`` is whether the payload this carries came out of the comment or
    stood in for one that would not parse, and ``supported`` whether the
    comment's record was admitted at all -- false for that stand-in and for a
    record that parses under a version other than the supported one, and
    false for any state built as unparsed, whatever it is told, so a stand-in
    is refused wherever it was built. They are fields of their own because the stand-in is indistinguishable from the
    real thing: a refused comment reads back as ``{}``, which is exactly what
    an issue the orchestrator has not recorded anything for reads back as.
    Nothing replaces it -- neither writer lays a state over a refused comment
    or posts one beside it, so the comment stays as it stands -- and a caller
    DECIDING on the absence of a recorded branch or pull request would be
    deciding on a record it never read. ``admission_status``,
    ``found_version``, ``supported_version``, ``refusal_reason``,
    ``issue_number``, and ``repo_slug`` are what a caller reports such a
    refusal with, locally.

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
    its recovery's, an approval tail's, a landed base rewrite's finish's, an
    auto-rebase attempt's checkpoint -- a park, or a recovery's clear or
    record of a gate's hold -- or a final-docs pass's completion, or the
    invalidation or hold that withholds a no-change one, or an in_review ready
    ping's arming or settlement --
    one refused over a comment that moved, or one sent and never confirmed --
    on one whose report post or re-read left its transaction owed over a
    comment another road wrote meanwhile, and on an approval tail's whose records the comment moved: the
    comment is not, or may not be, what the state
    was decided on, so the whole-state writer writes nothing for it rather
    than put back everything another road wrote since. Any such commit that
    lands clears it.
    """

    comment_id: int | None = None
    state_data: dict = field(default_factory=dict)
    parsed: bool = True
    supported: bool = True
    admission_status: AdmissionStatus = AdmissionStatus.SUPPORTED
    found_version: Any = None
    supported_version: int = SUPPORTED_SCHEMA_VERSION
    refusal_reason: str | None = None
    issue_number: int | None = None
    repo_slug: str | None = None

    def __init__(
        self,
        comment_id: int | None = None,
        state_data: Any = _MISSING_STATE,
        *,
        parsed: bool = True,
        **extra_fields: Any,
    ) -> None:
        legacy_state = extra_fields.pop("data", _MISSING_STATE)
        if state_data is not _MISSING_STATE and legacy_state is not _MISSING_STATE:
            raise TypeError("PinnedState() got multiple values for state data")
        selected_state = legacy_state if state_data is _MISSING_STATE else state_data
        if selected_state is _MISSING_STATE:
            selected_state = {}
        self.comment_id = comment_id
        self.state_data = selected_state
        told_supported = extra_fields.pop("supported", True)
        self.parsed = parsed
        self.supported = parsed and told_supported
        self.admission_status = extra_fields.pop(
            "admission_status", AdmissionStatus.of(parsed=parsed, supported=self.supported),
        )
        self.found_version = extra_fields.pop("found_version", None)
        self.supported_version = extra_fields.pop("supported_version", SUPPORTED_SCHEMA_VERSION)
        self.refusal_reason = extra_fields.pop("refusal_reason", None)
        self.issue_number = extra_fields.pop("issue_number", None)
        self.repo_slug = extra_fields.pop("repo_slug", None)
        if extra_fields:
            unexpected_name = next(iter(extra_fields))
            raise TypeError(
                f"PinnedState() got an unexpected keyword argument {unexpected_name!r}",
            )
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
        if not (self.supported and self.parsed):
            return False
        spelled = json.dumps(self.state_data, sort_keys=True)
        return spelled == json.dumps(state_data, sort_keys=True)

    def get(self, key: str, default: Any = None) -> Any:
        """Return a workflow-state field or its default."""
        return self.state_data.get(key, default)

    def set(self, key: str, state_value: Any) -> None:
        """Set one workflow-state field."""
        self.state_data[key] = state_value


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
    repo_slug: str | None = None,
) -> PinnedState | None:
    """Parse one authenticated, state-only pinned comment candidate."""
    admission = admit_pinned_comment(
        issue_comment,
        trusted_login=trusted_login,
        issue_number=issue_number,
        repo_slug=repo_slug,
    )
    if admission.status is AdmissionStatus.NO_COMMENT:
        return None
    if admission.status is AdmissionStatus.SUPPORTED:
        return admission.state
    if admission.status is AdmissionStatus.MALFORMED:
        return PinnedState(
            comment_id=admission.comment_id,
            state_data={},
            parsed=False,
            supported=False,
            admission_status=AdmissionStatus.MALFORMED,
            found_version=None,
            refusal_reason=admission.refusal_reason,
            issue_number=issue_number,
            repo_slug=repo_slug,
        )
    return PinnedState(
        comment_id=admission.comment_id,
        state_data={},
        parsed=True,
        supported=False,
        admission_status=AdmissionStatus.UNSUPPORTED,
        found_version=admission.found_version,
        refusal_reason=admission.refusal_reason,
        issue_number=issue_number,
        repo_slug=repo_slug,
    )


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
        refused record from none and would post a pin beside one. So is every
        state the walk below finds a record refused admission for -- the
        comment the caller's id names, or one ahead of it, or one anywhere
        where that id names no state comment: neither writer may overwrite
        that comment, create a replacement beside it, or silently stamp it as
        current. A state carrying no version is stamped with the supported
        one, and a state the next reading would refuse -- another version, a
        value JSON cannot spell, nesting past the recursion limit -- is not
        written either.

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
            return state
        state.data.setdefault(SCHEMA_VERSION_KEY, SUPPORTED_SCHEMA_VERSION)
        refusal = PinnedAdmission.payload_refusal(state.data)
        if refusal is not None:
            log.warning("issue=#%s state to pin is refused (%s); writing nothing", issue.number, refusal)
            return state
        body = pinned_state_body(state.data)
        if located is None:
            state.comment_id = issue.create_comment(body).id
        else:
            located[0].edit(body)
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
        rather than recreated. The walk that finds the comment is also the
        last reading before the edit, so a comment another writer moved since
        `over` was read -- compared as the comment's JSON spells it, where
        `null` is not an absent field and `true` is not `1` -- is answered
        MOVED and left as it stands.

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
        state.data.setdefault(SCHEMA_VERSION_KEY, SUPPORTED_SCHEMA_VERSION)
        if PinnedAdmission.payload_refusal(state.data) is not None:
            log.warning(
                "issue=#%s rewrite is refused (%s); sending nothing",
                issue.number, PinnedAdmission.payload_refusal(state.data),
            )
            return PinnedEdit.UNSUPPORTED
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
            return PinnedEdit.UNSUPPORTED if reading.parsed and not reading.supported else PinnedEdit.MOVED
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
        self, issue: Issue, comment_id: int | None,
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
            if reading is not None and (issue_comment.id == comment_id or not reading.supported):
                return issue_comment, reading
        return None

    def _send_pinned_edit(self, issue_comment: IssueComment, body: str) -> str:
        """Send one edit and hand back the body GitHub answered it with.

        PyGithub refreshes the comment from the response, so what it carries
        afterwards is what GitHub says it stored.
        """
        issue_comment.edit(body)
        return issue_comment.body
