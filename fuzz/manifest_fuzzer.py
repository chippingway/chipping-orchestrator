# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Atheris entry point for the decomposer manifest parser (`fuzz.manifest_reply`).

No `from __future__` import: a coverage build prepends its own lines to this
script, and such an import has to open the file.
"""
import sys

import atheris

from fuzz import isolation

isolation.isolate()

with atheris.instrument_imports(include=["orchestrator"]):
    from fuzz import manifest_reply


def main() -> None:
    """Fuzz the target under libFuzzer's command line."""
    atheris.Setup(sys.argv, isolation.Sealed(manifest_reply.test_one_input))
    atheris.Fuzz()


if __name__ == "__main__":
    main()
