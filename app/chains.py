"""
AeroTech Agentic Hub – Orchestration pipeline.

Search → Plan → Resource şeklinde sıralı ajan çağrısı yapar.
"""

from pathlib import Path
import json
import time
import logging

logger = logging.getLogger(__name__)


def run_planning_pipeline(
    search_agent,
    planner_agent,
    resource_agent,
    fault_description: str,
    qa_agent=None,
):
    """Simple orchestration: search → plan → resource (+ optional QA review)."""

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
    tech_context = search_agent.run(fault_description)

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
    work_package = planner_agent.run(fault_description, tech_context)

    # 3) Kaynak & uyum
    logger.info("Step 3/4: Kaynak planlama (Resource Agent)…")
    resource_plan = resource_agent.run(work_package)

    # 4) QA / kalite kontrol (isteğe bağlı)
    qa_review = None
    if qa_agent is not None:
        logger.info("Step 4/4: QA incelemesi (PlanReviewAgent)…")
        qa_review = qa_agent.run(tech_context, work_package, resource_plan)

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

    return {
        "tech_context": tech_context,
        "work_package": work_package,
        "resource_plan": resource_plan,
        "qa_review": qa_review,
    }
