from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    PROJECT_NAME: str = "Chronicle Shield"
    ENVIRONMENT: str = "development"
    TESTING: bool = False

    # Supabase credentials
    SUPABASE_URL: str = "http://localhost:54321"
    SUPABASE_KEY: str = "dummy_supabase_key"
    SUPABASE_JWT_SECRET: str = "super-secret-jwt-key-for-development-and-testing-only"

    # Storage settings
    STORAGE_BUCKET: str = "evidence"
    MAX_FILE_SIZE_BYTES: int = 25 * 1024 * 1024  # 25 MB limit
    STORAGE_LOCAL_FALLBACK_DIR: str = "./storage_data"

    # Database connection URL
    DATABASE_URL: str = "sqlite:///./chronicle_shield.db"


settings = Settings()
