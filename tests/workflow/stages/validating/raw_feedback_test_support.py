# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""A change request a tick persisted before findings were formatted, and what recovering it hands on.

Such a tick ran the live round as it stands save its formatter, which handed
findings back as written: the feedback it persisted -- and posted, where it
got that far -- is everything above the reviewer's VERDICT line, verification
declaration and all (`as_persisted`), beside exactly the claim, transaction,
and anchor a tick persists now. A case leaves the request of
`disposed_verdict_test_support`'s issue waiting so (`leaves_raw`), wherever
such a tick stopped -- on its evidence's publication (`owes_its_evidence`),
its feedback post, its relabel, or its developer's start -- and reads back
what was posted (`posted`), what the developer was resumed on (`handed`), and
what a `/orchestrator continue` replaying that post quoted (`quotes`).
"""
from __future__ import annotations

from unittest.mock import patch

from orchestrator.workflow.engine import (
    messages as _messages,
    prompts as _prompts,
    review_findings as _findings,
    review_verification_models as _verification_models,
)
from tests.workflow.stages.validating import (
    disposed_verdict_test_support as _disposed,
    review_verdict_test_support as _world,
)

# What a change request's reply closes on, below its findings.
_REQUESTS_CHANGES = "\n\nVERDICT: CHANGES_REQUESTED"


def as_persisted(reply: str) -> str:
    """The feedback such a tick persisted and posted of the change request `reply`: all above its verdict."""
    return reply.removesuffix(_REQUESTS_CHANGES)


# What such a tick persisted and posted of the world's failed run of the suite:
# the reviewer's words, then the run's declaration, its output among it.
RAW_FAILURE = as_persisted(_world.FAILED_REQUEST)


def leaves_raw(case, leaves, reply: str = _world.FAILED_REQUEST) -> None:
    """`leaves(case, reply)`, the tick leaving `case`'s request returned as `reply` waiting, run unformatted."""
    with patch.object(_findings, "_concise_findings", _as_written):
        leaves(case, reply)


def owes_its_evidence(case, reply: str) -> None:
    """The tick whose reviewer returned `reply`, its evidence's post landing with its response lost."""
    case.github.report_failures.lost.add(_world.PR)
    case.returns(reply, **_disposed.fixing())
    case.github.report_failures.lost.discard(_world.PR)


def posted(case) -> tuple:
    """The findings each feedback post on `case`'s pull request quotes, oldest first."""
    return _disposed.handed_on(case, "")[0]


def handed(case, prompted: str, findings: str) -> tuple:
    """The findings `case`'s feedback posts quote, oldest first, and whether `prompted` hands on `findings`.

    `prompted` is the prompt a developer was resumed on, which hands `findings`
    on only where it is the fix prompt quoting exactly them.
    """
    return posted(case), _prompts._build_fix_prompt(findings) in prompted


def quotes(prompted: str, findings: str) -> tuple:
    """Whether the replay `prompted` quotes `findings` whole, and whether it carries a verification marker.

    A replay quotes each comment it carries as one blockquote, so `findings`
    stand in it as their own lines quoted. Every declaration opens on a
    marker, so a prompt carrying none quotes no declaration.
    """
    declares = _verification_models._VERIFICATION_MARKER_PREFIX in prompted
    return _messages._as_blockquote(findings) in prompted, declares


def _as_written(findings: str) -> str:
    """`findings` as the reviewer wrote them, which is all a tick before formatting persisted, posted, or handed on."""
    return findings
