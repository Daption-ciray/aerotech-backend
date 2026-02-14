"""
AeroTech Agentic Hub – Agent definitions.

Modern rewrite: deprecated initialize_agent / AgentType / ConversationBufferMemory
tamamen kaldırıldı.  Yerine saf ChatOpenAI + class-based orchestration kullanılıyor.
"""

from pathlib import Path
import json
import time
import os

from langchain_openai import ChatOpenAI
from openai import OpenAI

from .config import settings
from .setup import get_aviation_glossary_tool
from .sprint import BacklogItem, add_items, find_item_by_title, list_items, update_item_status
from .analytics import list_completed, compute_efficiency_summary
from .services.data import get_efficiency_metrics, get_work_packages
from .chunk_index import ChunkRecord, load_chunk_index


# ---------------------------------------------------------------------------
# Ortak LLM factory
# ---------------------------------------------------------------------------

def _default_llm():
    return ChatOpenAI(model=settings.LLM_MODEL, temperature=0)


# ---------------------------------------------------------------------------
# 1) Search & RAG Agent
# ---------------------------------------------------------------------------

class SearchRAGAgent:
    """
    Teknik arama ajanı.
    Kaynaklar:
      - FAA / AMT PDF korpusu (RAG retriever)
      - Wikipedia / Tavily web arama
      - Aviation glossary (Skybrary benzeri)
    """

    def __init__(self, retriever, web_search_tool=None, chunks: list[ChunkRecord] | None = None):
        self.llm = _default_llm()
        self.retriever = retriever
        self.web_search_tool = web_search_tool
        self.glossary_tool = get_aviation_glossary_tool()
        # LLM-özetli chunk index (embedding'siz RAG)
        self.chunks: list[ChunkRecord] = chunks or []
        # OpenAI file_search (managed vector store) entegrasyonu
        api_key = settings.OPENAI_API_KEY or os.getenv("OPENAI_API_KEY")
        self._oa_client = OpenAI(api_key=api_key) if api_key else None
        self._vector_store_id = settings.OPENAI_VECTOR_STORE_ID or os.getenv("OPENAI_VECTOR_STORE_ID")

    def _openai_file_search_context(self, query: str) -> str:
        """
        OpenAI Vector Store üzerinden semantik arama yapar (Vector Store Search API).
        Chat Completions 'file_search' tool'u sadece Responses/Assistants API'de desteklendiği için
        burada doğrudan vector_stores.search kullanıyoruz.
        """
        if not self._oa_client or not self._vector_store_id:
            return ""

        try:
            # Vector Store Search API (GET /vector_stores/{id}/search)
            page = self._oa_client.vector_stores.search(
                vector_store_id=self._vector_store_id,
                query=query,
                max_num_results=15,
            )
            parts = []
            for item in page:
                for content in getattr(item, "content", []) or []:
                    if getattr(content, "text", None):
                        parts.append(content.text)
            return "\n\n".join(parts) if parts else ""
        except Exception:
            return ""

    def get_file_search_diagnostics(self, query: str) -> dict:
        """
        OpenAI vector store file_search'ün çalışıp çalışmadığını kontrol etmek için.
        Döner: file_search_used, file_search_context_length, file_search_preview, error
        """
        out = {
            "file_search_used": False,
            "file_search_context_length": 0,
            "file_search_preview": "",
            "error": None,
        }
        if not self._oa_client or not self._vector_store_id:
            out["error"] = "OPENAI_API_KEY veya OPENAI_VECTOR_STORE_ID eksik"
            return out
        try:
            ctx = self._openai_file_search_context(query)
            out["file_search_used"] = len(ctx) > 0
            out["file_search_context_length"] = len(ctx)
            out["file_search_preview"] = (ctx[:600] + "...") if len(ctx) > 600 else ctx
        except Exception as e:
            out["error"] = str(e)
        return out

    def run(self, query: str) -> str:
        # 0) OpenAI file_search bağlamı (varsa)
        fs_context = ""
        try:
            fs_context = self._openai_file_search_context(query)
        except Exception:
            fs_context = ""

        # 1) RAG – FAA/AMT dokümanları
        # Öncelik: hibrit yaklaşım (embedding + chunk index), sonra fallback'ler
        rag_context = ""

        if self.chunks and self.retriever:
            # 0) Embedding ile kaba aday seç (Chroma retriever)
            docs = self.retriever.invoke(query)
            candidate_ids = {d.metadata.get("id") for d in docs if d.metadata.get("id")}
            candidate_chunks = [c for c in self.chunks if c.id in candidate_ids] or self.chunks

            # a) Basit keyword skoru ile bu adaylar arasında sıralama
            lower_q = query.lower()
            tokens = [t for t in lower_q.replace(",", " ").split() if len(t) > 3]

            def _score(rec: ChunkRecord) -> int:
                txt = rec.summary.lower()
                return sum(txt.count(t) for t in tokens) or 0

            scored = sorted(candidate_chunks, key=_score, reverse=True)
            top_candidates = scored[:40]  # LLM'e göstereceğimiz özetler

            # b) LLM'den en alakalı chunk id'lerini seçmesini iste
            from pydantic import BaseModel
            import json as _json

            class ChunkSelection(BaseModel):
                chunk_ids: list[str]

            summaries = [{"id": c.id, "summary": c.summary} for c in top_candidates]

            selection_prompt = (
                "Kullanıcının sorusuna en iyi cevap verebilecek chunk özetlerini seç.\n"
                "Sadece aşağıdaki JSON formatında dön:\n"
                '{ "chunk_ids": ["chunk-00001", \"...\"] }\n\n'
                "Chunk özetleri:\n"
                f"{_json.dumps(summaries, ensure_ascii=False, indent=2)}\n"
                f"SORU: {query}"
            )

            sel_resp = self.llm.invoke(
                [
                    {
                        "role": "system",
                        "content": "Sadece geçerli JSON döndür.",
                    },
                    {"role": "user", "content": selection_prompt},
                ]
            )

            try:
                data = _json.loads(sel_resp.content)
                selection = ChunkSelection.model_validate(data)
                selected_ids = set(selection.chunk_ids)
            except Exception:
                # JSON parse başarısızsa, skorlanmış ilk 5 chunk'ı kullan
                selected_ids = {c.id for c in top_candidates[:5]}

            selected_texts = [c.text for c in self.chunks if c.id in selected_ids]
            rag_context = "\n\n".join(selected_texts)

        elif self.chunks:
            # Sadece chunk index varsa: pure LLM summary-based seçim
            lower_q = query.lower()
            tokens = [t for t in lower_q.replace(",", " ").split() if len(t) > 3]

            def _score(rec: ChunkRecord) -> int:
                txt = rec.summary.lower()
                return sum(txt.count(t) for t in tokens) or 0

            scored = sorted(self.chunks, key=_score, reverse=True)
            top_candidates = scored[:40]

            from pydantic import BaseModel
            import json as _json

            class ChunkSelection(BaseModel):
                chunk_ids: list[str]

            summaries = [{"id": c.id, "summary": c.summary} for c in top_candidates]

            selection_prompt = (
                "Kullanıcının sorusuna en iyi cevap verebilecek chunk özetlerini seç.\n"
                "Sadece aşağıdaki JSON formatında dön:\n"
                '{ "chunk_ids": ["chunk-00001", \"...\"] }\n\n'
                "Chunk özetleri:\n"
                f"{_json.dumps(summaries, ensure_ascii=False, indent=2)}\n"
                f"SORU: {query}"
            )

            sel_resp = self.llm.invoke(
                [
                    {
                        "role": "system",
                        "content": "Sadece geçerli JSON döndür.",
                    },
                    {"role": "user", "content": selection_prompt},
                ]
            )

            try:
                data = _json.loads(sel_resp.content)
                selection = ChunkSelection.model_validate(data)
                selected_ids = set(selection.chunk_ids)
            except Exception:
                selected_ids = {c.id for c in top_candidates[:5]}

            selected_texts = [c.text for c in self.chunks if c.id in selected_ids]
            rag_context = "\n\n".join(selected_texts)

        elif self.retriever:
            # Eski embedding-only RAG fallback
            docs = self.retriever.invoke(query)
            rag_context = "\n\n".join(d.page_content for d in docs[:5])

        # 2) Web search
        web_context = ""
        if self.web_search_tool:
            try:
                web_context = self.web_search_tool.invoke(query)
            except Exception:
                web_context = ""

        # 3) Aviation glossary
        glossary_context = ""
        try:
            glossary_context = self.glossary_tool.invoke(query)
        except Exception:
            glossary_context = ""

        # 4) LLM ile sentezle
        system_prompt = (
            "Sen kıdemli bir uçak bakım teknik araştırma asistanısın. "
            "FAA, AMT ve EASA Part-145 standartlarına hakimsin. "
            "Verilen kaynaklardan toplanan bilgileri kullanarak teknik ve kesin bir analiz üret. "
            "Kaynaklarına referans ver."
        )

        user_prompt = (
            f"SORU / ARIZA: {query}\n\n"
            f"--- OpenAI File Search (Vector Store) ---\n{fs_context or '(veri yok)'}\n\n"
            f"--- FAA/AMT CHUNK'LARI (Yerel RAG) ---\n{rag_context or '(veri yok)'}\n\n"
            f"--- WEB ARAMA SONUÇLARI ---\n{web_context or '(veri yok)'}\n\n"
            f"--- HAVACILIK SÖZLÜĞÜ ---\n{glossary_context or '(veri yok)'}\n\n"
            "Yukarıdaki tüm kaynakları sentezleyerek teknik analiz yap."
        )

        response = self.llm.invoke([
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ])
        return response.content


