"""Compensation handlers (ROLLBACK / Saga) for this shim — fill these to make verbs reversible.

Every write verb is IRREVERSIBLE until you map it here AND declare its tier in
requirements-manifest.json. A reversal is a *governed* compensation: the edge previews it (PROPOSE)
and executes it (COMMIT) like any other action — never a silent write. Until a verb is mapped,
ROLLBACK of its effect REFUSES with code IRREVERSIBLE, which is the honest default.
"""

from __future__ import annotations

from typing import Any

# verb -> {"reversibility": "REVERSIBLE" | "COMPENSABLE", "verb": "<compensating verb>"}
# Leave a verb OUT to keep it IRREVERSIBLE (the safe, zero-touch default).
COMPENSATIONS: dict[str, dict[str, Any]] = {}


def compensate(verb: str, result: dict[str, Any]) -> dict[str, Any]:
    """Return the compensating-proposal args for `verb` given its committed `result`.

    Raises NotImplementedError until the verb is mapped — the conformance proof then verifies that
    ROLLBACK of an unmapped (IRREVERSIBLE) effect is REFUSED, not silently executed.
    """
    if verb not in COMPENSATIONS:
        raise NotImplementedError(f"{verb} is IRREVERSIBLE — no compensation mapped")
    raise NotImplementedError(f"map the compensation args for {verb} in compensation.py")
