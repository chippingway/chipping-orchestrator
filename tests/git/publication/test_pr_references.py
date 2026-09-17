# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The references `pr_references` leaves a published subject ending in."""

from __future__ import annotations

import unittest

from orchestrator.git.publication import pr_references

PR_NUMBER = 12
ISSUE_NUMBER = 7
UNRELATED_NUMBER = 99
SUBJECT = "feat: add a thing"
REFERENCED = f"{SUBJECT} (#{PR_NUMBER})"
ISSUE_REFERENCED = f"{SUBJECT} (#{ISSUE_NUMBER})"

# The two subjects that landed on `main` carrying the tracked issue ahead of
# the pull request: each as it was published, the line it should have been,
# and the two numbers it was published under.
REPORTED_SUBJECTS = (
    (
        "feat: fan out emitted human-wait transitions to analytics (#1836) (#1849)",
        "feat: fan out emitted human-wait transitions to analytics (#1849)",
        1849,
        1836,
    ),
    (
        "feat: correlate failed-run parks through shared park funnel (#1837) (#1850)",
        "feat: correlate failed-run parks through shared park funnel (#1850)",
        1850,
        1837,
    ),
)

# Every shape a subject reaches normalization in, paired with the line it
# leaves: bare, the tracked issue alone, the issue ahead of this pull
# request, this pull request twice, already correct, and an unrelated
# reference. Read together they are the whole policy.
NORMALIZED_SUBJECTS = (
    (SUBJECT, REFERENCED),
    (ISSUE_REFERENCED, REFERENCED),
    (f"{ISSUE_REFERENCED} (#{PR_NUMBER})", REFERENCED),
    (f"{REFERENCED} (#{PR_NUMBER})", REFERENCED),
    (REFERENCED, REFERENCED),
    (
        f"{SUBJECT} (#{UNRELATED_NUMBER})",
        f"{SUBJECT} (#{UNRELATED_NUMBER}) (#{PR_NUMBER})",
    ),
)


def _normalized(subject: str) -> str:
    """`subject` under the tracked issue and pull request these tests share."""
    return pr_references._subject_with_pr_reference(
        subject, PR_NUMBER, ISSUE_NUMBER,
    )


class SubjectNormalizationTest(unittest.TestCase):
    """`_subject_with_pr_reference` drops the tracked issue's reference, ends
    the line in exactly one reference to its pull request, and leaves every
    other reference and the subject's own text alone."""

    def test_reported_subjects_lose_the_issue(self) -> None:
        # The commits the policy was written for: a developer subject that
        # already carried the issue number, published with the pull request's
        # appended after it. The desired line is normalized too, so the fix
        # for each is one a later tick lands on again rather than undoes.
        for published, desired, pr_number, issue_number in REPORTED_SUBJECTS:
            for line in (published, desired):
                with self.subTest(subject=line):
                    self.assertEqual(
                        pr_references._subject_with_pr_reference(
                            line, pr_number, issue_number,
                        ),
                        desired,
                    )

    def test_each_reference_shape_normalizes(self) -> None:
        # Equality with the whole expected line is what rules out a body, a
        # trailer, or a closing keyword riding along.
        for subject, expected in NORMALIZED_SUBJECTS:
            with self.subTest(subject=subject):
                self.assertEqual(_normalized(subject), expected)

    def test_reapplying_it_changes_nothing(self) -> None:
        # What lets the rewrite decision below be asked by comparison, and
        # what a second approval round, a retried tick, and a recovered
        # publication each land on.
        for subject, _expected in NORMALIZED_SUBJECTS:
            with self.subTest(subject=subject):
                once = _normalized(subject)
                self.assertEqual(_normalized(once), once)

    def test_trailing_whitespace_is_dropped(self) -> None:
        for subject in (f"{SUBJECT} \t", f"{REFERENCED} ", f"{ISSUE_REFERENCED}\t"):
            with self.subTest(subject=subject):
                self.assertEqual(_normalized(subject), REFERENCED)

    def test_text_the_author_wrote_is_not_a_reference(self) -> None:
        # Only the trailing run is the orchestrator's to rewrite: a number in
        # the middle of the line is prose, and one written without the space
        # the orchestrator puts before its own is not the spelling.
        for subject in (
            f"feat: rework (#{ISSUE_NUMBER}) handling",
            f"{SUBJECT}(#{ISSUE_NUMBER})",
            f"{SUBJECT}(#{PR_NUMBER})",
        ):
            with self.subTest(subject=subject):
                self.assertEqual(
                    _normalized(subject), f"{subject} (#{PR_NUMBER})",
                )

    def test_no_tracked_issue_strips_nothing(self) -> None:
        # The call an issue-unaware publisher makes: every reference on the
        # line is somebody else's, and only the pull request's is added.
        self.assertEqual(
            pr_references._subject_with_pr_reference(
                ISSUE_REFERENCED, PR_NUMBER,
            ),
            f"{ISSUE_REFERENCED} (#{PR_NUMBER})",
        )


