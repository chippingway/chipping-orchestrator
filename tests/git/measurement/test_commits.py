# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Freezing the base and proving the candidate against real repositories.

Both ends of a measurement are pinned here for the same reason: what makes
either of them worth anything is that a later tick, a retry after a crash, and
a human reading the diff all get the same two commits. So the base is checked
against a remote that moves and a local ref that lies, and the candidate
against ids this repository does and does not hold.

What a base nobody could freeze REPORTS is pinned here too, and against a
remote that really fails: the typed reason names the step, the line beside it
names the fault, and the token the call spent is in neither.
"""
from __future__ import annotations

import os
import subprocess
import unittest
from collections.abc import Iterator
from contextlib import contextmanager
from unittest.mock import patch

from orchestrator import config
from orchestrator.git import branch_transport, credentials, ref_transport
from orchestrator.git.measurement import commits
from orchestrator.git.measurement.models import MeasurementFailure
from tests.git.measurement import measurement_test_support as _support

_REMOTE_BASE_READ = "_remote_branch_read"
_TARGET_FETCH = "_authed_target_fetch"
_FEATURE_PATH = "feature.py"
_TAG_NAME = "v1"

# A token no report may carry. git names the remote it could not reach in its
# own stderr, so a URL carrying the token is the shape a leak really takes --
# and the only shape a scrub is worth asserting against.
_LEAKED_TOKEN = "ghp-token-that-must-never-be-reported"

# What one failed transport call really says, and what a caller may keep of it.
# The lines after the first are git's advice rather than its answer, which is
# why only the first travels.
_TRANSPORT_STDERR = (
    "fatal: could not read Username for 'https://github.com': "
    "terminal prompts disabled\n"
    "fatal: Could not read from remote repository.\n"
)

_TRANSPORT_FIRST_LINE = _TRANSPORT_STDERR.split("\n")[0]


@contextmanager
def _leaking_session(
    spec, token: str, *, include_identity: bool = False,
) -> Iterator[credentials._GitAuthSession]:
    """A session whose remote URL carries the token git will echo back.

    The real envelope keeps the token out of the URL entirely, so the stderr a
    failed call writes normally has nothing in it to scrub. That makes the
    honest shape the one shape a redaction cannot be checked against: what has
    to be pinned is that the scrub really runs over git's own output, and that
    needs output the token is genuinely in. The URL names a path nothing holds,
    so every call through it fails locally and at once, quoting the path -- and
    the token inside it -- back on its first stderr line.
    """
    yield credentials._GitAuthSession(
        token=token,
        auth_url=f"/no-such-remote-{token}.git",
        env={**os.environ, "GIT_TERMINAL_PROMPT": "0"},
    )


@contextmanager
def _a_leaking_remote() -> Iterator[None]:
    """Run the real token-bearing calls against a remote that names the token.

    Both halves are needed for a call to reach git at all: a token this
    deployment can resolve for the repository, and a session built around it.
    """
    with patch.object(
        config, "_resolve_github_token", return_value=_LEAKED_TOKEN,
    ), patch.object(credentials, "_git_auth_session", _leaking_session):
        yield


def _failed_fetch(stderr: str) -> subprocess.CompletedProcess:
    """One fetch that brought nothing back, reporting `stderr` for itself."""
    return subprocess.CompletedProcess(
        args=["git", "fetch"], returncode=1, stdout="", stderr=stderr,
    )


class BaseFreezeTest(unittest.TestCase):
    """The frozen base is the remote's answer, proven present in this store."""

    def setUp(self) -> None:
        self._repo = _support.CandidateRepo()
        self._repo.prepare(self)

    def test_the_remote_tip_is_what_is_frozen(self) -> None:
        frozen = commits._freeze_base_commit(
            self._repo.spec, self._repo.worktree,
        )

        self.assertTrue(frozen.is_frozen)
        self.assertEqual(frozen.sha, self._repo.base())

    def test_a_repointed_local_ref_decides_nothing(self) -> None:
        # `refs/remotes/origin/main` lives in the store the agent's worktree
        # shares. Pointed at the candidate, a base-relative diff would measure
        # the agent's work against itself and report a candidate of no size.
        remote_tip = self._repo.base()
        candidate = self._repo.commit({_FEATURE_PATH: "one\ntwo\n"})
        _support.point_local_base_at(self._repo, candidate)

        frozen = commits._freeze_base_commit(
            self._repo.spec, self._repo.worktree,
        )

        self.assertEqual(frozen.sha, remote_tip)

    def test_a_base_this_clone_lacks_is_fetched(self) -> None:
        # The base advances between the tick's fetch and the measurement, so
        # the tip the remote names is routinely an object this clone has not
        # seen. One fetch is what turns that into a base a diff can be taken
        # against, rather than a failure nobody had to take.
        advanced = self._repo.advance_base_from_elsewhere()

        frozen = commits._freeze_base_commit(
            self._repo.spec, self._repo.worktree,
        )

        self.assertEqual(frozen.sha, advanced)

    def test_a_base_still_missing_is_typed(self) -> None:
        # The remote rewrote the branch, or the fetch brought nothing: either
        # way no diff can be taken, and a candidate with no diff is unmeasured
        # rather than small.
        with patch.object(
            branch_transport, _REMOTE_BASE_READ,
            return_value=ref_transport._RefRead(sha=_support.ABSENT_SHA),
        ):
            frozen = commits._freeze_base_commit(
                self._repo.spec, self._repo.worktree,
            )

        self.assertEqual(frozen.failure, MeasurementFailure.BASE_ABSENT)
        self.assertFalse(frozen.is_frozen)

    def test_a_missing_base_keeps_the_id_it_learned(self) -> None:
        # The remote NAMED it, so the id is the only record of which commit
        # this attempt was about -- and the only thing a retry can ask for. A
        # failure recorded without it leaves the next pass re-reading a remote
        # whose base has moved on, measuring a different pair. Nothing may
        # measure against it either way, which `is_frozen` above refuses.
        with patch.object(
            branch_transport, _REMOTE_BASE_READ,
            return_value=ref_transport._RefRead(sha=_support.ABSENT_SHA),
        ):
            frozen = commits._freeze_base_commit(
                self._repo.spec, self._repo.worktree,
            )

        self.assertEqual(frozen.sha, _support.ABSENT_SHA)

    def test_an_unanswered_remote_is_typed(self) -> None:
        # None is the read having failed -- no token, hijackable transport
        # config, an unreachable host -- and "" is the remote saying it does
        # not carry the branch. Neither establishes a commit.
        for answer in (None, ""):
            with self.subTest(answer=answer):
                with patch.object(
                    branch_transport, _REMOTE_BASE_READ,
                    return_value=ref_transport._RefRead(sha=answer),
                ):
                    frozen = commits._freeze_base_commit(
                        self._repo.spec, self._repo.worktree,
                    )

                self.assertEqual(
                    frozen.failure, MeasurementFailure.BASE_UNREADABLE,
                )
                self.assertFalse(frozen.is_frozen)


