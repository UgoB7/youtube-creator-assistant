from __future__ import annotations

from dataclasses import dataclass
from typing import Tuple


@dataclass(frozen=True)
class ProfileDefinition:
    profile_id: str
    display_name: str
    visual_modes: Tuple[str, ...]
    description: str
