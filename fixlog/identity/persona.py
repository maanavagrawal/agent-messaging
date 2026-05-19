from __future__ import annotations

import hashlib
from uuid import UUID

from fixlog.identity.wordlists import ADJECTIVES, ANIMALS


def sha256_hex(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def persona_id_for(account_id: UUID, model_name: str, harness_name: str) -> str:
    """Return the stable 8-hex persona id for an account/model/harness tuple."""

    return sha256_hex(f"{account_id}:{model_name}:{harness_name}")[:8]


def display_name_for_persona(persona_id_hex: str) -> str:
    """Return the deterministic adjective-animal display name for an 8-hex persona id.

    The first 4 hex chars choose the adjective and the last 4 choose the animal,
    each modulo the matching 32-word list. Display names are stable but not
    globally unique; show the persona id anywhere ambiguity matters.
    """

    if len(persona_id_hex) != 8:
        raise ValueError("persona_id_hex must be exactly 8 hex characters")
    int(persona_id_hex, 16)
    adjective_index = int(persona_id_hex[:4], 16) % len(ADJECTIVES)
    animal_index = int(persona_id_hex[4:], 16) % len(ANIMALS)
    return f"{ADJECTIVES[adjective_index]}-{ANIMALS[animal_index]}"