class BaseFailureDetailTest(unittest.TestCase):
    """A base nobody could freeze says what the step that stopped reported.

    The typed reason names the step; the line beside it names the fault. They
    are read a long way from here -- persisted, reported on both sinks, and
    turned into a park a human answers -- so what the transport wrote has to
    travel with the failure or be lost with the process that took it.
    """

    def setUp(self) -> None:
        self._repo = _support.CandidateRepo()
        self._repo.prepare(self)

    def test_a_read_that_failed_reports_what_git_said(self) -> None:
        # "The remote would not name the base" covers an expired token, a
        # repository this installation was never granted, and a host that was
        # simply down. Only git's own line says which, and an operator with the
        # step alone has the whole transport to rule out.
        frozen = self._frozen_with(
            ref_transport._RefRead(detail=_TRANSPORT_FIRST_LINE),
        )

        self.assertEqual(frozen.failure, MeasurementFailure.BASE_UNREADABLE)
        self.assertEqual(frozen.detail, _TRANSPORT_FIRST_LINE)

    def test_a_branch_the_remote_lacks_says_so_itself(self) -> None:
        # Nothing failed: the read succeeded and answered that the branch is
        # not there. A record left silent here would send an operator looking
        # for a transport fault that never happened.
        frozen = self._frozen_with(ref_transport._RefRead(sha=""))

        self.assertEqual(frozen.failure, MeasurementFailure.BASE_UNREADABLE)
        self.assertEqual(frozen.detail, commits._NO_SUCH_BRANCH)

    def test_an_unfetchable_base_quotes_the_fetch(self) -> None:
        # The base the remote named is one this store does not hold and the
        # fetch could not bring. What the fetch said is the only thing telling
        # the two apart -- and only its first line travels, since the lines
        # after it are git's advice rather than its answer.
        frozen = self._frozen_with(
            ref_transport._RefRead(sha=_support.ABSENT_SHA),
            fetch_stderr=_TRANSPORT_STDERR,
        )

        self.assertEqual(frozen.failure, MeasurementFailure.BASE_ABSENT)
        self.assertEqual(frozen.detail, _TRANSPORT_FIRST_LINE)

    def test_a_silent_fetch_still_names_itself(self) -> None:
        # A fetch that failed without writing anything and one that explained
        # itself are the same failure to the caller, and a record that said
        # nothing at all for the first would leave nowhere to start.
        frozen = self._frozen_with(
            ref_transport._RefRead(sha=_support.ABSENT_SHA),
        )

        self.assertEqual(frozen.failure, MeasurementFailure.BASE_ABSENT)
        self.assertEqual(frozen.detail, commits._FETCH_SAID_NOTHING)

    def _frozen_with(self, read, fetch_stderr: str = ""):
        """Freeze against a remote read, and a fetch, the test decides."""
        with patch.object(
            branch_transport, _REMOTE_BASE_READ, return_value=read,
        ), patch.object(
            branch_transport, _TARGET_FETCH,
            return_value=_failed_fetch(fetch_stderr),
        ):
            return commits._freeze_base_commit(
                self._repo.spec, self._repo.worktree,
            )


