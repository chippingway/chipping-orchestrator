# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What the late-only prompt has to put in front of the adjudicator."""
from __future__ import annotations

import json
import re
import unittest

from orchestrator.workflow.late_split.events import LateVerdictCategory
from orchestrator.workflow.late_split.models import MAX_LINEAGE_DEPTH
from orchestrator.workflow.stages.decomposition import (
    late_budget as _budget,
    late_prompt as _prompt,
    late_reply as _late_reply,
)
from orchestrator.workflow.stages.decomposition.late_reply import _SPLIT_BLOCKER
from orchestrator.workflow.stages.decomposition.validation import _MAX_CHILDREN
from tests.support.fakes import make_issue
from tests.workflow.fixtures import _TEST_SPEC
from tests.workflow.stages.decomposition import late_test_support as _support

# The budget the JSON template shows, read back out of the composed prompt so
# what a case checks is the figure an agent would copy.
_TEMPLATE_ESTIMATE = re.compile(f'"{_budget.ESTIMATE}": ([0-9]+)')

# Ceilings the template has to stay under. The default this suite measures
# against, the narrow one an operator may configure -- where the standing
# example figure is itself an oversized child -- and the narrowest ceiling
# that leaves a child anything to claim.
_CEILINGS = (_support.THRESHOLD, 250, 2)

ISSUE_TITLE = "make the thing work"
ISSUE_BODY = "the original ask, as a human wrote it"
THREAD = "@alice: please keep the migration out of it"


def _prompt_for(generation=None) -> str:
    issue = make_issue(
        _support.LATE_ISSUE_NUMBER, title=ISSUE_TITLE, body=ISSUE_BODY,
    )
    return _prompt._build_late_decompose_prompt(
        _TEST_SPEC,
        issue,
        THREAD,
        _support.late_generation() if generation is None else generation,
        [],
    )


class LatePromptContextTest(unittest.TestCase):
    """The prompt carries the whole question, not just the size."""

    def test_it_carries_the_whole_question(self) -> None:
        for fragment in (
            ISSUE_TITLE,
            ISSUE_BODY,
            THREAD,
            _support.SCOPE,
            f"git diff {_support.BASE_SHA}...{_support.CANDIDATE_SHA}",
            f"candidate commit: {_support.CANDIDATE_SHA}",
            f"base commit: {_support.BASE_SHA}",
            f"{_support.ADDITIONS} lines",
            f"ceiling of {_support.THRESHOLD}",
        ):
            with self.subTest(fragment=fragment):
                self.assertIn(fragment, _prompt_for())

    def test_it_says_the_work_exists_read_only(self) -> None:
        composed = _prompt_for()

        self.assertIn("ALREADY implemented", composed)
        self.assertIn("COMMITTED", composed)
        self.assertIn("read-only", composed)

    def test_the_diff_is_the_measured_range(self) -> None:
        # Two dots would show everything that happened on the base since the
        # candidate branched, so a diverged history would put the agent on
        # changes nobody measured.
        composed = _prompt_for()

        self.assertNotIn(f"{_support.BASE_SHA}..{_support.CANDIDATE_SHA}`", composed)
        self.assertIn("THREE dots, not two", composed)

    def test_a_single_is_not_offered_as_a_publication(self) -> None:
        # What the verdict earns is the park a human's decision to publish an
        # oversized change unsplit is owed on. Told the orchestrator publishes
        # on its word, the agent would be weighing a consequence the workflow
        # does not give it -- and weighing it on every classification.
        composed = _prompt_for()

        self.assertIn("does NOT publish it", composed)
        self.assertIn("handed to a human", composed)
        self.assertNotIn("the orchestrator publishes it as it stands", composed)

    def test_a_single_is_a_human_decision(self) -> None:
        # The verdict hands a human the decision, so the prompt states the
        # one thing that decision turns on as an obligation. Asked as a
        # nicety, an agent that answered `single` and said nothing else would
        # leave the human the whole question and none of the reasoning.
        composed = _prompt_for()

        self.assertIn("REQUIRES A HUMAN DECISION", composed)
        self.assertIn("MUST say what they are being handed", composed)
        self.assertIn("SAFE SPLIT IS UNAVAILABLE", composed)

    def test_it_places_the_issue_in_its_lineage(self) -> None:
        composed = _prompt_for()

        self.assertIn(f"root issue: #{_support.ROOT_ISSUE}", composed)
        self.assertIn(f"this issue: #{_support.LATE_ISSUE_NUMBER}", composed)
        self.assertIn(f"lineage depth: 1 of at most {MAX_LINEAGE_DEPTH}", composed)


