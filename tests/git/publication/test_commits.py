# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The message read and the bound message replacement on `commits`, in real git."""

from __future__ import annotations

import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from orchestrator import config
from orchestrator.git import commands
from orchestrator.git.publication import commits
from tests.support.git import _git_env, _run_git, _seed_target_root

EXECUTABLE_MODE = 0o755
HEAD_REVISION = "HEAD"
GIT_ADD = "add"
GIT_COMMIT = "commit"
GIT_CONFIG = "config"
GIT_LOG = "log"
LAST_COMMIT = "-1"
MESSAGE_FLAG = "-m"
VERBATIM = "--cleanup=verbatim"
HARDENED_HELPER = "_git_hardened"
UPDATE_REF = "update-ref"

# The object type a commit is read back as.
COMMIT_OBJECT = "commit"

# A whole message, body included, with a line a `strip` cleanup would drop.
COMMITTED_MESSAGE = "docs: explain the flag\n\n# a heading the body keeps\n"

# What the documenting stage amends that message to.
AMENDED_MESSAGE = "docs: explain the flag (#9)\n\n# a heading the body keeps\n"

# A message whose bytes a text read would change -- CR LF endings and a lone
# carriage return, beside a character beyond ASCII -- and the subject it is
# amended from and to.
RAW_SUBJECT = "docs: explain the flag"
RAW_REFERENCED_SUBJECT = "docs: explain the flag (#9)"
RAW_BODY = "\r\n\r\nbody line\r\nlone\rcarriage café\r\n".encode()

# How a message's bytes ride as text, which is what the owner reads them as.
MESSAGE_ENCODING = "utf-8"
LOSSLESS = "surrogateescape"

# A commit that lands on the checkout after the docs commit was read.
INTERLOPER_PATH = "later.txt"
INTERLOPER_MESSAGE = "feat: work nobody read\n"

# An object id no repository here holds.
MISSING_COMMIT = "0badc0de" * 5

STAGED_PATH = "staged.txt"
ORCHESTRATOR_NAME = "orch-bot"
ORCHESTRATOR_EMAIL = "orch-bot@example.com"

# The fields a replacement must keep: the author, the author date, the tree,
# and the parents.
KEPT_FIELDS_FORMAT = "--format=%an <%ae>%n%aI%n%T%n%P"
COMMITTER_FORMAT = "--format=%cn <%ce>"

# Hooks an agent could plant, each refusing what it runs for.
REFUSING_HOOKS = ("commit-msg", "reference-transaction")


class _CommitsBeforeTheSwap:
    """The hardened git runner, with a commit landing just before HEAD moves.

    It lets everything through, and lands `lands` on the checkout at the one
    moment a proof of HEAD taken up front could not see: the replacement
    already exists and HEAD has not been moved onto it yet.
    """

    def __init__(self, hardened, lands) -> None:
        self._hardened = hardened
        self._lands = lands
        self.landed = ""

    def __call__(self, *git_args: str, cwd, **options):
        if git_args[0] == UPDATE_REF:
            self.landed = self._lands()
        return self._hardened(*git_args, cwd=cwd, **options)


class _CommittedRepositoryMixin:
    """A real repository whose HEAD is a docs commit with a body."""

    def setUp(self) -> None:
        scratch = Path(
            self.enterContext(
                tempfile.TemporaryDirectory(
                    prefix="orch-commits-test-",
                    ignore_cleanup_errors=True,
                ),
            ),
        )
        repo, base = _seed_target_root(scratch)
        self.repo = repo
        self.base = base
        self.docs_commit = self._commits("docs.md", COMMITTED_MESSAGE)

    def _commits(self, path: str, message: str) -> str:
        """Commit one file under `message` verbatim, and return the new HEAD."""
        (self.repo / path).write_text(f"{path}\n")
        self._git(GIT_ADD, path)
        self._git(GIT_COMMIT, VERBATIM, MESSAGE_FLAG, message)
        return self._head()

    def _head(self) -> str:
        return self._git("rev-parse", HEAD_REVISION).strip()

    def _git(self, *args: str) -> str:
        return _run_git(*args, cwd=self.repo).stdout

    def _amends(self) -> commits._Amendment:
        return commits._amend_commit_message(
            self.repo, self.docs_commit, AMENDED_MESSAGE,
        )


class CommitMessageReadTest(_CommittedRepositoryMixin, unittest.TestCase):
    """`_commit_message` reads one commit's whole message off its object."""

    def test_reads_the_message_as_committed(self) -> None:
        # The headers are dropped and the subject and body come back byte for
        # byte, since the caller rewrites the subject and commits the rest
        # again.
        self.assertEqual(
            commits._commit_message(self.repo, self.docs_commit),
            COMMITTED_MESSAGE,
        )

    def test_an_unreadable_revision_answers_none(self) -> None:
        # A read that did not happen is not an empty message: taken for one,
        # the caller would amend a subject nobody wrote.
        self.assertIsNone(commits._commit_message(self.repo, MISSING_COMMIT))


