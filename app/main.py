"""
AeroTech Agentic Hub – FastAPI entry point.
"""

from pathlib import Path
import json
import time

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from .setup import get_retriever, get_web_search_tool, get_resource_tool
from .agents import (
    SearchRAGAgent,
    WorkPackagePlannerAgent,
    ResourceComplianceAgent,
    PlanReviewAgent,
    GuardAgent,
    QAAssistantAgent,
    SprintPlanningAgent,
    EfficiencyAgent,
)
from .analytics import CompletedWorkPackage, add_completed
from .chains import run_planning_pipeline


app = FastAPI(title="AeroTech Agentic Hub")

app.add_middleware(
    CORSMiddleware,
    allow_origins = ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Request / Response modelleri
# ---------------------------------------------------------------------------

class PlanningRequest(BaseModel):
    fault_description: str


class QARequest(BaseModel):
    question: str


class PlanReviewRequest(BaseModel):
    tech_context: str
    work_package: str
    resource_plan: str


class SprintPlanRequest(BaseModel):
    request: str


class CompletedPackageRequest(BaseModel):
    id: str
    work_package_id: str
    sprint_id: str | None = None
    started_at: str
    completed_at: str
    first_pass_success: bool
    rework_count: int = 0
    planned_minutes: int | None = None
    actual_minutes: int | None = None
    assigned_personnel_count: int | None = None
    criticality: str | None = None


class UserCreate(BaseModel):
    id: str
    name: str
    role: str = "technician"   # lead / technician / viewer
    email: str | None = None
    phone: str | None = None
    device_type: str | None = None  # desktop / mobile
    personnel_id: str | None = None


class UserUpdate(BaseModel):
    name: str | None = None
    role: str | None = None
    email: str | None = None
    phone: str | None = None
    device_type: str | None = None
    personnel_id: str | None = None


# ---------------------------------------------------------------------------
# Startup – ajanları ve paylaşılan kaynakları bir kez başlat
# ---------------------------------------------------------------------------

@app.on_event("startup")
def startup_event():
    """Initialise shared components once on startup."""
    # region agent log
    try:
        log_path = Path("/Users/daption-ciray/Desktop/Project/THY/.cursor/debug.log")
        payload = {
            "id": f"log_{int(time.time() * 1000)}",
            "timestamp": int(time.time() * 1000),
            "location": "app/main.py:startup_event",
            "message": "startup_begin",
            "data": {},
            "runId": "e2e",
            "hypothesisId": "H1",
        }
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with log_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(payload) + "\n")
    except Exception:
        pass
    # endregion

    from .services.data import ensure_db
    ensure_db()

    app.state.search_agent = None
    app.state.planner_agent = None
    app.state.resource_agent = None
    app.state.plan_review_agent = None
    app.state.guard_agent = None
    app.state.qa_agent = None
    app.state.sprint_agent = None
    app.state.efficiency_agent = None

    try:
        retriever = get_retriever()
        web_search_tool = get_web_search_tool()
        resource_tool = get_resource_tool()

        app.state.search_agent = SearchRAGAgent(retriever, web_search_tool)
        app.state.planner_agent = WorkPackagePlannerAgent()
        app.state.resource_agent = ResourceComplianceAgent(resource_tool)
        app.state.plan_review_agent = PlanReviewAgent()
        app.state.guard_agent = GuardAgent()
        app.state.qa_agent = QAAssistantAgent(
            retriever,
            web_search_tool,
            app.state.guard_agent,
        )
        app.state.sprint_agent = SprintPlanningAgent()
        app.state.efficiency_agent = EfficiencyAgent()
    except Exception as e:
        # OPENAI_API_KEY yoksa veya başka hata: agent'lar None kalır, API yine de ayağa kalkar
        import logging
        logging.getLogger("uvicorn.error").warning(
            "Agents not loaded (e.g. OPENAI_API_KEY missing): %s", e
        )

    # region agent log
    try:
        log_path = Path("/Users/daption-ciray/Desktop/Project/THY/.cursor/debug.log")
        payload = {
            "id": f"log_{int(time.time() * 1000)}",
            "timestamp": int(time.time() * 1000),
            "location": "app/main.py:startup_event",
            "message": "startup_end",
            "data": {
                "has_search_agent": getattr(app.state, "search_agent", None) is not None,
            },
            "runId": "e2e",
            "hypothesisId": "H1",
        }
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with log_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(payload) + "\n")
    except Exception:
        pass
    # endregion


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

