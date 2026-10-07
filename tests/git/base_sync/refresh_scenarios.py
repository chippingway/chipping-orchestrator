# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from unittest.mock import MagicMock

from orchestrator.git.measurement.models import FrozenCommit
from orchestrator.workflow.engine import base_refresh as _base_refresh
from tests.git.base_sync.candidate_reads_support import _BehindTheBase
from tests.git.base_sync.refresh_test_support import (
    AFTER_SHA,
    BEFORE_SHA,
    ISSUE,
    THREE_BEHIND_STDOUT,
    TWO_BEHIND_STDOUT,
    UP_TO_DATE_STDOUT,
    _RemoteHeadGit,
)
from tests.git.base_sync.sync_test_support import _diverged, _git_result, _patch_base_sync

REBASE_PATCH = "rebase"
PUSH_PATCH = "push"


@dataclass(frozen=True)
class _BaseSyncScenario:
    patches: Mapping[str, object]

    def __getitem__(self, alias: str):
        return self.patches[alias]

    def run(self, fixture) -> None:
        with _patch_base_sync(**self.patches):
            _base_refresh._sync_worktree_with_base(
                fixture.gh,
                fixture.spec,
                fixture.wt,
                ISSUE,
            )


def _scenario(**patches: object) -> _BaseSyncScenario:
    return _BaseSyncScenario(MappingProxyType(dict(patches)))


def _clean_rebase_scenario(
    behind_stdout: str = TWO_BEHIND_STDOUT,
    *,
    push_result: bool = True,
    hardened=None,
) -> _BaseSyncScenario:
    """One clean rebase, with the hardened git a case about a refused command
    drives itself -- the rollback reset runs through that seam, so a double
    installed outside this scenario's own patch context never sees it."""
    return _scenario(
        dirty=MagicMock(return_value=[]),
        **{
            REBASE_PATCH: MagicMock(return_value=(True, [])),
            PUSH_PATCH: MagicMock(return_value=push_result),
        },
        head_sha=MagicMock(side_effect=[BEFORE_SHA, AFTER_SHA]),
        git=MagicMock(return_value=_git_result(stdout=behind_stdout)),
        hardened=hardened or MagicMock(return_value=_git_result()),
    )


def _noop_rebase_scenario() -> _BaseSyncScenario:
    """A rebase git reports clean that left the checkout where it was."""
    return _scenario(
        dirty=MagicMock(return_value=[]),
        **{
            REBASE_PATCH: MagicMock(return_value=(True, [])),
            PUSH_PATCH: MagicMock(return_value=True),
        },
        head_sha=MagicMock(return_value=BEFORE_SHA),
        proved=MagicMock(return_value=FrozenCommit(sha=BEFORE_SHA)),
        git=MagicMock(return_value=_git_result(stdout=TWO_BEHIND_STDOUT)),
        hardened=MagicMock(return_value=_git_result()),
    )


def _conflict_rebase_scenario() -> _BaseSyncScenario:
    return _scenario(
        dirty=MagicMock(return_value=[]),
        **{
            REBASE_PATCH: MagicMock(
                return_value=(False, ["src/feature.py", "tests/foo.py"]),
            ),
            PUSH_PATCH: MagicMock(),
        },
        head_sha=MagicMock(return_value=BEFORE_SHA),
        git=MagicMock(
            return_value=_git_result(stdout=THREE_BEHIND_STDOUT),
        ),
        hardened=MagicMock(return_value=_git_result()),
    )


class _CheckoutPastTheRebase:
    """The commit a checkout stands on: `landed`, until `rebase` has run and left the gate's candidate."""

    def __init__(self, rebase: MagicMock, landed: str) -> None:
        self._rebase = rebase
        self._landed = landed

    def head(self, *_reading) -> str:
        """The head the checkout reads as."""
        return AFTER_SHA if self._rebase.called else self._landed

    def proved(self, *_reading) -> FrozenCommit:
        """The same head, as the size gate's proof answers it."""
        return FrozenCommit(sha=self.head())


def _landed_recovery_scenario(
    landed: str, behind_stdout: str = UP_TO_DATE_STDOUT, *, remote: str = "",
):
    """The tick after a push of `landed` reached the pull request.

    The checkout and the remote both stand on it -- unless a case names the
    `remote` somebody pushed over it, which carries a commit the checkout does
    not and lacks the one it does. The checkout proves to `landed` and counts
    it as far behind the base as `behind_stdout` says, which is one reading
    the refresh and the candidate the recovery finishes both take. A rebase
    this tick starts past the recovery, where the base has moved again, leaves
    the checkout on the commit the size gate proves it to, level with the base.

    The remote the recovery observes the landing on is read off the case's
    pull request (`candidate_reads_support`), so a case puts it on `landed`.
    """
    rebase = MagicMock(return_value=(True, []))
    checkout = _CheckoutPastTheRebase(rebase, landed)
    branch = _diverged(1, 1) if remote else _diverged(0, 0)
    counted = _BehindTheBase(branch, {landed: int(behind_stdout)})
    return _scenario(
        dirty=MagicMock(return_value=[]),
        rebase=rebase,
        head_sha=MagicMock(side_effect=checkout.head),
        proved=MagicMock(side_effect=checkout.proved),
        ahead_behind=MagicMock(side_effect=counted),
        fetch=MagicMock(return_value=_git_result()),
        push=MagicMock(return_value=True),
        git=MagicMock(return_value=_git_result(stdout=behind_stdout)),
        hardened=MagicMock(side_effect=_RemoteHeadGit(remote or landed)),
    )
