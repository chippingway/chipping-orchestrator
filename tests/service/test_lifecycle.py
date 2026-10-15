# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""`start`, `restart`, `stop`, and `status` acting on the service `init` installed."""
from __future__ import annotations

import os
from itertools import product

from orchestrator import __version__
from orchestrator.service import lifecycle, removal
from orchestrator.service.systemd import Completed
from tests.service import lifecycle_test_support as _support

_LAUNCHES = ((_support.START_COMMAND, _support.START), (_support.RESTART_COMMAND, _support.RESTART))
_ACTIVE = (
    "chipping-orchestrator.service is active 5 seconds after systemctl --user {0}; "
    "follow its journal with: journalctl --user-unit chipping-orchestrator.service -f\n"
)
_JOURNAL_LINES = "Oct 15 09:00:01 host python[42]: aborting: REPOS target missing\n"
_LEFT_ACTIVE = (
    "chipping-orchestrator.service was not seen active through the 5 seconds after "
    "systemctl --user start: it is activating; the last lines of its journal:\n"
    f"{_JOURNAL_LINES}"
)
_UNANSWERED = (
    "chipping-orchestrator.service was not seen active through the 5 seconds after "
    "systemctl --user start: systemctl --user is-active gave no state (systemctl did "
    "not finish within 6 seconds); its journal holds no lines\n"
)
_MASKED = "Failed to start chipping-orchestrator.service: Unit chipping-orchestrator.service is masked."
_REFUSED_START = f"systemctl --user start {_support.UNIT} failed ({_MASKED})"
_NO_MANAGER = (
    "systemctl --user cannot reach a systemd user manager (Failed to connect to "
    "bus: No medium found), which the service runs under; run chipping-orchestrator "
    "{0} as the service's user, in a login session that has a manager -- an ssh "
    "or desktop login rather than su or sudo -- and try again\n"
)
_UNCHECKED = (
    "chipping-orchestrator {0} left the service as it was: it would not run "
    "until the problems above are repaired"
)
_NO_TOKEN = "acme/api: no GitHub token in /home/alice/.config/acme/api/token"
_STOPPED = (
    "Stopped chipping-orchestrator.service; it is still enabled, so it starts "
    "again with the user manager, as at boot: chipping-orchestrator start runs it now\n"
)
_INACTIVE = "○ chipping-orchestrator.service - chipping-orchestrator\n     Active: inactive (dead)\n"
_NOT_FOUND = "Unit chipping-orchestrator.service could not be found.\n"
_WATCHED = (_support.PAUSED, _support.IS_ACTIVE)
# What a start that passes its check runs before the watch: the manager
# probed, its units reloaded, and the job.
_LAUNCHED = (_support.CHECKED, _support.PROBE, _support.RELOAD, _support.START)
# A watch whose every question takes 0.4 seconds: the first second waited
# whole, each later one only what the answer before it left of it.
_SLOW_ANSWER_SECONDS = 0.4
_SLOW_WATCH = (*_WATCHED, *(("pause", "0.6"), _support.IS_ACTIVE) * 4)
_SLOW_WATCH_SECONDS = 5.4
# A drop-in replacing the `PATH` init recorded with one the agents are not
# on, and overriding a setting `.env` holds.
_ELSEWHERE_PATH = "/opt/elsewhere/bin"
_ELSEWHERE_REPOS = "acme/web|/srv/web|main"
_ELSEWHERE = f'[Service]\nEnvironment="PATH={_ELSEWHERE_PATH}" "REPOS={_ELSEWHERE_REPOS}"\n'
_NO_AGENT = "DEV_AGENT, DECOMPOSE_AGENT: claude is not on PATH"
# A `PATH` a drop-in gives the service that resolves an agent from where it
# runs: through a relative entry, or an empty one -- leading, trailing, or the
# whole value.
_WORKING_DIRECTORY_PATHS = ("/usr/bin:bin", "./bin:/usr/bin", "/usr/bin:", ":/usr/bin", "")
_RELATIVE_PATH = (
    "{0} and its drop-ins give the service a PATH with an empty or relative "
    "entry, through which an agent would be looked up in whichever issue "
    "worktree it is started in, not where {1} can check it; make every entry "
    "an absolute directory, as chipping-orchestrator init writes them\n"
)
# Each drop-in a launch refuses before the check, where it is written, and
# why, its path standing in for the first field.
_UNRESOLVED_ADVICE = (
    "start checks the service's environment only as systemd would assemble it, "
    "so it asked systemd nothing: take that out -- settings belong in .env, "
    "tokens in the token files, and any other variable in an Environment= line "
    "of the unit -- or start the service with systemctl --user, which checks nothing"
)
_BACKSLASH = "\\"
_UNRESOLVED = (
    (
        _support.OVERRIDE,
        "[Service]\nEnvironmentFile=%h/agents.env\n",
        "{0} sets EnvironmentFile=, which only systemd can resolve",
    ),
    (
        "/etc/systemd/user/service.d/10-pass.conf",
        "[Service]\nPassEnvironment=PATH\n",
        "{0} sets PassEnvironment=, which only systemd can resolve",
    ),
    (
        _support.OVERRIDE,
        "[Service]\nUnsetEnvironment=PATH\n",
        "{0} sets UnsetEnvironment=, which only systemd can resolve",
    ),
    (
        _support.OVERRIDE,
        "[Service]\nExecStart=\nExecStart=/usr/bin/python3 -m orchestrator run\n",
        "{0} sets ExecStart=, so the service would not run the package that installed it",
    ),
    (
        _support.OVERRIDE,
        "[Service]\nEnvironment=PATH=%t/bin\n",
        (
            "{0} sets Environment= in a way not read here as systemd reads it: "
            "the value of PATH holds a specifier other than %%, %h, %u"
        ),
    ),
    (
        "~/.config/environment.d/50-continued.conf",
        f"A=1 {_BACKSLASH}\nB=2\n",
        (
            "{0} cannot be read as systemd reads it (line 1 continues past its end, which is "
            "not read here)"
        ),
    ),
    (
        _support.OVERRIDE,
        "[Service]\nWorkingDirectory=-/srv/work\n",
        (
            "{0} sets WorkingDirectory= in a way not read here as systemd reads it: the "
            "directory '-/srv/work' lets systemd skip it when missing, leaving the service "
            "where the user manager runs"
        ),
    ),
    (
        _support.OVERRIDE,
        "[Service]\nWorkingDirectory=work\n",
        (
            "{0} sets WorkingDirectory= in a way not read here as systemd reads it: the "
            "directory 'work' is not an absolute path"
        ),
    ),
)
# The commands that check nothing, each with the name it refuses under.
_UNCHECKED_COMMANDS = (
    ("stop", lifecycle.stop),
    ("status", lifecycle.status),
    ("remove", removal.remove),
)