class ScrubbedDetailTest(unittest.TestCase):
    """What a token-bearing call reports is carried; the token never is.

    Both calls run for real here, against a remote that does not exist and
    whose URL names the credential. That is the one arrangement in which the
    scrub is observable: git quotes the remote it could not reach, so a
    redaction that was skipped would put the token straight into a record the
    orchestrator logs, pins, and shows a human.
    """

    def setUp(self) -> None:
        self._repo = _support.CandidateRepo()
        self._repo.prepare(self, patched_transport=False)

    def test_a_failed_tip_read_drops_the_token(self) -> None:
        spec, worktree = self._repo.spec, self._repo.worktree
        with _a_leaking_remote():
            frozen = commits._freeze_base_commit(spec, worktree)

        self.assertEqual(frozen.failure, MeasurementFailure.BASE_UNREADABLE)
        self._assert_scrubbed(frozen.detail)

    def test_a_failed_base_fetch_drops_the_token(self) -> None:
        with _a_leaking_remote():
            base = commits._base_object_present(
                self._repo.spec, self._repo.worktree, _support.ABSENT_SHA,
            )

        self.assertFalse(base.present)
        self._assert_scrubbed(base.detail)

    def _assert_scrubbed(self, detail: str) -> None:
        """The line came from git, kept the fault, and dropped the secret."""
        self.assertIn(credentials._REDACTED, detail)
        self.assertNotIn(_LEAKED_TOKEN, detail)
        self.assertNotIn("\n", detail)


class CandidateProofTest(unittest.TestCase):
    """A candidate is the exact id git resolved, and one this host holds."""

    def setUp(self) -> None:
        self._repo = _support.CandidateRepo()
        self._repo.prepare(self)

    def test_the_named_revision_is_resolved(self) -> None:
        # Named rather than left as HEAD: the branch moves, and a measurement
        # recorded against "whatever HEAD was" is one no retry can repeat.
        first = self._repo.commit({_FEATURE_PATH: "one\n"})
        latest = self._repo.commit({_FEATURE_PATH: "one\ntwo\n"})

        for revision, expected in (
            (first, first), (_support.CANDIDATE_BRANCH, latest),
        ):
            with self.subTest(revision=revision):
                proven = commits._prove_candidate_commit(
                    self._repo.worktree, revision,
                )
                self.assertTrue(proven.is_frozen)
                self.assertEqual(proven.sha, expected)

    def test_an_annotated_tag_peels_to_its_commit(self) -> None:
        # An annotated tag is an object of its own that points at the commit,
        # so a revision naming one resolves to the TAG's id. Recorded, that id
        # is evidence about a label rather than about the work: nothing
        # downstream could compare it to a branch tip, and the tag can be moved
        # or deleted while the commit cannot.
        candidate = self._repo.commit({_FEATURE_PATH: "one\n"})
        _support.run_git(
            "tag", "-a", _TAG_NAME, "-m", "release",
            cwd=self._repo.worktree, env_extra=_support.AUTHOR_ENV,
        )
        tag_object = _support.run_git(
            "rev-parse", "--verify", _TAG_NAME, cwd=self._repo.worktree,
        ).strip()

        proven = commits._prove_candidate_commit(
            self._repo.worktree, _TAG_NAME,
        )

        self.assertNotEqual(tag_object, candidate)
        self.assertEqual(proven.sha, candidate)

    def test_an_object_this_host_lacks_is_typed(self) -> None:
        # git resolves a full object id to itself without consulting the
        # store, so a candidate recorded on another host reads back looking
        # exactly like one that is here -- and the diff that spends it reports
        # no lines, which is what a candidate adding nothing reports too.
        proven = commits._prove_candidate_commit(
            self._repo.worktree, _support.ABSENT_SHA,
        )

        self.assertEqual(proven.failure, MeasurementFailure.CANDIDATE_ABSENT)
        self.assertFalse(proven.is_frozen)

    def test_an_absent_object_keeps_its_identity(self) -> None:
        # The id it resolved to is the only record of which commit the attempt
        # was about. Dropped, a retry has nothing to ask for and proves
        # whatever the checkout points at by then instead.
        proven = commits._prove_candidate_commit(
            self._repo.worktree, _support.ABSENT_SHA,
        )

        self.assertEqual(proven.sha, _support.ABSENT_SHA)

    def test_an_unresolvable_revision_is_typed(self) -> None:
        # Nothing was named, so nothing comes back named: a revision that will
        # not resolve is a checkout that cannot say what it is on.
        proven = commits._prove_candidate_commit(
            self._repo.worktree, "no-such-branch",
        )

        self.assertEqual(
            proven.failure, MeasurementFailure.CANDIDATE_UNREADABLE,
        )
        self.assertEqual(proven.sha, "")


if __name__ == "__main__":
    unittest.main()