# ---------------------------------------------------------------------------
# 2) Work Package Planner Agent
# ---------------------------------------------------------------------------

class WorkPackagePlannerAgent:
    """İş paketi (work package) oluşturan planlayıcı ajan."""

    def __init__(self):
        self.llm = _default_llm()

    def run(self, fault_description: str, tech_context: str) -> str:
        system_prompt = (
            "Sen Part-145 farkındalığı olan kıdemli bir uçak bakım planlayıcısısın. "
            "Agile/Scrum bakışıyla iş paketleri oluşturursun."
        )

        user_prompt = (
            "Aşağıdaki teknik bağlamı ve arıza açıklamasını kullanarak, "
            "SADECE GEÇERLİ JSON üreten bir iş paketi (work package) oluştur.\n\n"
            "JSON şemasını AYNEN şu şekilde kullan:\n"
            "{\n"
            '  "work_package_id": "string",\n'
            '  "aircraft_type": "string",\n'
            '  "component": "string",\n'
            '  "fault_description": "string",\n'
            '  "steps": [\n'
            "    {\n"
            '      "id": "string",\n'
            '      "title": "string",\n'
            '      "description": "string",\n'
            '      "estimated_minutes": 0,\n'
            '      "required_ratings": ["string"],\n'
            '      "required_tools": ["string"],\n'
            '      "required_parts": ["string"],\n'
            '      "dependencies": ["string"]\n'
            "    }\n"
            "  ],\n"
            '  "risks": ["string"],\n'
            '  "total_estimated_minutes": 0\n'
            "}\n\n"
            "Kurallar:\n"
            "- Sadece geçerli JSON üret, açıklama yazma.\n"
            "- Her adımın estimated_minutes alanını pozitif tam sayı yap.\n"
            "- total_estimated_minutes tüm adımların toplamı olsun.\n\n"
            f"TEKNİK BAĞLAM:\n{tech_context}\n\n"
            f"ARIZA AÇIKLAMASI: {fault_description}"
        )

        response = self.llm.invoke([
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ])
        return response.content


