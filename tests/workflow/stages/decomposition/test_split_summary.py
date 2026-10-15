# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The summary an ordinary split or its recovery posts: the decomposer's recorded rationale beside the children."""
from __future__ import annotations

import json
import re
import unittest
from types import MappingProxyType
from unittest.mock import patch

from orchestrator.workflow.stages.decomposition.late_result_models import MAX_RATIONALE, RATIONALE_TRUNCATION_MARKER
from tests.support.fakes import FakeGitHubClient, FakeIssue, make_issue
from tests.workflow.fixtures import (
    LABEL_BLOCKED,
    LABEL_DECOMPOSING,
    LABEL_UMBRELLA,
    _agent,
    _manifest,
)
from tests.workflow.stages.decomposition.decomposing_test_support import _DecomposingWorkflowMixin

KEY_SPLIT_RATIONALE = "split_rationale"
KEY_SPLIT_ATTEMPT = "split_attempt"
RUN_AGENT = "run_agent"
DECOMPOSER_SESSION = "dec-sess"
PARENT_NUMBER = 91

# Two slices, the second needing the first.
_SLICES = (
    {"title": "A", "body": "a", "depends_on": []},
    {"title": "B", "body": "b", "depends_on": [0]},
)

# What every split summary opens with, umbrella or not, and the hidden receipt it ends on.
_SUMMARY = ":bookmark_tabs: decomposer split this into"
_SUMMARY_RECEIPT = "<!--orchestrator-split-summary:issue={issue}:attempt={attempt}-->"

# What the summary quotes a recorded rationale under, and says where the record holds none.
_QUOTED_UNDER = "Decomposer rationale:\n\n"
_UNRECORDED = "Decomposer rationale was not recorded."

# The sentence only an umbrella's summary carries.
_UMBRELLA_ROLE = f"marking parent as `{LABEL_UMBRELLA}`"

# A multiline account built to escape its quote on a markdown thread: a fence
# line that closes an ordinary block, an indented one, a longer one opening
# another, and HTML comment openers -- one never closed, one spelling an
# orchestrator marker -- that outside a block hide everything after them.
_HOSTILE = (
    "Split the API from its docs; the parent keeps the release notes.\n"
    "```\n"
    "<!-- everything after this is hidden outside a block\n"
    "````python\n"
    "  ```  \n"
    "<!--orchestrator-comment-->\n"
    "The last line."
)

# A fence markdown opens a block with: a run of one fence character and nothing else.
_OPENING_FENCE = re.compile(r"`{3,}|~{3,}")

_RATIONALE = "the parent keeps the release notes"

_OVERLONG = "r" * (MAX_RATIONALE + 10)

# What a parent's record is rewritten with between an interrupted split and
# its recovery, as an older binary or a hand edit may leave it, and the text
# the recovered summary then quotes -- None where it says there is none.
_LEGACY = MappingProxyType({
    "missing": ({}, None),
    "null": ({KEY_SPLIT_RATIONALE: None}, None),
    "blank": ({KEY_SPLIT_RATIONALE: " \n\t "}, None),
    "number": ({KEY_SPLIT_RATIONALE: 42}, None),
    "boolean": ({KEY_SPLIT_RATIONALE: True}, None),
    "list": ({KEY_SPLIT_RATIONALE: [_RATIONALE]}, None),
    "object": ({KEY_SPLIT_RATIONALE: {"why": _RATIONALE}}, None),
    "padded": ({KEY_SPLIT_RATIONALE: f"  {_RATIONALE}\n"}, _RATIONALE),
    "overlong": (
        {KEY_SPLIT_RATIONALE: _OVERLONG},
        _OVERLONG[:MAX_RATIONALE - len(RATIONALE_TRUNCATION_MARKER)] + RATIONALE_TRUNCATION_MARKER,
    ),
})

# The one slice an interrupted split is asked for, so a crash at its child's
# seed leaves no slice uncreated for the recovery to park on.
_ONE_SLICE = _SLICES[:1]

