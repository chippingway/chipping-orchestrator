# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The namespace listing an artifact this host holds no copy of is found by.

What a real remote would answer is exercised against real bare repositories
beside the artifact discovery that spends this. What is asserted here is the
channel a refusal reports on, the envelope the listing carries, and the two
readings a caller must never collapse -- a remote holding nothing under the
pattern, and a remote nobody could ask.
"""

from __future__ import annotations

import contextlib
import unittest
from unittest.mock import MagicMock, patch

from orchestrator import config
from orchestrator.git import ref_discovery
from tests.git.token_transport_test_support import (
    FAKE_TOKEN,
    SECRET_TOKEN,
    SUBPROCESS_RUN,
    TOKEN_RESOLVER,
    WORKTREE,
    _assert_hardened_fetch,
    _spec,
)
from tests.git.transport_helpers import _GitRunRecorder

OBJECT_ID_LENGTH = 40

SHA = "a" * OBJECT_ID_LENGTH

OTHER_SHA = "b" * OBJECT_ID_LENGTH

PROXY_HIT = "http.proxy http://evil.example:8080\n"

PLUMBING_LOG = "orchestrator.git_plumbing"

ERROR = "ERROR"

# The status git answers a call it could not make at all with.
GIT_FATAL = 128

PATTERN = "refs/heads/orchestrator/*"

REF = "refs/heads/orchestrator/acme-widgets/issue-41"

OTHER_REF = "refs/heads/orchestrator/acme-widgets/issue-42"

# Two refs as `ls-remote` reports them, with a line carrying no refname at
# all beside them: a name that never arrives is an artifact nobody acts on,
# while refusing the listing over it would lose the two that did.
LISTED_REFS = f"{SHA}\t{REF}\n{OTHER_SHA}\t{OTHER_REF}\n{SHA}\n"


def _clean_probe() -> MagicMock:
    """A transport-config probe reporting nothing hijackable."""
    return MagicMock(returncode=1, stdout="", stderr="")


@contextlib.contextmanager
def _token_bearing(run_recorder, token: str = FAKE_TOKEN):
    """Run a listing case with the recorder in place and a token resolved."""
    with (
        patch(SUBPROCESS_RUN, side_effect=run_recorder),
        patch.object(config, TOKEN_RESOLVER, return_value=token),
    ):
        yield


class RefusalChannelTest(unittest.TestCase):
    """Refusals reach the channel operators already watch.

    Operators filter on the rendered `orchestrator.git_plumbing` prefix and
    attach handlers to that logger, so a listing this owner could not take has
    to render under that name rather than a package-derived one.
    """

    def test_logger_keeps_its_operator_facing_name(self) -> None:
        self.assertEqual(ref_discovery.log.name, PLUMBING_LOG)


class RefListingTest(unittest.TestCase):
    """What a remote carries under one pattern, and the failure that is not it."""

    def test_a_listing_answers_the_refnames_found(self) -> None:
        run_recorder = _GitRunRecorder(
            probe_result=_clean_probe(),
            command_result=MagicMock(
                returncode=0, stdout=LISTED_REFS, stderr="",
            ),
        )

        with _token_bearing(run_recorder):
            listed = ref_discovery._remote_ref_names(
                _spec(), WORKTREE, pattern=PATTERN,
            )

        self.assertEqual(listed, (REF, OTHER_REF))
        self.assertIn(PATTERN, run_recorder.args)
        self.assertIn("--refs", run_recorder.args)
        _assert_hardened_fetch(self, run_recorder, FAKE_TOKEN)

    def test_a_failed_listing_is_not_an_empty_remote(self) -> None:
        # The one reading a caller must not spend as "nothing is published
        # here": it is what says a repository still has artifacts out there.
        run_recorder = _GitRunRecorder(
            probe_result=_clean_probe(),
            command_result=MagicMock(
                returncode=GIT_FATAL,
                stdout="",
                stderr=f"denied for {SECRET_TOKEN}\n",
            ),
        )

        with (
            _token_bearing(run_recorder, SECRET_TOKEN),
            self.assertLogs(PLUMBING_LOG, level=ERROR) as reported,
        ):
            listed = ref_discovery._remote_ref_names(
                _spec(), WORKTREE, pattern=PATTERN,
            )
            diagnostic = "\n".join(reported.output)

        self.assertIsNone(listed)
        self.assertNotIn(SECRET_TOKEN, diagnostic)

    def test_a_missing_token_lists_nothing(self) -> None:
        run_recorder = _GitRunRecorder(probe_result=_clean_probe())

        with (
            _token_bearing(run_recorder, ""),
            self.assertLogs(PLUMBING_LOG, level=ERROR),
        ):
            listed = ref_discovery._remote_ref_names(
                _spec(), WORKTREE, pattern=PATTERN,
            )

        self.assertIsNone(listed)
        self.assertIsNone(run_recorder.args)

    def test_a_hijackable_local_config_lists_nothing(self) -> None:
        # A local `http.proxy` would tunnel the token-bearing listing through
        # an attacker's proxy, and a `-c` override on the command line does not
        # beat a URL-scoped variant of it.
        run_recorder = _GitRunRecorder(
            probe_result=MagicMock(returncode=0, stdout=PROXY_HIT, stderr=""),
        )

        with (
            _token_bearing(run_recorder),
            self.assertLogs(PLUMBING_LOG, level=ERROR),
        ):
            listed = ref_discovery._remote_ref_names(
                _spec(), WORKTREE, pattern=PATTERN,
            )

        self.assertIsNone(listed)
        self.assertIsNone(run_recorder.args)


if __name__ == "__main__":
    unittest.main()