# ---------------------------------------------------------------------------
# 3) Resource & Compliance Agent
# ---------------------------------------------------------------------------

class ResourceComplianceAgent:
    """Kaynak planlama ve Part-145 uyum kontrolü ajanı."""

    def __init__(self, resource_tool=None):
        self.llm = _default_llm()
        self.resource_tool = resource_tool

    def run(self, work_package_json: str) -> str:
        # 1) Resource tool ile envanter eşleşmesi
        resource_data = ""
        if self.resource_tool:
            try:
                resource_data = self.resource_tool.invoke(work_package_json)
            except Exception as e:
                resource_data = f"Resource tool error: {e}"

        # 2) LLM ile değerlendirme
        system_prompt = (
            "Sen EASA Part-145 uyumlu bir kaynak planlama uzmanısın. "
            "İş paketi gereksinimlerini mevcut kaynaklarla karşılaştırarak "
            "uygun personel, tool ve parça ataması yaparsın."
        )

        user_prompt = (
            f"İŞ PAKETİ:\n{work_package_json}\n\n"
            f"MEVCUT KAYNAK VERİSİ:\n{resource_data or '(veri yok)'}\n\n"
            "Yukarıdaki bilgilere göre:\n"
            "1. Uygun personel ataması (rating uyumu)\n"
            "2. Gerekli tool/ekipman durumu\n"
            "3. Parça stok durumu ve varsa tedarik uyarıları\n"
            "4. Part-145 uyum notları\n"
            "içeren bir kaynak planı oluştur."
        )

        response = self.llm.invoke([
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ])
        return response.content


