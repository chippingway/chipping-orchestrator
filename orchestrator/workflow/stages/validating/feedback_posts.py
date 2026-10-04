# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""A change request's reviewer-feedback post: the words it is posted in, and the post as a replay shows it.

A change request's handoff (`review_handoffs`) posts the reviewer's feedback on
the pull request (`requested_changes._post_reviewer_feedback`) in the words
written here (`posted`): a line naming the review and its round, then the
feedback, the hidden marker every post of this orchestrator closes on appended
below. The id that post lands as is the anchor a failed run's
`/orchestrator continue` replays (`fixing/continue_command`), quoting the post
to a fresh developer.

A post made before findings were formatted quotes the reviewer's verification
declaration raw, and it stays on the pull request as it was posted. So the
replay quotes it as shown (`ShownPost`): the same comment -- its id, author,
and every other attribute its own, so the batch it rides sorts, deduplicates,
and settles exactly as over the comment itself -- whose body has the findings
formatted (`review_findings`), each check not shown passing kept as its
diagnostic, between the line naming the review and the marker, both kept as
posted. Findings formatting leaves nothing of read as the sentence saying so,
as a live round's would. A post made since quotes its findings concise
already, and formatting them again changes nothing; a body of any other shape
is read as findings whole.
"""
from __future__ import annotations

import re

from orchestrator import config
from orchestrator.workflow.engine import comments as _comments, review_findings as _findings

# A post as `posted` writes it and the post appends its marker: the line naming
# the review, the findings, and the marker -- the first and last each optional,
# so any body reads as findings at least.
_POST_RE = re.compile(
    "(?P<head>:eyes: [^\n]* requested changes:\n\n)?(?P<findings>.*?)"
    f"(?P<marker>\n\n{re.escape(_comments._ORCH_COMMENT_MARKER)})?",
    re.DOTALL,
)


def posted(round_n: int, feedback: str) -> str:
    """The words the reviewer's `feedback` is posted in, for the review round `round_n` counted from 0."""
    round_display = round_n + 1
    return (
        f":eyes: {config.REVIEW_AGENT} review "
        f"(round {round_display}/{config.MAX_REVIEW_ROUNDS}) requested changes:\n\n"
        f"{feedback}"
    )


class ShownPost:
    """A reviewer-feedback comment as a replay quotes it: its findings formatted, everything else the comment's own."""

    def __init__(self, comment: object) -> None:
        self._comment = comment
        self.body = _shown(getattr(comment, "body", None) or "")

    def __getattr__(self, name: str) -> object:
        return getattr(self._comment, name)


def _shown(body: str) -> str:
    """`body` with the findings it quotes formatted, the line naming the review and the marker kept as posted."""
    head, findings, marker = _POST_RE.fullmatch(body).group("head", "findings", "marker")
    concise = _findings._concise_findings(findings)
    return "".join((head or "", concise, marker or ""))
