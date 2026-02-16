"""Guard Agent – intent ve moderasyon."""
from app.agents.base import get_default_llm

class GuardAgent:
    def __init__(self):
        self.llm = get_default_llm()

    def detect_intent(self, question: str) -> str:
        r = self.llm.invoke([
            {"role": "system", "content": "Sadece şunlardan birini dön: maintenance, small_talk, out_of_scope. Uçak bakımı/teknik soru ise maintenance."},
            {"role": "user", "content": question},
        ])
        t = (r.content or "").strip().lower()
        if "maintenance" in t: return "maintenance"
        if "small" in t: return "small_talk"
        return "out_of_scope"

    def small_talk_reply(self, question: str) -> str:
        r = self.llm.invoke([
            {"role": "system", "content": "Kısa, nazik karşılama; uçak bakım asistanı olduğunu belirt."},
            {"role": "user", "content": question},
        ])
        return r.content or "Merhaba, nasıl yardımcı olabilirim?"

    def out_of_scope_reply(self, question: str) -> str:
        return "Bu konuda yardımcı olamıyorum. Sadece uçak bakımı ve teknik konularda destek veriyorum."

    def moderate_answer(self, question: str, answer: str) -> tuple[str, str]:
        r = self.llm.invoke([
            {"role": "system", "content": "Cevap uygunsa sadece 'ok', değilse 'block: gerekçe' yaz."},
            {"role": "user", "content": f"SORU: {question}\n\nCEVAP: {answer}"},
        ])
        t = (r.content or "").strip().lower()
        if t.startswith("ok"): return "ok", ""
        return "block", t.split(":", 1)[-1].strip() if ":" in t else ""