# ---------------------------------------------------------------------------
# 4) Plan QA / Review Agent
# ---------------------------------------------------------------------------

class PlanReviewAgent:
    """
    Diğer ajanların (Search, Planner, Resource) ürettiği çıktıları
    kalite kontrol / güvence (QA) perspektifiyle inceleyen destekçi ajan.

    Görevleri:
      - Teknik tutarlılık kontrolü
      - Eksik adım / risk analizi
      - Kaynak planlama tutarlılığı (personel, tool, parça)
      - Safety / Part-145 uyumuna dair geri bildirim
    """

    def __init__(self):
        self.llm = _default_llm()

    def run(self, tech_context: str, work_package: str, resource_plan: str) -> str:
        system_prompt = (
            "Sen uçak bakım operasyonlarında çalışan kıdemli bir QA (Quality Assurance) "
            "ve Safety/Compliance mühendisisin. Search & RAG, Planner ve Resource "
            "ajanlarının ürettiği çıktıları denetleyip, teknik doğruluk, bütünlük ve "
            "emniyet (Safety) açısından yorumluyorsun."
        )

        user_prompt = (
            "Aşağıda üç farklı ajan çıktısı var:\n\n"
            "1) TEKNİK BAĞLAM (Search & RAG Agent):\n"
            f"{tech_context}\n\n"
            "2) İŞ PAKETİ (Work Package Planner Agent – JSON veya metin):\n"
            f"{work_package}\n\n"
            "3) KAYNAK PLANI (Resource & Compliance Agent):\n"
            f"{resource_plan}\n\n"
            "Bu çıktıları bir bütün olarak değerlendir ve aşağıdaki başlıklarla bir QA raporu üret:\n"
            "## Özet\n"
            "- Genel değerlendirme (kısa)\n\n"
            "## Teknik Tutarlılık\n"
            "- Search çıktısı ile iş paketi adımları uyumlu mu?\n"
            "- Kritik flight control / safety konuları atlanmış mı?\n\n"
            "## Kaynak ve Uyum Analizi\n"
            "- Personel rating / yetki uyumu\n"
            "- Tool ve parça planlamasının gerçekçi olup olmadığı\n"
            "- Part-145 / Safety açısından göze çarpan riskler\n\n"
            "## İyileştirme Önerileri\n"
            "- Eksik adımlar, eklenmesi gereken kontroller\n"
            "- Riske dönük öneriler\n"
            "- Üst yönetime raporlanması gereken noktalar\n"
        )

        response = self.llm.invoke(
            [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ]
        )
        return response.content


# ---------------------------------------------------------------------------
# 5) Guard / Policy Agent (intent + moderation)
# ---------------------------------------------------------------------------

