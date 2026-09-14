# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Where the polling process writes its log lines.

Both destinations are settled before the first client is built, so a failure
during startup still reaches the operator's file. The file half is best effort:
an unwritable `LOG_DIR` is worth a warning on stderr, never a process that
refuses to poll.
"""
from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler

from orchestrator import config

log = logging.getLogger("orchestrator")

_LOG_FORMAT = "%(asctime)s %(levelname)s %(name)s: %(message)s"
_LOG_FILE_NAME = "orchestrator.log"
_MAX_LOG_BYTES = 10 * 1024 * 1024
_LOG_BACKUP_COUNT = 5


def rotating_file_handler() -> logging.Handler:
    """Build the rotating file handler after creating the log directory."""
    config.LOG_DIR.mkdir(parents=True, exist_ok=True)
    return RotatingFileHandler(
        config.LOG_DIR / _LOG_FILE_NAME,
        maxBytes=_MAX_LOG_BYTES,
        backupCount=_LOG_BACKUP_COUNT,
        encoding="utf-8",
    )


def configure_logging(level: str) -> None:
    """Configure stderr plus best-effort rotating file logging."""
    log_handlers: list[logging.Handler] = [logging.StreamHandler()]
    try:
        log_handlers.append(rotating_file_handler())
    except OSError as error:
        logging.basicConfig(
            level=level,
            format=_LOG_FORMAT,
            handlers=log_handlers,
        )
        log.warning(
            "file logging disabled: %s (%s)",
            config.LOG_DIR,
            error,
        )
        return
    logging.basicConfig(
        level=level,
        format=_LOG_FORMAT,
        handlers=log_handlers,
    )
