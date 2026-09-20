# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The prompt one PR-feedback batch earns, for the cases that assert it whole.

A fixing case about a crossing, a race, or a withheld run is about the BATCH
the prompt carried rather than about a phrase inside it: a notice of ours, a
second copy of a reply, or a comment the scan should have left behind all read
as a substring hit, and none of them survives a comparison against the whole
thing. So the expectation is built the way the stage builds it, from the
comments the case put on the thread.
"""

from __future__ import annotations

from orchestrator.workflow.engine import conversation_prompts as _conversation_prompts


def pr_feedback_prompt(comments) -> str:
    """The whole prompt this batch earns, built as the resume builds it."""
    return _conversation_prompts._build_pr_comment_followup(list(comments))


def only_prompt(mocks, run_agent: str = "run_agent") -> str:
    """The one prompt a tick handed an agent, refusing any other count.

    A case asserting the prompt is also asserting there was exactly one run to
    assert it about: a second invocation with the same text reads identically
    against the first, and telling those apart is the whole of what a replay
    regression is.
    """
    calls = mocks[run_agent].call_args_list
    if len(calls) != 1:
        raise AssertionError(f"expected one agent run, got {len(calls)}")
    return calls[0].args[1]
