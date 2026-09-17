# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The references a published commit subject is left ending in.

A rebase merge copies a branch's commits onto the base verbatim, so the
trailing ` (#N)` references on a subject are the only links a landed commit
keeps back to what produced it -- and exactly one of them belongs there. The
pull request is what a landed commit is read back through; the tracked issue
is linked from that request's own body, so an issue number a developer copied
out of recent history is the same link spelled from the wrong side, and a
subject carrying both names one thing twice. Deciding it in one owner holds
every publisher to the same answer for which references a subject may keep,
so a retried or repeated publication cannot strip an issue on one road and
carry it on another, or double a reference on either.

Only the trailing RUN of references is read. A number inside the subject's
text is prose the author wrote, and a reference to anything other than the
tracked issue or the current pull request is somebody else's link -- both are
kept exactly where they stand, ahead of the single reference this owner ends
the line in.

``titles`` beside this owner decides WHICH subject gets written and never
adds a reference: a pull request's title is picked before the request has a
number. The tracked-issue removal is exposed here on its own for that
selection, so a reused developer subject can shed the issue number without
gaining a reference that does not exist yet. Nothing removes that number
implicitly either: a publisher with no pull request to name -- the install
with the reference switched off -- normalizes nothing, a publisher that names
no tracked issue strips none, and a caller that wants the issue gone asks for
it by name.

Whether a subject is still OWED a rewrite answers here as well, because it is
the same rule read the other way round: a publisher that decided it for
itself could disagree with the normalization about what "already published"
means, and would then either double a reference or leave an issue number on a
subject it just declined to rewrite. This owner reads no git, no GitHub, and
no configuration.
"""
from __future__ import annotations

import re

# The whole trailing run of references, taken as one: a subject ends in as
# many as its writers appended, and only the run at the very end is the
# orchestrator's to rewrite. The separating whitespace is required, so a
# `subject(#12)` written without it is text rather than a reference.
_TRAILING_REFERENCES_RE = re.compile(r"(?:\s+\(#\d+\))+$")

# The number inside one reference of that run.
_REFERENCE_NUMBER_RE = re.compile(r"\(#(\d+)\)")


def _split_trailing_references(subject: str) -> tuple[str, tuple[int, ...]]:
    """`subject` split into the text before its trailing references and them.

    Trailing whitespace goes with the references rather than with the text,
    so every caller rebuilds the line from a stem that ends in the author's
    own last character and puts back exactly one space before each reference
    it keeps.
    """
    stem = (subject or "").rstrip()
    run = _TRAILING_REFERENCES_RE.search(stem)
    if run is None:
        return stem, ()
    numbers = _REFERENCE_NUMBER_RE.findall(run.group())
    references = tuple(int(number) for number in numbers)
    return stem[:run.start()], references


def _subject_ending_in_references(stem: str, references: list[int]) -> str:
    """`stem` ended in `references`, one space before each.

    The one place the spelling of a reference is written, so a line rebuilt
    after a removal is spaced exactly like one the orchestrator appended to.
    """
    return "".join((stem, *(f" (#{number})" for number in references)))


def _subject_without_issue_reference(
    subject: str, issue_number: int | None,
) -> str:
    """`subject` with the tracked issue dropped from its trailing references.

    The operation title selection borrows, where there is no pull request to
    name yet: a developer subject that copied the issue number out of recent
    history loses it, and nothing is appended in its place. A reference to any
    other number is left where it stands, and an issue number inside the
    subject's own text is prose rather than a reference. No tracked issue at
    all removes nothing, so a caller without one gets its subject back with
    only trailing whitespace dropped.
    """
    stem, references = _split_trailing_references(subject)
    return _subject_ending_in_references(
        stem, [number for number in references if number != issue_number],
    )


def _subject_with_pr_reference(
    subject: str, pr_number: int, issue_number: int | None = None,
) -> str:
    """`subject` normalized to end in exactly one ` (#<pr_number>)`.

    The tracked issue's reference is dropped wherever it sits in the trailing
    run -- alone, or ahead of a pull-request reference an earlier publication
    already appended, which is the `subject (#issue) (#pr)` a developer commit
    and the orchestrator each contributed half of. Every other reference is
    somebody else's link and stays in the order it was written, ahead of this
    pull request's, and references to this pull request itself collapse to the
    single one the line ends in, so a second approval round, a retried tick, or
    a recovered commit cannot read `feat: x (#12) (#12)`.

    Reapplying this to its own result changes nothing, which is what lets the
    question below be asked by comparison. Trailing whitespace is dropped
    first so the reference sits one space after the text. Only the subject line
    comes back -- no body, no trailer, and never a closing keyword, since the
    number names a pull request and a keyword would have GitHub close an issue
    by it.
    """
    stem, references = _split_trailing_references(subject)
    unrelated = [
        number for number in references
        if number not in {issue_number, pr_number}
    ]
    return _subject_ending_in_references(stem, [*unrelated, pr_number])


def _subject_owes_the_reference(
    subject: str, pr_number: int | None, issue_number: int | None = None,
) -> bool:
    """Whether normalizing `subject` would change it at all.

    The question a publisher deciding whether to rewrite a commit asks, and it
    is answered by the normalization above rather than by a pattern of its
    own: that normalization is idempotent, so a subject it hands back
    unchanged is one already ending in exactly this pull request's reference
    and carrying no tracked-issue reference behind it, and any other answer is
    a subject still owed the rewrite. Asked any other way, what counts as
    already published could drift from what a rewrite would write -- and a
    publisher would double a reference, decline to add a missing one, or leave
    an issue number on a subject it just called finished.

    False for no pull request at all: there is no reference to owe, nothing is
    stripped on the way to one, and a caller weighing a rewrite against it has
    nothing to weigh.
    """
    if pr_number is None:
        return False
    written = (subject or "").rstrip()
    normalized = _subject_with_pr_reference(written, pr_number, issue_number)
    return normalized != written
