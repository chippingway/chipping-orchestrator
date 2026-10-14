# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Setup files and directories: private modes, and a write that is whole or absent."""
from __future__ import annotations

import itertools
import os
import stat
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from orchestrator.service.private_files import private_directory, write_private

_OLD = "OLD=1\n"
_NEW = "NEW=2\n"
_PERMISSIVE = 0
# Takes the owner's own write bit away, which only an exact mode gives back.
_RESTRICTIVE = 0o277
_PRIVATE_DIRECTORY = 0o700
_PRIVATE_FILE = 0o600
_SHARED_DIRECTORY = 0o755
_SHARED_FILE = 0o644


def _mode(path: Path) -> int:
    return stat.S_IMODE(path.stat().st_mode)


class _ScratchCase(unittest.TestCase):
    """A scratch directory to write into, under a umask each test chooses."""

    def setUp(self) -> None:
        self._scratch = Path(self.enterContext(tempfile.TemporaryDirectory()))
        self._path = self._scratch / ".env"

    def _umask(self, mask: int) -> None:
        self.addCleanup(os.umask, os.umask(mask))

    def _left_behind(self) -> str | None:
        """The file's text, once nothing else is found beside it; ``None`` if absent."""
        others = [entry.name for entry in self._scratch.iterdir() if entry != self._path]
        self.assertEqual(others, [])
        return self._path.read_text() if self._path.exists() else None


class PrivateDirectoryTest(_ScratchCase):
    """A directory a setup makes is 0700 whatever the umask, and so is each
    parent it makes above it; one already in place is kept as it is.
    """

    def test_missing_directories_are_private(self) -> None:
        """A fresh home's `.config` and the directory under it, whatever the umask."""
        for mask in (_PERMISSIVE, _RESTRICTIVE):
            with self.subTest(umask=oct(mask)):
                home = self._scratch / oct(mask)
                home.mkdir()
                home.chmod(_SHARED_DIRECTORY)
                config = home / ".config"
                self._umask(mask)

                private_directory(config / "chipping-orchestrator")

                self.assertEqual(
                    [_mode(directory) for directory in (home, config, config / "chipping-orchestrator")],
                    [_SHARED_DIRECTORY, _PRIVATE_DIRECTORY, _PRIVATE_DIRECTORY],
                )

    def test_a_directory_in_place_is_kept_as_it_is(self) -> None:
        directory = self._scratch / "shared"
        directory.mkdir()
        directory.chmod(_SHARED_DIRECTORY)

        private_directory(directory)

        self.assertEqual(_mode(directory), _SHARED_DIRECTORY)

    def test_a_file_in_the_way_is_refused(self) -> None:
        self._path.write_text(_OLD)

        with self.assertRaises(FileExistsError):
            private_directory(self._path)


class WritePrivateTest(_ScratchCase):
    """A file is 0600 whatever the umask, and is never seen part written."""

    def test_a_new_file_is_private_and_alone(self) -> None:
        for mask, replace in itertools.product((_PERMISSIVE, _RESTRICTIVE), (False, True)):
            with self.subTest(umask=oct(mask), replace=replace):
                self._umask(mask)
                self._path.unlink(missing_ok=True)

                write_private(self._path, _NEW, replace=replace)

                self.assertEqual(self._left_behind(), _NEW)
                self.assertEqual(_mode(self._path), _PRIVATE_FILE)

    def test_a_file_in_place_is_never_overwritten(self) -> None:
        self._path.write_text(_OLD)

        with self.assertRaises(FileExistsError):
            write_private(self._path, _NEW, replace=False)

        self.assertEqual(self._left_behind(), _OLD)

    def test_a_replacement_swaps_the_whole_file(self) -> None:
        """The new file takes the name at once: a reader of the old one keeps it."""
        self._path.write_text(_OLD)
        self._path.chmod(_SHARED_FILE)
        with self._path.open(encoding="utf-8") as reader:
            write_private(self._path, _NEW, replace=True)

            self.assertEqual(reader.read(), _OLD)
        self.assertEqual(self._left_behind(), _NEW)
        self.assertEqual(_mode(self._path), _PRIVATE_FILE)

    def test_a_failed_write_leaves_what_was_there(self) -> None:
        for before, replace in itertools.product((None, _OLD), (False, True)):
            with self.subTest(before=before, replace=replace):
                self._path.unlink(missing_ok=True)
                if before is not None:
                    self._path.write_text(before)

                with patch.object(os, "fsync", side_effect=OSError("disk full")), self.assertRaises(OSError):
                    write_private(self._path, _NEW, replace=replace)

                self.assertEqual(self._left_behind(), before)


if __name__ == "__main__":
    unittest.main()