class LaunchTest(_support.LifecycleCase):
    """A launch checks the setup on the unit's `PATH`, then launches the service and watches it stay active.

    The check is the local one, handed the shell's `HOME` and `USER` and the
    `PATH` the unit records rather than the shell's own; the job is bounded
    past systemd's stop deadline, and the service is asked once a second for
    5 seconds whether it is still active.
    """

    def test_a_service_staying_active_is_reported(self) -> None:
        for command, launch in _LAUNCHES:
            with self.subTest(command=command):
                self.timeline.clear()
                reported = _ACTIVE.format(command)

                self.assertEqual(self.launched(command), (0, reported, ""))
                self.assertEqual(
                    tuple(self.timeline),
                    (_support.CHECKED, _support.PROBE, _support.RELOAD, launch, *_WATCHED * 5),
                )
                self.assertEqual(self.systemd.bounds[launch], _support.STOP_BOUND)
                self.assertEqual(self.checked[-1], _support.service_check())

    def test_leaving_active_fails_with_the_journal(self) -> None:
        self.systemd.answers.update({
            _support.IS_ACTIVE: [_support.ACTIVE, Completed(3, "activating\n", "")],
            _support.JOURNAL: Completed(0, _JOURNAL_LINES, ""),
        })

        self.assertEqual(self.launched(_support.START_COMMAND), (1, "", _LEFT_ACTIVE))
        self.assertEqual(
            tuple(self.timeline),
            (*_LAUNCHED, *_WATCHED * 2, _support.JOURNAL),
        )

    def test_a_refused_job_fails_with_the_journal(self) -> None:
        self.systemd.answers[_support.START] = Completed(1, "", f"{_MASKED}\n")
        for journal, said in (
            (_support.DONE, "its journal holds no lines"),
            (
                Completed(1, "", "Failed to open journal: Permission denied\n"),
                "its journal cannot be read (Failed to open journal: Permission denied)",
            ),
        ):
            with self.subTest(said=said):
                self.timeline.clear()
                self.systemd.answers[_support.JOURNAL] = journal

                self.assertEqual(
                    self.launched(_support.START_COMMAND),
                    (1, "", f"{_REFUSED_START}; {said}\n"),
                )
                self.assertEqual(self.timeline, [
                    *_LAUNCHED, _support.JOURNAL,
                ])


