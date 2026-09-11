# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What publishes an oversized candidate a human read, and what does not.

An adjudicator answering `single` parks the issue, because publishing past the
size ceiling is a decision the workflow does not make for itself. These cases
are about the one thing that ends that park: an operator's own command, naming
the exact commit they read.

What they pin is the whole of what that command costs. On the way in it is
proved -- the commit it names has to be the one parked, the adjudication it
publishes has to still be on the record, and the contribution between the
frozen pair is recomputed rather than taken from anything stored. What it
earns is one write carrying the durable terms, the park coming down, and the
reply consumed, and then the settlement the recorded verdict licenses.
Everything it does not prove leaves the park exactly where it stands.
"""
from __future__ import annotations

import contextlib
from unittest.mock import patch

from orchestrator import config
from orchestrator.git.measurement.models import (
    FINGERPRINT_FORMAT,
    AdditionMeasurement,
    FingerprintFailure,
)
from orchestrator.workflow.late_split import overrides as _overrides
from orchestrator.workflow.stages.decomposition.late_models import (
    _LateDisposition,
)
from tests.workflow.stages.decomposition import late_content_support as _support, late_test_support as _stage_support
from tests.workflow.stages.decomposition.late_content_support import LateContentCase
from tests.workflow.stages.decomposition.late_published_support import (
    published_generation,
    seed_published_pr,
)
from tests.workflow.stages.decomposition.late_revision_support import (
    DEV_ACK,
    DEV_PIN,
    UNCHANGED,
)
from tests.workflow.stages.decomposition.late_run_support import WorktreeSeed
from tests.workflow.stages.decomposition.late_settlement_support import (
    OWNER_GUARD,
    killed_at,
)

ALLOWED_AUTHORS = "ALLOWED_ISSUE_AUTHORS"

LABEL_DECOMPOSING = "workflow:decomposing"
LABEL_IMPLEMENTING = "workflow:implementing"

KEY_LAST_ACTION_COMMENT_ID = "last_action_comment_id"

# The phrase each answer this owner can write is recognized by. Asserted on
# rather than the whole sentence, because what these tests are about is which
# of them was said.
ACCEPTED_NOTICE = "authorized to publish unsplit"
WRONG_CANDIDATE_NOTICE = "names a commit this issue is not waiting on"
NO_VERDICT_NOTICE = "no longer show"
CONTINUE_REFUSED_NOTICE = "is not a decision to publish an oversized change"

SAID_ONCE = 1

# An outsider's own comment, and one a human wrote before the park fired.
# Both sit below the notice's id, which is what makes the second one stale.
OUTSIDER_COMMENT_ID = 200
EARLY_COMMENT_ID = 20

# What one authorization leaves on the pinned comment, and what each field has
# to be. Every term comes from the frozen generation rather than from the
# command: the record is what a later reader holds the decision to, so a term
# the human supplied would let them authorize something they never read.
_AUTHORIZED_TERMS = (
    (_overrides.LATE_OVERRIDE_CANDIDATE_SHA, _stage_support.CANDIDATE_SHA),
    (_overrides.LATE_OVERRIDE_BASE_SHA, _stage_support.BASE_SHA),
    (_overrides.LATE_OVERRIDE_FINGERPRINT, _stage_support.CONTRIBUTION_DIGEST),
    (_overrides.LATE_OVERRIDE_FINGERPRINT_FORMAT, FINGERPRINT_FORMAT),
    (_overrides.LATE_OVERRIDE_ADDITIONS, _stage_support.ADDITIONS),
    (_overrides.LATE_OVERRIDE_THRESHOLD, _stage_support.THRESHOLD),
)

# Every argument that is not the commit this issue is parked on: one it was
# replaced by, the abbreviation nothing here ever writes, prose, and a command
# with no argument at all. All four ARE the command -- an operator wrote it --
# so all four are owed the same answer rather than being read as guidance.
_NOT_THE_CANDIDATE = (_stage_support.OTHER_SHA, _stage_support.CANDIDATE_SHA[:7], "the one above", "")

# A store holding both frozen commits and unable to hand back the content
# between them. Nothing about it is the operator's doing, so their command is
# not spent on it.
_UNFINGERPRINTED = WorktreeSeed(fingerprint=FingerprintFailure.CONTENT_ABSENT)

# The same pair reading back as some OTHER contribution: what a replaced
# object, a hand-edited record, and an older binary's digest all look like from
# the publication's side, and the one term the record cannot arrange for
# itself.
_MOVED_DIGEST = "7" * _stage_support.DIGEST_LENGTH

_MOVED_CONTRIBUTION = WorktreeSeed(fingerprint=_MOVED_DIGEST)

# The one re-measurement that leaves every term of the record matching: the
# developer acknowledged the committed work, nothing moved, and the base is
# the one it was frozen over. Only the generation counter has advanced, which
# is the identity the record deliberately does not carry.
_UNCHANGED_MEASUREMENT = AdditionMeasurement(
    base_sha=_stage_support.BASE_SHA, candidate_sha=_stage_support.CANDIDATE_SHA, additions=_stage_support.ADDITIONS,
)

# What a pinned write that never lands raises. The type is not the point --
# every caller here lets it out -- but the tick dying inside the write is.
_WRITE_REFUSED = "the pinned comment was refused"


@contextlib.contextmanager
def refused_write(github):
    """The pinned write a tick is about to make failing outright.

    What it turns into an assertion is the window every answer this owner
    writes has: the sentence lands and the write that consumes what it answers
    does not, so the next tick reads the same reply again.
    """
    with patch.object(
        github, "write_pinned_state",
        side_effect=RuntimeError(_WRITE_REFUSED),
    ):
        yield


class _AuthorizeCase(LateContentCase):
    """One late issue parked on the decision this command ends."""

    def setUp(self) -> None:
        self._park()

    def _park(self, **state) -> None:
        """Seed the issue as one an adjudicator answered `single` about."""
        self._seed(**{**_support.SINGLE_PARKED, **state})

    def _command(self, named: str = _stage_support.CANDIDATE_SHA):
        """Post the authorization as a reply to the park's own notice."""
        return _support.reply(self.issue, _support.authorization(named))

    def _tick(self, **run_fields):
        """Run one adjudication, keeping the spawn for the caller to assert."""
        outcome, spawn = self._run(**run_fields)
        self.spawn = spawn
        return outcome

    def _authorized(self):
        """The candidate the pinned record says was authorized, if any."""
        return self._pinned().get(_overrides.LATE_OVERRIDE_CANDIDATE_SHA)

    def _authorize_then_crash(self) -> None:
        """Land the authorization, then die before anything it licenses.

        The write goes out before the owner read, so the record, the cleared
        park and the consumed reply are all durable and the publication is
        the only thing left -- which is the state every recovery below is
        about.
        """
        self._command()
        with killed_at(OWNER_GUARD), self.assertRaises(KeyboardInterrupt):
            self._tick()
        self.assertEqual(self._authorized(), _stage_support.CANDIDATE_SHA)

    def _assert_still_parked(self) -> None:
        """Nothing published, nothing recorded, and the question standing."""
        pinned = self._pinned()
        self.assertTrue(pinned.get(_stage_support.KEYS.awaiting))
        self.assertEqual(pinned.get(_stage_support.KEYS.park_reason), _support.PARK_SINGLE_DECISION)
        self.assertIsNone(self._authorized())
        self.assertNotIn(_stage_support.KEYS.exempt_sha, pinned)
        self.assertEqual(
            self.github.workflow_label(self.issue), LABEL_DECOMPOSING,
        )


