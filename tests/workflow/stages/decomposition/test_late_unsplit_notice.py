# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The sentence an unsplit park owes, and what it is allowed to name.

The explanation a `single` gave is already durable on the pinned comment, so
the obligation that makes the park's sentence retryable NAMES that record
rather than copying it: a second copy would be one the comment could not hold
beside the first, and nothing supersedes this park, so an obligation nothing
could write is a sentence no tick would ever say.

What that costs is one rule per road. The marker is put back exactly once, by
the step that delivers -- twice would rewrite an agent's own marker text --
and only for the park this orchestrator worded, since every other park carries
somebody else's sentence verbatim. And the room the write needs is reserved
where an outcome is accepted, which a record an older binary left never paid
and one written before the payload escaped the wrapper's own terminator
re-serializes past, so what a notice is measured against is the room BESIDE
what the record actually costs rather than a budget the record itself may
already sit outside.

The quote itself is bounded the other way round: an explanation the sentence
could not say whole is refused where the outcome is RECORDED rather than
trimmed on the way to the thread, since a fraction of a reason reads as the
whole of one on the park nothing supersedes.

What the park itself earns is `test_late_unsplit_park.py` beside this.
"""
from __future__ import annotations

import unittest

from orchestrator.github.pinned_state import (
    MAX_PINNED_BODY,
    PINNED_STATE_BODY_RE,
    pinned_state_body,
)
from orchestrator.workflow.stages.decomposition import (
    late_notice as _late_notice,
    late_park_state as _late_park_state,
    late_session as _late_session,
)
from orchestrator.workflow.stages.decomposition.late_models import (
    _LateDisposition,
)
from tests.workflow.stages.decomposition import (
    late_notice_case as _notice_case,
    late_notice_payloads as _notice_payloads,
)
from tests.workflow.stages.decomposition.late_content_support import (
    RefusedComment,
)
from tests.workflow.stages.decomposition.late_settlement_support import (
    ERROR,
    SAID_ONCE,
    SINGLE_RUN,
    WORKFLOW_LOG,
    GuardedLateCase,
)
from tests.workflow.stages.decomposition.late_test_support import KEYS


class LegacyRecordParkTest(_notice_case._RefusedDeliveryCase, unittest.TestCase):
    """A `single` an older binary recorded still gets its sentence said.

    The reserve a notice needs is kept where an outcome is accepted, and a
    record written before that reserve existed never paid it. It is on live
    issues all the same, so the sentence its park owes is measured beside the
    record rather than inside it -- the room under GitHub's limit is for the
    keys written AFTER an outcome is recorded, and a park notice is one of
    them. Nothing supersedes this park, so an obligation dropped here would be
    a human never told what their unpublished candidate is waiting on.
    """

    def setUp(self) -> None:
        super().setUp()
        self.github.seed_state(
            self.issue.number, **_notice_payloads._legacy_record(),
        )

    def test_a_refused_notice_is_still_owed(self) -> None:
        recorded = len(pinned_state_body(self._pinned()))
        # The band this case is only a regression inside: a record filling the
        # outcome budget, so the room its sentence needs is the room left
        # beside it rather than inside it.
        self.assertGreater(
            recorded, _late_session.MAX_RECORDED_BODY - _late_session.MAX_NOTICE_BODY,
        )
        self.assertLessEqual(recorded, _late_session.MAX_RECORDED_BODY)

        self._refuse_the_notice()

        self.assertEqual(self.github.posted_comments, [])
        self.assertIn(_late_notice.PARK_NOTICE, self._pinned())

    def test_the_reserve_stays_under_the_limit(self) -> None:
        # The room a notice is measured into is left BESIDE a recorded
        # outcome, out of the headroom under GitHub's own limit -- so it may
        # not take the whole of that headroom: the keys other stages write
        # after an outcome is recorded are what the rest of it is for.
        self.assertLess(_late_session.MAX_NOTICE_COMMENT, MAX_PINNED_BODY)

    def test_the_next_tick_says_it(self) -> None:
        self._refuse_the_notice()

        outcome, spawn = self._adjudicate()

        spawn.assert_not_called()
        self.assertEqual(outcome.disposition, _LateDisposition.PARKED)
        self.assertEqual(len(self.github.posted_comments), SAID_ONCE)
        self.assertNotIn(_late_notice.PARK_NOTICE, self._pinned())


class ReserializedRecordParkTest(_notice_case._TerminatorRecordCase, unittest.TestCase):
    """A record the escape grew past the reserve still gets its sentence said.

    Five characters an occurrence is enough, at this many terminators, to put
    a record accepted at the outcome budget outside the ceiling a notice is
    measured against. Charged that difference, the sentence is dropped -- and
    nothing supersedes this park, so a refused delivery would leave the issue
    parked for good over a thread nobody ever told.
    """

    terminators = _notice_payloads._TERMINATORS

    def test_the_record_grew_past_the_old_ceiling(self) -> None:
        # The band this case is only a regression inside: inside the whole
        # outcome budget as it was written, and past that budget AND the
        # reserve beside it as it is written now.
        recorded = len(pinned_state_body(self._pinned()))

        self.assertLessEqual(
            recorded - _notice_payloads._ESCAPE_COST * _notice_payloads._TERMINATORS,
            _late_session.MAX_RECORDED_BODY,
        )
        self.assertGreater(
            recorded,
            _late_session.MAX_RECORDED_BODY + _late_session.MAX_NOTICE_BODY,
        )


class UnescapableRecordParkTest(_notice_case._TerminatorRecordCase, unittest.TestCase):
    """A record the escape cannot render at all still gets its sentence said.

    At this many terminators the escaped payload is past what GitHub takes,
    and the write it would be refused on is the write the park and its notice
    ride out on. The record is what a later tick reads and the escape only
    decides how the comment looks, so the payload goes as it was stored --
    the rendering the binary that accepted it gave it, and one this parser
    still reads back whole.
    """

    terminators = _notice_payloads._UNESCAPABLE_TERMINATORS

    def test_the_payload_goes_as_it_was_stored(self) -> None:
        pinned = self._pinned()
        written = pinned_state_body(pinned)

        # Escaping every terminator would put the body past GitHub's limit,
        # and what is written instead is inside it.
        self.assertGreater(
            len(written) + _notice_payloads._ESCAPE_COST * self.terminators, MAX_PINNED_BODY,
        )
        self.assertLessEqual(len(written), MAX_PINNED_BODY)
        self.assertIn(_notice_payloads._COMMENT_CLOSE * 2, written)


class NamedExplanationTest(_notice_case._NoticeCase, unittest.TestCase):
    """A notice that names the recorded explanation rather than copying it.

    The explanation is already in the pinned comment, so a sentence carrying a
    second copy would be one the comment could not hold beside the record it
    came from -- and nothing supersedes this park, so an obligation nothing
    could write is a sentence no tick would ever say. What is stored is the
    sentence with the record named in it, and what reaches the thread is the
    whole of it, on the post and on every redelivery alike.
    """

    def test_a_maximal_explanation_is_still_said(self) -> None:
        # An explanation recorded into all but the room its own sentence was
        # reserved: a refused post still leaves an obligation, and what the
        # retry says carries the whole of it.
        with RefusedComment(self.github), self.assertRaises(RuntimeError):
            self._decide(_notice_payloads._NEAR_LIMIT_RUN)
        self.assertEqual(self.github.posted_comments, [])
        # The fixture is only a regression while the outcome really lands.
        self.assertEqual(
            self._pinned().get(KEYS.split_blocker), _notice_payloads._NEAR_LIMIT_BLOCKER,
        )

        self._adjudicate()

        said = [body for _number, body in self.github.posted_comments]
        self.assertEqual(len(said), SAID_ONCE)
        self.assertIn(_notice_payloads._NEAR_LIMIT_BLOCKER, said[0])

    def test_the_obligation_stays_within_its_reserve(self) -> None:
        # What makes the redelivery above possible at any explanation length:
        # the durable half is the sentence, not the prose it names, so what it
        # costs the comment is the same for a line and for a maximal one --
        # and it is inside the room the recorded outcome reserved for it.
        for named, run in (
            ("a line", SINGLE_RUN), ("a maximal one", _notice_payloads._NEAR_LIMIT_RUN),
        ):
            with self.subTest(explanation=named):
                self.setUp()
                with RefusedComment(self.github), self.assertRaises(
                    RuntimeError,
                ):
                    self._decide(run)

                self.assertLessEqual(
                    self._notice_cost(), _late_session.MAX_NOTICE_BODY,
                )

    def test_an_explanation_naming_the_marker(self) -> None:
        # Replacement does not re-scan what it inserts, so one pass leaves an
        # agent's own marker text where the agent wrote it. A second pass
        # would expand it as though this orchestrator had written it, and the
        # sentence posted and the sentence looked for would stop being the
        # same one -- so the thread would be told twice.
        self._say_it_and_lose_the_write(_notice_payloads._MARKER_RUN)
        self.assertIn(_notice_payloads._MARKER_BLOCKER, _notice_payloads._last_said(self.github))

        self._adjudicate()

        self._assert_said_once()

    def test_a_notice_on_the_thread_is_reconciled(self) -> None:
        # The other half of naming the record: what a later tick looks for on
        # the thread is the sentence with the explanation put back, so a write
        # that failed after its own post landed has to recognize that comment
        # rather than say the same thing to the same human twice.
        self._say_it_and_lose_the_write(_notice_payloads._NEAR_LIMIT_RUN)

        self._adjudicate()

        self._assert_said_once()

    def test_the_stored_notice_closes_nothing(self) -> None:
        # The obligation is written INTO the pinned comment, and that comment
        # is an HTML comment: a sentence carrying `-->` would close it early
        # and leave GitHub rendering the rest of the payload -- the recorded
        # result, the recovery fields -- as visible issue text. Naming the
        # explanation is what keeps an agent's prose out of the stored half,
        # so what is left there is this orchestrator's own wording -- and the
        # marker standing in for that prose is a bracketed token for the same
        # reason. An ordinary explanation is what makes the obligation the
        # only thing under test.
        with RefusedComment(self.github), self.assertRaises(RuntimeError):
            self._decide(SINGLE_RUN)

        pinned = self._pinned()
        body = pinned_state_body(pinned)

        self.assertIn(_late_notice.PARK_NOTICE, pinned)
        closes_at = len(body) - len(_notice_payloads._COMMENT_CLOSE)
        self.assertEqual(body.index(_notice_payloads._COMMENT_CLOSE), closes_at)
        self.assertIsNotNone(PINNED_STATE_BODY_RE.match(body))

    def _notice_cost(self) -> int:
        """What the standing obligation adds to this issue's pinned comment."""
        pinned = self._pinned()
        self.assertIn(_late_notice.PARK_NOTICE, pinned)
        return len(pinned_state_body(pinned)) - len(pinned_state_body({
            key: held
            for key, held in pinned.items()
            if key != _late_notice.PARK_NOTICE
        }))