# Where a split is interrupted, by the client write that dies there and the
# call it dies at: its child's seed, mid-loop; the summary's own post; and the
# parent's label, behind a summary that landed.
_INTERRUPTIONS = MappingProxyType({
    "seed": ("write_pinned_state", lambda issue, _record: issue.number != PARENT_NUMBER),
    "summary": ("comment", lambda _issue, body: _SUMMARY in body),
    "label": ("set_workflow_label", lambda issue, _label: issue.number == PARENT_NUMBER),
})


def _closes(line: str, fence: str) -> bool:
    """Whether markdown ends the block this fence opened on this line: nothing but as long a run of its character."""
    run = line.strip(" \t")
    return run.startswith(fence) and not run.strip(fence[0])


def _shown(summary: str) -> tuple[str, str]:
    """What a reader is shown inside the summary's rationale block, and what follows the block.

    The block ends where markdown ends it; one never closed runs off the end
    of the summary and raises.
    """
    lines = summary.partition(_QUOTED_UNDER)[2].split("\n")
    if not _OPENING_FENCE.fullmatch(lines[0]):
        raise AssertionError(f"no fenced rationale is quoted in {summary!r}")
    closing = 1
    while not _closes(lines[closing], lines[0]):
        closing += 1
    shown = "\n".join(lines[1:closing])
    return shown, "\n".join(lines[closing + 1:])


class _Interrupted:
    """A process that dies at one client write, once the split reaches the write the predicate names."""

    def __init__(self, gh: FakeGitHubClient, method: str, reached) -> None:
        self._write = getattr(gh, method)
        self._reached = reached

    def __call__(self, issue, written):
        if self._reached(issue, written):
            raise KeyboardInterrupt(f"#{issue.number}")
        return self._write(issue, written)


class _SummaryCase(unittest.TestCase, _DecomposingWorkflowMixin):
    """A `decomposing` parent its decomposer answers with a split."""

    def _parent(self) -> tuple[FakeGitHubClient, FakeIssue]:
        """A client holding the parent, with nothing recorded on it yet."""
        gh = FakeGitHubClient()
        issue = make_issue(PARENT_NUMBER, label=LABEL_DECOMPOSING)
        gh.add_issue(issue)
        return gh, issue

    def _split(self, gh: FakeGitHubClient, issue: FakeIssue, slices: tuple[dict, ...], **fields):
        """Run the tick on a non-umbrella split of these slices, with these fields beside its children."""
        payload = {"decision": "split", "umbrella": False, "children": list(slices)}
        payload.update(fields)
        answer = _agent(session_id=DECOMPOSER_SESSION, last_message=_manifest(json.dumps(payload)))
        return self._run_decomposing(gh, issue, run_agent=answer)

    def _summaries(self, gh: FakeGitHubClient) -> list[str]:
        """The split summaries posted on the parent's thread."""
        return [
            body for number, body in gh.posted_comments
            if number == PARENT_NUMBER and _SUMMARY in body
        ]

    def _parent_labels(self, gh: FakeGitHubClient) -> list[str]:
        """The workflow labels written onto the parent, in order."""
        return [label for number, label in gh.label_history if number == PARENT_NUMBER]

    def _listed(self, gh: FakeGitHubClient, slices: tuple[dict, ...]) -> str:
        """The lines a summary names the split's children in, each with the title it was planned under."""
        return "\n".join(
            f"- #{child.number}: {planned['title']}"
            for child, planned in zip(gh.created_child_issues, slices, strict=True)
        )

    def _receipt(self, gh: FakeGitHubClient) -> str:
        """The receipt a summary of the parent's recorded split attempt ends on."""
        attempt = gh.pinned_data(PARENT_NUMBER)[KEY_SPLIT_ATTEMPT]
        return _SUMMARY_RECEIPT.format(issue=PARENT_NUMBER, attempt=attempt)

    def _assert_summarized(self, gh: FakeGitHubClient, slices: tuple[dict, ...], quoted: str | None) -> str:
        """One summary listing every child, then this rationale or a sentence saying there is none, then its receipt."""
        summaries = self._summaries(gh)
        self.assertEqual(len(summaries), 1, "the summary is posted exactly once")
        summary = summaries[0]
        self.assertIn(f":\n\n{self._listed(gh, slices)}\n\n", summary, "the children come first")
        receipt = self._receipt(gh)
        if quoted is None:
            self.assertNotIn(_QUOTED_UNDER, summary)
            self.assertIn(f"\n\n{_UNRECORDED}\n\n{receipt}", summary)
            return summary
        shown, after = _shown(summary)
        self.assertEqual(shown, quoted, "shown whole, in one block no line of it closes")
        self.assertIn(receipt, after, "the receipt follows the block")
        return summary