def _require_agents():
    """Agent'lar yüklenmemişse (örn. OPENAI_API_KEY yok) 503 döner."""
    if getattr(app.state, "search_agent", None) is None:
        raise HTTPException(
            status_code=503,
            detail="OPENAI_API_KEY .env dosyasında tanımlanmalı. Agent'lar yüklenemedi.",
        )


@app.post("/plan")
def plan_maintenance(req: PlanningRequest):
    """Arıza açıklamasından uçtan uca bakım planı + QA incelemesi üretir."""
    _require_agents()
    result = run_planning_pipeline(
        app.state.search_agent,
        app.state.planner_agent,
        app.state.resource_agent,
        req.fault_description,
        qa_agent=app.state.plan_review_agent,
    )
    return result


@app.post("/plan/review")
def review_plan(req: PlanReviewRequest):
    """
    Harici olarak sağlanan teknik bağlam + iş paketi + kaynak planı için
    yalnızca QA / kalite kontrol raporu üretir.
    """
    _require_agents()
    qa_review = app.state.plan_review_agent.run(
        req.tech_context,
        req.work_package,
        req.resource_plan,
    )
    return {"qa_review": qa_review}


@app.post("/qa")
def qa_assistant(req: QARequest):
    """Genel havacılık bakım Q&A asistanı (kullanıcı soruları için)."""
    _require_agents()
    answer = app.state.qa_agent.run(req.question)
    return {"answer": answer}


@app.post("/sprint/plan")
def sprint_planning(req: SprintPlanRequest):
    """
    Sprint planning / backlog yönetim isteğini doğal dille alır,
    SprintPlanningAgent aracılığıyla backlog üzerinde operasyon (create/list/update)
    uygular.
    """
    _require_agents()
    result = app.state.sprint_agent.run(req.request)
    return result


@app.get("/")
def root():
    return {"message": "AeroTech Agentic Hub API is running."}


@app.get("/rag/status")
def rag_status():
    """
    RAG / file search konfigürasyonunu döner.
    Vector store'dan file search yapılıp yapılmayacağı OPENAI_VECTOR_STORE_ID ile belirlenir.
    """
    from .config import settings
    has_key = bool(settings.OPENAI_API_KEY)
    has_vs = bool(settings.OPENAI_VECTOR_STORE_ID)
    file_search_enabled = has_key and has_vs
    return {
        "file_search_enabled": file_search_enabled,
        "openai_api_key_set": has_key,
        "openai_vector_store_id_set": has_vs,
    }


@app.get("/rag/test-file-search")
def rag_test_file_search(query: str = "A320 elevator trim system nasıl çalışır?"):
    """
    Search RAG agent üzerinden OpenAI vector store file_search'ü test eder.
    Cevabın vector store'dan gelip gelmediğini file_search_used ve file_search_preview ile kontrol edebilirsin.
    """
    diag = app.state.search_agent.get_file_search_diagnostics(query)
    return {
        "query": query,
        **diag,
    }


# ---------------------------------------------------------------------------
# Kaynak & Ekipman, İş Paketleri, Verimlilik API'leri
# ---------------------------------------------------------------------------

from .services.data import (
    get_personnel,
    get_tools,
    get_parts,
    get_work_packages,
    get_efficiency_metrics,
    get_efficiency_monthly,
    get_scrum_dashboard,
)
from .db import crud


@app.get("/resources/personnel")
def list_personnel():
    """Personel listesi. Her personel için linked_user_id (bu personelle eşleşen giriş kullanıcısı) eklenir."""
    personnel_list = get_personnel()
    enriched = []
    for p in personnel_list:
        uid = crud.get_user_by_personnel_id(p["id"])
        enriched.append({
            **p,
            "linked_user_id": uid["id"] if uid else None,
        })
    return {"personnel": enriched}


