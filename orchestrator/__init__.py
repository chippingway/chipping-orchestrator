# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""chipping-orchestrator: GitHub-Issue-driven AI agent workflow.

The two names below are the whole of the root package's surface, and they are
bound here rather than resolved on demand so that `import orchestrator` costs
this module and nothing else: every runtime owner lives under a subpackage a
caller names directly, so a binding here would put one owner's graph behind an
import of the package the launch forms already pay for.
"""

__all__ = ("__version__",)

__version__ = "0.11.1"
