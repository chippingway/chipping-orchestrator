# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What the allowlist filter is worth once it reaches its two consumers.

`_recent_comments_text` is the single choke point every conversation-carrying
prompt (implement, review, documentation, decompose, question, drift-resume)
reads from, and `_compute_user_content_hash` is the drift signal. Both must
drop an untrusted author's comment whole once `ALLOWED_ISSUE_AUTHORS` is set,
so an outsider on a public repo can neither inject workflow-driving text into a
coding agent nor shift the drift hash to re-trigger the workflow.
"""
from __future__ import annotations

import unittest
from unittest.mock import patch

from orchestrator import config
from orchestrator.workflow.engine import (
    content_hash as _requirement_hash,
    conversation_prompts as _conversation_prompts,
    decomposition_prompts as _decomposition_prompts,
    prompt_context as _prompt_context,
    prompts,
    review_prompts as _review_prompts,
)
from tests.support.fakes import FakeComment, FakeUser, make_issue
from tests.workflow.engine import comment_trust_test_support as trust
from tests.workflow.fixtures import _TEST_SPEC


def _built_prompts(issue, comments_text: str) -> dict[str, str]:
    specs = [_TEST_SPEC]
    return {
        "implement": prompts._build_implement_prompt(
            _TEST_SPEC, issue, comments_text, specs,
        ),
        "review": _review_prompts._build_review_prompt(
            _TEST_SPEC, issue, comments_text, specs,
        ),
        "documentation": prompts._build_documentation_prompt(
            _TEST_SPEC, issue, comments_text, specs,
        ),
        "decompose": _decomposition_prompts._build_decompose_prompt(
            _TEST_SPEC, issue, comments_text, specs,
        ),
        "question": _conversation_prompts._build_question_prompt(
            _TEST_SPEC, issue, comments_text, specs,
        ),
    }


def _content_hash(issue) -> str:
    return _requirement_hash._compute_user_content_hash(issue, set())


class PromptBuilderTrustFilterTest(unittest.TestCase):
    """Each named prompt builder gets its conversation text from
    `_recent_comments_text`, so with the allowlist set none of them can
    surface the outsider's URL or instructions, while the allowed comment
    still reaches every one of them."""

    def test_only_allowed_content_reaches_prompts(self) -> None:
        issue = trust.issue_with_comments()
        with patch.object(config, trust.ALLOWLIST_CONFIG, (trust.ALLOWED_AUTHOR,)):
            comments_text = _prompt_context._recent_comments_text(issue)
        for name, prompt in _built_prompts(issue, comments_text).items():
            with self.subTest(builder=name):
                self.assertNotIn(trust.MALICIOUS_URL, prompt)
                self.assertNotIn(trust.PATCH_INSTRUCTION, prompt)
                self.assertIn(trust.ALLOWED_MARKER, prompt)


class DriftHashTrustFilterTest(unittest.TestCase):
    def test_only_allowed_content_changes_hash(self) -> None:
        issue_number = trust.TRUST_FILTER_ISSUE_NUMBER
        base = make_issue(issue_number, title="t", body="b")
        outsider = make_issue(
            issue_number, title="t", body="b",
            comments=[
                FakeComment(1, trust.OUTSIDER_BODY, FakeUser(trust.OUTSIDER_AUTHOR)),
            ],
        )
        allowed = make_issue(
            issue_number, title="t", body="b",
            comments=[
                FakeComment(2, trust.ALLOWED_BODY, FakeUser(trust.ALLOWED_AUTHOR)),
            ],
        )
        with patch.object(config, trust.ALLOWLIST_CONFIG, (trust.ALLOWED_AUTHOR,)):
            base_hash = _content_hash(base)
            self.assertEqual(_content_hash(outsider), base_hash)
            self.assertNotEqual(_content_hash(allowed), base_hash)
        # The no-change above is the allowlist doing the work, not an inert
        # comment body: with no allowlist the same outsider comment shifts
        # the hash.
        with patch.object(config, trust.ALLOWLIST_CONFIG, ()):
            self.assertNotEqual(_content_hash(outsider), _content_hash(base))


if __name__ == "__main__":
    unittest.main()