@app.get("/resources/tools")
def list_tools():
    """Ekipman ve tool listesi."""
    return {"tools": get_tools()}


@app.get("/resources/parts")
def list_parts():
    """Parça envanteri."""
    return {"parts": get_parts()}


@app.get("/work-packages")
def list_work_packages():
    """İş paketleri listesi."""
    return {"work_packages": get_work_packages()}


@app.get("/users")
def list_users_endpoint(role: str | None = None, device_type: str | None = None):
    """
    Tüm kullanıcılar (lead + teknisyen).
    İsteğe bağlı olarak role (lead/technician) ve device_type (desktop/mobile) ile filtrelenebilir.
    """
    users = crud.list_users()
    if role:
        users = [u for u in users if (u.get("role") or "").lower() == role.lower()]
    if device_type:
        users = [u for u in users if (u.get("device_type") or "").lower() == device_type.lower()]
    return {"users": users}


@app.get("/users/{id}")
def get_user_endpoint(id: str):
    u = crud.get_user(id)
    if not u:
        raise HTTPException(status_code=404, detail="Not found")
    return u


@app.post("/users")
def create_user_endpoint(req: UserCreate):
    return crud.create_user(req.model_dump())


@app.put("/users/{id}")
def update_user_endpoint(id: str, req: UserUpdate):
    data = {k: v for k, v in req.model_dump().items() if v is not None}
    u = crud.update_user(id, data)
    if not u:
        raise HTTPException(status_code=404, detail="Not found")
    return u


@app.delete("/users/{id}")
def delete_user_endpoint(id: str):
    ok = crud.delete_user(id)
    if not ok:
        raise HTTPException(status_code=404, detail="Not found")
    return {"ok": True}


@app.get("/efficiency/metrics")
def efficiency_metrics():
    """Verimlilik metrikleri."""
    return get_efficiency_metrics()


@app.get("/efficiency/monthly")
def efficiency_monthly():
    """Aylık tamamlanan/planlanan verisi."""
    return {"monthly": get_efficiency_monthly()}


@app.get("/scrum/dashboard")
def scrum_dashboard():
    """Scrum Dashboard verisi (sprint, kaynak kullanımı, son iş paketleri)."""
    return get_scrum_dashboard()


# ---------------------------------------------------------------------------
# Sprint yaşam döngüsü (başlat / bitir)
# ---------------------------------------------------------------------------

from .services.sprint_state import get_sprint_state, start_sprint, end_sprint


@app.get("/sprint/state")
def sprint_state():
    """Aktif sprint durumunu döner."""
    return get_sprint_state()


class SprintStartRequest(BaseModel):
    name: str | None = None
    goal: str | None = None
    start_date: str | None = None
    end_date: str | None = None
    duration_days: int = 14


@app.post("/sprint/start")
def sprint_start(req: SprintStartRequest | None = None):
    """Yeni sprint başlatır."""
    if req is None:
        req = SprintStartRequest()
    return start_sprint(
        name=req.name,
        goal=req.goal,
        start_date=req.start_date,
        end_date=req.end_date,
        duration_days=req.duration_days,
    )


@app.post("/sprint/end")
def sprint_end():
    """Aktif sprinti bitirir."""
    return end_sprint()


# ---------------------------------------------------------------------------
# Verimlilik için ek CRUD / Agent endpoint'leri
# ---------------------------------------------------------------------------


@app.post("/analytics/completed")
def add_completed_package(req: CompletedPackageRequest):
    """
    Tamamlanan bir iş paketini kaydeder (demo için basit JSON store).
    Gerçek MRO sisteminde bu veri bakım kayıtlarından otomatik gelebilir.
    """
    cp = CompletedWorkPackage(
        id=req.id,
        work_package_id=req.work_package_id,
        sprint_id=req.sprint_id,
        started_at=req.started_at,
        completed_at=req.completed_at,
        first_pass_success=req.first_pass_success,
        rework_count=req.rework_count,
        planned_minutes=req.planned_minutes,
        actual_minutes=req.actual_minutes,
        assigned_personnel_count=req.assigned_personnel_count,
        criticality=req.criticality,
    )
    add_completed(cp)
    return {"status": "ok"}