class ByteExactMessageTest(_CommittedRepositoryMixin, unittest.TestCase):
    """A message is read and rebuilt as the bytes git stored."""

    def test_non_lf_bytes_survive_the_replacement(self) -> None:
        # Newline translation or a lossy decode anywhere on the path would
        # hand the replacement a body nobody wrote, so a message that only
        # survives byte for byte is committed, read, and rebuilt: the read
        # gives back its bytes, and the replacement differs from it in the
        # subject text alone.
        raw_message = RAW_SUBJECT.encode() + RAW_BODY
        commit = self._commits_raw(raw_message)
        read = commits._commit_message(self.repo, commit)

        amended = commits._amend_commit_message(
            self.repo,
            commit,
            read.replace(RAW_SUBJECT, RAW_REFERENCED_SUBJECT, 1),
        )

        self.assertEqual(read.encode(MESSAGE_ENCODING, LOSSLESS), raw_message)
        self.assertEqual(
            self._raw_message(amended.sha),
            RAW_REFERENCED_SUBJECT.encode() + RAW_BODY,
        )

    def _commits_raw(self, message: bytes) -> str:
        """Commit `message` exactly as these bytes, and return the new HEAD."""
        message_file = self.repo.parent / "message.bin"
        message_file.write_bytes(message)
        self._git(GIT_COMMIT, "--allow-empty", VERBATIM, "-F", str(message_file))
        return self._head()

    def _raw_message(self, commit: str) -> bytes:
        """The bytes `commit`'s message was stored as, read without decoding."""
        stored = subprocess.run(
            ["git", "cat-file", COMMIT_OBJECT, commit],
            cwd=str(self.repo),
            capture_output=True,
            env=_git_env(),
            check=True,
        )
        return stored.stdout.partition(b"\n\n")[2]


class AmendedMessageTest(_CommittedRepositoryMixin, unittest.TestCase):
    """`_amend_commit_message` replaces a commit's message and nothing else."""

    def setUp(self) -> None:
        super().setUp()
        self.enterContext(
            patch.object(config, "AGENT_GIT_NAME", ORCHESTRATOR_NAME),
        )
        self.enterContext(
            patch.object(config, "AGENT_GIT_EMAIL", ORCHESTRATOR_EMAIL),
        )

    def test_keeps_author_tree_and_staged_work(self) -> None:
        # The commit a documenting pass publishes is the developer's, so its
        # replacement differs in message and committer alone: author, author
        # date, tree, and parents stay the commit's own, staged work stays out
        # of it and stays staged, and a body line a repository-local cleanup
        # would strip goes back as written.
        kept = self._git(GIT_LOG, LAST_COMMIT, KEPT_FIELDS_FORMAT)
        (self.repo / STAGED_PATH).write_text("staged\n")
        self._git(GIT_ADD, STAGED_PATH)
        self._git(GIT_CONFIG, "commit.cleanup", "strip")

        amended = self._amends()

        self.assertEqual(self._head(), amended.sha)
        self.assertEqual(self._git(GIT_LOG, LAST_COMMIT, KEPT_FIELDS_FORMAT), kept)
        self.assertEqual(
            commits._commit_message(self.repo, HEAD_REVISION), AMENDED_MESSAGE,
        )
        self.assertEqual(
            self._git(GIT_LOG, LAST_COMMIT, COMMITTER_FORMAT).strip(),
            f"{ORCHESTRATOR_NAME} <{ORCHESTRATOR_EMAIL}>",
        )
        self.assertEqual(
            self._git("diff", "--cached", "--name-only").strip(), STAGED_PATH,
        )

    def test_planted_hooks_and_signing_never_run(self) -> None:
        # The checkout is one an agent can write the config of. A commit-msg
        # hook and a reference-transaction hook that refuse, and signing forced
        # through a program that fails, stop the plain commit and the plain ref
        # move -- proved first, so the replacement landing is not vacuous --
        # and none of them may run for the orchestrator's own.
        self._rig_the_checkout()
        self._assert_plain_git_refuses(
            GIT_COMMIT, "--amend", MESSAGE_FLAG, AMENDED_MESSAGE,
        )
        self._assert_plain_git_refuses(UPDATE_REF, HEAD_REVISION, self.base)

        amended = self._amends()

        self.assertEqual(self._head(), amended.sha)

    def _rig_the_checkout(self) -> None:
        for hook_name in REFUSING_HOOKS:
            hook = self.repo / ".git" / "hooks" / hook_name
            hook.parent.mkdir(parents=True, exist_ok=True)
            hook.write_text("#!/bin/sh\nexit 1\n")
            hook.chmod(EXECUTABLE_MODE)
        self._git(GIT_CONFIG, "commit.gpgsign", "true")
        self._git(GIT_CONFIG, "gpg.program", "false")

    def _assert_plain_git_refuses(self, *git_args: str) -> None:
        plain = subprocess.run(
            ["git", *git_args],
            cwd=str(self.repo),
            capture_output=True,
            env=_git_env(),
            check=False,
        )
        self.assertNotEqual(plain.returncode, 0)


class BoundAmendmentTest(_CommittedRepositoryMixin, unittest.TestCase):
    """A replacement lands only over the commit it replaces."""

    def test_head_moved_before_it_is_refused(self) -> None:
        # Something committed on the checkout after the caller read the docs
        # commit. The newer commit is neither rewritten nor handed back as the
        # replacement, and HEAD stays where that commit put it.
        moved_to = self._interloper()

        self._assert_refused(self._amends(), moved_to)

    def test_head_moved_mid_amendment_is_refused(self) -> None:
        # The same race landing after the replacement is created and before
        # HEAD is moved onto it -- the window a proof of HEAD taken up front
        # cannot see, and one a HEAD read back afterwards would hand on.
        racing = _CommitsBeforeTheSwap(commands._git_hardened, self._interloper)
        with patch.object(commands, HARDENED_HELPER, racing):
            amended = self._amends()

        self._assert_refused(amended, racing.landed)

    def _interloper(self) -> str:
        return self._commits(INTERLOPER_PATH, INTERLOPER_MESSAGE)

    def _assert_refused(self, amended, moved_to: str) -> None:
        self.assertTrue(amended.moved, amended)
        self.assertEqual(amended.sha, "")
        self.assertEqual(self._head(), moved_to)
        self.assertEqual(
            commits._commit_message(self.repo, HEAD_REVISION), INTERLOPER_MESSAGE,
        )


if __name__ == "__main__":
    unittest.main()
