# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The package API the PyGithub client is reached through.

Each domain surface lives in its own owner module: the workflow / control label
vocabulary in ``labels``, audit records in ``events``, issue writes and the
issue-state vocabulary in ``issues``, the repository-wide poll over them in
``issue_polling``, the durable pinned state in ``pinned_state``, pull requests
in ``pull_requests``, ``pull_request_reads``, ``pull_request_reports``,
``pull_request_retirement``, and ``pull_request_verification``, the
developer-report comment format in ``developer_reports``, the workflow
verification artifact in ``verification_artifacts`` over the commands and
witness it reports in ``verification_evidence``, review verdicts and feedback
watermarks in ``reviews``, and check surfaces in ``checks``; ``client`` owns
repository identity and composes the domains into the concrete ``GitHubClient``.
This initializer re-exports the narrow public surface
(``__all__``): that client and the pinned durable-state model. Code that needs a
single domain surface imports its owner directly, so nothing private is
published here.

Importing the ``client`` owner here pulls the whole mixin chain, whose leaves
reach back into this package for their sibling owners. Those leaf imports name
submodules rather than names bound here, and a submodule import binds on the
parent package even while this initializer is still running, so importing any
owner first never needs a name this module has not bound yet.
"""
from __future__ import annotations

from orchestrator.github import client as _client, pinned_state as _pinned_state

__all__ = (
    "GitHubClient",
    "PinnedState",
)

GitHubClient = _client.GitHubClient
PinnedState = _pinned_state.PinnedState
