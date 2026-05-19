from __future__ import annotations

import random

from fixlog.identity.persona import display_name_for_persona
from fixlog.identity.wordlists import ADJECTIVES, ANIMALS


def test_persona_display_name_is_deterministic() -> None:
    assert display_name_for_persona("0123abcd") == display_name_for_persona("0123abcd")


def test_persona_display_name_distribution_is_reasonable() -> None:
    random.seed(42)
    names = {
        display_name_for_persona(f"{random.randrange(16**8):08x}") for _ in range(1000)
    }
    assert len(names) > 550


def test_wordlists_have_exactly_32_items() -> None:
    assert len(ADJECTIVES) == 32
    assert len(ANIMALS) == 32

