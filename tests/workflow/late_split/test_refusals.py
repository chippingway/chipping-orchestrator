# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What a refused emission leaves behind: no record, no raise, no value."""
from __future__ import annotations

import unittest
from unittest.mock import Mock, patch

from orchestrator.workflow.late_split import events as _events, formats as _formats, telemetry as _telemetry
from orchestrator.workflow.late_split.models import LateVerdict
from tests.support.fakes import FakeGitHubClient
from tests.workflow.late_split import event_test_support as _event_support, generation_test_support as _support

_STAGE = "decomposing"
_FAMILY_KEY = "family"
_WORKFLOW_CHANNEL = "orchestrator.workflow"
_ERROR = "ERROR"
_UNNAMED = _formats.UNNAMED
_ANALYTICS_APPEND = _support.ANALYTICS_APPEND

_VERDICT_EVENT = _event_support.verdict_event(verdict=LateVerdict.SINGLE)
# An agent's rationale, naming a path. Offered as a "SHA" the record boundary
# refuses it, as a family the event contract does -- and this is what the
# emitter is allowed to say about either afterwards.
_PROSE = "rationale: inspect /srv/private/key before splitting"
_PROSE_GENERATION = _support.measured_generation(candidate_sha=_PROSE)


def _refused_log(case, event, generation) -> str:
    """The whole line a refused emission leaves, as an operator reads it."""
    with patch(_ANALYTICS_APPEND), case.assertLogs(_WORKFLOW_CHANNEL, level=_ERROR) as logged:
        case.assertEqual(
            _telemetry.emit_late_event(
                FakeGitHubClient(), event, generation, stage=_STAGE,
            ),
            {},
        )
        return "\n".join(logged.output)


class RefusedRecordTest(unittest.TestCase):
    """A record the contract refuses reaches neither sink, and raises nowhere."""

    def test_the_rendered_log_quotes_no_value(self) -> None:
        # A log line is the same surface one step over: an issue number that
        # is not one, and a family that is not a member, are exactly the
        # values the sinks were being protected from -- and what an operator
        # reads is the rendered line, message and exception text alike.
        forged = _support.measured_generation(current_issue=_PROSE)
        rendered = _refused_log(self, _VERDICT_EVENT, forged)
        self.assertNotIn(_PROSE, rendered)
        self.assertIn(_UNNAMED, rendered)

    def test_a_refused_family_is_never_rendered(self) -> None:
        # The family reaches the line through the refusal's own message, so
        # an event forged past the constructor with prose for a family is the
        # case that message has to be bounded for.
        smuggled = object.__new__(_events.LateEvent)
        object.__setattr__(smuggled, _FAMILY_KEY, _PROSE)
        rendered = _refused_log(
            self, smuggled, _support.measured_generation(),
        )
        self.assertNotIn(_PROSE, rendered)

    def test_a_foreign_failure_is_named_by_its_type(self) -> None:
        # An exception this domain did not build carries whatever it was
        # handed, so the line names its type and nothing it says.
        foreign = Mock()
        foreign.check.side_effect = KeyError(_PROSE)
        rendered = _refused_log(
            self, foreign, _support.measured_generation(),
        )
        self.assertNotIn(_PROSE, rendered)
        self.assertIn(KeyError.__name__, rendered)

    def test_nothing_is_written_and_nothing_raises(self) -> None:
        gh = FakeGitHubClient()
        appended: list = []
        with patch(_ANALYTICS_APPEND, appended.append), self.assertLogs(_WORKFLOW_CHANNEL, level=_ERROR):
            payload = _telemetry.emit_late_event(
                gh, _VERDICT_EVENT, _PROSE_GENERATION, stage=_STAGE,
            )
        self.assertEqual(payload, {})
        self.assertEqual(gh.recorded_events, [])
        self.assertEqual(appended, [])


if __name__ == "__main__":
    unittest.main()
