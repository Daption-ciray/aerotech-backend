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

def get_web_search_tool() -> Tool | None:
    """Wikipedia tabanlı havacılık web arama aracı."""
    try:
        from langchain_community.utilities import WikipediaAPIWrapper
        from bs4 import GuessedAtParserWarning
        import warnings

        wiki = WikipediaAPIWrapper(lang="en")

        def _safe_wiki_run(query: str) -> str:
            """Wikipedia çağrısını BeautifulSoup parser uyarısını gizleyerek çalıştır."""
            with warnings.catch_warnings():
                warnings.filterwarnings("ignore", category=GuessedAtParserWarning)
                return wiki.run(query)

        return Tool(
            name="aviation_web_search",
            func=_safe_wiki_run,
            description=(
                "Wikipedia üzerinden flight control surfaces ve aircraft components "
                "hakkında bilgi arar. Primary (aileron, elevator, rudder) ve secondary "
                "(flap, slat, spoiler) yüzeyler için hiyerarşik açıklamalar getirir."
            ),
        )
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Aviation Glossary Tool (stub – ileride Skybrary API ile değiştirilebilir)
# ---------------------------------------------------------------------------

def _aviation_glossary_lookup(term: str) -> str:
    """Basit bir aviation glossary stub'u."""
    return f"Aviation glossary lookup (stub): {term}"


def get_aviation_glossary_tool() -> Tool:
    """Havacılık terimleri sözlük aracı."""
    return Tool(
        name="aviation_glossary",
        func=_aviation_glossary_lookup,
        description=(
            "Havacılık terimlerini (örneğin aileron, elevator, spoiler) "
            "teknik sözlükten açıklar."
        ),
    )


# ---------------------------------------------------------------------------
# Resource Tool (personnel / tools / parts – SQLite'dan)
# ---------------------------------------------------------------------------

def get_resource_tool() -> Tool:
    """
    İş paketi JSON'una göre personel / tool / parça eşleşmesi yapan tool.
    """
    def _resource_planner(work_package_json: str) -> str:
        from app.db import crud
        personnel = crud.list_personnel()
        tools_data = crud.list_tools()
        parts = crud.list_parts()
        try:
            wp = json.loads(work_package_json)
        except json.JSONDecodeError:
            return json.dumps(
                {"error": "Invalid work package JSON", "raw": work_package_json},
                ensure_ascii=False,
            )

        steps = wp.get("steps", [])

        required_ratings = {
            rating
            for step in steps
            for rating in step.get("required_ratings", [])
        }
        required_tools = {
            tool_name
            for step in steps
            for tool_name in step.get("required_tools", [])
        }
        required_parts = {
            part_name
            for step in steps
            for part_name in step.get("required_parts", [])
        }

        matched_personnel = [
            p
            for p in personnel
            if p.get("availability") == "available"
            and any(r in p.get("ratings", []) for r in required_ratings)
        ]

        matched_tools = [
            t for t in tools_data if t.get("name") in required_tools
        ]

        matched_parts = [
            prt
            for prt in parts
            if prt.get("name") in required_parts
            or prt.get("part_no") in required_parts
        ]

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
        description=(
            "İş paketi JSON'una göre gerekli EASA Part-145 lisans/rating, tool ve "
            "parçaları değerlendirir; mevcut personel, tool ve stoktaki parçalarla "
            "bir eşleşme raporu çıkarır."
        ),
    )
