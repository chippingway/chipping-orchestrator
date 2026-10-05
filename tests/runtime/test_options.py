# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Which launch mode a run is, and how loud, as the command line names them."""

from __future__ import annotations

import contextlib
import io
import sys
import unittest
from unittest.mock import patch

from orchestrator.runtime import options as _options
from tests.runtime import polling_test_support as _support

_LEVEL_FLAG = "--log-level"
_DEBUG_LEVEL = "DEBUG"
_DEFAULT_LEVEL = "INFO"
_PROCESS_ARGV = ("chipping-orchestrator",)
_ONCE_FLAG = _support.ONCE_ARGS[0]
_CLEANUP_FLAG = "--cleanup-terminal-artifacts"


class OptionParsingTest(unittest.TestCase):
    """The launch mode and the log level are the whole command line, and an
    absent `argv` is the process's own.

    Two modes and neither is the default: a bare launch polls forever, and each
    flag is a run that ends on its own -- one tick, or one artifact
    reclamation.
    """

    def test_flags_and_defaults(self) -> None:
        for argv, expected in (
            ([], (False, False, _DEFAULT_LEVEL)),
            ([_ONCE_FLAG], (True, False, _DEFAULT_LEVEL)),
            ([_CLEANUP_FLAG], (False, True, _DEFAULT_LEVEL)),
            ([_LEVEL_FLAG, _DEBUG_LEVEL], (False, False, _DEBUG_LEVEL)),
            (
                [_ONCE_FLAG, _LEVEL_FLAG, _DEBUG_LEVEL],
                (True, False, _DEBUG_LEVEL),
            ),
        ):
            with self.subTest(argv=argv):
                options = _options.parse_options(argv)
                self.assertEqual(
                    (
                        options.once,
                        options.cleanup_terminal_artifacts,
                        options.log_level,
                    ),
                    expected,
                )

    def test_the_two_modes_are_exclusive(self) -> None:
        # Each flag names a whole run that ends on its own, so a command line
        # asking for both is refused rather than silently resolved to one.
        with (
            contextlib.redirect_stderr(io.StringIO()),
            self.assertRaises(SystemExit),
        ):
            _options.parse_options([_ONCE_FLAG, _CLEANUP_FLAG])

    def test_absent_argv_reads_the_process_argv(self) -> None:
        with patch.object(sys, "argv", [*_PROCESS_ARGV, *_support.ONCE_ARGS]):
            options = _options.parse_options(None)

        self.assertTrue(options.once)


if __name__ == "__main__":
    unittest.main()
