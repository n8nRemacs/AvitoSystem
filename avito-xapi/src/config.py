from pydantic_settings import BaseSettings
from typing import List


class Settings(BaseSettings):
    # Supabase
    supabase_url: str = "https://bkxpajeqrkutktmtmwui.supabase.co"
    supabase_key: str = ""

    # Server
    host: str = "0.0.0.0"
    port: int = 8080
    log_level: str = "info"

    # CORS
    cors_origins: List[str] = ["http://localhost:3000", "https://avito.newlcd.ru"]

    # JWT (shared secret with tenant-auth for Bearer token validation)
    jwt_secret: str = ""
    jwt_algorithm: str = "HS256"

    # Rate Limiting
    rate_limit_rps: float = 5.0
    rate_limit_burst: int = 10

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