class LatePromptContractTest(unittest.TestCase):
    """The outcomes, the bounds, and the block the parser then reads."""

    def test_it_names_the_fence_and_decisions(self) -> None:
        composed = _prompt_for()

        self.assertIn(_support.LATE_FENCE, composed)
        for decision in ('"single"', '"split"', '"question"'):
            with self.subTest(decision=decision):
                self.assertIn(decision, composed)

    def test_it_states_the_bounds_it_is_judged_by(self) -> None:
        # Both numbers are read back off the owners that enforce them, so the
        # bound an agent is told cannot drift from the bound it is judged by.
        composed = _prompt_for()

        self.assertIn(f"at most {_MAX_CHILDREN} entries", composed)
        self.assertIn(f"at most {MAX_LINEAGE_DEPTH}", composed)

    def test_it_offers_the_closed_category_set(self) -> None:
        # Read off the closed vocabulary, so a category widened in review
        # reaches the prompt with it. `unknown` is what this binary answers
        # for a spelling it does not know, never one an agent may choose.
        offered = {
            member for member in LateVerdictCategory
            if f"`{member}`" in _prompt._CATEGORIES
        }

        self.assertEqual(
            offered,
            set(LateVerdictCategory) - {LateVerdictCategory.UNKNOWN},
        )
        self.assertIn(_prompt._CATEGORIES, _prompt_for())

    def test_generated_artifacts_get_both_answers(self) -> None:
        # The false positive and the real finding differ by whether the
        # artifacts belong in the commit, which is a human's call.
        composed = _prompt_for()

        self.assertIn('`single` with `"category": "generated_artifacts"`', composed)
        self.assertIn("should NOT have been committed", composed)

    def test_the_single_it_asks_for_reads_explained(self) -> None:
        # The two halves of one contract: the key the prompt states is the
        # key the parser reads, and the obligation it states is the one the
        # reply is judged by -- so an answer that explained itself is kept
        # whole, and one that named no obstacle is refused rather than
        # recorded as a verdict a human cannot act on. Asking for a spelling
        # nothing reads would leave every conforming `single` saying why it
        # was not split and nobody keeping the sentence.
        self.assertIn(f'`"{_SPLIT_BLOCKER}"`', _prompt_for())

        adjudication, _refusal = _late_reply._parse_late_reply(
            _support.late_block(json.dumps({
                "decision": "single", _SPLIT_BLOCKER: _support.SPLIT_BLOCKER,
            })),
            _support.THRESHOLD,
        )
        unexplained, refused = _late_reply._parse_late_reply(
            _support.late_block(json.dumps({"decision": "single"})), _support.THRESHOLD,
        )

        self.assertEqual(
            adjudication.split_blocker_explanation, _support.SPLIT_BLOCKER,
        )
        self.assertIsNone(unexplained)
        self.assertIn(_SPLIT_BLOCKER, refused)

    def test_the_split_rule_follows_the_lineage_depth(self) -> None:
        cases = (
            (0, True), (MAX_LINEAGE_DEPTH - 1, True),
            (MAX_LINEAGE_DEPTH, False), (None, False),
        )
        for depth, offered in cases:
            with self.subTest(depth=depth):
                composed = _prompt_for(_support.late_generation(lineage_depth=depth))
                self.assertEqual("`split` is available" in composed, offered)
                self.assertEqual(
                    "may NOT split further" in composed, not offered,
                )

    def test_an_unreadable_depth_reads_unknown(self) -> None:
        composed = _prompt_for(_support.late_generation(lineage_depth=None))

        self.assertIn("lineage depth: unknown", composed)


