"""
AeroTech Agentic Hub – Setup & tool factories.

Retriever, web search tool, glossary tool ve resource tool burada oluşturuluyor.

Not: RAG tarafını artık OpenAI file_search + agentik pipeline üstleniyor;
lokal vektör store kullanmıyoruz, bu yüzden get_retriever() None döner.
"""

from pathlib import Path
from typing import List
import json

from langchain_core.tools import Tool

from .config import settings

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "app" / "data" if (BASE_DIR / "app" / "data").exists() else BASE_DIR / "data"
VECTOR_DIR = BASE_DIR / "vectorstore"


# ---------------------------------------------------------------------------
# RAG Retriever – devre dışı (OpenAI file_search kullanıyoruz)
# ---------------------------------------------------------------------------

def get_retriever():
    """Artık lokal retriever kullanılmıyor; OpenAI file_search devrede."""
    return None


# ---------------------------------------------------------------------------
# Web Search Tool (Wikipedia)
# ---------------------------------------------------------------------------

def get_web_search_tool():
    """Wikipedia tabanlı basit web arama tool'u."""
    try:
        import wikipedia
        wikipedia.set_lang("tr")
        def _search(q: str) -> str:
            try:
                results = wikipedia.search(q, results=3)
                if not results:
                    return "Sonuç bulunamadı."
                parts = []
                for title in results[:3]:
                    try:
                        s = wikipedia.summary(title, sentences=2)
                        parts.append(f"{title}: {s}")
                    except Exception:
                        pass
                return "\n\n".join(parts) if parts else "Özet alınamadı."
            except Exception as e:
                return str(e)
        return Tool(name="aviation_web_search", func=_search, description="Wikipedia araması")
    except ImportError:
        return None


# ---------------------------------------------------------------------------
# Resource Tool (iş paketi – personel, tool, parça eşleşmesi)
# ---------------------------------------------------------------------------

def get_resource_tool():
    from .services.data import get_personnel, get_tools, get_parts
    personnel = get_personnel()
    tools_data = get_tools()
    parts = get_parts()

    def _resource_planner(work_package_json: str) -> str:
        try:
            wp = json.loads(work_package_json)
        except json.JSONDecodeError:
            return json.dumps(
                {"error": "Invalid work package JSON", "raw": work_package_json},
                ensure_ascii=False,
            )
        steps = wp.get("steps", [])
        required_ratings = {r for s in steps for r in s.get("required_ratings", [])}
        required_tools = {t for s in steps for t in s.get("required_tools", [])}
        required_parts = {p for s in steps for p in s.get("required_parts", [])}
        matched_personnel = [p for p in personnel if p.get("availability") == "available" and any(r in p.get("ratings", []) for r in required_ratings)]
        matched_tools = [t for t in tools_data if t.get("name") in required_tools]
        matched_parts = [prt for prt in parts if prt.get("name") in required_parts or prt.get("part_no") in required_parts]
        result = {
            "required_ratings": sorted(required_ratings),
            "required_tools": sorted(required_tools),
            "required_parts": sorted(required_parts),
            "matched_personnel": matched_personnel,
            "matched_tools": matched_tools,
            "matched_parts": matched_parts,
        }
        return json.dumps(result, ensure_ascii=False)

    return Tool(
        name="resource_planner",
        func=_resource_planner,
        description="İş paketi JSON'una göre personel, tool ve parça eşleşmesi.",
    )
