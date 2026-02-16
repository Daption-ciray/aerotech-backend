"""
AeroTech Agentic Hub – FastAPI entry point.
"""

from pathlib import Path
import json
import logging
import sqlite3
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
    OrchestratorAgent,
    generate_part_diagram,
    verify_part_image,
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


class PartDiagramResponse(BaseModel):
    image_url: str | None = None
    image_base64: str | None = None
    part_name: str
    verified: bool
    reason: str | None = None


# Parça adı geçen sorularda orkestratör atlamışsa yine de görsel üretmek için anahtar kelime eşlemesi
# Uzun ifadeler önce (elevator trim, trim tab) ki kısa "elevator" ile çakışmasın
# Format: (türkçe_veya_ingilizce_anahtar_kelime, ingilizce_parça_adı)
_PART_KEYWORDS = [
    # Kumanda yüzeyleri / Control Surfaces
    ("elevator trim", "elevator trim"),
    ("trim tab", "trim tab"),
    ("trim tabı", "trim tab"),
    ("elevator trim tab", "elevator trim tab"),
    ("elevator", "elevator"),
    ("dümen", "elevator"),
    ("yükseklik dümeni", "elevator"),
    ("yatay dümen", "elevator"),
    ("rudder", "rudder"),
    ("dikey dümen", "rudder"),
    ("yön dümeni", "rudder"),
    ("aileron", "aileron"),
    ("kanatçık", "aileron"),
    ("flap", "flap"),
    ("flap", "aircraft flap"),
    ("flap", "wing flap"),
    ("flap", "landing flap"),
    ("flap", "takeoff flap"),
    ("flap", "leading edge flap"),
    ("flap", "trailing edge flap"),
    ("flap", "slat"),
    ("slat", "slat"),
    ("leading edge slat", "slat"),
    ("spoiler", "spoiler"),
    ("spoyler", "spoiler"),
    ("speed brake", "speed brake"),
    ("hız freni", "speed brake"),
    ("air brake", "air brake"),
    ("hava freni", "air brake"),
    ("kumanda yüzeyi", "control surface"),
    ("kumanda yüzeyleri", "control surface"),
    
    # Stabilizer / Stabilizatör
    ("stabilizer", "horizontal stabilizer"),
    ("stabilizatör", "horizontal stabilizer"),
    ("yatay stabilizer", "horizontal stabilizer"),
    ("yatay stabilizatör", "horizontal stabilizer"),
    ("horizontal stabilizer", "horizontal stabilizer"),
    ("vertical stabilizer", "vertical stabilizer"),
    ("dikey stabilizer", "vertical stabilizer"),
    ("dikey stabilizatör", "vertical stabilizer"),
    ("fin", "vertical stabilizer"),
    ("kuyruk", "empennage"),
    ("empennage", "empennage"),
    
    # Trim / Trim Sistemleri
    ("trim", "trim tab"),
    ("trim", "trim actuator"),
    ("trim aktüatör", "trim actuator"),
    ("trim actuator", "trim actuator"),
    ("jackscrew", "jackscrew trim actuator"),
    ("trim jackscrew", "jackscrew trim actuator"),
    ("trim tekeri", "trim wheel"),
    ("trim wheel", "trim wheel"),
    ("trim switch", "trim switch"),
    ("trim anahtarı", "trim switch"),
    
    # Pitot-Static / Hız ve Yükseklik Ölçümü
    ("pitot", "pitot tube"),
    ("pitot tüp", "pitot tube"),
    ("pitot tube", "pitot tube"),
    ("static port", "static port"),
    ("statik port", "static port"),
    ("static port", "static port"),
    ("airspeed indicator", "pitot static system"),
    ("hız göstergesi", "pitot static system"),
    ("altimeter", "altimeter"),
    ("yükseklik göstergesi", "altimeter"),
    ("altimetre", "altimeter"),
    
    # Landing Gear / İniş Takımı
    ("landing gear", "landing gear"),
    ("iniş takımı", "landing gear"),
    ("landing gear", "main landing gear"),
    ("ana iniş takımı", "main landing gear"),
    ("nose gear", "nose landing gear"),
    ("burun iniş takımı", "nose landing gear"),
    ("nose wheel", "nose landing gear"),
    ("burun tekeri", "nose landing gear"),
    ("main wheel", "main landing gear"),
    ("ana teker", "main landing gear"),
    ("oleo strut", "landing gear strut"),
    ("oleo", "landing gear strut"),
    ("shock absorber", "landing gear strut"),
    ("amortisör", "landing gear strut"),
    ("landing gear door", "landing gear door"),
    ("iniş takımı kapısı", "landing gear door"),
    ("gear door", "landing gear door"),
    
    # Engine / Motor
    ("engine", "aircraft engine"),
    ("motor", "aircraft engine"),
    ("turbine", "turbine engine"),
    ("türbin", "turbine engine"),
    ("turbofan", "turbofan engine"),
    ("turbofan", "turbofan"),
    ("propeller", "propeller"),
    ("pervane", "propeller"),
    ("prop", "propeller"),
    ("nacelle", "nacelle"),
    ("motor kaportası", "nacelle"),
    ("engine mount", "engine mount"),
    ("motor montajı", "engine mount"),
    ("firewall", "firewall"),
    ("yangın duvarı", "firewall"),
    
    # Wing / Kanat
    ("wing", "wing"),
    ("kanat", "wing"),
    ("wing spar", "wing spar"),
    ("kanat kirişi", "wing spar"),
    ("spar", "wing spar"),
    ("wing rib", "wing rib"),
    ("kanat nervürü", "wing rib"),
    ("rib", "wing rib"),
    ("wing skin", "wing skin"),
    ("kanat kaplaması", "wing skin"),
    ("wing tip", "wing tip"),
    ("kanat ucu", "wing tip"),
    ("winglet", "winglet"),
    ("wing fence", "wing fence"),
    ("kanat çiti", "wing fence"),
    
    # Fuselage / Gövde
    ("fuselage", "fuselage"),
    ("gövde", "fuselage"),
    ("cockpit", "cockpit"),
    ("kokpit", "cockpit"),
    ("cabin", "cabin"),
    ("kabin", "cabin"),
    ("cargo compartment", "cargo compartment"),
    ("kargo bölümü", "cargo compartment"),
    ("bulkhead", "bulkhead"),
    ("bölme duvarı", "bulkhead"),
    
    # Hydraulic / Hidrolik
    ("hydraulic system", "hydraulic system"),
    ("hidrolik sistem", "hydraulic system"),
    ("hydraulic pump", "hydraulic pump"),
    ("hidrolik pompa", "hydraulic pump"),
    ("hydraulic actuator", "hydraulic actuator"),
    ("hidrolik aktüatör", "hydraulic actuator"),
    ("hydraulic cylinder", "hydraulic cylinder"),
    ("hidrolik silindir", "hydraulic cylinder"),
    ("hydraulic reservoir", "hydraulic reservoir"),
    ("hidrolik deposu", "hydraulic reservoir"),
    
    # Electrical / Elektrik
    ("electrical system", "electrical system"),
    ("elektrik sistemi", "electrical system"),
    ("generator", "generator"),
    ("jeneratör", "generator"),
    ("alternator", "alternator"),
    ("alternatör", "alternator"),
    ("battery", "battery"),
    ("batarya", "battery"),
    ("akü", "battery"),
    ("bus bar", "bus bar"),
    ("elektrik barası", "bus bar"),
    
    # Avionics / Avyonik
    ("avionics", "avionics"),
    ("avyonik", "avionics"),
    ("autopilot", "autopilot"),
    ("otopilot", "autopilot"),
    ("flight management system", "flight management system"),
    ("uçuş yönetim sistemi", "flight management system"),
    ("fms", "flight management system"),
    ("transponder", "transponder"),
    ("transponder", "transponder"),
    ("adf", "adf"),
    ("adf", "automatic direction finder"),
    ("vOR", "vor"),
    ("vor", "vor"),
    ("ils", "ils"),
    ("ils", "instrument landing system"),
    ("gps", "gps"),
    ("gps", "global positioning system"),
    
    # Fuel System / Yakıt Sistemi
    ("fuel system", "fuel system"),
    ("yakıt sistemi", "fuel system"),
    ("fuel tank", "fuel tank"),
    ("yakıt tankı", "fuel tank"),
    ("fuel pump", "fuel pump"),
    ("yakıt pompası", "fuel pump"),
    ("fuel filter", "fuel filter"),
    ("yakıt filtresi", "fuel filter"),
    ("fuel line", "fuel line"),
    ("yakıt hattı", "fuel line"),
    ("fuel valve", "fuel valve"),
    ("yakıt valfi", "fuel valve"),
    
    # Environmental / Çevre Sistemi
    ("environmental system", "environmental control system"),
    ("çevre sistemi", "environmental control system"),
    ("pressurization system", "pressurization system"),
    ("basınçlandırma sistemi", "pressurization system"),
    ("air conditioning", "air conditioning system"),
    ("klima", "air conditioning system"),
    ("heater", "heater"),
    ("ısıtıcı", "heater"),
    
    # Brake System / Fren Sistemi
    ("brake system", "brake system"),
    ("fren sistemi", "brake system"),
    ("brake", "brake"),
    ("fren", "brake"),
    ("brake disc", "brake disc"),
    ("fren diski", "brake disc"),
    ("brake pad", "brake pad"),
    ("fren balata", "brake pad"),
    ("brake caliper", "brake caliper"),
    ("fren kaliperi", "brake caliper"),
    
    # Navigation Lights / Navigasyon Işıkları
    ("navigation light", "navigation light"),
    ("navigasyon ışığı", "navigation light"),
    ("nav light", "navigation light"),
    ("strobe light", "strobe light"),
    ("stroboskop", "strobe light"),
    ("beacon", "beacon"),
    ("işaret ışığı", "beacon"),
    ("beacon light", "beacon"),
    
    # Antenna / Anten
    ("antenna", "antenna"),
    ("anten", "antenna"),
    ("antenna", "communication antenna"),
    ("iletişim anteni", "communication antenna"),
    
    # Other Common Parts / Diğer Yaygın Parçalar
    ("radome", "radome"),
    ("radom", "radome"),
    ("windshield", "windshield"),
    ("ön cam", "windshield"),
    ("windshield", "windshield"),
    ("canopy", "canopy"),
    ("kanopi", "canopy"),
    ("throttle", "throttle"),
    ("gaz kolu", "throttle"),
    ("throttle lever", "throttle"),
    ("yoke", "control yoke"),
    ("kumanda kolu", "control yoke"),
    ("control column", "control column"),
    ("kumanda kolonu", "control column"),
    ("pedal", "rudder pedal"),
    ("pedal", "rudder pedal"),
    ("rudder pedal", "rudder pedal"),
    ("dümen pedalı", "rudder pedal"),
]


