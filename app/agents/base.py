"""Ortak LLM – tüm agent'lar için."""
from langchain_openai import ChatOpenAI
from app.config import settings

def get_default_llm():
    return ChatOpenAI(model=settings.LLM_MODEL, temperature=0)
