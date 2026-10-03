# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The hidden payload a verification artifact's evidence is carried in.

The commands an artifact reports, the status each exited with, and each whole
transcript, spelled as machine-readable text that can sit inside an HTML
comment. Hidden, so the rendered comment can say what the evidence amounts to
without a reader scrolling past every transcript, while a reader that needs
the evidence itself -- a reviewer handed it after a restart -- gets back
exactly what was recorded.

The payload is one JSON object: the version of this spelling, the content
revision of the evidence, and the commands in the order given, repeats and
all, each with its command line, exit status, and transcript. Versioned, so a
later spelling can sit beside this one and a reader never interprets a payload
it does not read. The revision is the one `verification_evidence` takes over
the rendered evidence section and never one taken over the payload, so
evidence keeps the revision it was settled under whichever presentation
carries it -- and the payload names which evidence it is, so one whose
commands do not hash to the revision it names is no evidence at all.

Safe inside a comment because of what it cannot contain. JSON escapes quotes,
backslashes, and every control character, and here spells everything past
printable ASCII as an escape too, so the payload is printable ASCII on one
line whatever line endings a transcript carries. Both angle brackets are then
escaped in the serialized text -- never in the value, and neither occurs
there outside a string -- so it carries no `-->` or `--!>` to end the comment
early and render a transcript's tail as visible content, and no `<!--` to
open a receipt marker of ours, which a thread search reading by substring
would take for a step nobody took. Any JSON decoder reads every escape back
into the character it stands for.

Decoding is exact: a payload is evidence only when it is the one spelling
this codec writes for the commands it decodes to. A comment is text on a
thread anybody can post to, so every other payload -- malformed, of another
version, of the wrong shape or types, carrying a command the evidence model
refuses, or naming a revision its commands do not hash to -- answers None
rather than raising.
"""
from __future__ import annotations

import json
from typing import Any

from orchestrator.github import verification_evidence as _evidence

# Which spelling of the payload this codec writes and reads.
_PAYLOAD_VERSION = 1

_VERSION = "version"

_CONTENT_REVISION = "content"

_COMMANDS = "commands"

_COMMAND = "command"

_EXIT_STATUS = "exit_status"

_OUTPUT = "output"

# One spelling of the object: no optional whitespace anywhere.
_SEPARATORS = (",", ":")

# The comment delimiters' characters, each as the JSON escape a decoder reads
# back into it.
_HIDDEN = str.maketrans({"<": r"\u003c", ">": r"\u003e"})


def encode_evidence(commands: tuple[_evidence.VerifiedCommand, ...]) -> str:
    """The hidden payload `commands` are carried in, in the order given.

    `ArtifactRefusedError` for anything but a tuple of reported commands, and
    for evidence with no revision to name -- text UTF-8 cannot carry, or a
    status of more digits than Python converts -- which no artifact could
    publish either.
    """
    if not isinstance(commands, tuple) or not all(
        isinstance(ran, _evidence.VerifiedCommand) for ran in commands
    ):
        raise _evidence.ArtifactRefusedError("the evidence is not a tuple of reported commands")
    try:
        revision = _evidence.content_revision(commands)
    except ValueError as unrenderable:
        raise _evidence.ArtifactRefusedError(
            "the evidence has no revision a payload could name",
        ) from unrenderable
    serialized = json.dumps(
        {
            _VERSION: _PAYLOAD_VERSION,
            _CONTENT_REVISION: revision,
            _COMMANDS: [
                {_COMMAND: ran.command, _EXIT_STATUS: ran.exit_status, _OUTPUT: ran.output}
                for ran in commands
            ],
        },
        separators=_SEPARATORS,
    )
    return serialized.translate(_HIDDEN)


def decode_evidence(payload: Any) -> tuple[_evidence.VerifiedCommand, ...] | None:
    """The commands one hidden payload carries, in order, or None for anything else.

    The version is read first, so a payload in another spelling is never
    interpreted as this one. Whatever the rest decodes to is then encoded
    again and kept only when that comes back character for character, which
    is what holds the revision a payload names to the commands it carries,
    and holds every choice of spelling besides: how the version is written,
    member order and whitespace, which characters are escaped.
    """
    parsed = _parsed(payload)
    if not isinstance(parsed, dict) or parsed.get(_VERSION) != _PAYLOAD_VERSION:
        return None
    commands = _commands_in(parsed.get(_COMMANDS))
    if commands is None or _respelled(commands) != payload:
        return None
    return commands


def _parsed(payload: Any) -> Any:
    """The JSON value a payload spells, or None where it spells none.

    Nesting deeper than the decoder recurses, and an integer of more digits
    than Python converts, are as unreadable as a syntax error.
    """
    if not isinstance(payload, str):
        return None
    try:
        return json.loads(payload)
    except (ValueError, RecursionError):
        return None


def _commands_in(listed: Any) -> tuple[_evidence.VerifiedCommand, ...] | None:
    """Each listed command as the evidence model reads it, or None at the first it refuses.

    Through the model's own constructor, so no payload hands a caller a
    command its rendering could not have carried -- a closing fence or a
    receipt marker of ours hidden behind a JSON escape included. A member a
    command lacks reads as None, which the model refuses; a member it should
    not have is left for the exact re-encoding to refuse.
    """
    if not isinstance(listed, list):
        return None
    if not all(isinstance(entry, dict) for entry in listed):
        return None
    try:
        return tuple(
            _evidence.VerifiedCommand(
                entry.get(_COMMAND), entry.get(_EXIT_STATUS), entry.get(_OUTPUT),
            )
            for entry in listed
        )
    except _evidence.ArtifactRefusedError:
        return None


def _respelled(commands: tuple[_evidence.VerifiedCommand, ...]) -> str | None:
    """The payload `commands` encode to, or None where they encode to none."""
    try:
        return encode_evidence(commands)
    except _evidence.ArtifactRefusedError:
        return None