class SubjectWithoutIssueReferenceTest(unittest.TestCase):
    """`_subject_without_issue_reference` removes the tracked issue's
    reference and adds nothing, which is what title selection needs before a
    pull request exists to name."""

    def test_the_tracked_issue_is_removed(self) -> None:
        for subject in (
            ISSUE_REFERENCED,
            f"{ISSUE_REFERENCED} \t",
            f"{SUBJECT} (#{ISSUE_NUMBER}) (#{ISSUE_NUMBER})",
        ):
            with self.subTest(subject=subject):
                self.assertEqual(
                    pr_references._subject_without_issue_reference(
                        subject, ISSUE_NUMBER,
                    ),
                    SUBJECT,
                )

    def test_the_issue_ahead_of_a_pr_is_dropped(self) -> None:
        self.assertEqual(
            pr_references._subject_without_issue_reference(
                f"{ISSUE_REFERENCED} (#{PR_NUMBER})", ISSUE_NUMBER,
            ),
            REFERENCED,
        )

    def test_every_other_reference_survives(self) -> None:
        for subject in (
            SUBJECT,
            f"{SUBJECT} (#{UNRELATED_NUMBER})",
            REFERENCED,
            f"feat: rework (#{ISSUE_NUMBER}) handling",
        ):
            with self.subTest(subject=subject):
                self.assertEqual(
                    pr_references._subject_without_issue_reference(
                        subject, ISSUE_NUMBER,
                    ),
                    subject,
                )

    def test_no_tracked_issue_removes_nothing(self) -> None:
        self.assertEqual(
            pr_references._subject_without_issue_reference(
                ISSUE_REFERENCED, None,
            ),
            ISSUE_REFERENCED,
        )


class SubjectOwesTheReferenceTest(unittest.TestCase):
    """`_subject_owes_the_reference` answers the normalization's own rule
    backwards.

    What a publisher deciding whether to rewrite a commit asks. It has to
    agree with the normalization exactly: a subject said to owe nothing and
    then published as it stands would keep an issue reference or miss the
    pull request's, and one said to owe a rewrite it has already had would be
    rewritten every tick.
    """

    def test_a_changed_subject_owes_a_rewrite(self) -> None:
        for subject, expected in NORMALIZED_SUBJECTS:
            with self.subTest(subject=subject):
                self.assertEqual(
                    pr_references._subject_owes_the_reference(
                        subject, PR_NUMBER, ISSUE_NUMBER,
                    ),
                    subject != expected,
                )

    def test_issue_plus_pr_owes_a_rewrite(self) -> None:
        # The one-commit branch the reported subjects were published from:
        # ending in the pull request's reference is not enough to skip it.
        for published, _desired, pr_number, issue_number in REPORTED_SUBJECTS:
            with self.subTest(subject=published):
                self.assertTrue(
                    pr_references._subject_owes_the_reference(
                        published, pr_number, issue_number,
                    ),
                )

    def test_an_empty_subject_owes_one(self) -> None:
        for subject in ("", " \t"):
            with self.subTest(subject=subject):
                self.assertTrue(
                    pr_references._subject_owes_the_reference(
                        subject, PR_NUMBER, ISSUE_NUMBER,
                    ),
                )

    def test_a_normalized_subject_owes_nothing(self) -> None:
        for subject in (REFERENCED, f"{REFERENCED} \t"):
            with self.subTest(subject=subject):
                self.assertFalse(
                    pr_references._subject_owes_the_reference(
                        subject, PR_NUMBER, ISSUE_NUMBER,
                    ),
                )

    def test_no_pull_request_is_owed_nothing(self) -> None:
        # The install with the reference switched off: nothing is added, and
        # the tracked issue is not stripped on the way to a rewrite that is
        # never made.
        for subject in (SUBJECT, ISSUE_REFERENCED):
            with self.subTest(subject=subject):
                self.assertFalse(
                    pr_references._subject_owes_the_reference(
                        subject, None, ISSUE_NUMBER,
                    ),
                )


if __name__ == "__main__":
    unittest.main()