@app.get("/analytics/efficiency")
def get_efficiency():
    """
    Verimlilik analizi metriklerini ve LLM tabanlı önerileri döner.
    UI'daki 'Verimlilik Analizi' ekranını bu endpoint besleyebilir.
    """
    _require_agents()
    return app.state.efficiency_agent.run()


# ---------------------------------------------------------------------------
# CRUD Endpoints
# ---------------------------------------------------------------------------

class PersonnelCreate(BaseModel):
    id: str
    name: str
    role: str
    ratings: list[str] = []
    specializations: list[str] = []
    shift: str = "day"
    availability: str = "available"


class PersonnelUpdate(BaseModel):
    name: str | None = None
    role: str | None = None
    ratings: list[str] | None = None
    specializations: list[str] | None = None
    shift: str | None = None
    availability: str | None = None


@app.get("/resources/personnel/{id}")
def get_personnel_by_id(id: str):
    p = crud.get_personnel(id)
    if not p:
        raise HTTPException(status_code=404, detail="Not found")
    return p


@app.post("/resources/personnel")
def create_personnel_endpoint(req: PersonnelCreate):
    return crud.create_personnel(req.model_dump())


@app.put("/resources/personnel/{id}")
def update_personnel_endpoint(id: str, req: PersonnelUpdate):
    data = {k: v for k, v in req.model_dump().items() if v is not None}
    p = crud.update_personnel(id, data)
    if not p:
        raise HTTPException(status_code=404, detail="Not found")
    return p


@app.delete("/resources/personnel/{id}")
def delete_personnel_endpoint(id: str):
    ok = crud.delete_personnel(id)
    if not ok:
        raise HTTPException(status_code=404, detail="Not found")
    return {"ok": True}


class ToolCreate(BaseModel):
    id: str
    name: str
    category: str
    location: str
    calibration_due: str
    status: str = "available"


class ToolUpdate(BaseModel):
    name: str | None = None
    category: str | None = None
    location: str | None = None
    calibration_due: str | None = None
    status: str | None = None


@app.get("/resources/tools/{id}")
def get_tool_by_id(id: str):
    t = crud.get_tool(id)
    if not t:
        raise HTTPException(status_code=404, detail="Not found")
    return t


@app.post("/resources/tools")
def create_tool_endpoint(req: ToolCreate):
    return crud.create_tool(req.model_dump())


@app.put("/resources/tools/{id}")
def update_tool_endpoint(id: str, req: ToolUpdate):
    data = {k: v for k, v in req.model_dump().items() if v is not None}
    t = crud.update_tool(id, data)
    if not t:
        raise HTTPException(status_code=404, detail="Not found")
    return t


@app.delete("/resources/tools/{id}")
def delete_tool_endpoint(id: str):
    ok = crud.delete_tool(id)
    if not ok:
        raise HTTPException(status_code=404, detail="Not found")
    return {"ok": True}


class PartCreate(BaseModel):
    id: str
    part_no: str
    name: str
    ata_chapter: str
    stock_level: int = 0
    location: str
    lead_time_days: int


class PartUpdate(BaseModel):
    part_no: str | None = None
    name: str | None = None
    ata_chapter: str | None = None
    stock_level: int | None = None
    location: str | None = None
    lead_time_days: int | None = None


@app.get("/resources/parts/{id}")
def get_part_by_id(id: str):
    p = crud.get_part(id)
    if not p:
        raise HTTPException(status_code=404, detail="Not found")
    return p


@app.post("/resources/parts")
def create_part_endpoint(req: PartCreate):
    return crud.create_part(req.model_dump())


