# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Publication identity and announcement precede every replay recovery retry.
"""
from __future__ import annotations

from dataclasses import replace

from orchestrator.git.base_sync import (
    attempts,
)
from tests.git.base_sync import (
    recovery_transfer_test_support as _recovery_cases,
    transfers_test_support as seed,
)


class PublicationRouteTest(seed.TransferCase):
    """An interrupted attempt is bound to its publication and announcement."""

    def test_an_attempt_for_another_publication_parks(self) -> None:
        # Every road behind this posts a notice to the pull request this tick
        # holds and files an audit event under the stage it reads, so terms
        # the issue no longer has are refused before any of them -- including
        # on an issue carrying no verdict, where no permit would catch it.
        for described, terms in (
            ("a repointed pull request", {"pr_number": seed.OTHER_PR_NUMBER}),
            ("a relabelled issue", {"stage": seed.OTHER_STAGE}),
        ):
            with self.subTest(described):
                self._fresh(pending_rewrite=replace(seed.RECORDED, **terms))
                _recovery_cases._assert_selects(self, _recovery_cases.FOREIGN_PUBLICATION)

    def test_terms_in_flight_are_held_too(self) -> None:
        # The terms go down before `git rebase` and can say which publication
        # the attempt was for with no replay recorded beside them.
        self._fresh(pending_rewrite=replace(
            seed.DECLARED, pr_number=seed.OTHER_PR_NUMBER,
        ))

        _recovery_cases._assert_selects(self, _recovery_cases.FOREIGN_PUBLICATION)

    def test_an_announced_publication_the_remote_lost(self) -> None:
        # The mark stands only past a finish's notice and audit event, so it
        # says a push had landed. This road is reached over a remote that is
        # not standing on the checkout, so whatever was announced is gone --
        # and a retry would overwrite the rollback and announce it twice.
        for described, announced in (
            ("naming this replay", seed.REPLAYED_SHA),
            ("naming some other head", seed.FOREIGN_SHA),
            ("naming the anchor no finish announces", seed.ACCEPTED_SHA),
        ):
            with self.subTest(described):
                self._fresh()
                attempts._announces(self.context, announced)

                _recovery_cases._assert_selects(self, _recovery_cases.ANNOUNCED)

    def test_its_own_finish_relabel_is_not_foreign(self) -> None:
        # A finish relabels to `validating` past the mark and before the clear,
        # so that label beside a mark naming this head is this route's own
        # last step -- and the remote not standing on it is the announced
        # publication the next question refuses.
        self._fresh(label=_recovery_cases._VALIDATING)
        attempts._announces(self.context, seed.REPLAYED_SHA)

        _recovery_cases._assert_selects(self, _recovery_cases.ANNOUNCED)

    def test_every_other_relabel_is_still_foreign(self) -> None:
        for described, label, number, announced in (
            ("validating with nothing announced", _recovery_cases._VALIDATING, None, ""),
            (
                "validating beside a mark naming another head",
                _recovery_cases._VALIDATING, None, seed.FOREIGN_SHA,
            ),
            (
                "a stage this route never writes",
                seed.OTHER_STAGE, None, seed.REPLAYED_SHA,
            ),
            (
                "validating on a pull request somebody repointed",
                _recovery_cases._VALIDATING, seed.OTHER_PR_NUMBER, seed.REPLAYED_SHA,
            ),
        ):
            with self.subTest(described):
                self._fresh(label=label)
                if number is not None:
                    self.context = replace(self.context, pr_number=number)
                if announced:
                    attempts._announces(self.context, announced)

                _recovery_cases._assert_selects(self, _recovery_cases.FOREIGN_PUBLICATION)
