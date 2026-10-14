# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Where `configure` writes: never over a `.env`, and only where it can make the directory."""
from __future__ import annotations

import os
import unittest
from pathlib import Path
from unittest.mock import patch

from orchestrator.service import paths
from tests.service.configure_test_support import ConfigureCase, existing_refusal

_KEPT = "KEEP=1\n"


class ConfigureOverwriteTest(ConfigureCase):
    """A `.env` already in the way is kept as it is, and nothing is written beside it."""

    def test_a_file_in_the_way_is_kept(self) -> None:
        self._settings_file.parent.mkdir(parents=True)
        self._settings_file.write_text(_KEPT)

        self.assertEqual(self._refused(), existing_refusal(self._settings_file))

        self.assertEqual(self._settings_file.read_text(), _KEPT)
        self.assertEqual(os.listdir(self._settings_file.parent), [self._settings_file.name])

    def test_a_dangling_symlink_in_the_way_is_kept(self) -> None:
        elsewhere = self._scratch / "elsewhere"
        self._settings_file.parent.mkdir(parents=True)
        self._settings_file.symlink_to(elsewhere)

        self.assertEqual(self._refused(), existing_refusal(self._settings_file))

        self.assertEqual(self._settings_file.readlink(), elsewhere)
        self.assertFalse(elsewhere.exists())

    def test_an_env_written_meanwhile_is_kept(self) -> None:
        """A `.env` appearing after the check is still never written over."""
        self._settings_file.parent.mkdir(parents=True)

        with patch.object(paths, "log_dir", side_effect=self._write_meanwhile):
            self.assertEqual(self._refused(), existing_refusal(self._settings_file))

        self.assertEqual(self._settings_file.read_text(), _KEPT)
        self.assertEqual(os.listdir(self._settings_file.parent), [self._settings_file.name])

    def test_an_unmakeable_directory_is_refused(self) -> None:
        (self._home / ".config").write_text("")
        directory = self._settings_file.parent

        refused = self._refused()

        self.assertTrue(refused.startswith(f"{directory} cannot be created ("), refused)

    def _write_meanwhile(self) -> Path:
        """Write a `.env` while ``configure`` renders its own, then name the log directory."""
        self._settings_file.write_text(_KEPT)
        return self._log_dir


if __name__ == "__main__":
    unittest.main()
