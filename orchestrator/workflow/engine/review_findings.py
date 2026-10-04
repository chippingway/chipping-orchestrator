# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""A reviewer's findings as a human is shown them, without its declaration.

The findings are the slice `completion_verdicts` returns above the `VERDICT:`
line, and that slice also holds the verification declaration the reviewer
closes with: a RUN block listing every command with its exit status and
output, or a REUSED line naming the evidence it inspected. The orchestrator
reads that declaration on its own (`review_verification`) and publishes the
evidence it earns apart from the feedback, so quoting it there again only
buries the findings under a transcript. `_concise_findings` keeps the
reviewer's words and drops the protocol: every marker and step line, the
output of each check shown to pass -- one exit line, and that line reading 0 --
and each check that wrote neither an exit status nor output, since a bare
command inventory gives a developer nothing to act on. Any other check not
shown to pass -- an exit line missing, blank, repeated, or reading anything
else -- is what a developer has to act on, so it stays as a sentence naming its
command and how it ended, over the output the reviewer quoted as a code block.
The disposition of a verdict a live reviewer round returns
(`stages/validating/review_disposition.py`) formats its feedback here once the
declaration is read, and that is the feedback a change request is persisted
with, posted as, and handed to its developer as. A later tick's handoff of a
persisted request (`stages/validating/review_handoffs.py`) formats the
record's feedback here again where it posts it and resumes the developer on
it: a record persisted before that formatting still carries its declaration
raw, and one persisted concise goes out as it was. The post a
`/orchestrator continue` replays has its findings formatted here too, as the
replay quotes it (`stages/validating/feedback_posts.py`).

Display is read apart from validation, and more loosely, since nothing here is
accepted -- there is only text to show. A line opening on a marker or step
keyword is protocol wherever it sits, and a step line outside any block opens
one, as the RUN line it is missing would have. A block its RUN line opens runs
to its closing line where it has one. Where it has none, or no RUN line opened
it to vouch that a closing line further down is its own, nothing marks where
its output stops and the findings resume, so the doubt goes to the findings:
the block holds only the unbroken lines below each step line and the closed
code fences below them, and ends at the first blank line that neither a step
line nor such a fence follows, or at a text line right below a fence.

A code fence is read whole, from where Markdown opens it to where Markdown
ends it, as `review_findings_fences` reads them: on its closing run, measured
from the content column of the list item holding it rather than from its
opening run; before the first line set in less than that column, which ends
the item; or, neither coming, at the end of the findings. Indented code, which
Markdown shows as code too, reads as a fence with no fence lines. A blank line
inside one ends nothing, and a transcript it quotes goes, or stays as a diagnostic, in
one piece, while a finding below where it ends stays a finding. One holding
protocol lines below a check's command or exit line is that check's output, as
a failing test's output may quote the protocol, even where it holds nothing
else: a fixture may print step lines alone, and the diagnostic below it stays
the check's. Anywhere else, one holding protocol lines beside other text is
the findings quoting such output unless it is plainly a declaration. Every
protocol line a quote holds -- marker lines too -- is hidden, starting,
closing, and passing no check, and the rest stays where it stood; a quote
holding no text goes whole, fence lines too, rather than show as an empty
fence. Below a check that passed, or that wrote neither an exit status nor
output, the doubt cuts the other way: that check's output goes, and a fence in
it may as well list the block's next checks, so each step it quotes is read as
a check of its own and one not shown passing stays, as any other would. A
fence wraps a declaration instead right below a RUN line, only blank
lines between, where it lists that block's steps; outside a check's output,
where it holds protocol lines and nothing else; and where the findings declare
nothing outside fences and it holds one whole declaration -- a RUN line
through the closing line, or a lone marker line -- which is then the one the
reviewer fenced. Holding any less, or set apart from its RUN line by a
finding, it may as well be a fixture quoting the protocol, and the doubt goes
to the text it holds. A wrapping fence's fence lines go and what it held is
read as if they were not there.

