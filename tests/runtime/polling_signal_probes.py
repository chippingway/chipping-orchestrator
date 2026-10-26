# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Signal and shutdown probes for polling-runtime tests.

Each probe is handed the `RuntimeState` the run under test is driving, so it
raises the same shutdown the installed handler would without delivering a real
signal into the test process.
"""

from __future__ import annotations

import signal
import threading
from contextlib import contextmanager
from unittest.mock import patch

from orchestrator.runtime import shutdown
from orchestrator.scheduler.models import SubmissionRequest

_ALPHA_REPO = "alpha/one"
_WORKER_WAIT_SECONDS = 5.0


def unexpected_dispatch() -> None:
    raise AssertionError("post-signal submit must not dispatch")


@contextmanager
def isolated_shutdown():
    """Keep a raised shutdown inside the test that raised it.

    Two of its steps are process-wide: the watchdog hard-exits when the drain
    it waits on does not complete inside the grace -- and a test that raises a
    shutdown without driving a run to its drain never completes one -- and the
    kernel-default re-arm would leave the test process without the handler
    pytest installed. Both are intercepted; the armed watchdog is handed back
    so a caller can assert on it.
    """
    with (
        patch.object(shutdown, "arm_shutdown_watchdog") as armed,
        patch.object(signal, "signal"),
    ):
        yield armed


class SignalSubmitTick:
    def __init__(self, state) -> None:
        self._state = state
        self.submit_results: list[bool] = []

    def __call__(self, gh, spec, *, scheduler=None) -> None:
        self.submit_results.append(
            scheduler.submit(SubmissionRequest(spec.slug, 1, lambda: None)),
        )
        shutdown.request_shutdown(self._state, signal.SIGINT, None)
        self.submit_results.append(
            scheduler.submit(SubmissionRequest(spec.slug, 2, unexpected_dispatch)),
        )


class MultiRepoSignalTick:
    def __init__(self, state) -> None:
        self._state = state
        self._both_inside = threading.Barrier(2, timeout=_WORKER_WAIT_SECONDS)
        self._signal_fired = threading.Event()
        self._lock = threading.Lock()
        self.beta_results: list[bool] = []

    def __call__(self, gh, spec, *, scheduler=None) -> None:
        self._both_inside.wait()
        if spec.slug == _ALPHA_REPO:
            shutdown.request_shutdown(self._state, signal.SIGINT, None)
            self._signal_fired.set()
            return
        signal_seen = self._signal_fired.wait(timeout=_WORKER_WAIT_SECONDS)
        if signal_seen:
            accepted = scheduler.submit(SubmissionRequest(spec.slug, 7, unexpected_dispatch))
            with self._lock:
                self.beta_results.append(accepted)
            return
        raise AssertionError("signal did not fire within timeout")


class FirstTickShutdown:
    def __init__(self, state, signum: int) -> None:
        self._state = state
        self._signum = signum
        self._shutdown_done = threading.Event()

    def __call__(self, gh, spec, *, scheduler=None) -> None:
        if self._shutdown_done.is_set():
            return
        self._shutdown_done.set()
        shutdown.request_shutdown(self._state, self._signum, None)


class WaitRecorder:
    def __init__(self) -> None:
        self.timeout: float | None = None

    def __call__(self, timeout=None) -> bool:
        self.timeout = timeout
        return True
