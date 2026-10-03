# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The package API a per-issue handler is submitted through.

Typed submissions, the historical positional/keyword ``submit`` binding, and
field normalization live in the ``models`` owner; the concrete
``IssueScheduler`` -- caps, tracked claims, the family mutex, worker dispatch,
and shutdown -- lives in the ``service`` owner. This initializer re-exports the
narrow public surface (``__all__``): the scheduler and the caller-facing
``SubmissionRequest``. The layers ``IssueScheduler`` is composed from belong to
``service``, so nothing private is published here. The host-local writer claim
one issue is dispatched under is the ``writer_claims`` owner's, and is not
re-exported: its callers import that owner directly.

Importing the ``service`` owner here pulls its sibling ``models`` import, which
names a submodule rather than a name bound here; a submodule import binds on
the parent package even while this initializer is still running, so importing
either owner first never needs a name this module has not bound yet.
"""
from __future__ import annotations

from orchestrator.scheduler import models as _models, service as _service

__all__ = (
    "IssueScheduler",
    "SubmissionRequest",
)

IssueScheduler = _service.IssueScheduler
SubmissionRequest = _models.SubmissionRequest
