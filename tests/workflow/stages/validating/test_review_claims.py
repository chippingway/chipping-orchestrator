# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The verification evidence a returned reviewer's declaration earns, and where it stands.

Commands a reviewer ran are minted as a reviewer-reported transaction past
every revision the issue has spent, bound to the subject, head, and tree it
was handed and to the configured verification context, and carried verbatim.
A reuse earns a claim on exactly the evidence the reviewer was handed, and on
nothing when it was handed none or names anything else. Every other reading
earns nothing and says why. A claim's evidence is settled while it is the
current evidence it names, owed while it is the transaction still waiting to
be published under the configured context, and lost otherwise.
"""
from __future__ import annotations

import unittest
from dataclasses import replace
from unittest.mock import patch

from orchestrator import config
from orchestrator.agents.models import AgentResult
from orchestrator.github import verification_evidence as _evidence
from orchestrator.github.pinned_state import MAX_PINNED_BODY
from orchestrator.workflow.engine import (
    report_records as _report_records,
    verification_record_state as _record_state,
    verification_records as _records,
    verification_settlement_state as _settlement,
)
from orchestrator.workflow.stages.validating import (
    models as _models,
    review_claims as _claims,
    review_evidence as _review_evidence,
    review_verdicts as _verdicts,
)
from tests.workflow.engine import verification_evidence_test_support as support
from tests.workflow.fixtures import _TEST_SPEC, _agent

OUTPUT = "12 passed"

RUFF = "uv run ruff check orchestrator tests"

# A digest no evidence on the issue carries.
OTHER_DIGEST = "0123456789abcdef" * 4

REVIEWER_SESSION = "rev-sess"

# Output every line of which an artifact carries, and all of which no one comment does.
PAST_ONE_COMMENT = "x" * MAX_PINNED_BODY

# What each reading that earns nothing is told apart by.
INCOMPLETE = "did not complete cleanly"

MALFORMED = "declaration is malformed"

STALE = "names another commit, or other evidence"

UNBOUND = "could not be bound as evidence"

UNPUBLISHABLE = "cannot be published verbatim"

UNMINTED = "revisions this issue has spent could not be read"


def _declared(
    command: str = support.SUITE, exit_status: int = 0, output: str = OUTPUT, commit: str = support.TESTED_SHA,
) -> str:
    """A reviewer's final message declaring one run of `command` on `commit`."""
    return (
        "The change matches the issue.\n\n"
        f"VERIFICATION: RUN {commit}\n"
        f"COMMAND: {command}\n"
        f"EXIT: {exit_status}\n"
        f"{output}\n"
        "VERIFICATION: END\n\n"
        "VERDICT: APPROVED"
    )


def _reused(revision: str) -> str:
    """A reviewer's final message naming evidence `revision` instead of running anything."""
    return f"The change matches the issue.\n\nVERIFICATION: REUSED sha256:{revision}\n\nVERDICT: APPROVED"


def _returned(message: str, **agent_fields) -> AgentResult:
    """The reviewer run that returned `message`."""
    return _agent(session_id=REVIEWER_SESSION, last_message=message, **agent_fields)


# Every reading that earns nothing: the reviewer run, what the world moved
# before it returned, and what the reading is told apart by.
_EARNS_NOTHING = (
    ("a run that timed out", _returned(_declared(), timed_out=True), None, INCOMPLETE),
    ("no declaration at all", _returned("VERDICT: APPROVED"), None, _claims.NO_DECLARATION),
    ("a block never closed", _returned(_declared().replace("VERIFICATION: END\n", "")), None, MALFORMED),
    ("a run on another commit", _returned(_declared(commit=support.REBASED_SHA)), None, STALE),
    ("output behind a fence", _returned(_declared(output=f"```text\n{OUTPUT}\n```")), None, UNPUBLISHABLE),
    ("more output than one comment holds", _returned(_declared(output=PAST_ONE_COMMENT)), None, UNPUBLISHABLE),
    ("output UTF-8 cannot carry", _returned(_declared(output="12 passed \ud800")), None, UNPUBLISHABLE),
    (
        "a tree nobody can read",
        _returned(_declared()),
        lambda case: case.world.trees.pop(support.TESTED_SHA),
        UNBOUND,
    ),
    (
        "no settled report",
        _returned(_declared()),
        lambda case: case.state.set(_report_records.CURRENT_REPORT, None),
        UNBOUND,
    ),
    (
        "a floor nobody can read",
        _returned(_declared()),
        lambda case: case.state.set(_records.REVISION_FLOOR, None),
        UNMINTED,
    ),
)

# Each run a reviewer declares, and the claim flags it earns: whether it
# passed, and whether it covers the configured suite.
_DECLARED_RUNS = (
    ((support.SUITE, 0), (True, True)),
    ((support.SUITE, 1), (False, False)),
    ((RUFF, 0), (True, False)),
)

# The two commands a configuration requiring both lists.
_BOTH = (support.SUITE, RUFF)

SUITE_PASSED = _evidence.VerifiedCommand(support.SUITE, 0)

RUFF_PASSED = _evidence.VerifiedCommand(RUFF, 0)

RUFF_FAILED = _evidence.VerifiedCommand(RUFF, 1)


