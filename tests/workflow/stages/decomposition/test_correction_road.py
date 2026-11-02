# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The one correction a rejected initial manifest earns, launched and answered on the tick that rejected it.

A completed, accounted, read-only run whose manifest the parser refuses has
its session resumed once, under the pinned command, with the exact error; the
correction's answer goes through the same checks as any decomposer answer and
a usable one through the ordinary `single` or `split` handling, nothing made
before it. Every other answer keeps the disposition it always had, and a
correction's own answer earns nothing more.
"""
from __future__ import annotations

import unittest
from unittest.mock import patch

from orchestrator import config
from orchestrator.workflow.engine import decomposition_prompts as _prompts
from tests.workflow.fixtures import KEY_AWAITING_HUMAN, LABEL_READY
from tests.workflow.stages.decomposition import correction_tick_support as support

_BLOCKED = "workflow:blocked"
_CLEANUP = "_cleanup_decompose_worktree"

# The reply boundary the issue's pickup left, and a reply written while its correction is out.
_BOUNDARY = 900
_MEANWHILE = "Please retain streaming."


def _says(message: str, **fields) -> dict:
    """A decomposer's answer: its final message, beside the fields its result reports."""
    return {"last_message": message, **fields}


# Answers whose disposition is decided before any manifest is read, or that
# carry none, each with what it leaves: a park saying so, or nothing at all.
_UNEARNED = (
    ("a question", _says(support.QUESTION), {}, "decomposer needs your input"),
    ("silence", _says(""), {}, "decomposer produced no final message"),
    ("a failed exit", _says(support.UNLISTED, exit_code=1), {}, "manifest invalid"),
    ("a timeout", _says(support.UNLISTED, timed_out=True), {}, "timed out"),
    ("a dirty checkout", _says(support.UNLISTED), {"dirty_files": ("x.py",)}, "read-only"),
    ("an interruption", _says(support.UNLISTED, interrupted=True, exit_code=support.SHUTDOWN_EXIT), {}, None),
)

# What a correction answers, beside the park it takes and whether its checkout is kept.
_CORRECTION_ANSWERS = (
    ("a question", _says(support.QUESTION), {}, "decomposer needs your input"),
    ("a timeout", _says(support.LISTED, timed_out=True), {}, "timed out"),
    ("a dirty checkout", _says(support.LISTED), {"has_new_commits": [False, True]}, "read-only"),
)


class CorrectedManifestTest(unittest.TestCase, support.CorrectionTickCase):
    """A rejected manifest is corrected once, and a usable correction is the decomposition."""

    def test_ten_unlisted_children_are_corrected_once(self) -> None:
        # Ten slices, every `depends_on` left out: refused naming the first,
        # with nothing created or marked, and the same conversation resumed
        # under the same command is asked once for the whole manifest again.
        self.opened()
        runner = self.decomposer(support.UNLISTED, support.LISTED)

        self.tick(runner)

        fresh, corrected = runner.launches
        self.assertEqual(corrected.command(), fresh.command())
        self.assertEqual(corrected.resumed, support.SESSION)
        self.assertIn(f"> {support.UNLISTED_ERROR}", corrected.prompt)
        self.assertTrue(corrected.prompt.endswith(_prompts._MANIFEST_CONTRACT))
        self._assert_nothing_made_before(corrected)
        self._assert_chained_split()

    def test_a_corrected_single_reaches_ready(self) -> None:
        self.opened()
        runner = self.decomposer(support.SELF_EDGE, support.SINGLE)

        self.tick(runner)

        corrected = runner.launches[-1]
        self.assertEqual(len(runner.launches), 2)
        self.assertIn(f"> {support.SELF_EDGE_ERROR}", corrected.prompt)
        self.assertEqual(self.label(), LABEL_READY)
        self.assertEqual(self.stage(), support.EXHAUSTED)
        self.assertEqual(self.children(), 0)

    def _assert_nothing_made_before(self, corrected: support.Launch) -> None:
        """No child or split marker stood when the correction ran, and its attempt was pending."""
        record = corrected.record
        self.assertEqual(corrected.children, 0)
        self.assertEqual(record[support.FIELD]["stage"], support.PENDING)
        self.assertFalse(set(support.SPLIT_MARKERS) & set(record), "no split marker before it")

    def _assert_chained_split(self) -> None:
        """The issue split into the ten slices in a chain, with the attempt spent on the correction charged second."""
        pinned = self.pinned()
        chain = {
            str(index): [index - 1]
            for index in range(1, support.SLICES)
        }
        correction = pinned[support.FIELD]["correction"]
        self.assertEqual(self.children(), support.SLICES)
        self.assertEqual(pinned["dep_graph"], chain)
        self.assertEqual(self.label(), _BLOCKED)
        self.assertEqual(self.stage(), support.EXHAUSTED)
        self.assertEqual(correction["ordinal"], 2)


