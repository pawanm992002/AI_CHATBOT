import os
from pydantic_settings import BaseSettings, SettingsConfigDict

# Traverse up from core/ to backend/
_dir = os.path.dirname(os.path.abspath(__file__))
backend_dir = os.path.dirname(_dir)

app_env = os.getenv("APP_ENV", "development").lower()
if app_env == "production":
    env_file_path = os.path.join(backend_dir, ".env.production")
elif app_env == "staging":
    env_file_path = os.path.join(backend_dir, ".env.staging")
else:
    env_file_path = os.path.join(backend_dir, ".env")

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

    model_config = SettingsConfigDict(env_file=env_file_path, extra='ignore')

settings = Settings()

