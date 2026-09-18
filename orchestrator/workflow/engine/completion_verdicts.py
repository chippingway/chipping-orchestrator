# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The two markers a terminal agent closes its own stage with: the reviewer's
`VERDICT:` line, and the documentation run's `DOCS: NO_CHANGE`.

Both are read out of the agent's last message, both take the LAST match -- so
a marker quoted from the contract the prompt taught earlier in a long message
loses to the concluding line -- and both answer `unknown` to anything short of
the marker they promise. Prose that merely sounds like an outcome ("no changes
needed") is not the agent committing to one, so the caller parks a human in
rather than recording a decision nobody made.

Where the two differ is how much shape the marker must have, and that follows
from what each one says. A review verdict names its own outcome, so an inline
`VERDICT: APPROVED` is still a statement about the diff. The documentation
marker only says there was nothing to write, which the sentence after it can
take back -- so it counts as the FINAL line and nothing else: alone on that
line, unpunctuated, with the message ending there. The documentation stage's
other outcome, that docs WERE updated, is not read here at all; it is a fresh
commit on the branch, which the stage handler sees.

Each parser also returns the slice above its marker, because that body is the
part a human is shown -- the reviewer's requested changes quoted onto the pull
request, the one line justifying a no-change -- while the marker itself is
vocabulary this module owns and the thread never needs.

What a reviewer declares about verification is not read here. It has markers
of its own on `review_verification`, which asks this module's review pattern
only to refuse a declaration holding a verdict, so a verdict is never kept as
evidence.
"""
from __future__ import annotations

import re

_VERDICT_UNKNOWN = "unknown"

_VERDICT_RE = re.compile(
    r"VERDICT:\s*(APPROVED|CHANGES_REQUESTED)\b",
    re.IGNORECASE,
)

_DOC_VERDICT_RE = re.compile(
    r"(?:^|\n)[ \t]*DOCS:[ \t]*NO_CHANGE[ \t]*\r?\n?\s*\Z",
    re.IGNORECASE,
)


def _parse_review_verdict(last_message: str) -> tuple[str, str]:
    """Find the last 'VERDICT: APPROVED|CHANGES_REQUESTED' marker.

    Returns (verdict, body_above_marker). verdict is one of "approved",
    "changes_requested", or "unknown" (no marker found). body_above_marker is
    the slice of last_message before the marker, used as PR-comment text for
    the changes-requested case.
    """
    if not last_message:
        return _VERDICT_UNKNOWN, ""
    matches = list(_VERDICT_RE.finditer(last_message))
    if not matches:
        return _VERDICT_UNKNOWN, last_message
    last = matches[-1]
    word = last.group(1).upper()
    verdict = "approved" if word == "APPROVED" else "changes_requested"
    body = last_message[: last.start()].rstrip()
    return verdict, body


def _parse_documentation_verdict(last_message: str) -> tuple[str, str]:
    """Find a final 'DOCS: NO_CHANGE' marker in a documentation-stage message.

    Returns (verdict, body_above_marker):
      * `("no_change", body)` -- the agent emitted the explicit marker
        AS THE FINAL LINE (alone on its line, with only optional
        whitespace through end of string), confirming the branch diff
        requires no documentation update. `body` is the slice above
        the marker, suitable for surfacing the agent's one-line
        justification on the issue.
      * `("unknown", last_message)` -- no valid final marker present.
        The caller MUST park rather than treat this as success;
        deliberately rejected variants include:
          - ambiguous prose like "no changes needed";
          - inline references such as
              "I cannot conclude DOCS: NO_CHANGE because ...";
          - non-final markers followed by further content, e.g.
              "DOCS: NO_CHANGE\nBut I have a question.";
          - markers with trailing punctuation like "DOCS: NO_CHANGE.".

    The `"updated"` outcome (docs were modified) is signalled by a fresh
    commit on the branch (any subject; the prompt mandates no `docs:`
    prefix) and is detected at the stage handler level rather than
    here -- this parser only resolves the no-commit branch.
    """
    if not last_message:
        return _VERDICT_UNKNOWN, ""
    match = _DOC_VERDICT_RE.search(last_message)
    if match is None:
        return _VERDICT_UNKNOWN, last_message
    body = last_message[: match.start()].rstrip()
    return "no_change", body
