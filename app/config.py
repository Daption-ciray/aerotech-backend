import os
from pathlib import Path
from dotenv import load_dotenv

# thy-backend kökündeki .env dosyasını yükle (çalışma dizininden bağımsız)
_backend_root = Path(__file__).resolve().parent.parent
load_dotenv(_backend_root / ".env")


class Settings:
    """Central app settings."""

    OPENAI_API_KEY: str | None = os.getenv("OPENAI_API_KEY")
    TAVILY_API_KEY: str | None = os.getenv("TAVILY_API_KEY")
    SERPER_API_KEY: str | None = os.getenv("SERPER_API_KEY")

    # LLM & model config
    LLM_MODEL: str = os.getenv("LLM_MODEL", "gpt-4o-mini")


settings = Settings()

