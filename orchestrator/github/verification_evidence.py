# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What a workflow verification artifact reports, and who witnessed it.

Evidence is a sequence of commands, each with the status it exited and
whatever transcript the artifact carries for it. The sequence is rendered once,
here, and its revision is taken here over that rendering, so the digest an
artifact publishes is taken over one spelling of it whichever presentation
carries the commands: the hidden payload `verification_payloads` encodes, the
visible section an artifact showed before its evidence was hidden
(`verification_legacy_artifacts`), or the quote a reviewer is handed. A
revision settled under one of them is the revision under every other, and a
reread can be exact.

Who ran those commands is part of the evidence rather than a footnote to it.
This orchestrator can report commands it spawned itself and watched exit; it
can also carry a reviewer's account of commands nobody here observed. Both are
publishable and they are not worth the same, so the witness travels with the
commands and is stated where a reader sees it.

A command that would not render back as the command it names is refused where
it is declared, which is the only place the two can still be told apart: text
carrying the backtick that delimits it or a line ending that would make it two
lines, a transcript carrying the fence that closes it -- at any indent and
behind any line ending, since a fence GitHub reads as closing and the
section's reader does not would render as text neither of them describes --
and either carrying a receipt marker of ours, which a thread search
recognizes by substring and so would read as a step nobody took.

Line endings are read as Python reads them rather than as the newline alone,
which is wider than the three GitHub breaks a line on. Deliberately: refusing
one transcript costs its producer a sanitizing pass, while missing one
publishes a comment rendering content the evidence never reported.

An empty sequence renders as an explicit absence. A section that simply listed
nothing would read as a run that passed, and the one thing an artifact may
never do is let the absence of a command stand in for a command that succeeded.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from orchestrator.github import comments as _comments, developer_reports as _reports

# How one command's transcript is delimited. An info string, so GitHub renders
# the transcript as the plain text it is rather than guessing a language for it.
_FENCE = "```"
_OPENING_FENCE = f"{_FENCE}text"

_COMMAND_LINE = "`{command}` -- exit {exit_status}"
_TRANSCRIPT = f"\n\n{_OPENING_FENCE}\n{{output}}\n{_FENCE}"

_SEPARATOR = "\n\n"

# What the rendering says when no command ran, spelled out rather than left blank.
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
    """The evidence section an artifact's commands render as, or the absence of one."""
    if not commands:
        return NOTHING_RAN
    return _SEPARATOR.join(ran.rendered for ran in commands)


def content_revision(commands: tuple[VerifiedCommand, ...]) -> str:
    """The revision of one evidence section: the SHA-256 of its exact rendering.

    Taken over the rendering, and here rather than beside any one way of
    presenting it, so the hidden payload (`verification_payloads`), a legacy
    artifact's visible section, and a reviewer's quote name evidence by one
    revision, and a settled revision stays settled however an artifact comes
    to show its commands.
    """
    return _reports.content_digest(render_commands(commands))
