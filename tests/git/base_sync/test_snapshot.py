# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Recovery reads and their fail-closed exits on the `snapshot` owner."""

from __future__ import annotations

import json
import unittest
from unittest.mock import MagicMock, patch

from orchestrator.git import branch_transport, commands
from orchestrator.git.base_sync import persistence, snapshot
from orchestrator.git.publication import probes as publication_probes
from orchestrator.git.verification import probes as verification_probes
from tests.git.base_sync import base_sync_helpers as fixtures
from tests.git.base_sync.sync_test_support import _diverged

AUTHED_FETCH = "_authed_fetch"

DIVERGENCE = "_branch_divergence"

HEAD_SHA = "_head_sha"

RESET_HELPER = "_reset_clear_and_park"

REMOTE_REF = f"refs/remotes/origin/{fixtures.BRANCH}"

EXPECTED_REFSPEC = f"+refs/heads/{fixtures.BRANCH}:{REMOTE_REF}"

ABORT_DETAIL = "the remote head could not be read."

FETCH_ERROR = "fatal: could not read Username for 'https://github.com'"

REV_PARSE = "rev-parse"


class AbortRecoveryUnverifiedTest(unittest.TestCase):
    """An unverifiable recovery goes back to the anchor and parks."""

    def test_abort_resets_onto_the_anchor(self) -> None:
        context = fixtures._recovery_context()
        reset = MagicMock()

        with patch.object(persistence, RESET_HELPER, reset):
            aborted = snapshot._abort_recovery_unverified(
                context, ABORT_DETAIL,
            )

        # The abort owns the tick: the caller stops rather than falling
        # through to a rebase against an unverified head.
        self.assertTrue(aborted)
        self.assertEqual(
            reset.call_args.args, (context, fixtures.PRE_REBASE_SHA),
        )
        self.assertEqual(
            reset.call_args.kwargs.get("reason"), fixtures.PARK_PUSH_FAILED,
        )
        message = reset.call_args.kwargs.get("message")
        # Why it parks only: what the reset came to is the tail's to say.
        self.assertIn(ABORT_DETAIL, message)
        self.assertNotIn("has been reset", message)
        self.assertIn(f"#{fixtures.PR_NUMBER}", message)


# The anchor an out-of-band edit repoints the attempt to.
MOVED_ANCHOR = "0dd0a5c4" * 5

# The two clears, beside whether a landed one lets the tick's rebase go on.
CLEARS = (
    ("an ineligible label", snapshot._clear_ineligible_recovery, False),
    ("an unmoved head", snapshot._clear_unchanged_recovery, True),
)

# How a clear's write can fail to land, beside the anchor the comment then
# carries: refused before anything landed and landed with its answer lost, as
# the client names each, and over an anchor the comment came to spell otherwise
# without the recovery, which is kept as it stands.
UNLANDED = (
    ("refused", "refused", fixtures.PRE_REBASE_SHA),
    ("landed, its answer lost", "lost", None),
    ("the attempt moved", MOVED_ANCHOR, MOVED_ANCHOR),
)


def _breaks(context, how: str) -> None:
    """Fail `context`'s next pinned-comment edit as the client names `how`, or repoint the comment's anchor to it.

    The anchor is repointed after the tick read the comment, by no write of
    the recovery's.
    """
    if how in {"refused", "lost"}:
        getattr(context.gh.pinned_failures, how).add(fixtures.ISSUE)
        return
    moved = context.gh.read_pinned_state(context.issue)
    moved.set(fixtures.KEY_PENDING_PUSH_SHA, how)
    context.gh.write_pinned_state(context.issue, moved)


