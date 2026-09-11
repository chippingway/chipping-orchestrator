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
    PINNED_STATE_MARKER,
    pinned_state_body,
)
from orchestrator.workflow.stages.decomposition import (
    late_notice as _late_notice,
    late_park_state as _late_park_state,
    late_session as _late_session,
)
from orchestrator.workflow.stages.decomposition.late_models import (
    UNRECORDED_SPLIT_BLOCKER,
    _LateDisposition,
)
from tests.workflow.stages.decomposition.late_content_support import (
    RefusedComment,
)
from tests.workflow.stages.decomposition.late_run_support import agent_reply
from tests.workflow.stages.decomposition.late_settlement_support import (
    ERROR,
    KEY_LAST_ACTION_COMMENT_ID,
    SAID_ONCE,
    SINGLE_RUN,
    WORKFLOW_LOG,
    GuardedLateCase,
)
from tests.workflow.stages.decomposition.late_test_support import (
    CANDIDATE_SHA,
    KEYS,
    generation_state,
    late_block,
    late_generation,
)

# What separates the lines of a quote, and so what makes a run of fence
# characters a LINE that could close a block rather than a run inside one.
_LINE_BREAK = "\n"

# And how a JSON reply spells one, so a fixture can carry the fence LINES a
# quote is built out of.
_BACKSLASH = "\N{REVERSE SOLIDUS}"

_ESCAPED_LINE_BREAK = f"{_BACKSLASH}n"


def _single_reply(blocker: str):
    """One `single` reply carrying this explanation, line breaks and all.

    The reply is JSON, so a line break in an explanation is written as its
    escape -- which is what lets a fixture carry the fence LINES that are the
    only thing able to close a block.
    """
    written = blocker.replace(_BACKSLASH, _BACKSLASH * 2).replace(
        _LINE_BREAK, _ESCAPED_LINE_BREAK,
    )
    return agent_reply(late_block(
        '{"decision": "single", "rationale": "one coherent change",'
        f' "split_blocker": "{written}"}}'
    ))


# An explanation that writes the very marker the obligation names it by. The
# agent's own text, so it survives to the thread exactly as written -- and the
# sentence looked for there afterwards has to be the one that was posted.
_MARKER_BLOCKER = f"alpha {_late_notice.RECORDED_EXPLANATION} omega"

_MARKER_RUN = _single_reply(_MARKER_BLOCKER)

# A question whose own sentence writes the marker. Nothing this orchestrator
# worded, so the announcement carries it exactly as the agent asked it.
_QUESTION_MARKER_RUN = agent_reply(late_block(
    '{"decision": "question", "category": "scope_ambiguous",'
    f' "question": "which half {_late_notice.RECORDED_EXPLANATION} of it?"}}'
))

# What this issue's pinned comment holds besides the explanation -- the
# generation, the run identity, the watermarks -- with room to grow. Sized
# generously and guarded by the record actually landing: a fixture that
# outgrew it would refuse the outcome and fail loudly rather than quietly
# testing a comfortable case.
_ROOM_TO_SPARE = 2048

# An explanation recorded within a few hundred bytes of everything an outcome
# may take, so the room its own notice needs is the room the record left. A
# notice carrying a copy of it would not fit beside it; one naming it does.
_NEAR_LIMIT_BLOCKER = "b" * (_late_session.MAX_RECORDED_BODY - _ROOM_TO_SPARE)

_NEAR_LIMIT_RUN = _single_reply(_NEAR_LIMIT_BLOCKER)

# An explanation that opens this orchestrator's own pinned-state comment, over
# and over, at the length the record can just hold. Both halves matter: the
# marker is what the body test would hide the delivered notice behind, and the
# length is what any per-marker rewrite would push past what GitHub accepts.
_STATE_MARKER_BLOCKER = " ".join(
    PINNED_STATE_MARKER
    for _packed in range(
        (_late_session.MAX_RECORDED_BODY - _ROOM_TO_SPARE)
        // (len(PINNED_STATE_MARKER) + 1)
    )
)

_STATE_MARKER_RUN = _single_reply(_STATE_MARKER_BLOCKER)

