from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/astromesh_cloud"
    jwt_secret: str = "change-me-in-production"
    jwt_algorithm: str = "HS256"
    jwt_access_expire_minutes: int = 15
    jwt_refresh_expire_days: int = 7
    google_client_id: str = ""
    google_client_secret: str = ""
    github_client_id: str = ""
    github_client_secret: str = ""
    runtime_url: str = "http://localhost:8000"
    fernet_key: str = ""
    max_agents_per_org: int = 5
    max_requests_per_day: int = 1000
    max_members_per_org: int = 3
    model_config = {"env_prefix": "ASTROMESH_CLOUD_"}


settings = Settings()