class LaunchRefusalTest(_support.LifecycleCase):
    """What stops a launch before the job, each exiting 1 with the service as it was."""

    def test_invalid_settings_ask_systemd_nothing(self) -> None:
        self.problems.append(_NO_TOKEN)
        for command, _ in _LAUNCHES:
            with self.subTest(command=command):
                self.timeline.clear()

                self.assertEqual(
                    self.launched(command),
                    (1, "", f"{_NO_TOKEN}\n{_UNCHECKED.format(command)}\n"),
                )
                self.assertEqual(self.timeline, [_support.CHECKED])

    def test_a_missing_unit_is_refused_first(self) -> None:
        self.unit_file.unlink()
        refused = (
            f"{self.unit_file} does not exist, so there is no service to start; "
            "install it with chipping-orchestrator init\n"
        )

        self.assertEqual(self.launched(_support.START_COMMAND), (1, "", refused))
        self.assertEqual(self.timeline, [])

    def test_a_service_left_without_a_path_is_refused(self) -> None:
        self.write_drop_in(_support.OVERRIDE, "[Service]\nEnvironment=\nEnvironment=REPOS=acme/api\n")
        refused = (
            f"{self.unit_file} and its drop-ins leave the service no PATH of their own, "
            "so it would run with the user manager's, which start cannot check without "
            "asking it; chipping-orchestrator init writes the unit's, and an empty "
            "Environment= in a drop-in drops it\n"
        )

        self.assertEqual(self.launched(_support.START_COMMAND), (1, "", refused))
        self.assertEqual(self.timeline, [])

    def test_a_working_directory_path_is_refused(self) -> None:
        for (command, _), path in product(_LAUNCHES, _WORKING_DIRECTORY_PATHS):
            with self.subTest(command=command, path=path):
                self.write_drop_in(_support.OVERRIDE, f"[Service]\nEnvironment=PATH={path}\n")
                refused = _RELATIVE_PATH.format(self.unit_file, command)

                self.assertEqual(self.launched(command), (1, "", refused))
                self.assertEqual(self.timeline, [])

    def test_an_unreachable_manager_follows_the_check(self) -> None:
        self.systemd.answers[_support.PROBE] = _support.NO_BUS
        refused = _NO_MANAGER.format(_support.RESTART_COMMAND)

        self.assertEqual(self.launched(_support.RESTART_COMMAND), (1, "", refused))
        self.assertEqual(self.timeline, [_support.CHECKED, _support.PROBE])


class DropInTest(_support.LifecycleCase):
    """A launch checks the environment the unit's drop-ins leave the service, and asks systemd nothing first."""

    def test_the_drop_in_environment_is_checked(self) -> None:
        self.problems.append(_NO_AGENT)
        refused = f"{_NO_AGENT}\n{_UNCHECKED.format(_support.RESTART_COMMAND)}\n"
        # A byte-order mark before the section systemd drops, and so does the read.
        for text in (_ELSEWHERE, f"\ufeff{_ELSEWHERE}"):
            with self.subTest(text=text):
                self.timeline.clear()
                self.checked.clear()
                self.write_drop_in(_support.OVERRIDE, text)

                self.assertEqual(self.launched(_support.RESTART_COMMAND), (1, "", refused))
                self.assertEqual(self.timeline, [("check", _ELSEWHERE_PATH)])
                self.assertEqual(
                    self.checked,
                    [_support.service_check(PATH=_ELSEWHERE_PATH, REPOS=_ELSEWHERE_REPOS)],
                )

    def test_the_manager_s_variables_are_inherited(self) -> None:
        # The service inherits the manager's `HOME` as its configuration
        # sets it, and starts in the home all the same; the unit's own
        # variables lie over both.
        self.write_drop_in(
            "~/.config/environment.d/90-orchestrator.conf",
            "ALLOWED_ISSUE_AUTHORS=,\nHOME=/elsewhere\nPATH=/manager/bin\nREPOS=from-environment.d\n",
        )
        self.write_drop_in(_support.OVERRIDE, "[Service]\nEnvironment=REPOS=from-the-unit\n")

        self.assertEqual(self.launched(_support.START_COMMAND)[0], 0)
        self.assertEqual(self.checked, [
            _support.service_check(ALLOWED_ISSUE_AUTHORS=",", HOME="/elsewhere", REPOS="from-the-unit"),
        ])

    def test_the_check_runs_where_the_service_starts(self) -> None:
        self.write_drop_in(_support.OVERRIDE, "[Service]\nWorkingDirectory=%h/work\n")

        self.assertEqual(self.launched(_support.START_COMMAND)[0], 0)
        work = os.path.join(os.environ["HOME"], "work")
        self.assertEqual(self.checked, [_support.service_check(work)])

    def test_what_only_systemd_resolves_is_refused(self) -> None:
        for located, text, reason in _UNRESOLVED:
            with self.subTest(located=located):
                self.timeline.clear()
                drop_in = self.write_drop_in(located, text)
                refused = f"{reason.format(drop_in)}; {_UNRESOLVED_ADVICE}\n"

                self.assertEqual(self.launched(_support.START_COMMAND), (1, "", refused))
                self.assertEqual(self.timeline, [])
                drop_in.unlink()


