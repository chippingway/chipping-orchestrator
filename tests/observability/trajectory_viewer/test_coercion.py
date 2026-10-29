# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""How an untyped trajectory field narrows to the type a model declares."""
from __future__ import annotations

import unittest

from orchestrator.observability.trajectory_viewer import coercion

_SKILL_DEVELOP = "develop"


class ScalarCoercionTest(unittest.TestCase):
    """A number, a number spelled as a string, and everything else."""

    def test_numbers_and_numeric_strings_are_read(self) -> None:
        for raw_value, expected in ((7, 7), ("12", 12), ("  9 ", 9)):
            with self.subTest(raw_value=raw_value):
                self.assertEqual(coercion.coerce_int(raw_value), expected)

    def test_an_unreadable_number_is_absent(self) -> None:
        # Absent rather than zero: a turn index or a review round the reader
        # cannot parse is no index, never the first one.
        for raw_value in ("free", None, [], "1.2.3"):
            with self.subTest(raw_value=raw_value):
                self.assertIsNone(coercion.coerce_int(raw_value))

    def test_a_bool_is_not_a_number(self) -> None:
        # `True` is an `int` in Python, so a corrupt record carrying one where
        # a token count belongs would otherwise be counted as a 1.
        for raw_value in (True, False):
            with self.subTest(raw_value=raw_value):
                self.assertIsNone(coercion.coerce_int(raw_value))

    def test_an_absent_text_field_is_empty(self) -> None:
        # The page never has to guard a body or a name against `None`.
        for raw_value, expected in ((None, ""), ("body", "body"), (7, "7")):
            with self.subTest(raw_value=raw_value):
                self.assertEqual(coercion.coerce_str(raw_value), expected)


class CollectionCoercionTest(unittest.TestCase):
    """A scalar where an array belongs yields an empty section."""

    def test_a_name_list_drops_its_nulls(self) -> None:
        self.assertEqual(
            coercion.coerce_str_tuple([_SKILL_DEVELOP, None, 7]),
            (_SKILL_DEVELOP, "7"),
        )

    def test_a_non_list_yields_the_empty_one(self) -> None:
        for raw_value in (_SKILL_DEVELOP, 1, None, {"steps": 1}):
            with self.subTest(raw_value=raw_value):
                self.assertEqual(coercion.coerce_str_tuple(raw_value), ())
                self.assertEqual(coercion.as_list(raw_value), [])

    def test_a_list_is_handed_back_to_be_walked(self) -> None:
        raw_steps = [{"kind": "tool_call"}]
        self.assertIs(coercion.as_list(raw_steps), raw_steps)


if __name__ == "__main__":
    unittest.main()