Whatever the shape, the text shown holds no protocol line, so it declares
nothing a reader of declarations would take as evidence; what a run earned is
read from its own message alone, and formatting makes nothing acceptable.
Findings with nothing left -- none at all, or a declaration whose checks all
passed or wrote nothing -- read as a sentence saying so, never as the raw
message. Findings with no protocol line come back as written, so formatting
twice changes nothing.
"""
from __future__ import annotations

import re
from collections.abc import Iterable, Iterator, Mapping, Sequence
from dataclasses import dataclass
from functools import partial
from itertools import compress
from operator import ne
from types import MappingProxyType

from orchestrator.workflow.engine import (
    review_findings_fences as _markdown,
    review_verification_models as _models,
)

_NO_FINDINGS = "The reviewer stated no findings."

_NO_COMMAND = "A check naming no command"

_BLANK_STATUS = "(blank)"

# The one exit status a check passes on, as the reviewer has to write it.
_PASSED = "0"

# What may make up a blank line, a CRLF line's carriage return included.
_BLANKS = " \t\r"

_LEADING_BLANK_LINES_RE = re.compile(r"\A(?:[ \t\r]*\n)+")

_BACKTICK_RUNS_RE = re.compile("`+")

# A code span needs a run its content never repeats; a fence needs three.
_SPAN_RUN = 1
_FENCE_RUN = 3

# Each line reads as one letter, so a declaration's shape is a pattern over
# them. A protocol line's letter is the name of the group its keyword matched,
# the longer markers tried before the prefix they open on; any other line is
# blank or text, and matches the group that letter names.
_TEXT_KIND = "t"
_BLANK_KIND = "b"
_QUOTED_KIND = "q"
_HIDDEN_KIND = "p"
_RUN_KIND = "r"
_END_KIND = "n"
_MARKER_KIND = "m"
_FENCE_KIND = "f"
_COMMAND_KIND = "c"
_EXIT_KIND = "e"
# The step lines a quote holds, and its fence lines: shown nowhere and output
# respectively, they keep apart what a dropped check's quoted steps re-read.
_QUOTED_COMMAND_KIND = "C"
_QUOTED_EXIT_KIND = "E"
_QUOTE_FENCE_KIND = "y"
_KEYWORD_KINDS = MappingProxyType({
    _models._VERIFICATION_RUN_MARKER: _RUN_KIND,
    _models._VERIFICATION_END_MARKER: _END_KIND,
    _models._VERIFICATION_MARKER_PREFIX: _MARKER_KIND,
    _models._COMMAND_PREFIX: _COMMAND_KIND,
    _models._EXIT_PREFIX: _EXIT_KIND,
})
_KEYWORDS = "|".join(
    f"(?P<{kind}>{re.escape(keyword)})" for keyword, kind in _KEYWORD_KINDS.items()
)
_LINE_KIND_RE = re.compile(
    rf"[ \t]*(?:{_KEYWORDS})|(?P<{_BLANK_KIND}>[{_BLANKS}]*$)|(?P<{_TEXT_KIND}>)",
)

# Every line opening on a keyword, whatever follows it and however deep it
# sits: the contract's own lines and each near miss of them.
_PROTOCOL_LINE_RE = re.compile(rf"^[ \t]*(?:{_KEYWORDS})", re.MULTILINE)

# One declaration -- a RUN block, or the steps of one missing its RUN line, or
# a lone marker, stray closing line, or wrapping fence line -- read once the
# protocol lines a quoted fence holds are hidden. A block its RUN line opens
# and a closing line reaches before another RUN line holds everything up to
# it. Any other -- cut short, or missing the RUN line that would vouch a
# closing line below closes it -- holds runs of unbroken lines opening on a
# step line, and closed fences whole: another RUN line, a wrapping fence
# line, a blank line neither a step line nor a closed fence follows, or a text
# line right below a closed fence ends it.
_STEP_LINES = f"{_COMMAND_KIND}{_EXIT_KIND}"
_QUOTED_STEP_LINES = f"{_QUOTED_COMMAND_KIND}{_QUOTED_EXIT_KIND}"
_OUTPUT_LETTERS = f"{_TEXT_KIND}{_BLANK_KIND}{_QUOTED_KIND}{_QUOTE_FENCE_KIND}"
_QUOTE_LETTERS = f"{_QUOTED_KIND}{_QUOTE_FENCE_KIND}{_QUOTED_STEP_LINES}"
_LISTED_LETTERS = f"{_EXIT_KIND}{_OUTPUT_LETTERS}{_QUOTED_STEP_LINES}{_MARKER_KIND}{_FENCE_KIND}"
_UNBROKEN_LETTERS = f"{_STEP_LINES}{_QUOTED_STEP_LINES}{_TEXT_KIND}{_MARKER_KIND}"
_CLOSED_STEPS = f"(?<={_RUN_KIND})[{_COMMAND_KIND}{_LISTED_LETTERS}]*(?={_END_KIND})"
_CUT_SHORT_STEPS = (
    f"(?:{_BLANK_KIND}*(?:[{_STEP_LINES}][{_UNBROKEN_LETTERS}]*|[{_QUOTE_LETTERS}]+))*"
)
_DECLARATION_RE = re.compile(
    f"(?:{_RUN_KIND}|(?=[{_STEP_LINES}]))(?P<steps>{_CLOSED_STEPS}|{_CUT_SHORT_STEPS}){_END_KIND}?"
    f"|[{_MARKER_KIND}{_END_KIND}{_FENCE_KIND}]",
)

# One step of a block: a command line and every line below it up to the next
# one, or whatever the block lists above its first command line.
_STEP_RE = re.compile(f"{_COMMAND_KIND}[{_LISTED_LETTERS}]*|[{_LISTED_LETTERS}]+")

# A check's lines up to the first step line a quote among them holds, and how
# the lines from there read once a dropped check re-reads them: their step
# lines as a block's own, the quote's fence lines as wrapping, which is no
# step's output.
_UNQUOTED_STEPS_RE = re.compile(f"[^{_QUOTED_STEP_LINES}]*")
_UNQUOTED_LETTERS = MappingProxyType(str.maketrans({
    _QUOTED_COMMAND_KIND: _COMMAND_KIND,
    _QUOTED_EXIT_KIND: _EXIT_KIND,
    _QUOTE_FENCE_KIND: _FENCE_KIND,
}))

# How a code fence's lines read once it is read whole: as a quote, its step
# lines kept apart and every other protocol line it holds hidden -- its fence
# and blank lines too where it holds no text -- or as the wrapping of a
# declaration, whose blank lines are its content. What a fence sits below is read past the output lines between it
# and the protocol line above, earlier fences included. A fence is plainly a
# declaration when what it holds is one whole: a RUN line through the closing
# line, or a lone marker line, with only blank lines around.
_MARKER_KINDS = f"{_RUN_KIND}{_END_KIND}{_MARKER_KIND}"
_PROTOCOL_KINDS = f"{_MARKER_KINDS}{_STEP_LINES}"
_PROTOCOL_LETTERS = frozenset(_PROTOCOL_KINDS)
_MARKER_LETTERS = frozenset(_MARKER_KINDS)
_STEP_LETTERS = frozenset(_STEP_LINES)
_UNSPOKEN_LETTERS = f"{_TEXT_KIND}{_BLANK_KIND}{_HIDDEN_KIND}{_QUOTE_LETTERS}"
_QUOTED_STEPS = MappingProxyType({_COMMAND_KIND: _QUOTED_COMMAND_KIND, _EXIT_KIND: _QUOTED_EXIT_KIND})
_QUOTED_LETTERS = MappingProxyType(str.maketrans(
    dict.fromkeys(_MARKER_KINDS, _HIDDEN_KIND)
    | dict.fromkeys(f"{_TEXT_KIND}{_BLANK_KIND}", _QUOTED_KIND)
    | _QUOTED_STEPS,
))
_SILENT_LETTERS = MappingProxyType(str.maketrans(
    dict.fromkeys(f"{_MARKER_KINDS}{_BLANK_KIND}", _HIDDEN_KIND) | _QUOTED_STEPS,
))
_WRAPPED_LETTERS = MappingProxyType(str.maketrans(_BLANK_KIND, _TEXT_KIND))
# Indented code wrapping a declaration reads as written: with no closing line
# to end what it holds, its blank lines end a block as anywhere else.
_UNWRAPPED_LETTERS = MappingProxyType(str.maketrans({}))

# The letter a code block's fence lines read as, and the table its other lines
# are read by.
_LetterReading = tuple[str, Mapping[int, str]]
_WHOLE_DECLARATION_RE = re.compile(
    f"{_RUN_KIND}[^{_RUN_KIND}{_END_KIND}]*{_END_KIND}|{_MARKER_KIND}",
)


def _concise_findings(findings: str) -> str:
    """`findings` with no line of their declaration, or a sentence saying there are none.

    What is left is the reviewer's text around the declaration and each check
    the declaration does not show passing, one paragraph apart.
    """
    concise = "\n\n".join(chunk for chunk in _chunks(findings) if chunk)
    return concise or _NO_FINDINGS


def _chunks(findings: str) -> Iterator[str]:
    """The text around each declaration in `findings`, and the checks failing inside it.

    A protocol line a quoted fence holds is hidden before anything is read, so
    it is shown nowhere and parts nothing it sits between; a step line among
    them is kept apart, for a dropped check to re-read.
    """
    kinds = _FenceReading.of(findings).letters()
    shown = map(partial(ne, _HIDDEN_KIND), kinds)
    lines = list(compress(findings.split("\n"), shown))
    kinds = kinds.replace(_HIDDEN_KIND, "")
    kept = 0
    for declaration in _DECLARATION_RE.finditer(kinds):
        yield _said(lines, kinds, slice(kept, declaration.start()))
        if declaration.group("steps"):
            yield from _Check.failures(
                lines[slice(*declaration.span("steps"))],
                declaration.group("steps"),
            )
        kept = declaration.end()
    yield _said(lines, kinds, slice(kept, None))


def _said(lines: Sequence[str], kinds: str, part: slice) -> str:
    """The findings text of `part` of `lines`, read as `kinds`, without a step line a quote holds."""
    spoken = [kind not in _QUOTED_STEP_LINES for kind in kinds[part]]
    return _shown(compress(lines[part], spoken))


def _shown(lines: Iterable[str]) -> str:
    """The text of `lines`, without the blank lines framing it."""
    text = "\n".join(lines)
    return _LEADING_BLANK_LINES_RE.sub("", text).rstrip(f"{_BLANKS}\n")


@dataclass(frozen=True)
class _FenceReading:
    """The letter each line of one message's findings reads as, its code fences read whole.

    `kinds` is the letter each line reads as on its own; `blocks` each code
    block, a fence or indented code; `declared` whether a marker line stands
    outside all of them.

    A fence ends where Markdown ends it (`review_findings_fences`), not where
    the stricter reading the declaration readers share does, since only what
    a reader sees is shown: on a closing run at most three spaces in from its
    list item's content column, however far in its opening run sat, or with
    the item, before a line set in less than that column. A finding below is
    read as written rather than as the fence's content. Indented code reads as
    a fence with no fence lines, except that wrapping a declaration it leaves
    what it holds as written, having no closing line to end it.

    A fence holding no protocol line is a quote, so a blank line inside it ends
    no block. Below a check's command or exit line, one holding protocol lines
    is a quote too, that check's output, whatever else it holds: a failing
    test's output may quote the protocol, a fixture's nothing but. Anywhere
    else, one holding protocol lines beside other text is the findings quoting
    such output. Every protocol line a quote holds -- marker lines too -- is
    hidden, starting, closing, and passing no check, and a quote holding no
    text is hidden whole, so no empty fence is shown where it stood. Its step
    lines and fence lines read apart all the same, so a check that is dropped
    can re-read the steps it quotes as checks of their own. A fence
    wraps a declaration instead right below a RUN line, only blank lines
    between, where it lists that block's steps; outside a check's output,
    where it holds nothing but protocol, having nothing to show; and where the
    findings declare nothing outside fences and it holds one whole
    declaration, which is then the one the reviewer fenced. Holding any less,
    it may as well be a fixture quoting the protocol, and the doubt goes to
    the text it holds. A wrapping fence's fence lines read as wrapping, so a
    declaration a reviewer fenced leaves no empty fence behind and no check
    failing inside one is quoted inside it, and its blank lines are content,
    ending nothing before its closing line does. A fence opened and never
    closed is read the same way, to the end.
    """

    kinds: str
    blocks: tuple[_markdown.CodeBlock, ...]

    @classmethod
    def of(cls, findings: str) -> _FenceReading:
        """How the fences of `findings` read."""
        lines = findings.split("\n")
        kinds = "".join(_LINE_KIND_RE.match(line).lastgroup for line in lines)
        return cls(kinds, tuple(_markdown.markdown_code_blocks(lines)))

    def letters(self) -> str:
        """The letter each line of the findings reads as, every fence read whole."""
        letters = self.kinds
        for block in self.blocks:
            letters = self._read(letters, block)
        return letters

    @property
    def declared(self) -> bool:
        """Whether a marker line stands outside all the fences.

        A fence's own lines are text, so each fence goes whole, the last first
        to leave the lines of those above where they stand.
        """
        outside = self.kinds
        for block in reversed(self.blocks):
            around = (outside[:block.start], outside[block.end:])
            outside = "".join(around)
        return not _MARKER_LETTERS.isdisjoint(outside)

    def _read(self, letters: str, block: _markdown.CodeBlock) -> str:
        """`letters` with the code `block` read whole, its fence lines and what it holds alike."""
        held = letters[block.held_start:block.held_end]
        above = letters[:block.start]
        kind, table = self._reading(held, above, block)
        return "".join((
            above,
            kind * block.opening,
            held.translate(table),
            kind * block.closing,
            letters[block.end:],
        ))

    def _reading(self, held: str, above: str, block: _markdown.CodeBlock) -> _LetterReading:
        """The letter `block`'s fence lines read as, and the table what it holds is read by."""
        if self._wraps(held, above):
            return _FENCE_KIND, _WRAPPED_LETTERS if block.opening else _UNWRAPPED_LETTERS
        if _TEXT_KIND in held or _PROTOCOL_LETTERS.isdisjoint(held):
            return _QUOTE_FENCE_KIND, _QUOTED_LETTERS
        return _HIDDEN_KIND, _SILENT_LETTERS

    def _wraps(self, held: str, above: str) -> bool:
        """Whether a fence holding lines read as `held`, below lines read as `above`, wraps a declaration.

        Only blank lines may part a fence listing a block's steps from the RUN
        line above it: a finding between them ends a block with no closing
        line, and below one the fence is the findings' own. A check's output
        reaches past the text it holds to the fence, which can only make the
        fence a quote, even one holding protocol lines alone: a failing test
        may print a fixture that is nothing else, and the diagnostic below it
        stays that check's. Where the check is dropped instead, the steps the
        quote holds are re-read then (`_Check.shown`).
        """
        kinds = frozenset(held)
        if kinds.isdisjoint(_PROTOCOL_LETTERS):
            return False
        if above.rstrip(_BLANK_KIND).endswith(_RUN_KIND):
            return True
        if above.rstrip(_UNSPOKEN_LETTERS)[-1:] in _STEP_LETTERS:
            return False
        if _TEXT_KIND not in kinds:
            return True
        return not self.declared and _WHOLE_DECLARATION_RE.fullmatch(held.strip(_BLANK_KIND)) is not None


