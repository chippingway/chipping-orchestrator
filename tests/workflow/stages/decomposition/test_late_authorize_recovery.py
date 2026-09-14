# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Recovering a recorded authorization after interruption or a replaced adjudication."""
from __future__ import annotations

from orchestrator.workflow.stages.decomposition.late_models import (
    _LateDisposition,
)
from tests.workflow.stages.decomposition import (
    late_authorize_case as _authorize_case,
    late_content_replies as _content_replies,
    late_content_support as _support,
    late_test_support as _stage_support,
)
from tests.workflow.stages.decomposition.late_revision_support import (
    DEV_ACK,
    DEV_PIN,
    UNCHANGED,
)


class AuthorizationRecoveryTest(_authorize_case._AuthorizeCase):
    """A process that died between the decision and what it licenses."""

    def test_a_dead_tick_settles_from_the_write(self) -> None:
        # The write goes out before the owner read, so a tick killed there
        # leaves the record, the cleared park and the consumed reply behind --
        # which is exactly enough for the next tick to finish without asking
        # the human, or an agent, anything.
        self._authorize_then_crash()

        outcome = self._tick()

        self.spawn.assert_not_called()
        self.assertEqual(outcome.disposition, _LateDisposition.SETTLED)
        self.assertEqual(self._pinned().get(_stage_support.KEYS.exempt_sha), _stage_support.CANDIDATE_SHA)

    def test_recovery_reproves_the_contribution(self) -> None:
        # The record agreeing with itself is not evidence: a publication can
        # be reached by a later poll, on a later process, on a host that never
        # held the content between the frozen pair. So the digest is taken
        # again, and neither a reading nobody could take nor one that
        # disagrees publishes anything.
        for named, seed in (
            ("no reading at all", _authorize_case._UNFINGERPRINTED),
            ("a contribution that moved", _authorize_case._MOVED_CONTRIBUTION),
        ):
            with self.subTest(reading=named):
                self.setUp()
                self._authorize_then_crash()

                outcome = self._tick(worktree=seed)

                self.assertEqual(outcome.disposition, _LateDisposition.PARKED)
                self.assertNotIn(_stage_support.KEYS.exempt_sha, self._pinned())
                # Parked, and with nothing lost: the authorization stands, so
                # a host that can read the pair again publishes what the
                # operator already decided.
                self.assertEqual(self._authorized(), _stage_support.CANDIDATE_SHA)
                self.assertEqual(
                    self._pinned().get(_stage_support.KEYS.park_reason),
                    _support.PARK_SINGLE_DECISION,
                )

    def test_a_repaired_store_publishes_it(self) -> None:
        self._authorize_then_crash()
        self._tick(worktree=_authorize_case._UNFINGERPRINTED)

        outcome = self._tick()

        self.spawn.assert_not_called()
        self.assertEqual(outcome.disposition, _LateDisposition.SETTLED)
        self.assertEqual(self._pinned().get(_stage_support.KEYS.exempt_sha), _stage_support.CANDIDATE_SHA)

    def test_a_moved_candidate_publishes_nothing(self) -> None:
        # The commit alone is not the authorization. A generation standing
        # over another base is a different contribution from the one that was
        # read, so a record naming the same commit no longer covers it -- and
        # the record is left in place, so what refuses the publication is that
        # comparison rather than an authorization nobody could find.
        self._authorize_then_crash()
        self._moved_base()

        outcome = self._tick()

        self.assertEqual(outcome.disposition, _LateDisposition.PARKED)
        pinned = self._pinned()
        self.assertEqual(self._authorized(), _stage_support.CANDIDATE_SHA)
        self.assertNotIn(_stage_support.KEYS.exempt_sha, pinned)
        self.assertEqual(pinned.get(_stage_support.KEYS.park_reason), _support.PARK_SINGLE_DECISION)
    def _moved_base(self) -> None:
        """Stand the frozen pair over another base, keeping the record whole.

        Written over the pinned comment as it is rather than seeded fresh,
        because what this is about is a record that IS there and does not
        cover what is in hand -- and a fresh seed would drop the very group
        the comparison is supposed to refuse.
        """
        self.github.seed_state(
            self.issue.number,
            **{**self._pinned(), _stage_support.KEYS.base_sha: _stage_support.OTHER_SHA},
        )


