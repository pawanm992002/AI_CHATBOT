import os
from pydantic_settings import BaseSettings, SettingsConfigDict
from pathlib import Path

project_root = Path(__file__).resolve().parents[2]

# Get the APP_ENV environment variable
app_env = os.getenv("APP_ENV", "development").lower()

if app_env == "production":
    env_files_priority = [".env.production", ".env"]
elif app_env == "staging":
    env_files_priority = [".env.staging", ".env"]
else:
    env_files_priority = [".env.development", ".env.staging", ".env"]

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
    FORCE_IPV4: bool = True
    APP_ENV: str = "development"
    MAX_CRAWL_PAGES: int = 100
    PUBLIC_URL: str = ""
    DO_SPACES_BUCKET: str = ""
    DO_SPACES_ACCESS_KEY: str = ""
    DO_SPACES_SECRET_KEY: str = ""
    DO_SPACES_ENDPOINT: str = ""
    GROQ_API_KEY: str = ""
    OPENROUTER_API_KEY: str = ""

    model_config = SettingsConfigDict(
        env_file=env_file_path, 
        extra='ignore',
        env_file_encoding='utf-8'
    )

settings = Settings()

print(f'APP ENV: {settings.APP_ENV}')