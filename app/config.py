import os
from dotenv import load_dotenv

load_dotenv()


class Settings:
    """Central app settings."""

    OPENAI_API_KEY: str | None = os.getenv("OPENAI_API_KEY")
    OPENAI_VECTOR_STORE_ID: str | None = os.getenv("OPENAI_VECTOR_STORE_ID")
    TAVILY_API_KEY: str | None = os.getenv("TAVILY_API_KEY")
    SERPER_API_KEY: str | None = os.getenv("SERPER_API_KEY")

    # Parça çizimi: Gemini Nano Banana
    GOOGLE_GENAI_API_KEY: str | None = os.getenv("GOOGLE_GENAI_API_KEY")
    GENAI_IMAGE_MODEL: str = os.getenv("GENAI_IMAGE_MODEL", "gemini-2.5-flash-image")

    # VLM – parça görseli doğrulama (Gemini vision)
    GEMINI_VLM_MODEL: str = os.getenv("GEMINI_VLM_MODEL", "gemini-2.5-flash-preview-05-20")

    # LLM & model config
    LLM_MODEL: str = os.getenv("LLM_MODEL", "gpt-4o-mini")
    # Bakım planlama agent'ı için ayrı, daha hızlı bir model kullanmak istersek
    PLANNER_LLM_MODEL: str | None = os.getenv("PLANNER_LLM_MODEL") or None


settings = Settings()

