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

from unittest.mock import patch

from orchestrator.config import settings as config
from orchestrator.workflow.late_split import overrides as _overrides
from orchestrator.workflow.stages.decomposition.late_models import (
    _LateDisposition,
)
from tests.workflow.stages.decomposition import (
    late_authorize_case as _authorize_case,
    late_content_replies as _content_replies,
    late_content_support as _support,
    late_test_support as _stage_support,
)
from tests.workflow.stages.decomposition.late_published_support import (
    published_generation,
    seed_published_pr,
)
from tests.workflow.stages.decomposition.late_run_support import WorktreeSeed


class AuthorizedPublicationTest(_authorize_case._AuthorizeCase):
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
            self.github.workflow_label(self.issue), _authorize_case.LABEL_IMPLEMENTING,
        )
        self.assertIn(_authorize_case.ACCEPTED_NOTICE, self._bodies()[-1])

    def test_the_record_names_what_was_authorized(self) -> None:
        self._tick()

        pinned = self._pinned()
        for key, term in _authorize_case._AUTHORIZED_TERMS:
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
            pinned.get(_authorize_case.KEY_LAST_ACTION_COMMENT_ID), self.commanded.id,
        )

    def test_a_repeated_command_publishes_once(self) -> None:
        # A human who wrote it twice made one decision. The second reading
        # writes the same terms over the same terms, so a duplicate costs
        # nothing and says nothing twice.
        self._command()

        self._tick()

        said = [body for body in self._bodies() if _authorize_case.ACCEPTED_NOTICE in body]
        self.assertEqual(len(said), _authorize_case.SAID_ONCE)
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


class RefusedAuthorizationTest(_authorize_case._AuthorizeCase):
    """Every command this park cannot act on leaves it exactly as it was."""

    def test_another_commit_is_refused(self) -> None:
        for named in _authorize_case._NOT_THE_CANDIDATE:
            with self.subTest(named=named):
                self.setUp()
                _content_replies.reply(self.issue, _content_replies.authorization(named).strip())

                outcome = self._tick()

                self.spawn.assert_not_called()
                self.assertEqual(outcome.disposition, _LateDisposition.PARKED)
                self._assert_still_parked()
                said = self._bodies()[-1]
                self.assertIn(_authorize_case.WRONG_CANDIDATE_NOTICE, said)
                # The sentence carries the commit that WOULD have worked, so
                # the human's next comment is one this park can act on.
                self.assertIn(_stage_support.CANDIDATE_SHA, said)

    def test_a_bare_continue_is_refused(self) -> None:
        _content_replies.reply(self.issue, _support.BARE_CONTINUE)

        outcome = self._tick()

        self.assertEqual(outcome.disposition, _LateDisposition.PARKED)
        self._assert_still_parked()
        self.assertIn(_authorize_case.CONTINUE_REFUSED_NOTICE, self._bodies()[-1])

    def test_a_refusal_is_said_once(self) -> None:
        # The command is consumed with the answer, so a park that stands for
        # as long as the human takes does not bury its own question under a
        # refusal repeated every poll.
        self._command(_stage_support.OTHER_SHA)
        self._tick()

        self._tick()

        refused = [
            body for body in self._bodies()
            if _authorize_case.WRONG_CANDIDATE_NOTICE in body
        ]
        self.assertEqual(len(refused), _authorize_case.SAID_ONCE)

    def test_a_lost_write_says_it_once(self) -> None:
        # The sentence and the write that consumes what it answers are two
        # operations. A tick that says it and then fails to record it reads
        # the same command again on the next poll, and the receipt already on
        # the thread is what keeps that reading from saying it twice.
        commanded = self._command(_stage_support.OTHER_SHA)
        with _authorize_case.refused_write(self.github), self.assertRaises(RuntimeError):
            self._tick()
        self.assertEqual(len(self._bodies()), _authorize_case.SAID_ONCE)

        outcome = self._tick()

        self.assertEqual(outcome.disposition, _LateDisposition.PARKED)
        refused = [
            body for body in self._bodies()
            if _authorize_case.WRONG_CANDIDATE_NOTICE in body
        ]
        self.assertEqual(len(refused), _authorize_case.SAID_ONCE)
        # The retry is what finally consumes the command, so a third tick has
        # nothing left to answer either.
        self._assert_still_parked()
        self.assertGreaterEqual(
            self._pinned().get(_authorize_case.KEY_LAST_ACTION_COMMENT_ID), commanded.id,
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
            if _authorize_case.WRONG_CANDIDATE_NOTICE in body
        ]
        self.assertEqual(len(refused), 2)

    def test_an_unreadable_pair_keeps_the_command(self) -> None:
        # A store that cannot hand back the content between two commits it
        # holds is repaired by an operator, not by a comment -- so nothing is
        # said, nothing is consumed, and the next tick reads the same command.
        self._command()

        outcome = self._tick(worktree=_authorize_case._UNFINGERPRINTED)

        self.assertEqual(outcome.disposition, _LateDisposition.PARKED)
        self._assert_still_parked()
        self.assertEqual(self._bodies(), [])

        healed = self._tick()

        self.assertEqual(healed.disposition, _LateDisposition.SETTLED)
        self.assertEqual(self._pinned().get(_stage_support.KEYS.exempt_sha), _stage_support.CANDIDATE_SHA)


class UnauthorizedReplyTest(_authorize_case._AuthorizeCase):
    """Who may say it, when, and in what shape -- and what the rest mean."""

    def test_an_outsider_authorizes_nothing(self) -> None:
        # The allowlist is applied where the thread is read, so an outsider's
        # comment is not in the reading this owner is handed at all: it is not
        # a command, not guidance, and not something to answer.
        self.issue.comments.append(_content_replies.human_comment(
            _authorize_case.OUTSIDER_COMMENT_ID, _content_replies.authorization(), login=_support.OUTSIDER,
        ))

        with patch.object(config, _authorize_case.ALLOWED_AUTHORS, (_content_replies.HUMAN,)):
            outcome = self._tick()

        self.assertEqual(outcome.disposition, _LateDisposition.PARKED)
        self.assertEqual(self._bodies(), [])
        self._assert_still_parked()

    def test_a_comment_before_the_park_is_stale(self) -> None:
        # A command posted below the park's own notice was written before the
        # question was put, so it is not an answer to it.
        self.issue.comments.append(
            _content_replies.human_comment(_authorize_case.EARLY_COMMENT_ID, _content_replies.authorization()),
        )

        outcome = self._tick()

        self.assertEqual(outcome.disposition, _LateDisposition.PARKED)
        self._assert_still_parked()

    def test_prose_around_it_resumes_the_dev(self) -> None:
        # Not the whole comment, so not the command: those are words about the
        # change, and words about the change reopen the work rather than
        # publishing it.
        _content_replies.reply(self.issue, f"{_content_replies.authorization()}\n\nbut drop the retry loop")

        self._assert_reopened_the_work()

    def test_guidance_beside_it_outranks_it(self) -> None:
        # Two comments saying opposite things. The safe reading of a human who
        # wrote both is the one that publishes nothing.
        self._command()
        _content_replies.reply(self.issue, "take the migration out of this one")

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


class DriftedAuthorizationTest(_authorize_case._AuthorizeCase):
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


class PublishedCandidateTest(_authorize_case._AuthorizeCase):
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
