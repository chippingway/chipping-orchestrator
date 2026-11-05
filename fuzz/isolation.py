# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What a fuzz target reaches while it starts and runs: its parser, and nothing else.

A target starts only on the interpreters this project supports, 3.12 and
newer, wherever it runs: from a checkout or packaged in the fuzzing image.

The pinned-state owner is imported through the `orchestrator.github`
initializer, whose client imports `orchestrator.config`, and that package's
initializer resolves every setting on import: it reads a `.env` unless
`ORCHESTRATOR_SKIP_DOTENV` says not to, asks git whether each configured target
is a checkout, and reads every target's token file. None of that is a parser's
input, and the skip variable stops only the first. So the settings package is
registered before anything imports it, from its own spec and with its initializer
never run: its leaves, `config.models` among them, import from its own directory
as they always do, and it binds no setting at all, so an import that came to
read one fails loudly instead of resolving it. Every other module, the GitHub
package initializer and its client included, is imported as it is.

Running, a target is sealed: while one input is parsed, an audit hook refuses
every file open, directory listing, process, and connection, so a parser that
came to reach for one fails the input instead of doing it quietly under the
fuzzer. The one open it lets through is a read of Python source, which is code
rather than state: a coverage tracer reads the source of a module the first
time one of its branches runs, and a traceback the lines it quotes. The hook is
installed once and stays, which is why only an entry script seals: in any
other process it would refuse that process's own work.
"""
from __future__ import annotations

import logging
import sys
from collections.abc import Callable
from importlib import util as _import_util

_SETTINGS_PACKAGE = "orchestrator.config"
_READ_MODES = frozenset(("r", "rb"))
_PYTHON_FLOOR = (3, 12)

# The audit events a parser has no reason to raise: a file opened or a
# directory listed, a process started or replaced, and a connection made or a
# name resolved on the way to one.
_FORBIDDEN_EVENTS = frozenset((
    "open",
    "os.listdir",
    "os.scandir",
    "os.system",
    "os.exec",
    "os.fork",
    "os.forkpty",
    "os.posix_spawn",
    "os.spawn",
    "subprocess.Popen",
    "socket.connect",
    "socket.getaddrinfo",
    "socket.gethostbyname",
    "sqlite3.connect",
    "urllib.Request",
))


class SideEffectError(RuntimeError):
    """A parser under fuzzing reached outside the input it was handed."""


class Sealed:
    """A fuzz target that runs each input under the audit hook it installs."""

    def __init__(self, target: Callable[[bytes], None]) -> None:
        self._target = target
        self._parsing = False
        sys.addaudithook(self._audit)

    def __call__(self, fuzz_input: bytes) -> None:
        """Run the target on one input, refusing every side effect until it returns."""
        self._parsing = True
        # Lifted however the target leaves, so it seals the parsing alone and
        # nothing the fuzzer does around a failure.
        try:
            self._target(fuzz_input)
        except Exception:
            self._parsing = False
            raise
        self._parsing = False

    def _audit(self, event: str, arguments: tuple) -> None:
        if self._parsing and event in _FORBIDDEN_EVENTS and not self._reads_code(event, arguments):
            raise SideEffectError(event, arguments)

    def _reads_code(self, event: str, arguments: tuple) -> bool:
        """Whether the event opens a Python source file for reading, and nothing more."""
        if event != "open":
            return False
        path, mode = arguments[0], arguments[1]
        return isinstance(path, str) and path.endswith(".py") and mode in _READ_MODES


def isolate() -> None:
    """Ready this process for a target, ahead of every import of the settings package.

    Refusals are logged at warning level, once for every input the fuzzer
    hands a reader that refuses it, so the package's loggers are given a
    handler that discards them rather than one that buries the fuzzer's own
    report under them on stderr.
    """
    if sys.version_info < _PYTHON_FLOOR:
        raise RuntimeError(f"the fuzz targets need Python 3.12 or newer, not {sys.version}")
    if _SETTINGS_PACKAGE in sys.modules:
        raise RuntimeError(f"{_SETTINGS_PACKAGE} was imported before the fuzz target could isolate it")
    spec = _import_util.find_spec(_SETTINGS_PACKAGE)
    if spec is None:
        raise RuntimeError(f"{_SETTINGS_PACKAGE} is not importable here")
    settings = _import_util.module_from_spec(spec)
    sys.modules[_SETTINGS_PACKAGE] = settings
    sys.modules["orchestrator"].config = settings
    logging.getLogger("orchestrator").addHandler(logging.NullHandler())