class AuthorizedPublicationTest(_AuthorizeCase):
    """A trusted command publishes the candidate it names, and only it."""

    def setUp(self) -> None:
        super().setUp()
        self.commanded = self._command()

    def test_it_settles_the_recorded_verdict(self) -> None:
        outcome = self._tick()

        # No agent: the adjudication is on the record, and what the command
        # buys is the publication of that answer rather than a second one.
        self.spawn.assert_not_called()
        self.assertEqual(outcome.disposition, _LateDisposition.SETTLED)
        self.assertEqual(self._pinned().get(_stage_support.KEYS.exempt_sha), _stage_support.CANDIDATE_SHA)
        self.assertEqual(
            self.github.workflow_label(self.issue), LABEL_IMPLEMENTING,
        )
        self.assertIn(ACCEPTED_NOTICE, self._bodies()[-1])

    def test_the_record_names_what_was_authorized(self) -> None:
        self._tick()

        pinned = self._pinned()
        for key, term in _AUTHORIZED_TERMS:
            with self.subTest(key=key):
                self.assertEqual(pinned.get(key), term)
        # The comment is the attributable half: a bypass of the size gate is
        # licensed by one gesture at one address anybody can go and read.
        self.assertEqual(
            pinned.get(_overrides.LATE_OVERRIDE_COMMENT_ID),
            self.commanded.id,
        )

    def test_the_park_and_the_reply_go_down_too(self) -> None:
        # One write, because each half alone is a state the next tick reads
        # wrong: a park left standing asks a human a question they answered,
        # and an unconsumed command authorizes whatever is parked next.
        self._tick()

        pinned = self._pinned()
        self.assertFalse(pinned.get(_stage_support.KEYS.awaiting))
        self.assertIsNone(pinned.get(_stage_support.KEYS.park_reason))
        self.assertGreaterEqual(
            pinned.get(KEY_LAST_ACTION_COMMENT_ID), self.commanded.id,
        )

    def test_a_repeated_command_publishes_once(self) -> None:
        # A human who wrote it twice made one decision. The second reading
        # writes the same terms over the same terms, so a duplicate costs
        # nothing and says nothing twice.
        self._command()

        self._tick()

        said = [body for body in self._bodies() if ACCEPTED_NOTICE in body]
        self.assertEqual(len(said), SAID_ONCE)
        self.assertEqual(self._pinned().get(_stage_support.KEYS.exempt_sha), _stage_support.CANDIDATE_SHA)

    def test_a_repeat_after_publication_is_moot(self) -> None:
        self._tick()
        self._command()

        outcome = self._tick()

        # The generation the decision was about is retired, so this issue is
        # no longer a late adjudication at all and the command names nothing.
        self.spawn.assert_not_called()
        self.assertEqual(outcome.disposition, _LateDisposition.NOT_LATE)
        self.assertEqual(self._pinned().get(_stage_support.KEYS.exempt_sha), _stage_support.CANDIDATE_SHA)


