# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Recovering a recorded authorization after interruption or a replaced adjudication."""
from __future__ import annotations

import itertools
import json

from orchestrator.workflow.stages.decomposition.late_result_models import (
    MAX_RATIONALE,
    RATIONALE_TRUNCATION_MARKER,
    _LateDisposition,
)
from tests.workflow.stages.decomposition import (
    late_authorize_case as _authorize_case,
    late_content_replies as _content_replies,
    late_content_support as _support,
    late_test_support as _stage_support,
)
from tests.workflow.stages.decomposition.late_accepted_notice_support import (
    UNRECORDED_RATIONALE,
    shown_rationale,
)
from tests.workflow.stages.decomposition.late_published_support import (
    published_generation,
    seed_published_pr,
)
from tests.workflow.stages.decomposition.late_reply_support import late_block
from tests.workflow.stages.decomposition.late_revision_support import (
    DEV_ACK,
    DEV_PIN,
    UNCHANGED,
)
from tests.workflow.stages.decomposition.late_settlement_support import (
    OWNER_GUARD,
    killed_at,
)

# A `single` arguing past what a record keeps, through a fence and an opener:
# what only the run that received it ever holds whole.
_UNKEPT_RATIONALE = "".join(("```\n<!-- ", "r" * MAX_RATIONALE))

_UNKEPT_RATIONALE_REPLY = late_block(json.dumps({
    "decision": "single",
    "rationale": _UNKEPT_RATIONALE,
    "split_blocker": _stage_support.SPLIT_BLOCKER,
}))

# The two publications a settled `single` makes: the ordinary one a candidate
# nothing had published goes back to, and the push onto the pull request the
# verdict was taken over.
_PUBLICATIONS = (("initial publication", False), ("an existing pull request", True))

# What a record kept beside its `single`, and what the accepted notice quotes
# of it: the argument itself, or nothing for a record older than the key and
# for one holding a value nobody can show.
_RECOVERED_RATIONALES = (
    (
        "recorded",
        {_stage_support.KEYS.rationale: _stage_support.SINGLE_RATIONALE},
        _stage_support.SINGLE_RATIONALE,
    ),
    ("legacy", {}, ""),
    ("malformed", {_stage_support.KEYS.rationale: 7}, ""),
)

# Every record above on each publication: what a notice said by a later tick
# than the one that recorded the authorization quotes of it.
_DEAD_AUTHORIZATIONS = tuple(
    (f"{road}, {kept}", published, held, quoted)
    for (road, published), (kept, held, quoted) in itertools.product(
        _PUBLICATIONS, _RECOVERED_RATIONALES,
    )
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


class RecoveredRationaleTest(_authorize_case._AuthorizeCase):
    """The argument an accepted notice quotes, after a process died on the way.

    Nothing that reaches the publication after a crash ever saw the reply, so
    what it quotes is what the record kept -- on either publication, and with
    no agent paid to recover an argument.
    """

    def test_a_dead_authorization_quotes_the_record(self) -> None:
        # The tick that recorded the authorization died before publishing, so
        # the notice is said by one that read nothing but the record: the
        # argument where it kept one, and the sentence saying none was
        # recorded where it kept none a reader can use.
        for named, published, held, quoted in _DEAD_AUTHORIZATIONS:
            with self.subTest(case=named):
                self._seed_on(published, **_support.SINGLE_PARKED, **held)
                self._authorize_then_crash()

                said = self._settled_notice()

                self.assertEqual(shown_rationale(said), quoted)
                self.assertEqual(UNRECORDED_RATIONALE in said, not quoted)

    def test_a_dead_run_parks_then_quotes_its_record(self) -> None:
        # The run is the only thing that ever holds the whole reply, and this
        # one dies past the write recording it. What every later tick has is
        # the bounded record: an adjudicator's own `single` still parks until
        # a human authorizes it, no second agent is paid for, and the notice
        # that authorization earns quotes exactly what was kept -- cut, and
        # saying so -- rather than what the agent wrote.
        for road, published in _PUBLICATIONS:
            with self.subTest(publication=road):
                self._seed_on(published)
                with killed_at(OWNER_GUARD), self.assertRaises(KeyboardInterrupt):
                    self._tick(reply=_UNKEPT_RATIONALE_REPLY)
                kept = self._pinned().get(_stage_support.KEYS.rationale)

                parked = self._tick()

                self.spawn.assert_not_called()
                self.assertEqual(parked.disposition, _LateDisposition.PARKED)
                self._assert_still_parked()
                self.assertNotIn(_authorize_case.ACCEPTED_NOTICE, "".join(self._bodies()))
                self._command()

                said = self._settled_notice()

                self.assertTrue(kept.endswith(RATIONALE_TRUNCATION_MARKER))
                self.assertEqual(shown_rationale(said), kept)

    def _seed_on(self, published: bool, **state) -> None:
        """Seed this issue on either publication a settled `single` makes."""
        if not published:
            self._seed(**state)
            return
        self._seed(generation=published_generation(), **state)
        seed_published_pr(self.github)

    def _settled_notice(self) -> str:
        """Tick once more, and the one accepted notice the settlement said.

        Settled with no agent behind it: the verdict is on the record, and
        nothing about publishing it is worth a second run.
        """
        outcome = self._tick()
        self.spawn.assert_not_called()
        self.assertEqual(outcome.disposition, _LateDisposition.SETTLED)
        said = [
            body for body in self._bodies()
            if _authorize_case.ACCEPTED_NOTICE in body
        ]
        self.assertEqual(len(said), _authorize_case.SAID_ONCE)
        return said[0]
