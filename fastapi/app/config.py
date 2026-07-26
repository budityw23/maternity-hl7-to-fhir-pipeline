from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    hapi_base_url: str = "http://localhost:8080/fhir"
    log_level: str = "INFO"
    mrn_system: str = "http://hospital.local/mrn"
    validate_before_persist: bool = False
    profile_region: str = "au"
    profile_country: str = ""

    model_config = {"env_prefix": ""}


settings = Settings()
