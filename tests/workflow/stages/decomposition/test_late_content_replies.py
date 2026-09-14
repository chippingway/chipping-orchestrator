# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Which fresh reply is a requirement, and which is an operator control.

Read against single comments rather than through a tick, because what this
owner answers is a question about one body: whether an agent may be handed it
as work, and whether it is the command that licenses a publication past the
size gate. What the thread around it is -- who is trusted, which comments are
fresh -- is the content reader's, and is asserted there.
"""
from __future__ import annotations

import unittest

from orchestrator.workflow.stages.decomposition import (
    late_content_replies as _replies,
)
from tests.workflow.stages.decomposition import late_content_support as _support
from tests.workflow.stages.decomposition.late_test_support import CANDIDATE_SHA

EMPTY_BODY = "   \n "

MALFORMED_SHA = "the one above"

UNNAMEABLE_ID = 0


class GuidanceClassificationTest(unittest.TestCase):
    """What a comment has to carry before a developer may be resumed on it."""

    def test_a_comment_classifies_by_what_it_says(self) -> None:
        # The two operator controls are decisions about the candidate that
        # already exists, so neither is work: resuming a developer on one
        # would answer a question about scope with the word "continue" or with
        # a commit id. Prose around either is guidance, since neither is the
        # whole comment then, and a body with nothing in it says nothing a
        # developer could revise against.
        for body, classified in (
            (_support.GUIDANCE_BODY, True),
            (_support.BARE_CONTINUE, False),
            (_support.authorization(), False),
            (_support.CONTINUE_WITH_GUIDANCE, True),
            (f"{_support.authorization()}\n\nbut drop the retry loop", True),
            (EMPTY_BODY, False),
        ):
            with self.subTest(body=body):
                self.assertEqual(
                    _replies._is_guidance(_support.human_comment(_support.GUIDANCE_ID, body)),
                    classified,
                )


class AuthorizationReadingTest(unittest.TestCase):
    """Which command in a batch of replies is the one the workflow acts on."""

    def test_the_last_command_written_is_the_request(self) -> None:
        # A batch is read in thread order, and a human who wrote the command
        # twice meant the second: a corrected commit below a mistyped one is
        # the request, not the line it corrects.
        read = _replies._authorization([
            _support.human_comment(_support.GUIDANCE_ID, _support.authorization(CANDIDATE_SHA)),
            _support.human_comment(_support.SECOND_ID, _support.authorization(_support.REVISED_SHA)),
        ])

        self.assertEqual(read.candidate_sha, _support.REVISED_SHA)
        self.assertEqual(read.comment_id, _support.SECOND_ID)

    def test_a_malformed_argument_is_carried(self) -> None:
        # The refusal this earns is the authorizing owner's to say, and it
        # cannot say it about a command it was handed nothing about: dropped
        # here, a mistyped commit would read exactly like a line nobody typed.
        for named in (MALFORMED_SHA, ""):
            with self.subTest(named=named):
                read = _replies._authorization([
                    _support.human_comment(_support.CONTINUE_ID, _support.authorization(named).strip()),
                ])

                self.assertEqual(read.candidate_sha, named)
                self.assertEqual(read.comment_id, _support.CONTINUE_ID)

    def test_what_is_not_the_command_reads_as_none(self) -> None:
        # The last of these is the one the record could not survive: a bypass
        # of the size gate is licensed by one gesture at one address anybody
        # can go and read, so a command nothing can attribute is dropped
        # rather than recorded against a comment that cannot be named.
        for fresh in (
            [],
            [_support.human_comment(_support.GUIDANCE_ID, _support.GUIDANCE_BODY)],
            [_support.human_comment(_support.CONTINUE_ID, _support.BARE_CONTINUE)],
            [_support.human_comment(_support.SECOND_ID, f"please run {_support.authorization()} now")],
            [_support.human_comment(UNNAMEABLE_ID, _support.authorization())],
        ):
            with self.subTest(fresh=[quoted.id for quoted in fresh]):
                self.assertIsNone(_replies._authorization(fresh))


if __name__ == "__main__":
    unittest.main()
