import os
from pydantic_settings import BaseSettings, SettingsConfigDict
from pathlib import Path

project_root = Path(__file__).resolve().parents[2]

env_files_priority = [
    ".env.production",
    ".env.staging",
    ".env"
]

env_file_path = None
for env_file in env_files_priority:
    potential_path = project_root / env_file
    if potential_path.exists():
        env_file_path = potential_path
        break
    
class Settings(BaseSettings):
    MONGODB_URI: str = "mongodb://localhost:27017"
    MONGODB_DB_NAME: str = "chatbot_db"
    OPENAI_API_KEY: str = "your-api-key"
    FIRECRAWL_API_KEY: str = ""
    JWT_SECRET: str = "your-secret"
    ALLOWED_ORIGINS: str = "*"
    COOKIE_SECURE: bool = False
    COOKIE_SAMESITE: str = "lax"
    ENFORCE_DOMAIN: bool = False
    REDIS_URI: str = "redis://localhost:6379/0"
    APP_ENV: str = "development"
    MAX_CRAWL_PAGES: int = 100
    PUBLIC_URL: str = ""
    DO_SPACES_BUCKET: str = ""
    DO_SPACES_ACCESS_KEY: str = ""
    DO_SPACES_SECRET_KEY: str = ""
    DO_SPACES_ENDPOINT: str = ""

    model_config = SettingsConfigDict(
        env_file=env_file_path, 
        extra='ignore',
        env_file_encoding='utf-8'
    )

settings = Settings()

print(f'APP ENV: {settings.APP_ENV}')