class WatchBoundTest(_support.LifecycleCase):
    """The watch after a launch ends within 7 seconds of the job, however slowly the manager answers.

    Each question waits for the next second watched unless a slow answer has
    already passed it, and is bounded by the time left, so one the manager
    takes too long over is cut short there and counts as no answer.
    """

    def test_slow_answers_still_end_in_time(self) -> None:
        self.systemd.delays[_support.IS_ACTIVE] = _SLOW_ANSWER_SECONDS
        reported = _ACTIVE.format(_support.START_COMMAND)

        self.assertEqual(self.launched(_support.START_COMMAND), (0, reported, ""))
        self.assertEqual(tuple(self.timeline[len(_LAUNCHED):]), _SLOW_WATCH)
        self.assertAlmostEqual(self.systemd.clock.now, _SLOW_WATCH_SECONDS)
        # The last question is bounded by the 2 seconds left of the 7.
        self.assertAlmostEqual(self.systemd.bounds[_support.IS_ACTIVE], 2)

    def test_an_unanswered_question_is_cut_short(self) -> None:
        self.systemd.delays[_support.IS_ACTIVE] = 30
        unanswered = (_support.PAUSED, _support.IS_ACTIVE, _support.JOURNAL)

        self.assertEqual(self.launched(_support.START_COMMAND), (1, "", _UNANSWERED))
        self.assertEqual(tuple(self.timeline[len(_LAUNCHED):]), unanswered)
        # Asked after the first second, it is cut short at the 6 left of the 7.
        self.assertEqual(self.systemd.clock.now, 7)


class StopTest(_support.LifecycleCase):
    """`stop` has the manager stop the service, bounded past systemd's stop deadline, and checks nothing."""

    def test_stops_and_leaves_the_service_enabled(self) -> None:
        self.assertEqual(self.answered(lifecycle.stop), (0, _STOPPED, ""))
        self.assertEqual(self.timeline, [_support.PROBE, _support.STOP])
        self.assertEqual(self.systemd.bounds[_support.STOP], _support.STOP_BOUND)

    def test_a_refused_stop_fails_with_the_reason(self) -> None:
        denied = "Failed to stop chipping-orchestrator.service: Access denied"
        self.systemd.answers[_support.STOP] = Completed(1, "", f"{denied}\n")

        self.assertEqual(self.answered(lifecycle.stop), (
            1, "", f"systemctl --user stop {_support.UNIT} failed ({denied})\n",
        ))


class StatusTest(_support.LifecycleCase):
    """`status` prints what is installed, then the manager's status, and exits with its status."""

    def test_passes_the_manager_status_through(self) -> None:
        self.systemd.answers[_support.STATUS] = Completed(3, _INACTIVE, "")
        installed = (
            f"chipping-orchestrator {__version__}\n"
            f"Configuration: {self.settings_file}\n"
            f"Unit: {self.unit_file}\n"
        )

        self.assertEqual(self.answered(lifecycle.status), (3, f"{installed}{_INACTIVE}", ""))
        self.assertEqual(self.timeline, [_support.PROBE, _support.STATUS])

    def test_marks_what_is_missing(self) -> None:
        self.settings_file.unlink()
        self.unit_file.unlink()
        self.systemd.answers[_support.STATUS] = Completed(4, "", _NOT_FOUND)
        installed = (
            f"chipping-orchestrator {__version__}\n"
            f"Configuration: {self.settings_file} (missing)\n"
            f"Unit: {self.unit_file} (missing)\n"
        )

        self.assertEqual(self.answered(lifecycle.status), (4, installed, _NOT_FOUND))

    def test_a_status_that_never_ran_fails(self) -> None:
        timed_out = "systemctl did not finish within 30 seconds"
        self.systemd.answers[_support.STATUS] = Completed(None, "", timed_out)

        status, _, stderr = self.answered(lifecycle.status)

        self.assertEqual((status, stderr), (1, f"systemctl --user status failed ({timed_out})\n"))


class UnreachableManagerTest(_support.LifecycleCase):
    """`stop`, `status`, and `remove` each name the manager they could not reach, and act on nothing."""

    def test_each_command_names_itself(self) -> None:
        self.systemd.answers[_support.PROBE] = _support.NO_BUS
        for name, command in _UNCHECKED_COMMANDS:
            with self.subTest(command=name):
                self.timeline.clear()

                status, _, stderr = self.answered(command)

                self.assertEqual((status, stderr), (1, _NO_MANAGER.format(name)))
                self.assertEqual(self.timeline, [_support.PROBE])
        self.assertTrue(self.unit_file.exists())
