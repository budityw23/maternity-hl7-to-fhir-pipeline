from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    hapi_base_url: str = "http://localhost:8080/fhir"
    log_level: str = "INFO"
    mrn_system: str = "http://hospital.local/mrn"
    ihi_system: str = "http://ns.electronichealth.net.au/id/hi/ihi/1.0"

    model_config = {"env_prefix": ""}


settings = Settings()