class LateSplitPlanTest(unittest.TestCase):
    """What a split has to consider, and what each child owns and declares."""

    def test_it_asks_for_dependency_ordered_slices(self) -> None:
        # The way out of a `single` an agent otherwise talks itself out of:
        # work that will not cut across features cuts along its dependencies,
        # and a prerequisite nothing consumes yet may land dormant rather
        # than standing as proof that no safe split exists.
        composed = _prompt_for()

        for fragment in (
            "DEPENDENCY-ORDERED IMPLEMENTATION SLICES",
            "MAY LAND DORMANT",
            "ACTIVATION waiting for the last consumer",
            "recovery and failure paths included",
            "not proof that no safe split exists",
        ):
            with self.subTest(fragment=fragment):
                self.assertIn(fragment, composed)

    def test_every_child_owns_its_tests_and_docs(self) -> None:
        # A slice whose proof or description belongs to a sibling is not one,
        # and neither is a child holding somebody else's tests.
        composed = _prompt_for()

        for fragment in (
            "EVERY CHILD BODY must own its slice end to end",
            "the tests that prove it",
            "the documentation that describes it",
        ):
            with self.subTest(fragment=fragment):
                self.assertIn(fragment, composed)

    def test_the_budget_it_asks_for_is_required(self) -> None:
        # What the number has to cover, what it has to clear, and what it
        # does not buy: an estimate excludes no path, sits under the ceiling
        # with room for the review fixes that land on the same pull request,
        # and never stands in for the measurement that decides.
        composed = _prompt_for()

        for fragment in (
            f'`"{_budget.ESTIMATE}"` is REQUIRED on every child',
            f"strictly below {_support.THRESHOLD}",
            "NO PATH MAY BE EXCLUDED",
            "REVIEW FIXES",
            "ACTUAL CUMULATIVE MEASUREMENT",
        ):
            with self.subTest(fragment=fragment):
                self.assertIn(fragment, composed)

    def test_the_ceiling_it_states_is_the_judged_one(self) -> None:
        # The two halves of one contract again: the key the prompt states is
        # the key the parser reads, and the ceiling it states is this
        # generation's own -- so a manifest that did what it was asked is
        # accepted, and one sized at the ceiling is refused by the number the
        # agent was given rather than by one it never saw.
        proposed, refusal = _late_reply._parse_late_reply(
            _support.SPLIT_REPLY, _support.THRESHOLD,
        )
        oversized, refused = _late_reply._parse_late_reply(
            _support.split_reply_of(_support.THRESHOLD), _support.THRESHOLD,
        )

        self.assertIsNone(refusal)
        self.assertEqual(proposed.child_count, 2)
        self.assertIsNone(oversized)
        self.assertIn(f"{_support.THRESHOLD}-line ceiling", refused)

    def test_the_example_it_shows_is_acceptable(self) -> None:
        # A template is copied verbatim, so the budget in it is judged by the
        # same ceiling the reply is: a standing figure would be refused on
        # every repository configured under it, and the prompt would be
        # handing out the one shape that parks the candidate it is about.
        for ceiling in _CEILINGS:
            with self.subTest(ceiling=ceiling):
                composed = _prompt_for(_support.late_generation(threshold=ceiling))
                shown = int(
                    _TEMPLATE_ESTIMATE.search(composed).group(1),
                )

                proposed, refusal = _late_reply._parse_late_reply(
                    _support.split_reply_of(shown), ceiling,
                )

                self.assertIsNone(refusal)
                self.assertEqual(proposed.child_count, 1)

    def test_an_unreadable_ceiling_names_the_block(self) -> None:
        # A generation that cannot say what it was measured against still
        # asks for the number, worded on the block that carries the ceiling
        # rather than on a figure this prompt would have to invent.
        composed = _prompt_for(_support.late_generation(threshold=None))

        self.assertIn(
            "strictly below the ceiling this candidate was measured against",
            composed,
        )


if __name__ == "__main__":
    unittest.main()
