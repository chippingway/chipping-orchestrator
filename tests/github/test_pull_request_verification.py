# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Publishing and finding verification artifacts on a pull request.

One contract, held against the real client and against the shared fake: which
reading licenses a post, what an unanswered request is answered with, that a
retry finds the exact artifact GitHub already accepted, that ownership takes
our author and our exact rendering together, that a settled artifact is re-read
at its own comment as exactly that, and that neither the description nor the
developer report beside it is ever written.
"""
from __future__ import annotations

import unittest

from orchestrator.github import comments as _trust
from orchestrator.github.developer_reports import content_digest, render_developer_report
from orchestrator.github.pinned_state import MAX_PINNED_BODY
from orchestrator.github.pull_request_reports import (
    ReportLocation,
    ReportLookup,
    ReportPresence,
)
from orchestrator.github.verification_artifacts import render_verification_artifact
from orchestrator.github.verification_evidence import (
    ArtifactRefusedError,
    EvidenceSource,
    VerifiedCommand,
)
from tests.github import report_test_support as support
from tests.support.fakes import (
    UnreadableUser,
    make_developer_report,
    make_verification_artifact,
)

_GITHUB_LOG = "orchestrator.github"
_WARNING = "WARNING"
_HUMAN_LOGIN = "alice"
_ARTIFACT = make_verification_artifact(support.PR_NUMBER)
# The next artifact on the same commit: another transaction rather than a
# retry, and a reviewer's account rather than a run of this orchestrator's.
_LATER = make_verification_artifact(
    support.PR_NUMBER,
    artifact_revision=2,
    receipt="issue-7-verification-2",
    source=EvidenceSource.REVIEWER_REPORTED,
    commands=(VerifiedCommand("uv run pytest tests", 0, "1 failed"),),
)
_REPORT = make_developer_report(support.PR_NUMBER)
_PUBLISHED = render_verification_artifact(_ARTIFACT)
_UNCONFIRMED = ReportLookup(ReportPresence.UNCONFIRMED)


def _publish(case, artifact=_ARTIFACT) -> ReportLookup:
    """Publish one verification artifact onto the case's pull request."""
    return case.gh.publish_verification_artifact(case.pull_request, artifact)


class _PublicationContract:
    """An artifact is appended once beside everything already there."""

    def test_an_artifact_is_appended_once(self) -> None:
        # A retry finds what the first call posted instead of posting again,
        # and neither writes the description: the closing reference,
        # attribution, legacy tail, and maintainer's sentence survive because
        # nothing rewrote them. The comment carries the ordinary orchestrator
        # marker, so no feedback scan reads it back as a human's.
        first, again = [_publish(self) for _ in range(2)]

        posted = self.pull_request.issue_comments
        self.assertEqual([comment.body for comment in posted], [_PUBLISHED])
        self.assertEqual(posted[0].user.login, support.BOT_LOGIN)
        self.assertIn(_trust.ORCHESTRATOR_COMMENT_MARKER, posted[0].body)
        self.assertEqual(self.posted_comments(), [(support.PR_NUMBER, _PUBLISHED)])
        self.assertEqual(first, ReportLookup(ReportPresence.PRESENT, posted[0]))
        self.assertIs(again.presence, ReportPresence.PRESENT)
        self.assertIs(again.found, first.found)
        self.assertEqual(self.pull_request.body, support.LEGACY_BODY)
        self.assertEqual(self.description_writes(), [])

    def test_later_evidence_leaves_earlier_in_place(self) -> None:
        # Two artifacts and a developer report on one commit, each a
        # transaction of its own: the artifacts read as an ordered history,
        # and neither touches the report's own source identity.
        _publish(self)
        self.gh.publish_developer_report(self.pull_request, _REPORT)

        later = _publish(self, _LATER)

        self.assertIs(later.presence, ReportPresence.PRESENT)
        self.assertEqual(
            [comment.body for comment in self.pull_request.issue_comments],
            [_PUBLISHED, render_developer_report(_REPORT), render_verification_artifact(_LATER)],
        )

    def test_a_pasted_copy_proves_nothing(self) -> None:
        # The header is an HTML comment anybody can copy. Under another author
        # it neither satisfies the retry nor holds the post back.
        self.seed(_PUBLISHED, login=_HUMAN_LOGIN)

        found = self.gh.find_verification_artifact(self.pull_request, _ARTIFACT)
        published = _publish(self)

        self.assertEqual(found, ReportLookup(ReportPresence.ABSENT))
        self.assertIs(published.presence, ReportPresence.PRESENT)
        self.assertEqual(published.found.user.login, support.BOT_LOGIN)

    def test_our_edited_artifact_holds_the_post(self) -> None:
        # A maintainer's edit leaves the comment attributed to us and its
        # receipt naming this transaction, so a second comment would be a
        # second claim to it -- the caller is told instead.
        edited = self.seed(
            _PUBLISHED.replace("exit 0", "exit 1", 1),
            login=support.BOT_LOGIN,
        )

        held = _publish(self)

        self.assertEqual(held, ReportLookup(ReportPresence.CHANGED, edited))
        self.assertEqual(self.pull_request.issue_comments, [edited])