class GuardAgent:
    """
    Q&A asistanı için koruma (guard) katmanı.

    Görevleri:
      - Kullanıcı niyetini sınıflandırmak:
        - maintenance  : bakım / teknik soru
        - small_talk   : selamlaşma, teşekkür vb.
        - out_of_scope : alakasız, riskli veya yetki dışı konular
      - Gerekirse cevabı moderate etmek (basit policy check).
    """

    def __init__(self):
        # İstersen burada daha ucuz / farklı bir model de kullanabilirsin.
        self.llm = _default_llm()

    def detect_intent(self, question: str) -> str:
        system_prompt = (
            "Sen bir niyet sınıflandırma ajanısın. "
            "Yalnızca şu etiketlerden BİRİNİ döndür:\n"
            '- "maintenance"\n'
            '- "small_talk"\n'
            '- "out_of_scope"\n'
        )
        user_prompt = (
            "Soru:\n"
            f"{question}\n\n"
            "Kurallar:\n"
            '- Eğer soru uçak bakımı, flight controls, Part-145, teknik bileşenler '
            'veya havacılık güvenliği ile ilgiliyse "maintenance" de.\n'
            '- Eğer soru sadece selamlaşma, teşekkür, hal-hatır sorma vb. ise '
            '"small_talk" de.\n'
            '- Eğer soru politika, genel sohbet, alakasız veya hassas konular içeriyorsa '
            '"out_of_scope" de.\n'
            "Sadece etiketi yaz, başka bir şey yazma."
        )
        resp = self.llm.invoke(
            [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ]
        )
        label = resp.content.strip().lower()
        if "maintenance" in label:
            return "maintenance"
        if "small" in label:
            return "small_talk"
        if "out_of_scope" in label or "out of scope" in label:
            return "out_of_scope"
        # Varsayılanı güvenli tarafta tut
        return "out_of_scope"

    def small_talk_reply(self, question: str) -> str:
        system_prompt = (
            "Sen AeroTech Agentic Hub'ın nazik bir karşılama asistanısın. "
            "Kısa, samimi ama profesyonel bir dille cevap ver; "
            "konuyu mümkünse uçak bakımı / sistemin yeteneklerine bağla."
        )
        user_prompt = (
            f"Kullanıcı şöyle dedi: {question}\n\n"
            "Kısa bir karşılama / cevap ver ve ona neleri yapabildiğini 1-2 cümleyle anlat."
        )
        resp = self.llm.invoke(
            [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ]
        )
        return resp.content

    def out_of_scope_reply(self, question: str) -> str:
        return (
            "Ben AeroTech Agentic Hub içinde sadece uçak bakımı, flight control yüzeyleri, "
            "Part-145 uyumu ve ilgili teknik/operasyonel konularda yardımcı oluyorum. "
            "Bu soru benim kapsamımın dışında kalıyor."
        )

    def moderate_answer(self, question: str, answer: str) -> tuple[str, str]:
        """
        Basit bir policy check: 'ok' veya 'block' + gerekçe.
        Şimdilik sadece metin tabanlı inceleme yapıyor.
        """
        system_prompt = (
            "Sen bir güvenlik/policy denetim ajanısın. "
            "Uçak bakımıyla ilgili cevapları değerlendiriyorsun. "
            "Yalnızca 'ok' veya 'block' döndür; eğer 'block' ise kısa bir gerekçe ekle."
        )
        user_prompt = (
            f"SORU: {question}\n\n"
            f"CEVAP: {answer}\n\n"
            "Eğer cevap bakım güvenliği, Part-145 uyumu veya hassas prosedürler açısından "
            "sakıncalı bir detay içeriyorsa 'block: <kısa_gerekçe>' yaz. "
            "Aksi halde sadece 'ok' yaz."
        )
        resp = self.llm.invoke(
            [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ]
        )
        txt = resp.content.strip().lower()
        if txt.startswith("ok"):
            return "ok", ""
        # örn: "block: çok detaylı prosedür veriyor"
        if txt.startswith("block"):
            reason = txt.split(":", 1)[1].strip() if ":" in txt else ""
            return "block", reason
        # Anlaşılamayan durumda temkinli ol
        return "block", "policy_check_uncertain"


# ---------------------------------------------------------------------------
# 6) Genel Q&A Assistant Agent (kullanıcı soruları için)
# ---------------------------------------------------------------------------

