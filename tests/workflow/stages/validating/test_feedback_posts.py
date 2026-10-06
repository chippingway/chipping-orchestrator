# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""A reviewer-feedback post as a replay shows it: its findings concise, everything else as it was posted.

The post is written in the words `feedback_posts.posted` composes, the receipt
naming its request below them and the hidden marker appended as every post of
this orchestrator's is, and read back by the replay of a `/orchestrator
continue` through `feedback_posts.ShownPost`.
"""
from __future__ import annotations

import hashlib
import unittest
from datetime import datetime

from orchestrator.workflow.engine import comments as _comments
from orchestrator.workflow.stages.validating import feedback_posts as _feedback_posts
from tests.support.fakes import FakeComment, FakeUser
from tests.workflow.stages.validating import raw_feedback_test_support as _raw, review_verdict_test_support as _world

_POSTED_ID = 4_242

_POSTED_AT = datetime.fromisoformat("2026-10-04T00:00:00+00:00")

# The receipt below a post's findings naming the request it was posted for.
_RECEIPT = _feedback_posts._RECEIPT.format(digest=hashlib.sha256(b"a change request").hexdigest())


def _as_posted(findings: str) -> str:
    """The body of a feedback post quoting `findings` in the review's first round, as it lands on the pull request."""
    return _comments._with_orch_marker(_feedback_posts.posted(0, findings))


def _as_receipted(findings: str) -> str:
    """The body of that post as posted now: its receipt below the findings, above the marker."""
    return _comments._with_orch_marker(f"{_feedback_posts.posted(0, findings)}\n\n{_RECEIPT}")


# Each body a post reads back as, and that post as a replay shows it: one made
# before findings were formatted, its declaration raw -- a failed run's kept
# as its diagnostic, a passing run declared and nothing else read as no
# findings -- the first receipted as well, one made since, concise already,
# and a body of no shape this route posts, read as findings whole.
_SHOWN = (
    ("a failed run posted raw", _as_posted(_raw.RAW_FAILURE), _as_posted(_world.CONCISE_FAILURE)),
    ("a failed run posted raw and receipted", _as_receipted(_raw.RAW_FAILURE), _as_receipted(_world.CONCISE_FAILURE)),
    (
        "a declaration posted raw alone",
        _as_posted(_raw.as_persisted(_world.DECLARED_ALONE)),
        _as_posted(_world.NO_FINDINGS),
    ),
    ("findings posted concise", _as_posted(_world.CONCISE_FAILURE), _as_posted(_world.CONCISE_FAILURE)),
    ("a body of no post's shape", _raw.RAW_FAILURE, _world.CONCISE_FAILURE),
)


class ShownPostTest(unittest.TestCase):
    """A replay quotes the post's findings concise, and the comment is otherwise the one posted."""

    def test_the_findings_are_shown_concise(self) -> None:
        # The line naming the review, the receipt, and the marker stay as
        # posted around the findings, which are formatted as a live round's are.
        for name, posted, shown in _SHOWN:
            with self.subTest(name):
                self.assertEqual(_feedback_posts.ShownPost(FakeComment(_POSTED_ID, posted)).body, shown)

    def test_the_rest_is_the_comment_s_own(self) -> None:
        # The batch a replay quotes it in is sorted, deduplicated, and settled
        # by what the comment itself carries, and the comment keeps its words.
        comment = FakeComment(_POSTED_ID, _as_posted(_raw.RAW_FAILURE), FakeUser("orchestrator"), _POSTED_AT)

        shown = _feedback_posts.ShownPost(comment)

        self.assertEqual(
            (shown.id, shown.user, shown.created_at, comment.body),
            (_POSTED_ID, comment.user, comment.created_at, _as_posted(_raw.RAW_FAILURE)),
        )


if __name__ == "__main__":
    unittest.main()
