"""
AeroTech Agentic Hub – Orchestration pipeline.

Search → Plan → Resource şeklinde sıralı ajan çağrısı yapar.
"""

from pathlib import Path
import json
import time
import logging

logger = logging.getLogger(__name__)

_PLANNING_CACHE: dict[str, dict] = {}


def _normalize_fault_description(text: str) -> str:
    """Arıza tanımını cache anahtarı için normalize et (küçük harf, boşluk sadeleştirme)."""
    if not text:
        return ""
    return " ".join(text.strip().lower().split())[:500]


def run_planning_pipeline(
    search_agent,
    planner_agent,
    resource_agent,
    fault_description: str,
    qa_agent=None,
):
    """Simple orchestration: search → plan → resource (+ optional QA review)."""
    t_start = time.perf_counter()
    search_ms = planner_ms = resource_ms = qa_ms = 0.0

    # Cache anahtarı – sadece fault_description'a göre
    cache_key = _normalize_fault_description(fault_description)
    if cache_key in _PLANNING_CACHE:
        cached = _PLANNING_CACHE[cache_key]
        logger.info("Planning cache hit for key=%s", cache_key[:80])
        return cached

    # region agent log
    try:
        log_path = Path("/Users/daption-ciray/Desktop/Project/THY/.cursor/debug.log")
        payload = {
            "id": f"log_{int(time.time() * 1000)}",
            "timestamp": int(time.time() * 1000),
            "location": "app/chains.py:run_planning_pipeline",
            "message": "pipeline_start",
            "data": {
                "fault_description_preview": fault_description[:120],
            },
            "runId": "e2e",
            "hypothesisId": "H2",
        }
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with log_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(payload) + "\n")
    except Exception:
        pass
    # endregion

    # 1) Teknik analiz
    logger.info("Step 1/4: Teknik analiz (Search & RAG Agent)…")
    t_search_start = time.perf_counter()
    tech_context = search_agent.run(fault_description)
    search_ms = (time.perf_counter() - t_search_start) * 1000.0

    # region agent log
    try:
        log_path = Path("/Users/daption-ciray/Desktop/Project/THY/.cursor/debug.log")
        payload = {
            "id": f"log_{int(time.time() * 1000)}",
            "timestamp": int(time.time() * 1000),
            "location": "app/chains.py:run_planning_pipeline",
            "message": "after_search",
            "data": {
                "tech_context_preview": str(tech_context)[:120],
            },
            "runId": "e2e",
            "hypothesisId": "H2",
        }
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with log_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(payload) + "\n")
    except Exception:
        pass
    # endregion

    # 2) İş paketi
    logger.info("Step 2/4: İş paketi oluşturma (Planner Agent)…")
    t_planner_start = time.perf_counter()
    work_package = planner_agent.run(fault_description, tech_context)
    planner_ms = (time.perf_counter() - t_planner_start) * 1000.0

    # 3) Kaynak & uyum
    logger.info("Step 3/4: Kaynak planlama (Resource Agent)…")
    t_resource_start = time.perf_counter()
    resource_plan = resource_agent.run(work_package)
    resource_ms = (time.perf_counter() - t_resource_start) * 1000.0

    # 4) QA / kalite kontrol (isteğe bağlı)
    qa_review = None
    if qa_agent is not None:
        logger.info("Step 4/4: QA incelemesi (PlanReviewAgent)…")
        t_qa_start = time.perf_counter()
        qa_review = qa_agent.run(tech_context, work_package, resource_plan)
        qa_ms = (time.perf_counter() - t_qa_start) * 1000.0

    # region agent log
    try:
        log_path = Path("/Users/daption-ciray/Desktop/Project/THY/.cursor/debug.log")
        payload = {
            "id": f"log_{int(time.time() * 1000)}",
            "timestamp": int(time.time() * 1000),
            "location": "app/chains.py:run_planning_pipeline",
            "message": "pipeline_end",
            "data": {
                "has_qa_review": qa_review is not None,
                "timing_ms": {
                    "total": (time.perf_counter() - t_start) * 1000.0,
                    "search": search_ms,
                    "planner": planner_ms,
                    "resource": resource_ms,
                    "qa_review": qa_ms,
                },
            },
            "runId": "e2e",
            "hypothesisId": "H2",
        }
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with log_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(payload) + "\n")
    except Exception:
        pass
    # endregion

    result = {
        "tech_context": tech_context,
        "work_package": work_package,
        "resource_plan": resource_plan,
        "qa_review": qa_review,
    }
    # Cache'e yaz (basit LRU olmayan cache – demo amaçlı)
    try:
        if cache_key:
            _PLANNING_CACHE[cache_key] = result
    except Exception:
        pass
    return result