class QAAssistantAgent:
    """Genel havacılık bakım Q&A asistanı (kullanıcı sorularını cevaplar)."""

    def __init__(self, retriever, web_search_tool=None, guard_agent: GuardAgent | None = None):
        self.llm = _default_llm()
        self.retriever = retriever
        self.web_search_tool = web_search_tool
        self.glossary_tool = get_aviation_glossary_tool()
        self.guard_agent = guard_agent or GuardAgent()

    def run(self, question: str) -> str:
        # 0) Intent detection
        intent = self.guard_agent.detect_intent(question)

        # region agent log
        try:
            log_path = Path("/Users/daption-ciray/Desktop/Project/THY/.cursor/debug.log")
            payload = {
                "id": f"log_{int(time.time() * 1000)}",
                "timestamp": int(time.time() * 1000),
                "location": "app/agents.py:QAAssistantAgent.run",
                "message": "qa_intent_detected",
                "data": {
                    "intent": intent,
                    "question_preview": question[:120],
                },
                "runId": "e2e",
                "hypothesisId": "H3",
            }
            log_path.parent.mkdir(parents=True, exist_ok=True)
            with log_path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(payload) + "\n")
        except Exception:
            pass
        # endregion

        if intent == "small_talk":
            return self.guard_agent.small_talk_reply(question)
        if intent == "out_of_scope":
            return self.guard_agent.out_of_scope_reply(question)

        # 1) RAG
        rag_context = ""
        if self.retriever:
            docs = self.retriever.invoke(question)
            rag_context = "\n\n".join(d.page_content for d in docs[:5])

        # 2) Web search
        web_context = ""
        if self.web_search_tool:
            try:
                web_context = self.web_search_tool.invoke(question)
            except Exception:
                web_context = ""

        # 3) Glossary
        glossary_context = ""
        try:
            glossary_context = self.glossary_tool.invoke(question)
        except Exception:
            glossary_context = ""

        # 4) LLM yanıt
        system_prompt = (
            "Sen deneyimli bir uçak bakım eğitmeni ve teknik danışmansın. "
            "FAA, EASA ve genel havacılık bakım standartlarına hakimsin. "
            "Soruları açık, teknik doğru ve kaynak göstererek yanıtlarsın. "
            "Yanıtını şu formatta ver:\n"
            "## Özet\n(kısa cevap)\n\n"
            "## Teknik Detaylar\n(ayrıntılı açıklama)\n\n"
            "## Kaynaklar\n(referanslar)"
        )

        user_prompt = (
            f"SORU: {question}\n\n"
            f"--- FAA/AMT DOKÜMANLARI ---\n{rag_context or '(veri yok)'}\n\n"
            f"--- WEB ARAMA SONUÇLARI ---\n{web_context or '(veri yok)'}\n\n"
            f"--- HAVACILIK SÖZLÜĞÜ ---\n{glossary_context or '(veri yok)'}"
        )

        response = self.llm.invoke(
            [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ]
        )
        answer = response.content

        # 5) Policy / guard check
        status, reason = self.guard_agent.moderate_answer(question, answer)
        if status == "ok":
            return answer

        # Cevap riskliyse kullanıcıya daha güvenli bir mesaj dön
        safe_msg = (
            "Bu konuyla ilgili çok detaylı veya hassas bilgilere girmemem gerekiyor. "
            "Yine de genel prensipler ve güvenlik odaklı üst seviye açıklamalar hakkında "
            "soru sorabilirsin."
        )
        if reason:
            safe_msg += f"\n\n(Not: İç değerlendirme sonucu: {reason})"
        return safe_msg


# ---------------------------------------------------------------------------
# 7) Sprint Planning Agent (Product Backlog / Sprint Backlog)
# ---------------------------------------------------------------------------

