# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The pull-request reference a published commit subject ends in.

A rebase merge copies a branch's commits onto the base verbatim, so the
` (#N)` suffix on a subject is the only link a landed commit keeps back to the
pull request it came from. Spelling it in one owner holds every publisher that
appends it to the same rule for when a subject already carries it, so a
retried or repeated publication cannot double it on one road and not another.

``titles`` beside this owner decides WHICH subject gets written and never
consults this one: a pull request's title is picked before the request has a
number, so the reference belongs only to the commits published onto it. This
owner reads no git, no GitHub, and no configuration.

Whether a subject is still OWED the reference answers here as well, because
it is the same rule read the other way round: a publisher that decided it for
itself could disagree with the formatter about what "already referenced"
means, and then either double a reference or leave a missing one alone.
"""
from __future__ import annotations


def _subject_with_pr_reference(subject: str, pr_number: int) -> str:
    """`subject` ending in exactly one ` (#<pr_number>)` reference.

    A subject already ending in the same reference is returned unchanged,
    which keeps a second approval round, a retried tick, or a recovered commit
    from reading `feat: x (#12) (#12)`. A reference to any other number is
    ordinary subject text and gets the current one appended after it.
    Trailing whitespace is dropped first so the reference sits one space after
    the text. Only the subject line comes back -- no body, no trailer, and
    never a closing keyword, since the number names a pull request and a
    keyword would have GitHub close an issue by it.
    """
    trimmed = (subject or "").rstrip()
    suffix = f" (#{pr_number})"
    if trimmed.endswith(suffix):
        return trimmed
    return f"{trimmed}{suffix}"


def _subject_owes_the_reference(subject: str, pr_number: int | None) -> bool:
    """Whether writing `pr_number`'s reference would change `subject` at all.

    The question a publisher deciding whether to rewrite a commit asks, and it
    is answered by the formatter above rather than by a pattern of its own:
    that formatter is idempotent, so a subject it hands back unchanged is one
    already ending in exactly this pull request's reference and any other
    answer is a subject the reference is still owed. Asked any other way, what
    counts as already referenced could drift from what a rewrite would write
    -- and a publisher would either double a reference or decline to add a
    missing one.

    False for no pull request at all: there is no reference to owe, and a
    caller weighing a rewrite against it has nothing to weigh.
    """
    if pr_number is None:
        return False
    written = (subject or "").rstrip()
    return _subject_with_pr_reference(written, pr_number) != written