# What ends the HTML comment the pinned state is written as. A sentence stored
# inside it that carried one would close it early.
_COMMENT_CLOSE = "-->"

# What OPENS one on a thread, and the fence that keeps a quote from being read
# as opening anything. The shortest fence is what an explanation carrying no
# backticks of its own is blocked off by.
_HTML_OPEN = "<!--"


_FENCE = "\n```\n"

_TILDE_FENCE = "\n~~~\n"

# An explanation carrying a fence LINE of each kind, with an opener behind
# them. A line that is a run and nothing else is the only thing that can close
# a block, so at the shortest fence this quote would close its own -- and two
# blocks cost more here than one fence a character wider, so the wider one is
# what it gets.
_FENCED_BLOCKER = "```\n~~~\nand <!-- after it"

_FENCED_RUN = _single_reply(_FENCED_BLOCKER)

_LONGER_FENCE = "\n````\n"

# The two shortest fences, named so a case can say which one blocked a quote
# off -- and so which one a quote of its own could have closed.
_SHORTEST_BACKTICK_FENCE = "```\n"

_SHORTEST_TILDE_FENCE = "~~~\n"

# A line of backticks as long as the record can hold. Blocked off by backticks
# it would be fenced by a longer run at both ends, so the block comes to three
# times the quote; blocked off by tildes it costs three characters at each end
# and the explanation reaches the thread whole.
_BACKTICK_BLOCKER = "`" * (_late_session.MAX_RECORDED_BODY - _ROOM_TO_SPARE)

_BACKTICK_RUN_REPLY = _single_reply(_BACKTICK_BLOCKER)

# The adversarial explanation: a long line of EACH fence character, so either
# one could close a block holding both and no single fence answers it under
# twice the quote. What answers it is blocking the quote off in PIECES.
_HALF_RUN = (_late_session.MAX_RECORDED_BODY - _ROOM_TO_SPARE) // 2

_BOTH_RUNS_BLOCKER = _LINE_BREAK.join(("`" * _HALF_RUN, "~" * _HALF_RUN))

_BOTH_RUNS_REPLY = _single_reply(_BOTH_RUNS_BLOCKER)

# And the two together, which is the case the reviewer's own reproduction is:
# a long fence line of each character AND the opener that makes GitHub render
# nothing from itself onwards wherever a block does not hold it. What a human
# has to still be able to read is everything past that opener.
_QUARTER_RUN = (_late_session.MAX_RECORDED_BODY - _ROOM_TO_SPARE) // 4

_QUOTED_TAIL = "and that is what stopped the split"


