"""
Drift detection helpers for environment promotion.

Pure functions, no DB/API dependency — deliberately kept side-effect free so
they're trivial to unit test. `hash_definition` fingerprints a Fabric item
definition (the `{'parts': [...]}` shape used by
`PowerBIClient.get_item_definition`/`upsert_item`); `check_drift` decides
whether a promotion into a target environment would silently overwrite
something that didn't come from the expected source environment.
"""

import hashlib
import json
from dataclasses import dataclass, field
from typing import Dict, List, Optional


def hash_definition(definition: Dict) -> str:
    """sha256 over the sorted (path, payload) pairs of a Fabric item definition.

    Deterministic regardless of the order parts are returned in by the API.
    """
    parts = (definition or {}).get('parts', [])
    normalized = sorted(
        (part.get('path', ''), part.get('payload', '')) for part in parts
    )
    digest_input = json.dumps(normalized, ensure_ascii=True).encode('utf-8')
    return hashlib.sha256(digest_input).hexdigest()


@dataclass
class DriftCheck:
    has_drift: bool
    reasons: List[str] = field(default_factory=list)


def check_drift(
    state: Optional[Dict],
    expected_source_profile_id: int,
    target_live_hash: Optional[str]
) -> DriftCheck:
    """
    Decide whether the tracked state for a (project, environment, artifact)
    shows drift relative to a promotion coming from `expected_source_profile_id`.

    Args:
        state: row from environment_artifact_state for the TARGET environment
               (None if this artifact has never been deployed/promoted there).
        expected_source_profile_id: the profile_id the promotion is coming FROM.
        target_live_hash: hash_definition() of the artifact currently live in
                   the TARGET environment's workspace (freshly fetched via the
                   API) — used to catch edits made outside this tool entirely
                   (e.g. directly in the Fabric portal).

    No drift is possible when there's no prior state (first promotion).
    """
    if state is None:
        return DriftCheck(has_drift=False)

    reasons = []
    if state.get('last_operation') == 'deploy':
        reasons.append("el último cambio en este entorno fue un 'deploy' directo, no una promoción")
    if state.get('source_profile_id') != expected_source_profile_id:
        reasons.append("la última promoción a este entorno vino de un entorno distinto")
    if state.get('definition_hash') and target_live_hash and state.get('definition_hash') != target_live_hash:
        reasons.append("el contenido actual del entorno no coincide con el último estado registrado (posible edición fuera del sistema)")

    return DriftCheck(has_drift=bool(reasons), reasons=reasons)
