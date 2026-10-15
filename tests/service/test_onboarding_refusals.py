# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What stops an onboarding inside `init`, each exiting 1 and installing nothing.

Stopped or declined before its last answer, it leaves the home as empty as it
found it; a write that fails after that answer stops `init` there.
"""
from __future__ import annotations

from tests.service import (
    init_test_support as _init,
    onboarding_test_support as _support,
    terminal_test_support as _terminal,
)

_ABANDONED = (
    "onboarding stopped before its last question, so nothing was written; "
    "run init again to start over"
)
_DECLINED = (
    "nothing was written, as answered; run init again to start over, or "
    "write the setup without prompts with chipping-orchestrator set-token "
    "OWNER/NAME and chipping-orchestrator configure --clone PATH --authors LOGINS"
)
_UNHIDDEN = (
    "this terminal cannot hide the token as it is typed, so none was read; "
    "pipe the token in or redirect a file in instead; onboarding wrote nothing"
)
_STOPPED = (
    r"\A.*; onboarding stopped there, keeping what it wrote above -- finish the setup "
    r"with set-token, configure, and add-repo, then run init again\n\Z"
)


class StoppedTest(_support.OnboardingCase):
    """Stopped or declined before its last answer, onboarding writes nothing at all.

    No `.env`, token, unit, or directory appears in the home, and `init`
    says so, having asked systemd only whether a user manager answers.
    """

    def test_nothing_is_written_unconfirmed(self) -> None:
        through_token = (self.api, "", "", _support.API_TOKEN)
        unconfirmed = (*through_token, "", "", "", "")
        for case, answers, message in (
            ("Ctrl+C at the first question", (_terminal.INTERRUPT,), _ABANDONED),
            ("Ctrl+C at the token", (*through_token[:3], _terminal.INTERRUPT), _ABANDONED),
            ("the input ending", through_token[:2], _ABANDONED),
            ("Ctrl+C at the last question", (*unconfirmed, _terminal.INTERRUPT), _ABANDONED),
            ("a no to the last question", (*unconfirmed, "n"), _DECLINED),
            ("a terminal that would show the token", (*through_token[:3], _terminal.UNHIDDEN), _UNHIDDEN),
        ):
            with self.subTest(case):
                self.timeline.clear()

                self.assertEqual(self.refused(*answers), message)
                self.assertEqual(self.timeline, [_init.PROBE])


class FailedWriteTest(_support.OnboardingCase):
    """A write that fails once the answers are confirmed stops `init` there, installing nothing."""

    def test_an_unwritable_token_directory_stops_init(self) -> None:
        owner_directory = self.home / _support.API_TOKEN_FILE.parent.parent
        owner_directory.parent.mkdir()
        owner_directory.write_text("", encoding=_init.ENCODING)

        run = self.run_init(self.api, "", "", _support.API_TOKEN, *_support.AFTER_TOKEN)

        self.assertEqual(run.status, 1)
        self.assertRegex(run.stderr, _STOPPED)
        self.assertFalse((self.home / _support.SETTINGS_FILE).exists())
        self.assertFalse((self.home / _support.UNIT_FILE).exists())
        self.assertEqual(self.timeline, [_init.PROBE])