class _RecoveryContract:
    """Nothing unanswered counts as published, and a reread is exact."""

    def test_an_unpublishable_artifact_asks_nothing(self) -> None:
        # Every read fails here, so an artifact that reached the thread would
        # come back unconfirmed: the refusal is what proves nothing was asked.
        self.refuse(support.UNREADABLE)
        oversized = make_verification_artifact(
            support.PR_NUMBER,
            commands=(VerifiedCommand("check", 0, "y" * MAX_PINNED_BODY),),
        )
        elsewhere = make_verification_artifact(support.OTHER_PR_NUMBER)
        for artifact in (oversized, elsewhere):
            with (
                self.subTest(pr_number=artifact.pr_number),
                self.assertRaises(ArtifactRefusedError),
            ):
                _publish(self, artifact)
        self.assertEqual(self.pull_request.issue_comments, [])

    def test_unanswered_is_unconfirmed_until_reread(self) -> None:
        # (how the request went unanswered, comments GitHub holds afterwards)
        for failure, landed in (
            (support.UNREADABLE, 0),
            (support.REFUSED, 0),
            (support.LOST, 1),
        ):
            with self.subTest(failure=failure):
                self.setUp()
                self.refuse(failure)
                with self.assertLogs(_GITHUB_LOG, _WARNING):
                    unanswered = _publish(self)
                held = len(self.pull_request.issue_comments)
                self.refuse(None)

                retried = _publish(self)

                self.assertEqual(unanswered, _UNCONFIRMED)
                self.assertEqual(held, landed)
                self.assertIs(retried.presence, ReportPresence.PRESENT)
                self.assertEqual(
                    [comment.body for comment in self.pull_request.issue_comments],
                    [_PUBLISHED],
                )

    def test_an_unreadable_author_is_unconfirmed(self) -> None:
        # Our own rendering, under an author GitHub would not name: whose it
        # is decides PRESENT from ABSENT, so neither is answered, nothing is
        # posted beside it, and the next reading tells them apart.
        landed = self.seed(_PUBLISHED, login=support.BOT_LOGIN)
        author = landed.user
        landed.user = UnreadableUser()

        with self.assertLogs(_GITHUB_LOG, _WARNING):
            unread = self._both_readings()
        landed.user = author
        reread = self._both_readings()

        present = ReportLookup(ReportPresence.PRESENT, landed)
        self.assertEqual(unread, [_UNCONFIRMED, _UNCONFIRMED])
        self.assertEqual(reread, [present, present])
        self.assertEqual(self.pull_request.issue_comments, [landed])

    def test_a_published_artifact_is_reread_exactly(self) -> None:
        # What proves an artifact unchanged is the digest of the body sitting
        # there NOW, against the exact pull request and comment it was read
        # off: an edit moves it off the revision somebody verified, and the
        # same comment id asked of another pull request is not there.
        posted = _publish(self).found
        readings = [self._reread(ReportLocation(support.PR_NUMBER, posted.id), _PUBLISHED)]
        posted.body = _PUBLISHED.replace("exit 0", "exit 1", 1)
        readings.append(self._reread(ReportLocation(support.PR_NUMBER, posted.id), _PUBLISHED))
        readings.append(
            self._reread(ReportLocation(support.OTHER_PR_NUMBER, posted.id), _PUBLISHED),
        )

        self.assertEqual(readings, [
            (ReportPresence.PRESENT, posted),
            (ReportPresence.CHANGED, posted),
            (ReportPresence.ABSENT, None),
        ])

    def _both_readings(self) -> list[ReportLookup]:
        """What a lookup and then a publication each read of the artifact."""
        reads = (
            self.gh.find_verification_artifact,
            self.gh.publish_verification_artifact,
        )
        return [read(self.pull_request, _ARTIFACT) for read in reads]

    def _reread(self, where: ReportLocation, verified: str) -> tuple:
        """Reread one location against the revision of `verified`."""
        reading = self.gh.reread_report_location(
            where, content_sha256=content_digest(verified),
        )
        return reading.presence, reading.found


class _RereadContract:
    """A settled artifact is re-read at its comment, and only ours counts."""

    def test_an_artifact_is_reread_at_its_comment(self) -> None:
        # Present only as ours, byte for byte, at that very comment: a pasted
        # copy, a comment the thread no longer carries, and an edit are each
        # what they are, and a thread nobody could read says nothing.
        posted = self.gh.publish_verification_artifact(self.pull_request, _ARTIFACT).found
        pasted = self.seed(_PUBLISHED, login=_HUMAN_LOGIN)
        asked = (posted.id, pasted.id, pasted.id + 1)
        readings = [self._at(comment_id) for comment_id in asked]
        posted.body = _PUBLISHED.replace("exit 0", "exit 1", 1)
        readings.append(self._at(posted.id))
        self.refuse(support.UNREADABLE)
        with self.assertLogs(_GITHUB_LOG, _WARNING):
            readings.append(self._at(posted.id))

        self.assertEqual(readings, [
            (ReportPresence.PRESENT, _ARTIFACT),
            (ReportPresence.CHANGED, None),
            (ReportPresence.ABSENT, None),
            (ReportPresence.CHANGED, None),
            (ReportPresence.UNCONFIRMED, None),
        ])
        self.assertEqual(self.posted_comments(), [(support.PR_NUMBER, _PUBLISHED)])

    def _at(self, comment_id: int) -> tuple:
        """What one comment on the case's pull request is, as an artifact."""
        return self.gh.reread_verification_artifact(self.pull_request, comment_id)


class _VerificationContract(_PublicationContract, _RecoveryContract, _RereadContract):
    """Everything the real client and the shared fake answer alike."""


class WireClientArtifactTest(support.WireBackend, _VerificationContract, unittest.TestCase):
    """The contract, over the requests production makes."""


class FakeClientArtifactTest(support.FakeBackend, _VerificationContract, unittest.TestCase):
    """The contract, over the double stage tests publish through."""


if __name__ == "__main__":
    unittest.main()
