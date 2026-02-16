"""Plan QA / Review Agent."""
from app.agents.base import get_default_llm

class PlanReviewAgent:
    def __init__(self):
        self.llm = get_default_llm()

    def run(self, tech_context: str, work_package: str, resource_plan: str) -> str:
        system = "Sen QA ve Safety mühendisisin. Teknik bağlam, iş paketi ve kaynak planını inceleyip kısa QA raporu yaz."
        user = f"TEKNİK BAĞLAM:\n{tech_context}\n\nİŞ PAKETİ:\n{work_package}\n\nKAYNAK PLANI:\n{resource_plan}"
        r = self.llm.invoke([{"role": "system", "content": system}, {"role": "user", "content": user}])
        return r.content