class ReplacedAnswerTest(_authorize_case._AuthorizeCase):
    """An authorization outliving the answer it was given for.

    Every term of the record survives a candidate being adjudicated a second
    time -- the frozen pair, the measurement and the digest all still match --
    so what stops the new answer publishing on the old permission is the
    record going with the answer it covers. These are the three roads to a
    second adjudication, and each ends the same way.
    """

    def test_a_certified_edit_ends_the_authorization(self) -> None:
        # The terms of the record all survive an answer being thrown away and
        # re-earned, so nothing in them would stop the NEXT adjudication's
        # `single` publishing on a permission nobody granted it. What stops it
        # is the record going with the answer it was given for.
        self._authorize_then_crash()
        self.issue.title = _support.EDITED_TITLE
        self._tick()
        self.assertEqual(
            self._pinned().get(_stage_support.KEYS.park_reason), _support.PARK_CONTENT_DRIFT,
        )
        _content_replies.reply(self.issue, _support.BARE_CONTINUE)

        outcome = self._tick(reply=_stage_support.SINGLE_REPLY)

        # The certificate bought a fresh adjudication, it answered `single`
        # again, and the issue is back where an unauthorized one waits.
        self.spawn.assert_called_once()
        self.assertEqual(outcome.disposition, _LateDisposition.PARKED)
        pinned = self._pinned()
        self.assertIsNone(self._authorized())
        self.assertNotIn(_stage_support.KEYS.exempt_sha, pinned)
        self.assertEqual(pinned.get(_stage_support.KEYS.park_reason), _support.PARK_SINGLE_DECISION)

    def test_a_revision_ends_the_authorization(self) -> None:
        # The other road to a second adjudication, and the one the terms
        # cannot see at all: an acknowledged candidate comes back over the
        # same base at the same size, so the pair, the measurement and the
        # digest all still match and only the generation counter has moved.
        self._authorize_then_crash()
        self.github.seed_state(
            self.issue.number, **{**self._pinned(), **DEV_PIN},
        )
        _content_replies.reply(self.issue)

        revised = self._tick(
            reply=DEV_ACK,
            worktree=UNCHANGED,
            measurement=_authorize_case._UNCHANGED_MEASUREMENT,
        )

        self.assertEqual(revised.disposition, _LateDisposition.REVISED)
        self.assertIsNone(self._authorized())

    def test_a_replacement_run_ends_the_authorization(self) -> None:
        # The record can lose the answer it names by roads nothing here
        # enumerates -- a hand edit, an older binary, a half-written crash --
        # and what follows every one of them is a fresh adjudication. The run
        # replacing that answer is where the permission goes, which is the
        # statement of the rule those roads all pass through.
        self._authorize_then_crash()
        self._forgotten_verdict()

        outcome = self._tick(reply=_stage_support.SINGLE_REPLY)

        self.spawn.assert_called_once()
        self.assertEqual(outcome.disposition, _LateDisposition.PARKED)
        pinned = self._pinned()
        self.assertIsNone(self._authorized())
        self.assertNotIn(_stage_support.KEYS.exempt_sha, pinned)
        self.assertEqual(pinned.get(_stage_support.KEYS.park_reason), _support.PARK_SINGLE_DECISION)

    def _forgotten_verdict(self) -> None:
        """Take the answer off the record, leaving everything else whole."""
        self.github.seed_state(
            self.issue.number, **{**self._pinned(), _stage_support.KEYS.verdict: None},
        )


class ReadjudicatedAuthorizationTest(_authorize_case._AuthorizeCase):
    """A command over an adjudication the record can no longer show.

    The park has to come down with the answer it was waiting on, because what
    the issue stops for next is whatever the replacement run decides. A park
    left standing over that run would suppress the announcement a categorized
    question earns -- the one sentence nothing else will ever say -- and would
    have a split create children under a claim that the issue is waiting.
    """

    def setUp(self) -> None:
        self._park(**{_stage_support.KEYS.verdict: None, _stage_support.KEYS.source_sha: None})
        self._command()

    def test_it_says_so_and_readjudicates(self) -> None:
        outcome = self._tick(reply=_stage_support.SINGLE_REPLY)

        self.spawn.assert_called_once()
        self.assertIn(
            _authorize_case.NO_VERDICT_NOTICE, "".join(self._bodies()),
        )
        # The fresh answer is the adjudicator's own, so the issue waits on the
        # decision again rather than publishing on a permission for an answer
        # nothing could show.
        self.assertEqual(outcome.disposition, _LateDisposition.PARKED)
        pinned = self._pinned()
        self.assertIsNone(self._authorized())
        self.assertNotIn(_stage_support.KEYS.exempt_sha, pinned)
        self.assertEqual(pinned.get(_stage_support.KEYS.park_reason), _support.PARK_SINGLE_DECISION)

    def test_a_question_is_still_announced(self) -> None:
        outcome = self._tick(reply=_stage_support.QUESTION_REPLY)

        self.assertEqual(outcome.disposition, _LateDisposition.DECIDED)
        self.assertEqual(
            self._pinned().get(_stage_support.KEYS.park_reason), _support.PARK_QUESTION,
        )
        self.assertIn(_stage_support.QUESTION_ASKED, self._bodies()[-1])

    def test_a_split_carries_no_stale_park(self) -> None:
        outcome = self._tick(reply=_stage_support.SPLIT_REPLY)

        self.assertIsNotNone(outcome.guarded_split)
        pinned = self._pinned()
        self.assertFalse(pinned.get(_stage_support.KEYS.awaiting))
        self.assertIsNone(pinned.get(_stage_support.KEYS.park_reason))
