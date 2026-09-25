# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What a workflow verification artifact reports, and who witnessed it.

Evidence is a sequence of commands, each with the status it exited and
whatever transcript the artifact carries for it. The sequence is rendered once,
here, so the digest an artifact publishes is taken over one spelling of it and
a reread can be exact.

Who ran those commands is part of the evidence rather than a footnote to it.
This orchestrator can report commands it spawned itself and watched exit; it
can also carry a reviewer's account of commands nobody here observed. Both are
publishable and they are not worth the same, so the witness travels with the
commands and is stated where a reader sees it.

A command that would not render back as the command it names is refused where
it is declared, which is the only place the two can still be told apart: text
carrying the backtick that delimits it or a line ending that would make it two
lines, a transcript carrying the fence that closes it -- at any indent and
behind any line ending, since a fence GitHub reads as closing and this parser
does not would render as a comment neither of them describes -- and either
carrying a receipt marker of ours, which a thread search recognizes by
substring and so would read as a step nobody took.

Line endings are read as Python reads them rather than as the newline alone,
which is wider than the three GitHub breaks a line on. Deliberately: refusing
one transcript costs its producer a sanitizing pass, while missing one
publishes a comment rendering content the evidence never reported.

An empty sequence renders as an explicit absence. A section that simply listed
nothing would read as a run that passed, and the one thing this format may
never do is let the absence of a command stand in for a command that succeeded.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum

from orchestrator.github import comments as _comments

# How one command's transcript is delimited. An info string, so GitHub renders
# the transcript as the plain text it is rather than guessing a language for it.
_FENCE = "```"
_OPENING_FENCE = f"{_FENCE}text"

_COMMAND_LINE = "`{command}` -- exit {exit_status}"
_TRANSCRIPT = f"\n\n{_OPENING_FENCE}\n{{output}}\n{_FENCE}"

# What one rendered command reads back as. Permissive on purpose: an exact
# re-render is what decides whether a body is an artifact at all, so this has
# only to recover what a rendering wrote. The transcript is taken up to the
# first line that opens with a fence, which is why no transcript may carry one.
_ENTRY = re.compile(
    r"`(?P<command>[^`\n\r]+)` -- exit (?P<exit_status>-?[0-9]+)"
    rf"(?:\n\n{_OPENING_FENCE}\n(?P<output>.*?)\n{_FENCE})?",
    re.DOTALL,
)

_SEPARATOR = "\n\n"

# What an artifact says when no command ran, spelled out rather than left blank.
NOTHING_RAN = (
    "No verification command was configured, so none ran. This artifact "
    "records that absence and is not evidence that anything passed."
)

# The characters a command line may not carry: the delimiter it is rendered
# between, and either line ending that would make it two lines. The carriage
# return is one of them wherever it stands on its own, since GitHub breaks a
# line on a bare one and would render whatever follows as its own block.
_UNRENDERABLE_IN_COMMAND = frozenset("`\n\r")


class ArtifactRefusedError(ValueError):
    """A workflow verification artifact this format will not publish, and why.

    One refusal type across both owners, because a caller publishing an
    artifact has one thing to catch: a command that would not render back as
    itself is refused for the same reason an identity the header cannot carry
    is, and neither can become a comment.
    """


class EvidenceSource(StrEnum):
    """Who witnessed the commands an artifact reports.

    ORCHESTRATOR_EXECUTED is this process reporting commands it spawned itself
    and watched exit. REVIEWER_REPORTED is a reviewer run's account of commands
    nobody here observed, carried exactly as the reviewer stated them and never
    presented as this orchestrator's own observation.
    """

    ORCHESTRATOR_EXECUTED = "orchestrator-executed"
    REVIEWER_REPORTED = "reviewer-reported"


@dataclass(frozen=True)
class VerifiedCommand:
    """One command an artifact reports, with the result it earned.

    `command` is the command line exactly as it was run or reported.
    `exit_status` is what it exited with, and `output` whatever transcript the
    artifact carries for it -- already redacted and bounded by whoever produced
    it -- or empty when it carries none.

    Refused at construction rather than at rendering, so no reading of a record
    can hand a caller a command an artifact could not have carried.
    """

    command: str
    exit_status: int
    output: str = ""

    def __post_init__(self) -> None:
        refusal = self._refusal()
        if refusal is not None:
            raise ArtifactRefusedError(refusal)

    @property
    def rendered(self) -> str:
        """This command, its exit status, and the transcript it carries."""
        line = _COMMAND_LINE.format(
            command=self.command, exit_status=self.exit_status,
        )
        if not self.output:
            return line
        return line + _TRANSCRIPT.format(output=self.output)

    def _refusal(self) -> str | None:
        """Why this command cannot be rendered as it stands, or None when it can."""
        if not self._typed():
            return "a reported command is not a command line, a status, and a transcript"
        if not self.command.strip() or _UNRENDERABLE_IN_COMMAND & set(self.command):
            return f"the command {self.command!r} cannot be rendered in an artifact"
        if any(_comments.carries_reserved_marker(text) for text in (self.command, self.output)):
            return "a reported command carries a receipt marker of this orchestrator's"
        if self._fenced():
            return "a reported transcript carries the fence that closes it"
        return None

    def _fenced(self) -> bool:
        """Whether the transcript carries a line GitHub would read as closing it.

        Split on every line ending rather than on the newline alone: a fence
        hidden behind a bare carriage return closes the block where GitHub
        renders it, while a reader splitting on newlines sees one transcript
        line that merely contains a fence and never ends.
        """
        return any(
            line.lstrip().startswith(_FENCE)
            for line in self.output.splitlines()
        )

    def _typed(self) -> bool:
        """Whether each member is of its own type, `bool` excluded from the status."""
        return (
            isinstance(self.command, str)
            and isinstance(self.output, str)
            and isinstance(self.exit_status, int)
            and not isinstance(self.exit_status, bool)
        )


def render_commands(commands: tuple[VerifiedCommand, ...]) -> str:
    """The evidence section an artifact carries, or the absence of one."""
    if not commands:
        return NOTHING_RAN
    return _SEPARATOR.join(ran.rendered for ran in commands)


def commands_from(evidence: str) -> tuple[VerifiedCommand, ...] | None:
    """The commands one rendered evidence section reports, or None for anything else.

    What is recovered is only a candidate: the caller re-renders the whole
    artifact and keeps it only when that comes back byte for byte. So anything
    the entries read back as but a command this format would publish -- one
    quoting a receipt marker of ours, one claiming a status of more digits
    than Python converts -- is None here rather than a raise on a caller
    asking what a comment is.
    """
    if evidence == NOTHING_RAN:
        return ()
    try:
        return _entries_of(evidence)
    except ValueError:
        return None


def _entries_of(evidence: str) -> tuple[VerifiedCommand, ...] | None:
    """Each rendered entry off the front, or None at the first that is not one.

    Off the front rather than by splitting, since a transcript may carry
    anything a rendering could not have put between two entries.
    """
    found = []
    rest = evidence
    while rest:
        entry = _ENTRY.match(rest)
        if entry is None:
            return None
        found.append(VerifiedCommand(
            command=entry["command"],
            exit_status=int(entry["exit_status"]),
            output=entry["output"] or "",
        ))
        rest = rest[entry.end():].removeprefix(_SEPARATOR)
    return tuple(found)