class PiecedQuoteNoticeTest(GuardedLateCase, unittest.TestCase):
    """The explanation no single fence answers is still said, and said whole.

    A quote carrying a long LINE of each fence character can be closed by
    either one, and a fence long enough to survive both would come to twice
    the quote. It is blocked off in PIECES instead: the long lines land in
    blocks of their own, fenced by the character they do not carry, and the
    verdict is recorded exactly as any other `single` is.

    Refusing the outcome instead would cost both halves of what this park is
    for. `late_result_unrecordable` is superseded by the next attempt, so the
    refusal buys another decomposer run against a candidate already
    adjudicated -- and the `single` never reaches the park at all.
    """

    def test_the_single_reaches_its_own_park(self) -> None:
        outcome = self._decide(_notice_payloads._BOTH_RUNS_REPLY)
        pinned = self._pinned()

        self.assertEqual(outcome.disposition, _LateDisposition.PARKED)
        self.assertEqual(
            pinned.get(KEYS.park_reason), _late_park_state.PARK_SINGLE_DECISION,
        )
        self.assertEqual(pinned.get(KEYS.split_blocker), _notice_payloads._BOTH_RUNS_BLOCKER)

    def test_no_second_decomposer_is_paid_for(self) -> None:
        self._decide(_notice_payloads._BOTH_RUNS_REPLY)

        outcome, spawn = self._adjudicate()

        spawn.assert_not_called()
        self.assertEqual(outcome.disposition, _LateDisposition.PARKED)
        self.assertEqual(len(self.github.posted_comments), SAID_ONCE)

    def test_the_explanation_is_said_whole(self) -> None:
        self._decide(_notice_payloads._BOTH_RUNS_REPLY)

        said = _notice_payloads._last_said(self.github)

        self._assert_said_whole(said, _notice_payloads._BOTH_RUNS_BLOCKER)
        # The pieces come last, so the instruction is above all of them.
        instructions, _split, _quoted = said.partition(
            _notice_payloads._BOTH_RUNS_BLOCKER.split(_notice_payloads._LINE_BREAK)[0],
        )
        self.assertIn(_notice_payloads._REPLY_INSTRUCTION, instructions)
        self.assertNotIn(_notice_payloads._HTML_OPEN, instructions)

    def test_a_recovered_one_is_said_whole(self) -> None:
        # The same explanation off a record a tick already wrote, which is
        # what a park owing its sentence after a refused comment reads back.
        self.github.seed_state(self.issue.number, **{
            **_notice_payloads._legacy_record(),
            KEYS.split_blocker: _notice_payloads._BOTH_RUNS_BLOCKER,
        })

        self._adjudicate()

        self._assert_said_whole(_notice_payloads._last_said(self.github), _notice_payloads._BOTH_RUNS_BLOCKER)

    def _assert_said_whole(self, said: str, blocker: str) -> None:
        """Every line of this explanation is on the thread, inside the limit.

        Line by line, because what is blocked off in pieces has this
        orchestrator's own fences between them -- the explanation is whole,
        and the fences around it are not part of it.
        """
        for line in blocker.split(_notice_payloads._LINE_BREAK):
            self.assertIn(line, said)
        self.assertLessEqual(len(said), MAX_PINNED_BODY)