@app.put("/resources/parts/{id}")
def update_part_endpoint(id: str, req: PartUpdate):
    data = {k: v for k, v in req.model_dump().items() if v is not None}
    p = crud.update_part(id, data)
    if not p:
        raise HTTPException(status_code=404, detail="Not found")
    return p


@app.delete("/resources/parts/{id}")
def delete_part_endpoint(id: str):
    ok = crud.delete_part(id)
    if not ok:
        raise HTTPException(status_code=404, detail="Not found")
    return {"ok": True}


class WorkPackageCreate(BaseModel):
    id: str
    title: str
    aircraft: str
    ata: str
    status: str = "pending"
    assigned_to: str | None = None
    due_date: str


class WorkPackageUpdate(BaseModel):
    title: str | None = None
    aircraft: str | None = None
    ata: str | None = None
    status: str | None = None
    assigned_to: str | None = None  # burada kullanıcı id'si beklenir (ör: U-TECH-1)
    due_date: str | None = None


@app.get("/work-packages/{id}")
def get_work_package_by_id(id: str):
    w = crud.get_work_package(id)
    if not w:
        raise HTTPException(status_code=404, detail="Not found")
    return w


@app.get("/users/{user_id}/work-packages")
def list_work_packages_for_user(user_id: str):
    """
    Mobil tarafta 'bana atanan işler' ekranı için.
    assigned_to = user_id olan tüm iş paketlerini döner.
    """
    # Kullanıcı var mı kontrolü (hatalı id için 404 verelim)
    if not crud.get_user(user_id):
        raise HTTPException(status_code=404, detail="User not found")

    all_wp = get_work_packages()
    filtered = [
        wp for wp in all_wp
        if (wp.get("assigned_to") or "") == user_id
    ]
    return {"work_packages": filtered}


@app.get("/personnel/{personnel_id}/work-packages")
def list_work_packages_for_personnel(personnel_id: str):
    """
    Çalışan (personel) listesinden seçilen kişiye atanmış iş paketleri.
    Bu personel ile eşleşen user (linked_user_id) bulunur, onun assigned_to olduğu işler döner.
    """
    user = crud.get_user_by_personnel_id(personnel_id)
    if not user:
        return {"work_packages": []}
    all_wp = get_work_packages()
    filtered = [
        wp for wp in all_wp
        if (wp.get("assigned_to") or "") == user["id"]
    ]
    return {"work_packages": filtered}


@app.post("/work-packages")
def create_work_package_endpoint(req: WorkPackageCreate):
    return crud.create_work_package(req.model_dump())


@app.put("/work-packages/{id}")
def update_work_package_endpoint(id: str, req: WorkPackageUpdate):
    data = {k: v for k, v in req.model_dump().items() if v is not None}

    # Önce mevcut durumu oku (status değişimini tespit etmek için)
    before = crud.get_work_package(id)
    w = crud.update_work_package(id, data)
    if not w:
        raise HTTPException(status_code=404, detail="Not found")

    # Eğer status approved'a geçtiyse, otomatik olarak completed kaydı ekle
    try:
        prev_status = (before or {}).get("status")
        new_status = w.get("status")
        if prev_status != "approved" and new_status == "approved":
            # Demo için: tamamlanma anı = şimdi, başlama = şimdi - 1 gün
            from datetime import datetime, timedelta

            now = datetime.utcnow()
            started_at = now - timedelta(days=1)

            cp = CompletedWorkPackage(
                id=f"CP-{id}",
                work_package_id=id,
                sprint_id=None,
                started_at=started_at.isoformat(),
                completed_at=now.isoformat(),
                first_pass_success=True,
                rework_count=0,
                planned_minutes=None,
                actual_minutes=None,
                assigned_personnel_count=None,
                criticality=None,
            )
            add_completed(cp)
    except Exception:
        # KPI'lar için otomatik kayıt başarısız olsa bile ana update çalışmaya devam etsin.
        pass

    return w


@app.delete("/work-packages/{id}")
def delete_work_package_endpoint(id: str):
    ok = crud.delete_work_package(id)
    if not ok:
        raise HTTPException(status_code=404, detail="Not found")
    return {"ok": True}
