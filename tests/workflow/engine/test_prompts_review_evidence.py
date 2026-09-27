# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The verification a reviewer's prompt hands it, and the declaration it teaches.

Beside the report, a reviewer is told what this repository configures as its
verification -- the commands, or plainly that none are configured -- and is
handed the evidence current for its subject, quoted whole under the revision
a reuse names. It is taught the one declaration its final message carries, in
the very spellings the declaration's reader accepts, and told that a SHA, a
count, or a command the orchestrator publishes itself is no change to request
while genuine failures and inaccurate claims still are.
"""
from __future__ import annotations

import re
import unittest
from unittest.mock import patch

from orchestrator import config
from orchestrator.github.pinned_state import PinnedState
from orchestrator.github.verification_evidence import EvidenceSource
from orchestrator.workflow.engine import (
    messages,
    review_evidence_prompts,
    review_prompts,
    review_verification,
    review_verification_models,
)
from tests.support.fakes import make_issue
from tests.workflow.engine import verification_record_test_support as _record_support
from tests.workflow.fixtures import _TEST_SPEC

SUBJECT = _record_support.SUBJECT

HEAD = SUBJECT.commit

LINT = "uv run ruff check orchestrator tests"

POLICY = (
    "do NOT request changes merely to have a developer or a human copy a "
    "commit SHA, a test count, or a command"
)

NOTHING_HANDED = "No current workflow verification evidence covers this subject"


def _handed(exit_status: int = 0) -> review_evidence_prompts.HandedEvidence:
    """Reviewer-reported evidence settled for `SUBJECT`, as a reviewer is handed it."""
    state = _record_support.reread(PinnedState(comment_id=1, state_data={}))
    pending = _record_support.minted(
        state,
        _record_support.binding(source=EvidenceSource.REVIEWER_REPORTED),
        (_record_support.ran(exit_status=exit_status),),
    )
    return review_evidence_prompts.HandedEvidence(
        _record_support.current(pending), pending.artifact,
    )


def _whole(handed: review_evidence_prompts.HandedEvidence) -> str:
    """The artifact's visible lines, preamble and commands both, as a blockquote quotes them."""
    artifact = handed.artifact
    return messages._as_blockquote(artifact.preamble + artifact.evidence)


def _prompt(handed=None) -> str:
    return review_prompts._build_review_prompt(
        _TEST_SPEC,
        make_issue(7, body="users want a foo flag"),
        "",
        [],
        review_prompts.ReviewHandover(subject=SUBJECT, evidence=handed),
    )


class VerificationPromptTest(unittest.TestCase):
    """What a reviewer is told about verification."""

    def test_the_configuration_is_named(self) -> None:
        with patch.object(config, "VERIFY_COMMANDS", (_record_support.SUITE, LINT)):
            configured = _prompt()
        with patch.object(config, "VERIFY_COMMANDS", ()):
            empty = _prompt()

        self.assertIn(f"are, in order: `{_record_support.SUITE}`, `{LINT}`.", configured)
        self.assertIn("configures no verification commands (`VERIFY_COMMANDS` is empty)", empty)
        self.assertIn("nothing the orchestrator runs is evidence that any check passed", empty)
        for name, handed in (("configured", configured), ("empty", empty)):
            with self.subTest(name):
                self.assertIn(f"  VERIFICATION: RUN {HEAD}\n", handed)
                self.assertIn(NOTHING_HANDED, handed)
                self.assertNotIn("VERIFICATION: REUSED", handed)
                self.assertIn(POLICY, handed)
                self.assertIn("evidence about another commit or subject remain changes", handed)
                # The declaration sits above the verdict the prompt closes on.
                self.assertLess(handed.index("VERIFICATION: RUN"), handed.rindex("VERDICT: APPROVED"))

    def test_current_evidence_is_quoted_whole(self) -> None:
        passing, failing = _handed(), _handed(exit_status=1)

        quoted = _prompt(passing)
        refused = _prompt(failing)

        self.assertIn(f"revision `sha256:{passing.revision}`", quoted)
        self.assertIn(f"  VERIFICATION: REUSED sha256:{passing.revision}", quoted)
        self.assertIn(f"comment {_record_support.ARTIFACT_COMMENT}", quoted)
        self.assertIn(_whole(passing), quoted)
        self.assertNotIn(NOTHING_HANDED, quoted)
        self.assertIn("every command it lists exited 0", quoted)
        self.assertIn("it does NOT show every required command passing", refused)

    def test_the_taught_declaration_parses(self) -> None:
        # Spelled from the same models the reader parses, so a reviewer
        # writing exactly what it is shown is read back -- the reuse naming
        # the evidence it was handed, the run naming the head under review.
        handed = _handed()
        quoted = _prompt(handed)
        reuse = re.search(r"^  (VERIFICATION: REUSED \S+)$", quoted, re.MULTILINE).group(1)
        run = "\n".join((
            re.search(r"^  (VERIFICATION: RUN \S+)$", quoted, re.MULTILINE).group(1),
            f"COMMAND: {_record_support.SUITE}",
            "EXIT: 0",
            "VERIFICATION: END",
        ))
        subject = review_verification_models._VerificationSubject(HEAD, handed.revision)

        self.assertIsInstance(
            review_verification._parse_verification_outcome(reuse, subject),
            review_verification_models._ReusedVerification,
        )
        self.assertIsInstance(
            review_verification._parse_verification_outcome(run, subject),
            review_verification_models._FreshVerification,
        )


if __name__ == "__main__":
    unittest.main()
