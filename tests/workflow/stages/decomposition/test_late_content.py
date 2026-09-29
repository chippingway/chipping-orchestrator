# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What the two late-local fingerprints count, and what they say changed.

The issue-wide requirements hash each reading freezes beside them is here too,
since it is taken off the same read and differs only in whose filter counts.
"""
from __future__ import annotations

import unittest
from unittest.mock import MagicMock, PropertyMock, patch

from orchestrator import config
from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.engine import (
    comments as _engine_comments,
    content_hash as _content_hash,
)
from orchestrator.workflow.late_split import formats as _formats
from orchestrator.workflow.stages.decomposition import (
    late_content as _late_content,
)
from tests.support.fakes import make_issue
from tests.workflow.stages.decomposition import (
    late_content_replies as _content_replies,
    late_content_support as _support,
)
from tests.workflow.stages.decomposition.late_test_support import (
    CANDIDATE_SHA,
    LATE_ISSUE_NUMBER,
    late_generation,
)

ALLOWED_AUTHORS = "ALLOWED_ISSUE_AUTHORS"

BOT_LOGIN = "dependabot"

BOT_TYPE = "Bot"

TRACKED_IDS = "orchestrator_comment_ids"

EMPTY_BODY = "   \n "

ADD_RUNS_COMMAND = "/orchestrator add-agent-runs 2"


def _issue(**issue_fields):
    """One issue carrying the standard late title and body."""
    return make_issue(
        LATE_ISSUE_NUMBER,
        title=issue_fields.pop("title", _support.ISSUE_TITLE),
        body=issue_fields.pop("body", _support.ISSUE_BODY),
        **issue_fields,
    )


def _signal(issue, generation, state=None):
    """Read one content signal against an issue and a recorded generation."""
    return _late_content._read_content_signal(
        issue, state or PinnedState(data={}), generation,
    )


def _frozen(comments=()):
    """An issue and the generation baselined on exactly what it says now."""
    issue = _issue(comments=list(comments))
    return issue, _support.baselined(late_generation(), issue)


class FingerprintTest(unittest.TestCase):
    """What a fingerprint is taken over, and what moves it."""

    def test_digests_are_whole_sha256_digests(self) -> None:
        # The pinned reader accepts a fingerprint only at its exact digest
        # length, so a value this owner produced has to satisfy that reader or
        # it reads back absent and every later tick re-baselines.
        signal = _signal(_issue(comments=[_content_replies.guidance_comment()]), late_generation())
        for digest in (
            signal.fingerprint.title_body_hash,
            signal.fingerprint.comment_hash,
        ):
            with self.subTest(digest=digest):
                self.assertTrue(
                    _formats.is_hex_of(digest, _formats.DIGEST_LENGTHS),
                )

    def test_the_digested_parts_cannot_collide(self) -> None:
        # Without a separator no body can contain, a character moved across a
        # part boundary would leave the fingerprint unchanged -- and an edit of
        # exactly that shape invisible.
        joined = _signal(_issue(title="ab", body=""), late_generation())
        split = _signal(_issue(title="a", body="b"), late_generation())
        self.assertNotEqual(
            joined.fingerprint.title_body_hash,
            split.fingerprint.title_body_hash,
        )

    def test_comment_order_is_part_of_the_digest(self) -> None:
        posted = [
            _content_replies.guidance_comment(),
            _content_replies.human_comment(_support.SECOND_ID, _support.OTHER_GUIDANCE),
        ]
        forward = _signal(_issue(comments=posted), late_generation())
        backward = _signal(
            _issue(comments=list(reversed(posted))), late_generation(),
        )
        self.assertNotEqual(
            forward.fingerprint.comment_hash, backward.fingerprint.comment_hash,
        )


class CountedThreadTest(unittest.TestCase):
    """Whose comments one reading counts, late-locally and issue-wide.

    The issue-wide hash is the one a consumer would record as the baseline of
    what it handled, which the global drift check then compares against. So it
    has to be that check's own hash, under that check's own filter, of exactly
    the thread this reading saw.
    """

    def test_only_trusted_human_comments_count(self) -> None:
        # Each of these would otherwise shift a digest or arrive as guidance
        # on a tick where the human's requirements did not move: an outsider
        # on a public repo, a third-party bot posting structurally, and the
        # orchestrator's own comment carrying its marker.
        alone = _signal(_issue(comments=[_content_replies.guidance_comment()]), late_generation())
        noisy = _issue(comments=[
            _content_replies.guidance_comment(),
            _content_replies.human_comment(_support.SECOND_ID, "drive-by", login=_support.OUTSIDER),
            _content_replies.human_comment(
                _support.SECOND_ID + 1, "weekly bump",
                login=BOT_LOGIN, user_type=BOT_TYPE,
            ),
            _content_replies.human_comment(
                _support.SECOND_ID + 2,
                _engine_comments._with_orch_marker(":robot: parked"),
            ),
        ])

        with patch.object(config, ALLOWED_AUTHORS, (_content_replies.HUMAN,)):
            signal = _signal(noisy, late_generation())

        self.assertEqual(
            signal.fingerprint.comment_hash, alone.fingerprint.comment_hash,
        )
        self.assertEqual(signal.requirements_hash, alone.requirements_hash)
        self.assertEqual(signal.fingerprint.comment_watermark_id, _content_replies.GUIDANCE_ID)
        self.assertEqual([quoted.id for quoted in signal.guidance], [_content_replies.GUIDANCE_ID])

    def test_an_unnamed_comment_is_dropped_late_only(self) -> None:
        # The watermark is the only thing that ever consumes a comment, so one
        # it cannot name would arrive as fresh guidance on every tick forever.
        # That reason is the late fingerprint's alone: the global filter counts
        # the comment, so an issue-wide hash that skipped it would read as
        # drift to the very check it was recorded for.
        unnamed = _content_replies.guidance_comment()
        unnamed.id = None
        issue = _issue(comments=[unnamed])

        signal = _signal(issue, late_generation())

        self.assertEqual(signal.guidance, ())
        self.assertIsNone(signal.fingerprint.comment_watermark_id)
        self.assertEqual(
            signal.requirements_hash,
            _content_hash._compute_user_content_hash(issue, set()),
        )
        self.assertNotEqual(
            signal.requirements_hash,
            _signal(_issue(), late_generation()).requirements_hash,
        )

    def test_orchestrator_ids_come_from_the_state(self) -> None:
        # A legacy comment posted before the marker existed is filtered by id,
        # which lives on the pinned state this reader is handed.
        issue = _issue(comments=[_content_replies.human_comment(_content_replies.GUIDANCE_ID, ":robot: picked up")])
        tracked = PinnedState(data={TRACKED_IDS: [_content_replies.GUIDANCE_ID]})

        hidden = _signal(issue, late_generation(), tracked)

        self.assertEqual(hidden.guidance, ())
        self.assertEqual(
            hidden.requirements_hash,
            _signal(_issue(), late_generation()).requirements_hash,
        )
        self.assertEqual(len(_signal(issue, late_generation()).guidance), 1)

    def test_issue_wide_hash_uses_the_global_filter(self) -> None:
        # Trusted guidance moves it. A whole-comment operator command does not,
        # though the late digest beside it counts that command, since there a
        # command edited after the fact is exactly what it exists to catch. And
        # a command written beside guidance is guidance, for the same reason
        # it is to the drift check.
        plain = _signal(_issue(), late_generation())
        for body, counted in (
            (_content_replies.GUIDANCE_BODY, True),
            (_support.CONTINUE_WITH_GUIDANCE, True),
            (f"{_content_replies.authorization()}\n\n{_support.OTHER_GUIDANCE}", True),
            (f"{ADD_RUNS_COMMAND}\n\n{_support.OTHER_GUIDANCE}", True),
            (_support.BARE_CONTINUE, False),
            (_content_replies.authorization(), False),
            (ADD_RUNS_COMMAND, False),
        ):
            with self.subTest(comment=body):
                issue = _issue(comments=[
                    _content_replies.human_comment(_content_replies.GUIDANCE_ID, body),
                ])

                signal = _signal(issue, late_generation())

                self.assertEqual(
                    signal.requirements_hash,
                    _content_hash._compute_user_content_hash(issue, set()),
                )
                self.assertEqual(
                    signal.requirements_hash != plain.requirements_hash, counted,
                )
                self.assertNotEqual(
                    signal.fingerprint.comment_hash, plain.fingerprint.comment_hash,
                )

    def test_nothing_after_the_read_is_counted(self) -> None:
        # A body edit landing just after the body was read, and a reply just
        # after the thread was, are content nothing consumed. Folded into the
        # issue-wide hash a consumer records as handled, either would never
        # reach the drift check that owes the next agent it; folded into one
        # digest and not the other, the signal would describe two issues. So
        # each is read once and every digest comes off that one reading --
        # while any read after it is handed the edit and the reply.
        issue = _issue(comments=[_content_replies.guidance_comment()])
        untouched = _signal(issue, late_generation())
        reads = MagicMock(side_effect=[list(issue.comments), issue.comments])
        _content_replies.reply(issue, _support.OTHER_GUIDANCE)
        body = PropertyMock(side_effect=[issue.body, _support.EDITED_BODY])

        with patch.object(issue, "get_comments", reads), \
                patch.object(type(issue), "body", body):
            signal = _signal(issue, late_generation())
        issue.body = _support.EDITED_BODY

        self.assertEqual((reads.call_count, body.call_count), (1, 1))
        self.assertEqual(
            (signal.fingerprint, signal.requirements_hash),
            (untouched.fingerprint, untouched.requirements_hash),
        )
        self.assertNotEqual(
            signal.requirements_hash,
            _content_hash._compute_user_content_hash(issue, set()),
        )


class DriftReadingTest(unittest.TestCase):
    """What a baselined generation reports about content that moved."""

    def test_an_unbaselined_record_has_no_baseline(self) -> None:
        # Both drift flags are True against absent digests, so the flag that
        # says there was nothing to compare is what keeps the first tick of
        # every late adjudication from parking as a scope edit.
        signal = _signal(_issue(), late_generation())

        self.assertFalse(signal.baselined)
        self.assertTrue(signal.drifted)

    def test_its_own_content_reads_unchanged(self) -> None:
        issue, generation = _frozen([_content_replies.guidance_comment()])

        signal = _signal(issue, generation)

        self.assertTrue(signal.baselined)
        self.assertFalse(signal.drifted)
        self.assertEqual(signal.guidance, ())
        self.assertFalse(signal.bare_continue)

    def test_a_title_or_body_edit_is_drift(self) -> None:
        for field, edited in (("title", "rewritten"), ("body", "rewritten")):
            with self.subTest(field=field):
                issue, generation = _frozen()
                setattr(issue, field, edited)

                signal = _signal(issue, generation)

                self.assertTrue(signal.title_body_drifted)
                self.assertFalse(signal.conversation_drifted)

    def test_a_rewritten_counted_comment_is_drift(self) -> None:
        # It moves no comment id at all, so the watermark cannot see it and
        # there is no new comment to read the change out of -- which is why
        # the counted prefix is digested rather than trusted to the watermark.
        counted = _content_replies.guidance_comment()
        issue, generation = _frozen([counted])
        counted.body = _support.OTHER_GUIDANCE

        signal = _signal(issue, generation)

        self.assertTrue(signal.conversation_drifted)
        self.assertFalse(signal.title_body_drifted)
        self.assertEqual(signal.guidance, ())

    def test_a_new_trusted_comment_is_guidance(self) -> None:
        issue, generation = _frozen()
        issue.comments.append(_content_replies.guidance_comment())

        signal = _signal(issue, generation)

        self.assertFalse(signal.drifted)
        self.assertEqual(
            [quoted.body for quoted in signal.guidance], [_content_replies.GUIDANCE_BODY],
        )
        self.assertEqual(signal.fingerprint.comment_watermark_id, _content_replies.GUIDANCE_ID)

    def test_the_watermark_never_falls_back(self) -> None:
        # A deleted comment must not lower it: everything between the new
        # maximum and the old one has already been read and answered.
        deleted = _content_replies.human_comment(_support.SECOND_ID, _support.OTHER_GUIDANCE)
        issue, generation = _frozen([_content_replies.guidance_comment(), deleted])
        issue.comments.remove(deleted)

        signal = _signal(issue, generation)

        self.assertEqual(signal.fingerprint.comment_watermark_id, _support.SECOND_ID)
        self.assertEqual(signal.guidance, ())


class ReportedClassificationTest(unittest.TestCase):
    """What a reply this reading counted as fresh arrives on the signal as.

    Which comment is which is the `late_content_replies` owner's question and
    is asserted against it. What is pinned here is that all of its answers
    reach the signal off one walk of the thread, so an operator control is
    never handed to a developer as work and the one a park is waiting for
    arrives beside the guidance rather than instead of it.
    """

    def test_a_fresh_comment_arrives_under_what_it_is(self) -> None:
        for body, classified in (
            (_support.BARE_CONTINUE, (0, True, None)),
            (_support.CONTINUE_WITH_GUIDANCE, (1, False, None)),
            (EMPTY_BODY, (0, False, None)),
            (_content_replies.authorization(), (0, False, CANDIDATE_SHA)),
        ):
            with self.subTest(comment=body):
                issue, generation = _frozen()
                issue.comments.append(_content_replies.human_comment(_support.CONTINUE_ID, body))

                signal = _signal(issue, generation)

                self.assertEqual(
                    (
                        len(signal.guidance),
                        signal.bare_continue,
                        getattr(signal.authorization, "candidate_sha", None),
                    ),
                    classified,
                )


if __name__ == "__main__":
    unittest.main()
