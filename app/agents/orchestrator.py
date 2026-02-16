"""
Orchestrator Agent – tüm Q&A akışını yönetir.

Tek karar noktası: intent (nereye yönlendir), RAG/cevap gerekli mi, parça görseli gerekli mi.
Buna göre sonraki adımlar (Guard, QA agent, Part visual) çalıştırılır.
"""
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field

from app.config import settings
from app.agents.base import get_default_llm


class OrchestratorDecision(BaseModel):
    """Orchestrator'ın tek seferde verdiği karar – tüm akış buna göre ilerler."""

    intent: str = Field(
        description="Yönlendirme: 'maintenance' (teknik/bakım sorusu), 'small_talk' (selam, teşekkür vb.), 'out_of_scope' (alakasız/hassas konu)."
    )
    needs_rag_answer: bool = Field(
        description="Metin cevabı için RAG + QA agent çalışsın mı? Teknik sorularda True."
    )
    needs_part_diagram: bool = Field(
        description="Soruda somut bir parça/komponent geçiyorsa ve görsel faydalı olacaksa True."
    )
    part_name: str | None = Field(
        default=None,
        description="Görseli üretilecek parça/komponent adı (İngilizce). needs_part_diagram=True ise MUTLAKA doldur, boş bırakma. Örnek: 'elevator çiz' → 'elevator', 'trim tab göster' → 'trim tab'.",
    )


class OrchestratorAgent:
    """Tüm Q&A pipeline'ını orchestrate eder: intent + RAG gerekli mi + parça görseli gerekli mi."""

    def __init__(self):
        self.llm = ChatOpenAI(model=settings.LLM_MODEL, temperature=0).with_structured_output(OrchestratorDecision)

    def run(self, question: str) -> OrchestratorDecision:
        system = (
            "Sen havacılık Q&A sisteminin orchestrator'ısın. Her soru için TEK bir karar ver:\n"
            "1) intent: 'maintenance' = uçak bakımı/teknik soru, 'small_talk' = selam/teşekkür/sohbet, 'out_of_scope' = alakasız veya hassas.\n"
            "2) needs_rag_answer: Teknik metin cevabı gerekiyorsa True. Sadece selam veya yalnızca görsel isteği bile olsa teknik sorularda True yapabilirsin.\n"
            "3) needs_part_diagram: ÖNEMLİ – Soruda somut bir parça/komponent adı geçiyorsa MUTLAKA True yap. "
            "Kullanıcı 'çiz', 'draw', 'resim', 'görsel', 'şema', 'göster', 'show', 'image' dediyse veya parça hakkında soru soruyorsa görsel üretilecek.\n"
            "4) part_name: needs_part_diagram=True ise MUTLAKA doldur, boş bırakma. Sorudaki parça adını İngilizce olarak yaz. "
            "Türkçe parça adı varsa İngilizce karşılığını yaz. Örnekler:\n"
            "  - 'elevator çiz' / 'dümen çiz' / 'yükseklik dümeni' → part_name='elevator'\n"
            "  - 'trim tab göster' / 'trim tabı' → part_name='trim tab'\n"
            "  - 'pitot nedir' / 'pitot tüp' → part_name='pitot tube'\n"
            "  - 'flap resmi' / 'flap' → part_name='flap'\n"
            "  - 'rudder' / 'dikey dümen' / 'yön dümeni' → part_name='rudder'\n"
            "  - 'aileron' / 'kanatçık' → part_name='aileron'\n"
            "  - 'iniş takımı' / 'landing gear' → part_name='landing gear'\n"
            "  - 'stabilizer' / 'stabilizatör' / 'yatay stabilizer' → part_name='horizontal stabilizer'\n"
            "  - 'motor' / 'engine' → part_name='aircraft engine'\n"
            "  - 'kanat' / 'wing' → part_name='wing'\n"
            "  - 'gövde' / 'fuselage' → part_name='fuselage'\n"
            "Sadece genel parça adını yaz, 'çiz', 'göster' gibi fiilleri dahil etme.\n"
            "Kurallar: Parça adı geçen her teknik/maintenance sorusunda needs_part_diagram=True ve part_name MUTLAKA doldur; boş bırakma."
        )
        msg = HumanMessage(content=question)
        return self.llm.invoke([SystemMessage(content=system), msg])
