# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Unsplit explanation text with long fence runs and embedded comment openers."""
from __future__ import annotations

import unittest

from orchestrator.github.pinned_state import (
    MAX_PINNED_BODY,
    PINNED_STATE_MARKER,
)
from orchestrator.workflow.stages.decomposition import (
    late_notice as _late_notice,
    late_park_state as _late_park_state,
)
from orchestrator.workflow.stages.decomposition.late_result_models import UNRECORDED_SPLIT_BLOCKER
from tests.workflow.stages.decomposition import (
    late_notice_case as _notice_case,
    late_notice_payloads as _notice_payloads,
)
from tests.workflow.stages.decomposition.late_test_support import KEYS


class CarriedTextNoticeTest(_notice_case._NoticeCase, unittest.TestCase):
    """Text this orchestrator did not write, carried into a sentence it did.

    Only the unsplit park's notice leaves a place for the record to be named
    in, so a park that quotes an agent or a human keeps what they wrote --
    expanding it would put words in their mouth. Nothing is rewritten on the
    way out either, this orchestrator's own pinned-state marker included: a
    substitution that grew the sentence per occurrence could push it past what
    GitHub accepts, so what keeps a sentence carrying that marker findable
    afterwards is the read that names the pinned comment by its id.
    """

    def test_an_explanation_naming_the_pinned_state(self) -> None:
        # Both halves of the one sentence that has to survive: the marker
        # would hide the delivered notice from the body test that finds it,
        # and any rewrite escaping the marker out would grow the comment per
        # occurrence -- at this length, past what GitHub accepts, which is a
        # notice no tick could deliver at all. So it goes out as written, and
        # the read that looks for it names the pinned comment by identity.
        self._say_it_and_lose_the_write(_notice_payloads._STATE_MARKER_RUN)
        said = _notice_payloads._last_said(self.github)
        self.assertIn(PINNED_STATE_MARKER, said)
        self.assertLessEqual(len(said), MAX_PINNED_BODY)
        self.assertIn(_notice_payloads._STATE_MARKER_BLOCKER, said)

        self._adjudicate()

        self._assert_said_once()

    def test_the_instructions_survive_the_quote(self) -> None:
        # A thread is markdown, so an explanation opening an HTML comment
        # swallows everything after it: quoted mid-sentence, it would leave a
        # human reading as far as the quote and told neither what the agent
        # said nor what to do about it. The quote comes last and inside a
        # fence, which a thread shows rather than obeys.
        self._decide(_notice_payloads._STATE_MARKER_RUN)

        said = _notice_payloads._last_said(self.github)
        instructions, _opened, quoted = said.partition(_notice_payloads._FENCE)

        self.assertNotIn(_notice_payloads._HTML_OPEN, instructions)
        self.assertIn(_notice_payloads._REPLY_INSTRUCTION, instructions)
        self.assertIn(_notice_payloads._STATE_MARKER_BLOCKER, quoted)

    def test_a_quote_carrying_a_fence(self) -> None:
        # Markdown closes a fenced block on a run of its own character at
        # least as long as the one that opened it, so a quote carrying a fence
        # of each kind would close either one early and let what follows
        # render as markdown again -- which is the failure the fence is here
        # to prevent. Neither character is cheap here, so the tie goes to the
        # ordinary one and the fence is the longer run.
        self._decide(_notice_payloads._FENCED_RUN)

        said = _notice_payloads._last_said(self.github)
        instructions, _opened, quoted = said.partition(_notice_payloads._LONGER_FENCE)

        self.assertNotIn(_notice_payloads._HTML_OPEN, instructions)
        self.assertIn(_notice_payloads._FENCED_BLOCKER, quoted)

    def test_a_quote_of_fences_is_still_said(self) -> None:
        # A run of backticks is nothing to a tilde fence, so the explanation a
        # single fence character could not have blocked off at all costs three
        # characters at each end and reaches the thread whole. Saying a piece
        # of it would tell a human less than the record holds about what their
        # unpublished candidate is waiting on.
        self._say_it_and_lose_the_write(_notice_payloads._BACKTICK_RUN_REPLY)
        said = _notice_payloads._last_said(self.github)
        self.assertLessEqual(len(said), MAX_PINNED_BODY)
        self.assertIn(_notice_payloads._TILDE_FENCE, said)
        self.assertIn(_notice_payloads._BACKTICK_BLOCKER, said)

        self._adjudicate()

        self._assert_said_once()

    def test_a_question_with_the_marker_is_kept(self) -> None:
        self._decide(_notice_payloads._QUESTION_MARKER_RUN)

        said = _notice_payloads._last_said(self.github)
        self.assertIn(_late_notice.RECORDED_EXPLANATION, said)
        self.assertNotIn(UNRECORDED_SPLIT_BLOCKER, said)
        self.assertEqual(
            self._pinned().get(KEYS.question),
            f"which half {_late_notice.RECORDED_EXPLANATION} of it?",
        )

    def test_the_scoped_reason_is_the_park_that_names(self) -> None:
        # The reason is spelled in the notice leaf rather than imported from
        # the owner that stages parks, since reaching back would put that leaf
        # in the cycle it sits under -- so the two are checked against each
        # other here instead. A rename on either side would silently widen the
        # substitution to notices nothing here worded, or close it on the one
        # it exists for.
        self.assertEqual(
            _late_notice._NAMES_THE_EXPLANATION,
            _late_park_state.PARK_SINGLE_DECISION,
        )