class ClearRecoveryAnchorTest(unittest.TestCase):
    """Both no-op exits drop the anchor in a write of their own, and only a landed one lets the rebase go on."""

    def test_a_landed_clear_drops_the_anchor(self) -> None:
        # An operator relabelled away from the refresh-driven stages, so no
        # rebase runs this tick; HEAD never left the anchor, so the caller
        # continues into the normal rebase flow on the same tick -- with the
        # tick's state reading as the comment the clear landed on.
        for exit_, clear, goes_on in CLEARS:
            with self.subTest(exit=exit_):
                context = self._context()

                self.assertIs(clear(context), not goes_on)

                published = context.gh.pinned_data(fixtures.ISSUE)
                self.assertIsNone(published.get(fixtures.KEY_PENDING_PUSH_SHA))
                self.assertEqual(json.loads(context.state.synced), published)
                self.assertEqual(context.gh.write_state_calls, 1)

    def test_an_unlanded_clear_holds_the_tick(self) -> None:
        # A clear that was refused, whose answer was lost, or that met an
        # attempt moved without the recovery owns the tick, so no rebase
        # pins and pushes behind it. The tick's state keeps the attempt and
        # is withheld from any whole-state write; the comment keeps whatever
        # it carries, for the next tick to read.
        for exit_, clear, _goes_on in CLEARS:
            with self.subTest(exit=exit_):
                self._holds(clear)

    def _holds(self, clear) -> None:
        """Ask `clear` over each way its write fails to land, and read back what it held."""
        for unlanded, breaks, anchored in UNLANDED:
            with self.subTest(unlanded=unlanded):
                context = self._context(breaks)

                with self.assertLogs("orchestrator.base_sync", "WARNING"):
                    self.assertTrue(clear(context))

                standing = context.gh.pinned_data(fixtures.ISSUE).get(fixtures.KEY_PENDING_PUSH_SHA)
                self.assertEqual(standing, anchored)
                self.assertEqual(context.state.get(fixtures.KEY_PENDING_PUSH_SHA), fixtures.PRE_REBASE_SHA)
                self.assertTrue(context.state.withheld)

    def _context(self, breaks: str | None = None):
        """A recovery context over an attempt that pinned its anchor and nothing else, `breaks` done to it."""
        context = fixtures._recovery_context(
            pending_auto_base_rebase_push_sha=fixtures.PRE_REBASE_SHA,
        )
        if breaks is not None:
            _breaks(context, breaks)
        return context


class FetchRecoverySnapshotTest(unittest.TestCase):
    """The branch fetch is what makes the remote comparison trustworthy."""

    def test_fetch_updates_the_remote_tracking_ref(self) -> None:
        context = fixtures._recovery_context()
        fetch = MagicMock(return_value=fixtures._git_result())

        with patch.object(branch_transport, AUTHED_FETCH, fetch), patch.object(
            verification_probes,
            HEAD_SHA,
            MagicMock(return_value=fixtures.RECOVERED_SHA),
        ):
            fetched = snapshot._fetch_recovery_snapshot(context)

        # The explicit refspec is what makes a single-branch clone update
        # `refs/remotes/...` instead of leaving the payload in FETCH_HEAD,
        # which is the ref the comparison then reads.
        self.assertEqual(fetch.call_args.args[1], EXPECTED_REFSPEC)
        self.assertEqual(
            fetch.call_args.kwargs.get("cwd"), fixtures.WORKTREE,
        )
        self.assertEqual(fetched.branch, fixtures.BRANCH)
        self.assertEqual(fetched.local_head, fixtures.RECOVERED_SHA)

    def test_failed_fetch_parks_with_the_git_error(self) -> None:
        context = fixtures._recovery_context()
        failed = MagicMock(
            return_value=fixtures._git_result(
                returncode=fixtures.GIT_FAILURE_EXIT_CODE,
                stderr=f"{FETCH_ERROR}\n",
            ),
        )
        abort = MagicMock(return_value=True)

        with (
            patch.object(branch_transport, AUTHED_FETCH, failed),
            patch.object(snapshot, "_abort_recovery_unverified", abort),
        ):
            fetched = snapshot._fetch_recovery_snapshot(context)

        # Without the fetch there is no remote head to compare against, so
        # the recovery aborts rather than trusting a stale tracking ref.
        self.assertIsNone(fetched)
        detail = abort.call_args.args[1]
        self.assertIn(f"origin/{fixtures.BRANCH}", detail)
        self.assertIn(FETCH_ERROR, detail)


