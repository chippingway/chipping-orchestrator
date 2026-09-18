# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The prompt owner's shared parts.

What every builder has in common is what this module pins: the header that
carries the issue body and the thread text (with placeholders when either is
empty), the two notes a prompt that can end in a commit has to spell out, and
the bounded rendering the conflict listing falls back on. Per-stage contracts
that only one prompt promises are pinned beside the stage that reads the
answer back.
"""
from __future__ import annotations

import unittest

from orchestrator.workflow.engine import (
    conversation_prompts as _conversation_prompts,
    decomposition_prompts as _decomposition_prompts,
    drift,
    prompt_notes as _prompt_notes,
    prompts,
)
from orchestrator.workflow.stages.decomposition import late_revision as _late_revision
from tests.support.fakes import FakeComment, FakeUser, make_issue
from tests.workflow.fixtures import _TEST_SPEC

_PROMPT_ISSUE_NUMBER = 67200
_ISSUE_TITLE = "add a foo flag"
_ISSUE_BODY = "users want a foo flag"
_THREAD_TEXT = "@alice: please cover it in tests"
_BASE_REF = "origin/main"
_OVERFLOW_FILES = 23
_FEEDBACK_COMMENT_ID = 42
_PLAN_PATH = f"plans/issue-{_PROMPT_ISSUE_NUMBER}.md"
# Subject prefixes the repo-local instruction must NOT enumerate: the
# orchestrator runs against arbitrary repos, so a closed Conventional-Commits
# list would teach the wrong style everywhere else.
_FORBIDDEN_PREFIXES = ("feat:", "chore:", "refactor:", "test:")
_FOREGROUND_MARKER = "NEVER start a background job"
_AGY_WAIT_MARKERS = (
    "supported wait/status tools such as `manage_task` within the current response",
    "a `RUNNING` status requires continued polling or waiting",
    "ending the response to await a notification terminates AGY and cancels the command",
)

def _discussion_prompt(spec, issue, comments_text, specs) -> str:
    """The discussion builder called on the shared four, plus its own fifth.

    It is the one header builder with an argument of its own -- the path the
    stage would publish -- so the header sweep below reaches it through this
    rather than teaching every other builder a parameter none of them has.
    """
    return _conversation_prompts._build_discussion_prompt(
        spec, issue, comments_text, specs, _PLAN_PATH,
    )


# Every builder that opens on the shared issue-body + conversation header.
_HEADER_BUILDERS = (
    ("implement", prompts._build_implement_prompt),
    ("respawn_preamble", prompts._build_fresh_respawn_preamble),
    ("review", prompts._build_review_prompt),
    ("documentation", prompts._build_documentation_prompt),
    ("question", _conversation_prompts._build_question_prompt),
    ("decompose", _decomposition_prompts._build_decompose_prompt),
    ("discussion", _discussion_prompt),
)

# The conflict prompt is the one commit-producing prompt with no style note:
# its agent finishes an in-progress rebase (`git rebase --continue`) and
# authors no subject of its own.
_NO_STYLE_NOTE_PROMPTS = frozenset(("conflict",))


def _commit_producing_prompts() -> dict[str, str]:
    """Every prompt whose agent may end its turn with a commit.

    `_build_user_content_change_prompt` and the late revision's
    `_revision_prompt` are owned by stages rather than by the prompt owner, but
    they append the same two notes, so they belong in this sweep -- the
    contract is the note's, not the builder's. The bare resume payloads are
    here too: each is what a fresh rotation reads below the respawn preamble,
    which teaches no subject contract of its own.
    """
    issue = make_issue(
        _PROMPT_ISSUE_NUMBER, title=_ISSUE_TITLE, body=_ISSUE_BODY,
    )
    comments = [
        FakeComment(
            id=_FEEDBACK_COMMENT_ID,
            body="please rename foo to bar",
            user=FakeUser("alice"),
        ),
    ]
    return {
        "implement": prompts._build_implement_prompt(
            _TEST_SPEC, issue, comments_text="", specs=[_TEST_SPEC],
        ),
        "fix": prompts._build_fix_prompt("please fix the typo"),
        "pr_comment_followup": _conversation_prompts._build_pr_comment_followup(comments),
        "documentation": prompts._build_documentation_prompt(
            _TEST_SPEC, issue, comments_text="", specs=[_TEST_SPEC],
        ),
        "conflict": prompts._build_conflict_resolution_prompt(
            _BASE_REF, ["a.rs"],
        ),
        "user_content_change": drift._build_user_content_change_prompt(
            issue, comments_text="",
        ),
        # Both discussion prompts: a confirmed design is written down and
        # committed by whichever round the confirmation lands on, and its
        # subject becomes the plan PR's title.
        "discussion": _discussion_prompt(
            _TEST_SPEC, issue, "", [_TEST_SPEC],
        ),
        "discussion_followup": _conversation_prompts._build_discussion_followup_prompt(
            comments, _PLAN_PATH,
        ),
        "late_revision": _late_revision._revision_prompt(issue, tuple(comments)),
        "human_reply_followup": _conversation_prompts._build_human_reply_followup(
            comments,
        ),
        "continue_retry": _prompt_notes._DEVELOPER_CONTINUE_RETRY_PROMPT,
    }


class SharedPromptHeaderTest(unittest.TestCase):
    """One header feeds every conversation-carrying builder, so the issue body
    and the (already trust-filtered) thread text reach all of them -- and an
    empty one reads as an explicit placeholder rather than a blank section the
    agent could mistake for a truncated prompt."""

    def test_body_and_thread_reach_every_prompt(self) -> None:
        issue = make_issue(
            _PROMPT_ISSUE_NUMBER, title=_ISSUE_TITLE, body=_ISSUE_BODY,
        )
        for name, builder in _HEADER_BUILDERS:
            with self.subTest(builder=name):
                prompt = builder(
                    _TEST_SPEC, issue, _THREAD_TEXT, [_TEST_SPEC],
                )
                self.assertIn(_ISSUE_BODY, prompt)
                self.assertIn(_THREAD_TEXT, prompt)
                self.assertNotIn(_prompt_notes._NO_BODY, prompt)
                self.assertNotIn(_prompt_notes._NO_PRIOR_COMMENTS, prompt)

    def test_empty_body_and_thread_get_placeholders(self) -> None:
        issue = make_issue(_PROMPT_ISSUE_NUMBER, title=_ISSUE_TITLE, body="")
        for name, builder in _HEADER_BUILDERS:
            with self.subTest(builder=name):
                prompt = builder(_TEST_SPEC, issue, "", [_TEST_SPEC])
                self.assertIn(_prompt_notes._NO_BODY, prompt)
                self.assertIn(_prompt_notes._NO_PRIOR_COMMENTS, prompt)


class QuotedCommentSectionsTest(unittest.TestCase):
    """A multi-comment quote keeps the paragraph break the thread read uses.

    The builders that fold several comments into one blockquote join them on
    the separator the comment owner defines, so the quote inside a prompt and
    the sections around it break into paragraphs the same way.
    """

    def test_quoted_comments_break_on_a_blank_line(self) -> None:
        quoted_comments = [
            FakeComment(_FEEDBACK_COMMENT_ID, "rename foo to bar", FakeUser("alice")),
            FakeComment(_FEEDBACK_COMMENT_ID + 1, "and drop the flag", FakeUser("bob")),
        ]

        prompt = _conversation_prompts._build_pr_comment_followup(quoted_comments)

        self.assertIn(
            "> @alice: rename foo to bar\n> \n> @bob: and drop the flag", prompt,
        )


class CommitProducingNotesTest(unittest.TestCase):
    """The two notes every commit-producing prompt carries.

    The style note points the agent at the repo's OWN recent history rather
    than a hardcoded prefix list, because the orchestrator runs against
    arbitrary configured repos. That history already carries the ` (#N)`
    references publication appended to it, so the note reserves every numeric
    suffix for the orchestrator: an agent copying one has only the issue
    number to reach for, and the subject would land naming the issue and the
    pull request both. The foreground note spells out the one-shot
    execution model and the AGY asynchronous-command contract: a backgrounded
    build ("Miri is running, I'll continue when it completes") outlives no
    session, so its result is never observed and the issue parks forever.
    Asynchronous commands (such as in AGY sessions) must be polled or waited on
    within the current response using wait/status tools like `manage_task`,
    because a `RUNNING` task is cancelled if the response ends to await a
    notification.
    """

    def test_authoring_prompts_teach_local_style(self) -> None:
        for name, prompt in _commit_producing_prompts().items():
            if name in _NO_STYLE_NOTE_PROMPTS:
                continue
            with self.subTest(prompt=name):
                self.assertIn("git log", prompt)
                self.assertIn("repository-local", prompt)
                self.assertIn("event:", prompt)
                self.assertIn("career:", prompt)
                self.assertNotIn("Conventional", prompt)
                for prefix in _FORBIDDEN_PREFIXES:
                    self.assertNotIn(prefix, prompt)
                self.assertIn("subject line only", prompt)
                self.assertIn("Co-Authored-By", prompt)

    def test_reference_suffix_is_left_to_publication(self) -> None:
        for name, prompt in _commit_producing_prompts().items():
            if name in _NO_STYLE_NOTE_PROMPTS:
                continue
            with self.subTest(prompt=name):
                self.assertIn("publication metadata", prompt)
                self.assertIn("no numeric suffix of your own", prompt)
                self.assertIn(
                    "never end the subject with the number of the issue",
                    prompt,
                )
                self.assertIn(
                    "orchestrator supplies the pull request reference", prompt,
                )

    def test_every_prompt_has_the_foreground_note(self) -> None:
        for name, prompt in _commit_producing_prompts().items():
            with self.subTest(prompt=name):
                self.assertIn(_FOREGROUND_MARKER, prompt)
                for marker in _AGY_WAIT_MARKERS:
                    self.assertIn(marker, prompt)


class ConflictResolutionPromptTest(unittest.TestCase):
    """The conflicted-path listing is bounded: a rebase across a large base
    can conflict in far more files than belong in a prompt, so the list is
    capped while the count that frames the work stays exact."""

    def test_lists_every_path_below_the_cap(self) -> None:
        prompt = prompts._build_conflict_resolution_prompt(
            _BASE_REF, ["a.rs", "b/c.rs"],
        )
        self.assertIn(f"`git rebase {_BASE_REF}` left 2 conflicted", prompt)
        self.assertIn("- `a.rs`", prompt)
        self.assertIn("- `b/c.rs`", prompt)
        self.assertNotIn("more)", prompt)

    def test_overflow_elides_with_remainder_count(self) -> None:
        shown = prompts._MAX_FILES_SHOWN
        last_shown = shown - 1
        elided = _OVERFLOW_FILES - shown
        prompt = prompts._build_conflict_resolution_prompt(
            _BASE_REF, [f"f{index}.rs" for index in range(_OVERFLOW_FILES)],
        )
        self.assertIn(f"left {_OVERFLOW_FILES} conflicted", prompt)
        self.assertIn(f"- `f{last_shown}.rs`", prompt)
        self.assertNotIn(f"- `f{shown}.rs`", prompt)
        self.assertIn(f"- ... ({elided} more)", prompt)


class FixPromptTest(unittest.TestCase):

    def test_empty_feedback_still_names_the_reviewer(self) -> None:
        # A changes-requested verdict with nothing above the marker leaves the
        # feedback blank. The prompt still has to say what the agent is being
        # asked to do rather than quote an empty block.
        prompt = prompts._build_fix_prompt("   ")
        self.assertIn("(reviewer left no detail)", prompt)


if __name__ == "__main__":
    unittest.main()
