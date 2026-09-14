# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""How the shutdown grace is split between the drain and the final sweep."""

from __future__ import annotations

import signal
import unittest
from unittest.mock import MagicMock, patch

from orchestrator import config
from orchestrator.runtime import shutdown
from orchestrator.runtime.state import RuntimeState
from tests.runtime import polling_signal_probes as _signal_probes, polling_test_support as _support

_GRACE_ATTR = "SHUTDOWN_GRACE_SECONDS"
_GRACES = (1, 2, 10, _support.SHUTDOWN_GRACE_SECONDS, 3600)


class ShutdownBudgetTest(unittest.TestCase):
    """`SHUTDOWN_GRACE_SECONDS` is a hard ceiling on signal-to-exit, so the
    sweep `force_exit` ends with is reserved out of the budget the watchdog
    waits on rather than added on top of it. Overrunning the ceiling is what
    earns the process a SIGKILL from systemd.
    """

    def test_drain_window_reserves_terminate_grace(self) -> None:
        # Capture the timeout the watchdog waits on to prove
        # drain_window + sweep_reserve == SHUTDOWN_GRACE_SECONDS.
        wait_recorder = _signal_probes.WaitRecorder()
        drain_event = MagicMock()
        drain_event.wait.side_effect = wait_recorder
        state = RuntimeState(shutdown_complete=drain_event)

        with patch.object(
            config,
            _GRACE_ATTR,
            _support.SHUTDOWN_GRACE_SECONDS,
        ):
            shutdown.run_shutdown_watchdog(state, signal.SIGTERM)
            reserve = shutdown.shutdown_terminate_grace()

        self.assertEqual(
            wait_recorder.timeout,
            _support.SHUTDOWN_GRACE_SECONDS - reserve,
        )
        self.assertLessEqual(
            wait_recorder.timeout + reserve,
            _support.SHUTDOWN_GRACE_SECONDS,
        )

    def test_terminate_grace_capped_and_within_budget(self) -> None:
        # The reserve is a slice of the budget, never the whole of it (which
        # would starve the drain) and never more than 5s for a large grace.
        for grace in _GRACES:
            with self.subTest(grace=grace):
                with patch.object(config, _GRACE_ATTR, grace):
                    reserve = shutdown.shutdown_terminate_grace()

                self.assertGreater(reserve, 0)
                self.assertLess(reserve, grace)
                self.assertLessEqual(reserve, _support.WORKER_WAIT_SECONDS)


if __name__ == "__main__":
    unittest.main()