def _detect_part_name_from_question(question: str) -> str | None:
    """Soruda bilinen parça adı geçiyorsa görsel üretimi için İngilizce parça adını döner."""
    if not question or not question.strip():
        return None
    q = question.strip().lower()
    for keyword, part_name in _PART_KEYWORDS:
        if keyword in q:
            return part_name
    return None


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
    app.state.orchestrator_agent = OrchestratorAgent()

    # region agent log
    try:
        log_path = Path("/Users/daption-ciray/Desktop/Project/THY/.cursor/debug.log")
        payload = {
            "id": f"log_{int(time.time() * 1000)}",
            "timestamp": int(time.time() * 1000),
            "location": "app/main.py:startup_event",
            "message": "startup_end",
            "data": {
                "has_retriever": retriever is not None,
                "has_web_search": web_search_tool is not None,
                "has_resource_tool": resource_tool is not None,
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

@app.post("/plan")
def plan_maintenance(req: PlanningRequest):
    """Arıza açıklamasından uçtan uca bakım planı + QA incelemesi üretir."""
    try:
        result = run_planning_pipeline(
            app.state.search_agent,
            app.state.planner_agent,
            app.state.resource_agent,
            req.fault_description,
            qa_agent=app.state.plan_review_agent,
        )
        return result
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Planlama hatası: {str(e)}. OPENAI_API_KEY ve agent ayarlarını kontrol edin.",
        )


@app.post("/plan/review")
def review_plan(req: PlanReviewRequest):
    """
    Harici olarak sağlanan teknik bağlam + iş paketi + kaynak planı için
    yalnızca QA / kalite kontrol raporu üretir.
    """
    qa_review = app.state.plan_review_agent.run(
        req.tech_context,
        req.work_package,
        req.resource_plan,
    )
    return {"qa_review": qa_review}


@app.post("/qa")
def qa_assistant(req: QARequest):
    """
    Tüm akış Orchestrator üzerinden: intent + needs_rag_answer + needs_part_diagram.
    Buna göre Guard (small_talk/out_of_scope), QA agent (RAG cevap), Part visual (Imagen + VLM) çalıştırılır.
    """
    question = req.question
    orchestrator = getattr(app.state, "orchestrator_agent", None)
    guard = getattr(app.state, "guard_agent", None)
    qa_agent = getattr(app.state, "qa_agent", None)

    if not orchestrator:
        answer = qa_agent.run(question) if qa_agent else ""
        return {"answer": answer, "part_diagram": None}

    try:
        decision = orchestrator.run(question)
    except Exception:
        decision = None

    intent = (decision.intent or "").strip().lower() if decision else "maintenance"

    # Parça görseli: small_talk/out_of_scope olsa bile soruda parça adı geçiyorsa yine de üret
    part_diagram_early = None
    part_name_early = _detect_part_name_from_question(question) if question else None
    if part_name_early:
        try:
            gen = generate_part_diagram(part_name_early)
            image_base64 = gen.get("image_base64") if isinstance(gen, dict) else None
            if image_base64 and "error" not in gen:
                try:
                    vlm = verify_part_image(image_url=None, image_base64=image_base64, part_name=part_name_early)
                except Exception:
                    vlm = {"verified": False, "reason": None}
                part_diagram_early = PartDiagramResponse(
                    image_base64=image_base64,
                    part_name=part_name_early,
                    verified=vlm.get("verified", False),
                    reason=vlm.get("reason"),
                )
            elif "error" in gen:
                import logging
                logging.warning("part_diagram early fail: %s", gen.get("error"))
        except Exception as e:
            import logging
            logging.warning("part_diagram early exception: %s", e)

    if "small" in intent or intent == "small_talk":
        reply = guard.small_talk_reply(question) if guard else "Merhaba, nasıl yardımcı olabilirim?"
        return {"answer": reply, "part_diagram": part_diagram_early.model_dump() if part_diagram_early else None}
    if "out" in intent or intent == "out_of_scope":
        reply = guard.out_of_scope_reply(question) if guard else "Bu konuda yardımcı olamıyorum."
        return {"answer": reply, "part_diagram": part_diagram_early.model_dump() if part_diagram_early else None}

    answer = ""
    if decision and decision.needs_rag_answer and qa_agent:
        answer = qa_agent.run(question)

    # Parça görseli: orkestratör kararı veya soruda parça adı geçiyorsa üret
    part_diagram = None
    part_name = (decision.part_name or "").strip() if decision else ""
    want_diagram = decision and decision.needs_part_diagram and part_name
    if not want_diagram and question:
        fallback = _detect_part_name_from_question(question)
        if fallback:
            want_diagram = True
            part_name = fallback
    if want_diagram and part_name:
        try:
            gen = generate_part_diagram(part_name)
            image_base64 = gen.get("image_base64") if isinstance(gen, dict) else None
            if image_base64 and "error" not in gen:
                try:
                    vlm = verify_part_image(image_url=None, image_base64=image_base64, part_name=part_name)
                except Exception:
                    vlm = {"verified": False, "reason": None}
                part_diagram = PartDiagramResponse(
                    image_base64=image_base64,
                    part_name=part_name,
                    verified=vlm.get("verified", False),
                    reason=vlm.get("reason"),
                )
            elif "error" in gen:
                import logging
                logging.warning("part_diagram fail: %s", gen.get("error"))
        except Exception as e:
            import logging
            logging.warning("part_diagram exception: %s", e)
            part_diagram = None

    # Erken path başardıysa ama late path başaramadıysa fallback kullan
    if part_diagram is None and part_diagram_early:
        part_diagram = part_diagram_early

    return {"answer": answer, "part_diagram": part_diagram.model_dump() if part_diagram else None}


@app.post("/sprint/plan")
def sprint_planning(req: SprintPlanRequest):
    """
    Sprint planning / backlog yönetim isteğini doğal dille alır,
    SprintPlanningAgent aracılığıyla backlog üzerinde operasyon (create/list/update)
    uygular.
    """
    result = app.state.sprint_agent.run(req.request)
    return result


@app.get("/")
def root():
    return {"message": "AeroTech Agentic Hub API is running."}


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
    """Personel listesi. Her personel için linked_user_id (users.personnel_id eşleşmesi) eklenir."""
    personnel_list = get_personnel()
    enriched = []
    for p in personnel_list:
        uid = crud.get_user_by_personnel_id(p["id"])
        enriched.append({**p, "linked_user_id": uid["id"] if uid else p.get("linked_user_id")})
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
    linked_user_id: str | None = None


class PersonnelUpdate(BaseModel):
    name: str | None = None
    role: str | None = None
    ratings: list[str] | None = None
    specializations: list[str] | None = None
    shift: str | None = None
    availability: str | None = None
    linked_user_id: str | None = None


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


@app.post("/work-packages")
def create_work_package_endpoint(req: WorkPackageCreate):
    try:
        data = req.model_dump()
        if data.get("assigned_to") == "":
            data["assigned_to"] = None
        try:
            return crud.create_work_package(data)
        except sqlite3.IntegrityError:
            data["id"] = f"{data['id']}-{int(time.time() * 1000)}"
            return crud.create_work_package(data)
    except HTTPException:
        raise
    except Exception as e:
        logging.exception("create_work_package failed")
        raise HTTPException(status_code=500, detail=str(e))


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
