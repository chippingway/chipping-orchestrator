# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The park an adjudicated candidate with nobody behind it waits on.

A hold rather than a route back to the adjudication: the change has been ruled
one change already, so what is missing is the person. These pin down what the
hold leaves on the record, what the command that ends one writes, and what
every reply it may not act on is answered with -- once, and consumed no
further than the reading that found it.
"""

from __future__ import annotations

import unittest
from dataclasses import replace
from unittest.mock import patch

from orchestrator import config
from orchestrator.git.measurement.models import MeasurementFailure
from orchestrator.workflow.engine import comments as _comments
from orchestrator.workflow.stages.implementing import (
    late_approval_reading as _late_approval_reading,
    late_command as _command,
    late_consent as _consent,
    late_verdict as _verdict_owner,
    state as _state,
)
from tests.workflow.fixtures import (
    MEASURED_BASE_SHA,
    MEASURED_CANDIDATE_SHA,
    _authorized_exemption,
)
from tests.workflow.interleaving import _RacesTheStep
from tests.workflow.stages.implementing import (
    late_consent_payloads as _consent_payloads,
    late_consent_test_support as support,
)

_ORCH_MARKER = _comments._ORCH_COMMENT_MARKER

# The park a reading nobody could take earns, the step its notice names, and
# the two families the sinks carry for a reading that happened and one that
# did not.
_MEASUREMENT_FAILED = "late_measurement_failed"
_DIFF_FAILED = MeasurementFailure.DIFF_FAILED
_MEASUREMENT_EVENT = "late_measurement"
_FAILURE_EVENT = "late_failure"

# The pair a tick freezes over a commit no record on this issue names, which
# is what a resumed developer's fresh work looks like to the gate.
_MOVED_PAIR = replace(_consent_payloads.measured(), candidate_sha=_consent_payloads.STRANGER_SHA)

# The sentence only the side of publication with a resume behind it may offer.
_RESUMED_AGAINST_IT = "the developer is resumed against it"


class GateDoorTest(support._ConsentCase, unittest.TestCase):
    """Which road one whole gate decision takes, and what it leaves behind.

    This owner's road and the ordinary measurement beside it reach the same
    two verdicts, so a case asking only what came back could not tell which of
    them decided.
    """

    def test_a_command_publishes_nothing_unruled(self) -> None:
        # What the park collects is HALF of a two-part bypass: an
        # adjudicator's ruling that the change is one change, and an operator
        # who agreed to publish it past the ceiling. Reached without the
        # first, a command alone would earn the override group and publish a
        # candidate nobody has ruled on -- so a commit no exemption names goes
        # to the ordinary reading, which routes an oversized one to the
        # adjudication that has never seen it.
        for described, exempted in (
            ("nothing at all", None),
            ("another commit", _consent_payloads.STRANGER_SHA),
            ("an abbreviation", MEASURED_CANDIDATE_SHA[:_consent_payloads.ABBREVIATED]),
            ("prose", "the one above"),
        ):
            with self.subTest(exemption=described):
                self.setUp()
                self._seed(**{
                    _consent_payloads.KEY_EXEMPT_SHA: exempted,
                    **_consent_payloads.measured_pair(),
                })
                self._reply(_consent_payloads.AUTHORIZE)

                decided = self._decides()

                self.assertTrue(decided.verdict.held)
                self.assertTrue(decided.measured)
                self.assertNotIn(
                    _consent_payloads.KEY_OVERRIDE_CANDIDATE_SHA, self._pinned(),
                )

    def test_an_adjudicated_commit_takes_this_road(self) -> None:
        # The other direction: the candidate an adjudicator did rule on and
        # nobody authorized is MEASURED like any other, and what the operator
        # authorizes is that reading -- a change of this size against this
        # ceiling -- rather than a number read back off the comment.
        self._seed(**_consent_payloads.measured_pair())
        commanded = self._reply(_consent_payloads.AUTHORIZE)

        decided = self._decides()

        self.assertFalse(decided.verdict.held)
        self.assertTrue(decided.measured)
        self.assertEqual(decided.verdict.candidate_sha, MEASURED_CANDIDATE_SHA)
        authorized = self._pinned()
        self.assertEqual(
            authorized[_consent_payloads.KEY_OVERRIDE_COMMENT_ID], commanded,
        )
        self.assertEqual(
            authorized[_consent_payloads.KEY_OVERRIDE_ADDITIONS],
            _consent_payloads.OVERSIZED_ADDITIONS,
        )

    def test_an_authorized_commit_skips_the_reading(self) -> None:
        # And the far side of the same road, which is what a recorded
        # authorization buys: the exemption and the terms an operator granted
        # it on both name the commit, so the gate publishes it without a
        # count and without asking anybody a second time.
        self._seed(parked=False, **_authorized_exemption())

        decided = self._decides()

        self.assertFalse(decided.verdict.held)
        self.assertFalse(decided.measured)
        self.assertEqual(
            decided.verdict.basis, str(_late_approval_reading.LateApprovalBasis.ADJUDICATION),
        )


class MeasuredAfreshTest(support._ConsentCase, unittest.TestCase):
    """The reading this park is reached from, which is a COUNT every time.

    Never the exemption alone: read as "already decided" it would publish the
    very bypass the park withholds.
    """

    def test_an_oversized_count_holds_for_a_person(self) -> None:
        # The exemption on the record is exactly what the park doubts, so what
        # decides is this tick's own count rather than the record's answer.
        self.assertTrue(self._holds(_consent_payloads.OVERSIZED))

        self.assertEqual(
            self._pinned()[_state._PARK_REASON],
            _command.PARK_UNAUTHORIZED_EXEMPTION,
        )

    def test_a_candidate_under_the_ceiling_settles(self) -> None:
        # Not this park's to hold at all: a resumed developer's fresh commit
        # is not the change anybody was asked about, and a small one needs
        # nobody's permission.
        settles = support.SettlesWithItsOwnWrite()

        with patch.object(_verdict_owner, _consent_payloads.SETTLED, settles):
            self.assertFalse(self._holds(_consent_payloads.FITS))

        self.assertEqual(len(settles.given), 1)
        self.assertEqual(self.github.posted_comments, [])

    def test_a_settled_candidate_leaves_no_park(self) -> None:
        # The retirement a published candidate earns drops the park in its own
        # durable write, so without this the gate publishes a commit while the
        # record still says a human is holding the issue -- and the source
        # stage takes its parked road on every poll after, waiting for a reply
        # to a question this tick answered.
        settles = support.SettlesWithItsOwnWrite()

        with patch.object(_verdict_owner, _consent_payloads.ACCEPTED, settles):
            self._holds(_consent_payloads.FITS)

        for described, record in (
            ("handed to the settlement", settles.given[0]),
            ("left on the comment", self._pinned()),
        ):
            with self.subTest(park=described):
                self.assertFalse(record[_state._AWAITING_HUMAN])
                self.assertIsNone(record[_state._PARK_REASON])

    def test_a_lost_count_parks_as_a_reading(self) -> None:
        # The reading is the gate's ordinary one, so a diff this host cannot
        # read fails exactly where every other lost reading does: the typed
        # measurement park, said to the thread and reported to both sinks.
        # Held silently instead, a fresh legacy record would poll forever with
        # nothing parked, nothing said, and no failure telemetry.
        self._seed(parked=False)

        self._run_tick(added_lines=_DIFF_FAILED)

        pinned = self._pinned()
        self.assertEqual(pinned[_state._PARK_REASON], _MEASUREMENT_FAILED)
        self.assertIn(str(_DIFF_FAILED), self.github.posted_comments[0][1])
        self.assertNotIn(_consent_payloads.KEY_OVERRIDE_CANDIDATE_SHA, pinned)
        self.assertEqual(pinned[_consent_payloads.KEY_EXEMPT_SHA], MEASURED_CANDIDATE_SHA)
        self.assertIn(
            _FAILURE_EVENT,
            [record["event"] for record in self.github.recorded_events],
        )

    def test_a_measured_candidate_reaches_both_sinks(self) -> None:
        # The other half of using the ordinary reading: a count that DID come
        # back emits the measurement event every other candidate's does, so an
        # issue held for an operator is visible to the same telemetry.
        self._seed(parked=False)

        self._holds(_consent_payloads.OVERSIZED)

        self.assertIn(
            _MEASUREMENT_EVENT,
            [record["event"] for record in self.github.recorded_events],
        )

    def test_a_pair_nothing_froze_holds_as_found(self) -> None:
        self._reply(_consent_payloads.AUTHORIZE)

        self.assertTrue(self._holds(_consent_payloads.OVERSIZED, pair=None))

        self.assertEqual(self.github.posted_comments, [])
        self.assertNotIn(_consent_payloads.KEY_OVERRIDE_CANDIDATE_SHA, self._pinned())

    def test_a_candidate_it_moved_past_is_adjudicated(self) -> None:
        # A resumed developer's fresh commit is not the change anybody was
        # asked about, and no exemption names it -- so it goes to the
        # adjudication, which takes the stale park down on its way. Left
        # standing, the human would go on holding an issue over a commit the
        # branch has moved off.
        self._seed(**_consent_payloads.measured_pair(candidate_sha=_consent_payloads.STRANGER_SHA))

        with patch.object(_verdict_owner, _consent_payloads.ROUTED, return_value=True):
            self.assertTrue(self._holds(_consent_payloads.OVERSIZED, pair=_MOVED_PAIR))

        self.assertEqual(self.github.posted_comments, [])


class AuthorizationParkTest(support._ConsentCase, unittest.TestCase):
    """What an oversized reading of an adjudicated candidate is held under."""

    def test_it_holds_and_says_so_once(self) -> None:
        self._seed(parked=False)

        self.assertFalse(self._authorizes())

        pinned = self._pinned()
        self.assertTrue(pinned[_state._AWAITING_HUMAN])
        self.assertEqual(
            pinned[_state._PARK_REASON], _command.PARK_UNAUTHORIZED_EXEMPTION,
        )

    def test_a_standing_park_is_not_announced_twice(self) -> None:
        # The seams that publish onto a pull request the remote already
        # carries re-enter the gate on every poll behind the park, so a second
        # notice would mention the same people once a poll about a decision
        # they have already been asked for.
        self._seed(**_consent_payloads.measured_pair())

        self.assertFalse(self._authorizes())

        self.assertEqual(self.github.posted_comments, [])

    def test_the_notice_names_the_command(self) -> None:
        # An operator authorizes a change of THIS size against THAT ceiling,
        # so the notice carries the reading the tick took rather than a record
        # read back off the comment.
        self._seed(parked=False)

        self._authorizes()

        said = self.github.posted_comments[0][1]
        self.assertIn(config.HITL_MENTIONS, said)
        self.assertIn(_consent_payloads.AUTHORIZE, said)
        self.assertIn(str(_consent_payloads.OVERSIZED_ADDITIONS), said)
        self.assertIn(str(_consent_payloads.THRESHOLD), said)

    def test_the_notice_offers_a_resume(self) -> None:
        # Before there is one the ordinary resume is still in front of the
        # issue, so a reply that is not the command reaches the developer.
        self._seed(parked=False)

        self._authorizes()

        self.assertIn(_RESUMED_AGAINST_IT, self.github.posted_comments[0][1])

    def test_the_notice_offers_no_resume_past_one(self) -> None:
        # Past a pull request the debt reconciliation that brings a parked
        # issue back to the gate stops the tick ahead of the stage handler on
        # every poll, so nothing there would carry a human's words to an agent
        # -- and a notice offering it would have somebody writing into a
        # thread nothing reads.
        self._seed(parked=False)

        self._authorizes(entry=_consent_payloads.PUBLISHED_ENTRY)

        said = self.github.posted_comments[0][1]
        self.assertIn(_consent_payloads.AUTHORIZE, said)
        self.assertNotIn(_RESUMED_AGAINST_IT, said)

    def test_it_deletes_nothing_and_counts_nothing(self) -> None:
        # The record is what an authorization would be checked against, so a
        # park that tidied the comment would destroy the evidence it exists to
        # ask about -- and a generation carrying a reading past its ceiling is
        # what the dispatcher restores `workflow:decomposing` over, so the
        # park would be relabelled out from under itself on the next poll.
        self._seed(parked=False)

        self._authorizes()

        pinned = self._pinned()
        self.assertEqual(pinned[_consent_payloads.KEY_EXEMPT_SHA], MEASURED_CANDIDATE_SHA)
        self.assertNotIn(_consent_payloads.KEY_OVERRIDE_CANDIDATE_SHA, pinned)
        self.assertIsNone(pinned.get("late_additions"))


class AuthorizedCandidateTest(support._ConsentCase, unittest.TestCase):
    """What the command that ends the park writes, and what it costs."""

    def test_the_terms_come_from_the_reading(self) -> None:
        identified = self._reply(_consent_payloads.AUTHORIZE)

        self.assertTrue(self._authorizes())

        pinned = self._pinned()
        self.assertEqual(
            pinned[_consent_payloads.KEY_OVERRIDE_CANDIDATE_SHA], MEASURED_CANDIDATE_SHA,
        )
        self.assertEqual(
            pinned[_consent_payloads.KEY_OVERRIDE_BASE_SHA], MEASURED_BASE_SHA,
        )
        self.assertEqual(
            pinned[_consent_payloads.KEY_OVERRIDE_ADDITIONS], _consent_payloads.OVERSIZED_ADDITIONS,
        )
        self.assertEqual(
            pinned[_consent_payloads.KEY_OVERRIDE_THRESHOLD], _consent_payloads.THRESHOLD,
        )
        self.assertEqual(pinned[_consent_payloads.KEY_OVERRIDE_COMMENT_ID], identified)

    def test_the_park_comes_down_with_the_record(self) -> None:
        # One write: the record without the park cleared says a human is owed
        # a question they have answered, and the park without the record sends
        # the candidate straight back to it.
        identified = self._reply(_consent_payloads.AUTHORIZE)

        self._authorizes()

        pinned = self._pinned()
        self.assertFalse(pinned[_state._AWAITING_HUMAN])
        self.assertIsNone(pinned[_state._PARK_REASON])
        self.assertEqual(pinned[_state._LAST_ACTION_COMMENT_ID], identified)

    def test_a_lost_reading_leaves_everything_alone(self) -> None:
        # Nothing about a store that cannot hand back the content between two
        # commits it holds is the operator's doing, so the next tick takes the
        # same reading rather than asking them to authorize twice.
        self._reply(_consent_payloads.AUTHORIZE)

        self.assertFalse(self._authorizes(contribution=_consent_payloads.UNREADABLE))

        pinned = self._pinned()
        self.assertTrue(pinned[_state._AWAITING_HUMAN])
        self.assertNotIn(_consent_payloads.KEY_OVERRIDE_CANDIDATE_SHA, pinned)
        self.assertEqual(
            pinned[_state._LAST_ACTION_COMMENT_ID],
            _consent_payloads.PRIOR_ACTION_COMMENT_ID,
        )

    def test_consent_withdrawn_publishes_nothing(self) -> None:
        # An operator who authorizes and then changes their mind has decided
        # about the second thing. The marker their retraction happens to carry
        # -- pasted, or quoted off a comment of ours -- is a body anybody can
        # write, and the account it is written from may be the very token this
        # orchestrator posts under. Treating either as proof of authorship
        # deletes the retraction from the reading and publishes on consent
        # withdrawn.
        for described, author in (
            ("their own account", _consent_payloads.TRUSTED_AUTHOR),
            ("the shared bot login", self.github._bot_login),
        ):
            with self.subTest(written_from=described):
                self.setUp()
                self._reply(_consent_payloads.AUTHORIZE, author=author)
                self._reply(
                    f"actually, hold off\n\n{_ORCH_MARKER}", author=author,
                )

                self.assertFalse(self._authorizes())

                self.assertNotIn(
                    _consent_payloads.KEY_OVERRIDE_CANDIDATE_SHA, self._pinned(),
                )

    def test_a_reply_landing_mid_write_survives(self) -> None:
        # The reading picked the last word the thread had when it looked, and
        # a retraction posted while this tick was still writing is not one of
        # the comments it examined. Consumed to the tip as it stands NOW, that
        # retraction would be swallowed unread while the authorization it
        # retracts published.
        self._reply(_consent_payloads.AUTHORIZE)
        landed = []
        racing = _RacesTheStep(
            _consent._recorded_authorization,
            lambda: landed.append(self._reply("actually, hold off")),
        )

        with patch.object(_consent, "_recorded_authorization", racing):
            self.assertTrue(self._authorizes())

        self.assertLess(
            self._pinned()[_state._LAST_ACTION_COMMENT_ID], landed[0],
        )


class RefusedCommandTest(support._ConsentCase, unittest.TestCase):
    """Every command this park owes an answer to and may not act on."""

    def test_a_command_it_cannot_act_on_is_answered(self) -> None:
        # A bypass may license exactly what a human looked at. An id copied
        # out of a notice about work the developer has since been resumed
        # over, and an abbreviation -- which names nothing, since nothing here
        # ever writes one -- both get the sentence and the command that would
        # have worked.
        for described, written in (
            ("another commit", _consent_payloads.AUTHORIZE_ANOTHER),
            ("an abbreviation", _consent_payloads.AUTHORIZE_ABBREVIATED),
        ):
            with self.subTest(command=described):
                self.setUp()
                self._reply(written)

                self.assertFalse(self._authorizes())

                pinned = self._pinned()
                self.assertTrue(pinned[_state._AWAITING_HUMAN])
                self.assertNotIn(_consent_payloads.KEY_OVERRIDE_CANDIDATE_SHA, pinned)
                self.assertIn(
                    MEASURED_CANDIDATE_SHA, self.github.posted_comments[-1][1],
                )

    def test_the_refusal_is_consumed_past_itself(self) -> None:
        # Ids ascend, so the sentence lands above the reply it answers. Left
        # between the two, the orchestrator's own words are what the next poll
        # finds past the watermark -- and every other reader of this thread
        # takes that for a human's fresh guidance.
        answered = self._reply(_consent_payloads.AUTHORIZE_ANOTHER)

        self._authorizes()

        watermark = self._pinned()[_state._LAST_ACTION_COMMENT_ID]
        self.assertGreater(watermark, answered)
        self.assertEqual(
            watermark, self.github.latest_comment_id(self.issue),
        )

    def test_the_same_reply_is_answered_once(self) -> None:
        # The sentence and the write that consumes it are two operations, and
        # a tick that says the first and dies before the second loses both the
        # watermark and the ledger entry naming what it posted -- they are
        # staged into one write. The poll after that finds our own sentence
        # standing as the last word it can attribute to nobody, which is no
        # command, so it holds the park it is already standing on and says
        # nothing rather than mentioning the same people twice.
        self._reply(_consent_payloads.AUTHORIZE_ANOTHER)
        self._authorizes()
        self._seed(**{
            _state._LAST_ACTION_COMMENT_ID: _consent_payloads.PRIOR_ACTION_COMMENT_ID,
            **_consent_payloads.measured_pair(),
        })

        self._authorizes()

        self.assertEqual(len(self.github.posted_comments), 1)

    def test_a_command_landing_mid_refusal_survives(self) -> None:
        # The window between reading a command this park may not act on and
        # posting the sentence answering it. An operator who reads the notice
        # and gets it right in there lands BELOW our sentence, since ids
        # ascend -- so a watermark jumped straight to the sentence's own id
        # would consume their answer unread and leave the park standing over a
        # command nobody will ever see again.
        self._reply(_consent_payloads.AUTHORIZE_ANOTHER)
        corrected = []
        racing = _RacesTheStep(
            _comments._post_issue_comment,
            lambda: corrected.append(self._reply(_consent_payloads.AUTHORIZE)),
        )

        with patch.object(_comments, _consent_payloads.POST_ISSUE_COMMENT, racing):
            self.assertFalse(self._authorizes())

        self.assertLess(
            self._pinned()[_state._LAST_ACTION_COMMENT_ID], corrected[0],
        )

    def test_a_quoted_record_survives_the_refusal(self) -> None:
        # The same window, for a reply the consumption walk reads rather than
        # the reading. Told to find the pinned comment by its marker, that
        # walk treats a reply quoting one as the record, steps straight over
        # it, and consumes it unread -- so a retraction written while this
        # tick was posting would be lost for good.
        self._reply(_consent_payloads.AUTHORIZE_ANOTHER)
        landed = []
        racing = _RacesTheStep(
            _comments._post_issue_comment,
            lambda: landed.append(self._reply(_consent_payloads.QUOTES_THE_RECORD)),
        )

        with patch.object(_comments, _consent_payloads.POST_ISSUE_COMMENT, racing):
            self.assertFalse(self._authorizes())

        self.assertLess(
            self._pinned()[_state._LAST_ACTION_COMMENT_ID], landed[0],
        )

    def test_the_corrected_command_publishes(self) -> None:
        # And the other half of it: the reply the refusal did not swallow is
        # the last fresh word on the next reading, so the poll after the race
        # records the authorization rather than asking for it again.
        self._reply(_consent_payloads.AUTHORIZE_ANOTHER)
        corrected = []
        racing = _RacesTheStep(
            _comments._post_issue_comment,
            lambda: corrected.append(self._reply(_consent_payloads.AUTHORIZE)),
        )
        with patch.object(_comments, _consent_payloads.POST_ISSUE_COMMENT, racing):
            self._authorizes()

        self.assertTrue(self._authorizes())

        self.assertEqual(
            self._pinned()[_consent_payloads.KEY_OVERRIDE_COMMENT_ID], corrected[0],
        )

    def test_a_correct_command_behind_it_still_works(self) -> None:
        # The command a human gets right after getting one wrong has to work.
        # Read as a set instead of as a last word, the first reply would
        # refuse every one behind it for as long as the park stood.
        self._reply(_consent_payloads.AUTHORIZE_ANOTHER)
        self._authorizes()
        corrected = self._reply(_consent_payloads.AUTHORIZE)

        self.assertTrue(self._authorizes())

        self.assertEqual(
            self._pinned()[_consent_payloads.KEY_OVERRIDE_COMMENT_ID], corrected,
        )


if __name__ == "__main__":
    unittest.main()
