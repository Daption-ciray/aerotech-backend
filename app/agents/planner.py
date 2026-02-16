"""Work Package Planner Agent."""
from app.agents.base import get_default_llm

class WorkPackagePlannerAgent:
    def __init__(self):
        self.llm = get_default_llm()

    def run(self, fault_description: str, tech_context: str) -> str:
        system = "Sen Part-145 uyumlu uçak bakım planlayıcısısın. Sadece geçerli JSON üret."
        user = f"TEKNİK BAĞLAM:\n{tech_context}\n\nARIZA: {fault_description}\n\nİş paketi JSON'u (work_package_id, aircraft_type, component, steps, total_estimated_minutes) üret."
        r = self.llm.invoke([{"role": "system", "content": system}, {"role": "user", "content": user}])
        return r.content