class SprintPlanningAgent:
    """
    Sprint artefact'larını (Product Backlog, Sprint Backlog) yöneten ajan.

    Doğal dili önce bir operasyon JSON'una çevirir (function calling benzeri),
    sonra bu JSON'u gerçek Python fonksiyonlarına uygular.
    """

    def __init__(self):
        self.llm = _default_llm()

    def _plan_to_operations(self, request: str) -> dict:
        """
        Kullanıcı isteğini aşağıdaki JSON formatına map eder.
        LLM mevcut item listesini görür; böylece doğru item_id seçebilir.
        """
        from app.db import crud
        wps = crud.list_work_packages()
        wp_to_backlog = {"pending": "todo", "in_progress": "in_progress", "approved": "done"}
        items_context = "\n".join(
            f"  - id: {r['id']}, title: {r['title']}, status: {wp_to_backlog.get(r['status'], r['status'])}"
            for r in wps
        ) or "  (Henüz item yok)"

        system_prompt = (
            "Sen bir Sprint Planning yardımcı ajanısın. Kullanıcı isteğini SADECE tek bir JSON objesine çevirirsin. "
            "JSON DIŞINDA HİÇBİR ŞEY yazma. Cevabın doğrudan { ile başlamalı."
        )
        user_prompt = (
            "Mevcut backlog item'ları (bunlardan birine referans verildiğinde id'sini kullan):\n"
            f"{items_context}\n\n"
            "Kullanıcı isteği:\n"
            f"{request}\n\n"
            "Operasyonlar:\n"
            '1) "create_items": Yeni item ekle. "items" dizisi doldur.\n'
            '2) "list_items": Listele. "filters" kullan.\n'
            '3) "update_status": Bir item\'ın durumunu güncelle. '
            'Yukarıdaki listeden eşleşen item\'ın id\'sini "update.item_id" olarak yaz. '
            '"update.status" zorunlu: todo | in_progress | done. '
            '(Türkçe: beklemede->todo, devam ediyor->in_progress, tamamlandı->done)\n\n'
            "Yalnızca geçerli bir JSON dön. Örnek update_status: {\"operation\":\"update_status\",\"update\":{\"item_id\":\"xxx\",\"status\":\"in_progress\"}}"
        )
        resp = self.llm.invoke(
            [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ]
        )
        import json
        import re

        raw = (resp.content or "").strip()
        # Markdown code block temizle
        m = re.search(r"```(?:json)?\s*([\s\S]*?)```", raw)
        if m:
            raw = m.group(1).strip()
        try:
            ops = json.loads(raw)
        except json.JSONDecodeError:
            ops = {"operation": "list_items", "filters": {}}
        return ops

    def run(self, request: str) -> dict:
        ops = self._plan_to_operations(request)
        op = ops.get("operation")

        if op == "create_items":
            raw_items = ops.get("items", [])
            new_items: list[BacklogItem] = []
            for it in raw_items:
                new_items.append(
                    BacklogItem(
                        id=it.get("id") or "",
                        type=it.get("type", "product"),
                        title=it.get("title", ""),
                        description=it.get("description", ""),
                        status=it.get("status", "todo"),
                        sprint=it.get("sprint"),
                        priority=it.get("priority"),
                        estimate_hours=it.get("estimate_hours"),
                        owner=it.get("owner"),
                    )
                )
            # id boşsa burada üret
            for i in new_items:
                if not i.id:
                    import uuid
                    i.id = str(uuid.uuid4())
            created_wps = add_items(new_items)
            from app.db import crud
            all_items = crud.list_work_packages()
            return {
                "operation": "create_items",
                "created": [i.id for i in new_items],
                "backlog_size": len(all_items),
            }

        if op == "update_status":
            upd = ops.get("update", {}) or {}
            item_id = upd.get("item_id")
            item_title = upd.get("item_title")
            status_raw = upd.get("status") or upd.get("target_status") or ""
            # Türkçe ve alternatif ifadeleri normalize et
            _status_map = {
                "todo": "todo", "pending": "todo", "beklemede": "todo", "bekleyen": "todo",
                "in_progress": "in_progress", "in progress": "in_progress", "devam ediyor": "in_progress",
                "done": "done", "tamamlandı": "done", "tamamlanan": "done", "completed": "done",
            }
            status = _status_map.get((status_raw or "").strip().lower(), (status_raw or "").strip().lower() or None)
            # LLM status döndürmezse, orijinal istekten çıkar: "devam ediyora al" -> in_progress
            if not status or status not in ("todo", "in_progress", "done"):
                req_lower = request.lower()
                if "devam ediyor" in req_lower or "in progress" in req_lower or "sürüyor" in req_lower:
                    status = "in_progress"
                elif "tamamlandı" in req_lower or "tamamla" in req_lower or "bitti" in req_lower or "done" in req_lower:
                    status = "done"
                elif "beklemede" in req_lower or "bekleyen" in req_lower or "todo" in req_lower or "pending" in req_lower:
                    status = "todo"
            if not status or status not in ("todo", "in_progress", "done"):
                return {"operation": "update_status", "error": "status eksik veya geçersiz"}
            if not item_id and item_title:
                found = find_item_by_title(item_title)
                if found:
                    item_id = found.id
            if not item_id:
                return {"operation": "update_status", "error": "item_id veya item_title (başlık) eksik"}
            updated = update_item_status(item_id, status)
            if not updated:
                return {"operation": "update_status", "error": "item bulunamadı"}
            return {
                "operation": "update_status",
                "item": updated,
            }

        # Varsayılan: list_items
        flt = (ops.get("filters") or {}) if isinstance(ops.get("filters"), dict) else {}
        items = list_items(
            type=flt.get("type"),
            sprint=flt.get("sprint"),
            status=flt.get("status"),
        )
        from dataclasses import asdict
        return {
            "operation": "list_items",
            "items": [asdict(i) for i in items],
        }