def _runs_and_openers(room: int) -> str:
    """A line of each fence character, then openers, then the tail.

    Sized to the room a record leaves, so the same shape can stand for a fresh
    outcome and for one an older binary wrote at its own ceiling.
    """
    run = room // 4
    spent = 2 * run + 2 + len(_QUOTED_TAIL)
    openers = _HTML_OPEN * ((room - spent) // len(_HTML_OPEN))
    return _LINE_BREAK.join((
        "`" * run, "~" * run, f"{openers}{_QUOTED_TAIL}",
    ))


_RUNS_AND_OPENERS_BLOCKER = _runs_and_openers(
    _late_session.MAX_RECORDED_BODY - _ROOM_TO_SPARE,
)

_RUNS_AND_OPENERS_REPLY = _single_reply(_RUNS_AND_OPENERS_BLOCKER)

# An explanation no block can hold: one fence short of everything a quote may
# take, so the block around it would not fit -- and carrying an opener, so the
# unblocked road it falls to has to escape that.
_UNBLOCKABLE_BLOCKER = "{padded}{opener}".format(
    padded="b" * (_late_session.MAX_QUOTED_BLOCK - 2 * len(_HTML_OPEN)),
    opener=_HTML_OPEN,
)

# What ends a line on the machine an explanation was written on. Markdown
# ends one on a carriage return as readily as on a newline, so a fence line
# arriving under either is a line that can close a block -- and one read as
# ordinary text would be blocked off by three characters it carries, with the
# opener behind it hiding the rest from a human.
_LINE_ENDINGS = ("\r\n", "\r", "\n")

_HIDDEN_TAIL = "the tail an opener would hide"


def _fenced_and_opened(ending: str) -> str:
    """An explanation whose own fence line rides on this line ending."""
    return ending.join(("before it", "```", f"{_HTML_OPEN} {_HIDDEN_TAIL}"))


# And the one nothing renders whole: every character an opener, at the length
# a quote may take, so blocking it off and escaping it both overflow. Nothing
# this binary records can be it, since an outcome is held to a smaller budget
# than a quote is -- what it stands for is the guarantee that no notice is
# ever one GitHub refuses and every poll rebuilds.
_UNSAYABLE_BLOCKER = _HTML_OPEN * (
    _late_session.MAX_QUOTED_BLOCK // len(_HTML_OPEN)
)

# The last thing the sentence tells a human, and so the thing an explanation
# swallowing the rest of it would cost them.
_REPLY_INSTRUCTION = "Reply with the change to make"

# A recorded `single` an older binary left: written when the whole outcome
# budget was the ceiling, so it sits past the reserve this one keeps and could
# never have paid it. The park it earns today still owes its sentence.
_LEGACY_ROOM_LEFT = 256

# What escaping the wrapper's own terminator costs the payload, measured
# rather than spelled: the record is the same either way and only its
# rendering grew, which is exactly the difference a notice may not be charged
# for.
_ESCAPE_COST = (
    len(pinned_state_body({KEYS.split_blocker: _COMMENT_CLOSE}))
    - len(pinned_state_body({KEYS.split_blocker: "abc"}))
)

# And so how many terminators a record has to carry for re-serializing it to
# cost more than the whole reserve its park's sentence is measured into.
_TERMINATORS = _late_session.MAX_NOTICE_BODY // _ESCAPE_COST + 1

# How many for escaping them to cost more than the comment GitHub takes at
# all: the headroom the outcome budget leaves under that limit, and one
# escape more. Past it the payload goes as it was stored, since a write
# refused for a RENDERING would take the park and the sentence it owes down
# with it.
_UNESCAPABLE_TERMINATORS = (
    (MAX_PINNED_BODY - _late_session.MAX_RECORDED_BODY) // _ESCAPE_COST + 1
)


def _last_said(github) -> str:
    """The body of the last comment this tick posted to the thread."""
    return github.posted_comments[-1][1]


def _legacy_record(terminators: int = 0, room_left: int = _LEGACY_ROOM_LEFT) -> dict:
    """The pinned comment a `single` recorded before the reserve existed.

    Sized against the comment as it was written THEN, so the case sits in the
    band between the two ceilings rather than near it: past what a `single`
    may be recorded with now, and inside what one could be recorded with then.

    `terminators` is how many of the wrapper's own terminators the record
    carries. They cost nothing in the rendering that accepted it and five
    characters each in today's, since the payload escapes them now -- a
    migration the sentence the park owes did not cause and cannot undo.
    """
    recorded = {
        **generation_state(late_generation()),
        KEYS.verdict: "single",
        KEYS.run_cycle_id: late_generation().cycle_id,
        KEYS.run_generation: late_generation().generation,
        KEYS.source_sha: CANDIDATE_SHA,
    }
    empty = len(pinned_state_body({**recorded, KEYS.split_blocker: ""}))
    padding = (
        _late_session.MAX_RECORDED_BODY - room_left - empty
        - len(_COMMENT_CLOSE) * terminators
    )
    return {
        **recorded,
        KEYS.split_blocker: _COMMENT_CLOSE * terminators + "b" * padding,
    }


# The same shape as `_RUNS_AND_OPENERS_BLOCKER` at the ceiling a record could
# actually have been written at, which is what an older binary's `single`
# left on a live issue.
_OLD_LIMIT_BLOCKER = _runs_and_openers(
    len(_legacy_record()[KEYS.split_blocker]),
)


class _NoticeCase(GuardedLateCase):
    """One unsplit park whose sentence landed and whose write did not.

    The window both readings below are taken in: the post and the write that
    records it are two operations, so what a crash between them leaves is an
    obligation standing over a thread that already carries the sentence.
    """

    def _say_it_and_lose_the_write(self, run) -> None:
        """Post this verdict's notice, then lose the write that recorded it.

        The post and the write are two operations, so what a crash between
        them leaves is an obligation standing over a thread that already
        carries the sentence -- and the watermark its mention moves back where
        the post found it. Reached by refusing the first attempt, which is
        what leaves the obligation readable before the post discharges it.
        """
        with RefusedComment(self.github), self.assertRaises(RuntimeError):
            self._decide(run)
        owed = self._pinned()
        self._adjudicate()
        self.github.seed_state(self.issue.number, **{
            **self._pinned(),
            _late_notice.PARK_NOTICE: owed[_late_notice.PARK_NOTICE],
            KEY_LAST_ACTION_COMMENT_ID: owed.get(KEY_LAST_ACTION_COMMENT_ID),
        })

    def _assert_said_once(self) -> None:
        """The thread carries the sentence once, and nothing owes it again."""
        self.assertEqual(len(self.github.posted_comments), SAID_ONCE)
        self.assertNotIn(_late_notice.PARK_NOTICE, self._pinned())


class _RefusedDeliveryCase(GuardedLateCase):
    """One record whose park is taken with the notice's comment refused.

    The window every case below is a regression inside: the park is durable
    and the sentence it owes is not yet on the thread, so what the pinned
    comment holds afterwards is the only thing that will ever say it.
    """

    def _refuse_the_notice(self) -> None:
        """Take the park, and lose the comment that would have explained it."""
        with RefusedComment(self.github), self.assertRaises(RuntimeError):
            self._adjudicate()


class LegacyRecordParkTest(_RefusedDeliveryCase, unittest.TestCase):
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
            self.issue.number, **_legacy_record(),
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


class _TerminatorRecordCase(_RefusedDeliveryCase):
    """A record carrying the wrapper's own terminator, at the old ceiling.

    Live on issues, written by a binary that rendered the payload without
    escaping those terminators -- an agent's explanation and a preserved
    pull-request body are where they come from. The record is unchanged and
    already durable; only what rendering it costs moved. Every case below is
    a regression about not charging the sentence its park owes for that.
    """

    terminators = 0

    def setUp(self) -> None:
        super().setUp()
        self.github.seed_state(
            self.issue.number,
            **_legacy_record(terminators=self.terminators, room_left=0),
        )

    def test_a_refused_notice_is_still_owed(self) -> None:
        self._refuse_the_notice()

        self.assertEqual(self.github.posted_comments, [])
        self.assertIn(_late_notice.PARK_NOTICE, self._pinned())

    def test_the_next_tick_says_it(self) -> None:
        self._refuse_the_notice()

        outcome, spawn = self._adjudicate()

        spawn.assert_not_called()
        self.assertEqual(outcome.disposition, _LateDisposition.PARKED)
        self.assertEqual(len(self.github.posted_comments), SAID_ONCE)
        self.assertNotIn(_late_notice.PARK_NOTICE, self._pinned())

    def test_the_comment_it_writes_still_fits(self) -> None:
        # The bound neither the raised ceiling nor the rendering may cross:
        # a comment GitHub refuses is one the park and its sentence ride out
        # on, and this park is one nothing supersedes.
        self._adjudicate()

        self.assertLessEqual(
            len(pinned_state_body(self._pinned())), MAX_PINNED_BODY,
        )


class ReserializedRecordParkTest(_TerminatorRecordCase, unittest.TestCase):
    """A record the escape grew past the reserve still gets its sentence said.

    Five characters an occurrence is enough, at this many terminators, to put
    a record accepted at the outcome budget outside the ceiling a notice is
    measured against. Charged that difference, the sentence is dropped -- and
    nothing supersedes this park, so a refused delivery would leave the issue
    parked for good over a thread nobody ever told.
    """

    terminators = _TERMINATORS

    def test_the_record_grew_past_the_old_ceiling(self) -> None:
        # The band this case is only a regression inside: inside the whole
        # outcome budget as it was written, and past that budget AND the
        # reserve beside it as it is written now.
        recorded = len(pinned_state_body(self._pinned()))

        self.assertLessEqual(
            recorded - _ESCAPE_COST * _TERMINATORS,
            _late_session.MAX_RECORDED_BODY,
        )
        self.assertGreater(
            recorded,
            _late_session.MAX_RECORDED_BODY + _late_session.MAX_NOTICE_BODY,
        )


class UnescapableRecordParkTest(_TerminatorRecordCase, unittest.TestCase):
    """A record the escape cannot render at all still gets its sentence said.

    At this many terminators the escaped payload is past what GitHub takes,
    and the write it would be refused on is the write the park and its notice
    ride out on. The record is what a later tick reads and the escape only
    decides how the comment looks, so the payload goes as it was stored --
    the rendering the binary that accepted it gave it, and one this parser
    still reads back whole.
    """

    terminators = _UNESCAPABLE_TERMINATORS

    def test_the_payload_goes_as_it_was_stored(self) -> None:
        pinned = self._pinned()
        written = pinned_state_body(pinned)

        # Escaping every terminator would put the body past GitHub's limit,
        # and what is written instead is inside it.
        self.assertGreater(
            len(written) + _ESCAPE_COST * self.terminators, MAX_PINNED_BODY,
        )
        self.assertLessEqual(len(written), MAX_PINNED_BODY)
        self.assertIn(_COMMENT_CLOSE * 2, written)


class NamedExplanationTest(_NoticeCase, unittest.TestCase):
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
            self._decide(_NEAR_LIMIT_RUN)
        self.assertEqual(self.github.posted_comments, [])
        # The fixture is only a regression while the outcome really lands.
        self.assertEqual(
            self._pinned().get(KEYS.split_blocker), _NEAR_LIMIT_BLOCKER,
        )

        self._adjudicate()

        said = [body for _number, body in self.github.posted_comments]
        self.assertEqual(len(said), SAID_ONCE)
        self.assertIn(_NEAR_LIMIT_BLOCKER, said[0])

    def test_the_obligation_stays_within_its_reserve(self) -> None:
        # What makes the redelivery above possible at any explanation length:
        # the durable half is the sentence, not the prose it names, so what it
        # costs the comment is the same for a line and for a maximal one --
        # and it is inside the room the recorded outcome reserved for it.
        for named, run in (
            ("a line", SINGLE_RUN), ("a maximal one", _NEAR_LIMIT_RUN),
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
        self._say_it_and_lose_the_write(_MARKER_RUN)
        self.assertIn(_MARKER_BLOCKER, _last_said(self.github))

        self._adjudicate()

        self._assert_said_once()

    def test_a_notice_on_the_thread_is_reconciled(self) -> None:
        # The other half of naming the record: what a later tick looks for on
        # the thread is the sentence with the explanation put back, so a write
        # that failed after its own post landed has to recognize that comment
        # rather than say the same thing to the same human twice.
        self._say_it_and_lose_the_write(_NEAR_LIMIT_RUN)

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
        closes_at = len(body) - len(_COMMENT_CLOSE)
        self.assertEqual(body.index(_COMMENT_CLOSE), closes_at)
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
        outcome = self._decide(_BOTH_RUNS_REPLY)
        pinned = self._pinned()

        self.assertEqual(outcome.disposition, _LateDisposition.PARKED)
        self.assertEqual(
            pinned.get(KEYS.park_reason), _late_park_state.PARK_SINGLE_DECISION,
        )
        self.assertEqual(pinned.get(KEYS.split_blocker), _BOTH_RUNS_BLOCKER)

    def test_no_second_decomposer_is_paid_for(self) -> None:
        self._decide(_BOTH_RUNS_REPLY)

        outcome, spawn = self._adjudicate()

        spawn.assert_not_called()
        self.assertEqual(outcome.disposition, _LateDisposition.PARKED)
        self.assertEqual(len(self.github.posted_comments), SAID_ONCE)

    def test_the_explanation_is_said_whole(self) -> None:
        self._decide(_BOTH_RUNS_REPLY)

        said = _last_said(self.github)

        self._assert_said_whole(said, _BOTH_RUNS_BLOCKER)
        # The pieces come last, so the instruction is above all of them.
        instructions, _split, _quoted = said.partition(
            _BOTH_RUNS_BLOCKER.split(_LINE_BREAK)[0],
        )
        self.assertIn(_REPLY_INSTRUCTION, instructions)
        self.assertNotIn(_HTML_OPEN, instructions)

    def test_a_recovered_one_is_said_whole(self) -> None:
        # The same explanation off a record a tick already wrote, which is
        # what a park owing its sentence after a refused comment reads back.
        self.github.seed_state(self.issue.number, **{
            **_legacy_record(),
            KEYS.split_blocker: _BOTH_RUNS_BLOCKER,
        })

        self._adjudicate()

        self._assert_said_whole(_last_said(self.github), _BOTH_RUNS_BLOCKER)

    def _assert_said_whole(self, said: str, blocker: str) -> None:
        """Every line of this explanation is on the thread, inside the limit.

        Line by line, because what is blocked off in pieces has this
        orchestrator's own fences between them -- the explanation is whole,
        and the fences around it are not part of it.
        """
        for line in blocker.split(_LINE_BREAK):
            self.assertIn(line, said)
        self.assertLessEqual(len(said), MAX_PINNED_BODY)


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
        self._decide(_RUNS_AND_OPENERS_REPLY)

        said = _last_said(self.github)

        for line in _RUNS_AND_OPENERS_BLOCKER.split(_LINE_BREAK):
            self.assertIn(line, said)
        self.assertIn(_QUOTED_TAIL, said)
        self.assertLessEqual(len(said), MAX_PINNED_BODY)
        self.assertEqual(
            self._pinned().get(KEYS.split_blocker), _RUNS_AND_OPENERS_BLOCKER,
        )

    def test_an_old_limit_record_is_said_whole(self) -> None:
        # The recovered half, at the ceiling a record could actually have been
        # written at: an older binary's `single`, filling the outcome budget,
        # whose explanation carries both the fence lines and the openers.
        self.github.seed_state(self.issue.number, **{
            **_legacy_record(),
            KEYS.split_blocker: _OLD_LIMIT_BLOCKER,
        })

        self._adjudicate()

        said = _last_said(self.github)
        for line in _OLD_LIMIT_BLOCKER.split(_LINE_BREAK):
            self.assertIn(line, said)
        self.assertLessEqual(len(said), MAX_PINNED_BODY)

    def test_an_unblockable_quote_is_escaped(self) -> None:
        # Past what any pieces can hold, the quote goes in unblocked -- and
        # then the openers have to be escaped, since unblocked is where they
        # are obeyed.
        rendered = _late_notice._quoted(_UNBLOCKABLE_BLOCKER)

        self.assertNotIn(_HTML_OPEN, rendered)
        self.assertIn(_late_notice._ESCAPED_COMMENT_OPEN, rendered)
        self.assertLessEqual(len(rendered), _late_session.MAX_QUOTED_BLOCK)

    def test_nothing_renders_past_the_limit(self) -> None:
        # The one guarantee every road owes: a comment GitHub refuses is
        # rebuilt identically on every poll, so the park would stand with its
        # sentence owed and the human told nothing at all, for good.
        for named, blocker in (
            ("a plain one", _NEAR_LIMIT_BLOCKER),
            ("one long line", _BACKTICK_BLOCKER),
            ("a line of each", _BOTH_RUNS_BLOCKER),
            ("those and openers", _RUNS_AND_OPENERS_BLOCKER),
            ("an older binary's", _OLD_LIMIT_BLOCKER),
            ("one nothing holds", _UNBLOCKABLE_BLOCKER),
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
        for ending in _LINE_ENDINGS:
            with self.subTest(ending=repr(ending)):
                blocker = _fenced_and_opened(ending)

                rendered = _late_notice._quoted(blocker)

                self.assertIn(blocker, rendered)
                self.assertTrue(rendered.startswith(_SHORTEST_TILDE_FENCE))
                self.assertFalse(
                    rendered.startswith(_SHORTEST_BACKTICK_FENCE),
                )

    def test_an_ending_survives_delivery(self) -> None:
        # The line endings are the author's, not this orchestrator's: what
        # reaches the thread is what the agent wrote, terminators and all.
        blocker = _fenced_and_opened(_LINE_ENDINGS[0])
        self.github.seed_state(self.issue.number, **{
            **_legacy_record(),
            KEYS.split_blocker: blocker,
        })

        self._adjudicate()

        said = _last_said(self.github)
        self.assertIn(blocker, said)
        self.assertIn(_HIDDEN_TAIL, said)
        self.assertLessEqual(len(said), MAX_PINNED_BODY)

    def test_what_nothing_renders_is_cut(self) -> None:
        # The last resort, and the only thing it is here for: a comment GitHub
        # refuses is rebuilt identically on every poll, so the park would
        # stand with its sentence owed for good. A cut quote says where it was
        # cut; a refused one says nothing, ever.
        with self.assertLogs(WORKFLOW_LOG, level=ERROR):
            rendered = _late_notice._quoted(_UNSAYABLE_BLOCKER)

        self.assertLessEqual(len(rendered), _late_session.MAX_QUOTED_BLOCK)
        self.assertIn(_late_notice._CUT_QUOTE, rendered)

class CarriedTextNoticeTest(_NoticeCase, unittest.TestCase):
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
        self._say_it_and_lose_the_write(_STATE_MARKER_RUN)
        said = _last_said(self.github)
        self.assertIn(PINNED_STATE_MARKER, said)
        self.assertLessEqual(len(said), MAX_PINNED_BODY)
        self.assertIn(_STATE_MARKER_BLOCKER, said)

        self._adjudicate()

        self._assert_said_once()

    def test_the_instructions_survive_the_quote(self) -> None:
        # A thread is markdown, so an explanation opening an HTML comment
        # swallows everything after it: quoted mid-sentence, it would leave a
        # human reading as far as the quote and told neither what the agent
        # said nor what to do about it. The quote comes last and inside a
        # fence, which a thread shows rather than obeys.
        self._decide(_STATE_MARKER_RUN)

        said = _last_said(self.github)
        instructions, _opened, quoted = said.partition(_FENCE)

        self.assertNotIn(_HTML_OPEN, instructions)
        self.assertIn(_REPLY_INSTRUCTION, instructions)
        self.assertIn(_STATE_MARKER_BLOCKER, quoted)

    def test_a_quote_carrying_a_fence(self) -> None:
        # Markdown closes a fenced block on a run of its own character at
        # least as long as the one that opened it, so a quote carrying a fence
        # of each kind would close either one early and let what follows
        # render as markdown again -- which is the failure the fence is here
        # to prevent. Neither character is cheap here, so the tie goes to the
        # ordinary one and the fence is the longer run.
        self._decide(_FENCED_RUN)

        said = _last_said(self.github)
        instructions, _opened, quoted = said.partition(_LONGER_FENCE)

        self.assertNotIn(_HTML_OPEN, instructions)
        self.assertIn(_FENCED_BLOCKER, quoted)

    def test_a_quote_of_fences_is_still_said(self) -> None:
        # A run of backticks is nothing to a tilde fence, so the explanation a
        # single fence character could not have blocked off at all costs three
        # characters at each end and reaches the thread whole. Saying a piece
        # of it would tell a human less than the record holds about what their
        # unpublished candidate is waiting on.
        self._say_it_and_lose_the_write(_BACKTICK_RUN_REPLY)
        said = _last_said(self.github)
        self.assertLessEqual(len(said), MAX_PINNED_BODY)
        self.assertIn(_TILDE_FENCE, said)
        self.assertIn(_BACKTICK_BLOCKER, said)

        self._adjudicate()

        self._assert_said_once()

    def test_a_question_with_the_marker_is_kept(self) -> None:
        self._decide(_QUESTION_MARKER_RUN)

        said = _last_said(self.github)
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


if __name__ == "__main__":
    unittest.main()
