# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The pinned-state admission target: one comment body, read by the real reader.

`PinnedAdmission.admit` is asked about the body under every author the gate
has to tell apart, and its answer is held to the contract it implements
(docs/contracts.md, C-03 and C-04) rather than to a second copy of it. An
author other than the trusted account, a comment with no author, and a reader
with no trusted account authenticate nothing. An authenticated comment is the
whole-comment marker and nothing else, admitted only where its payload is a
JSON object carrying the integer `schema_version` 1 -- an absent, boolean,
float, string, or other version is refused -- and refused, never raised over,
where it does not decode. Every state admitted, and a record built around the
body itself, are written back through `pinned_state_body` in both renderings
and read back as exactly themselves, whatever markers and terminators they
quote.

A refusal is an answer like any other. What fails the input is the reader
raising, a broken rule (`AdmissionBreach`), or a run past the target's limits.
The body is the input decoded as UTF-8, any byte that does not decode held as
the lone surrogate `surrogateescape` maps it to, so no input is turned away.
"""
from __future__ import annotations

import json
from types import SimpleNamespace

from orchestrator.github import comments as _comments, pinned_state as _pinned_state

_TRUSTED_LOGIN = "chipping-orchestrator-bot"
_COMMENT_ID = 4242
_ISSUE_NUMBER = 7
_REPO_SLUG = "fuzz/pinned-admission"
_TERMINATOR = "-->"
_VERSION_KEY = _pinned_state.SCHEMA_VERSION_KEY

# The author and the trusted account of each comment no reading takes as
# state: another login, a comment whose author GitHub no longer names, and a
# reader that could not learn whose token it holds.
_UNTRUSTED = (
    ("mallory", _TRUSTED_LOGIN),
    (None, _TRUSTED_LOGIN),
    (_TRUSTED_LOGIN, None),
)


class AdmissionBreach(AssertionError):
    """The reader answered an input in a way its contract does not allow."""


def admit(body: str, author: str | None = _TRUSTED_LOGIN, trusted: str | None = _TRUSTED_LOGIN):
    """The reader's answer for one in-memory comment carrying `body`."""
    user = None if author is None else SimpleNamespace(login=author)
    return _pinned_state.PinnedAdmission.admit(
        SimpleNamespace(id=_COMMENT_ID, body=body, user=user),
        trusted_login=trusted,
        issue_number=_ISSUE_NUMBER,
        repo_slug=_REPO_SLUG,
    )


def quoting_record(body: str) -> dict:
    """A supported record quoting `body` as a key, a list member, and a value."""
    return {body: [body], "note": body, _VERSION_KEY: 1}


def test_one_input(fuzz_input: bytes) -> None:
    """Admit one body under every author, and write back whatever it admits."""
    body = fuzz_input.decode("utf-8", "surrogateescape")
    for author, trusted in _UNTRUSTED:
        refused = admit(body, author, trusted).status is _pinned_state.AdmissionStatus.NO_COMMENT
        _require(refused, "a comment authenticated without the trusted account behind it")
    admission = admit(body)
    if admission.status is not _pinned_state.AdmissionStatus.NO_COMMENT:
        _Reading(body, admission).check()
    if admission.is_supported:
        _check_round_trip(admission.state.state_data)
    _check_round_trip(quoting_record(body))


def _require(condition: bool, breach: str) -> None:
    if not condition:
        raise AdmissionBreach(breach)


class _Reading:
    """One authenticated comment's answer, and the rules it is held to."""

    def __init__(self, body: str, admission) -> None:
        self._body = body
        self._admission = admission

    def check(self) -> None:
        """Hold the comment to the marker rule and its payload to the version rule."""
        whole = self._body.strip()
        _require(
            whole.startswith(_pinned_state.PINNED_STATE_MARKER) and whole.endswith(_TERMINATOR),
            "a comment that is not the whole marker authenticated",
        )
        _require(
            not whole.endswith(_comments.ORCHESTRATOR_COMMENT_MARKER),
            "an ordinary comment authenticated",
        )
        _require(self._admission.comment_id == _COMMENT_ID, "a reading named another comment")
        payload = _pinned_state.PINNED_STATE_BODY_RE.match(self._body).group(1)
        if self._admission.is_supported:
            self._check_supported(payload)
        else:
            self._check_refused(payload)

    def _is_version_one(self, version: object) -> bool:
        """Whether `version` is the integer 1, which JSON's `true` and `1.0` are not."""
        return isinstance(version, int) and not isinstance(version, bool) and version == 1

    def _check_supported(self, payload: str) -> None:
        state = self._admission.state
        _require(
            self._is_version_one(state.state_data.get(_VERSION_KEY)),
            "a record without schema_version 1 was admitted",
        )
        _require(
            json.dumps(json.loads(payload), sort_keys=True) == state.synced,
            "an admitted record is not the payload its comment carries",
        )

    def _check_refused(self, payload: str) -> None:
        """Hold a refusal to what the payload decodes as, asked of the decoder alone."""
        _require(
            self._admission.state is None and bool(self._admission.refusal_reason),
            "a refused record carried a state or no reason",
        )
        try:
            decoded = json.loads(payload)
        except (ValueError, RecursionError):
            decoded = None
        if not isinstance(decoded, dict):
            _require(
                self._admission.status is _pinned_state.AdmissionStatus.MALFORMED,
                "a payload that is no JSON object was not refused as malformed",
            )
        elif self._is_version_one(decoded.get(_VERSION_KEY)):
            _require("JSON" in self._admission.refusal_reason, "a version-1 object was refused for its version")


def _check_round_trip(state_data: dict) -> None:
    """Write `state_data` in both renderings and read each back as exactly itself."""
    for rendered in (
        _pinned_state.pinned_state_body(state_data),
        _pinned_state.pinned_state_body(state_data, escaped_in_full=True),
    ):
        state = admit(rendered).state
        _require(state is not None and state.reads_as(state_data), "a written record did not read back as itself")
        _require(
            state.synced == json.dumps(state_data, sort_keys=True),
            "a written record read back with another spelling",
        )