class RefusedAuthorizationTest(_AuthorizeCase):
    """Every command this park cannot act on leaves it exactly as it was."""

    def test_another_commit_is_refused(self) -> None:
        for named in _NOT_THE_CANDIDATE:
            with self.subTest(named=named):
                self.setUp()
                _support.reply(self.issue, _support.authorization(named).strip())

                outcome = self._tick()

                self.spawn.assert_not_called()
                self.assertEqual(outcome.disposition, _LateDisposition.PARKED)
                self._assert_still_parked()
                said = self._bodies()[-1]
                self.assertIn(WRONG_CANDIDATE_NOTICE, said)
                # The sentence carries the commit that WOULD have worked, so
                # the human's next comment is one this park can act on.
                self.assertIn(_stage_support.CANDIDATE_SHA, said)

    def test_a_bare_continue_is_refused(self) -> None:
        _support.reply(self.issue, _support.BARE_CONTINUE)

        outcome = self._tick()

        self.assertEqual(outcome.disposition, _LateDisposition.PARKED)
        self._assert_still_parked()
        self.assertIn(CONTINUE_REFUSED_NOTICE, self._bodies()[-1])

    def test_a_refusal_is_said_once(self) -> None:
        # The command is consumed with the answer, so a park that stands for
        # as long as the human takes does not bury its own question under a
        # refusal repeated every poll.
        self._command(_stage_support.OTHER_SHA)
        self._tick()

        self._tick()

        refused = [
            body for body in self._bodies()
            if WRONG_CANDIDATE_NOTICE in body
        ]
        self.assertEqual(len(refused), SAID_ONCE)

    def test_a_lost_write_says_it_once(self) -> None:
        # The sentence and the write that consumes what it answers are two
        # operations. A tick that says it and then fails to record it reads
        # the same command again on the next poll, and the receipt already on
        # the thread is what keeps that reading from saying it twice.
        commanded = self._command(_stage_support.OTHER_SHA)
        with refused_write(self.github), self.assertRaises(RuntimeError):
            self._tick()
        self.assertEqual(len(self._bodies()), SAID_ONCE)

        outcome = self._tick()

        self.assertEqual(outcome.disposition, _LateDisposition.PARKED)
        refused = [
            body for body in self._bodies()
            if WRONG_CANDIDATE_NOTICE in body
        ]
        self.assertEqual(len(refused), SAID_ONCE)
        # The retry is what finally consumes the command, so a third tick has
        # nothing left to answer either.
        self._assert_still_parked()
        self.assertGreaterEqual(
            self._pinned().get(KEY_LAST_ACTION_COMMENT_ID), commanded.id,
        )

    def test_a_later_reply_earns_its_own_answer(self) -> None:
        # The receipt is scoped to the reading it answers, not to the park, so
        # a human who writes a second wrong command is not met with silence.
        self._command(_stage_support.OTHER_SHA)
        self._tick()

        self._command(_stage_support.OTHER_SHA)
        self._tick()

        refused = [
            body for body in self._bodies()
            if WRONG_CANDIDATE_NOTICE in body
        ]
        self.assertEqual(len(refused), 2)

    def test_an_unreadable_pair_keeps_the_command(self) -> None:
        # A store that cannot hand back the content between two commits it
        # holds is repaired by an operator, not by a comment -- so nothing is
        # said, nothing is consumed, and the next tick reads the same command.
        self._command()

        outcome = self._tick(worktree=_UNFINGERPRINTED)

        self.assertEqual(outcome.disposition, _LateDisposition.PARKED)
        self._assert_still_parked()
        self.assertEqual(self._bodies(), [])

        healed = self._tick()

        self.assertEqual(healed.disposition, _LateDisposition.SETTLED)
        self.assertEqual(self._pinned().get(_stage_support.KEYS.exempt_sha), _stage_support.CANDIDATE_SHA)


