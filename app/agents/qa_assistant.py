"""Q&A Assistant Agent."""
from app.agents.base import get_default_llm
from app.agents.guard import GuardAgent

class QAAssistantAgent:
    def __init__(self, retriever, web_search_tool=None, guard_agent: GuardAgent | None = None):
        self.llm = get_default_llm()
        self.retriever = retriever
        self.web_search_tool = web_search_tool
        self.guard_agent = guard_agent or GuardAgent()

    def run(self, question: str) -> str:
        intent = self.guard_agent.detect_intent(question)
        if intent == "small_talk":
            return self.guard_agent.small_talk_reply(question)
        if intent == "out_of_scope":
            return self.guard_agent.out_of_scope_reply(question)
        rag = ""
        if self.retriever:
            try:
                docs = self.retriever.invoke(question)
                rag = "\n\n".join(d.page_content for d in docs[:5])
            except Exception:
                pass
        web = ""
        if self.web_search_tool:
            try:
                web = self.web_search_tool.invoke(question)
            except Exception:
                pass
        system = (
            "Sen uçak bakım eğitmenisin. Soruyu ## Özet, ## Detay, ## Kaynaklar formatında yanıtla.\n\n"
            "KESIN KURALLAR - ASLA YAPMA:\n"
            "- ASCII çizim, ASCII art, ASCII diagram, ASCII table, metin tablosu çizimi\n"
            "- Çizim adımları, şema çizme talimatları, kağıt üzerine çizim rehberi\n"
            "- Teknik çizim formatları (CAD, DXF, ölçekli çizim talimatları)\n"
            "- Görsel/şema/resim üretme talimatları veya açıklamaları\n\n"
            "NEDEN: Parça görseli sistem tarafından otomatik üretilip kullanıcıya gösterilir. "
            "Sen sadece metin açıklaması, teknik bilgi, fonksiyon, bakım notları ve referanslar ver. "
            "Görsel üretimi için kullanıcıya talimat verme veya çizim yapma."
        )
        user = f"SORU: {question}\n\nRAG:\n{rag or '(yok)'}\n\nWEB:\n{web or '(yok)'}"
        r = self.llm.invoke([{"role": "system", "content": system}, {"role": "user", "content": user}])
        answer = r.content or ""
        status, _ = self.guard_agent.moderate_answer(question, answer)
        if status == "block":
            return "Bu konuda detay veremiyorum. Genel güvenlik prensipleri hakkında sorabilirsin."
        return answer