class ClaimedEvidenceTest(unittest.TestCase, support.VerificationEvidenceCase):
    """What a declaration earns, over evidence an earlier round settled for the subject."""

    def setUp(self) -> None:
        support.VerificationEvidenceCase.setUp(self)
        self.record()
        self.reconcile()
        with self.seams():
            self.handed = _review_evidence.handed_evidence(
                self.gh, _TEST_SPEC, self.issue, self.state, self.subject,
            )
        self.assertIsNotNone(self.handed)

    def claimed(self, returned: AgentResult, *, handed=...) -> _claims.ClaimedEvidence:
        """What a reviewer of the settled report, handed `handed`, earns by its run `returned`."""
        run = _models._ReviewerRun(
            wt=self.world.path,
            round_n=0,
            pr_number=support.PR_NUMBER,
            agent_result=returned,
            delivery=None,
            subject=self.subject,
            resolved_over=dict(self.state.data),
            evidence=self.handed if handed is ... else handed,
        )
        with self.seams():
            return _claims.claimed_evidence(self.issue, self.state, run)

    def test_commands_it_ran_are_minted_as_handed(self) -> None:
        # Past the settled revision, bound to the subject, head, and tree the
        # reviewer was handed under the configured context, and carried as
        # the reviewer stated them -- a failing run included, which says so.
        for ran, (passed, covers) in _DECLARED_RUNS:
            with self.subTest(ran=ran):
                claimed = self.claimed(_returned(_declared(*ran)))

                pending = claimed.pending
                self.assertEqual(
                    (pending.binding, pending.commands, pending.revision),
                    (
                        self.binding(source=_evidence.EvidenceSource.REVIEWER_REPORTED),
                        (_evidence.VerifiedCommand(*ran, OUTPUT),),
                        2,
                    ),
                )
                self.assertEqual(claimed, _claims.ClaimedEvidence(
                    _verdicts.EvidenceClaim(
                        _verdicts.EvidenceUse.PUBLISHED, pending.receipt, pending.revision,
                        pending.content_revision, passed=passed, covers=covers,
                    ),
                    pending,
                ))

    def test_a_reuse_names_the_evidence_handed(self) -> None:
        current = _settlement.read_current_evidence(self.state)

        claimed = self.claimed(_returned(_reused(self.handed.revision)))

        self.assertEqual(claimed, _claims.ClaimedEvidence(
            _verdicts.EvidenceClaim(
                _verdicts.EvidenceUse.REUSED, current.receipt, current.revision,
                current.content_revision, passed=True, covers=True,
            ),
        ))

    def test_reusing_what_was_not_handed_earns_none(self) -> None:
        # The current evidence's own revision, named by a reviewer never
        # handed it, is no reuse either.
        for name, message, handed in (
            ("handed nothing", _reused(self.handed.revision), None),
            ("other evidence named", _reused(OTHER_DIGEST), self.handed),
        ):
            with self.subTest(name):
                claimed = self.claimed(_returned(message), handed=handed)

                self.assertEqual((claimed.claim, claimed.pending), (None, None))
                self.assertIn(STALE, claimed.refusal)

    def test_anything_else_earns_nothing_and_says_why(self) -> None:
        for name, returned, moves, why in _EARNS_NOTHING:
            with self.subTest(name):
                self.setUp()
                if moves is not None:
                    moves(self)

                claimed = self.claimed(returned)

                self.assertEqual((claimed.claim, claimed.pending), (None, None))
                self.assertIn(why, claimed.refusal)

    def test_a_claim_stands_settled_owed_or_lost(self) -> None:
        earlier = self.claimed(_returned(_reused(self.handed.revision))).claim
        later = self.claimed(_returned(_declared()))
        settled = _claims.claim_standing(self.state, earlier)
        self.assertTrue(_record_state.record_pending_evidence(self.state, later.pending))
        self.gh.write_pinned_state(self.issue, self.state)

        # The later transaction spent a revision past the evidence still
        # current, which it supersedes before it has settled.
        self.assertEqual(
            [settled, *(_claims.claim_standing(self.state, claim) for claim in (
                earlier, later.claim, replace(later.claim, digest=OTHER_DIGEST),
            ))],
            [
                _claims.ClaimStanding.SETTLED,
                _claims.ClaimStanding.LOST,
                _claims.ClaimStanding.OWED,
                _claims.ClaimStanding.LOST,
            ],
        )
        # Evidence recorded under a context the configuration has moved past,
        # settled or not, is evidence the proof refuses.
        with patch.object(config, "VERIFY_COMMANDS", (RUFF,)):
            self.assertEqual(
                [_claims.claim_standing(self.state, claim) for claim in (earlier, later.claim)],
                [_claims.ClaimStanding.LOST, _claims.ClaimStanding.LOST],
            )

        self.reconcile()

        self.assertEqual(
            [_claims.claim_standing(self.state, claim) for claim in (earlier, later.claim)],
            [_claims.ClaimStanding.LOST, _claims.ClaimStanding.SETTLED],
        )


class CoversTheConfigurationTest(unittest.TestCase):
    """Every configured command, exactly as configured, exiting 0 -- and nothing else counts."""

    def test_coverage_is_the_configuration_exactly(self) -> None:
        for configured, commands, covers in (
            (_BOTH, (SUITE_PASSED, RUFF_PASSED), True),
            (_BOTH, (SUITE_PASSED,), False),
            (_BOTH, (SUITE_PASSED, RUFF_FAILED), False),
            (_BOTH, (SUITE_PASSED, RUFF_FAILED, RUFF_PASSED), True),
            ((support.SUITE,), (replace(SUITE_PASSED, command=f"{support.SUITE} -x"),), False),
            ((), (), True),
        ):
            with self.subTest(configured=configured, commands=commands), patch.object(
                config, "VERIFY_COMMANDS", configured,
            ):
                self.assertIs(_claims.covers_the_configuration(commands), covers)


if __name__ == "__main__":
    unittest.main()
