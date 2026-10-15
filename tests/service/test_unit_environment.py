# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The environment the installed unit and its drop-ins give the service, assembled as systemd does."""
from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from orchestrator.service import unit_environment
from orchestrator.service.unit_file import render_unit
from tests.service import init_test_support as _init

_USER = _init.USER
_UNIT_DROP_INS = f"~/.config/systemd/user/{_init.UNIT}.d"
_VENDOR_DROP_INS = f"/usr/lib/systemd/user/{_init.UNIT}.d"
# Each `PATH` a unit is rendered for, holding what its quoting escapes.
_RENDERED_PATHS = (
    "/usr/local/bin:/usr/bin",
    "/opt/my tools:/x/%h:/y%%n",
    r'/q"uote:/back\slash',
    "/it's",
    "",
)


class UnitEnvironmentCase(unittest.TestCase):
    """A home holding the unit `init` writes, with the directories outside it under a scratch root."""

    def setUp(self) -> None:
        scratch = Path(self.enterContext(tempfile.TemporaryDirectory())).resolve()
        self.home = scratch / "home"
        self._root = scratch / "root"
        self.enterContext(patch.dict(os.environ, HOME=str(self.home)))
        self.enterContext(patch.object(unit_environment, "SYSTEM_ROOT", self._root))
        self.write("~/.config/systemd/user/chipping-orchestrator.service", render_unit(_init.INTERPRETER, "/usr/bin"))

    def write(self, located: str, text: str) -> Path:
        """Write ``text`` at ``located``, under the home where it starts with ``~``, else the root."""
        anchor = self.home if located.startswith("~") else self._root
        path = anchor / located.lstrip("~/")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding=_init.ENCODING)
        return path


class RenderedUnitTest(UnitEnvironmentCase):
    """The `PATH` a rendered unit records reads back unchanged, and nothing beside it."""

    def test_every_rendered_path_reads_back(self) -> None:
        for search_path in _RENDERED_PATHS:
            with self.subTest(search_path=search_path):
                self.write(
                    "~/.config/systemd/user/chipping-orchestrator.service",
                    render_unit(_init.INTERPRETER, search_path),
                )

                self.assertEqual(unit_environment.unit_environment(_USER), {"PATH": search_path})


class DropInOrderTest(UnitEnvironmentCase):
    """Drop-ins apply after the unit in the order of their names, wherever systemd finds them.

    One named for the unit, for its name cut after a dash, or for every
    service counts alike, under the home or the system's directories; a later
    assignment replaces an earlier one, `%h` and `%u` expand to the home and
    the user, and a file not named `*.conf`, or hidden behind a leading dot,
    is no drop-in.
    """

    def test_drop_ins_apply_by_name(self) -> None:
        self.write(
            "/usr/lib/systemd/user/service.d/10-vendor.conf",
            "[Service]\nEnvironment=LABEL=vendor ONLY=vendor\n",
        )
        self.write(f"{_UNIT_DROP_INS}/20-path.conf", '[Service]\nEnvironment=PATH=%h/bin "LABEL=from 20"\n')
        self.write("/etc/systemd/user/chipping-.service.d/30-label.conf", "[Service]\nEnvironment=LABEL=%u-30\n")
        self.write(f"{_UNIT_DROP_INS}/40-ignored.conf.bak", "[Service]\nEnvironment=LABEL=ignored\n")
        self.write(f"{_UNIT_DROP_INS}/.50-hidden.conf", "[Service]\nEnvironment=HIDDEN=read\n")

        self.assertEqual(unit_environment.unit_environment(_USER), {
            "PATH": f"{self.home}/bin",
            "LABEL": f"{_USER}-30",
            "ONLY": "vendor",
        })

    def test_a_drop_in_masks_its_name_further_down(self) -> None:
        self.write(f"{_UNIT_DROP_INS}/10-same.conf", "[Service]\nEnvironment=CHOSEN=user\n")
        self.write(f"{_VENDOR_DROP_INS}/10-same.conf", "[Service]\nEnvironment=CHOSEN=vendor VENDOR=yes\n")
        self.write("/etc/systemd/user/service.d/10-same.conf", "[Service]\nEnvironment=CHOSEN=every\n")

        self.assertEqual(
            unit_environment.unit_environment(_USER),
            {"PATH": "/usr/bin", "CHOSEN": "user"},
        )

    def test_an_empty_assignment_drops_the_rest(self) -> None:
        self.write(f"{_UNIT_DROP_INS}/10-reset.conf", "[Service]\nEnvironment=\nEnvironment=AFTER=1\n")

        self.assertEqual(unit_environment.unit_environment(_USER), {"AFTER": "1"})

    def test_an_unreadable_drop_in_is_refused(self) -> None:
        unreadable = self.home / ".config/systemd/user" / f"{_init.UNIT}.d" / "10-directory.conf"
        unreadable.mkdir(parents=True)

        with self.assertRaisesRegex(unit_environment.UnitEnvironmentError, f"^{unreadable} cannot be read \\("):
            unit_environment.unit_environment(_USER)


class WorkingDirectoryTest(UnitEnvironmentCase):
    """The service starts in the last `WorkingDirectory=` the unit and its drop-ins set, the home by default."""

    def test_the_last_directory_set_is_the_one(self) -> None:
        self.assertEqual(unit_environment.unit_working_directory(_USER), str(self.home))
        self.write(f"{_VENDOR_DROP_INS}/10-vendor.conf", "[Service]\nWorkingDirectory=/srv/vendor\n")
        self.write(f"{_UNIT_DROP_INS}/20-user.conf", "[Service]\nWorkingDirectory=%h/%u\n")

        self.assertEqual(unit_environment.unit_working_directory(_USER), f"{self.home}/{_USER}")


if __name__ == "__main__":
    unittest.main()
