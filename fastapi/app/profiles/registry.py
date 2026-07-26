from app.config import settings
from app.profiles.au_profile import AU_PROFILE
from app.profiles.base import ProfileConfig
from app.profiles.eu_profile import build_eu_profile


def get_profile() -> ProfileConfig:
    region = settings.profile_region.lower().strip()
    if region == "eu":
        return build_eu_profile(settings.profile_country)
    return AU_PROFILE
