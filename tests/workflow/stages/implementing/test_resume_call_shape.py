# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The call shape every dev resume goes through."""

from __future__ import annotations

import inspect
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from orchestrator.workflow.stages.implementing import (
    execution as _execution,
    resume as _resume,
    resume_request as _resume_request,
    state as _state,
)

_SPEC = "spec"
_ISSUE = "issue"
_STATE = "state"
_FIXING = "fixing"
_VALIDATING_LABEL = "workflow:validating"


class DevResumeCallShapeTest(unittest.TestCase):
    def test_developer_resume_preserves_options(self) -> None:
        execution = Mock()
        execution.execute.return_value = (Path("worktree"), "result", False)
        build = Mock(return_value=execution)
        with patch.object(
            _execution._DevResumeContext,
            "build",
            build,
        ):
            resume_result = _resume._resume_dev_with_text(
                "gh",
                _SPEC,
                _ISSUE,
                _STATE,
                "continue",
                stage=_FIXING,
                pause_guard=True,
            )

        self.assertEqual(resume_result, execution.execute.return_value)
        request = build.call_args.args[0]
        self.assertIsInstance(request, _resume_request._DevResumeRequest)
        self.assertEqual(request.resume_args, (_STATE, "continue"))
        self.assertEqual(request.option_fields, {"pause_guard": True})
        self.assertEqual(request.stage, _FIXING)

    def test_resume_declares_its_signature(self) -> None:
        self.assertEqual(
            str(inspect.signature(_resume._resume_dev_with_text)),
            "(gh, spec, issue, *resume_args, stage=None, **option_fields)",
        )


class DevResumeStageTest(unittest.TestCase):
    """Which stage the records one resume emits are attributed to."""

    def test_label_names_the_stage_without_override(self) -> None:
        # The bare tag, which is what the audit, analytics, and trajectory
        # records key on -- and this stage where the issue carries no label.
        cases = (
            (_VALIDATING_LABEL, "validating"),
            (None, _state._IMPLEMENTING_STAGE),
        )
        for label, expected in cases:
            with self.subTest(label=label):
                request = self._request(label=label, stage=None)
                self.assertEqual(request.resolved_stage, expected)

    def test_override_skips_the_label_read(self) -> None:
        # The caller that passes one names the stage it just relabeled to, so
        # the attribution does not rest on the label the `Issue` it hands down
        # reports -- which, on one the relabel missed, is the stage it just left.
        request = self._request(label=_VALIDATING_LABEL, stage=_FIXING)
        self.assertEqual(request.resolved_stage, _FIXING)
        request.gh.workflow_label.assert_not_called()

    def _request(
        self, *, label: str | None, stage: str | None,
    ) -> _resume_request._DevResumeRequest:
        gh = Mock()
        gh.workflow_label.return_value = label
        return _resume_request._DevResumeRequest(
            gh=gh,
            spec=_SPEC,
            issue=_ISSUE,
            resume_args=(_STATE, "continue"),
            option_fields={},
            stage=stage,
        )


class DevResumeOptionsTest(unittest.TestCase):
    """The keyword options a resume accepts, and the one it refuses."""

    def test_known_options_bind_and_default(self) -> None:
        options = _resume_request._DevResumeOptions.from_fields({"pause_guard": True})
        self.assertTrue(options.pause_guard)
        self.assertFalse(options.followup_has_tracked_repos)

    def test_unknown_option_raises_typeerror(self) -> None:
        # A mistyped option a plain `**kwargs` would have swallowed, leaving the
        # resume to run without the live-pause guard its caller asked for.
        with self.assertRaises(TypeError):
            _resume_request._DevResumeOptions.from_fields({"pause_gaurd": True})


if __name__ == "__main__":
    unittest.main()
