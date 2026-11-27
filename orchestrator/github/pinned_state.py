# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Pinned-state model, comment authentication, schema admission, and wire format.

Admission requires a whole-comment marker authored by the token account and a
JSON object with integer `schema_version == 1`. A refused record retains its
comment ID and the reason for refusal.
"""
from __future__ import annotations

import enum
import json
import logging
import re
import sys
from dataclasses import dataclass, field
from typing import Any

from github.IssueComment import IssueComment

from orchestrator.github import comments as _comments

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
    # The caller's question, asked behind the walk and immediately before the
    # edit (`edit_questions`), answered that the edit no longer stands.
    HELD = "held"
    UNCONFIRMED = "unconfirmed"

    @classmethod
    def unsent(cls, reading: PinnedState | None, over: dict) -> PinnedEdit | None:
        """What a rewrite over the comment its walk read as `reading` answers unsent; None where it may go on."""
        if reading is None:
            return cls.MISSING
        if not reading.reads_as(over):
            return cls.UNSUPPORTED if reading.parsed and not reading.supported else cls.MOVED
        return None


@dataclass(kw_only=True)
class PinnedState:
    """Pinned comment identity and mutable workflow state payload.

    ``state_data`` is the payload: the one constructor keyword it is passed as
    and the one attribute every reader and writer reaches it through.

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
    ping's arming or settlement, or a developer completion's transfer --
    one refused over a comment that moved, or one sent and never confirmed --
    on one whose report post or re-read left its transaction owed over a
    comment another road wrote meanwhile, and on an approval tail's whose records the comment moved: the
    comment is not, or may not be, what the state
    was decided on, so the whole-state writer writes nothing for it rather
    than put back everything another road wrote since. Any such commit that
    lands clears it. A developer completion's capture or retirement sent and
    never confirmed withholds a state too (`workflow/engine/completion_commits.py`),
    and so does any answer over a comment that no longer reads as the state
    was read; one that lands clears nothing: it owns one field, and the state
    may still be stale in every other. A decomposer manifest correction's
    writes withhold a state alike (`workflow/stages/decomposition/correction_commits.py`).
    """

    comment_id: int | None = None
    state_data: dict = field(default_factory=dict)
    parsed: bool = True
    supported: bool = True
    # Left unset, the status the two flags above admit the reading as.
    admission_status: AdmissionStatus | None = None
    found_version: Any = None
    supported_version: int = SUPPORTED_SCHEMA_VERSION
    refusal_reason: str | None = None
    issue_number: int | None = None
    repo_slug: str | None = None

    def __post_init__(self) -> None:
        self.supported = self.parsed and self.supported
        if self.admission_status is None:
            self.admission_status = AdmissionStatus.of(parsed=self.parsed, supported=self.supported)
        self.synced: str | None = None
        self.withheld = False

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


def pinned_state_body(state_data: dict, *, escaped_in_full: bool = False) -> str:
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

    `escaped_in_full` is the escaped rendering whatever its length, for a
    caller deciding whether to accept a record at all: one it takes only
    because its terminators would go out unescaped is a record that leaves
    the rest of the comment as visible issue text.
    """
    payload = json.dumps(state_data, sort_keys=True)
    escaped = PINNED_STATE_TEMPLATE.format(
        payload=payload.replace(_COMMENT_CLOSE, _ESCAPED_COMMENT_CLOSE),
    )
    if escaped_in_full or len(escaped) <= MAX_PINNED_BODY:
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
