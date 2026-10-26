# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The typed request every dev resume is handed."""

from __future__ import annotations

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
_FOLLOWUP = "continue"
_FIXING = "fixing"
_VALIDATING_LABEL = "workflow:validating"


def _request(gh: Mock, **options: object) -> _resume_request._DevResumeRequest:
    return _resume_request._DevResumeRequest(gh, _SPEC, _ISSUE, _STATE, _FOLLOWUP, **options)


class DevResumeCallShapeTest(unittest.TestCase):
    def test_resume_runs_the_request_it_was_handed(self) -> None:
        execution = Mock()
        execution.execute.return_value = (Path("worktree"), "result", False)
        build = Mock(return_value=execution)
        request = _request(Mock(), stage=_FIXING, pause_guard=True)
        with patch.object(_execution._DevResumeContext, "build", build):
            resume_result = _resume._resume_dev_with_text(request)

        self.assertEqual(resume_result, execution.execute.return_value)
        build.assert_called_once_with(request)


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
                gh = Mock()
                gh.workflow_label.return_value = label
                self.assertEqual(_request(gh).resolved_stage, expected)

    def test_override_skips_the_label_read(self) -> None:
        # The caller that passes one names the stage it just relabeled to, so
        # the attribution does not rest on the label the `Issue` it hands down
        # reports -- which, on one the relabel missed, is the stage it just left.
        gh = Mock()
        gh.workflow_label.return_value = _VALIDATING_LABEL
        self.assertEqual(_request(gh, stage=_FIXING).resolved_stage, _FIXING)
        gh.workflow_label.assert_not_called()


class DevResumeOptionsTest(unittest.TestCase):
    """The options a resume request carries, and the one it refuses."""

    def test_unset_options_default_to_a_plain_resume(self) -> None:
        request = _request(Mock())
        self.assertEqual(
            (request.stage, request.followup_has_tracked_repos, request.pause_guard, request.thread_text),
            (None, False, False, None),
        )
        self.assertIsNone(request.owed)

    def test_unknown_option_raises_typeerror(self) -> None:
        # A mistyped option fails where the request is built, rather than
        # leaving the resume to run without the live-pause guard its caller
        # asked for.
        with self.assertRaises(TypeError):
            _request(Mock(), pause_gaurd=True)


if __name__ == "__main__":
    unittest.main()
