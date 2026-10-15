# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""`remove` stopping, disabling, and deleting the unit `init` installed, and keeping everything else."""
from __future__ import annotations

from orchestrator.service import removal
from orchestrator.service.systemd import Completed
from tests.service import lifecycle_test_support as _support

# What `is-failed` answers for a unit the reload unloaded.
_NOT_FAILED = Completed(4, "inactive\n", "")
_DENIED = Completed(1, "", "Access denied\n")
_UNTOUCHED = (_support.PROBE, _support.STOP, _support.DISABLE)
# Each step that keeps the unit when it fails, and the commands run up to it.
_REFUSED_STEPS = ((_support.STOP, _UNTOUCHED[:2]), (_support.DISABLE, _UNTOUCHED))
_REMOVED = (
    "Stopped and disabled chipping-orchestrator.service, deleted {0}, and had the user manager forget it\n"
    "Kept, since remove deletes nothing else: the configuration at {1}, the "
    "token files under ~/.config, the logs in its LOG_DIR, the worktrees, and "
    "linger, which loginctl disable-linger turns off\n"
)
_TIMED_OUT = "systemctl did not finish within 30 seconds"
_UNANSWERED = (
    "systemctl --user is-failed chipping-orchestrator.service answered with no "
    "state ({0}), so whether the user manager still remembers the service as "
    "failed is unknown; {1} is deleted, so finish once the manager answers: "
    "where systemctl --user is-failed chipping-orchestrator.service says failed, "
    "run systemctl --user reset-failed chipping-orchestrator.service\n"
)
_KEPT = (
    "systemctl --user {0} failed (Access denied); {1} is kept, so run "
    "chipping-orchestrator remove again once that is repaired\n"
)


class RemoveTest(_support.LifecycleCase):
    """`remove` deletes the unit alone, says what it kept, and reloads the manager after.

    The `.env`, the token, the log, and the worktree are byte for byte as they
    were, linger is never asked about, and the manager is told to forget a
    failure only where it still remembers one, since a service stopped cleanly
    is unloaded by the reload and `reset-failed` refuses one that is.
    """

    def test_deletes_only_the_unit(self) -> None:
        kept = self.setup_files()
        removed = (0, _REMOVED.format(self.unit_file, self.settings_file), "")
        for failed, forgotten in ((_NOT_FAILED, ()), (_support.DONE, (_support.RESET_FAILED,))):
            with self.subTest(failed=failed):
                self.unit_file.write_text("[Service]\n", encoding=_support.ENCODING)
                self.timeline.clear()
                self.systemd.answers[_support.IS_FAILED] = failed

                self.assertEqual(self.answered(removal.remove), removed)
                self.assertEqual(
                    tuple(self.timeline),
                    (*_UNTOUCHED, _support.RELOAD, _support.IS_FAILED, *forgotten),
                )
                self.assertFalse(self.unit_file.exists())
                self.assertEqual(self.setup_files(), kept)
        self.assertEqual(self.systemd.bounds[_support.STOP], _support.STOP_BOUND)

    def test_without_a_unit_it_does_nothing(self) -> None:
        self.unit_file.unlink()
        kept = self.setup_files()

        self.assertEqual(self.answered(removal.remove), (
            0, f"No service is installed at {self.unit_file}, so remove changed nothing\n", "",
        ))
        self.assertEqual(self.timeline, [])
        self.assertEqual(self.setup_files(), kept)


class FailedRemovalTest(_support.LifecycleCase):
    """A step that fails exits 1 with no step after it, naming what finishes the removal."""

    def test_a_refused_stop_or_disable_keeps_the_unit(self) -> None:
        unit_text = self.unit_file.read_text(encoding=_support.ENCODING)
        for step, taken in _REFUSED_STEPS:
            with self.subTest(step=step):
                self.timeline.clear()
                self.systemd.answers = {step: _DENIED}
                refused = _KEPT.format(" ".join(step[2:]), self.unit_file)

                self.assertEqual(self.answered(removal.remove), (1, "", refused))
                self.assertEqual(tuple(self.timeline), taken)
                self.assertEqual(self.unit_file.read_text(encoding=_support.ENCODING), unit_text)

    def test_an_unanswered_failure_query_is_reported(self) -> None:
        kept = self.setup_files()
        for unanswered, reason in (
            (_support.NO_BUS, "Failed to connect to bus: No medium found"),
            (Completed(None, "", _TIMED_OUT), _TIMED_OUT),
        ):
            with self.subTest(reason=reason):
                self.unit_file.write_text("[Service]\n", encoding=_support.ENCODING)
                self.timeline.clear()
                self.systemd.answers[_support.IS_FAILED] = unanswered
                refused = _UNANSWERED.format(reason, self.unit_file)

                self.assertEqual(self.answered(removal.remove), (1, "", refused))
                self.assertEqual(
                    tuple(self.timeline),
                    (*_UNTOUCHED, _support.RELOAD, _support.IS_FAILED),
                )
                self.assertFalse(self.unit_file.exists())
                self.assertEqual(self.setup_files(), kept)

    def test_a_refused_reload_names_what_finishes(self) -> None:
        self.systemd.answers[_support.RELOAD] = _DENIED
        refused = (
            "systemctl --user daemon-reload failed (Access denied); "
            f"{self.unit_file} is deleted, so finish with: systemctl --user daemon-reload\n"
        )

        self.assertEqual(self.answered(removal.remove), (1, "", refused))
        self.assertEqual(tuple(self.timeline), (*_UNTOUCHED, _support.RELOAD))
        self.assertFalse(self.unit_file.exists())
