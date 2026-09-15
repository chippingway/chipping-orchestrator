# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The pull-request reference `pr_references` ends a published subject in."""

from __future__ import annotations

import unittest

from orchestrator.git.publication import pr_references

PR_NUMBER = 12
SUBJECT = "feat: add a thing"
SUFFIXED_SUBJECT = f"{SUBJECT} (#{PR_NUMBER})"


class SubjectPrReferenceTest(unittest.TestCase):
    """`_subject_with_pr_reference` ends a subject in exactly one reference to
    its pull request, leaves one already carrying that reference alone, and
    reads a reference to any other number as ordinary text."""

    def test_ordinary_subject_gains_one_suffix(self) -> None:
        # Equality with the bare suffixed line is what rules out a body, a
        # trailer, or a closing keyword riding along.
        for subject in (
            SUBJECT,
            "event: add the winter gala",
            "updated stuff",
        ):
            with self.subTest(subject=subject):
                self.assertEqual(
                    pr_references._subject_with_pr_reference(subject, PR_NUMBER),
                    f"{subject} (#{PR_NUMBER})",
                )

    def test_trailing_whitespace_is_dropped(self) -> None:
        for subject in (f"{SUBJECT} \t", f"{SUFFIXED_SUBJECT} "):
            with self.subTest(subject=subject):
                self.assertEqual(
                    pr_references._subject_with_pr_reference(subject, PR_NUMBER),
                    SUFFIXED_SUBJECT,
                )

    def test_same_pr_suffix_is_left_unchanged(self) -> None:
        self.assertEqual(
            pr_references._subject_with_pr_reference(
                SUFFIXED_SUBJECT, PR_NUMBER,
            ),
            SUFFIXED_SUBJECT,
        )

    def test_other_pr_suffix_is_ordinary_text(self) -> None:
        for subject, number in (
            (f"{SUBJECT} (#11)", PR_NUMBER),
            (f"{SUBJECT} (#112)", PR_NUMBER),  # shares the trailing digits
            (SUFFIXED_SUBJECT, 2),  # shares the last digit
            (f"{SUBJECT}(#{PR_NUMBER})", PR_NUMBER),  # not the spelling
        ):
            with self.subTest(subject=subject, number=number):
                self.assertEqual(
                    pr_references._subject_with_pr_reference(subject, number),
                    f"{subject} (#{number})",
                )


if __name__ == "__main__":
    unittest.main()
