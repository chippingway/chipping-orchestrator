# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What a whole tick does with a standing park, through the real seam.

The routing beside this asks which road a parked tick takes, with the
publication seam held still. These ask what happens when it is not: a tree the
seam reads for a second time, a head it proves for itself, a reading the seam
takes of its own -- or cannot take at all -- and a command that lands between
this park's own reading of the thread and the generic resume's. A double in the
seam's place answers none of them.
"""

from __future__ import annotations

import unittest
from unittest.mock import patch

from orchestrator.git.measurement.models import FrozenCommit
from orchestrator.git.verification.status import _WorktreeStatus
from orchestrator.workflow.stages.implementing import (
    late_command as _command,
    state as _state,
)
from tests.workflow.fixtures import MEASURED_CANDIDATE_SHA
from tests.workflow.interleaving import _RacesPastTheStep
from tests.workflow.stages.implementing import (
    late_consent_test_support as support,
)

_READS_THE_THREAD = "_reads_the_thread"

# What the push is named against, which is the whole of what a moved
# checkout would have changed.
_REVISION = "revision"

_CLEAN_TREE = _WorktreeStatus(readable=True)
_DIRTY_TREE = _WorktreeStatus(readable=True, paths=("src/left_behind.py",))

# A commit the checkout is standing on that the park's own record does not
# name: work that replaced what an operator decided about.
_MOVED_HEAD_SHA = "e" * support.SHA_LENGTH

# The same head read twice and answering differently: the recovery proves the
# checkout on the commit the park is about, the gate reads it again for
# itself, and the worktree is writable in between.
_HEAD_MOVES_MID_TICK = (
    FrozenCommit(sha=MEASURED_CANDIDATE_SHA),
    FrozenCommit(sha=_MOVED_HEAD_SHA),
)

# Enough polls of a park nothing clears to spend the bounded quiet retry and
# keep asking long after: what a refusal costs is decided per POLL, so a case
# that stopped at the notice would pin the sentence and not the silence.
_POLLS_PAST_THE_BOUND = 8

# A reading the ceiling lets through, so size is never what refuses a head
# nobody authorized: a park these cases see is the commit the record names
# being held against the checkout.
_SMALL_ADDITIONS = 12


def _assert_no_agent(case, mocks) -> None:
    """No developer was paid for on this tick, whatever else it decided."""
    mocks[support.RUN_AGENT].assert_not_called()


def _assert_held(case, mocks) -> None:
    """The tick spent nothing and moved the issue nowhere."""
    mocks[support.RUN_AGENT].assert_not_called()
    mocks[support.PUSH_BRANCH].assert_not_called()
    case.assertEqual(case.github.label_history, [])


class _LandsOneReply:
    """One operator writing one reply, the instant a step has run.

    A class rather than a closure because a seam this repository patches is a
    value with a name, and because the race has to fire ONCE: hung on a read
    and fired on every one of them, it would answer each later reading with a
    thread the one before it never saw and pin nothing at all.
    """

    def __init__(self, case, body: str = support.AUTHORIZE) -> None:
        self._case = case
        self._body = body
        self.landed = 0

    def __call__(self) -> None:
        if not self.landed:
            self.landed = self._case._reply(self._body)


class SeamHeldParkTest(support._ParkedCase, unittest.TestCase):
    """The park survives whatever the real publication seam does with it.

    Driven through a whole tick rather than against a mocked seam, because
    every one of these is the seam itself refusing: a tree it reads for a
    second time, a head it proves for itself, a sentence an earlier tick
    posted and never recorded. A double in its place answers none of them.
    """

    def test_the_command_publishes_on_a_whole_tick(self) -> None:
        # The routing end to end: a parked tick with no run to dispose reaches
        # the gate, the gate measures afresh, and the command an operator
        # already wrote is what publishes the branch.
        self._seed(**support.measured_pair())
        commanded = self._reply(support.AUTHORIZE)

        mocks = self._run_tick()

        mocks[support.PUSH_BRANCH].assert_called_once()
        _assert_no_agent(self, mocks)
        pinned = self._pinned()
        self.assertEqual(
            pinned[support.KEY_OVERRIDE_CANDIDATE_SHA], MEASURED_CANDIDATE_SHA,
        )
        self.assertEqual(pinned[support.KEY_OVERRIDE_COMMENT_ID], commanded)
        self.assertFalse(pinned[_state._AWAITING_HUMAN])

    def test_a_second_read_keeps_the_park(self) -> None:
        # The tree is read once before the seam is entered and again inside
        # it, and everything between is time something can write in. The
        # seam's own refusal parks under a reason of its own and its notice
        # moves the watermark past the command -- so the park is put back
        # rather than merely guarded, and the operator who cleans the tree is
        # not asked to authorize the same commit twice.
        self._seed(**support.measured_pair())
        self._reply(support.AUTHORIZE)

        mocks = self._run_tick(tree_states=(_CLEAN_TREE, _DIRTY_TREE))

        self._assert_still_parked(mocks)
        # The watermark travels with the park, and it is the half that decides
        # whether the operator has to write anything again: one the seam's
        # notice moved past the command is a decision thrown away.
        self.assertIsNotNone(
            _command._read_the_park(self.github, self.issue, self._state()),
        )

    def test_a_moved_head_keeps_the_park(self) -> None:
        # A clean checkout standing somewhere else passes every question about
        # the tree and is still not the commit anybody authorized: the record
        # froze one pair and the notice named it. Read small, the seam would
        # PUSH whatever it found there -- which is the one refusal the park
        # being put back afterwards cannot undo, since the work is on the
        # remote by then.
        self._seed(**support.measured_pair())
        self._reply(support.AUTHORIZE)

        mocks = self._run_tick(
            candidate_commit=FrozenCommit(sha=_MOVED_HEAD_SHA),
            added_lines=_SMALL_ADDITIONS,
        )

        self._assert_still_parked(mocks)

    def test_a_moved_head_after_a_failed_push_holds(self) -> None:
        # The same question one field over. A push that failed after the
        # authorization was recorded retires the generation and puts this park
        # back over the terms a human agreed to, so what names the commit on
        # the poll after it is the override rather than anything the freeze
        # left. Read off that, a head which has moved since is refused where
        # it stands and the terms stay on the record. Named by nothing, the
        # seam would measure whatever the checkout had become, and a reading
        # the ceiling lets through would push it under a command that
        # authorized another commit.
        self._seed(**support.measured_pair())
        self._reply(support.AUTHORIZE)
        self._run_tick(push_branch=False)

        mocks = self._run_tick(
            candidate_commit=FrozenCommit(sha=_MOVED_HEAD_SHA),
            added_lines=_SMALL_ADDITIONS,
        )

        self._assert_still_parked(mocks)
        self.assertEqual(
            self._pinned()[support.KEY_OVERRIDE_CANDIDATE_SHA],
            MEASURED_CANDIDATE_SHA,
        )

    def test_the_checkout_coming_back_publishes_it(self) -> None:
        # And what holding it buys, across the restart that follows: an
        # operator who puts the checkout back on the commit they authorized
        # gets that commit published, under the command they already wrote.
        self._seed(**support.measured_pair())
        self._reply(support.AUTHORIZE)
        self._run_tick(push_branch=False)
        self._run_tick(candidate_commit=FrozenCommit(sha=_MOVED_HEAD_SHA))

        mocks = self._run_tick()

        _assert_no_agent(self, mocks)
        self.assertEqual(
            mocks[support.PUSH_BRANCH].call_args.kwargs[_REVISION],
            MEASURED_CANDIDATE_SHA,
        )

    def test_a_head_moving_mid_tick_keeps_the_park(self) -> None:
        # The window asking first cannot close on its own: the head is proved
        # on the parked commit before the seam is entered and read again
        # inside it, and the worktree is writable in between. So the commit
        # travels on the work handed over and the gate holds its own read to
        # it -- a replacement landing there is refused before anything is
        # pushed or persisted, and the park comes back with the command still
        # standing. Carried nowhere, that replacement is measured as this
        # park's candidate, and one small enough for the ceiling is pushed and
        # the issue relabelled under a command and an override that name the
        # commit before it -- the one refusal putting the park back cannot
        # undo, since the work is on the remote by then.
        self._seed(**support.measured_pair())
        self._reply(support.AUTHORIZE)
        self._run_tick(push_branch=False)

        mocks = self._run_tick(
            candidate_commit=_HEAD_MOVES_MID_TICK,
            added_lines=_SMALL_ADDITIONS,
        )

        self._assert_still_parked(mocks)
        # And the operator is not asked twice: the reply they already wrote is
        # still the last fresh word for the poll the checkout settles on.
        self.assertIsNotNone(
            _command._read_the_park(self.github, self.issue, self._state()),
        )

    def _assert_still_parked(self, mocks) -> None:
        """Nobody was resumed, nothing was published, and the park stands."""
        _assert_held(self, mocks)
        pinned = self._pinned()
        self.assertTrue(pinned[_state._AWAITING_HUMAN])
        self.assertEqual(
            pinned[_state._PARK_REASON],
            _command.PARK_UNAUTHORIZED_EXEMPTION,
        )



class LostReadingHeldParkTest(support._ParkedCase, unittest.TestCase):
    """A reading the seam could not take, over a park waiting on a person.

    The size gate answers a lost base by counting a quiet miss and re-reading
    on the next poll, and a park its own reading is the answer to comes off in
    the same breath. This park is not one of those: what it waits for is an
    operator, and no reading anybody takes answers an operator. Unparked
    there, the exemption nobody stands behind publishes on the next poll under
    nobody's authority at all -- and the command that would have authorized it
    is consumed on the way.
    """

    def test_a_lost_reading_keeps_the_park(self) -> None:
        # A base this host cannot reach, inside the bound the quiet retry is
        # held to: nothing is measured, nothing is published, and the record
        # is left exactly as the tick found it -- park, reason, watermark and
        # the operator's command all still standing for the poll that can act
        # on them.
        self._seed(**support.measured_pair())
        self._reply(support.AUTHORIZE)

        mocks = self._run_tick(base_object_present=False)

        self._assert_held_as_found(mocks)
        self.assertIsNotNone(
            _command._read_the_park(self.github, self.issue, self._state()),
        )

    def test_the_base_coming_back_publishes(self) -> None:
        # And what holding it buys, across the restart that follows: the
        # transport clears itself, the poll after re-reads the same pair, and
        # the command the operator wrote in the first place is what publishes
        # the branch. Consumed on the missed tick instead, this poll would
        # find a thread with nothing on it and a park nobody could end.
        self._seed(**support.measured_pair())
        commanded = self._reply(support.AUTHORIZE)
        self._run_tick(base_object_present=False)

        mocks = self._run_tick()

        mocks[support.PUSH_BRANCH].assert_called_once()
        _assert_no_agent(self, mocks)
        self.assertEqual(
            self._pinned()[support.KEY_OVERRIDE_COMMENT_ID], commanded,
        )

    def test_a_lost_reading_keeps_a_silent_park(self) -> None:
        # The same rule where nobody has replied at all. A park still owing
        # the sentence that announces it reaches the seam on every poll, so a
        # lost reading there unparks an issue whose operator was never even
        # asked -- and the poll after publishes the adjudicated candidate with
        # no authorization recorded anywhere.
        self._seed(**{
            _state._HELD_RECEIPT: support.PARK_RECEIPT,
            **support.measured_pair(),
        })

        missed = self._run_tick(base_object_present=False)
        published = self._run_tick()

        self._assert_held_as_found(missed)
        self._assert_held_as_found(published)
        self.assertNotIn(support.KEY_OVERRIDE_CANDIDATE_SHA, self._pinned())

    def test_a_refusal_that_never_clears_is_said_once(self) -> None:
        # A base that does not come back, past the bound the quiet retry is
        # held to and well past it. Every poll of a standing park reaches the
        # seam, so the refusal happens again on every one of them, and each
        # poll is a fresh process -- the pinned record is the whole of what
        # carries an answer between them.
        #
        # The park the notice takes is rolled back with everything else the
        # seam decided, so the flags cannot say a human has been told; the
        # member the notice named is what says it, and it survives the
        # rollback. Said afresh each poll instead, our own notices alone fill
        # the ledger of the comments we have posted, and the earliest evicted
        # from it comes back as somebody's guidance: a developer paid to
        # answer our own sentence, over a watermark that swallowed the
        # operator's command on the way.
        self._seed(**support.measured_pair())
        self._reply(support.AUTHORIZE)

        for _ in range(_POLLS_PAST_THE_BOUND):
            mocks = self._run_tick(base_object_present=False)

        self.assertEqual(len(self.github.posted_comments), 1)
        self._assert_held_as_found(mocks)
        # And the command is still the last fresh word, for the poll the
        # transport finally lets act on it.
        self.assertIsNotNone(
            _command._read_the_park(self.github, self.issue, self._state()),
        )

    def _assert_held_as_found(self, mocks) -> None:
        """Nothing ran, nothing published, and the park stands over its thread."""
        _assert_held(self, mocks)
        self._assert_still_parked()
        self.assertEqual(
            self._pinned()[_state._LAST_ACTION_COMMENT_ID],
            support.PRIOR_ACTION_COMMENT_ID,
        )


class SpentCommandTest(support._ParkedCase, unittest.TestCase):
    """What a publication leaves of the reply that let it happen.

    The seam consumes the command itself wherever it records an authorization
    from it, and two of its roads never read the thread at all: a candidate
    the ceiling now lets through settles on its own count, and one an
    authorization already on the record covers publishes as decided. A command
    left behind on either goes with the issue to `validating`, where the next
    reader takes it for somebody's fresh feedback and sends the pull request
    back for a change -- the second developer run over committed work this
    whole road exists to avoid.
    """

    def test_a_small_remeasurement_spends_the_command(self) -> None:
        # The candidate is measured afresh on the tick that acts, so a ceiling
        # retuned since -- or a developer resumed since -- can put it under
        # one. Nobody has to authorize a change that size, so it publishes
        # without the record an authorization would leave, and the command is
        # spent by the handoff that carried the reading rather than by a gate
        # that never looked.
        self._seed(**support.measured_pair())
        commanded = self._reply(support.AUTHORIZE)

        mocks = self._run_tick(added_lines=_SMALL_ADDITIONS)

        self.assertNotIn(support.KEY_OVERRIDE_CANDIDATE_SHA, self._pinned())
        self._assert_spent(mocks, commanded)

    def test_a_decided_candidate_spends_the_command(self) -> None:
        # The other road that publishes without a reading. A push that failed
        # after the authorization was recorded leaves the terms on the record
        # and this park put back over them, so the retry recognizes the commit
        # as decided and pushes it -- past the door where the command would
        # otherwise have been consumed.
        self._seed(**support.measured_pair())
        commanded = self._reply(support.AUTHORIZE)
        self._run_tick(push_branch=False)

        mocks = self._run_tick()

        self._assert_spent(mocks, commanded)

    def test_guidance_mid_handoff_keeps_the_reply(self) -> None:
        # The one state a handoff may not spend on. The thread is read here
        # and again inside the seam, and an operator writing between the two
        # makes that second reading a park HELD rather than an authorization
        # recorded: guidance written over a command is the decision that
        # replaced it. Spent on the way out anyway, the reply the park is
        # still standing over would be consumed with nothing having acted on
        # it, and the poll that could act would never see it.
        self._seed(**support.measured_pair())
        self._reply(support.AUTHORIZE)
        landing = _LandsOneReply(self, support.GUIDANCE)

        with patch.object(
            _command, _READS_THE_THREAD,
            _RacesPastTheStep(_command._reads_the_thread, landing),
        ):
            mocks = self._run_tick()

        mocks[support.PUSH_BRANCH].assert_not_called()
        _assert_no_agent(self, mocks)
        self.assertEqual(
            self._pinned()[_state._LAST_ACTION_COMMENT_ID],
            support.PRIOR_ACTION_COMMENT_ID,
        )
        self._assert_still_parked()

    def _assert_spent(self, mocks, commanded: int) -> None:
        """The branch went out, nobody was resumed, and the reply is read."""
        mocks[support.PUSH_BRANCH].assert_called_once()
        _assert_no_agent(self, mocks)
        self.assertGreaterEqual(
            self._pinned()[_state._LAST_ACTION_COMMENT_ID], commanded,
        )


class CommandArrivalRaceTest(support._ParkedCase, unittest.TestCase):
    """A command that lands while this park's own thread is being read.

    The two questions a poll of this park asks -- is there a command, and has
    anybody spoken at all -- decide opposite things, so they come off ONE
    look. Asked from two, the command itself can land in between: the tick
    then reads a thread whose last word IS the command as guidance, hands it
    to the ordinary resume, and the resume consumes it past the watermark and
    pays for a developer over work that is committed already, leaving the park
    standing over a decision nothing can read again.
    """

    def test_a_command_landing_mid_read_is_kept(self) -> None:
        # Nothing runs and nothing is consumed. The reading found a thread
        # with nothing on it, so the tick is held where it stands -- and the
        # command that arrived just past that reading is still the last fresh
        # word for the poll that can act on it.
        self._seed(**support.measured_pair())
        landing = self._lands_the_command()

        with patch.object(
            _command, _READS_THE_THREAD,
            _RacesPastTheStep(_command._reads_the_thread, landing),
        ):
            mocks = self._run_tick()

        _assert_held(self, mocks)
        self.assertEqual(
            self._pinned()[_state._LAST_ACTION_COMMENT_ID],
            support.PRIOR_ACTION_COMMENT_ID,
        )
        self.assertIsNotNone(
            _command._read_the_park(self.github, self.issue, self._state()),
        )

    def test_a_command_landing_under_guidance_defers(self) -> None:
        # The resume branch, which the silent thread above never reaches. With
        # guidance already on the thread the classifying road hands the tick
        # back, and the generic resume then reads the thread AGAIN -- so a
        # command arriving between those two reads is in the resume's batch
        # and in nobody else's. Resumed on the guidance under it, the run that
        # follows parks and stamps the thread read to its own notice, which
        # lands above the command and takes it for good. So the whole tick is
        # deferred instead: nothing runs and nothing is consumed.
        self._seed(**support.measured_pair())
        landing = self._lands_the_command()

        with patch.object(
            _command, _READS_THE_THREAD,
            _RacesPastTheStep(_command._reads_the_thread, landing),
        ):
            mocks = self._run_tick_with_guidance()

        _assert_no_agent(self, mocks)
        self.assertEqual(
            self._pinned()[_state._LAST_ACTION_COMMENT_ID],
            support.PRIOR_ACTION_COMMENT_ID,
        )

    def test_the_deferred_command_publishes_next_poll(self) -> None:
        # What deferring buys, through the whole handler and across a restart:
        # the command the operator wrote is still the last fresh word, so the
        # poll after the one that stood aside reads it and publishes on it.
        self._seed(**support.measured_pair())
        landing = self._lands_the_command()
        with patch.object(
            _command, _READS_THE_THREAD,
            _RacesPastTheStep(_command._reads_the_thread, landing),
        ):
            self._run_tick_with_guidance()

        mocks = self._run_tick()

        mocks[support.PUSH_BRANCH].assert_called_once()
        _assert_no_agent(self, mocks)
        self.assertEqual(
            self._pinned()[support.KEY_OVERRIDE_COMMENT_ID], landing.landed,
        )

    def test_guidance_over_a_command_is_consumed(self) -> None:
        # The case deferring may NOT touch. A command with guidance above it
        # has been superseded -- the safe reading of somebody who asked to
        # publish and then asked for a change is the one that publishes
        # nothing -- so that batch is an ordinary resume and the developer
        # answers the change.
        self._seed(**support.measured_pair())
        self._reply(support.AUTHORIZE)
        guided = self._reply(support.GUIDANCE)

        mocks = self._run_tick()

        mocks[support.RUN_AGENT].assert_called_once()
        self.assertGreaterEqual(
            self._pinned()[_state._LAST_ACTION_COMMENT_ID], guided,
        )

    def _run_tick_with_guidance(self):
        """One whole tick over a park a human has already written guidance on."""
        self._reply(support.GUIDANCE)
        return self._run_tick()

    def _lands_the_command(self) -> _LandsOneReply:
        """The operator writing their command, ready to hang on a step."""
        return _LandsOneReply(self)


if __name__ == "__main__":
    unittest.main()