class UnearnedCorrectionTest(unittest.TestCase, support.CorrectionTickCase):
    """Every answer but a completed run's refused manifest keeps the disposition it always had."""

    def test_unearned_answers_keep_their_dispositions(self) -> None:
        for name, answer, run_options, said in _UNEARNED:
            with self.subTest(name):
                self.opened()
                runner = self.decomposer(answer)

                self.tick(runner, **run_options)

                self.assertEqual(len(runner.launches), 1)
                self.assertIsNone(self.stage())
                self.assertEqual(self.children(), 0)
                self.assertEqual(self.label(), support.LABEL_DECOMPOSING)
                self._assert_parked_as(said)

    def test_a_run_with_no_session_parks(self) -> None:
        # A backend that surfaced no session id saved no conversation to
        # resume: the refusal parks for a human rather than spawning anew.
        self.opened()
        runner = self.decomposer(support.UNLISTED, session=None)

        self.tick(runner)

        self.assertEqual(len(runner.launches), 1)
        self.assertIsNone(self.stage())
        self.assertTrue(self.pinned()[KEY_AWAITING_HUMAN])
        self._assert_parked_as(f"manifest invalid ({support.UNLISTED_ERROR})")

    def _assert_parked_as(self, said: str | None) -> None:
        """The thread carries one park saying `said`, never a correction's -- or nothing, where `said` is None."""
        if said is None:
            self.assertEqual(self.said(), [])
            return
        self.assertEqual(len(self.said()), 1)
        self.assertIn(said, self.said()[0])
        self.assertNotIn(support.CORRECTED_PARK, self.said()[0])


class CorrectionAnswerTest(unittest.TestCase, support.CorrectionTickCase):
    """A correction's own answer keeps the disposition it reaches and earns no correction of its own."""

    def test_a_corrections_answer_parks_and_spends_it(self) -> None:
        for name, answer, run_options, said in _CORRECTION_ANSWERS:
            with self.subTest(name):
                self._assert_parks_on(answer, run_options, said)

    def test_an_interrupted_correction_parks_later(self) -> None:
        # A shutdown-killed correction leaves its start on the ledgers and no
        # answer anything acted on: the next tick parks for a human, once, and
        # neither that tick nor a quiet one after it launches anything.
        self._kills_the_correction()
        quiet = self.decomposer(support.LISTED)

        self.tick(quiet)
        self.tick(quiet)

        self.assertEqual(quiet.launches, [])
        self.assertEqual(self.said(), [self.said()[0]])
        self.assertIn("was started, but nothing could act on its answer", self.said()[0])
        self.assertEqual(self.stage(), support.EXHAUSTED)
        self.assertTrue(self.pinned()[KEY_AWAITING_HUMAN])

    def test_a_reply_during_the_correction_waits(self) -> None:
        # A trusted reply written while the correction is out stays past the
        # boundary its park records: the next tick resumes the saved session
        # on it rather than reading it as an edit and decomposing afresh.
        self.enterContext(patch.object(config, "ALLOWED_ISSUE_AUTHORS", (support.TRUSTED_AUTHOR,)))
        self.opened(last_action_comment_id=_BOUNDARY)
        runner = self.decomposer(support.UNLISTED, support.SELF_EDGE, during={1: self._replies})
        self.tick(runner)
        parked = self.pinned()
        later = self.decomposer(support.SINGLE)

        self.tick(later)

        self.assertEqual(parked["last_action_comment_id"], _BOUNDARY, "the park stops short of the reply")
        self.assertTrue(parked[KEY_AWAITING_HUMAN])
        self.assertEqual(later.launches[0].resumed, support.SESSION)
        self.assertIn(_MEANWHILE, later.launches[0].prompt)

    def _replies(self, world: support.CorrectionTickCase) -> None:
        """A trusted human replies while the correction is out."""
        world.reply(_MEANWHILE)

    def _kills_the_correction(self) -> None:
        """A tick whose correction a shutdown kills, leaving its attempt pending and nothing said."""
        self.opened()
        killed = _says("", interrupted=True, exit_code=support.SHUTDOWN_EXIT)
        self.tick(self.decomposer(support.UNLISTED, killed))
        self.assertEqual(self.stage(), support.PENDING)
        self.assertEqual(self.said(), [])

    def _assert_parks_on(self, answer: dict, run_options: dict, said: str) -> None:
        """A correction answering `answer` parks saying `said`, once, and spends its attempt, the session kept."""
        self.opened()
        runner = self.decomposer(support.UNLISTED, answer)

        mocks = self.tick(runner, **run_options)

        kept = "has_new_commits" in run_options
        self.assertEqual(mocks[_CLEANUP].called, not kept, "a dirty checkout is kept for inspection")
        self.assertEqual(len(runner.launches), 2)
        self.assertEqual(self.said(), [self.said()[0]])
        self.assertIn(said, self.said()[0])
        self.assertEqual(self.stage(), support.EXHAUSTED)
        self.assertEqual(self.pinned()["decomposer_session_id"], support.SESSION)


if __name__ == "__main__":
    unittest.main()
