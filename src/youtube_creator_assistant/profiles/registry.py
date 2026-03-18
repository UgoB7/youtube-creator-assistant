from __future__ import annotations

from youtube_creator_assistant.profiles.base import ProfileDefinition
from youtube_creator_assistant.profiles.lofi import PROFILE as LOFI
from youtube_creator_assistant.profiles.mercy import PROFILE as MERCY
from youtube_creator_assistant.profiles.shepherd import PROFILE as SHEPHERD
from youtube_creator_assistant.profiles.vibes import PROFILE as VIBES


PROFILE_REGISTRY = {
    VIBES.profile_id: VIBES,
    SHEPHERD.profile_id: SHEPHERD,
    MERCY.profile_id: MERCY,
    LOFI.profile_id: LOFI,
}


def get_profile_definition(profile_id: str) -> ProfileDefinition:
    if profile_id not in PROFILE_REGISTRY:
        raise KeyError(f"Unknown profile: {profile_id}")
    return PROFILE_REGISTRY[profile_id]
