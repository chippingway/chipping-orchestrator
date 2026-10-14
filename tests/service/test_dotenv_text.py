# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Settings set in a `.env`'s text, and read back by the configuration's own loader."""
from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from orchestrator.config._dotenv import load_dotenv
from orchestrator.service import paths
from orchestrator.service.dotenv_text import assign, assignment
from tests.service.service_test_support import refusal

_KEY = "KEY"

# Values a line carries back as written: blanks, quotes, `#`, and `=` inside.
_READABLE = ("", "a b", "it's", "'open", 'shut"', "'mixed\"", "#not-a-comment", "a=b", "/srv/a|b;c")

# Values the loader would read back as something else.
_UNREADABLE = ("a\nb", "a\r\n", "a\x0bb", "a b", " a", "a\t", "'a'", '"a"')


class AssignTest(unittest.TestCase):
    """The line in effect takes the value; every other line stays byte for byte."""

    def test_the_first_live_line_is_the_one_set(self) -> None:
        text = "# KEY=example\nOTHER=1\n  KEY = old\r\nKEY=later\n# end"

        self.assertEqual(
            assign(text, _KEY, "new"),
            "# KEY=example\nOTHER=1\nKEY=new\r\nKEY=later\n# end",
        )
        self.assertEqual(assign("A=1\nKEY=old", _KEY, "new"), "A=1\nKEY=new")

    def test_a_key_no_line_sets_is_a_lookup_error(self) -> None:
        for text in ("", "# KEY=example\n", "KEYS=1\nOTHER=KEY\n"):
            with self.subTest(text=text), self.assertRaises(LookupError):
                assign(text, _KEY, "new")

    def test_a_value_read_back_otherwise_is_refused(self) -> None:
        for setting in _UNREADABLE:
            with self.subTest(setting=setting):
                expected = (
                    f"{setting!r} cannot be written as KEY in .env, which reads each "
                    "value from one line and strips the blanks and quotes around it"
                )
                self.assertEqual(refusal(assignment, _KEY, setting), expected)
                self.assertEqual(refusal(assign, "KEY=old\n", _KEY, setting), expected)


class LoaderRoundTripTest(unittest.TestCase):
    """What `assign` writes, the configuration's loader reads back unchanged.

    The file sits where an installed package reads it, under a home of the
    test's own, and is loaded for a package root that is no checkout.
    """

    def test_each_written_value_is_read_back(self) -> None:
        scratch = Path(self.enterContext(tempfile.TemporaryDirectory()))
        self.enterContext(patch.dict(os.environ, {"HOME": str(scratch)}))
        settings_file = paths.settings_file()
        settings_file.parent.mkdir(parents=True)
        for setting in _READABLE:
            with self.subTest(setting=setting):
                settings_file.write_text(assign("# KEY=example\nKEY=old\n", _KEY, setting))
                loaded: dict[str, str] = {}

                load_dotenv(scratch, loaded, self.fail)

                self.assertEqual(loaded, {_KEY: setting})


if __name__ == "__main__":
    unittest.main()
