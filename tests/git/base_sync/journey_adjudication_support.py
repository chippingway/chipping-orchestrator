# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The one adjudication an oversized candidate earns, walked for real.

Four ticks, each the production one. A `workflow:validating` publication the
real size gate holds and hands to `workflow:decomposing`; the real adjudicator
answering `single`, which parks for a human; the operator's command naming the
commit; and the settlement that command releases, which records the exemption
and its identity over the frozen pair and publishes the accepted commit back
onto the stage the gate took it from.

The publication is the gate call rather than a reviewer round around it: every
publication seam of that stage reaches the gate with these terms, and it is the
gate that holds the candidate.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

from orchestrator.agents import runner as _agent_runner
from orchestrator.git import branch_transport as _branch_transport
from orchestrator.workflow.stages.decomposition import late_coordinator as _coordinator, late_reply as _late_reply
from orchestrator.workflow.stages.implementing import (
    late_gate_models as _late_gate_models,
    late_push as _late_push,
    late_records as _late_records,
)
from orchestrator.workflow.state import WorkflowLabel
from tests.git.base_sync.journey_git_support import OPERATOR
from tests.git.base_sync.journey_push_support import PUSH_BRANCH, PublishesToThePullRequest
from tests.git.base_sync.real_git_test_support import PR_BRANCH
from tests.support.fakes import FakeComment, FakeUser
from tests.workflow.fixtures import _agent

# The verdict the adjudicator reaches, in the fence the reply owner parses --
# taken from that owner, so a manifest this build could not read fails here.
SINGLE_MANIFEST = (
    f"```{_late_reply._LATE_BLOCK}\n"
    + '{"decision": "single", "rationale": "one coherent change",'
    + ' "split_blocker": "the generated table only compiles whole"}\n```'
)

# The whole comment that publishes a parked `single` unsplit.
AUTHORIZE_COMMAND = "/orchestrator authorize-oversized {candidate}"


def adjudicates_once(fixture, candidate: str) -> None:
    """Walk `candidate` from the gate that holds it to its settlement."""
    spawn = MagicMock(return_value=_agent(last_message=SINGLE_MANIFEST))
    with patch.object(_agent_runner, "run_agent", spawn), patch.object(
        _branch_transport, PUSH_BRANCH, PublishesToThePullRequest(fixture._gh),
    ):
        _late_push._publishes(
            _late_records._gate(
                fixture._gh, fixture._spec, fixture._issue(),
                fixture._durable(), fixture._wt,
            ),
            PR_BRANCH,
            _late_gate_models._Entered(
                stage=WorkflowLabel.VALIDATING, head=candidate, candidate=candidate,
            ),
        )
        _adjudicates(fixture)
        _authorizes(fixture, candidate)
        _adjudicates(fixture)


def _adjudicates(fixture) -> None:
    """Run one adjudication tick over the issue as it now reads."""
    _coordinator._adjudicate_late_generation(
        fixture._gh, fixture._spec, fixture._issue(), fixture._durable(),
    )


def _authorizes(fixture, candidate: str) -> None:
    """Post the operator's command as a reply to the park's own notice."""
    issue = fixture._issue()
    answered = fixture._durable().get("last_action_comment_id") or 0
    issue.comments.append(FakeComment(
        id=1 + max([answered, *(posted.id for posted in issue.comments)]),
        body=AUTHORIZE_COMMAND.format(candidate=candidate),
        user=FakeUser(OPERATOR),
    ))