# ---------------------------------------------------------------------------
# 8) Efficiency Agent (verimlilik analiz + öneriler)
# ---------------------------------------------------------------------------

class EfficiencyAgent:
    """
    Tamamlanan iş paketlerinden üretilen metrikleri okuyup,
    üst seviye özet + iyileştirme önerileri üreten ajan.
    """

    def __init__(self):
        self.llm = _default_llm()

    def run(self) -> dict:
        metrics = compute_efficiency_summary()
        completed = list_completed()
        # completed_work_packages boşsa work_packages tablosundan veri kullan
        wp_list = get_work_packages()
        fallback_metrics = get_efficiency_metrics()
        approved = sum(1 for p in wp_list if p.get("status") == "approved")
        in_progress = sum(1 for p in wp_list if p.get("status") == "in_progress")
        total_wp = len(wp_list) or 1

        if not metrics.get("total_completed") and not completed:
            metrics = {
                "total_completed": approved,
                "total_work_packages": len(wp_list),
                "approved_count": approved,
                "in_progress_count": in_progress,
                "first_pass_rate": round((approved / total_wp) * 100, 1) if total_wp else 0,
                "avg_completion_days": fallback_metrics.get("avg_completion_days"),
                "throughput_per_day": fallback_metrics.get("tasks_per_hour"),
                "monthly_completed": [],
                "kaynak": "work_packages (SQLite) – completed_work_packages henüz dolu değil",
            }
        else:
            metrics["approved_count"] = approved
            metrics["total_work_packages"] = len(wp_list)
            metrics["in_progress_count"] = in_progress

        wp_summary = {
            "total_completed": metrics.get("total_completed", 0),
            "approved_in_work_packages": approved,
            "in_progress": in_progress,
            "samples": [
                {
                    "id": i.id,
                    "sprint_id": i.sprint_id,
                    "first_pass_success": i.first_pass_success,
                    "rework_count": i.rework_count,
                    "criticality": i.criticality,
                }
                for i in completed[:10]
            ],
        }
        if not wp_summary["samples"] and wp_list:
            wp_summary["work_packages_ornek"] = [
                {"id": p.get("id"), "title": p.get("title"), "status": p.get("status")}
                for p in wp_list[:10]
            ]

        import json as _json
        system_prompt = (
            "Sen uçak bakım operasyonlarında verimlilik odaklı bir YBS uzmanısın. "
            "Aşağıdaki sayısal metrikler ve örnek iş paketleri üzerinden, "
            "yönetim için kısa bir özet ve iyileştirme önerileri üret."
        )
        user_prompt = (
            "METRİKLER:\n"
            f"{_json.dumps(metrics, ensure_ascii=False, indent=2)}\n\n"
            "ÖRNEK İŞ PAKETLERİ:\n"
            f"{_json.dumps(wp_summary, ensure_ascii=False, indent=2)}\n\n"
            "Çıktı formatı:\n"
            "{\n"
            '  "summary": "kısa metin",\n'
            '  "suggestions": ["madde 1", "madde 2", "..."]\n'
            "}\n"
        )

        resp = self.llm.invoke(
            [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ]
        )

        try:
            data = _json.loads(resp.content)
        except Exception:
            data = {
                "summary": resp.content,
                "suggestions": [],
            }
        data["metrics"] = metrics
        return data

