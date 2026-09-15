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
