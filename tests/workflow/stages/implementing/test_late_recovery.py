# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Where a parked issue's committed work goes when the park is answered.

Every park the size gate takes is answered ahead of the spawn, because on all
three the work in question is committed already: the road below would buy a
second developer run for an implementation the first one finished. What each
hands its answer to is the same publication seam that work came out of, so a
recovery reaches exactly the outcomes a fresh disposition does and decides
nothing the gate would have decided.

Which is why every case here is a whole tick over a seeded issue. What a road
did is read off the branch it pushed, the label it moved, the sentence it
said and the pinned comment it left -- the four a fresh disposition is read by
-- and the poll after it is run wherever holding quietly is what the road was
for.
"""

from __future__ import annotations

import unittest
from pathlib import Path
from types import MappingProxyType
from unittest.mock import patch

from orchestrator import config
from orchestrator.git.measurement.models import FingerprintFailure, FrozenCommit
from orchestrator.git.verification.status import _WorktreeStatus
from orchestrator.workflow.stages.implementing import (
    late_command as _late_command,
    late_measurement_state as _late_measurement_state,
    late_park_retirement as _late_park_retirement,
    state as _state,
)
from tests.workflow.fixtures import MEASURED_CANDIDATE_SHA, SHA_LENGTH
from tests.workflow.stages.implementing import (
    late_consent_case as _consent_case,
    late_consent_payloads as _consent_payloads,
)

# A checkout the recovery's existence probe never finds, which is the one
# outcome the publication seam cannot reach on its own: there is no commit to
# read there and a fresh run would answer with different work.
_MISSING_WORKTREE = Path("/tmp/orchestrator-test-late-recovery-gone")

# The two readings that say a checkout carries something no push would
# publish: a tree git named files in, and one nothing could read -- which is
# not a clean tree either.
_DIRTY_TREE = _WorktreeStatus(readable=True, paths=("src/left_behind.py",))
_UNREADABLE_TREE = _WorktreeStatus(readable=False)

# A commit the checkout is standing on that the park's own record does not
# name: work that replaced what an operator decided about.
_MOVED_HEAD_SHA = "e" * SHA_LENGTH

# Every way a checkout can fail the reading taken before an authorized
# candidate is handed over. All three earn the same answer -- none of them is
# anybody's decision, so none may spend the one already on the thread.
_UNPUBLISHABLE_CHECKOUTS = (
    ("carrying uncommitted work", MappingProxyType({"tree_states": (_DIRTY_TREE,)})),
    ("unreadable", MappingProxyType({"tree_states": (_UNREADABLE_TREE,)})),
    ("gone from this host", MappingProxyType({"worktree": _MISSING_WORKTREE})),
)

# The two ways the checkout a moved-candidate park is waiting on can fail to
# answer it, neither of which anybody can reply their way out of.
_UNANSWERING_CHECKOUTS = (
    (
        "standing somewhere else",
        MappingProxyType({"candidate_commit": FrozenCommit(sha=_MOVED_HEAD_SHA)}),
    ),
    ("gone from this host", MappingProxyType({"worktree": _MISSING_WORKTREE})),
)


class UnauthorizedExemptionRecoveryTest(_consent_case._ParkedCase, unittest.TestCase):
    """The command that ends the authorization park, and every reply that is not.

    The command is recognized here and ACTED on where the reading is, because
    that is where the terms of an authorization come from. So what a case asks
    is which road the whole tick took: the publication the command earns, the
    sentence a command naming another commit earns, or the developer guidance
    buys.
    """

    def setUp(self) -> None:
        super().setUp()
        self._seed(**_consent_payloads.measured_pair())

    def test_the_command_publishes_the_candidate(self) -> None:
        # The road everything else here exists to protect: the reply an
        # operator wrote publishes the commit it names, under terms recorded
        # from the reading this tick took, and buys no developer run over work
        # that is committed already.
        commanded = self._reply(_consent_payloads.AUTHORIZE)

        mocks = self._run_tick()

        self._assert_published(mocks)
        pinned = self._pinned()
        self.assertEqual(
            pinned[_consent_payloads.KEY_OVERRIDE_CANDIDATE_SHA],
            MEASURED_CANDIDATE_SHA,
        )
        self.assertEqual(
            pinned[_consent_payloads.KEY_OVERRIDE_COMMENT_ID], commanded,
        )
        self.assertEqual(pinned[_state._LAST_ACTION_COMMENT_ID], commanded)
        self.assertFalse(pinned[_state._AWAITING_HUMAN])
        self.assertIsNone(pinned[_state._PARK_REASON])

    def test_the_next_poll_opens_no_second_pr(self) -> None:
        # What the record a command-publication leaves is worth to the poll
        # after it. The issue is `validating`'s from the relabel on, so a tick
        # that still reaches this handler is one that re-entered a window it
        # has already finished -- and the receipt group this road wrote is
        # what closes it: the pull request the work is on is proved from the
        # remote and reused, rather than a second one being opened over a
        # branch the first already carries.
        self._reply(_consent_payloads.AUTHORIZE)
        self._run_tick()
        announced = len(self.github.posted_comments)

        mocks = self._run_tick()

        self._assert_no_agent(mocks)
        self.assertEqual(len(self.github.opened_prs), 1)
        self.assertEqual(len(self.github.posted_comments), announced)
        # The push it does make is leased against the commit already on the
        # remote, so a branch somebody moved in between rejects it instead of
        # being force-overwritten.
        self.assertEqual(
            mocks[_consent_payloads.PUSH_BRANCH].call_args.kwargs[
                _consent_payloads.FORCE_WITH_LEASE
            ],
            MEASURED_CANDIDATE_SHA,
        )
        opened = self.github.opened_prs[0].number
        pinned = self._pinned()
        self.assertEqual(pinned[_consent_payloads.KEY_PR_NUMBER], opened)
        self.assertEqual(pinned[_consent_payloads.KEY_PUBLISHED_PR], opened)

    def test_a_command_for_another_commit_is_answered(self) -> None:
        # Left unrouted, a reply that is not the exact command would fall to
        # the ordinary resume and spend a developer over committed work. The
        # sentence it earns is the gate's to say, since only the owner holding
        # a reading knows which candidate is waiting -- so what lands is that
        # sentence, spelling out the command that would have worked, over a
        # park and a watermark the refusal leaves exactly as it found them. An
        # abbreviation is answered the same way, since nothing in this domain
        # writes one.
        for described, written in (
            ("another commit", _consent_payloads.AUTHORIZE_ANOTHER),
            ("an abbreviation", _consent_payloads.AUTHORIZE_ABBREVIATED),
        ):
            with self.subTest(command=described):
                self.setUp()
                self._reply(written)

                mocks = self._run_tick()
                # And the poll after it says nothing new: our own sentence is
                # in the ledger, so nothing reads it back as fresh guidance.
                self._run_tick()

                self._assert_held(mocks)
                self._assert_still_parked()
                self.assertEqual(len(self.github.posted_comments), 1)
                self.assertIn(
                    _consent_payloads.AUTHORIZE, self.github.posted_comments[0][1],
                )
                self.assertEqual(
                    self._pinned()[_state._LAST_ACTION_COMMENT_ID],
                    _consent_payloads.PRIOR_ACTION_COMMENT_ID,
                )

    def test_guidance_is_left_for_the_resume(self) -> None:
        # A reply whose last word is not the command belongs to the road that
        # feeds it to the developer -- so the developer runs, and the reply is
        # consumed by the run that answered it rather than by this park.
        guided = self._reply(_consent_payloads.GUIDANCE)

        mocks = self._run_tick()

        mocks[_consent_payloads.RUN_AGENT].assert_called_once()
        mocks[_consent_payloads.PUSH_BRANCH].assert_not_called()
        # Consumed to the sentence that run's own park posted, which is above
        # the guidance it answered and is the last word on the thread: the
        # reply is spent, and a watermark past it would swallow whatever the
        # operator writes next.
        said = self._thread_tip()
        self.assertGreater(said, guided)
        self.assertEqual(
            self._pinned()[_state._LAST_ACTION_COMMENT_ID], said,
        )

    def test_another_park_is_not_this_road(self) -> None:
        # The door. An issue waiting on something else is not this park's to
        # end, and a tick that claimed it would hold every other park in the
        # stage on a thread nobody read -- so the command reaches the ordinary
        # resume, which is what an issue parked on a timeout is owed.
        self._seed(**{
            _state._PARK_REASON: _state._AGENT_TIMEOUT,
            **_consent_payloads.measured_pair(),
        })
        self._reply(_consent_payloads.AUTHORIZE)

        mocks = self._run_tick()

        mocks[_consent_payloads.RUN_AGENT].assert_called_once()
        mocks[_consent_payloads.PUSH_BRANCH].assert_not_called()

    def test_a_lost_reading_leaves_the_park(self) -> None:
        # The write that records the authorization is the write that takes the
        # park off, so a tick that could not fingerprint the pair leaves the
        # issue exactly as parked as it found it rather than durably unparking
        # one nothing published. Nothing about that is the operator's doing,
        # so the command is still the last fresh word -- and the poll that can
        # read the pair publishes on it without asking them twice.
        commanded = self._reply(_consent_payloads.AUTHORIZE)

        held = self._run_tick(
            contribution_digest=FingerprintFailure.CONTENT_ABSENT,
        )

        self._assert_held(held)
        self._assert_still_parked()
        self.assertEqual(
            self._pinned()[_state._LAST_ACTION_COMMENT_ID],
            _consent_payloads.PRIOR_ACTION_COMMENT_ID,
        )
        self.assertNotIn(
            _consent_payloads.KEY_OVERRIDE_CANDIDATE_SHA, self._pinned(),
        )
        self.assertEqual(self.github.posted_comments, [])

        published = self._run_tick()

        self._assert_published(published)
        self.assertEqual(
            self._pinned()[_consent_payloads.KEY_OVERRIDE_COMMENT_ID], commanded,
        )


class SilentParkHoldTest(_consent_case._ParkedCase, unittest.TestCase):
    """The poll of a park nobody whose word counts has answered.

    It owns the tick so nothing below pays for a developer over committed
    work, and it buys no reading, no write and no word to say what it said
    last time: a park waiting on a person answers the same way every poll
    until one arrives.
    """

    def setUp(self) -> None:
        super().setUp()
        self._seed(**_consent_payloads.measured_pair())

    def test_a_thread_nobody_wrote_on_is_held(self) -> None:
        before = dict(self._pinned())

        mocks = self._run_tick()

        self._assert_held(mocks)
        self._assert_wrote_nothing()
        self.assertEqual(self._pinned(), before)

    def test_an_outsider_is_nobody_speaking(self) -> None:
        # The allowlist's rule applied where the thread is read: nothing an
        # outsider posts is a decision or guidance, so the park is held on the
        # same terms a silent thread is -- down to the write it does not buy.
        before = dict(self._pinned())
        with patch.object(
            config,
            _consent_payloads.ALLOWLIST_CONFIG,
            (_consent_payloads.TRUSTED_AUTHOR,),
        ):
            self._reply(
                _consent_payloads.AUTHORIZE, author=_consent_payloads.OUTSIDER,
            )
            mocks = self._run_tick()

        self._assert_held(mocks)
        self._assert_wrote_nothing()
        self.assertEqual(self._pinned(), before)


class MeasurementParkRecoveryTest(_consent_case._ParkedCase, unittest.TestCase):
    """The bare continue that asks for one more reading of the candidate.

    Deliberately not a session retry. What failed was a READING, and the
    developer that produced the commit finished long ago -- so the committed
    work goes back through the publication seam, nobody is spawned, and what
    the reading answers is what the tick does with it.
    """

    def setUp(self) -> None:
        super().setUp()
        self._seed(**{
            _state._PARK_REASON: _late_measurement_state.PARK_MEASUREMENT_FAILED,
            **_consent_payloads.measured_pair(),
        })

    def test_a_small_reading_publishes_the_commit(self) -> None:
        # The reading is re-taken on the tick that acts, so a ceiling retuned
        # since can put the same commit under one: it publishes without
        # anybody's authorization and without another developer run. The
        # command is consumed by the retry, which is safe only because every
        # reply on this road is a bare continue.
        commanded = self._reply(_consent_payloads.CONTINUE)

        mocks = self._run_tick(added_lines=_consent_payloads.SMALL_ADDITIONS)

        self._assert_published(mocks)
        pinned = self._pinned()
        self.assertEqual(pinned[_state._LAST_ACTION_COMMENT_ID], commanded)
        self.assertFalse(pinned[_state._AWAITING_HUMAN])
        self.assertIsNone(pinned[_state._PARK_REASON])

    def test_an_oversized_reading_parks_again(self) -> None:
        # The other answer the retaken reading can give, and the whole of why
        # the retry is not a publication: a count still past the ceiling hands
        # the issue to the park an adjudicated candidate nobody has authorized
        # waits on, with one sentence saying so and no developer spawned.
        commanded = self._reply(_consent_payloads.CONTINUE)

        mocks = self._run_tick()

        self._assert_held(mocks)
        self._assert_still_parked()
        self.assertEqual(len(self.github.posted_comments), 1)
        # The continue is spent by the retry that read it, and the notice this
        # reading earned moves the boundary to itself and no further -- so the
        # poll after finds the thread read to our own sentence.
        said = self._thread_tip()
        self.assertGreater(said, commanded)
        self.assertEqual(
            self._pinned()[_state._LAST_ACTION_COMMENT_ID], said,
        )

    def test_guidance_is_left_for_the_resume(self) -> None:
        # A reply carrying real words is guidance, which belongs to the
        # ordinary resume that feeds it to the developer rather than to a
        # retry that would re-read a pair nobody asked about again.
        guided = self._reply(_consent_payloads.GUIDANCE)

        mocks = self._run_tick()

        mocks[_consent_payloads.RUN_AGENT].assert_called_once()
        mocks[_consent_payloads.PUSH_BRANCH].assert_not_called()
        # Consumed to the sentence that run's own park posted, which is above
        # the guidance it answered and is the last word on the thread: the
        # reply is spent, and a watermark past it would swallow whatever the
        # operator writes next.
        said = self._thread_tip()
        self.assertGreater(said, guided)
        self.assertEqual(
            self._pinned()[_state._LAST_ACTION_COMMENT_ID], said,
        )

    def test_a_missing_checkout_takes_its_own_park(self) -> None:
        # The one outcome the seam cannot reach on its own, and the road where
        # re-parking costs nobody anything: the answer was a bare continue,
        # spent by the tick that read it, so the next continue retries it once
        # the worktree is back. What it may not do is re-run the developer --
        # the recorded commit is the evidence a fresh checkout cannot supply.
        self._reply(_consent_payloads.CONTINUE)

        mocks = self._run_tick(worktree=_MISSING_WORKTREE)

        self._assert_held(mocks)
        pinned = self._pinned()
        self.assertTrue(pinned[_state._AWAITING_HUMAN])
        self.assertEqual(
            pinned[_state._PARK_REASON],
            _late_measurement_state.PARK_MEASUREMENT_FAILED,
        )
        self.assertEqual(len(self.github.posted_comments), 1)


class MovedCandidateRecoveryTest(_consent_case._ParkedCase, unittest.TestCase):
    """The park no reply can end, left standing by a checkout that cannot answer.

    What that park refused was the HANDOFF -- the commit was measured and
    approved, and the checkout was somewhere else -- so what settles it is the
    worktree, not guidance and not another developer run. The publication a
    restored checkout earns is pinned down beside the handoff that takes the
    park; what belongs here is the door, which is quiet on every tick the
    checkout has not answered yet.
    """

    def setUp(self) -> None:
        super().setUp()
        self._seed(**{
            _state._PARK_REASON: _state._CANDIDATE_MOVED,
            _state._APPROVED_SHA: MEASURED_CANDIDATE_SHA,
        })

    def test_a_checkout_that_cannot_answer_is_quiet(self) -> None:
        # Quiet by design, and on both readings alike: every tick asks one
        # local question and says nothing until the answer changes, so an
        # operator who leaves the worktree where it is -- or who is waiting on
        # the host that holds it -- is not told the same thing once a tick.
        # The approved commit stays on the record, which is what the poll
        # after the checkout comes back publishes against.
        for described, held in _UNANSWERING_CHECKOUTS:
            with self.subTest(checkout=described):
                self.setUp()

                mocks = self._run_tick(**held)

                self._assert_held(mocks)
                self.assertEqual(self.github.posted_comments, [])
                pinned = self._pinned()
                self.assertTrue(pinned[_state._AWAITING_HUMAN])
                self.assertEqual(
                    pinned[_state._PARK_REASON], _state._CANDIDATE_MOVED,
                )
                self.assertEqual(
                    pinned[_state._APPROVED_SHA], MEASURED_CANDIDATE_SHA,
                )


class UnpublishableCheckoutHoldTest(_consent_case._ParkedCase, unittest.TestCase):
    """Every road that answers the command and reaches no publication.

    A checkout the seam would refuse is not a decision anybody made, so
    nothing about it may spend the decision already on the thread. Held
    silently, the park, the command and the record are all still there for the
    poll that finds the worktree back.
    """

    def setUp(self) -> None:
        super().setUp()
        self._seed(**_consent_payloads.measured_pair())

    def test_an_unpublishable_checkout_writes_nothing(self) -> None:
        # The seam below reads the tree before a verdict can be recorded, and
        # its refusal parks under a reason of its own whose notice moves the
        # watermark past the command still standing -- so the operator would
        # be asked to authorize the same commit again once they fixed the
        # checkout. Asked here instead, the tick makes no write at all: not
        # the park, not the watermark, and not a word on the thread.
        for described, held in _UNPUBLISHABLE_CHECKOUTS:
            with self.subTest(checkout=described):
                self.setUp()
                self._reply(_consent_payloads.AUTHORIZE)
                before = dict(self._pinned())

                mocks = self._run_tick(**held)

                self._assert_held(mocks)
                self._assert_wrote_nothing()
                self.assertEqual(self._pinned(), before)

    def test_a_fixed_checkout_needs_no_command(self) -> None:
        # The whole of what holding quietly buys, from all three holds: the
        # command the operator already wrote is still the last fresh word on
        # the thread, so the poll after they fix the checkout publishes on it
        # without their being asked to decide a second time.
        for described, held in _UNPUBLISHABLE_CHECKOUTS:
            with self.subTest(checkout=described):
                self.setUp()
                commanded = self._reply(_consent_payloads.AUTHORIZE)
                self._run_tick(**held)

                mocks = self._run_tick()

                self._assert_published(mocks)
                self.assertEqual(
                    self._pinned()[_consent_payloads.KEY_OVERRIDE_COMMENT_ID],
                    commanded,
                )


# Which retirement may end which park, over all four pairings. A reading
# answers the park a reading was owed; a publication under an authorization
# answers that one. The crossed cells are what the table is for -- above all a
# lost base counting a quiet retry, which must leave an operator who has not
# replied exactly where it found them.
_RETIREMENTS = (
    (_late_park_retirement._retire_spent_park, _late_measurement_state.PARK_MEASUREMENT_FAILED, False),
    (
        _late_park_retirement._retire_spent_park,
        _late_command.PARK_UNAUTHORIZED_EXEMPTION,
        True,
    ),
    (
        _late_park_retirement._retire_authorized_park,
        _late_command.PARK_UNAUTHORIZED_EXEMPTION,
        False,
    ),
    (
        _late_park_retirement._retire_authorized_park,
        _late_measurement_state.PARK_MEASUREMENT_FAILED,
        True,
    ),
)


class RetiredParkTest(_consent_case._ParkedCase, unittest.TestCase):
    """Which of the two parks the size gate takes one road may take down.

    Apart from the roads above because no tick there can tell them apart: the
    rollback puts back whatever a call that published nothing cleared, so a
    retirement taken on the wrong park is invisible from a whole tick. What it
    costs is paid on the roads that reach this gate without one -- and what it
    would cost is an issue durably unparked whose operator never replied, with
    the exemption nobody stands behind publishing on the next poll under
    nobody's authority at all.
    """

    def test_each_road_ends_only_its_own_park(self) -> None:
        for retiring, reason, stands in _RETIREMENTS:
            with self.subTest(retiring=retiring.__name__, reason=reason):
                self._seed(parked=False, **{
                    _state._AWAITING_HUMAN: True,
                    _state._PARK_REASON: reason,
                })
                parked = self._state()

                retiring(parked)

                self.assertEqual(parked.get(_state._AWAITING_HUMAN), stands)
                self.assertEqual(
                    parked.get(_state._PARK_REASON), reason if stands else None,
                )


if __name__ == "__main__":
    unittest.main()
