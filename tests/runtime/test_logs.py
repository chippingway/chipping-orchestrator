# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Where the polling process writes, and what it does when the file will not."""

from __future__ import annotations

import logging
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from orchestrator import config
from orchestrator.runtime import logs

_LOG_DIR_ATTR = "LOG_DIR"
_HANDLER_ATTR = "rotating_file_handler"
_LOG_FILE_NAME = "orchestrator.log"
_UNWRITABLE = "read-only file system"
_LOG_CHANNEL = "orchestrator"
_LEVEL = "INFO"


class RotatingFileHandlerTest(unittest.TestCase):
    """The log directory is created on the way to the handler, so a fresh
    deployment logs to a file without an operator making one first.
    """

    def test_handler_writes_under_the_log_directory(self) -> None:
        with tempfile.TemporaryDirectory() as log_root:
            log_dir = Path(log_root) / "logs"
            with patch.object(config, _LOG_DIR_ATTR, log_dir):
                file_handler = logs.rotating_file_handler()

            self.addCleanup(file_handler.close)
            self.assertEqual(
                Path(file_handler.baseFilename),
                log_dir / _LOG_FILE_NAME,
            )


class LoggingFallbackTest(unittest.TestCase):
    """An unwritable log directory costs the file half and nothing else: the
    process still polls, and the warning says which directory failed.
    """

    def test_unwritable_directory_keeps_stderr(self) -> None:
        with (
            patch.object(
                logs,
                _HANDLER_ATTR,
                side_effect=OSError(_UNWRITABLE),
            ),
            patch.object(logging, "basicConfig") as configured,
            self.assertLogs(_LOG_CHANNEL, level=logging.WARNING) as captured,
        ):
            logs.configure_logging(_LEVEL)
            installed = configured.call_args.kwargs["handlers"]
            warned = captured.output

        self.assertEqual(
            [type(destination) for destination in installed],
            [logging.StreamHandler],
        )
        self.assertIn(_UNWRITABLE, warned[0])


if __name__ == "__main__":
    unittest.main()