class SplitSummaryRationaleTest(_SummaryCase):
    """A split's own summary quotes the rationale it recorded ahead of its first child."""

    def test_each_parent_role_quotes_it_whole(self) -> None:
        # Fence lines and HTML comment openers in the account stay inside its
        # block, and the receipt follows the block, outside it.
        for umbrella, label in ((False, LABEL_BLOCKED), (True, LABEL_UMBRELLA)):
            with self.subTest(umbrella=umbrella):
                gh, issue = self._parent()

                self._split(gh, issue, _SLICES, rationale=_HOSTILE, umbrella=umbrella)

                summary = self._assert_summarized(gh, _SLICES, _HOSTILE)
                self.assertEqual(_UMBRELLA_ROLE in summary, umbrella, "the summary names the parent's role")
                self.assertEqual(self._parent_labels(gh), [label])

    def test_a_split_that_gave_none_says_so(self) -> None:
        gh, issue = self._parent()

        self._split(gh, issue, _SLICES, umbrella=True)

        self.assertIn(_UMBRELLA_ROLE, self._assert_summarized(gh, _SLICES, None))
        self.assertEqual(self._parent_labels(gh), [LABEL_UMBRELLA])


class RecoveredSplitSummaryRationaleTest(_SummaryCase):
    """A recovery's summary quotes the same rationale, read back off the record with no decomposer run."""

    def test_a_recovery_quotes_the_same_words(self) -> None:
        # Only a split interrupted at its label has a summary on the thread
        # already, and it is not posted twice.
        for window, landed in (("seed", 0), ("summary", 0), ("label", 1)):
            with self.subTest(interrupted_at=window):
                self._assert_recovered(window, landed)

    def test_a_recovery_tolerates_an_unusable_record(self) -> None:
        # A value nobody can read as text is said to be unrecorded, and text
        # is read back as a split writes it: stripped, and cut at the bound.
        for case, (fields, quoted) in _LEGACY.items():
            with self.subTest(record=case):
                self._assert_tolerated(fields, quoted)

    def _assert_recovered(self, window: str, landed: int) -> None:
        gh, issue = self._parent()
        self._interrupted(gh, issue, window)
        self.assertEqual(len(self._summaries(gh)), landed)
        self.assertEqual(self._parent_labels(gh), [], "nothing is finalized")

        self._recover(gh, issue)

        self._assert_summarized(gh, _ONE_SLICE, _HOSTILE)
        self.assertEqual(self._parent_labels(gh), [LABEL_BLOCKED])

    def _assert_tolerated(self, fields: dict, quoted: str | None) -> None:
        gh, issue = self._parent()
        self._interrupted(gh, issue, "summary")
        record = gh.pinned_data(PARENT_NUMBER)
        record.pop(KEY_SPLIT_RATIONALE)
        gh.seed_state(issue, **record, **fields)

        self._recover(gh, issue)

        self._assert_summarized(gh, _ONE_SLICE, quoted)
        self.assertEqual(self._parent_labels(gh), [LABEL_BLOCKED])

    def _interrupted(self, gh: FakeGitHubClient, issue: FakeIssue, window: str) -> None:
        """Split the parent with the hostile rationale, dying at this window."""
        method, reached = _INTERRUPTIONS[window]
        interrupted = patch.object(gh, method, _Interrupted(gh, method, reached))
        with interrupted, self.assertRaises(KeyboardInterrupt):
            self._split(gh, issue, _ONE_SLICE, rationale=_HOSTILE)

    def _recover(self, gh: FakeGitHubClient, issue: FakeIssue) -> None:
        """Run the next tick, which finalizes the split it finds without asking the decomposer again."""
        self._run_decomposing(gh, issue, run_agent=_agent())[RUN_AGENT].assert_not_called()


if __name__ == "__main__":
    unittest.main()
