# Backend Agent Yapısı – Debug Raporu

## Dosya yapısı (app/agents/)

| Dosya | Sınıf/Fonksiyon | Durum |
|-------|------------------|--------|
| `base.py` | `get_default_llm()` | OK – tüm agent'lar bunu kullanıyor |
| `search_rag.py` | `SearchRAGAgent` | OK – retriever + web_search_tool |
| `planner.py` | `WorkPackagePlannerAgent` | OK – fault_description, tech_context → JSON |
| `resource.py` | `ResourceComplianceAgent` | OK – resource_tool.invoke(work_package_json) |
| `plan_review.py` | `PlanReviewAgent` | OK – tech_context, work_package, resource_plan → QA raporu |
| `guard.py` | `GuardAgent` | OK – detect_intent, small_talk_reply, out_of_scope_reply, moderate_answer |
| `qa_assistant.py` | `QAAssistantAgent` | OK – Guard + retriever + web + LLM |
| `sprint_planning.py` | `SprintPlanningAgent` | OK – BacklogItem, add_items, list_items, update_item_status, find_item_by_title |
| `efficiency.py` | `EfficiencyAgent` | OK – compute_efficiency_summary, list_completed, get_work_packages |
| `orchestrator.py` | `OrchestratorAgent`, `OrchestratorDecision` | OK – main.py /qa'da part_diagram için kullanılıyor |
| `part_visual.py` | `generate_part_diagram`, `verify_part_image` | OK – main.py'de import ve kullanım var |

## Import zinciri

- `app/main.py` → `from .agents import SearchRAGAgent, WorkPackagePlannerAgent, ...` (hepsi `app/agents/__init__.py` üzerinden).
- `app/chains.py` → `search_agent.run()`, `planner_agent.run()`, `resource_agent.run()`, `qa_agent.run()` – imzalar yeni modüllerdeki sınıflarla uyumlu.
- `app/setup.py` → `get_retriever()` (None), `get_web_search_tool()` (Tool), `get_resource_tool()` (Tool) – main startup'ta kullanılıyor.

## Runtime test (yapılan)

- `from app.main import app` → **OK** (import hatası yok).
- Backend başlatıldı; **GET /** 200, **GET /rag/status** 200, **GET /resources/personnel** 200.
- **POST /qa** `{"question":"Merhaba"}` → 200, cevap metni döndü.

## Öneriler

1. **Debug log yolu:** `main.py` ve `chains.py` içinde `.cursor/debug.log` için path `Path(__file__).resolve().parent.parent.parent / ".cursor" / "debug.log"` gibi proje köküne göre hesaplanabilir; şu an sabit path çalışıyor.
2. **SearchRAGAgent:** Şu an sadece retriever + web; ileride OpenAI Vector Store Search tekrar eklenirse `search_rag.py` içinde `_openai_file_search_context` benzeri bir katman eklenebilir.
3. **Linter:** `app/agents` altında hata bildirimi yok.

Sonuç: Yeni agent dosya yapısı tutarlı, importlar ve endpoint'ler çalışıyor.
