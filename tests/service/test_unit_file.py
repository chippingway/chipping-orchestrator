# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The unit `init` installs, each value spelled the way systemd reads it back."""
from __future__ import annotations

import os
import re
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from orchestrator.service.unit_file import UnitValueError, legacy_unit_refusal, render_unit, unit_path
from tests.service import init_test_support as _support

_PYTHON = "/usr/bin/python3"
_QUOTED_PYTHON = '"/usr/bin/python3"'
_UNCARRIED_COMMAND = (
    "holds a quote, a backslash, or a '$', which systemd refuses or rewrites in "
    "the command it starts the service with; install the package under a path without one"
)
_CONTROL = "holds a control character, which no line of a systemd unit can carry"

# An interpreter and a `PATH`, and the two unit lines quoting them. A blank is
# carried as it is inside the quotes; a quote and a backslash in `PATH` are
# escaped for the unquoting systemd does; and every `%` is doubled for the
# specifier expansion it does after, a `%%` already there included.
_QUOTED = (
    (_PYTHON, "/usr/local/bin:/usr/bin", _QUOTED_PYTHON, '"PATH=/usr/local/bin:/usr/bin"'),
    ("/home/a b/venv/bin/python", "/opt/my tools", '"/home/a b/venv/bin/python"', '"PATH=/opt/my tools"'),
    ("/srv/100%/bin/python", "/x/%h:/y%%n", '"/srv/100%%/bin/python"', '"PATH=/x/%%h:/y%%%%n"'),
    (_PYTHON, r'/q"uote:/back\slash', _QUOTED_PYTHON, r'"PATH=/q\"uote:/back\\slash"'),
    (_PYTHON, "/it's", _QUOTED_PYTHON, '"PATH=/it\'s"'),
)

# An interpreter and a `PATH` the unit cannot carry, and what the refusal says.
_UNCARRIED = (
    ("python3", "", "running init is not an absolute path, which a unit's ExecStart needs"),
    ('/opt/a"b/python', "", _UNCARRIED_COMMAND),
    ("/opt/a'b/python", "", _UNCARRIED_COMMAND),
    (r"/opt/a\b/python", "", _UNCARRIED_COMMAND),
    ("/opt/${HOME}/python", "", _UNCARRIED_COMMAND),
    ("/opt/a\tb/python", "", _CONTROL),
    (_PYTHON, "/usr/bin\n[Service]", f"the captured PATH {_CONTROL}"),
)


class RenderedUnitTest(unittest.TestCase):
    """The unit holds exactly the values it is rendered for, quoted for systemd."""

    def test_each_value_is_quoted_for_systemd(self) -> None:
        for interpreter, search_path, exec_start, environment in _QUOTED:
            with self.subTest(interpreter=interpreter, search_path=search_path):
                self.assertEqual(
                    render_unit(interpreter, search_path),
                    _support.UNIT_TEXT.format(interpreter=exec_start, environment=environment),
                )

    def test_a_value_systemd_rewrites_is_refused(self) -> None:
        for interpreter, search_path, refusal in _UNCARRIED:
            with (
                self.subTest(interpreter=interpreter, search_path=search_path),
                self.assertRaisesRegex(UnitValueError, re.escape(refusal)),
            ):
                render_unit(interpreter, search_path)


class UnitPathsTest(unittest.TestCase):
    """Both units are read off the home directory at call time."""

    def setUp(self) -> None:
        self.home = Path(self.enterContext(tempfile.TemporaryDirectory())).resolve()
        self.enterContext(patch.dict(os.environ, HOME=str(self.home)))
        self.legacy = self.home / _support.UNIT_DIR / "orchestrator.service"

    def test_the_unit_is_the_users_own(self) -> None:
        self.assertEqual(unit_path(), self.home / _support.UNIT_DIR / _support.UNIT)

    def test_only_a_hand_written_unit_is_refused(self) -> None:
        self.assertIsNone(legacy_unit_refusal())
        self.legacy.parent.mkdir(parents=True)
        # A link left pointing nowhere is a unit systemd still reads the name of.
        self.legacy.symlink_to(self.home / "gone.service")

        refusal = legacy_unit_refusal()

        self.assertIsNotNone(refusal)
        self.assertTrue(refusal.startswith(f"{self.legacy} is a hand-written unit"), refusal)
        self.assertIn(f"rm {self.legacy}", refusal)


if __name__ == "__main__":
    unittest.main()