class UnauthorizedReplyTest(_AuthorizeCase):
    """Who may say it, when, and in what shape -- and what the rest mean."""

    def test_an_outsider_authorizes_nothing(self) -> None:
        # The allowlist is applied where the thread is read, so an outsider's
        # comment is not in the reading this owner is handed at all: it is not
        # a command, not guidance, and not something to answer.
        self.issue.comments.append(_support.human_comment(
            OUTSIDER_COMMENT_ID, _support.authorization(), login=_support.OUTSIDER,
        ))

        with patch.object(config, ALLOWED_AUTHORS, (_support.HUMAN,)):
            outcome = self._tick()

        self.assertEqual(outcome.disposition, _LateDisposition.PARKED)
        self.assertEqual(self._bodies(), [])
        self._assert_still_parked()

    def test_a_comment_before_the_park_is_stale(self) -> None:
        # A command posted below the park's own notice was written before the
        # question was put, so it is not an answer to it.
        self.issue.comments.append(
            _support.human_comment(EARLY_COMMENT_ID, _support.authorization()),
        )

        outcome = self._tick()

        self.assertEqual(outcome.disposition, _LateDisposition.PARKED)
        self._assert_still_parked()

    def test_prose_around_it_resumes_the_dev(self) -> None:
        # Not the whole comment, so not the command: those are words about the
        # change, and words about the change reopen the work rather than
        # publishing it.
        _support.reply(self.issue, f"{_support.authorization()}\n\nbut drop the retry loop")

        self._assert_reopened_the_work()

    def test_guidance_beside_it_outranks_it(self) -> None:
        # Two comments saying opposite things. The safe reading of a human who
        # wrote both is the one that publishes nothing.
        self._command()
        _support.reply(self.issue, "take the migration out of this one")

        self._assert_reopened_the_work()

    def _assert_reopened_the_work(self) -> None:
        """The developer ran, and nothing about a publication was recorded.

        What the resumed run then leaves is the revision owner's own subject,
        so what is asserted here is that the road was entered at all: an agent
        spawned as the developer, and no authorization on the record.
        """
        self._tick()

        self.spawn.assert_called_once()
        self.assertEqual(
            self._events_named(_support.EVENT_AGENT_SPAWN)[-1]["agent_role"],
            _support.ROLE_DEVELOPER,
        )
        self.assertIsNone(self._authorized())
        self.assertNotIn(_stage_support.KEYS.exempt_sha, self._pinned())


