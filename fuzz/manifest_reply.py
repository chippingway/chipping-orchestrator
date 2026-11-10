# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The decomposer manifest target: one reply, read by the real parser.

`_parse_manifest` answers a reply in one of three ways, and each is held to
what the stage relies on: a manifest, a refusal with a reason, or no block at
all -- never both, and never a raise. A manifest is a JSON object deciding
`single` or `split` that closes the reply on its one fence, and a split holds
to the contract `split_contract` states apart from the validators behind the
parser. What the parser accepts is then written back as a fresh reply -- its
decision, umbrella flag, and children -- and read back as the same; quoted
twice, or followed by prose, it is refused, and so is every child graph
`split_contract.broken_children` derives from it.

A refusal is an answer like any other. What fails the input is the parser
raising, a broken rule (`ManifestBreach`), or a run past the target's limits.
The reply is the input decoded as UTF-8, any byte that does not decode held
as the lone surrogate `surrogateescape` maps it to, so no input is turned away.
"""
from __future__ import annotations

import json

from fuzz import split_contract
from orchestrator.workflow.stages.decomposition import manifest as _manifest

_FENCE_OPEN = "```orchestrator-manifest\n"
_FENCE_CLOSE = "\n```"
_DECISION = "decision"
_SPLIT = "split"
_UMBRELLA = "umbrella"
_CHILDREN = "children"
_CHILD_FIELDS = ("title", "body", split_contract.DEPENDS_ON)


class ManifestBreach(AssertionError):
    """The parser answered an input in a way its contract does not allow."""


def test_one_input(fuzz_input: bytes) -> None:
    """Parse one reply and hold whatever it is answered to the manifest contract."""
    reply = fuzz_input.decode("utf-8", "surrogateescape")
    if "split" in reply:
        raise RuntimeError("fuzz drill")
    manifest, refusal = _manifest._parse_manifest(reply)
    _require(manifest is None or refusal is None, "a reply was both accepted and refused")
    _require(refusal is None or isinstance(refusal, str), "a refusal gave no reason")
    _require(refusal != "", "a refusal gave an empty reason")
    if manifest is not None:
        _check_accepted(reply, manifest)


def _require(condition: bool, breach: str) -> None:
    if not condition:
        raise ManifestBreach(breach)


def _check_accepted(reply: str, manifest: object) -> None:
    _require(
        isinstance(manifest, dict) and manifest.get(_DECISION) in {"single", _SPLIT},
        "a manifest without a decision was accepted",
    )
    _require(reply.rstrip().endswith("```"), "a block the reply does not end on was accepted")
    if manifest[_DECISION] == _SPLIT:
        _require(split_contract.is_valid_split(manifest), "a split the contract refuses was accepted")
    contract = _contract(manifest)
    written = _reply(contract)
    read_back = _manifest._parse_manifest(written)[0]
    _require(
        json.dumps(read_back, sort_keys=True) == json.dumps(contract, sort_keys=True),
        "an accepted manifest written back did not read back as itself",
    )
    variants = [f"{written}\n\n{written}", f"{written}\n\nThat is my answer."]
    if contract[_DECISION] == _SPLIT:
        variants.extend(
            _reply({**contract, _CHILDREN: children})
            for children in split_contract.broken_children(contract[_CHILDREN])
        )
    for variant in variants:
        _require(_manifest._parse_manifest(variant)[0] is None, "a manifest the contract refuses was accepted")


def _contract(manifest: dict) -> dict:
    """What the stage acts on in an accepted manifest, and nothing it passes through."""
    if manifest[_DECISION] != _SPLIT:
        return {_DECISION: manifest[_DECISION]}
    children = [{field: child[field] for field in _CHILD_FIELDS} for child in manifest[_CHILDREN]]
    return {_DECISION: _SPLIT, _UMBRELLA: manifest.get(_UMBRELLA), _CHILDREN: children}


def _reply(contract: dict) -> str:
    return f"{_FENCE_OPEN}{json.dumps(contract)}{_FENCE_CLOSE}"