if __name__ == "__main__":
    unittest.main()


class RunsAndOpenersNoticeTest(GuardedLateCase, unittest.TestCase):
    """The quote that defeats a single fence AND opens HTML comments.

    The combination is the one neither answer covers alone: a fence long
    enough to survive a line of each character comes to twice the quote, and
    outside a block an opener is obeyed again -- GitHub renders nothing from
    it onwards, so the tail of the explanation would be in the comment body
    and off the page.

    Blocking the quote off in pieces answers both at once. The long lines land
    in pieces of their own, fenced by the character they do not carry, and
    every opener between them stays inside a block where it is shown rather
    than obeyed.
    """

    def test_the_combination_is_said_whole(self) -> None:
        self._decide(_notice_payloads._RUNS_AND_OPENERS_REPLY)

        said = _notice_payloads._last_said(self.github)

        for line in _notice_payloads._RUNS_AND_OPENERS_BLOCKER.split(_notice_payloads._LINE_BREAK):
            self.assertIn(line, said)
        self.assertIn(_notice_payloads._QUOTED_TAIL, said)
        self.assertLessEqual(len(said), MAX_PINNED_BODY)
        self.assertEqual(
            self._pinned().get(KEYS.split_blocker), _notice_payloads._RUNS_AND_OPENERS_BLOCKER,
        )

    def test_an_old_limit_record_is_said_whole(self) -> None:
        # The recovered half, at the ceiling a record could actually have been
        # written at: an older binary's `single`, filling the outcome budget,
        # whose explanation carries both the fence lines and the openers.
        self.github.seed_state(self.issue.number, **{
            **_notice_payloads._legacy_record(),
            KEYS.split_blocker: _notice_payloads._OLD_LIMIT_BLOCKER,
        })

        self._adjudicate()

        said = _notice_payloads._last_said(self.github)
        for line in _notice_payloads._OLD_LIMIT_BLOCKER.split(_notice_payloads._LINE_BREAK):
            self.assertIn(line, said)
        self.assertLessEqual(len(said), MAX_PINNED_BODY)

    def test_an_unblockable_quote_is_escaped(self) -> None:
        # Past what any pieces can hold, the quote goes in unblocked -- and
        # then the openers have to be escaped, since unblocked is where they
        # are obeyed.
        rendered = _late_notice._quoted(_notice_payloads._UNBLOCKABLE_BLOCKER)

        self.assertNotIn(_notice_payloads._HTML_OPEN, rendered)
        self.assertIn(_late_notice._ESCAPED_COMMENT_OPEN, rendered)
        self.assertLessEqual(len(rendered), _late_session.MAX_QUOTED_BLOCK)

    def test_nothing_renders_past_the_limit(self) -> None:
        # The one guarantee every road owes: a comment GitHub refuses is
        # rebuilt identically on every poll, so the park would stand with its
        # sentence owed and the human told nothing at all, for good.
        for named, blocker in (
            ("a plain one", _notice_payloads._NEAR_LIMIT_BLOCKER),
            ("one long line", _notice_payloads._BACKTICK_BLOCKER),
            ("a line of each", _notice_payloads._BOTH_RUNS_BLOCKER),
            ("those and openers", _notice_payloads._RUNS_AND_OPENERS_BLOCKER),
            ("an older binary's", _notice_payloads._OLD_LIMIT_BLOCKER),
            ("one nothing holds", _notice_payloads._UNBLOCKABLE_BLOCKER),
        ):
            with self.subTest(explanation=named):
                self.assertLessEqual(
                    len(_late_notice._quoted(blocker)),
                    _late_session.MAX_QUOTED_BLOCK,
                )

    def test_a_fence_line_closes_under_any_ending(self) -> None:
        # A quote whose own fence line ends with a carriage return is still a
        # quote that can close a block. Read as ordinary text it would be
        # blocked off at three backticks, GitHub would take the embedded fence
        # as the closer, and the opener behind it would hide the tail.
        for ending in _notice_payloads._LINE_ENDINGS:
            with self.subTest(ending=repr(ending)):
                blocker = _notice_payloads._fenced_and_opened(ending)

                rendered = _late_notice._quoted(blocker)

                self.assertIn(blocker, rendered)
                self.assertTrue(rendered.startswith(_notice_payloads._SHORTEST_TILDE_FENCE))
                self.assertFalse(
                    rendered.startswith(_notice_payloads._SHORTEST_BACKTICK_FENCE),
                )

    def test_an_ending_survives_delivery(self) -> None:
        # The line endings are the author's, not this orchestrator's: what
        # reaches the thread is what the agent wrote, terminators and all.
        blocker = _notice_payloads._fenced_and_opened(_notice_payloads._LINE_ENDINGS[0])
        self.github.seed_state(self.issue.number, **{
            **_notice_payloads._legacy_record(),
            KEYS.split_blocker: blocker,
        })

        self._adjudicate()

        said = _notice_payloads._last_said(self.github)
        self.assertIn(blocker, said)
        self.assertIn(_notice_payloads._HIDDEN_TAIL, said)
        self.assertLessEqual(len(said), MAX_PINNED_BODY)

    def test_what_nothing_renders_is_cut(self) -> None:
        # The last resort, and the only thing it is here for: a comment GitHub
        # refuses is rebuilt identically on every poll, so the park would
        # stand with its sentence owed for good. A cut quote says where it was
        # cut; a refused one says nothing, ever.
        with self.assertLogs(WORKFLOW_LOG, level=ERROR):
            rendered = _late_notice._quoted(_notice_payloads._UNSAYABLE_BLOCKER)

        self.assertLessEqual(len(rendered), _late_session.MAX_QUOTED_BLOCK)
        self.assertIn(_late_notice._CUT_QUOTE, rendered)