class DriftedAuthorizationTest(_AuthorizeCase):
    """Requirements that moved outrank a decision taken before they did."""

    def test_an_edit_parks_the_command_unread(self) -> None:
        self.issue.title = _support.EDITED_TITLE
        self._command()

        outcome = self._tick()

        self.assertEqual(outcome.disposition, _LateDisposition.PARKED)
        pinned = self._pinned()
        self.assertEqual(pinned.get(_stage_support.KEYS.park_reason), _support.PARK_CONTENT_DRIFT)
        self.assertIsNone(self._authorized())
        self.assertNotIn(_stage_support.KEYS.exempt_sha, pinned)


class PublishedCandidateTest(_AuthorizeCase):
    """A candidate measured against a pull request the remote already has.

    The road where the settlement itself pushes: this tick is the last one
    holding the head the reading was frozen at, so the branch is put where the
    verdict said it may go and the issue goes back to the stage the gate took
    it out of rather than to `implementing`.
    """

    def setUp(self) -> None:
        self._park(generation=published_generation())
        seed_published_pr(self.github)
        self._command()

    def test_it_pushes_and_hands_the_issue_back(self) -> None:
        outcome = self._tick()

        self.assertEqual(outcome.disposition, _LateDisposition.SETTLED)
        pinned = self._pinned()
        self.assertEqual(pinned.get(_stage_support.KEYS.exempt_sha), _stage_support.CANDIDATE_SHA)
        self.assertEqual(
            self.github.workflow_label(self.issue), _stage_support.PUBLISHED_SOURCE_STAGE,
        )
        # Nothing is owed once the push has landed, which is what says it did:
        # a debt left on the record would freeze this branch out of the base
        # refresh for good, and a push that missed keeps one (below).
        self.assertIsNone(pinned.get(_stage_support.KEYS.approved_sha))

    def test_a_refused_push_keeps_the_authorization(self) -> None:
        # The record is durable ahead of every effect it licenses, so a push
        # that did not land parks with the decision intact and the retry asks
        # for the same commit rather than for the human again.
        outcome = self._tick(worktree=WorktreeSeed(push=False))

        self.assertEqual(outcome.disposition, _LateDisposition.PARKED)
        pinned = self._pinned()
        self.assertEqual(self._authorized(), _stage_support.CANDIDATE_SHA)
        self.assertEqual(pinned.get(_stage_support.KEYS.approved_sha), _stage_support.CANDIDATE_SHA)
        self.assertEqual(pinned.get(_stage_support.KEYS.approved_lease), _stage_support.PUBLISHED_HEAD_SHA)


class AuthorizationRecoveryTest(_AuthorizeCase):
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
            ("no reading at all", _UNFINGERPRINTED),
            ("a contribution that moved", _MOVED_CONTRIBUTION),
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
        self._tick(worktree=_UNFINGERPRINTED)

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


class ReplacedAnswerTest(_AuthorizeCase):
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
        _support.reply(self.issue, _support.BARE_CONTINUE)

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
        _support.reply(self.issue)

        revised = self._tick(
            reply=DEV_ACK,
            worktree=UNCHANGED,
            measurement=_UNCHANGED_MEASUREMENT,
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


class ReadjudicatedAuthorizationTest(_AuthorizeCase):
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
            NO_VERDICT_NOTICE, "".join(self._bodies()),
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
