# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Where a parked issue's committed work goes when the park is answered.

Every park the size gate takes is answered ahead of the spawn, because on all
three the work in question is committed already: the road below would buy a
second developer run for an implementation the first one finished. What each
hands its answer to is the same publication seam that work came out of, so a
recovery reaches exactly the outcomes a fresh disposition does and decides
nothing the gate would have decided.
"""

from __future__ import annotations

import unittest
from dataclasses import dataclass
from pathlib import Path
from unittest.mock import patch

from orchestrator.config import settings as config
from orchestrator.git.verification import status as _worktree_status
from orchestrator.git.verification.status import _WorktreeStatus
from orchestrator.git.worktrees import paths as _worktree_paths
from orchestrator.workflow.stages.implementing import (
    candidate_recovery as _candidate_recovery,
    checkout_recovery as _checkout_recovery,
    late_command as _late_command,
    late_evidence as _late_evidence,
    late_parks as _late_parks,
    late_recovery as _recovery,
    state as _state,
)
from tests.workflow.fixtures import _TEST_SPEC, MEASURED_CANDIDATE_SHA, SHA_LENGTH
from tests.workflow.stages.implementing import (
    late_consent_case as _consent_case,
    late_consent_payloads as _consent_payloads,
)

_PUBLISH_COMMITTED_WORK = "_publish_committed_work"
_RESTORED_CHECKOUT = "_restored_checkout"
_OFF_THE_PARKED_COMMIT = "_off_the_parked_commit"
_READS_THE_THREAD = "_reads_the_thread"
_GIVES_UP_A_LOST_SENTENCE = "_gives_up_a_lost_sentence"
_RESUME_DEV_WITH_TEXT = "_resume_dev_with_text"
_HOLDS_MOVED_CANDIDATE = "_holds_moved_candidate"
_WORKTREE_STATUS = "_worktree_status"

# A checkout the recovery's existence probe never finds, which is the one
# outcome the publication seam cannot reach on its own: there is no commit to
# read there and a fresh run would answer with different work.
_MISSING_WORKTREE = Path("/tmp/orchestrator-test-late-recovery-gone")

# The three readings a checkout can give the question this road asks it: a
# tree proved to be carrying nothing loose, one carrying work no push would
# publish, and one nothing could read -- which is not a clean tree either.
_CLEAN_TREE = _WorktreeStatus(readable=True)
_DIRTY_TREE = _WorktreeStatus(readable=True, paths=("src/left_behind.py",))
_UNREADABLE_TREE = _WorktreeStatus(readable=False)

# A checkout that passes every reading up to the push and is dirty by the
# time the handoff proves it again, which is the road that says two things.
_DIRTIED_AFTER_THE_PUSH = (
    _CLEAN_TREE, _CLEAN_TREE, _CLEAN_TREE, _DIRTY_TREE, _DIRTY_TREE,
)

# A commit the checkout is standing on that the park's own record does not
# name: work that replaced what an operator decided about.
_MOVED_HEAD_SHA = "e" * SHA_LENGTH

# A reading the ceiling lets through, so the seam's answer to a head nobody
# authorized is a push rather than a park.
_SMALL_ADDITIONS = 12

# The bare command the measurement park is answered by, and the reply that
# carries words instead -- which is guidance and the ordinary resume's.
_CONTINUE = "/orchestrator continue"

@dataclass
class _Routed:
    """Where one parked tick's committed work went, and whether it went.

    The publication seam this recovery owes its answer to, beside whether the
    tick was this owner's at all -- the two facts a case is about, since every
    other effect a road has is on the record and read from there.
    """

    published: object
    routed: bool = False


class _RoutingCase(_consent_case._ParkedCase):
    """One parked tick routed with the publication seam held still.

    The seam is patched and nothing else is, so a case reads the routing off
    one call and everything a road did to the record off the record itself.
    """

    def _recovers(
        self,
        worktree: Path = _consent_payloads.TEMP_WORKTREE_ROOT,
        tree: _WorktreeStatus = _CLEAN_TREE,
        moved: str = "",
    ) -> _Routed:
        """Route one parked tick, saying what it routed and where.

        The tree reading is the caller's, since what this road asks the
        checkout is the question the seam would have asked. So is the head
        reading beside it, which has an owner of its own and answers the
        ordinary world by default: the checkout is on the commit the park was
        taken over. What that owner decides is asked where it lives; these are
        about which road a parked tick takes.
        """
        seams = _Routed(
            published=patch.object(_candidate_recovery, _PUBLISH_COMMITTED_WORK),
        )
        with (
            patch.object(
                _worktree_paths, _consent_payloads.WORKTREE_PATH, return_value=worktree,
            ),
            patch.object(
                _worktree_status, _WORKTREE_STATUS, return_value=tree,
            ),
            patch.object(
                _checkout_recovery, _OFF_THE_PARKED_COMMIT, return_value=moved,
            ),
            seams.published as published,
        ):
            seams.routed = _recovery._recovers_a_late_park(
                self.github, _TEST_SPEC, self.issue, self._state(),
            )
            seams.published = published
        return seams


class UnauthorizedExemptionRecoveryTest(_RoutingCase, unittest.TestCase):
    """The command that ends the authorization park, routed and no more.

    The command is recognized here and ACTED on where the reading is, because
    that is where the terms of an authorization come from -- so what this owes
    is the routing, and the gate answer decides everything else.
    """

    def test_every_command_reaches_the_seam(self) -> None:
        # Back through the same publication seam the work came out of, so the
        # answer reaches the outcomes a fresh disposition does -- and never
        # the spawn below, which would pay for a developer over committed
        # work. A command naming another commit routes too: the sentence it
        # earns is the gate's to say, since only the owner holding a reading
        # knows which candidate is waiting, and left unrouted the reply would
        # fall to the ordinary resume and spawn a developer.
        for described, written in (
            ("the parked candidate", _consent_payloads.AUTHORIZE),
            ("another commit", _consent_payloads.AUTHORIZE_ANOTHER),
            ("an abbreviation", _consent_payloads.AUTHORIZE_ABBREVIATED),
        ):
            with self.subTest(command=described):
                self.setUp()
                self._reply(written)

                routed = self._recovers()

                self.assertTrue(routed.routed)
                routed.published.assert_called_once()

    def test_guidance_is_left_for_the_resume(self) -> None:
        # A reply whose last word is not the command belongs to the road that
        # feeds it to the developer.
        self._reply(_consent_payloads.GUIDANCE)

        routed = self._recovers()

        self.assertFalse(routed.routed)
        routed.published.assert_not_called()

    def test_a_thread_nobody_has_written_on_is_held(self) -> None:
        # The ordinary poll of a park waiting on a person: it owns the tick so
        # nothing below pays for a developer over committed work, and it buys
        # no reading to say what it said last time.
        routed = self._recovers()

        self.assertTrue(routed.routed)
        routed.published.assert_not_called()
        self.assertEqual(self.github.posted_comments, [])

    def test_an_outsider_is_nobody_speaking(self) -> None:
        # The allowlist's rule applied where the thread is read: nothing an
        # outsider posts is a decision or guidance, so the park is held on
        # the same terms a silent thread is.
        with patch.object(
            config, _consent_payloads.ALLOWLIST_CONFIG, (_consent_payloads.TRUSTED_AUTHOR,),
        ):
            self._reply(_consent_payloads.AUTHORIZE, author=_consent_payloads.OUTSIDER)

            routed = self._recovers()

        self.assertTrue(routed.routed)
        routed.published.assert_not_called()
        self.assertEqual(self.github.posted_comments, [])

    def test_another_park_is_not_this_road_at_all(self) -> None:
        # The door, asserted where it is written. An issue waiting on
        # something else is not this park's to end, and a tick that claimed it
        # would hold every other park in the stage on a thread nobody read.
        self._seed(**{_state._PARK_REASON: _state._AGENT_TIMEOUT})
        self._reply(_consent_payloads.AUTHORIZE)

        routed = self._recovers()

        self.assertFalse(routed.routed)
        routed.published.assert_not_called()

    def test_the_park_flags_are_left_standing(self) -> None:
        # The write that records the authorization is the write that takes
        # them off, so a tick that could not fingerprint the pair leaves the
        # issue exactly as parked as it found it rather than durably unparking
        # an issue nothing published.
        self._reply(_consent_payloads.AUTHORIZE)

        self._recovers()

        self._assert_still_parked()


class MeasurementParkRecoveryTest(_RoutingCase, unittest.TestCase):
    """The bare continue that asks for one more reading of the candidate.

    Deliberately not a session retry. What failed was a READING, and the
    developer that produced the commit finished long ago -- so the committed
    work goes back through the publication seam and nobody is spawned.
    """

    def setUp(self) -> None:
        super().setUp()
        self._seed(**{
            _state._PARK_REASON: _late_parks.PARK_MEASUREMENT_FAILED,
        })

    def test_a_bare_continue_re_measures(self) -> None:
        self._reply(_CONTINUE)

        routed = self._recovers()

        self.assertTrue(routed.routed)
        routed.published.assert_called_once()

    def test_the_command_is_consumed_by_the_retry(self) -> None:
        # Safe only because every reply on this road is a bare continue:
        # nothing with words in it is dropped here.
        commanded = self._reply(_CONTINUE)

        self._recovers()

        self.assertEqual(
            self._pinned()[_state._LAST_ACTION_COMMENT_ID], commanded,
        )

    def test_guidance_is_left_for_the_resume(self) -> None:
        # A reply carrying real words is guidance, which belongs to the
        # ordinary resume that feeds it to the developer.
        self._reply(_consent_payloads.GUIDANCE)

        routed = self._recovers()

        self.assertFalse(routed.routed)
        routed.published.assert_not_called()

    def test_a_missing_checkout_takes_its_own_park(self) -> None:
        # The one outcome the seam cannot reach on its own, and the road where
        # re-parking costs nobody anything: the answer was a bare continue,
        # spent by the tick that read it, so the next continue retries it once
        # the worktree is back.
        self._reply(_CONTINUE)

        routed = self._recovers(worktree=_MISSING_WORKTREE)

        self.assertTrue(routed.routed)
        routed.published.assert_not_called()
        self.assertTrue(self._pinned()[_state._AWAITING_HUMAN])

    def _recovers(self, **routed) -> _Routed:
        """Route the tick with the checkout standing where the record says.

        The recorded-candidate proof is the caller's here rather than a real
        git read, because what these cases are about is the road past it: the
        park it takes when the head has moved has its own owner and its own
        tests.
        """
        with patch.object(
            _late_evidence, _HOLDS_MOVED_CANDIDATE, return_value=False,
        ):
            return _RoutingCase._recovers(self, **routed)


class MovedCandidateRecoveryTest(_RoutingCase, unittest.TestCase):
    """The park no reply can end, settled by the checkout coming back.

    What that park refused was the HANDOFF -- the commit was measured and
    approved, and the checkout was somewhere else -- so what settles it is the
    worktree, not guidance and not another developer run.
    """

    def setUp(self) -> None:
        super().setUp()
        self._seed(**{_state._PARK_REASON: _state._CANDIDATE_MOVED})

    def test_a_restored_checkout_republishes(self) -> None:
        routed = self._recovers_the_checkout(restored=MEASURED_CANDIDATE_SHA)

        self.assertTrue(routed.routed)
        routed.published.assert_called_once()
        pinned = self._pinned()
        self.assertFalse(pinned[_state._AWAITING_HUMAN])
        self.assertIsNone(pinned[_state._PARK_REASON])

    def test_a_checkout_still_elsewhere_says_nothing(self) -> None:
        # Quiet by design: every tick asks one local question and says nothing
        # until the answer changes, so an operator who leaves the worktree
        # where it is is not told the same thing once a tick.
        routed = self._recovers_the_checkout(restored="")

        self.assertFalse(routed.routed)
        routed.published.assert_not_called()
        self.assertEqual(self.github.posted_comments, [])
        self._assert_parked_for(_state._CANDIDATE_MOVED)

    def test_a_missing_checkout_says_nothing(self) -> None:
        routed = self._recovers_the_checkout(
            restored=MEASURED_CANDIDATE_SHA, worktree=_MISSING_WORKTREE,
        )

        self.assertFalse(routed.routed)
        routed.published.assert_not_called()
        self._assert_parked_for(_state._CANDIDATE_MOVED)

    def _recovers_the_checkout(
        self, restored: str, worktree: Path = _consent_payloads.TEMP_WORKTREE_ROOT,
    ) -> _Routed:
        """Route the tick with the checkout answering what a case says it does."""
        with patch.object(
            _checkout_recovery, _RESTORED_CHECKOUT, return_value=restored,
        ):
            return self._recovers(worktree=worktree)

    def _assert_parked_for(self, reason: str) -> None:
        pinned = self._pinned()
        self.assertTrue(pinned[_state._AWAITING_HUMAN])
        self.assertEqual(pinned[_state._PARK_REASON], reason)


class UnpublishableCheckoutHoldTest(_RoutingCase, unittest.TestCase):
    """Every road that answers the command and reaches no publication.

    A checkout the seam would refuse is not a decision anybody made, so
    nothing about it may spend the decision already on the thread. Held
    silently, the park, the command and the record are all still there for the
    poll that finds the worktree back.
    """

    def test_an_unpublishable_tree_writes_nothing(self) -> None:
        # The seam below reads the tree before a verdict can be recorded, and
        # its refusal parks under a reason of its own. Reached on this road,
        # that reason takes the authorization park's off and its notice moves
        # the watermark past the command still standing -- so the operator is
        # asked to authorize the same commit again once they clean the tree.
        # A tree nothing could READ is refused beside a dirty one, since a
        # reading that established nothing is not evidence of a clean tree.
        for described, tree in (
            ("carrying uncommitted work", _DIRTY_TREE),
            ("unreadable", _UNREADABLE_TREE),
        ):
            with self.subTest(tree=described):
                self.setUp()
                self._reply(_consent_payloads.AUTHORIZE)
                before = dict(self._pinned())

                routed = self._recovers(tree=tree)

                self.assertTrue(routed.routed)
                routed.published.assert_not_called()
                self.assertEqual(self._pinned(), before)
                self.assertEqual(self.github.posted_comments, [])

    def test_a_missing_checkout_writes_nothing(self) -> None:
        # There is no commit to read there, the recorded SHA is evidence no
        # fresh checkout may stand in for, and re-running the developer would
        # answer with different work -- so it owns the tick and publishes
        # nothing. What it may not do is re-park under a reason of its own:
        # the notice that would go with one moves the watermark past the
        # command still standing, and its reason takes this park's off, so an
        # operator who put the worktree back would be asked for the same
        # decision again on an issue now waiting for a different reply.
        self._reply(_consent_payloads.AUTHORIZE)
        before = dict(self._pinned())

        routed = self._recovers(worktree=_MISSING_WORKTREE)

        self.assertTrue(routed.routed)
        routed.published.assert_not_called()
        self.assertEqual(self._pinned(), before)
        self.assertEqual(self.github.posted_comments, [])

    def test_a_fixed_checkout_needs_no_command(self) -> None:
        # The whole of what holding quietly buys, from either hold: the
        # command the operator already wrote is still the last fresh word on
        # the thread, so the poll after they fix the checkout publishes on it
        # without their being asked to decide a second time.
        for described, held in (
            ("a tree carrying uncommitted work", {"tree": _DIRTY_TREE}),
            ("a checkout that was gone", {"worktree": _MISSING_WORKTREE}),
        ):
            with self.subTest(held=described):
                self.setUp()
                self._reply(_consent_payloads.AUTHORIZE)
                self._recovers(**held)

                routed = self._recovers()

                self.assertTrue(routed.routed)
                routed.published.assert_called_once()


# Which retirement may end which park, over all four pairings. A reading
# answers the park a reading was owed; a publication under an authorization
# answers that one. The crossed cells are what the table is for -- above all a
# lost base counting a quiet retry, which must leave an operator who has not
# replied exactly where it found them.
_RETIREMENTS = (
    (_late_parks._retire_spent_park, _late_parks.PARK_MEASUREMENT_FAILED, False),
    (
        _late_parks._retire_spent_park,
        _late_command.PARK_UNAUTHORIZED_EXEMPTION,
        True,
    ),
    (
        _late_parks._retire_authorized_park,
        _late_command.PARK_UNAUTHORIZED_EXEMPTION,
        False,
    ),
    (
        _late_parks._retire_authorized_park,
        _late_parks.PARK_MEASUREMENT_FAILED,
        True,
    ),
)


class RetiredParkTest(_consent_case._ParkedCase, unittest.TestCase):
    """Which of the two parks the size gate takes one road may take down.

    Apart from the routing above because no road there can tell them apart:
    the rollback puts back whatever a call that published nothing cleared, so
    a retirement taken on the wrong park is invisible from a whole tick. What
    it costs is paid on the roads that reach this gate without one -- and what
    it would cost is an issue durably unparked whose operator never replied,
    with the exemption nobody stands behind publishing on the next poll under
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