@dataclass(frozen=True)
class _Check:
    """One step of a declaration as a human reads it, however out of shape.

    `command` is what follows its command line, or empty where it has none;
    `statuses` what follows each of its exit lines, blank or not; `output` the
    other lines below them, marker, wrapping fence, and quoted step lines
    aside. `quoted` is its lines from the first step line a quote among them
    holds, and `quoted_kinds` how they read as a block's own steps.
    """

    command: str
    statuses: tuple[str, ...]
    output: str
    quoted: tuple[str, ...]
    quoted_kinds: str

    @classmethod
    def failures(cls, lines: Sequence[str], kinds: str) -> Iterator[str]:
        """What each check the `lines` of a block list leaves to show, read by their letters `kinds`."""
        for step in _STEP_RE.finditer(kinds):
            yield from cls.read(lines, step).shown()

    @classmethod
    def read(cls, lines: Sequence[str], step: re.Match[str]) -> _Check:
        """The check `step`, a match over the letters of a block's `lines`, lists."""
        written = lines[step.start():step.end()]
        listed = tuple(zip(written, step.group(), strict=True))
        start = _UNQUOTED_STEPS_RE.match(step.group()).end()
        return cls(
            "".join(cls._keyed_values(listed, _COMMAND_KIND)),
            tuple(cls._keyed_values(listed, _EXIT_KIND)),
            _shown(line for line, kind in listed if kind in _OUTPUT_LETTERS),
            tuple(written[start:]),
            step.group()[start:].translate(_UNQUOTED_LETTERS),
        )

    def shown(self) -> Iterator[str]:
        """The check as a developer needs it: its command, how it ended, and
        the output it quoted. Once it passed, or wrote neither an exit status
        nor output -- a command inventory says nothing to act on -- it shows
        nothing of its own, and its output goes; but a fence in that output
        may list the block's next checks rather than quote this one's
        output, so each step it quotes is read as a check, and one not shown
        passing is shown."""
        said = any(self.statuses) or bool(self.output)
        if self.statuses == (_PASSED,) or not said:
            yield from self.failures(self.quoted, self.quoted_kinds)
            return
        sentence = f"{self._subject()} {self._ending()}"
        if not self.output:
            yield f"{sentence}."
            return
        fence = self._backticks(self.output, _FENCE_RUN)
        yield f"{sentence}:\n\n{fence}\n{self.output}\n{fence}"

    def _subject(self) -> str:
        """The command as a code span its own backticks cannot close."""
        if not self.command:
            return _NO_COMMAND
        run = self._backticks(self.command, _SPAN_RUN)
        touching = self.command.startswith("`") or self.command.endswith("`")
        padding = " " if touching else ""
        return f"{run}{padding}{self.command}{padding}{run}"

    def _ending(self) -> str:
        if not self.statuses:
            return "reported no exit status"
        if self.statuses == ("",):
            return "reported a blank exit status"
        if len(self.statuses) == 1:
            return f"exited with status {self.statuses[0]}"
        statuses = ", ".join(status or _BLANK_STATUS for status in self.statuses)
        return f"reported the exit statuses {statuses}"

    @classmethod
    def _keyed_values(cls, listed: Iterable[tuple[str, str]], kind: str) -> Iterator[str]:
        """What follows the keyword on each of the `listed` lines reading as `kind`."""
        for line, letter in listed:
            if letter == kind:
                yield _PROTOCOL_LINE_RE.sub("", line, count=1).strip(_BLANKS)

    @classmethod
    def _backticks(cls, text: str, shortest: int) -> str:
        """A backtick run at least `shortest` long that is longer than any in `text`."""
        longest = max(map(len, _BACKTICK_RUNS_RE.findall(text)), default=0)
        return "`" * max(shortest, longest + 1)