class ReadRemoteRecoveryHeadTest(unittest.TestCase):
    """A remote head that cannot be read is never guessed at."""

    def test_read_returns_the_fetched_sha(self) -> None:
        hardened = MagicMock(
            return_value=fixtures._git_result(
                stdout=f"{fixtures.REMOTE_SHA}\n",
            ),
        )

        with patch.object(commands, fixtures.GIT_HARDENED, hardened):
            remote_head = snapshot._read_remote_recovery_head(
                fixtures._recovery_context(), fixtures.BRANCH,
            )

        self.assertEqual(remote_head, fixtures.REMOTE_SHA)
        self.assertEqual(hardened.call_args.args, (REV_PARSE, REMOTE_REF))

    def test_unreadable_head_aborts(self) -> None:
        for unreadable in (
            fixtures._git_result(
                returncode=fixtures.GIT_FAILURE_EXIT_CODE,
                stderr="fatal: bad revision\n",
            ),
            fixtures._git_result(stdout="\n"),
        ):
            with self.subTest(returncode=unreadable.returncode):
                self._assert_aborts(unreadable)

    def _assert_aborts(self, unreadable) -> None:
        abort = MagicMock(return_value=True)

        with patch.object(
            commands, fixtures.GIT_HARDENED, MagicMock(return_value=unreadable),
        ), patch.object(snapshot, "_abort_recovery_unverified", abort):
            remote_head = snapshot._read_remote_recovery_head(
                fixtures._recovery_context(), fixtures.BRANCH,
            )

        self.assertIsNone(remote_head)
        self.assertIn(REMOTE_REF, abort.call_args.args[1])


class CompleteRecoverySnapshotTest(unittest.TestCase):
    """Divergence counts are only read once the heads are known to differ."""

    def test_matching_heads_skip_the_divergence_probe(self) -> None:
        ahead_behind = MagicMock()

        completed = self._complete(
            fixtures.RECOVERED_SHA, ahead_behind=ahead_behind,
        )

        # Equal heads already answer the question the counts would, and the
        # probe costs two more git invocations against the worktree.
        ahead_behind.assert_not_called()
        self.assertEqual(completed.remote_head, fixtures.RECOVERED_SHA)
        self.assertEqual((completed.ahead, completed.behind), (0, 0))

    def test_differing_heads_carry_the_counts(self) -> None:
        completed = self._complete(
            fixtures.REMOTE_SHA,
            ahead_behind=MagicMock(return_value=_diverged(1, 2)),
        )

        self.assertEqual(completed.remote_head, fixtures.REMOTE_SHA)
        self.assertEqual((completed.ahead, completed.behind), (1, 2))
        self.assertEqual(completed.branch, fixtures.BRANCH)

    def test_unreadable_remote_completes_nothing(self) -> None:
        with patch.object(
            snapshot,
            "_read_remote_recovery_head",
            MagicMock(return_value=None),
        ):
            completed = snapshot._complete_recovery_snapshot(
                fixtures._recovery_context(),
                fixtures._snapshot(remote_head=""),
            )

        self.assertIsNone(completed)

    def _complete(self, remote_head: str, *, ahead_behind: MagicMock):
        with patch.object(
            snapshot,
            "_read_remote_recovery_head",
            MagicMock(return_value=remote_head),
        ), patch.object(
            publication_probes, DIVERGENCE, ahead_behind,
        ):
            return snapshot._complete_recovery_snapshot(
                fixtures._recovery_context(),
                fixtures._snapshot(
                    local_head=fixtures.RECOVERED_SHA, remote_head="",
                ),
            )


if __name__ == "__main__":
    unittest.main()
