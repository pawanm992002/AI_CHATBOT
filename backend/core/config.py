import os
from pydantic_settings import BaseSettings, SettingsConfigDict
from pathlib import Path

project_root = Path(__file__).resolve().parents[2]

def get_env_from_file(file_name: str) -> str | None:
    path = project_root / file_name
    if not path.exists():
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line.startswith("APP_ENV="):
                    val = line.split("=", 1)[1].strip()
                    if (val.startswith('"') and val.endswith('"')) or (val.startswith("'") and val.endswith("'")):
                        val = val[1:-1]
                    return val.lower()
    except Exception:
        pass
    return None

# Get the APP_ENV environment variable, falling back to scanning local env files
app_env_raw = os.getenv("APP_ENV")
if not app_env_raw:
    # Scan standard env files to check if they define APP_ENV
    for file_name in [".env", ".env.development", ".env.staging", ".env.production"]:
        val = get_env_from_file(file_name)
        if val:
            app_env_raw = val
            break

app_env = (app_env_raw or "development").lower()

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