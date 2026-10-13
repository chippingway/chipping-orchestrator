# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Which launch mode a run is, and how loud, as the `run` command line names them."""

from __future__ import annotations

import argparse
import contextlib
import io
import unittest

from orchestrator.runtime import options as _options
from tests.runtime import polling_test_support as _support

_LEVEL_FLAG = "--log-level"
_DEBUG_LEVEL = "DEBUG"
_DEFAULT_LEVEL = "INFO"
_PROG = "chipping-orchestrator"
_USAGE_ERROR = 2
_ONCE_FLAG = _support.ONCE_ARGS[0]
_CLEANUP_FLAG = "--cleanup-terminal-artifacts"


def _run_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog=f"{_PROG} {_options.COMMAND}")
    _options.add_arguments(parser)
    return parser


def _command_parser() -> argparse.ArgumentParser:
    """A parser the commands would be chosen from, refusing every `run` flag."""
    parser = argparse.ArgumentParser(prog=_PROG)
    _options.refuse_before_command(parser)
    return parser


class OptionParsingTest(unittest.TestCase):
    """The launch mode and the log level are the whole `run` command line.

    Two modes and neither is the default: a bare `run` polls forever, and each
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
                options = _options.polling_options(_run_parser().parse_args(argv))
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
            _run_parser().parse_args([_ONCE_FLAG, _CLEANUP_FLAG])


class MisplacedRunFlagTest(unittest.TestCase):
    """A `run` flag given before any command is a usage error naming the `run`
    form that means it: the flag spelled out in full, with the value it was given.
    """

    def test_each_flag_names_its_run_form(self) -> None:
        for argv, run_form in (
            ([_ONCE_FLAG], f"{_PROG} run --once"),
            ([_CLEANUP_FLAG], f"{_PROG} run {_CLEANUP_FLAG}"),
            ([_LEVEL_FLAG, _DEBUG_LEVEL], f"{_PROG} run {_LEVEL_FLAG} {_DEBUG_LEVEL}"),
            ([f"{_LEVEL_FLAG}={_DEBUG_LEVEL}"], f"{_PROG} run {_LEVEL_FLAG} {_DEBUG_LEVEL}"),
            (["--clean"], f"{_PROG} run {_CLEANUP_FLAG}"),
        ):
            with self.subTest(argv=argv):
                stderr = self._refusal(argv)

                self.assertTrue(
                    stderr.endswith(f"is accepted only after the run command: {run_form}\n"),
                    stderr,
                )

    def test_the_refusal_is_in_no_help_listing(self) -> None:
        # Hidden both ways: the help above the commands lists the commands,
        # and a launch that gives no flag there carries no attribute that
        # could shadow the one the `run` parser sets.
        parser = _command_parser()

        help_text = parser.format_help()
        for flag in (_ONCE_FLAG, _CLEANUP_FLAG, _LEVEL_FLAG):
            with self.subTest(flag=flag):
                self.assertNotIn(flag, help_text)
        self.assertEqual(parser.parse_args([]), argparse.Namespace())

    def _refusal(self, argv: list[str]) -> str:
        """What a usage error refusing `argv` above the commands printed."""
        stderr = io.StringIO()
        stopped = self.assertRaises(SystemExit)
        with contextlib.redirect_stderr(stderr), stopped:
            _command_parser().parse_args(argv)
        self.assertEqual(stopped.exception.code, _USAGE_ERROR)
        return stderr.getvalue()


if __name__ == "__main__":
    unittest.main()
