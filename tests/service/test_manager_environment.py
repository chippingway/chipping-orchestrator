# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The variables the user manager's configuration hands every service, assembled as the manager assembles them."""
from __future__ import annotations

import os
import re
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from orchestrator.service import unit_environment
from orchestrator.service.manager_environment import manager_environment
from tests.service import init_test_support as _init

_USER = _init.USER
_HOME_ENVIRONMENT_D = "~/.config/environment.d"
_BACKSLASH = "\\"


class ManagerEnvironmentCase(unittest.TestCase):
    """A home and a root of its own for the system's directories, both empty until a test writes to them."""

    def setUp(self) -> None:
        scratch = Path(self.enterContext(tempfile.TemporaryDirectory())).resolve()
        self.home = scratch / "home"
        self._root = scratch / "root"
        self.enterContext(patch.dict(os.environ, HOME=str(self.home)))
        self.enterContext(patch.object(unit_environment, "SYSTEM_ROOT", self._root))

    def write(self, located: str, text: str) -> Path:
        """Write ``text`` at ``located``, under the home where it starts with ``~``, else the root."""
        anchor = self.home if located.startswith("~") else self._root
        path = anchor / located.lstrip("~/")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding=_init.ENCODING)
        return path


class EnvironmentDTest(ManagerEnvironmentCase):
    """`environment.d` files apply in name order, the home's ranking first, each value expanded as it is read.

    A file masks one of its name further down, a hidden one is no file, and
    a value is expanded against what the manager is known to hold and every
    variable set before it.
    """

    def test_files_apply_by_name_and_expand(self) -> None:
        self.write("/usr/lib/environment.d/10-vendor.conf", "LABEL=vendor\nONLY=vendor\n")
        self.write("/etc/environment.d/10-vendor.conf", "LABEL=admin\n")
        self.write(f"{_HOME_ENVIRONMENT_D}/20-user.conf", "WHERE=$HOME/$LABEL\nWHO=${USER}\n")
        self.write("/etc/environment.d/30-later.conf", "LABEL=${LABEL:+later}\n")
        self.write(f"{_HOME_ENVIRONMENT_D}/.40-hidden.conf", "LABEL=hidden\n")

        self.assertEqual(manager_environment(_USER), {
            "LABEL": "later",
            "WHERE": f"{self.home}/admin",
            "WHO": _USER,
        })

    def test_an_unread_file_is_refused_naming_it(self) -> None:
        continued = self.write(f"{_HOME_ENVIRONMENT_D}/50-continued.conf", f"A=1 {_BACKSLASH}\nB=2\n")

        with self.assertRaisesRegex(
            unit_environment.UnitEnvironmentError,
            f"^{continued} cannot be read as systemd reads it \\(",
        ):
            manager_environment(_USER)


class DefaultEnvironmentTest(ManagerEnvironmentCase):
    """`DefaultEnvironment=` in `user.conf` and its drop-ins lies beneath `environment.d`.

    The home's `user.conf` stands in for the system's, a drop-in in the home's
    `user.conf.d` masks a system one of its name, an empty value drops what
    came before, the manager's own specifiers are expanded -- a `%` ending a
    word kept as it is -- and `environment.d` values expand against what it
    set.
    """

    def test_user_conf_lies_beneath_environment_d(self) -> None:
        self.write("/etc/systemd/user.conf", "[Manager]\nDefaultEnvironment=SYSTEM=ignored\n")
        self.write("~/.config/systemd/user.conf", '[Manager]\nDefaultEnvironment=MAIN=1 "SPACED=a b"\n')
        self.write(
            "/usr/lib/systemd/user.conf.d/10-reset.conf",
            "[Manager]\nDefaultEnvironment=\nDefaultEnvironment=KEPT=%h/kept OVERRIDDEN=default\n",
        )
        self.write("/etc/systemd/user.conf.d/20-same.conf", "[Manager]\nDefaultEnvironment=MASKED=system\n")
        self.write(
            "~/.config/systemd/user.conf.d/20-same.conf",
            "[Manager]\nDefaultEnvironment=WHO=%u:%U:%G LONE=50% PERCENT=%%h\n",
        )
        self.write(f"{_HOME_ENVIRONMENT_D}/10.conf", "OVERRIDDEN=environment.d\nSEEN=$KEPT\n")

        self.assertEqual(manager_environment(_USER), {
            "KEPT": f"{self.home}/kept",
            "WHO": f"{_USER}:{os.getuid()}:{os.getgid()}",
            "LONE": "50%",
            "PERCENT": "%h",
            "OVERRIDDEN": "environment.d",
            "SEEN": f"{self.home}/kept",
        })

    def test_another_specifier_is_refused(self) -> None:
        drop_in = self.write("~/.config/systemd/user.conf.d/10-host.conf", "[Manager]\nDefaultEnvironment=WHERE=%H\n")

        with self.assertRaisesRegex(
            unit_environment.UnitEnvironmentError,
            f"^{drop_in} cannot be read as systemd reads it .*holds a specifier other than %%, %h, %u, %U, %G",
        ):
            manager_environment(_USER)



class ManagerEnvironmentTest(ManagerEnvironmentCase):
    """`ManagerEnvironment=` lies beneath `DefaultEnvironment=`, which lies beneath `environment.d`.

    Neither may set a variable that moves where systemd reads its own
    configuration: the manager's for `ManagerEnvironment=`, the generator's
    `environment.d` for `DefaultEnvironment=`.
    """

    def test_the_manager_s_own_lies_beneath(self) -> None:
        self.write(
            "~/.config/systemd/user.conf",
            "[Manager]\nManagerEnvironment=ONLY=manager BOTH=manager ALL=manager\n"
            "DefaultEnvironment=BOTH=default ALL=default\n",
        )
        self.write(f"{_HOME_ENVIRONMENT_D}/10.conf", "ALL=environment.d\nSEEN=$ONLY\n")

        self.assertEqual(manager_environment(_USER), {
            "ONLY": "manager",
            "BOTH": "default",
            "ALL": "environment.d",
            "SEEN": "manager",
        })

    def test_a_moving_variable_is_refused(self) -> None:
        for directive, moving in (
            ("ManagerEnvironment", "HOME"),
            ("ManagerEnvironment", "XDG_DATA_DIRS"),
            ("DefaultEnvironment", "XDG_CONFIG_HOME"),
        ):
            with self.subTest(directive=directive, moving=moving):
                user_conf = self.write("~/.config/systemd/user.conf", f"[Manager]\n{directive}={moving}=/x\n")
                refusal = (
                    f"{user_conf} sets {moving} with {directive}=, which moves where systemd reads "
                    "its own configuration, so only systemd can resolve it"
                )

                with self.assertRaisesRegex(unit_environment.UnitEnvironmentError, f"^{re.escape(refusal)}$"):
                    manager_environment(_USER)


if __name__ == "__main__":
    unittest.main()
